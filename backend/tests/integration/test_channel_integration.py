"""Integration tests for the channel pipeline.

Verifies end-to-end behaviour across:
- InboundMessage → MessageRouter → AgentService → OutboundMessage flow
- nanobot package import availability
- Slash-command session reset via MessageRouter
- Auto-registration of unknown senders via UserChannelRepository
- NanobotGateway conformance to the ChannelGateway protocol
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage
from app.domain.services.channels.message_router import (
    MessageRouter,
    UserChannelRepository,
)

# ---------------------------------------------------------------------------
# Shared helpers — fake event / session objects
# ---------------------------------------------------------------------------


class _SessionStatus(str, Enum):
    RUNNING = "running"


class _FakeSession:
    def __init__(self, session_id: str = "sess-int-001") -> None:
        self.id = session_id
        self.status = _SessionStatus.RUNNING
        self.created_at = datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC)


class _FakeMessageEvent:
    type = "message"
    role = "assistant"
    message = "Hello! How can I help you today?"


class _FakePlanEvent:
    type = "plan"


class _FakeDoneEvent:
    type = "done"


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_inbound(
    content: str = "Hello, agent!",
    channel: ChannelType = ChannelType.TELEGRAM,
    sender_id: str = "tg-user-integration",
    chat_id: str = "tg-chat-integration",
    session_key_override: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        session_key_override=session_key_override,
    )


def _make_repo(
    user_id: str | None = "user-integration-abc",
    session_id: str | None = None,
) -> AsyncMock:
    """Build an AsyncMock that satisfies the UserChannelRepository protocol."""
    repo = AsyncMock(spec=UserChannelRepository)
    repo.get_user_by_channel = AsyncMock(return_value=user_id)
    repo.create_channel_user = AsyncMock(return_value="user-new-" + uuid.uuid4().hex[:6])
    repo.get_session_key = AsyncMock(return_value=session_id)
    repo.set_session_key = AsyncMock()
    repo.clear_session_key = AsyncMock()
    repo.link_channel_to_user = AsyncMock(return_value=None)
    repo.migrate_sessions = AsyncMock()
    repo.migrate_session_ownership = AsyncMock()
    repo.touch_last_inbound_at = AsyncMock()
    repo.touch_last_outbound_at = AsyncMock()
    repo.get_session_activity = AsyncMock(return_value=None)
    repo.set_session_context_summary = AsyncMock()
    return repo


def _make_agent_service(
    events: list[Any] | None = None,
    session: Any | None = None,
) -> AsyncMock:
    """Build an AsyncMock for AgentService with an async-generator chat()."""
    svc = AsyncMock()

    resolved_events = events if events is not None else [_FakeMessageEvent()]
    resolved_session = session or _FakeSession()

    async def _fake_chat(**kwargs: Any):
        for evt in resolved_events:
            yield evt

    svc.chat = _fake_chat
    svc.create_session = AsyncMock(return_value=resolved_session)
    svc.get_session = AsyncMock(return_value=resolved_session)
    svc.stop_session = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Test 1: Full channel pipeline greeting
# ---------------------------------------------------------------------------


class TestFullChannelPipelineGreeting:
    """End-to-end: InboundMessage → MessageRouter → AgentService → OutboundMessage."""

    @pytest.mark.asyncio
    async def test_full_channel_pipeline_greeting(self) -> None:
        """A greeting message reaches AgentService and the reply is routed back correctly.

        Verifies:
        - MessageRouter resolves the user identity via the repo.
        - A new session is created when none exists.
        - Agent events flow through and the assistant reply is surfaced.
        - The OutboundMessage is addressed to the originating channel and chat_id.
        - Internal events (plan, done) are silently discarded.
        """
        repo = _make_repo(user_id="user-integration-abc", session_id=None)
        agent_svc = _make_agent_service(
            events=[
                _FakePlanEvent(),  # internal — must be filtered
                _FakeMessageEvent(),  # user-visible reply
                _FakeDoneEvent(),  # internal — must be filtered
            ]
        )
        router = MessageRouter(agent_svc, repo)

        inbound = _make_inbound("Hello, Pythinker!")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        # Exactly one user-visible reply is produced
        assert len(replies) == 1

        reply = replies[0]

        # Reply is routed back to the originating channel and chat
        assert reply.channel == ChannelType.TELEGRAM
        assert reply.chat_id == "tg-chat-integration"

        # Content matches what the agent produced
        assert reply.content == "Hello! How can I help you today?"

        # reply_to references the inbound message id
        assert reply.reply_to == inbound.id

        # Session lifecycle: new session was created and stored
        agent_svc.create_session.assert_awaited_once()
        create_kwargs = agent_svc.create_session.await_args.kwargs
        assert create_kwargs["source"] == "telegram"
        repo.set_session_key.assert_awaited_once()

        # User was looked up by channel identity
        repo.get_user_by_channel.assert_awaited_once_with(ChannelType.TELEGRAM, "tg-user-integration")


# ---------------------------------------------------------------------------
# Test 2: Nanobot imports available
# ---------------------------------------------------------------------------


class TestNanobotImportsAvailable:
    """Verify that all key nanobot modules are importable from the vendored package."""

    def test_nanobot_imports_available(self) -> None:
        """All critical nanobot symbols must be importable without errors."""
        # AgentLoop
        from nanobot.agent.loop import AgentLoop

        # SkillsLoader
        from nanobot.agent.skills import SkillsLoader

        # SubagentManager
        from nanobot.agent.subagent import SubagentManager

        # MessageBus
        from nanobot.bus.queue import MessageBus

        # BaseChannel
        from nanobot.channels.base import BaseChannel

        # ChannelManager
        from nanobot.channels.manager import ChannelManager

        # CronService
        from nanobot.cron.service import CronService

        # Spot-check that the symbols are real classes (not None / stub objects)
        assert AgentLoop is not None
        assert MessageBus is not None
        assert BaseChannel is not None
        assert ChannelManager is not None
        assert CronService is not None
        assert SkillsLoader is not None
        assert SubagentManager is not None


# ---------------------------------------------------------------------------
# Test 3: /new slash command resets the session
# ---------------------------------------------------------------------------


class TestSlashCommandNewResetsSession:
    """The /new command clears the current session without touching AgentService."""

    @pytest.mark.asyncio
    async def test_slash_command_new_resets_session(self) -> None:
        """/new through MessageRouter calls clear_session_key and returns a confirmation.

        Verifies:
        - clear_session_key is called with the correct (user_id, channel, chat_id).
        - AgentService is NOT invoked (no session created, no chat called).
        - The reply confirms the reset to the user.
        """
        existing_session_id = "old-session-to-clear"
        repo = _make_repo(user_id="user-integration-abc", session_id=existing_session_id)
        agent_svc = _make_agent_service()
        router = MessageRouter(agent_svc, repo)

        inbound = _make_inbound("/new")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        # Exactly one confirmation reply
        assert len(replies) == 1
        assert "Session cleared" in replies[0].content

        # Session was cleared for the right identity
        repo.clear_session_key.assert_awaited_once_with(
            "user-integration-abc",
            ChannelType.TELEGRAM,
            "tg-chat-integration",
        )

        # AgentService is never called for slash commands
        agent_svc.create_session.assert_not_awaited()
        # chat is an async generator function, not AsyncMock — verify no session set
        repo.set_session_key.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 4: Unknown sender creates user
# ---------------------------------------------------------------------------


class TestUnknownSenderCreatesUser:
    """A message from an unknown sender triggers auto-registration via the repo."""

    @pytest.mark.asyncio
    async def test_unknown_sender_creates_user(self) -> None:
        """When get_user_by_channel returns None, create_channel_user is called.

        Verifies:
        - create_channel_user receives the correct (channel, sender_id, chat_id).
        - A new session is subsequently created for the new user.
        - The agent reply is still surfaced to the caller.
        """
        repo = _make_repo(user_id=None, session_id=None)
        new_user_id = "user-auto-registered-xyz"
        repo.create_channel_user = AsyncMock(return_value=new_user_id)

        agent_svc = _make_agent_service(events=[_FakeMessageEvent()])
        router = MessageRouter(agent_svc, repo)

        inbound = _make_inbound("First message from new user", sender_id="brand-new-sender")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        # One reply should come back
        assert len(replies) == 1

        # Auto-registration was called with the correct args
        repo.create_channel_user.assert_awaited_once_with(
            ChannelType.TELEGRAM,
            "brand-new-sender",
            "tg-chat-integration",
        )

        # A new session was created for the newly registered user
        agent_svc.create_session.assert_awaited_once()
        call_kwargs = agent_svc.create_session.call_args.kwargs
        assert call_kwargs.get("user_id") == new_user_id

        # Session key stored for the new user
        repo.set_session_key.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 5: Gateway protocol compliance
# ---------------------------------------------------------------------------


class TestGatewayProtocolCompliance:
    """NanobotGateway must satisfy the ChannelGateway runtime-checkable Protocol."""

    def test_gateway_protocol_compliance(self) -> None:
        """isinstance(gateway, ChannelGateway) is True after construction.

        ChannelGateway is a @runtime_checkable Protocol.  A NanobotGateway
        instance must pass the isinstance check, confirming it implements
        all required methods (start, stop, send_to_channel, get_active_channels).
        """
        from app.domain.external.channel_gateway import ChannelGateway
        from app.infrastructure.external.channels.nanobot_gateway import NanobotGateway

        patch_cm = "app.infrastructure.external.channels.nanobot_gateway.ChannelManager"

        mock_router = MagicMock()
        mock_router.route_inbound = AsyncMock(return_value=AsyncMock())

        mock_cm = MagicMock()
        mock_cm.enabled_channels = ["telegram"]
        mock_cm.start_all = AsyncMock()
        mock_cm.stop_all = AsyncMock()

        with patch(patch_cm) as mock_cls:
            mock_cls.return_value = mock_cm
            gateway = NanobotGateway(
                message_router=mock_router,
                telegram_token="123:FAKE_TOKEN_FOR_TEST",
                telegram_allowed=["*"],
            )

        # Protocol conformance check
        assert isinstance(gateway, ChannelGateway), (
            "NanobotGateway does not satisfy the ChannelGateway protocol. "
            "Ensure start(), stop(), send_to_channel(), and get_active_channels() are implemented."
        )

        # Spot-check individual method presence and callability
        assert callable(getattr(gateway, "start", None))
        assert callable(getattr(gateway, "stop", None))
        assert callable(getattr(gateway, "send_to_channel", None))
        assert callable(getattr(gateway, "get_active_channels", None))

        # get_active_channels returns the mapped ChannelType for telegram
        active = gateway.get_active_channels()
        assert ChannelType.TELEGRAM in active


# ---------------------------------------------------------------------------
# Test 6: /link slash command — valid code links account
# ---------------------------------------------------------------------------


class TestSlashCommandLinkAccount:
    """The /link command validates a Redis code and links the Telegram identity."""

    @pytest.mark.asyncio
    async def test_link_valid_code(self) -> None:
        """/link CODE with a valid code links the channel identity to the web user.

        Verifies:
        - link_code_store.get is queried with the uppercased code key.
        - link_channel_to_user is called with (channel, sender_id, web_user_id).
        - When a previous user_id exists (and differs), migrate_sessions is called.
        - The code key is deleted after use (single-use).
        - A confirmation message is returned.
        """
        import json

        web_user_id = "web-user-99"
        old_user_id = "old-channel-user-id"
        link_code = "ABC123"
        redis_key = f"channel_link:{link_code}"
        redis_value = json.dumps({"user_id": web_user_id, "channel": "telegram"})

        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        repo.link_channel_to_user = AsyncMock(return_value=old_user_id)

        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=redis_value)
        mock_store.delete = AsyncMock()

        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)
        with (
            patch("app.domain.services.channels.message_router.pm.record_channel_link_redeemed") as redeemed_metric,
            patch("app.domain.services.channels.message_router.pm.record_channel_link_redeem_failed") as failed_metric,
        ):
            inbound = _make_inbound(f"/link {link_code}")
            replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "linked" in replies[0].content.lower()
        redeemed_metric.assert_called_once_with("telegram")
        failed_metric.assert_not_called()

        # Store was queried with correct key
        mock_store.get.assert_awaited_once_with(redis_key)

        # link_channel_to_user called with correct args
        repo.link_channel_to_user.assert_awaited_once_with(
            ChannelType.TELEGRAM,
            "tg-user-integration",
            web_user_id,
        )

        # Old user_id differed → migrate_sessions called
        repo.migrate_sessions.assert_awaited_once_with(
            old_user_id,
            web_user_id,
            ChannelType.TELEGRAM,
        )
        repo.migrate_session_ownership.assert_awaited_once_with(
            old_user_id,
            web_user_id,
        )

        # Code deleted after use
        mock_store.delete.assert_awaited_once_with(redis_key)

    @pytest.mark.asyncio
    async def test_link_invalid_code(self) -> None:
        """/link CODE with an expired or unknown code returns an error message.

        Verifies:
        - link_code_store.get returns None.
        - link_channel_to_user is NOT called.
        - An "invalid or expired" error message is returned.
        """
        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=None)

        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)
        with (
            patch("app.domain.services.channels.message_router.pm.record_channel_link_redeemed") as redeemed_metric,
            patch("app.domain.services.channels.message_router.pm.record_channel_link_redeem_failed") as failed_metric,
        ):
            inbound = _make_inbound("/link BADCODE")
            replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        content_lower = replies[0].content.lower()
        assert "invalid" in content_lower or "expired" in content_lower
        failed_metric.assert_called_once_with("not_found_or_expired")
        redeemed_metric.assert_not_called()

        repo.link_channel_to_user.assert_not_awaited()
        repo.migrate_sessions.assert_not_awaited()
        repo.migrate_session_ownership.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_link_no_code_provided(self) -> None:
        """/link with no code argument returns usage instructions.

        Verifies:
        - No store call is made when no code is supplied.
        - A usage hint is returned to the user.
        - link_channel_to_user is NOT called.
        """
        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)

        inbound = _make_inbound("/link")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "/link" in replies[0].content

        # No store call — no code to validate
        mock_store.get.assert_not_awaited()

        repo.link_channel_to_user.assert_not_awaited()
        repo.migrate_session_ownership.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bind_alias_valid_code(self) -> None:
        """:bind CODE should be normalized and processed exactly like /link CODE."""
        import json

        web_user_id = "web-user-99"
        link_code = "AbCdEf123456"
        expected_key = f"channel_link:{link_code.upper()}"
        redis_value = json.dumps({"user_id": web_user_id, "channel": "telegram"})

        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=redis_value)
        mock_store.delete = AsyncMock()

        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)

        inbound = _make_inbound(f":bind {link_code}")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "linked" in replies[0].content.lower()
        repo.link_channel_to_user.assert_awaited_once_with(
            ChannelType.TELEGRAM,
            "tg-user-integration",
            web_user_id,
        )
        mock_store.get.assert_awaited_once_with(expected_key)
        mock_store.delete.assert_awaited_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_start_bind_payload_valid_code(self) -> None:
        """/start bind_CODE should be normalized to /link CODE for Telegram deep links."""
        import json

        web_user_id = "web-user-99"
        link_code = "XyZ987654321"
        expected_key = f"channel_link:{link_code.upper()}"
        redis_value = json.dumps({"user_id": web_user_id, "channel": "telegram"})

        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=redis_value)
        mock_store.delete = AsyncMock()

        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)

        inbound = _make_inbound(f"/start bind_{link_code}")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "linked" in replies[0].content.lower()
        repo.link_channel_to_user.assert_awaited_once()
        mock_store.get.assert_awaited_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_link_rejects_code_from_other_channel(self) -> None:
        """A Telegram link attempt must reject codes minted for another channel."""
        import json

        link_code = "CODEFOROTHERCHANNEL"
        redis_value = json.dumps({"user_id": "web-user-99", "channel": "discord"})

        repo = _make_repo(user_id="tg-auto-user", session_id=None)
        agent_svc = _make_agent_service()

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=redis_value)
        mock_store.delete = AsyncMock()

        router = MessageRouter(agent_svc, repo, link_code_store=mock_store)

        inbound = _make_inbound(f"/link {link_code}")
        replies: list[OutboundMessage] = [r async for r in router.route_inbound(inbound)]

        assert len(replies) == 1
        assert "different channel" in replies[0].content.lower()
        repo.link_channel_to_user.assert_not_awaited()
        mock_store.delete.assert_not_awaited()
