"""Tests for Telegram channel command, transport, and streaming behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import aiohttp
import pytest
from nanobot.bus.events import OutboundMessage
from nanobot.channels.telegram import TelegramChannel
from nanobot.channels.telegram_webhook import TelegramWebhookListener
from nanobot.config.schema import TelegramConfig
from telegram import ReactionTypeEmoji
from telegram.error import BadRequest, RetryAfter, TimedOut
from telegram.ext import CallbackQueryHandler, MessageReactionHandler

from app.domain.services.command_registry import CommandRegistry


def _make_channel(**config_overrides: object) -> TelegramChannel:
    allow_from = config_overrides.pop("allow_from", ["*"])
    config = TelegramConfig(
        enabled=True,
        token="123:fake",
        allow_from=allow_from,
        **config_overrides,
    )
    bus = MagicMock()
    bus.publish_inbound = AsyncMock()
    return TelegramChannel(config=config, bus=bus)


def _make_command_registry(*, aliases: bool = True) -> CommandRegistry:
    registry = CommandRegistry()
    registry.register_command(
        "brainstorm",
        "brainstorming",
        "Brainstorm a design with the user",
        aliases=["idea"] if aliases else None,
    )
    return registry


def _make_update(text: str) -> SimpleNamespace:
    message = SimpleNamespace(
        chat_id=5829880422,
        text=text,
        reply_text=AsyncMock(),
        message_id=99,
        chat=SimpleNamespace(type="private", is_forum=False),
    )
    user = SimpleNamespace(
        id=5829880422,
        username="john",
        first_name="John",
    )
    return SimpleNamespace(message=message, effective_user=user, update_id=101)


def _make_text_message_update(
    text: str,
    *,
    chat_id: int = 5829880422,
    user_id: int = 5829880422,
    username: str = "john",
    first_name: str = "John",
    chat_type: str = "private",
    message_id: int = 99,
    message_thread_id: int | None = None,
    is_forum: bool = False,
    reply_to_message: object | None = None,
    quote: object | None = None,
) -> SimpleNamespace:
    user = SimpleNamespace(
        id=user_id,
        username=username,
        first_name=first_name,
    )
    message = SimpleNamespace(
        chat_id=chat_id,
        text=text,
        caption=None,
        reply_text=AsyncMock(),
        photo=[],
        voice=None,
        audio=None,
        document=None,
        message_id=message_id,
        message_thread_id=message_thread_id,
        media_group_id=None,
        reply_to_message=reply_to_message,
        quote=quote,
        chat=SimpleNamespace(type=chat_type, is_forum=is_forum),
    )
    return SimpleNamespace(message=message, effective_user=user, update_id=101)


def _make_sticker_message_update(
    *,
    chat_id: int = 5829880422,
    user_id: int = 5829880422,
    username: str = "john",
    first_name: str = "John",
    chat_type: str = "private",
    message_id: int = 99,
    emoji: str = "🔥",
    set_name: str = "funny_pack",
    is_animated: bool = False,
    is_video: bool = False,
) -> SimpleNamespace:
    user = SimpleNamespace(
        id=user_id,
        username=username,
        first_name=first_name,
    )
    message = SimpleNamespace(
        chat_id=chat_id,
        text=None,
        caption=None,
        reply_text=AsyncMock(),
        photo=[],
        voice=None,
        audio=None,
        document=None,
        sticker=SimpleNamespace(
            file_id="sticker-file-id",
            file_unique_id="sticker-unique-id",
            emoji=emoji,
            set_name=set_name,
            is_animated=is_animated,
            is_video=is_video,
            mime_type="image/webp",
            file_size=2048,
        ),
        message_id=message_id,
        message_thread_id=None,
        media_group_id=None,
        chat=SimpleNamespace(type=chat_type, is_forum=False),
    )
    return SimpleNamespace(message=message, effective_user=user, update_id=101)


def _make_message_reaction_update(
    *,
    chat_id: int = 5829880422,
    message_id: int = 42,
    user_id: int = 5829880422,
    username: str = "ada",
    first_name: str = "Ada",
    chat_type: str = "private",
    emojis: tuple[str, ...] = ("👍",),
) -> SimpleNamespace:
    user = SimpleNamespace(
        id=user_id,
        username=username,
        first_name=first_name,
        last_name=None,
        is_bot=False,
    )
    reaction = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type, title="General", is_forum=False),
        message_id=message_id,
        user=user,
        old_reaction=[],
        new_reaction=[SimpleNamespace(type="emoji", emoji=emoji) for emoji in emojis],
    )
    return SimpleNamespace(
        message_reaction=reaction,
        effective_user=user,
        update_id=303,
    )


def _make_callback_update(
    data: str,
    *,
    chat_id: int = 5829880422,
    chat_type: str = "private",
    is_forum: bool = False,
    reply_markup: object | None = None,
) -> SimpleNamespace:
    callback_query = SimpleNamespace(
        data=data,
        id="callback-1",
        answer=AsyncMock(),
        message=SimpleNamespace(
            chat_id=chat_id,
            message_id=99,
            chat=SimpleNamespace(type=chat_type, is_forum=is_forum),
            reply_markup=reply_markup,
        ),
        from_user=SimpleNamespace(id=5829880422, username="john", first_name="John"),
    )
    return SimpleNamespace(callback_query=callback_query, effective_user=callback_query.from_user, update_id=101)


def _make_channel_post_update(text: str) -> SimpleNamespace:
    message = SimpleNamespace(
        chat_id=-1001234567890,
        text=text,
        caption=None,
        reply_text=AsyncMock(),
        photo=[],
        voice=None,
        audio=None,
        document=None,
        message_id=77,
        message_thread_id=None,
        media_group_id=None,
        chat=SimpleNamespace(type="channel", is_forum=False, id=-1001234567890),
        from_user=None,
        sender_chat=SimpleNamespace(id=-1001234567890, username="announcements", title="Announcements"),
    )
    return SimpleNamespace(
        message=None,
        channel_post=message,
        effective_user=None,
        update_id=202,
    )


def _make_fake_application(channel: TelegramChannel):
    add_handler_calls: list[object] = []
    app = SimpleNamespace()
    app.add_error_handler = MagicMock()
    app.add_handler = MagicMock(side_effect=lambda handler, **kwargs: add_handler_calls.append(handler))
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.process_update = AsyncMock()
    app.update_queue = asyncio.Queue()
    app.bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(username="pythinker_test")),
        set_my_commands=AsyncMock(),
        delete_webhook=AsyncMock(),
        get_updates=AsyncMock(),
    )

    async def _start_polling(**kwargs):
        channel._running = False
        return

    async def _start_webhook(**kwargs):
        channel._running = False
        return

    app.updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=_start_polling),
        start_webhook=AsyncMock(side_effect=_start_webhook),
        stop=AsyncMock(),
    )
    return app, add_handler_calls


class _FakeBuilder:
    def __init__(self, app: object):
        self._app = app

    def token(self, _value):
        return self

    def request(self, _value):
        return self

    def get_updates_request(self, _value):
        return self

    def updater(self, _value):
        return self

    def proxy(self, _value):
        return self

    def get_updates_proxy(self, _value):
        return self

    def build(self):
        return self._app


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
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:5829880422",
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
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_help_command_mentions_robot_icon_and_bind_alias() -> None:
    channel = _make_channel()
    update = _make_update("/help")
    context = SimpleNamespace(args=[])

    await channel._on_help(update, context)

    update.message.reply_text.assert_awaited_once()
    help_text = update.message.reply_text.await_args.args[0]
    assert "🤖 Pythinker commands" in help_text
    assert "/bind <CODE>" in help_text


@pytest.mark.asyncio
async def test_help_command_paginates_when_registered_custom_commands_overflow_first_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _make_channel()
    update = _make_update("/help")
    context = SimpleNamespace(args=[])
    registry = _make_command_registry()
    registry.register_command("review", "receiving-code-review", "Review the current implementation")
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", lambda: registry)

    await channel._on_help(update, context)

    update.message.reply_text.assert_awaited_once()
    help_text = update.message.reply_text.await_args.args[0]
    reply_markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    assert "🤖 Pythinker commands (1/2)" in help_text
    assert "/brainstorm" not in help_text
    assert reply_markup is not None
    assert reply_markup.inline_keyboard[0][1].callback_data == "commands_page_2"


@pytest.mark.asyncio
async def test_callback_query_commands_page_edits_help_message(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    registry = _make_command_registry()
    registry.register_command("review", "receiving-code-review", "Review the current implementation")
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", lambda: registry)
    bot = SimpleNamespace(edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    update = _make_callback_update("commands_page_2")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()
    args = bot.edit_message_text.await_args.args
    kwargs = bot.edit_message_text.await_args.kwargs
    assert args[0] == 5829880422
    assert args[1] == 99
    assert "🤖 Pythinker commands (2/2)" in args[2]
    assert "/brainstorm" in args[2]
    assert "/review" in args[2]
    assert kwargs["reply_markup"] is not None
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "commands_page_1"


@pytest.mark.asyncio
async def test_callback_query_commands_page_noop_only_answers_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", _make_command_registry)
    bot = SimpleNamespace(edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    update = _make_callback_update("commands_page_noop")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_command_sends_help_hint() -> None:
    channel = _make_channel()
    update = _make_update("/foo")
    context = SimpleNamespace(args=[])

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_awaited_once_with("Unknown command. Use /help to see available commands.")


@pytest.mark.asyncio
async def test_unknown_command_forwards_registered_custom_command(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_update("/brainstorm compare approaches")
    context = SimpleNamespace(args=["compare", "approaches"])
    registry = _make_command_registry()
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", lambda: registry)

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_not_awaited()
    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="/brainstorm compare approaches",
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_unknown_command_forwards_registered_alias_command(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_update("/idea sketch options")
    context = SimpleNamespace(args=["sketch", "options"])
    registry = _make_command_registry()
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", lambda: registry)

    await channel._unknown_command(update, context)

    update.message.reply_text.assert_not_awaited()
    channel._handle_message.assert_awaited_once()


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
        "/commands",
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
async def test_start_registers_callback_handler_and_polls_callback_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    fake_app, add_handler_calls = _make_fake_application(channel)
    fake_app.bot.get_updates.side_effect = [
        (SimpleNamespace(update_id=101),),
        asyncio.CancelledError(),
    ]
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    monkeypatch.setattr("nanobot.channels.telegram.read_telegram_update_offset", AsyncMock(return_value=None))
    monkeypatch.setattr("nanobot.channels.telegram.write_telegram_update_offset", AsyncMock())

    await channel.start()

    callback_handlers = [handler for handler in add_handler_calls if isinstance(handler, CallbackQueryHandler)]
    assert callback_handlers
    assert callback_handlers[0].pattern is None
    reaction_handlers = [handler for handler in add_handler_calls if isinstance(handler, MessageReactionHandler)]
    assert reaction_handlers

    fake_app.updater.start_polling.assert_not_awaited()
    fake_app.bot.get_updates.assert_awaited()
    allowed_updates = fake_app.bot.get_updates.await_args.kwargs["allowed_updates"]
    assert "message" in allowed_updates
    assert "callback_query" in allowed_updates
    assert "channel_post" in allowed_updates
    assert "message_reaction" in allowed_updates


@pytest.mark.asyncio
async def test_start_registers_custom_primary_commands_in_telegram_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    fake_app, _add_handler_calls = _make_fake_application(channel)
    fake_app.bot.get_updates.side_effect = [
        (),
        asyncio.CancelledError(),
    ]
    registry = _make_command_registry()
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    monkeypatch.setattr("nanobot.channels.telegram.read_telegram_update_offset", AsyncMock(return_value=None))
    monkeypatch.setattr("nanobot.channels.telegram.write_telegram_update_offset", AsyncMock())
    monkeypatch.setattr("app.domain.services.command_registry.get_command_registry", lambda: registry)

    await channel.start()

    fake_app.bot.set_my_commands.assert_awaited_once()
    registered = fake_app.bot.set_my_commands.await_args.args[0]
    command_names = {entry.command for entry in registered}
    assert "brainstorm" in command_names
    assert "idea" not in command_names


@pytest.mark.asyncio
async def test_commands_command_uses_paginated_help_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    fake_app, add_handler_calls = _make_fake_application(channel)
    fake_app.bot.get_updates.side_effect = [
        (),
        asyncio.CancelledError(),
    ]
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    monkeypatch.setattr("nanobot.channels.telegram.read_telegram_update_offset", AsyncMock(return_value=None))
    monkeypatch.setattr("nanobot.channels.telegram.write_telegram_update_offset", AsyncMock())

    await channel.start()

    command_handlers = [
        handler for handler in add_handler_calls if isinstance(getattr(handler, "commands", None), frozenset)
    ]
    registered_handler_commands = {command for handler in command_handlers for command in handler.commands}
    assert "commands" in registered_handler_commands

    registered_menu_commands = {entry.command for entry in fake_app.bot.set_my_commands.await_args.args[0]}
    assert "commands" in registered_menu_commands


@pytest.mark.asyncio
async def test_start_polling_resumes_from_persisted_offset_and_persists_processed_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _make_channel()
    fake_app, _add_handler_calls = _make_fake_application(channel)
    first_update = SimpleNamespace(update_id=101)
    second_update = SimpleNamespace(update_id=102)
    fake_app.bot.get_updates.side_effect = [
        (first_update, second_update),
        asyncio.CancelledError(),
    ]
    read_offset = AsyncMock(return_value=100)
    write_offset = AsyncMock()
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    monkeypatch.setattr("nanobot.channels.telegram.read_telegram_update_offset", read_offset)
    monkeypatch.setattr("nanobot.channels.telegram.write_telegram_update_offset", write_offset)

    await channel.start()

    first_poll_kwargs = fake_app.bot.get_updates.await_args_list[0].kwargs
    assert first_poll_kwargs["offset"] == 101
    fake_app.process_update.assert_has_awaits(
        [
            call(first_update),
            call(second_update),
        ]
    )
    write_offset.assert_has_awaits(
        [
            call(update_id=101, bot_token="123:fake"),
            call(update_id=102, bot_token="123:fake"),
        ]
    )


@pytest.mark.asyncio
async def test_polling_stall_timeout_cancels_hung_get_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel(
        polling_stall_restart_enabled=True,
        polling_stall_timeout_seconds=1,
    )
    fake_app, _add_handler_calls = _make_fake_application(channel)
    cancelled = asyncio.Event()
    call_count = 0

    async def _hung_then_exit(**kwargs):
        del kwargs
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise
        channel._running = False
        return ()

    fake_app.bot.get_updates.side_effect = _hung_then_exit
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    monkeypatch.setattr("nanobot.channels.telegram.read_telegram_update_offset", AsyncMock(return_value=None))
    monkeypatch.setattr("nanobot.channels.telegram.write_telegram_update_offset", AsyncMock())

    await channel.start()

    assert cancelled.is_set()
    assert fake_app.bot.get_updates.await_count >= 2


@pytest.mark.asyncio
async def test_callback_query_pdf_last_forwards_pdf_command() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()

    update = _make_callback_update("telegram:get_pdf:last")
    context = SimpleNamespace()

    await channel._on_callback_query(update, context)

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="/pdf",
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_callback_query_forwards_generic_callback_data_as_message() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()

    update = _make_callback_update("/status")
    context = SimpleNamespace()

    await channel._on_callback_query(update, context)

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="/status",
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_callback_query_follow_up_button_forwards_selected_suggestion_with_metadata() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()

    reply_markup = SimpleNamespace(
        inline_keyboard=[
            [
                SimpleNamespace(
                    text="Add examples",
                    callback_data="telegram:followup:evt-followup-123:0",
                )
            ],
            [
                SimpleNamespace(
                    text="Explain the tradeoffs",
                    callback_data="telegram:followup:evt-followup-123:1",
                )
            ],
        ]
    )
    update = _make_callback_update(
        "telegram:followup:evt-followup-123:1",
        reply_markup=reply_markup,
    )

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="Explain the tradeoffs",
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
            "follow_up": {
                "selected_suggestion": "Explain the tradeoffs",
                "anchor_event_id": "evt-followup-123",
                "source": "suggestion_click",
            },
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_callback_query_respects_inbound_authorization() -> None:
    channel = _make_channel(dm_policy="disabled")
    channel._handle_message = AsyncMock()
    update = _make_callback_update("/status")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_query_skips_when_inline_buttons_scope_is_off() -> None:
    channel = _make_channel(inline_buttons_scope="off")
    channel._handle_message = AsyncMock()

    update = _make_callback_update("/status")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_query_skips_private_chat_when_inline_buttons_scope_is_group() -> None:
    channel = _make_channel(inline_buttons_scope="group")
    channel._handle_message = AsyncMock()

    update = _make_callback_update("/status", chat_type="private")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_query_skips_group_chat_when_inline_buttons_scope_is_dm() -> None:
    channel = _make_channel(inline_buttons_scope="dm")
    channel._handle_message = AsyncMock()

    update = _make_callback_update("/status", chat_id=-1001234567890, chat_type="supergroup")

    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sticker_message_preserves_rich_media_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_sticker_message_update()

    async def _download_to_drive(path: str) -> None:
        Path(path).write_bytes(b"sticker")

    channel._app = SimpleNamespace(
        bot=SimpleNamespace(
            get_file=AsyncMock(
                return_value=SimpleNamespace(
                    download_to_drive=AsyncMock(side_effect=_download_to_drive),
                )
            )
        )
    )
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once()
    kwargs = channel._handle_message.await_args.kwargs
    assert "sticker" in kwargs["content"].lower()
    assert len(kwargs["media"]) == 1
    assert kwargs["metadata"]["media_attachments"] == [
        {
            "url": kwargs["media"][0],
            "content_type": "image/webp",
            "filename": "sticker-file-id.webp",
            "size": 2048,
            "type": "sticker",
            "metadata": {
                "telegram": {
                    "file_id": "sticker-file-id",
                    "file_unique_id": "sticker-unique-id",
                    "emoji": "🔥",
                    "set_name": "funny_pack",
                }
            },
        }
    ]


@pytest.mark.asyncio
async def test_message_reaction_update_forwards_system_event() -> None:
    channel = _make_channel(reaction_notifications="all")
    channel._handle_message = AsyncMock()
    update = _make_message_reaction_update(username="john", first_name="John", emojis=("🔥",))

    await channel._on_message_reaction(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="Telegram reaction added: 🔥 by John (@john) on msg 42",
        metadata={
            "message_id": 42,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
            "telegram_reaction": {
                "emoji": "🔥",
                "message_id": 42,
            },
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_on_message_dedupes_duplicate_update_before_forwarding() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update("hello")

    await channel._on_message(update, SimpleNamespace())
    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once()
    channel._start_typing.assert_called_once_with("5829880422")


@pytest.mark.asyncio
async def test_callback_query_dedupes_duplicate_update_before_forwarding() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    update = _make_callback_update("/status")

    await channel._on_callback_query(update, SimpleNamespace())
    await channel._on_callback_query(update, SimpleNamespace())

    update.callback_query.answer.assert_awaited_once()
    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_with_webhook_mode_uses_custom_webhook_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel(
        webhook_mode=True,
        webhook_url="https://example.test/telegram-webhook",
        webhook_secret="secret-token",
        webhook_path="/telegram-webhook",
        webhook_host="127.0.0.1",
        webhook_port=8787,
    )
    fake_app, _add_handler_calls = _make_fake_application(channel)
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))
    fake_listener = SimpleNamespace(stop=AsyncMock())

    async def _start_listener(**kwargs):
        channel._running = False
        channel._shutdown_event.set()
        return fake_listener

    start_listener = AsyncMock(side_effect=_start_listener)
    monkeypatch.setattr("nanobot.channels.telegram.start_telegram_webhook_listener", start_listener)

    await channel.start()

    fake_app.updater.start_polling.assert_not_awaited()
    fake_app.updater.start_webhook.assert_not_awaited()
    start_listener.assert_awaited_once()
    kwargs = start_listener.await_args.kwargs
    assert kwargs["application"] is fake_app
    assert kwargs["public_url"] == "https://example.test/telegram-webhook"
    assert kwargs["secret_token"] == "secret-token"
    assert kwargs["path"] == "/telegram-webhook"
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8787
    assert "message" in kwargs["allowed_updates"]
    assert "callback_query" in kwargs["allowed_updates"]
    assert "channel_post" in kwargs["allowed_updates"]
    assert "message_reaction" in kwargs["allowed_updates"]


@pytest.mark.asyncio
async def test_start_with_webhook_mode_rejects_empty_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel(webhook_mode=True, webhook_secret="")
    fake_app, _add_handler_calls = _make_fake_application(channel)
    monkeypatch.setattr("nanobot.channels.telegram.Application.builder", lambda: _FakeBuilder(fake_app))

    with pytest.raises(ValueError, match="webhook_secret"):
        await channel.start()


@pytest.mark.asyncio
async def test_dm_policy_disabled_blocks_direct_message() -> None:
    channel = _make_channel(dm_policy="disabled")
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update("hello from dm")

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_not_awaited()
    channel._start_typing.assert_not_called()


@pytest.mark.asyncio
async def test_dm_policy_pairing_replies_with_link_hint_for_unknown_sender() -> None:
    channel = _make_channel(dm_policy="pairing", allow_from=["999999"])
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update("hello from dm")

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()
    reply_text = update.message.reply_text.await_args.args[0]
    assert "/link" in reply_text
    assert "authorized" in reply_text.lower()


@pytest.mark.asyncio
async def test_dm_policy_pairing_allows_link_command_without_allowlist() -> None:
    channel = _make_channel(dm_policy="pairing", allow_from=["999999"])
    channel._handle_message = AsyncMock()
    update = _make_update("/link ABC123")
    context = SimpleNamespace(args=["ABC123"])

    await channel._forward_command(update, context)

    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_require_mention_blocks_unmentioned_messages() -> None:
    channel = _make_channel(group_require_mention=True)
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    channel._bot_username = "pythinker_bot"
    update = _make_text_message_update(
        "hello everyone",
        chat_id=-1001234567890,
        chat_type="supergroup",
        user_id=123456789,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_not_awaited()
    channel._start_typing.assert_not_called()


@pytest.mark.asyncio
async def test_group_require_mention_allows_explicit_bot_mentions() -> None:
    channel = _make_channel(group_require_mention=True)
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    channel._bot_username = "pythinker_bot"
    update = _make_text_message_update(
        "hello @pythinker_bot",
        chat_id=-1001234567890,
        chat_type="supergroup",
        user_id=123456789,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once()
    channel._start_typing.assert_called_once_with("-1001234567890")


@pytest.mark.asyncio
async def test_group_policy_allowlist_blocks_unknown_group_sender() -> None:
    channel = _make_channel(group_policy="allowlist", group_allow_from=["999999"])
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "hello group",
        chat_id=-1001234567890,
        chat_type="supergroup",
        user_id=123456789,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_not_awaited()
    channel._start_typing.assert_not_called()


@pytest.mark.asyncio
async def test_group_policy_allowlist_allows_explicit_group_config_without_sender_allowlist() -> None:
    channel = _make_channel(
        group_policy="allowlist",
        groups={"-1001234567890": {"enabled": True}},
    )
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "hello allowlisted group",
        chat_id=-1001234567890,
        chat_type="supergroup",
        user_id=123456789,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once()
    channel._start_typing.assert_called_once_with("-1001234567890")


@pytest.mark.asyncio
async def test_topic_override_require_mention_blocks_for_specific_forum_topic() -> None:
    channel = _make_channel(
        group_require_mention=False,
        groups={
            "-1001234567890": {
                "topics": {
                    "42": {
                        "require_mention": True,
                    }
                }
            }
        },
    )
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    channel._bot_username = "pythinker_bot"
    update = _make_text_message_update(
        "hello topic",
        chat_id=-1001234567890,
        chat_type="supergroup",
        user_id=123456789,
        message_thread_id=42,
        is_forum=True,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_not_awaited()
    channel._start_typing.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_forum_topic_forwards_thread_metadata_and_session_key() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "hello from topic",
        chat_type="supergroup",
        message_thread_id=42,
        is_forum=True,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="hello from topic",
        media=[],
        metadata={
            "message_id": 99,
            "message_thread_id": 42,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": True,
            "is_forum": True,
        },
        session_key="telegram:group:5829880422:topic:42",
    )


@pytest.mark.asyncio
async def test_on_message_preserves_reply_quote_context_in_metadata() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "Sure, see below",
        reply_to_message=SimpleNamespace(
            message_id=9001,
            text="Can you summarize this?",
            caption=None,
            photo=[],
            video=None,
            video_note=None,
            audio=None,
            voice=None,
            document=None,
            sticker=None,
            from_user=SimpleNamespace(id=7, username="ada", first_name="Ada"),
        ),
        quote=SimpleNamespace(text="summarize this"),
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="Sure, see below",
        media=[],
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
            "reply_to_id": 9001,
            "reply_to_body": "summarize this",
            "reply_to_sender": "Ada",
            "reply_to_is_quote": True,
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_on_message_uses_media_placeholder_for_reply_context_without_text() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "What is in this image?",
        reply_to_message=SimpleNamespace(
            message_id=9002,
            text=None,
            caption=None,
            photo=[SimpleNamespace(file_id="photo-1")],
            video=None,
            video_note=None,
            audio=None,
            voice=None,
            document=None,
            sticker=None,
            from_user=SimpleNamespace(id=8, username="ada", first_name="Ada"),
        ),
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="5829880422|john",
        chat_id="5829880422",
        content="What is in this image?",
        media=[],
        metadata={
            "message_id": 99,
            "user_id": 5829880422,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
            "reply_to_id": 9002,
            "reply_to_body": "<media:image>",
            "reply_to_sender": "Ada",
        },
        session_key="telegram:direct:5829880422",
    )


@pytest.mark.asyncio
async def test_on_message_dm_topic_uses_sender_scoped_session_key() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_text_message_update(
        "hello from dm topic",
        user_id=123456789,
        chat_type="private",
        message_thread_id=9,
    )

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="123456789|john",
        chat_id="5829880422",
        content="hello from dm topic",
        media=[],
        metadata={
            "message_id": 99,
            "message_thread_id": 9,
            "user_id": 123456789,
            "username": "john",
            "first_name": "John",
            "is_group": False,
            "is_forum": False,
        },
        session_key="telegram:direct:123456789:thread:5829880422:9",
    )


@pytest.mark.asyncio
async def test_on_channel_post_forwards_sender_chat_metadata() -> None:
    channel = _make_channel()
    channel._handle_message = AsyncMock()
    channel._start_typing = MagicMock()
    update = _make_channel_post_update("channel announcement")

    await channel._on_message(update, SimpleNamespace())

    channel._handle_message.assert_awaited_once_with(
        sender_id="chat:-1001234567890|announcements",
        chat_id="-1001234567890",
        content="channel announcement",
        media=[],
        metadata={
            "message_id": 77,
            "user_id": -1001234567890,
            "username": "announcements",
            "first_name": "Announcements",
            "is_group": False,
            "is_forum": False,
            "is_channel_post": True,
        },
        session_key="telegram:channel:-1001234567890",
    )
    channel._start_typing.assert_called_once_with("-1001234567890")


@pytest.mark.asyncio
async def test_on_message_sticker_downloads_and_preserves_sticker_metadata() -> None:
    channel = _make_channel()
    update = _make_sticker_message_update()
    channel._start_typing = MagicMock()

    async def _download_to_drive(destination: str) -> None:
        Path(destination).write_bytes(b"sticker")

    channel._app = SimpleNamespace(
        bot=SimpleNamespace(
            get_file=AsyncMock(
                return_value=SimpleNamespace(download_to_drive=AsyncMock(side_effect=_download_to_drive))
            )
        )
    )

    await channel._on_message(update, SimpleNamespace())

    channel.bus.publish_inbound.assert_awaited_once()
    inbound = channel.bus.publish_inbound.await_args.args[0]
    assert inbound.content.startswith("[sticker:")
    assert len(inbound.media) == 1
    assert inbound.media[0].endswith(".webp")
    assert inbound.metadata["telegram_sticker"] == {
        "emoji": "🔥",
        "file_id": "sticker-file-id",
        "file_unique_id": "sticker-unique-id",
        "is_animated": False,
        "is_video": False,
        "set_name": "funny_pack",
    }
    assert inbound.metadata["media_items"] == [
        {
            "url": inbound.media[0],
            "mime_type": "image/webp",
            "filename": Path(inbound.media[0]).name,
            "size_bytes": 2048,
        }
    ]
    assert inbound.session_key_override == "telegram:direct:5829880422"
    channel._start_typing.assert_called_once_with("5829880422")


@pytest.mark.asyncio
async def test_message_reaction_enqueues_added_reaction_event() -> None:
    channel = _make_channel(reaction_notifications="all")
    update = _make_message_reaction_update(emojis=("👍", "🎉"))

    await channel._on_message_reaction(update, SimpleNamespace())

    assert channel.bus.publish_inbound.await_count == 2
    first = channel.bus.publish_inbound.await_args_list[0].args[0]
    second = channel.bus.publish_inbound.await_args_list[1].args[0]
    assert first.content == "Telegram reaction added: 👍 by Ada (@ada) on msg 42"
    assert second.content == "Telegram reaction added: 🎉 by Ada (@ada) on msg 42"
    assert first.metadata["message_id"] == 42
    assert first.metadata["telegram_reaction"] == {"emoji": "👍", "message_id": 42}
    assert second.metadata["telegram_reaction"] == {"emoji": "🎉", "message_id": 42}
    assert first.session_key_override == "telegram:direct:5829880422"


@pytest.mark.asyncio
async def test_send_sticker_attachment_uses_send_sticker() -> None:
    channel = _make_channel()
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=AsyncMock(),
            send_photo=AsyncMock(),
            send_voice=AsyncMock(),
            send_audio=AsyncMock(),
            send_document=AsyncMock(),
            send_sticker=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        )
    )

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            media=["/tmp/sticker.webp"],
            metadata={
                "media_attachments": [
                    {
                        "url": "/tmp/sticker.webp",
                        "content_type": "image/webp",
                        "filename": "sticker.webp",
                        "size": 321,
                        "type": "sticker",
                        "metadata": {
                            "telegram": {
                                "file_id": "sticker-file-id",
                            }
                        },
                    }
                ]
            },
        )
    )

    channel._app.bot.send_sticker.assert_awaited_once_with(
        chat_id=5829880422,
        sticker="sticker-file-id",
    )
    channel._app.bot.send_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_webhook_listener_serves_healthz_registers_webhook_and_enqueues_update() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    bot = SimpleNamespace(
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    application = SimpleNamespace(bot=bot, update_queue=queue)
    listener = TelegramWebhookListener(
        application=application,
        secret_token="secret-token",
        path="/telegram-webhook",
        host="127.0.0.1",
        port=0,
        allowed_updates=["message", "callback_query", "channel_post", "message_reaction"],
    )

    await listener.start()
    try:
        async with aiohttp.ClientSession() as session:
            health = await session.get(listener.health_url)
            assert health.status == 200
            assert await health.text() == "ok"

            response = await session.post(
                listener.webhook_url,
                json={
                    "update_id": 500,
                    "message": {"message_id": 99, "date": 0, "chat": {"id": 42, "type": "private"}, "text": "hello"},
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
            )
            assert response.status == 200

        update = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert update.update_id == 500
        assert update.message.text == "hello"
        bot.set_webhook.assert_awaited_once()
        assert bot.set_webhook.await_args.kwargs["url"] == listener.webhook_url
        assert bot.set_webhook.await_args.kwargs["secret_token"] == "secret-token"
        assert bot.set_webhook.await_args.kwargs["allowed_updates"] == [
            "message",
            "callback_query",
            "channel_post",
            "message_reaction",
        ]
    finally:
        await listener.stop()

    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)


@pytest.mark.asyncio
async def test_telegram_webhook_listener_rejects_wrong_secret_without_queueing_update() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    bot = SimpleNamespace(
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    application = SimpleNamespace(bot=bot, update_queue=queue)
    listener = TelegramWebhookListener(
        application=application,
        secret_token="secret-token",
        path="/telegram-webhook",
        host="127.0.0.1",
        port=0,
        allowed_updates=["message"],
    )

    await listener.start()
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                listener.webhook_url,
                json={
                    "update_id": 501,
                    "message": {"message_id": 100, "date": 0, "chat": {"id": 42, "type": "private"}, "text": "ignored"},
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            )
            assert response.status == 401
            assert await response.text() == "unauthorized"
        assert queue.empty()
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_telegram_webhook_listener_rejects_oversize_body_before_processing() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    bot = SimpleNamespace(
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    application = SimpleNamespace(bot=bot, update_queue=queue)
    listener = TelegramWebhookListener(
        application=application,
        secret_token="secret-token",
        path="/telegram-webhook",
        host="127.0.0.1",
        port=0,
        allowed_updates=["message"],
        max_body_bytes=64,
    )

    await listener.start()
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                listener.webhook_url,
                data=json.dumps({"update_id": 502, "message": {"text": "x" * 256}}),
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "secret-token",
                },
            )
            assert response.status == 413
            assert await response.text() == "Payload too large"
        assert queue.empty()
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_telegram_webhook_listener_times_out_slow_request_body() -> None:
    queue: asyncio.Queue[object] = asyncio.Queue()
    bot = SimpleNamespace(
        set_webhook=AsyncMock(),
        delete_webhook=AsyncMock(),
    )
    application = SimpleNamespace(bot=bot, update_queue=queue)
    listener = TelegramWebhookListener(
        application=application,
        secret_token="secret-token",
        path="/telegram-webhook",
        host="127.0.0.1",
        port=0,
        allowed_updates=["message"],
        body_timeout_seconds=0.05,
    )

    await listener.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", listener.bound_port)
        payload = (
            b'{"update_id":503,"message":{"message_id":99,"date":0,"chat":{"id":42,"type":"private"},"text":"slow"}}'
        )
        headers = (
            b"POST /telegram-webhook HTTP/1.1\r\n"
            + f"Host: 127.0.0.1:{listener.bound_port}\r\n".encode()
            + b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(payload)}\r\n".encode()
            + b"X-Telegram-Bot-Api-Secret-Token: secret-token\r\n\r\n"
        )
        writer.write(headers)
        await writer.drain()
        await asyncio.sleep(0.1)
        response_head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=1.0)
        assert b"408 Request Timeout" in response_head
        writer.close()
        await writer.wait_closed()
        assert queue.empty()
    finally:
        await listener.stop()


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
async def test_send_text_strips_reply_markup_when_inline_buttons_scope_is_off() -> None:
    channel = _make_channel(inline_buttons_scope="off")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello",
            metadata={
                "is_group": False,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Status", "callback_data": "/status"}]],
                },
            },
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert "reply_markup" not in kwargs


@pytest.mark.asyncio
async def test_send_text_keeps_reply_markup_for_dm_when_inline_buttons_scope_is_dm() -> None:
    channel = _make_channel(inline_buttons_scope="dm")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello",
            metadata={
                "is_group": False,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Status", "callback_data": "/status"}]],
                },
            },
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_send_text_strips_reply_markup_for_group_when_inline_buttons_scope_is_dm() -> None:
    channel = _make_channel(inline_buttons_scope="dm")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="-1001234567890",
            content="Hello group",
            metadata={
                "is_group": True,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Status", "callback_data": "/status"}]],
                },
            },
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert "reply_markup" not in kwargs


@pytest.mark.asyncio
async def test_send_text_keeps_reply_markup_for_group_when_inline_buttons_scope_is_group() -> None:
    channel = _make_channel(inline_buttons_scope="group")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="-1001234567890",
            content="Hello group",
            metadata={
                "is_group": True,
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Status", "callback_data": "/status"}]],
                },
            },
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_send_telegram_action_edit_text_dispatches_to_edit_message_text() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Updated text",
            metadata={
                "telegram_action": {
                    "type": "edit_text",
                    "message_id": 321,
                }
            },
        )
    )

    bot.edit_message_text.assert_awaited_once()
    kwargs = bot.edit_message_text.await_args.kwargs
    assert kwargs["chat_id"] == 5829880422
    assert kwargs["message_id"] == 321
    assert kwargs["text"] == "Updated text"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_edit_buttons_dispatches_to_edit_message_reply_markup() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Status", "callback_data": "/status"}]],
                },
                "telegram_action": {
                    "type": "edit_buttons",
                    "message_id": 321,
                },
            },
        )
    )

    bot.edit_message_reply_markup.assert_awaited_once()
    kwargs = bot.edit_message_reply_markup.await_args.kwargs
    assert kwargs["chat_id"] == 5829880422
    assert kwargs["message_id"] == 321
    assert kwargs["reply_markup"] is not None
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_delete_dispatches_to_delete_message() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "telegram_action": {
                    "type": "delete",
                    "message_id": 321,
                }
            },
        )
    )

    bot.delete_message.assert_awaited_once_with(chat_id=5829880422, message_id=321)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_react_dispatches_to_set_message_reaction() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "telegram_action": {
                    "type": "react",
                    "message_id": 321,
                    "emoji": "🔥",
                }
            },
        )
    )

    bot.set_message_reaction.assert_awaited_once()
    kwargs = bot.set_message_reaction.await_args.kwargs
    assert kwargs["chat_id"] == 5829880422
    assert kwargs["message_id"] == 321
    assert isinstance(kwargs["reaction"], ReactionTypeEmoji)
    assert kwargs["reaction"].emoji == "🔥"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_react_remove_dispatches_none_reaction() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(),
        set_message_reaction=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "telegram_action": {
                    "type": "react",
                    "message_id": 321,
                    "remove": True,
                }
            },
        )
    )

    bot.set_message_reaction.assert_awaited_once_with(chat_id=5829880422, message_id=321, reaction=None)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_poll_dispatches_to_send_poll() -> None:
    channel = _make_channel(reply_to_mode="first")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        send_poll=AsyncMock(return_value=SimpleNamespace(message_id=654)),
        send_sticker=AsyncMock(),
        create_forum_topic=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "message_id": 99,
                "message_thread_id": 12,
                "telegram_action": {
                    "type": "poll",
                    "question": "Pick one",
                    "options": ["Fast", "Deep"],
                    "allows_multiple_answers": True,
                    "is_anonymous": False,
                    "open_period": 60,
                },
            },
        )
    )

    bot.send_poll.assert_awaited_once()
    kwargs = bot.send_poll.await_args.kwargs
    assert kwargs["chat_id"] == 5829880422
    assert kwargs["question"] == "Pick one"
    assert kwargs["options"] == ["Fast", "Deep"]
    assert kwargs["allows_multiple_answers"] is True
    assert kwargs["is_anonymous"] is False
    assert kwargs["open_period"] == 60
    assert kwargs["message_thread_id"] == 12
    assert kwargs["reply_parameters"] is not None
    assert kwargs["reply_parameters"].message_id == 99
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_topic_create_dispatches_to_create_forum_topic() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        send_poll=AsyncMock(),
        send_sticker=AsyncMock(),
        create_forum_topic=AsyncMock(return_value=SimpleNamespace(message_thread_id=777, name="Ops Room")),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="-1001234567890",
            content="",
            metadata={
                "telegram_action": {
                    "type": "topic_create",
                    "name": "Ops Room",
                    "icon_color": 7322096,
                    "icon_custom_emoji_id": "emoji-123",
                }
            },
        )
    )

    bot.create_forum_topic.assert_awaited_once_with(
        chat_id=-1001234567890,
        name="Ops Room",
        icon_color=7322096,
        icon_custom_emoji_id="emoji-123",
    )
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_telegram_action_sticker_dispatches_to_send_sticker() -> None:
    channel = _make_channel(reply_to_mode="first")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
        send_poll=AsyncMock(),
        send_sticker=AsyncMock(return_value=SimpleNamespace(message_id=777)),
        create_forum_topic=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "message_id": 99,
                "message_thread_id": 12,
                "telegram_action": {
                    "type": "sticker",
                    "file_id": "sticker-file-id",
                },
            },
        )
    )

    bot.send_sticker.assert_awaited_once()
    kwargs = bot.send_sticker.await_args.kwargs
    assert kwargs["chat_id"] == 5829880422
    assert kwargs["sticker"] == "sticker-file-id"
    assert kwargs["message_thread_id"] == 12
    assert kwargs["reply_parameters"] is not None
    assert kwargs["reply_parameters"].message_id == 99
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_document_failure_falls_back_to_text(tmp_path: Path) -> None:
    channel = _make_channel(send_retry_max_attempts=3)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming_mode", ["partial", "progress"])
async def test_progress_preview_creates_then_edits_single_message(streaming_mode: str) -> None:
    channel = _make_channel(
        streaming=streaming_mode,
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content=" world",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == "Hello"
    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["chat_id"] == 5829880422
    assert bot.edit_message_text.await_args.kwargs["message_id"] == 321
    assert bot.edit_message_text.await_args.kwargs["text"] == "Hello world"


@pytest.mark.asyncio
async def test_progress_preview_keeps_typing_active() -> None:
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    channel._stop_typing = MagicMock()
    channel._start_typing = MagicMock()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Working",
            metadata={
                "_progress": True,
                "_telegram_stream": True,
                "_telegram_stream_final": False,
                "message_id": 99,
            },
        )
    )

    channel._stop_typing.assert_not_called()
    channel._start_typing.assert_called_once_with("5829880422")


@pytest.mark.asyncio
async def test_research_ack_keeps_typing_active_until_final_reply() -> None:
    channel = _make_channel()
    channel._stop_typing = MagicMock()
    channel._start_typing = MagicMock()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Researching your request...",
            metadata={"_telegram_keep_typing": True},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Final answer",
        )
    )

    channel._start_typing.assert_called_once_with("5829880422")
    channel._stop_typing.assert_called_once_with("5829880422")


@pytest.mark.asyncio
async def test_progress_preview_uses_generic_preview_text_metadata() -> None:
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "_progress": True,
                "_telegram_stream": True,
                "_telegram_stream_preview_text": "Working on it...",
                "message_id": 99,
            },
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="garbled raw chunk that should stay hidden",
            metadata={
                "_progress": True,
                "_telegram_stream": True,
                "_telegram_stream_preview_text": "Preparing the final response...",
                "message_id": 99,
            },
        )
    )

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == "Working on it..."
    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["text"] == "Preparing the final response..."


@pytest.mark.asyncio
async def test_final_text_edits_existing_preview_instead_of_sending_new_message() -> None:
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Thinking",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Final answer",
            metadata={"message_id": 99},
        )
    )

    bot.send_message.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["text"] == "Final answer"


@pytest.mark.asyncio
async def test_media_or_pdf_final_clears_preview_and_uses_existing_delivery_path(tmp_path: Path) -> None:
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    media_path = tmp_path / "final.pdf"
    media_path.write_bytes(b"%PDF")

    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(document=SimpleNamespace(file_id="pdf-file-id"))),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(return_value=True),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Thinking",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Caption",
            media=[str(media_path)],
            metadata={
                "delivery_mode": "pdf_only",
                "caption": "Caption",
                "parse_mode": "HTML",
                "message_id": 99,
            },
        )
    )

    bot.send_message.assert_awaited_once()
    bot.edit_message_text.assert_not_awaited()
    bot.delete_message.assert_awaited_once()
    assert bot.delete_message.await_args.kwargs == {"chat_id": 5829880422, "message_id": 321}
    bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_streaming_off_skips_preview_logic() -> None:
    channel = _make_channel(
        streaming="off",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Final answer",
            metadata={"message_id": 99},
        )
    )

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["text"] == "Final answer"
    bot.edit_message_text.assert_not_awaited()
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_text_html_parse_error_retries_plain_text() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(
            side_effect=[
                BadRequest("can't parse entities"),
                SimpleNamespace(message_id=321),
            ]
        ),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Bad <b markup",
            metadata={"parse_mode": "HTML"},
        )
    )

    assert bot.send_message.await_count == 2
    first_call = bot.send_message.await_args_list[0].kwargs
    second_call = bot.send_message.await_args_list[1].kwargs
    assert first_call["parse_mode"] == "HTML"
    assert "parse_mode" not in second_call
    assert second_call["text"] == "Bad <b markup"


@pytest.mark.asyncio
async def test_send_text_dm_topic_thread_not_found_retries_without_thread_id() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(
            side_effect=[
                BadRequest("Message thread not found"),
                SimpleNamespace(message_id=321),
            ]
        ),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello topic",
            metadata={"message_thread_id": 42, "is_forum": False},
        )
    )

    assert bot.send_message.await_count == 2
    first_call = bot.send_message.await_args_list[0].kwargs
    second_call = bot.send_message.await_args_list[1].kwargs
    assert first_call["message_thread_id"] == 42
    assert "message_thread_id" not in second_call


@pytest.mark.asyncio
async def test_send_text_forum_topic_thread_not_found_does_not_retry_without_thread_id() -> None:
    channel = _make_channel()
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(side_effect=BadRequest("Message thread not found")),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Hello forum topic",
            metadata={"message_thread_id": 42, "is_forum": True},
        )
    )

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_reply_to_mode_first_only_applies_reply_to_first_text_chunk() -> None:
    channel = _make_channel(reply_to_mode="first")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content=("a" * 4000) + " b",
            metadata={"message_id": 99},
        )
    )

    assert bot.send_message.await_count == 2
    first_reply = bot.send_message.await_args_list[0].kwargs["reply_parameters"]
    second_reply = bot.send_message.await_args_list[1].kwargs["reply_parameters"]
    assert first_reply is not None
    assert first_reply.message_id == 99
    assert second_reply is None


@pytest.mark.asyncio
async def test_reply_to_mode_all_applies_reply_to_every_text_chunk() -> None:
    channel = _make_channel(reply_to_mode="all")
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content=("a" * 4000) + " b",
            metadata={"message_id": 99},
        )
    )

    assert bot.send_message.await_count == 2
    first_reply = bot.send_message.await_args_list[0].kwargs["reply_parameters"]
    second_reply = bot.send_message.await_args_list[1].kwargs["reply_parameters"]
    assert first_reply is not None
    assert second_reply is not None
    assert first_reply.message_id == 99
    assert second_reply.message_id == 99


@pytest.mark.asyncio
async def test_channel_finalizes_preview_against_original_message_context() -> None:
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
        reply_to_message=True,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
            ]
        ),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Preview one",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 99},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Preview two",
            metadata={"_progress": True, "_telegram_stream": True, "message_id": 100},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="Final answer for 99",
            metadata={"message_id": 99},
        )
    )

    assert bot.send_message.await_count == 2
    first_reply_params = bot.send_message.await_args_list[0].kwargs["reply_parameters"]
    second_reply_params = bot.send_message.await_args_list[1].kwargs["reply_parameters"]
    assert first_reply_params is not None
    assert second_reply_params is not None
    assert first_reply_params.message_id == 99
    assert second_reply_params.message_id == 100

    bot.edit_message_text.assert_awaited_once()
    edit_kwargs = bot.edit_message_text.await_args.kwargs
    assert edit_kwargs["chat_id"] == 5829880422
    assert edit_kwargs["message_id"] == 321
    assert edit_kwargs["text"] == "Final answer for 99"


# ---------------------------------------------------------------------------
# Dual-lane preview delivery (Task 3)
# ---------------------------------------------------------------------------


def _make_streaming_channel() -> TelegramChannel:
    """Helper: channel with streaming enabled and no throttle for predictable tests."""
    channel = _make_channel(
        streaming="partial",
        streaming_throttle_seconds=0.0,
        streaming_min_initial_chars=1,
    )
    bot = SimpleNamespace(
        send_document=AsyncMock(),
        send_photo=AsyncMock(),
        send_voice=AsyncMock(),
        send_audio=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)
    return channel


def _stream_msg(content: str, *, lane: str = "answer", is_final: bool = False, msg_id: int = 99) -> OutboundMessage:
    """Helper: build a stream-type OutboundMessage for a specific lane."""
    return OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content=content,
        metadata={
            "_progress": True,
            "_telegram_stream": True,
            "_telegram_stream_lane": lane,
            "_telegram_stream_final": is_final,
            "message_id": msg_id,
        },
    )


@pytest.mark.asyncio
async def test_dual_lane_answer_and_reasoning_get_separate_previews() -> None:
    """Answer and reasoning lanes create independent preview messages."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    # Stream answer lane
    await channel.send(_stream_msg("Answer part 1", lane="answer"))
    # Stream reasoning lane
    bot.send_message.return_value = SimpleNamespace(message_id=555)
    await channel.send(_stream_msg("Thinking...", lane="reasoning"))

    assert bot.send_message.await_count == 2
    # First call = answer preview (msg_id 321), second = reasoning preview (msg_id 555)
    first_text = bot.send_message.await_args_list[0].kwargs["text"]
    second_text = bot.send_message.await_args_list[1].kwargs["text"]
    assert "Answer" in first_text
    assert "Thinking" in second_text


@pytest.mark.asyncio
async def test_finalized_lane_ignores_further_updates() -> None:
    """Once a lane is finalized, subsequent stream updates are silently dropped."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    # Create and finalize answer preview
    await channel.send(_stream_msg("Hello", lane="answer"))
    key = channel._preview_key(
        OutboundMessage(channel="telegram", chat_id="5829880422", content="", metadata={"message_id": 99}),
        lane="answer",
    )
    state = channel._preview_states.get(key)
    assert state is not None
    state.finalized = True

    # Send more content — should be ignored
    await channel.send(_stream_msg(" more", lane="answer"))
    # Only the original send_message, no edits for the finalized content
    assert bot.edit_message_text.await_count == 0


@pytest.mark.asyncio
async def test_regressive_update_blocked_on_existing_preview() -> None:
    """Edits that would shrink the visible text are blocked."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    await channel.send(_stream_msg("Long answer text here", lane="answer"))
    assert bot.send_message.await_count == 1

    # Now send a shorter override — should be blocked
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="5829880422",
            content="",
            metadata={
                "_progress": True,
                "_telegram_stream": True,
                "_telegram_stream_lane": "answer",
                "_telegram_stream_preview_text": "Short",
                "message_id": 99,
            },
        )
    )
    assert bot.edit_message_text.await_count == 0


@pytest.mark.asyncio
async def test_force_new_preview_archives_old_message() -> None:
    """_force_new_preview archives the current preview and increments generation."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    msg = _stream_msg("Initial", lane="answer")
    await channel.send(msg)
    assert bot.send_message.await_count == 1

    # Force new preview (simulates boundary rotation)
    ref_msg = OutboundMessage(
        channel="telegram", chat_id="5829880422", content="", metadata={"message_id": 99},
    )
    channel._force_new_preview(ref_msg, lane="answer")

    # Old message should be archived
    base_key = channel._preview_base_key(ref_msg)
    assert base_key in channel._archived_previews
    archived_list = channel._archived_previews[base_key]
    assert len(archived_list) == 1
    assert archived_list[0].message_id == 321

    # New state should have incremented generation
    key = channel._preview_key(ref_msg, lane="answer")
    new_state = channel._preview_states.get(key)
    assert new_state is not None
    assert new_state.generation == 1
    assert new_state.message_id is None


@pytest.mark.asyncio
async def test_archived_preview_consumed_by_final_delivery() -> None:
    """Final text delivery reuses an archived preview message via edit."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    # Stream and archive an answer preview
    msg = _stream_msg("Preview text", lane="answer")
    await channel.send(msg)
    ref_msg = OutboundMessage(
        channel="telegram", chat_id="5829880422", content="", metadata={"message_id": 99},
    )
    channel._force_new_preview(ref_msg, lane="answer")

    # Now send final answer — should consume archived preview via edit
    final_msg = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Final answer",
        metadata={"message_id": 99},
    )
    await channel.send(final_msg)

    # Should have edited the archived message (321), not sent a new one
    bot.edit_message_text.assert_awaited()
    edit_kwargs = bot.edit_message_text.await_args.kwargs
    assert edit_kwargs["message_id"] == 321
    assert "Final answer" in edit_kwargs["text"]

    # Archived list should be consumed
    base_key = channel._preview_base_key(ref_msg)
    assert base_key not in channel._archived_previews


@pytest.mark.asyncio
async def test_clear_preview_cleans_all_lanes_and_archived() -> None:
    """_clear_preview removes both lanes and deletes archived previews."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    # Create answer preview
    await channel.send(_stream_msg("Answer", lane="answer"))

    # Create reasoning preview
    bot.send_message.return_value = SimpleNamespace(message_id=555)
    await channel.send(_stream_msg("Reasoning", lane="reasoning"))

    # Archive a preview
    ref_msg = OutboundMessage(
        channel="telegram", chat_id="5829880422", content="", metadata={"message_id": 99},
    )
    channel._force_new_preview(ref_msg, lane="answer")

    # Clear all
    await channel._clear_preview(ref_msg, chat_id=5829880422)

    # All states should be gone
    assert not channel._has_preview_state(ref_msg, lane="answer")
    assert not channel._has_preview_state(ref_msg, lane="reasoning")
    assert channel._preview_base_key(ref_msg) not in channel._archived_previews

    # Archived + reasoning message should have been deleted
    assert bot.delete_message.await_count >= 2


@pytest.mark.asyncio
async def test_per_lane_finalization_independence() -> None:
    """Answer can finalize while reasoning continues streaming."""
    channel = _make_streaming_channel()
    bot = channel._app.bot

    # Stream both lanes
    await channel.send(_stream_msg("Answer", lane="answer"))
    bot.send_message.return_value = SimpleNamespace(message_id=555)
    await channel.send(_stream_msg("Thinking step 1", lane="reasoning"))

    # Finalize answer via final delivery
    final_msg = OutboundMessage(
        channel="telegram",
        chat_id="5829880422",
        content="Final answer text",
        metadata={"message_id": 99},
    )
    await channel.send(final_msg)

    # Answer lane should be finalized and cleaned up
    ref_msg = OutboundMessage(
        channel="telegram", chat_id="5829880422", content="", metadata={"message_id": 99},
    )
    assert not channel._has_preview_state(ref_msg, lane="answer")

    # Reasoning lane should still be active
    assert channel._has_preview_state(ref_msg, lane="reasoning")
    reasoning_state = channel._preview_states[channel._preview_key(ref_msg, lane="reasoning")]
    assert not reasoning_state.finalized


# ---------------------------------------------------------------------------
# Forward and location context extraction tests (Task 7 parity)
# ---------------------------------------------------------------------------


def test_resolve_forward_context_user_origin() -> None:
    """Forwarded messages from a user carry sender name and id."""
    message = SimpleNamespace(
        forward_origin=SimpleNamespace(
            type="user",
            sender_user=SimpleNamespace(id=123, first_name="Alice"),
        ),
        forward_date="2026-03-08T12:00:00",
    )
    ctx = TelegramChannel._resolve_forward_context(message)
    assert ctx["is_forwarded"] is True
    assert ctx["forward_from"] == "Alice"
    assert ctx["forward_from_id"] == 123
    assert ctx["forward_date"] == "2026-03-08T12:00:00"


def test_resolve_forward_context_channel_origin() -> None:
    """Forwarded messages from a channel carry channel title and id."""
    message = SimpleNamespace(
        forward_origin=SimpleNamespace(
            type="channel",
            chat=SimpleNamespace(id=-1001234, title="News Channel"),
        ),
        forward_date=None,
    )
    ctx = TelegramChannel._resolve_forward_context(message)
    assert ctx["is_forwarded"] is True
    assert ctx["forward_from_chat"] == "News Channel"
    assert ctx["forward_from_chat_id"] == -1001234
    assert "forward_date" not in ctx


def test_resolve_forward_context_hidden_user_origin() -> None:
    """Forwarded messages from a hidden user use the provided name or [hidden]."""
    message = SimpleNamespace(
        forward_origin=SimpleNamespace(type="hidden_user", sender_user_name="Ghost"),
        forward_date=None,
    )
    ctx = TelegramChannel._resolve_forward_context(message)
    assert ctx["is_forwarded"] is True
    assert ctx["forward_from"] == "Ghost"


def test_resolve_forward_context_no_forward() -> None:
    """Non-forwarded messages produce an empty context dict."""
    message = SimpleNamespace(forward_origin=None, forward_date=None)
    assert TelegramChannel._resolve_forward_context(message) == {}


def test_resolve_location_context_plain_location() -> None:
    """Plain GPS locations produce lat/lng context."""
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=30.0, longitude=31.2),
        venue=None,
    )
    ctx = TelegramChannel._resolve_location_context(message)
    loc = ctx["location"]
    assert loc["latitude"] == 30.0
    assert loc["longitude"] == 31.2
    assert "title" not in loc


def test_resolve_location_context_venue() -> None:
    """Venue messages include title and address."""
    message = SimpleNamespace(
        location=None,
        venue=SimpleNamespace(
            location=SimpleNamespace(latitude=51.5, longitude=-0.1),
            title="Big Ben",
            address="London SW1A 0AA",
        ),
    )
    ctx = TelegramChannel._resolve_location_context(message)
    loc = ctx["location"]
    assert loc["latitude"] == 51.5
    assert loc["title"] == "Big Ben"
    assert loc["address"] == "London SW1A 0AA"


def test_resolve_location_context_no_location() -> None:
    """Messages without location/venue produce an empty context dict."""
    message = SimpleNamespace(location=None, venue=None)
    assert TelegramChannel._resolve_location_context(message) == {}


@pytest.mark.asyncio
async def test_on_message_forwarded_message_preserves_forward_context() -> None:
    """Forwarded messages should include forward context in the inbound bus message."""
    channel = _make_channel()
    channel._running = True
    channel._bot_username = "pythinker"
    channel._bot_user_id = 99999

    message = SimpleNamespace(
        chat_id=5829880422,
        text="Check this out",
        caption=None,
        reply_text=AsyncMock(),
        photo=[],
        voice=None,
        audio=None,
        document=None,
        video=None,
        video_note=None,
        sticker=None,
        message_id=42,
        message_thread_id=None,
        media_group_id=None,
        reply_to_message=None,
        quote=None,
        external_reply=None,
        forward_origin=SimpleNamespace(
            type="user",
            sender_user=SimpleNamespace(id=777, first_name="Bob"),
        ),
        forward_date="2026-03-08T15:00:00",
        location=None,
        venue=None,
        chat=SimpleNamespace(type="private", is_forum=False, id=5829880422),
        from_user=SimpleNamespace(id=5829880422, username="john", first_name="John"),
        sender_chat=None,
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=5829880422, username="john", first_name="John"),
        update_id=201,
    )
    ctx = MagicMock()
    await channel._on_message(update, ctx)

    assert channel.bus.publish_inbound.call_count == 1
    inbound = channel.bus.publish_inbound.call_args.args[0]
    assert inbound.metadata["is_forwarded"] is True
    assert inbound.metadata["forward_from"] == "Bob"
    assert inbound.metadata["forward_from_id"] == 777


@pytest.mark.asyncio
async def test_on_message_location_preserves_location_context() -> None:
    """Location messages should include location data in the inbound bus message."""
    channel = _make_channel()
    channel._running = True
    channel._bot_username = "pythinker"
    channel._bot_user_id = 99999

    message = SimpleNamespace(
        chat_id=5829880422,
        text=None,
        caption=None,
        reply_text=AsyncMock(),
        photo=[],
        voice=None,
        audio=None,
        document=None,
        video=None,
        video_note=None,
        sticker=None,
        message_id=43,
        message_thread_id=None,
        media_group_id=None,
        reply_to_message=None,
        quote=None,
        external_reply=None,
        forward_origin=None,
        forward_date=None,
        location=SimpleNamespace(latitude=30.05, longitude=31.23),
        venue=None,
        chat=SimpleNamespace(type="private", is_forum=False, id=5829880422),
        from_user=SimpleNamespace(id=5829880422, username="john", first_name="John"),
        sender_chat=None,
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=5829880422, username="john", first_name="John"),
        update_id=202,
    )
    ctx = MagicMock()
    await channel._on_message(update, ctx)

    assert channel.bus.publish_inbound.call_count == 1
    inbound = channel.bus.publish_inbound.call_args.args[0]
    loc = inbound.metadata["location"]
    assert loc["latitude"] == 30.05
    assert loc["longitude"] == 31.23


# ---------------------------------------------------------------------------
# quoteText support tests (Task 8 parity)
# ---------------------------------------------------------------------------


def test_reply_parameters_for_metadata_with_quote_text() -> None:
    """When metadata includes quote_text, ReplyParameters should carry the quote field."""
    metadata = {"message_id": 42, "quote_text": "This specific sentence"}
    result = TelegramChannel._reply_parameters_for_metadata(metadata, "first")
    assert result is not None
    assert result.message_id == 42
    assert result.quote == "This specific sentence"


def test_reply_parameters_for_metadata_without_quote_text() -> None:
    """Without quote_text, ReplyParameters should not carry a quote field."""
    metadata = {"message_id": 42}
    result = TelegramChannel._reply_parameters_for_metadata(metadata, "first")
    assert result is not None
    assert result.message_id == 42
    assert result.quote is None


def test_reply_parameters_for_metadata_empty_quote_text() -> None:
    """Empty or whitespace-only quote_text should be ignored."""
    metadata = {"message_id": 42, "quote_text": "   "}
    result = TelegramChannel._reply_parameters_for_metadata(metadata, "first")
    assert result is not None
    assert result.quote is None


def test_build_delivery_metadata_includes_quote_text() -> None:
    """build_message_notify_delivery_metadata should pass through quote_text."""
    from app.domain.services.tools.message import build_message_notify_delivery_metadata

    result = build_message_notify_delivery_metadata({"quote_text": "Important bit"})
    assert result is not None
    assert result["quote_text"] == "Important bit"


def test_build_delivery_metadata_ignores_empty_quote_text() -> None:
    """Empty quote_text should not appear in delivery metadata."""
    from app.domain.services.tools.message import build_message_notify_delivery_metadata

    result = build_message_notify_delivery_metadata({"quote_text": ""})
    assert result is None
