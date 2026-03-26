"""Tests for channel gateway models (app.domain.models.channel).

Covers ChannelType, MediaAttachment, InboundMessage, OutboundMessage,
UserChannelLink.
"""

from app.domain.models.channel import (
    ChannelType,
    InboundMessage,
    MediaAttachment,
    OutboundMessage,
    UserChannelLink,
)


class TestChannelType:
    def test_all_values(self) -> None:
        assert ChannelType.WEB == "web"
        assert ChannelType.TELEGRAM == "telegram"
        assert ChannelType.DISCORD == "discord"
        assert ChannelType.SLACK == "slack"
        assert ChannelType.WHATSAPP == "whatsapp"
        assert ChannelType.EMAIL == "email"
        assert ChannelType.CRON == "cron"
        assert ChannelType.API == "api"

    def test_is_string(self) -> None:
        assert isinstance(ChannelType.WEB, str)


class TestMediaAttachment:
    def test_creation(self) -> None:
        media = MediaAttachment(
            url="https://example.com/file.pdf",
            mime_type="application/pdf",
            filename="report.pdf",
            size_bytes=1024,
        )
        assert media.url == "https://example.com/file.pdf"
        assert media.mime_type == "application/pdf"
        assert media.size_bytes == 1024

    def test_defaults(self) -> None:
        media = MediaAttachment(url="https://example.com/img.png")
        assert media.mime_type == ""
        assert media.filename == ""
        assert media.size_bytes == 0
        assert media.metadata == {}


class TestInboundMessage:
    def test_creation(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.TELEGRAM,
            sender_id="tg-12345",
            chat_id="chat-789",
            content="Hello from Telegram",
        )
        assert msg.channel == ChannelType.TELEGRAM
        assert msg.sender_id == "tg-12345"
        assert msg.content == "Hello from Telegram"
        assert msg.id is not None
        assert len(msg.id) == 16
        assert msg.media == []
        assert msg.session_key_override is None

    def test_unique_ids(self) -> None:
        msgs = [
            InboundMessage(
                channel=ChannelType.WEB,
                sender_id="u",
                chat_id="c",
                content="test",
            )
            for _ in range(10)
        ]
        ids = [m.id for m in msgs]
        assert len(ids) == len(set(ids))

    def test_with_media(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.DISCORD,
            sender_id="user",
            chat_id="channel",
            content="Check this",
            media=[MediaAttachment(url="https://example.com/img.png")],
        )
        assert len(msg.media) == 1

    def test_session_key_override(self) -> None:
        msg = InboundMessage(
            channel=ChannelType.API,
            sender_id="api-user",
            chat_id="api-chat",
            content="test",
            session_key_override="custom-session-key",
        )
        assert msg.session_key_override == "custom-session-key"


class TestOutboundMessage:
    def test_creation(self) -> None:
        msg = OutboundMessage(
            channel=ChannelType.SLACK,
            chat_id="C12345",
            content="Response from agent",
        )
        assert msg.channel == ChannelType.SLACK
        assert msg.content == "Response from agent"
        assert msg.reply_to is None

    def test_with_reply(self) -> None:
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            chat_id="chat-1",
            content="Reply",
            reply_to="msg-42",
        )
        assert msg.reply_to == "msg-42"


class TestUserChannelLink:
    def test_creation(self) -> None:
        link = UserChannelLink(
            user_id="user-1",
            channel=ChannelType.DISCORD,
            sender_id="discord-123",
            chat_id="guild-456",
            display_name="TestUser#1234",
        )
        assert link.user_id == "user-1"
        assert link.channel == ChannelType.DISCORD
        assert link.display_name == "TestUser#1234"
        assert link.linked_at is not None

    def test_defaults(self) -> None:
        link = UserChannelLink(
            user_id="u",
            channel=ChannelType.WEB,
            sender_id="s",
            chat_id="c",
        )
        assert link.display_name is None
