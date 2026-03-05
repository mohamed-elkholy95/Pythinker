"""Tests for Telegram channel command and deep-link forwarding behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nanobot.bus.events import OutboundMessage
from nanobot.channels.telegram import TelegramChannel
from nanobot.config.schema import TelegramConfig
from telegram.error import RetryAfter, TimedOut


def _make_channel() -> TelegramChannel:
    config = TelegramConfig(
        enabled=True,
        token="123:fake",
        allow_from=["*"],
    )
    bus = MagicMock()
    bus.publish_inbound = AsyncMock()
    return TelegramChannel(config=config, bus=bus)


def _make_update(text: str) -> SimpleNamespace:
    message = SimpleNamespace(
        chat_id=5829880422,
        text=text,
        reply_text=AsyncMock(),
    )
    user = SimpleNamespace(
        id=5829880422,
        username="john",
        first_name="John",
    )
    return SimpleNamespace(message=message, effective_user=user)


@pytest.mark.asyncio
async def test_start_with_bind_payload_forwards_to_bus() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_update("/start bind_ABC123")
    context = SimpleNamespace(args=["bind_ABC123"])

    await channel._on_start(update, context)

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="/start bind_ABC123",
    )
    update.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_without_bind_payload_sends_greeting() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_update("/start")
    context = SimpleNamespace(args=[])

    await channel._on_start(update, context)

    channel._handle_message.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    greeting_text = update.message.reply_text.await_args.args[0]
    assert "Hi John" in greeting_text
    assert "/help" in greeting_text


@pytest.mark.asyncio
@pytest.mark.parametrize("command_text", ["/stop", "/status", "/pdf", "/link ABC123", "/bind ABC123"])
async def test_forward_command_routes_supported_slash_commands(command_text: str) -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_update(command_text)
    context = SimpleNamespace(args=command_text.split()[1:])

    await channel._forward_command(update, context)

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content=command_text,
    )


@pytest.mark.asyncio
async def test_help_command_mentions_pythinker_and_bind_alias() -> None:
    channel = _make_channel()
    update = _make_update("/help")
    context = SimpleNamespace(args=[])

    await channel._on_help(update, context)

    update.message.reply_text.assert_awaited_once()
    help_text = update.message.reply_text.await_args.args[0]
    assert "Pythinker commands" in help_text
    assert "/bind <CODE>" in help_text


@pytest.mark.asyncio
async def test_unknown_command_sends_help_hint() -> None:
    channel = _make_channel()
    update = _make_update("/foo")
    context = SimpleNamespace(args=[])

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_awaited_once_with("Unknown command. Use /help to see available commands.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    [
        "/start",
        "/start@Pythinker_bot bind_ABC123",
        "/new",
        "/stop",
        "/status",
        "/pdf",
        "/link ABC123",
        "/bind ABC123",
        "/help",
    ],
)
async def test_unknown_command_ignores_known_commands(command_text: str) -> None:
    channel = _make_channel()
    update = _make_update(command_text)
    context = SimpleNamespace(args=[])

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_command_ignores_unparseable_command_text() -> None:
    channel = _make_channel()
    update = _make_update("/foo")
    update.message.text = None
    context = SimpleNamespace(args=[])

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_document_uses_caption_parse_mode_and_cleanup(tmp_path: Path) -> None:
    channel = _make_channel()
    media_path = tmp_path / "report.pdf"
    media_path.write_bytes(b"%PDF-1.4\n%fake\n")

    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    outbound = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="<b>Caption</b>",
        media=[str(media_path)],
        metadata={
            "delivery_mode": "pdf_only",
            "caption": "<b>Caption</b>",
            "parse_mode": "HTML",
            "cleanup_media_paths": [str(media_path)],
        },
    )

    await channel.send(outbound)

    bot.send_document.assert_awaited_once()
    kwargs = bot.send_document.await_args.kwargs
    assert kwargs["caption"] == "<b>Caption</b>"
    assert kwargs["parse_mode"] == "HTML"
    bot.send_message.assert_not_awaited()
    assert not media_path.exists()


@pytest.mark.asyncio
async def test_send_document_without_caption_sends_document_only(tmp_path: Path) -> None:
    channel = _make_channel()
    media_path = tmp_path / "report.pdf"
    media_path.write_bytes(b"%PDF-1.4\n%fake\n")

    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    outbound = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="",
        media=[str(media_path)],
        metadata={
            "delivery_mode": "pdf_only",
            "cleanup_media_paths": [str(media_path)],
        },
    )

    await channel.send(outbound)

    bot.send_document.assert_awaited_once()
    kwargs = bot.send_document.await_args.kwargs
    assert "caption" not in kwargs
    assert "parse_mode" not in kwargs
    bot.send_message.assert_not_awaited()
    assert not media_path.exists()


@pytest.mark.asyncio
async def test_send_document_retries_on_retry_after(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    channel = _make_channel()
    media_path = tmp_path / "retry.pdf"
    media_path.write_bytes(b"%PDF")

    bot = SimpleNamespace(
        send_document=AsyncMock(side_effect=[RetryAfter(1), None]),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    sleep_mock = AsyncMock()
    monkeypatch.setattr("nanobot.channels.telegram.asyncio.sleep", sleep_mock)

    outbound = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Caption",
        media=[str(media_path)],
        metadata={"delivery_mode": "pdf_only", "caption": "Caption", "parse_mode": "HTML"},
    )

    await channel.send(outbound)

    assert bot.send_document.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_document_failure_falls_back_to_text(tmp_path: Path) -> None:
    channel = _make_channel()
    media_path = tmp_path / "broken.pdf"
    media_path.write_bytes(b"%PDF")

    bot = SimpleNamespace(
        send_document=AsyncMock(side_effect=[TimedOut("timeout"), TimedOut("timeout"), TimedOut("timeout")]),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    outbound = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Fallback text body",
        media=[str(media_path)],
        metadata={"delivery_mode": "pdf_only", "caption": "Caption", "parse_mode": "HTML"},
    )

    await channel.send(outbound)

    assert bot.send_document.await_count == 3
    # One failure notice plus fallback text send
    assert bot.send_message.await_count >= 1


@pytest.mark.asyncio
async def test_send_document_reuses_cached_file_id(tmp_path: Path) -> None:
    channel = _make_channel()
    media_path = tmp_path / "cached.pdf"
    media_path.write_bytes(b"%PDF")

    first_response = SimpleNamespace(document=SimpleNamespace(file_id="cached-file-id"))
    bot = SimpleNamespace(
        send_document=AsyncMock(side_effect=[first_response, None]),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    first = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Caption",
        media=[str(media_path)],
        metadata={
            "delivery_mode": "pdf_only",
            "caption": "Caption",
            "parse_mode": "HTML",
            "content_hash": "hash-123",
        },
    )
    await channel.send(first)

    second = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Caption",
        media=[str(tmp_path / "does-not-exist.pdf")],
        metadata={
            "delivery_mode": "pdf_only",
            "caption": "Caption",
            "parse_mode": "HTML",
            "content_hash": "hash-123",
        },
    )
    await channel.send(second)

    assert bot.send_document.await_count == 2
    second_kwargs = bot.send_document.await_args_list[1].kwargs
    assert second_kwargs["document"] == "cached-file-id"
