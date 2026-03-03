"""Tests for Telegram channel command and deep-link forwarding behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nanobot.channels.telegram import TelegramChannel
from nanobot.config.schema import TelegramConfig


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
@pytest.mark.parametrize("command_text", ["/stop", "/status", "/link ABC123"])
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
async def test_unknown_command_sends_help_hint() -> None:
    channel = _make_channel()
    update = _make_update("/foo")
    context = SimpleNamespace(args=[])

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_awaited_once_with("Unknown command. Use /help to see available commands.")
