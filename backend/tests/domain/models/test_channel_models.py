"""Tests for channel gateway domain models and scheduled job model."""

from datetime import UTC, datetime

import pytest

from app.domain.models.channel import (
    ChannelType,
    InboundMessage,
    MediaAttachment,
    OutboundMessage,
    UserChannelLink,
)
from app.domain.models.scheduled_job import ScheduledJob
from app.domain.models.session import Session


# ---------------------------------------------------------------------------
# ChannelType
# ---------------------------------------------------------------------------


class TestChannelType:
    def test_enum_values(self) -> None:
        assert ChannelType.WEB == "web"
        assert ChannelType.TELEGRAM == "telegram"
        assert ChannelType.DISCORD == "discord"
        assert ChannelType.SLACK == "slack"
        assert ChannelType.WHATSAPP == "whatsapp"
        assert ChannelType.EMAIL == "email"
        assert ChannelType.CRON == "cron"
        assert ChannelType.API == "api"

    def test_enum_count(self) -> None:
        assert len(ChannelType) == 8

    def test_string_comparison(self) -> None:
        """StrEnum values compare equal to plain strings."""
        assert ChannelType.TELEGRAM == "telegram"
        assert "discord" == ChannelType.DISCORD


# ---------------------------------------------------------------------------
# MediaAttachment
# ---------------------------------------------------------------------------


class TestMediaAttachment:
    def test_creation_minimal(self) -> None:
        att = MediaAttachment(url="https://example.com/photo.jpg")
        assert att.url == "https://example.com/photo.jpg"
        assert att.mime_type == ""
        assert att.filename == ""
        assert att.size_bytes == 0

    def test_creation_full(self) -> None:
        att = MediaAttachment(
            url="https://cdn.example.com/doc.pdf",
            mime_type="application/pdf",
            filename="report.pdf",
            size_bytes=1024,
        )
        assert att.mime_type == "application/pdf"
        assert att.filename == "report.pdf"
        assert att.size_bytes == 1024


# ---------------------------------------------------------------------------
# InboundMessage
# ---------------------------------------------------------------------------


class TestInboundMessage:
    def test_creation_with_defaults(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.TELEGRAM,
            sender_id="tg-123",
            chat_id="chat-456",
            content="Hello agent",
        )
        assert msg.channel == ChannelType.TELEGRAM
        assert msg.sender_id == "tg-123"
        assert msg.chat_id == "chat-456"
        assert msg.content == "Hello agent"
        # Auto-generated fields
        assert len(msg.id) == 16
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.tzinfo is not None
        assert msg.media == []
        assert msg.metadata == {}
        assert msg.session_key_override is None

    def test_creation_with_media(self) -> None:
        att = MediaAttachment(url="https://example.com/img.png", mime_type="image/png")
        msg = InboundMessage(
            channel=ChannelType.DISCORD,
            sender_id="user-abc",
            chat_id="channel-789",
            content="Check this image",
            media=[att],
        )
        assert len(msg.media) == 1
        assert msg.media[0].url == "https://example.com/img.png"

    def test_creation_with_session_override(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.API,
            sender_id="api-key-1",
            chat_id="req-001",
            content="Run task",
            session_key_override="session-xyz",
        )
        assert msg.session_key_override == "session-xyz"

    def test_creation_with_metadata(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.SLACK,
            sender_id="U12345",
            chat_id="C67890",
            content="Slash command",
            metadata={"thread_ts": "1234567890.123456"},
        )
        assert msg.metadata["thread_ts"] == "1234567890.123456"


# ---------------------------------------------------------------------------
# OutboundMessage
# ---------------------------------------------------------------------------


class TestOutboundMessage:
    def test_creation_minimal(self) -> None:
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            chat_id="chat-456",
            content="Here is the result",
        )
        assert msg.channel == ChannelType.TELEGRAM
        assert msg.chat_id == "chat-456"
        assert msg.content == "Here is the result"
        assert msg.reply_to is None
        assert msg.media == []
        assert msg.metadata == {}

    def test_creation_with_reply(self) -> None:
        msg = OutboundMessage(
            channel=ChannelType.DISCORD,
            chat_id="channel-789",
            content="Reply content",
            reply_to="msg-original-123",
        )
        assert msg.reply_to == "msg-original-123"

    def test_creation_with_media(self) -> None:
        att = MediaAttachment(
            url="https://example.com/chart.png",
            mime_type="image/png",
            filename="chart.png",
            size_bytes=2048,
        )
        msg = OutboundMessage(
            channel=ChannelType.EMAIL,
            chat_id="user@example.com",
            content="Attached is the chart",
            media=[att],
        )
        assert len(msg.media) == 1
        assert msg.media[0].filename == "chart.png"


# ---------------------------------------------------------------------------
# UserChannelLink
# ---------------------------------------------------------------------------


class TestUserChannelLink:
    def test_creation_with_defaults(self) -> None:
        link = UserChannelLink(
            user_id="user-001",
            channel=ChannelType.TELEGRAM,
            sender_id="tg-123",
            chat_id="chat-456",
        )
        assert link.user_id == "user-001"
        assert link.channel == ChannelType.TELEGRAM
        assert link.sender_id == "tg-123"
        assert link.chat_id == "chat-456"
        assert link.display_name is None
        assert isinstance(link.linked_at, datetime)
        assert link.linked_at.tzinfo is not None

    def test_creation_with_display_name(self) -> None:
        link = UserChannelLink(
            user_id="user-002",
            channel=ChannelType.DISCORD,
            sender_id="discord-user-789",
            chat_id="guild-001",
            display_name="JohnDoe#1234",
        )
        assert link.display_name == "JohnDoe#1234"


# ---------------------------------------------------------------------------
# ScheduledJob
# ---------------------------------------------------------------------------


class TestScheduledJob:
    def test_creation_with_defaults(self) -> None:
        job = ScheduledJob(
            user_id="user-001",
            schedule_type="cron",
            schedule_expr="0 9 * * 1-5",
            task_description="Check news headlines",
        )
        assert len(job.id) == 12
        assert job.user_id == "user-001"
        assert job.schedule_type == "cron"
        assert job.schedule_expr == "0 9 * * 1-5"
        assert job.task_description == "Check news headlines"
        assert job.channel is None
        assert job.chat_id is None
        assert job.timezone == "UTC"
        assert job.enabled is True
        assert job.last_run is None
        assert job.next_run is None
        assert job.run_count == 0
        assert job.max_runs is None
        assert job.metadata == {}
        assert isinstance(job.created_at, datetime)
        assert job.created_at.tzinfo is not None

    def test_creation_interval_type(self) -> None:
        job = ScheduledJob(
            user_id="user-002",
            schedule_type="interval",
            schedule_expr="30m",
            task_description="Poll stock prices",
        )
        assert job.schedule_type == "interval"
        assert job.schedule_expr == "30m"

    def test_creation_once_type(self) -> None:
        job = ScheduledJob(
            user_id="user-003",
            schedule_type="once",
            schedule_expr="2026-04-01T09:00:00Z",
            task_description="Send birthday reminder",
        )
        assert job.schedule_type == "once"

    def test_creation_with_channel_delivery(self) -> None:
        job = ScheduledJob(
            user_id="user-004",
            schedule_type="cron",
            schedule_expr="0 8 * * *",
            task_description="Morning briefing",
            channel=ChannelType.TELEGRAM,
            chat_id="chat-789",
        )
        assert job.channel == ChannelType.TELEGRAM
        assert job.chat_id == "chat-789"

    def test_creation_with_max_runs(self) -> None:
        job = ScheduledJob(
            user_id="user-005",
            schedule_type="interval",
            schedule_expr="1h",
            task_description="Hourly check",
            max_runs=24,
        )
        assert job.max_runs == 24

    def test_creation_with_metadata(self) -> None:
        job = ScheduledJob(
            user_id="user-006",
            schedule_type="cron",
            schedule_expr="*/5 * * * *",
            task_description="Health check",
            metadata={"priority": "high", "tags": ["monitoring"]},
        )
        assert job.metadata["priority"] == "high"

    def test_invalid_schedule_type_rejected(self) -> None:
        with pytest.raises(Exception):
            ScheduledJob(
                user_id="user-007",
                schedule_type="invalid",  # type: ignore[arg-type]
                schedule_expr="bad",
                task_description="Should fail",
            )


# ---------------------------------------------------------------------------
# Session.source field
# ---------------------------------------------------------------------------


class TestSessionSource:
    def test_default_source_is_web(self) -> None:
        session = Session(user_id="user-001", agent_id="agent-001")
        assert session.source == "web"

    def test_explicit_source_telegram(self) -> None:
        session = Session(user_id="user-002", agent_id="agent-001", source="telegram")
        assert session.source == "telegram"

    def test_explicit_source_discord(self) -> None:
        session = Session(user_id="user-003", agent_id="agent-001", source="discord")
        assert session.source == "discord"

    def test_explicit_source_cron(self) -> None:
        session = Session(user_id="user-004", agent_id="agent-001", source="cron")
        assert session.source == "cron"

    def test_explicit_source_api(self) -> None:
        session = Session(user_id="user-005", agent_id="agent-001", source="api")
        assert session.source == "api"

    def test_source_preserved_in_dict(self) -> None:
        session = Session(user_id="user-006", agent_id="agent-001", source="slack")
        data = session.model_dump()
        assert data["source"] == "slack"
