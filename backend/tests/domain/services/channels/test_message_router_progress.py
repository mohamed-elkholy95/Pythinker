"""Tests for progress event forwarding to gateway."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage
from app.domain.services.channels.message_router import _OUTBOUND_EVENT_TYPES, MessageRouter


class _FakeProgressEvent:
    type = "progress"
    message = "Researching..."


class _FakeMessageEvent:
    type = "message"
    role = "assistant"
    message = "Hello!"


class TestProgressHeartbeat:
    """Progress events should be forwarded to the gateway for stall prevention."""

    def test_progress_in_outbound_types(self):
        """'progress' must be in _OUTBOUND_EVENT_TYPES."""
        assert "progress" in _OUTBOUND_EVENT_TYPES

    def test_progress_event_produces_outbound(self):
        """A progress event should produce an outbound message with heartbeat metadata."""
        router = object.__new__(MessageRouter)
        source = MagicMock(spec=InboundMessage)
        source.channel = ChannelType.TELEGRAM
        source.chat_id = "123"
        source.id = "msg-1"

        result = router._event_to_outbound(_FakeProgressEvent(), source)
        assert result is not None
        assert isinstance(result, OutboundMessage)
        assert result.content == ""
        assert result.metadata.get("_progress_heartbeat") is True

    def test_message_event_not_heartbeat(self):
        """Regular message events should not have heartbeat metadata."""
        router = object.__new__(MessageRouter)
        source = MagicMock(spec=InboundMessage)
        source.channel = ChannelType.TELEGRAM
        source.chat_id = "123"
        source.id = "msg-1"

        result = router._event_to_outbound(_FakeMessageEvent(), source)
        assert result is not None
        assert result.metadata.get("_progress_heartbeat") is not True

    def test_other_event_types_unchanged(self):
        """message, report, error should still be in outbound types."""
        assert "message" in _OUTBOUND_EVENT_TYPES
        assert "report" in _OUTBOUND_EVENT_TYPES
        assert "error" in _OUTBOUND_EVENT_TYPES

    def test_progress_heartbeat_channel_and_chat_preserved(self):
        """Heartbeat outbound carries the source channel and chat_id."""
        router = object.__new__(MessageRouter)
        source = MagicMock(spec=InboundMessage)
        source.channel = ChannelType.DISCORD
        source.chat_id = "discord-chat-42"
        source.id = "msg-2"

        result = router._event_to_outbound(_FakeProgressEvent(), source)
        assert result is not None
        assert result.channel == ChannelType.DISCORD
        assert result.chat_id == "discord-chat-42"
        assert result.reply_to == "msg-2"

    def test_progress_heartbeat_empty_content(self):
        """Heartbeat outbound must carry empty string content (not visible to user)."""
        router = object.__new__(MessageRouter)
        source = MagicMock(spec=InboundMessage)
        source.channel = ChannelType.SLACK
        source.chat_id = "slack-channel-7"
        source.id = "msg-3"

        result = router._event_to_outbound(_FakeProgressEvent(), source)
        assert result is not None
        assert result.content == ""
