"""Tests for NanobotGateway infrastructure adapter.

Verifies that the gateway correctly:
- Reports active channels based on nanobot configuration
- Converts and publishes outbound messages to the nanobot bus
- Does not start real channels (all nanobot internals are mocked)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.channel import ChannelType, MediaAttachment, OutboundMessage
from app.infrastructure.external.channels.nanobot_gateway import (
    _CHANNEL_MAP,
    _CHANNEL_REVERSE,
    NanobotGateway,
)

_PATCH_CM = "app.infrastructure.external.channels.nanobot_gateway.ChannelManager"


@pytest.fixture()
def mock_router() -> MagicMock:
    """MessageRouter mock."""
    router = MagicMock()
    router.route_inbound = AsyncMock(return_value=AsyncMock())
    return router


def _make_mock_cm(enabled: list[str]) -> MagicMock:
    """Build a mock ChannelManager with the given enabled channel names."""
    mock_cm = MagicMock()
    mock_cm.enabled_channels = enabled
    mock_cm.start_all = AsyncMock()
    mock_cm.stop_all = AsyncMock()
    return mock_cm


@pytest.fixture()
def gateway_telegram(mock_router: MagicMock) -> NanobotGateway:
    """Gateway with only Telegram configured (ChannelManager is mocked)."""
    with patch(_PATCH_CM) as mock_cls:
        mock_cls.return_value = _make_mock_cm(["telegram"])
        return NanobotGateway(
            message_router=mock_router,
            telegram_token="123:FAKE_TOKEN",
            telegram_allowed=["user1", "user2"],
        )


@pytest.fixture()
def gateway_empty(mock_router: MagicMock) -> NanobotGateway:
    """Gateway with no channels configured."""
    with patch(_PATCH_CM) as mock_cls:
        mock_cls.return_value = _make_mock_cm([])
        return NanobotGateway(message_router=mock_router)


@pytest.fixture()
def gateway_multi(mock_router: MagicMock) -> NanobotGateway:
    """Gateway with Telegram + Discord + Slack configured."""
    with patch(_PATCH_CM) as mock_cls:
        mock_cls.return_value = _make_mock_cm(["telegram", "discord", "slack"])
        return NanobotGateway(
            message_router=mock_router,
            telegram_token="123:FAKE",
            discord_token="DISCORD_FAKE",
            slack_bot_token="xoxb-FAKE",
            slack_app_token="xapp-FAKE",
        )


class TestGetActiveChannels:
    """Tests for get_active_channels()."""

    def test_telegram_only(self, gateway_telegram: NanobotGateway) -> None:
        """Telegram configured returns [ChannelType.TELEGRAM]."""
        active = gateway_telegram.get_active_channels()
        assert active == [ChannelType.TELEGRAM]

    def test_no_channels(self, gateway_empty: NanobotGateway) -> None:
        """No channels configured returns empty list."""
        active = gateway_empty.get_active_channels()
        assert active == []

    def test_multi_channels(self, gateway_multi: NanobotGateway) -> None:
        """Multiple channels returns all mapped types."""
        active = gateway_multi.get_active_channels()
        assert set(active) == {
            ChannelType.TELEGRAM,
            ChannelType.DISCORD,
            ChannelType.SLACK,
        }

    def test_unmapped_channels_excluded(self, mock_router: MagicMock) -> None:
        """Nanobot channels without a Pythinker mapping are excluded."""
        with patch(_PATCH_CM) as mock_cls:
            mock_cls.return_value = _make_mock_cm(["telegram", "feishu"])
            gw = NanobotGateway(
                message_router=mock_router,
                telegram_token="123:FAKE",
            )

        active = gw.get_active_channels()
        assert active == [ChannelType.TELEGRAM]


class TestSendToChannel:
    """Tests for send_to_channel()."""

    @pytest.mark.asyncio()
    async def test_converts_and_publishes(self, gateway_telegram: NanobotGateway) -> None:
        """Outbound message is converted to nanobot format and published to the bus."""
        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            chat_id="chat_123",
            content="Hello from Pythinker!",
            reply_to="msg_456",
        )

        gateway_telegram._bus.publish_outbound = AsyncMock()
        await gateway_telegram.send_to_channel(message)

        gateway_telegram._bus.publish_outbound.assert_awaited_once()
        nb_msg = gateway_telegram._bus.publish_outbound.call_args[0][0]
        assert nb_msg.channel == "telegram"
        assert nb_msg.chat_id == "chat_123"
        assert nb_msg.content == "Hello from Pythinker!"
        assert nb_msg.reply_to == "msg_456"

    @pytest.mark.asyncio()
    async def test_media_urls_converted(self, gateway_telegram: NanobotGateway) -> None:
        """Media attachments are converted to URL strings for nanobot."""
        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            chat_id="chat_123",
            content="Here is a file",
            media=[
                MediaAttachment(url="https://example.com/file.pdf", mime_type="application/pdf"),
                MediaAttachment(url="https://example.com/img.png", mime_type="image/png"),
            ],
        )

        gateway_telegram._bus.publish_outbound = AsyncMock()
        await gateway_telegram.send_to_channel(message)

        nb_msg = gateway_telegram._bus.publish_outbound.call_args[0][0]
        assert nb_msg.media == [
            "https://example.com/file.pdf",
            "https://example.com/img.png",
        ]

    @pytest.mark.asyncio()
    async def test_unmapped_channel_skipped(self, gateway_telegram: NanobotGateway) -> None:
        """Messages for channels without a nanobot mapping are silently skipped."""
        message = OutboundMessage(
            channel=ChannelType.WEB,
            chat_id="chat_123",
            content="This should be skipped",
        )

        gateway_telegram._bus.publish_outbound = AsyncMock()
        await gateway_telegram.send_to_channel(message)
        gateway_telegram._bus.publish_outbound.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_metadata_preserved(self, gateway_telegram: NanobotGateway) -> None:
        """Metadata dict is passed through to the nanobot message."""
        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            chat_id="chat_123",
            content="Test",
            metadata={"thread_id": "t_789", "parse_mode": "Markdown"},
        )

        gateway_telegram._bus.publish_outbound = AsyncMock()
        await gateway_telegram.send_to_channel(message)

        nb_msg = gateway_telegram._bus.publish_outbound.call_args[0][0]
        assert nb_msg.metadata == {"thread_id": "t_789", "parse_mode": "Markdown"}


class TestChannelMapping:
    """Verify _CHANNEL_MAP and _CHANNEL_REVERSE are consistent."""

    def test_reverse_is_inverse(self) -> None:
        """_CHANNEL_REVERSE is the exact inverse of _CHANNEL_MAP."""
        for nb_name, pt_type in _CHANNEL_MAP.items():
            assert _CHANNEL_REVERSE[pt_type] == nb_name

    def test_all_mapped_types_are_valid(self) -> None:
        """Every mapped ChannelType is a valid enum member."""
        for pt_type in _CHANNEL_MAP.values():
            assert isinstance(pt_type, ChannelType)


class TestLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio()
    async def test_start_creates_consumer_task(self, gateway_telegram: NanobotGateway) -> None:
        """start() creates a consumer task."""
        gateway_telegram._consume_inbound = AsyncMock()
        await gateway_telegram.start()
        assert gateway_telegram._consumer_task is not None

        # Clean up
        await gateway_telegram.stop()

    @pytest.mark.asyncio()
    async def test_stop_cancels_consumer(self, gateway_telegram: NanobotGateway) -> None:
        """stop() cancels the consumer task and calls stop_all."""
        gateway_telegram._consume_inbound = AsyncMock()
        await gateway_telegram.start()
        assert gateway_telegram._consumer_task is not None

        await gateway_telegram.stop()
        assert gateway_telegram._consumer_task is None
        gateway_telegram._channel_manager.stop_all.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_stop_without_start(self, gateway_telegram: NanobotGateway) -> None:
        """stop() is safe to call even if start() was never called."""
        await gateway_telegram.stop()
        gateway_telegram._channel_manager.stop_all.assert_awaited_once()


class TestPollWatchdog:
    @pytest.mark.asyncio()
    async def test_watchdog_does_not_warn_during_recent_inflight_processing(
        self,
        gateway_telegram: NanobotGateway,
    ) -> None:
        """Recent in-flight message routing should not emit poll-stall warnings."""
        gateway_telegram.POLL_WATCHDOG_TIMEOUT = 0.05
        gateway_telegram.INBOUND_PROCESSING_WARN_TIMEOUT = 1.0
        gateway_telegram._inbound_processing_started_monotonic = asyncio.get_running_loop().time()

        with patch("app.infrastructure.external.channels.nanobot_gateway.logger.warning") as warning_mock:
            watchdog_task = asyncio.create_task(gateway_telegram._run_poll_watchdog())
            await asyncio.sleep(0.13)
            watchdog_task.cancel()
            await watchdog_task

        warning_mock.assert_not_called()

    @pytest.mark.asyncio()
    async def test_watchdog_warns_when_inflight_processing_exceeds_threshold(
        self,
        gateway_telegram: NanobotGateway,
    ) -> None:
        """Very long in-flight processing should still emit stall warnings."""
        gateway_telegram.POLL_WATCHDOG_TIMEOUT = 0.05
        gateway_telegram.INBOUND_PROCESSING_WARN_TIMEOUT = 0.10
        gateway_telegram._inbound_processing_started_monotonic = asyncio.get_running_loop().time() - 1.0

        with patch("app.infrastructure.external.channels.nanobot_gateway.logger.warning") as warning_mock:
            watchdog_task = asyncio.create_task(gateway_telegram._run_poll_watchdog())
            await asyncio.sleep(0.08)
            watchdog_task.cancel()
            await watchdog_task

        assert warning_mock.call_count >= 1
