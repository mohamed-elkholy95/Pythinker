from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.interfaces.schemas.channel_link import (
    GenerateLinkCodeRequest,
    GenerateLinkCodeResponse,
    LinkedChannelResponse,
    LinkedChannelsListResponse,
)


class TestGenerateLinkCodeRequest:
    def test_default_channel_is_telegram(self) -> None:
        req = GenerateLinkCodeRequest()
        assert req.channel == "telegram"

    def test_custom_channel(self) -> None:
        req = GenerateLinkCodeRequest(channel="whatsapp")
        assert req.channel == "whatsapp"

    def test_empty_string_channel(self) -> None:
        req = GenerateLinkCodeRequest(channel="")
        assert req.channel == ""

    def test_serialization(self) -> None:
        req = GenerateLinkCodeRequest(channel="slack")
        data = req.model_dump()
        assert data == {"channel": "slack"}


class TestGenerateLinkCodeResponse:
    def test_required_fields(self) -> None:
        resp = GenerateLinkCodeResponse(code="ABC123", channel="telegram")
        assert resp.code == "ABC123"
        assert resp.channel == "telegram"

    def test_default_expires_in_seconds(self) -> None:
        resp = GenerateLinkCodeResponse(code="XYZ", channel="telegram")
        assert resp.expires_in_seconds == 1800

    def test_default_optional_strings_are_empty(self) -> None:
        resp = GenerateLinkCodeResponse(code="XYZ", channel="telegram")
        assert resp.instructions == ""
        assert resp.bind_command == ""
        assert resp.bot_url == ""
        assert resp.deep_link_url == ""

    def test_custom_expires_in_seconds(self) -> None:
        resp = GenerateLinkCodeResponse(code="XYZ", channel="telegram", expires_in_seconds=900)
        assert resp.expires_in_seconds == 900

    def test_custom_instructions(self) -> None:
        resp = GenerateLinkCodeResponse(
            code="XYZ",
            channel="telegram",
            instructions="Send /start to @bot",
        )
        assert resp.instructions == "Send /start to @bot"

    def test_custom_bind_command(self) -> None:
        resp = GenerateLinkCodeResponse(
            code="XYZ",
            channel="telegram",
            bind_command="/bind ABC123",
        )
        assert resp.bind_command == "/bind ABC123"

    def test_custom_bot_url(self) -> None:
        resp = GenerateLinkCodeResponse(
            code="XYZ",
            channel="telegram",
            bot_url="https://t.me/pythinker_bot",
        )
        assert resp.bot_url == "https://t.me/pythinker_bot"

    def test_custom_deep_link_url(self) -> None:
        resp = GenerateLinkCodeResponse(
            code="XYZ",
            channel="telegram",
            deep_link_url="https://t.me/pythinker_bot?start=ABC123",
        )
        assert resp.deep_link_url == "https://t.me/pythinker_bot?start=ABC123"

    def test_all_fields_set(self) -> None:
        resp = GenerateLinkCodeResponse(
            code="LINK99",
            channel="telegram",
            expires_in_seconds=600,
            instructions="Follow instructions",
            bind_command="/bind LINK99",
            bot_url="https://t.me/bot",
            deep_link_url="https://t.me/bot?start=LINK99",
        )
        assert resp.code == "LINK99"
        assert resp.expires_in_seconds == 600
        assert resp.instructions == "Follow instructions"

    def test_missing_code_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            GenerateLinkCodeResponse(channel="telegram")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("code",) for e in errors)

    def test_missing_channel_raises(self) -> None:
        with pytest.raises(ValidationError):
            GenerateLinkCodeResponse(code="ABC")  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        resp = GenerateLinkCodeResponse(code="T1", channel="telegram")
        data = resp.model_dump()
        assert data["code"] == "T1"
        assert data["channel"] == "telegram"
        assert data["expires_in_seconds"] == 1800
        assert data["instructions"] == ""
        assert data["bind_command"] == ""
        assert data["bot_url"] == ""
        assert data["deep_link_url"] == ""


class TestLinkedChannelResponse:
    def test_required_fields(self) -> None:
        resp = LinkedChannelResponse(channel="telegram", sender_id="user-42")
        assert resp.channel == "telegram"
        assert resp.sender_id == "user-42"

    def test_linked_at_defaults_to_none(self) -> None:
        resp = LinkedChannelResponse(channel="telegram", sender_id="user-42")
        assert resp.linked_at is None

    def test_linked_at_can_be_set(self) -> None:
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        resp = LinkedChannelResponse(channel="telegram", sender_id="user-42", linked_at=dt)
        assert resp.linked_at == dt

    def test_missing_channel_raises(self) -> None:
        with pytest.raises(ValidationError):
            LinkedChannelResponse(sender_id="user-42")  # type: ignore[call-arg]

    def test_missing_sender_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            LinkedChannelResponse(channel="telegram")  # type: ignore[call-arg]

    def test_serialization_without_linked_at(self) -> None:
        resp = LinkedChannelResponse(channel="telegram", sender_id="u123")
        data = resp.model_dump()
        assert data["channel"] == "telegram"
        assert data["sender_id"] == "u123"
        assert data["linked_at"] is None

    def test_serialization_with_linked_at(self) -> None:
        dt = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)
        resp = LinkedChannelResponse(channel="telegram", sender_id="u123", linked_at=dt)
        data = resp.model_dump()
        assert data["linked_at"] == dt


class TestLinkedChannelsListResponse:
    def test_empty_channels(self) -> None:
        resp = LinkedChannelsListResponse(channels=[])
        assert resp.channels == []

    def test_single_channel(self) -> None:
        channel = LinkedChannelResponse(channel="telegram", sender_id="u1")
        resp = LinkedChannelsListResponse(channels=[channel])
        assert len(resp.channels) == 1
        assert resp.channels[0].sender_id == "u1"

    def test_multiple_channels(self) -> None:
        channels = [LinkedChannelResponse(channel="telegram", sender_id=f"u{i}") for i in range(3)]
        resp = LinkedChannelsListResponse(channels=channels)
        assert len(resp.channels) == 3

    def test_missing_channels_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            LinkedChannelsListResponse()  # type: ignore[call-arg]

    def test_serialization(self) -> None:
        channel = LinkedChannelResponse(channel="telegram", sender_id="u99")
        resp = LinkedChannelsListResponse(channels=[channel])
        data = resp.model_dump()
        assert "channels" in data
        assert isinstance(data["channels"], list)
        assert data["channels"][0]["sender_id"] == "u99"
