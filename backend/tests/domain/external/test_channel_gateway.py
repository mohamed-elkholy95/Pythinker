"""Tests for ChannelGateway protocol — runtime_checkable isinstance checks."""

from __future__ import annotations

import pytest

from app.domain.external.channel_gateway import ChannelGateway
from app.domain.models.channel import ChannelType, OutboundMessage

# ---------------------------------------------------------------------------
# Concrete implementations for testing
# ---------------------------------------------------------------------------


class _CompleteGateway:
    """Implements all ChannelGateway methods."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_to_channel(self, message: OutboundMessage) -> None:
        pass

    def get_active_channels(self) -> list[ChannelType]:
        return [ChannelType.TELEGRAM]


class _MissingSendGateway:
    """Missing send_to_channel — should NOT satisfy the protocol."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_active_channels(self) -> list[ChannelType]:
        return []


class _MissingStartGateway:
    """Missing start — should NOT satisfy the protocol."""

    async def stop(self) -> None:
        pass

    async def send_to_channel(self, message: OutboundMessage) -> None:
        pass

    def get_active_channels(self) -> list[ChannelType]:
        return []


class _EmptyClass:
    """No methods at all."""

    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChannelGatewayProtocol:
    """Verify runtime_checkable Protocol enforcement."""

    def test_complete_implementation_satisfies_protocol(self) -> None:
        gateway = _CompleteGateway()
        assert isinstance(gateway, ChannelGateway)

    def test_missing_send_to_channel_fails_protocol(self) -> None:
        gateway = _MissingSendGateway()
        assert not isinstance(gateway, ChannelGateway)

    def test_missing_start_fails_protocol(self) -> None:
        gateway = _MissingStartGateway()
        assert not isinstance(gateway, ChannelGateway)

    def test_empty_class_fails_protocol(self) -> None:
        obj = _EmptyClass()
        assert not isinstance(obj, ChannelGateway)

    def test_protocol_is_runtime_checkable(self) -> None:
        """ChannelGateway must be decorated with @runtime_checkable."""
        assert hasattr(ChannelGateway, "__protocol_attrs__") or hasattr(ChannelGateway, "_is_runtime_protocol")

    @pytest.mark.asyncio
    async def test_complete_gateway_methods_callable(self) -> None:
        """Ensure the complete gateway's methods actually work."""
        gateway = _CompleteGateway()

        # start / stop should not raise
        await gateway.start()
        await gateway.stop()

        # send_to_channel accepts an OutboundMessage
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            channel_user_id="u123",
            text="hello",
        )
        await gateway.send_to_channel(msg)

        # get_active_channels returns the expected list
        channels = gateway.get_active_channels()
        assert channels == [ChannelType.TELEGRAM]
