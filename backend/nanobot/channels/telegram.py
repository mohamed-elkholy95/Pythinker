"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji, ReplyParameters, Update
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    filters,
)
from telegram.request import HTTPXRequest

from nanobot.bus.events import InboundMessage as BusInboundMessage
from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.channels.telegram_update_offset_store import (
    read_telegram_update_offset,
    write_telegram_update_offset,
)
from nanobot.channels.telegram_webhook import TelegramWebhookListener, start_telegram_webhook_listener
from nanobot.config.schema import TelegramConfig


@dataclass(slots=True)
class _TelegramPreviewState:
    """Tracks the lifecycle of a streamed Telegram preview message.

    Fields mirror OpenClaw's ``DraftLaneState`` and ``TelegramDraftStream``:
    - ``generation`` increments on boundary rotation (``forceNewMessage``).
    - ``finalized`` marks the lane as done; further updates are ignored.
    """

    content: str = ""
    message_id: int | None = None
    last_sent_at: float = 0.0
    last_text: str = ""
    reply_applied: bool = False
    generation: int = 0
    finalized: bool = False


@dataclass(slots=True)
class _ArchivedPreview:
    """An old preview message available for consumption by final delivery.

    Mirrors OpenClaw ``lane-delivery.ts`` archived-preview semantics:
    the old message can be edited in-place by final send instead of
    creating a new message, reducing message-count churn.
    """

    message_id: int
    last_text: str
    delete_if_unused: bool = True


_FOLLOW_UP_CALLBACK_PREFIX = "telegram:followup:"


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []

    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []

    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)

    # 3. Headers # Title -> just the title text
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 10. Bullet lists - item -> • item
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def _split_message(content: str, max_len: int = 4000) -> list[str]:
    """Split content into chunks within max_len, preferring line breaks."""
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos == -1:
            pos = cut.rfind(" ")
        if pos == -1:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


_TELEGRAM_HTML_PARSE_ERR_RE = re.compile(r"can't parse entities|parse entities|find end of the entity", re.IGNORECASE)
_TELEGRAM_THREAD_NOT_FOUND_RE = re.compile(r"message thread not found", re.IGNORECASE)
_TELEGRAM_MESSAGE_NOT_MODIFIED_RE = re.compile(r"message is not modified", re.IGNORECASE)
_TELEGRAM_RECENT_UPDATE_TTL_SECONDS = 5 * 60.0
_TELEGRAM_RECENT_UPDATE_MAX = 2000
_TELEGRAM_SENT_MESSAGE_TTL_SECONDS = 24 * 60 * 60.0
_TELEGRAM_SENT_MESSAGE_MAX = 4000
_TELEGRAM_MAX_COMMANDS = 100
_TELEGRAM_MENU_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_TELEGRAM_HELP_PAGE_SIZE = 8


class TelegramChannel(BaseChannel):
    """
    Telegram channel using polling or webhook delivery.

    The transport mode is selected from config at startup.
    """

    name = "telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS: ClassVar[list[BotCommand]] = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("stop", "Stop the current task"),
        BotCommand("status", "Show current session status"),
        BotCommand("pdf", "Get the last response as a PDF"),
        BotCommand("link", "Link your account with a code"),
        BotCommand("bind", "Alias of /link for link codes"),
        BotCommand("help", "Show available commands"),
        BotCommand("commands", "List all slash commands"),
        BotCommand("reasoning", "Set reasoning visibility (off, on, stream)"),
        BotCommand("think", "Set thinking level (off, low, medium, high)"),
        BotCommand("verbose", "Toggle verbose mode (off, on)"),
        BotCommand("elevated", "Toggle elevated mode (off, on)"),
        BotCommand("models", "Show model information"),
    ]
    _KNOWN_SLASH_COMMANDS = frozenset({
        "start", "new", "stop", "status", "pdf", "link", "bind", "help", "commands",
        "reasoning", "think", "thinking", "t", "verbose", "v", "elevated", "elev",
        "models",
    })

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task
        self._media_group_buffers: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task] = {}
        self._pdf_file_id_cache: dict[str, tuple[str, float]] = {}
        self._pdf_file_id_cache_ttl_seconds = 24 * 60 * 60
        self._preview_states: dict[str, _TelegramPreviewState] = {}
        self._archived_previews: dict[str, list[_ArchivedPreview]] = {}  # base_key -> archived msgs
        self._recent_update_keys: OrderedDict[str, float] = OrderedDict()
        self._sent_message_keys: OrderedDict[tuple[str, int], float] = OrderedDict()
        self._shutdown_event: asyncio.Event = asyncio.Event()
        self._active_polling_request: asyncio.Task | None = None
        self._webhook_listener: TelegramWebhookListener | None = None
        self._bot_username: str | None = None
        self._bot_user_id: int | None = None

    async def start(self) -> None:
        """Start the Telegram bot with polling or webhook delivery."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        webhook_mode = bool(getattr(self.config, "webhook_mode", False))
        secret_token = str(getattr(self.config, "webhook_secret", "") or "").strip()
        if webhook_mode and not secret_token:
            raise ValueError("Telegram webhook mode requires webhook_secret")

        self._running = True
        self._shutdown_event = asyncio.Event()
        self._active_polling_request = None
        self._webhook_listener = None
        self._bot_username = None
        self._bot_user_id = None

        # Build the application with larger connection pool to avoid pool-timeout on long runs
        req = HTTPXRequest(connection_pool_size=16, pool_timeout=5.0, connect_timeout=30.0, read_timeout=30.0)
        builder = Application.builder().token(self.config.token).request(req).get_updates_request(req)
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        builder = builder.updater(None)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._forward_command))
        # PYTHINKER-PATCH: forward router-supported commands to the bus.
        self._app.add_handler(CommandHandler("stop", self._forward_command))
        self._app.add_handler(CommandHandler("status", self._forward_command))
        self._app.add_handler(CommandHandler("pdf", self._forward_command))
        self._app.add_handler(CommandHandler("link", self._forward_command))
        self._app.add_handler(CommandHandler("bind", self._forward_command))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("commands", self._on_help))
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))
        self._app.add_handler(MessageReactionHandler(self._on_message_reaction))

        # Add message handler for text, photos, voice, documents, videos, and stickers.
        self._app.add_handler(
            MessageHandler(
                (
                    filters.TEXT
                    | filters.PHOTO
                    | filters.VOICE
                    | filters.AUDIO
                    | filters.Document.ALL
                    | filters.VIDEO
                    | filters.VIDEO_NOTE
                    | filters.Sticker.ALL
                )
                & ~filters.COMMAND,
                self._on_message,
            )
        )
        # PYTHINKER-PATCH: unknown slash commands should return a help hint.
        self._app.add_handler(
            MessageHandler(filters.COMMAND, self._unknown_command),
            group=1,
        )

        try:
            logger.info("Starting Telegram bot ({})...", "webhook" if webhook_mode else "polling")

            await self._app.initialize()
            await self._app.start()

            # Get bot info and register command menu
            bot_info = await self._app.bot.get_me()
            self._bot_username = getattr(bot_info, "username", None)
            self._bot_user_id = getattr(bot_info, "id", None)
            logger.info("Telegram bot @{} connected", bot_info.username)

            try:
                await self._app.bot.set_my_commands(self._build_registered_bot_commands())
                logger.debug("Telegram bot commands registered")
            except Exception as e:
                logger.warning("Failed to register bot commands: {}", e)

            allowed_updates = self._resolve_allowed_updates()
            if webhook_mode:
                self._webhook_listener = await start_telegram_webhook_listener(
                    application=self._app,
                    secret_token=secret_token,
                    path=str(getattr(self.config, "webhook_path", "/telegram-webhook") or "/telegram-webhook"),
                    host=str(getattr(self.config, "webhook_host", "127.0.0.1") or "127.0.0.1"),
                    port=int(getattr(self.config, "webhook_port", 8787)),
                    public_url=str(getattr(self.config, "webhook_url", "") or "").strip() or None,
                    allowed_updates=allowed_updates,
                )
                if not self._running:
                    return
                await self._shutdown_event.wait()
                return

            await self._run_polling_loop(allowed_updates=allowed_updates)
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        self._shutdown_event.set()

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()
        self._preview_states.clear()
        self._recent_update_keys.clear()
        self._sent_message_keys.clear()
        if self._active_polling_request is not None:
            self._active_polling_request.cancel()

        if self._app:
            logger.info("Stopping Telegram bot...")
            if self._webhook_listener is not None:
                try:
                    await self._webhook_listener.stop()
                except Exception as exc:
                    logger.debug("Telegram webhook listener shutdown failed: {}", exc)
                finally:
                    self._webhook_listener = None
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
        self._active_polling_request = None
        self._bot_username = None
        self._bot_user_id = None

    @staticmethod
    def _get_media_type(path: str) -> str:
        """Guess media type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    @staticmethod
    def _reaction_notification_mode(value: object) -> str:
        """Normalize Telegram reaction notification mode to OpenClaw's runtime set."""
        normalized = str(value or "own").strip().lower()
        if normalized in {"off", "own", "all"}:
            return normalized
        return "own"

    @staticmethod
    def _normalize_streaming_mode(value: object) -> str:
        """Normalize Telegram preview streaming mode to the OpenClaw runtime set."""
        if isinstance(value, bool):
            return "partial" if value else "off"
        normalized = str(value or "").strip().lower()
        if normalized == "progress":
            return "partial"
        if normalized in {"off", "partial", "block"}:
            return normalized
        return "partial"

    def _reply_to_mode(self) -> str:
        """Resolve Telegram reply threading mode, preserving the legacy boolean flag."""
        mode = str(getattr(self.config, "reply_to_mode", "") or "").strip().lower()
        if getattr(self.config, "reply_to_message", False):
            if mode == "all":
                return "all"
            return "first"
        if mode in {"off", "first", "all"}:
            return mode
        return "off"

    @staticmethod
    def _normalize_message_id(value: object) -> int | None:
        """Parse a Telegram message/thread id into a positive integer."""
        if isinstance(value, bool):
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized > 0 else None

    @classmethod
    def _reply_parameters_for_metadata(cls, metadata: dict[str, object], reply_to_mode: str) -> ReplyParameters | None:
        """Build ReplyParameters for the source message when reply threading is enabled.

        Supports OpenClaw-style ``quote_text`` (maps to Telegram ``reply_parameters.quote``).
        """
        if reply_to_mode == "off":
            return None
        message_id = cls._normalize_message_id(metadata.get("message_id"))
        if message_id is None:
            return None
        quote_text = str(metadata.get("quote_text", "") or "").strip() or None
        return ReplyParameters(
            message_id=message_id,
            allow_sending_without_reply=True,
            **({"quote": quote_text} if quote_text else {}),
        )

    @staticmethod
    def _should_include_reply_for_send(
        reply_to_mode: str,
        *,
        reply_applied: bool,
    ) -> bool:
        """Return whether the next physical Telegram send should include reply parameters."""
        return reply_to_mode == "all" or (reply_to_mode == "first" and not reply_applied)

    @staticmethod
    def _resolve_outbound_message_thread_id(metadata: dict[str, object]) -> int | None:
        """Resolve Telegram outbound thread param, omitting the General forum topic id=1."""
        thread_id = TelegramChannel._normalize_message_id(metadata.get("message_thread_id"))
        if thread_id is None:
            return None
        if bool(metadata.get("is_forum")) and thread_id == 1:
            return None
        return thread_id

    @staticmethod
    def _format_bad_request(exc: BadRequest) -> str:
        """Normalize PTB BadRequest messages for pattern matching."""
        return str(exc).strip()

    @classmethod
    def _is_html_parse_error(cls, exc: BadRequest) -> bool:
        return bool(_TELEGRAM_HTML_PARSE_ERR_RE.search(cls._format_bad_request(exc)))

    @classmethod
    def _is_thread_not_found_error(cls, exc: BadRequest) -> bool:
        return bool(_TELEGRAM_THREAD_NOT_FOUND_RE.search(cls._format_bad_request(exc)))

    @classmethod
    def _is_message_not_modified_error(cls, exc: BadRequest) -> bool:
        return bool(_TELEGRAM_MESSAGE_NOT_MODIFIED_RE.search(cls._format_bad_request(exc)))

    @staticmethod
    def _without_message_thread_id(kwargs: dict[str, object]) -> dict[str, object]:
        next_kwargs = dict(kwargs)
        next_kwargs.pop("message_thread_id", None)
        return next_kwargs

    async def _send_with_thread_fallback(self, sender, **kwargs):
        """Retry one Telegram send without message_thread_id when the thread no longer exists."""
        try:
            return await self._send_with_retry(sender, **kwargs)
        except BadRequest as exc:
            if "message_thread_id" not in kwargs or not self._is_thread_not_found_error(exc):
                raise
            logger.warning("Telegram thread not found; retrying without message_thread_id")
            fallback_kwargs = self._without_message_thread_id(kwargs)
            return await self._send_with_retry(sender, **fallback_kwargs)

    async def _send_text_with_fallback(
        self,
        *,
        sender,
        text: str,
        plain_text: str | None = None,
        parse_mode: str | None = None,
        allow_thread_fallback: bool = False,
        ignore_not_modified: bool = False,
        **kwargs,
    ):
        """Send or edit Telegram text, retrying plain text on HTML parse failures."""
        send_kwargs = dict(kwargs)
        if send_kwargs.get("reply_markup") is None:
            send_kwargs.pop("reply_markup", None)
        send_kwargs["text"] = text
        if parse_mode == "HTML":
            send_kwargs["parse_mode"] = "HTML"

        try:
            if allow_thread_fallback:
                return await self._send_with_thread_fallback(sender, **send_kwargs)
            return await self._send_with_retry(sender, **send_kwargs)
        except BadRequest as exc:
            if ignore_not_modified and self._is_message_not_modified_error(exc):
                return None
            if parse_mode != "HTML" or not self._is_html_parse_error(exc):
                raise

            fallback_kwargs = dict(send_kwargs)
            fallback_kwargs.pop("parse_mode", None)
            fallback_kwargs["text"] = plain_text if plain_text is not None else text
            if allow_thread_fallback:
                return await self._send_with_thread_fallback(sender, **fallback_kwargs)
            try:
                return await self._send_with_retry(sender, **fallback_kwargs)
            except BadRequest as fallback_exc:
                if ignore_not_modified and self._is_message_not_modified_error(fallback_exc):
                    return None
                raise

    async def _send_media_with_fallback(
        self,
        *,
        sender,
        caption_plain: str | None = None,
        parse_mode: str | None = None,
        allow_thread_fallback: bool = False,
        **kwargs,
    ):
        """Send Telegram media, retrying without HTML parse mode when captions fail."""
        send_kwargs = dict(kwargs)
        if parse_mode == "HTML" and caption_plain:
            send_kwargs["parse_mode"] = "HTML"

        try:
            if allow_thread_fallback:
                return await self._send_with_thread_fallback(sender, **send_kwargs)
            return await self._send_with_retry(sender, **send_kwargs)
        except BadRequest as exc:
            if parse_mode != "HTML" or not caption_plain or not self._is_html_parse_error(exc):
                raise
            fallback_kwargs = dict(send_kwargs)
            fallback_kwargs.pop("parse_mode", None)
            fallback_kwargs["caption"] = caption_plain
            if allow_thread_fallback:
                return await self._send_with_thread_fallback(sender, **fallback_kwargs)
            return await self._send_with_retry(sender, **fallback_kwargs)

    def _prune_recent_updates(self, now_monotonic: float) -> None:
        """Drop expired dedupe keys and cap the cache to the configured max size."""
        while self._recent_update_keys:
            oldest_key = next(iter(self._recent_update_keys))
            seen_at = self._recent_update_keys[oldest_key]
            if now_monotonic - seen_at <= _TELEGRAM_RECENT_UPDATE_TTL_SECONDS:
                break
            self._recent_update_keys.popitem(last=False)

        while len(self._recent_update_keys) > _TELEGRAM_RECENT_UPDATE_MAX:
            self._recent_update_keys.popitem(last=False)

    @staticmethod
    def _message_like_from_update(update: Update) -> object | None:
        """Resolve the primary Telegram message-like payload from an update."""
        return (
            getattr(update, "message", None)
            or getattr(update, "edited_message", None)
            or getattr(update, "channel_post", None)
            or getattr(update, "edited_channel_post", None)
            or getattr(getattr(update, "callback_query", None), "message", None)
        )

    @classmethod
    def _update_dedupe_key(cls, update: Update) -> str | None:
        """Build an OpenClaw-style dedupe key for Telegram updates."""
        update_id = getattr(update, "update_id", None)
        if isinstance(update_id, int):
            return f"update:{update_id}"

        callback = getattr(update, "callback_query", None)
        callback_id = getattr(callback, "id", None)
        if isinstance(callback_id, str) and callback_id.strip():
            return f"callback:{callback_id.strip()}"

        message = cls._message_like_from_update(update)
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)
        if chat_id is None:
            chat_id = getattr(message, "chat_id", None)
        message_id = getattr(message, "message_id", None)
        if chat_id is not None and isinstance(message_id, int):
            return f"message:{chat_id}:{message_id}"
        return None

    def _should_skip_update(self, update: Update) -> bool:
        """Return whether this Telegram update was recently processed already."""
        key = self._update_dedupe_key(update)
        if not key:
            return False

        now_monotonic = time.monotonic()
        self._prune_recent_updates(now_monotonic)
        if key in self._recent_update_keys:
            self._recent_update_keys.move_to_end(key)
            self._recent_update_keys[key] = now_monotonic
            logger.debug("Telegram duplicate update skipped: {}", key)
            return True

        self._recent_update_keys[key] = now_monotonic
        self._recent_update_keys.move_to_end(key)
        self._prune_recent_updates(now_monotonic)
        return False

    def _prune_sent_message_keys(self, now_monotonic: float) -> None:
        """Drop expired sent-message cache entries and cap the cache size."""
        while self._sent_message_keys:
            oldest_key = next(iter(self._sent_message_keys))
            seen_at = self._sent_message_keys[oldest_key]
            if now_monotonic - seen_at <= _TELEGRAM_SENT_MESSAGE_TTL_SECONDS:
                break
            self._sent_message_keys.popitem(last=False)

        while len(self._sent_message_keys) > _TELEGRAM_SENT_MESSAGE_MAX:
            self._sent_message_keys.popitem(last=False)

    def _remember_sent_message(self, *, chat_id: int | str, message_id: object) -> None:
        """Remember a bot-authored message id so reaction routing can filter on own messages."""
        if not isinstance(message_id, int):
            return
        key = (str(chat_id), message_id)
        now_monotonic = time.monotonic()
        self._sent_message_keys[key] = now_monotonic
        self._sent_message_keys.move_to_end(key)
        self._prune_sent_message_keys(now_monotonic)

    def _was_sent_by_bot(self, *, chat_id: int | str, message_id: object) -> bool:
        """Return whether the message id was recently produced by this bot."""
        if not isinstance(message_id, int):
            return False
        now_monotonic = time.monotonic()
        self._prune_sent_message_keys(now_monotonic)
        key = (str(chat_id), message_id)
        if key not in self._sent_message_keys:
            return False
        self._sent_message_keys[key] = now_monotonic
        self._sent_message_keys.move_to_end(key)
        return True

    @staticmethod
    def _should_keep_typing_for_outbound(msg: OutboundMessage) -> bool:
        """Return whether Telegram typing should remain active after this outbound."""
        metadata = msg.metadata or {}
        if bool(metadata.get("_telegram_keep_typing")):
            return True
        if bool(metadata.get("_progress_heartbeat")):
            return True
        if bool(metadata.get("async_pdf")):
            return True
        return bool(metadata.get("_telegram_stream")) and not bool(metadata.get("_telegram_stream_final"))

    @classmethod
    def _resolve_reply_target_sender(cls, reply_like) -> str | None:
        """Return a simple sender label for a replied-to Telegram message."""
        if reply_like is None:
            return None
        reply_from = getattr(reply_like, "from_user", None)
        first_name = str(getattr(reply_from, "first_name", "") or "").strip()
        if first_name:
            return first_name
        username = str(getattr(reply_from, "username", "") or "").strip()
        if username:
            return username
        user_id = getattr(reply_from, "id", None)
        return str(user_id).strip() if user_id is not None else None

    @staticmethod
    def _resolve_reply_media_placeholder(reply_like) -> str | None:
        """Mirror OpenClaw-style media placeholders for replied-to Telegram messages."""
        if reply_like is None:
            return None
        if getattr(reply_like, "photo", None):
            return "<media:image>"
        if getattr(reply_like, "video", None) or getattr(reply_like, "video_note", None):
            return "<media:video>"
        if getattr(reply_like, "audio", None) or getattr(reply_like, "voice", None):
            return "<media:audio>"
        if getattr(reply_like, "document", None):
            return "<media:document>"
        if getattr(reply_like, "sticker", None):
            return "<media:sticker>"
        return None

    @classmethod
    def _resolve_reply_context(cls, message) -> dict[str, object]:
        """Extract reply target metadata from Telegram reply and quote fields."""
        reply_to_message = getattr(message, "reply_to_message", None)
        external_reply = getattr(message, "external_reply", None)
        reply_like = reply_to_message or external_reply
        quote = getattr(message, "quote", None)
        external_quote = getattr(external_reply, "quote", None) if external_reply is not None else None

        quote_text = str(getattr(quote, "text", "") or getattr(external_quote, "text", "") or "").strip()
        if quote_text:
            reply_body = quote_text
            reply_is_quote = True
        else:
            reply_body = str(getattr(reply_like, "text", "") or getattr(reply_like, "caption", "") or "").strip()
            reply_is_quote = False
            if not reply_body:
                reply_body = cls._resolve_reply_media_placeholder(reply_like) or ""

        if not reply_body:
            return {}

        metadata: dict[str, object] = {"reply_to_body": reply_body}
        reply_message_id = cls._normalize_message_id(getattr(reply_like, "message_id", None))
        if reply_message_id is not None:
            metadata["reply_to_id"] = reply_message_id
        reply_sender = cls._resolve_reply_target_sender(reply_like)
        if reply_sender:
            metadata["reply_to_sender"] = reply_sender
        if reply_is_quote:
            metadata["reply_to_is_quote"] = True
        return metadata

    @staticmethod
    def _resolve_forward_context(message) -> dict[str, object]:
        """Extract forwarded message metadata (OpenClaw bot-message-context.ts parity)."""
        forward_origin = getattr(message, "forward_origin", None)
        forward_date = getattr(message, "forward_date", None)
        if forward_origin is None and forward_date is None:
            return {}

        metadata: dict[str, object] = {"is_forwarded": True}
        if forward_date is not None:
            metadata["forward_date"] = str(forward_date)

        # Origin type determines what we can extract
        origin_type = getattr(forward_origin, "type", None)
        if origin_type == "user":
            fwd_user = getattr(forward_origin, "sender_user", None)
            if fwd_user is not None:
                metadata["forward_from"] = getattr(fwd_user, "first_name", None) or str(getattr(fwd_user, "id", ""))
                metadata["forward_from_id"] = getattr(fwd_user, "id", None)
        elif origin_type == "channel":
            fwd_chat = getattr(forward_origin, "chat", None)
            if fwd_chat is not None:
                metadata["forward_from_chat"] = getattr(fwd_chat, "title", None) or str(getattr(fwd_chat, "id", ""))
                metadata["forward_from_chat_id"] = getattr(fwd_chat, "id", None)
        elif origin_type == "hidden_user":
            metadata["forward_from"] = getattr(forward_origin, "sender_user_name", None) or "[hidden]"
        return metadata

    @staticmethod
    def _resolve_location_context(message) -> dict[str, object]:
        """Extract location/venue from a Telegram message."""
        location = getattr(message, "location", None)
        venue = getattr(message, "venue", None)
        if location is None and venue is None:
            return {}
        metadata: dict[str, object] = {}
        if venue is not None:
            loc = getattr(venue, "location", None) or location
            metadata["location"] = {
                "latitude": getattr(loc, "latitude", None),
                "longitude": getattr(loc, "longitude", None),
                "title": getattr(venue, "title", None),
                "address": getattr(venue, "address", None),
            }
        elif location is not None:
            metadata["location"] = {
                "latitude": getattr(location, "latitude", None),
                "longitude": getattr(location, "longitude", None),
            }
        return metadata

    @classmethod
    def _build_inbound_delivery_context(cls, message, user) -> tuple[dict[str, object], str]:
        """Build OpenClaw-style Telegram routing context for inbound messages."""
        chat = getattr(message, "chat", None)
        chat_type = getattr(chat, "type", None)
        sender_chat = getattr(message, "sender_chat", None)
        is_group = chat_type in {"group", "supergroup"}
        is_channel_post = chat_type == "channel"
        is_forum = bool(getattr(chat, "is_forum", False))
        raw_thread_id = cls._normalize_message_id(getattr(message, "message_thread_id", None))
        resolved_forum_thread_id = raw_thread_id if raw_thread_id is not None else 1 if is_forum else None
        actor_id = getattr(user, "id", None)
        if actor_id is None:
            actor_id = getattr(sender_chat, "id", None)
        username = getattr(user, "username", None)
        if username is None:
            username = getattr(sender_chat, "username", None)
        first_name = getattr(user, "first_name", None)
        if first_name is None:
            first_name = getattr(sender_chat, "title", None) or getattr(sender_chat, "username", None)

        metadata: dict[str, object] = {
            "message_id": getattr(message, "message_id", None),
            "user_id": actor_id,
            "username": username,
            "first_name": first_name,
            "is_group": is_group,
            "is_forum": is_forum,
        }
        if is_channel_post:
            metadata["is_channel_post"] = True
        if is_forum and resolved_forum_thread_id is not None:
            metadata["message_thread_id"] = resolved_forum_thread_id
        elif not is_group and raw_thread_id is not None:
            metadata["message_thread_id"] = raw_thread_id
        metadata.update(cls._resolve_reply_context(message))
        metadata.update(cls._resolve_forward_context(message))
        metadata.update(cls._resolve_location_context(message))

        chat_id = str(message.chat_id)
        if is_channel_post:
            return metadata, f"telegram:channel:{chat_id}"
        if is_group:
            if resolved_forum_thread_id is not None:
                return metadata, f"telegram:group:{chat_id}:topic:{resolved_forum_thread_id}"
            return metadata, f"telegram:group:{chat_id}"

        direct_peer_id = str(actor_id or chat_id)
        if raw_thread_id is not None:
            return metadata, f"telegram:direct:{direct_peer_id}:thread:{chat_id}:{raw_thread_id}"
        return metadata, f"telegram:direct:{direct_peer_id}"

    @staticmethod
    def _build_media_item(
        *,
        path: str,
        mime_type: str | None,
        filename: str | None,
        size_bytes: object,
        media_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Build a structured media item that survives the nanobot-to-app gateway hop."""
        item: dict[str, object] = {
            "url": path,
            "content_type": str(mime_type or ""),
            "filename": str(filename or Path(path).name),
            "size": size_bytes if isinstance(size_bytes, int) else 0,
        }
        if media_type:
            item["type"] = media_type
        if metadata:
            item["metadata"] = metadata
        return item

    async def _download_inbound_media(self, media_file, *, media_type: str) -> tuple[str, dict[str, object]] | None:
        """Download one inbound Telegram attachment and describe it for gateway conversion."""
        if not self._app:
            return None

        file = await self._app.bot.get_file(media_file.file_id)
        ext = self._get_extension(media_type, getattr(media_file, "mime_type", None))
        media_dir = Path.home() / ".nanobot" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
        await file.download_to_drive(str(file_path))
        return str(file_path), self._build_media_item(
            path=str(file_path),
            mime_type=getattr(media_file, "mime_type", None),
            filename=getattr(media_file, "file_name", None),
            size_bytes=getattr(media_file, "file_size", 0),
            media_type=media_type,
        )

    @staticmethod
    def _reaction_sender_label(user) -> str:
        """Render the OpenClaw-style label used in Telegram reaction events."""
        first_name = str(getattr(user, "first_name", "") or "").strip()
        last_name = str(getattr(user, "last_name", "") or "").strip()
        username = str(getattr(user, "username", "") or "").strip()
        display_name = " ".join(part for part in (first_name, last_name) if part).strip()
        if display_name and username:
            return f"{display_name} (@{username})"
        if display_name:
            return display_name
        if username:
            return f"@{username}"
        user_id = getattr(user, "id", None)
        return f"id:{user_id}" if user_id is not None else "unknown"

    @classmethod
    def _build_reaction_delivery_context(cls, reaction, user) -> tuple[dict[str, object], str]:
        """Build routing metadata for Telegram message_reaction updates."""
        chat = getattr(reaction, "chat", None)
        chat_id = str(getattr(chat, "id", ""))
        chat_type = getattr(chat, "type", None)
        is_group = chat_type in {"group", "supergroup"}
        is_forum = bool(getattr(chat, "is_forum", False))
        actor_id = getattr(user, "id", None)
        metadata: dict[str, object] = {
            "message_id": getattr(reaction, "message_id", None),
            "user_id": actor_id,
            "username": getattr(user, "username", None),
            "first_name": getattr(user, "first_name", None),
            "is_group": is_group,
            "is_forum": is_forum,
        }
        if is_group:
            return metadata, f"telegram:group:{chat_id}"

        direct_peer_id = str(actor_id or chat_id)
        return metadata, f"telegram:direct:{direct_peer_id}"

    @staticmethod
    def _resolve_allowed_updates() -> list[str]:
        """Match OpenClaw's wider Telegram update subscription set."""
        return ["message", "callback_query", "channel_post", "message_reaction"]

    @staticmethod
    def list_supported_actions() -> list[str]:
        """Return the Telegram action types supported by this channel adapter.

        Mirrors OpenClaw's ``listActions()`` pattern for action discovery.
        """
        return [
            "edit_text", "edit_buttons", "delete", "react",
            "poll", "topic_create", "sticker", "pin", "unpin",
        ]

    @staticmethod
    def _command_registry():
        """Resolve the shared app command registry when available."""
        try:
            from app.domain.services.command_registry import get_command_registry

            return get_command_registry()
        except Exception as exc:  # pragma: no cover - defensive import guard
            logger.debug("Telegram command registry unavailable: {}", exc)
            return None

    @classmethod
    def _custom_command_entries(cls) -> list[tuple[str, str]]:
        """Return Telegram-safe primary custom commands from the shared app registry."""
        registry = cls._command_registry()
        if registry is None:
            return []

        entries: list[tuple[str, str]] = []
        seen: set[str] = set(cls._KNOWN_SLASH_COMMANDS)
        for command, _skill_id, description in registry.get_available_commands():
            normalized_command = str(command or "").strip().lower()
            normalized_description = str(description or "").strip()
            if (
                not normalized_command
                or normalized_command in seen
                or not _TELEGRAM_MENU_COMMAND_RE.fullmatch(normalized_command)
                or not normalized_description
            ):
                continue
            entries.append((normalized_command, normalized_description[:256]))
            seen.add(normalized_command)
        return entries

    @classmethod
    def _all_known_slash_commands(cls) -> set[str]:
        """Return built-in Telegram commands plus app-registered command aliases."""
        known = set(cls._KNOWN_SLASH_COMMANDS)
        registry = cls._command_registry()
        if registry is None:
            return known
        known.update(str(command).strip().lower() for command in registry.get_command_map())
        return {command for command in known if command}

    @classmethod
    def _build_registered_bot_commands(cls) -> list[BotCommand]:
        """Merge built-in Telegram commands with shared app custom commands."""
        commands = list(cls.BOT_COMMANDS)
        commands.extend(BotCommand(command, description) for command, description in cls._custom_command_entries())
        return commands[:_TELEGRAM_MAX_COMMANDS]

    @classmethod
    def _help_entries(cls) -> list[tuple[str, str]]:
        """Return built-in and custom commands for Telegram help rendering."""
        entries = [(command.command, command.description) for command in cls.BOT_COMMANDS]
        entries.extend(cls._custom_command_entries())
        return entries

    @staticmethod
    def _format_help_command_name(command: str) -> str:
        """Render one Telegram command label for help text."""
        normalized = str(command or "").strip().lower()
        if normalized in {"link", "bind"}:
            return f"/{normalized} <CODE>"
        return f"/{normalized}"

    @classmethod
    def _build_help_pagination_keyboard(cls, current_page: int, total_pages: int) -> InlineKeyboardMarkup | None:
        """Build OpenClaw-style Telegram pagination controls for /help."""
        if total_pages <= 1:
            return None

        buttons: list[InlineKeyboardButton] = []
        if current_page > 1:
            buttons.append(InlineKeyboardButton(text="◀ Prev", callback_data=f"commands_page_{current_page - 1}"))
        buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="commands_page_noop"))
        if current_page < total_pages:
            buttons.append(InlineKeyboardButton(text="Next ▶", callback_data=f"commands_page_{current_page + 1}"))
        return InlineKeyboardMarkup([buttons]) if buttons else None

    @classmethod
    def _build_help_page(cls, page: int = 1) -> tuple[str, InlineKeyboardMarkup | None]:
        """Render one Telegram /help page with optional inline pagination."""
        entries = cls._help_entries()
        total_pages = max(1, (len(entries) + _TELEGRAM_HELP_PAGE_SIZE - 1) // _TELEGRAM_HELP_PAGE_SIZE)
        current_page = min(max(1, int(page)), total_pages)
        start = (current_page - 1) * _TELEGRAM_HELP_PAGE_SIZE
        end = start + _TELEGRAM_HELP_PAGE_SIZE
        page_entries = entries[start:end]

        header = f"🤖 Pythinker commands ({current_page}/{total_pages})" if total_pages > 1 else "🤖 Pythinker commands"
        lines = [header]
        lines.extend(
            f"{cls._format_help_command_name(command)} — {description}" for command, description in page_entries
        )
        return "\n".join(lines), cls._build_help_pagination_keyboard(current_page, total_pages)

    @classmethod
    def _build_help_text(cls) -> str:
        """Backward-compatible help text accessor for the first Telegram help page."""
        return cls._build_help_page(1)[0]

    @staticmethod
    def _parse_commands_page_callback_data(value: str) -> int | str | None:
        """Parse `commands_page_*` callback tokens."""
        match = re.fullmatch(r"commands_page_(\d+|noop)(?::.+)?", value.strip())
        if match is None:
            return None
        page_value = match.group(1)
        if page_value == "noop":
            return "noop"
        page = int(page_value)
        return page if page > 0 else None

    @staticmethod
    def _normalize_inline_buttons_scope(value: object) -> str:
        """Normalize Telegram inline button scope config to a supported value."""
        normalized = str(value or "").strip().lower()
        if normalized in {"off", "dm", "group", "all", "allowlist"}:
            return normalized
        return "allowlist"

    @classmethod
    def _inline_buttons_allowed_for_scope(cls, *, scope: str, is_group: bool) -> bool:
        """Return whether Telegram inline buttons are allowed for the given chat surface."""
        normalized_scope = cls._normalize_inline_buttons_scope(scope)
        if normalized_scope == "off":
            return False
        if normalized_scope == "dm":
            return not is_group
        if normalized_scope == "group":
            return is_group
        return True

    @staticmethod
    def _metadata_is_group(metadata: dict[str, object], chat_id: str) -> bool:
        """Infer whether an outbound Telegram target is group-like."""
        raw_is_group = metadata.get("is_group")
        if isinstance(raw_is_group, bool):
            return raw_is_group
        try:
            return int(str(chat_id).strip()) < 0
        except (TypeError, ValueError):
            return False

    def _inline_buttons_allowed_for_outbound(self, *, chat_id: str, metadata: dict[str, object]) -> bool:
        """Return whether reply markup should be attached to an outbound Telegram message."""
        scope = self._normalize_inline_buttons_scope(getattr(self.config, "inline_buttons_scope", "allowlist"))
        return self._inline_buttons_allowed_for_scope(
            scope=scope,
            is_group=self._metadata_is_group(metadata, chat_id),
        )

    def _inline_buttons_allowed_for_message(self, message) -> bool:
        """Return whether inline-button callbacks are allowed for the inbound message surface."""
        chat = getattr(message, "chat", None)
        chat_type = getattr(chat, "type", None)
        is_group = chat_type in {"group", "supergroup", "channel"}
        scope = self._normalize_inline_buttons_scope(getattr(self.config, "inline_buttons_scope", "allowlist"))
        return self._inline_buttons_allowed_for_scope(scope=scope, is_group=is_group)

    @staticmethod
    def _allow_entries_match(sender_id: str, entries: list[str]) -> bool:
        """Match sender identity against Telegram allowlist entries."""
        if "*" in entries:
            return True
        sender = str(sender_id or "").strip()
        if not sender:
            return False
        candidates = [sender, *[part for part in sender.split("|") if part]]
        return any(candidate in entries for candidate in candidates)

    @staticmethod
    def _chat_rule_key(message) -> str:
        """Normalize the Telegram chat id used for direct/group override lookup."""
        return str(getattr(message, "chat_id", ""))

    @classmethod
    def _topic_rule_key(cls, message) -> str | None:
        """Normalize the Telegram topic/thread id used for override lookup."""
        chat = getattr(message, "chat", None)
        is_forum = bool(getattr(chat, "is_forum", False))
        raw_thread_id = cls._normalize_message_id(getattr(message, "message_thread_id", None))
        if is_forum:
            return str(raw_thread_id or 1)
        if raw_thread_id is not None:
            return str(raw_thread_id)
        return None

    def _resolve_group_rule(self, message):
        """Resolve per-group policy override for this chat."""
        return (getattr(self.config, "groups", {}) or {}).get(self._chat_rule_key(message))

    def _resolve_direct_rule(self, message):
        """Resolve per-DM policy override for this direct chat."""
        return (getattr(self.config, "direct", {}) or {}).get(self._chat_rule_key(message))

    @classmethod
    def _resolve_topic_rule(cls, *, rule_owner, message):
        """Resolve per-topic policy override beneath a group/direct rule."""
        if rule_owner is None:
            return None
        topics = getattr(rule_owner, "topics", {}) or {}
        topic_key = cls._topic_rule_key(message)
        if topic_key is None:
            return None
        return topics.get(topic_key)

    @staticmethod
    def _rule_allow_from(rule_owner) -> list[str]:
        """Return the allow_from entries for a rule owner, preserving explicit empties."""
        if rule_owner is None:
            return []
        return [str(value) for value in (getattr(rule_owner, "allow_from", []) or []) if str(value).strip()]

    def _effective_dm_policy(self, *, direct_rule, topic_rule) -> str:
        """Resolve the DM policy after direct/topic overrides."""
        if direct_rule is not None:
            dm_policy = getattr(direct_rule, "dm_policy", None)
            if isinstance(dm_policy, str) and dm_policy.strip():
                return dm_policy.strip().lower()
        return str(getattr(self.config, "dm_policy", "open") or "open").strip().lower()

    def _effective_group_policy(self, *, group_rule, topic_rule) -> str:
        """Resolve the group policy after topic/group overrides."""
        for owner in (topic_rule, group_rule):
            if owner is None:
                continue
            group_policy = getattr(owner, "group_policy", None)
            if isinstance(group_policy, str) and group_policy.strip():
                return group_policy.strip().lower()
        return str(getattr(self.config, "group_policy", "open") or "open").strip().lower()

    def _effective_group_require_mention(self, *, group_rule, topic_rule) -> bool:
        """Resolve mention gating after topic/group overrides."""
        for owner in (topic_rule, group_rule):
            if owner is None:
                continue
            require_mention = getattr(owner, "require_mention", None)
            if require_mention is not None:
                return bool(require_mention)
        return bool(getattr(self.config, "group_require_mention", False))

    def _effective_dm_allow_from(self, *, direct_rule, topic_rule) -> list[str]:
        """Resolve DM allowlist after direct/topic overrides."""
        for owner in (topic_rule, direct_rule):
            if owner is None:
                continue
            entries = self._rule_allow_from(owner)
            if entries:
                return entries
        return [str(value) for value in (getattr(self.config, "allow_from", []) or []) if str(value).strip()]

    def _effective_group_allow_from(self, *, group_rule, topic_rule) -> list[str]:
        """Resolve group sender allowlist after topic/group overrides."""
        for owner in (topic_rule, group_rule):
            if owner is None:
                continue
            entries = self._rule_allow_from(owner)
            if entries:
                return entries
        configured = getattr(self.config, "group_allow_from", None) or getattr(self.config, "allow_from", [])
        return [str(value) for value in configured if str(value).strip()]

    def _group_is_explicitly_allowlisted(self, *, group_rule, topic_rule) -> bool:
        """Treat explicit group/topic config entries as chat-level allowlist authorization."""
        return topic_rule is not None or group_rule is not None

    @staticmethod
    def _is_linking_command(content: str) -> bool:
        """Return whether a message is an onboarding command that should bypass DM allowlists."""
        normalized = str(content or "").strip().lower()
        return (
            normalized.startswith("/link ") or normalized.startswith("/bind ") or normalized.startswith("/start bind_")
        )

    def _message_mentions_bot(self, message) -> bool:
        """Resolve whether a group message explicitly mentions or replies to the bot."""
        if self._bot_user_id is not None:
            reply_to_message = getattr(message, "reply_to_message", None)
            reply_from = getattr(reply_to_message, "from_user", None)
            if getattr(reply_from, "id", None) == self._bot_user_id:
                return True

        username = str(self._bot_username or "").strip().lower()
        if username:
            text_candidates = [
                str(getattr(message, "text", "") or ""),
                str(getattr(message, "caption", "") or ""),
            ]
            if any(f"@{username}" in candidate.lower() for candidate in text_candidates):
                return True

        parse_entities = getattr(message, "parse_entities", None)
        if callable(parse_entities):
            try:
                entities = parse_entities() or {}
            except Exception:
                entities = {}
            for text in entities.values():
                entity_text = str(text or "").strip().lower()
                if username and entity_text == f"@{username}":
                    return True
        return False

    async def _reply_pairing_required(self, message) -> None:
        """Explain how to authorize a Telegram DM when pairing/allowlist blocks it."""
        reply_text = getattr(message, "reply_text", None)
        if not callable(reply_text):
            return
        await reply_text(
            "This Telegram chat is not authorized yet. "
            "Ask the owner to add you to the allowlist or use /link CODE from the web app."
        )

    async def _is_inbound_allowed(
        self,
        *,
        message,
        user,
        sender_id: str,
        content: str,
        enforce_mention: bool = True,
    ) -> bool:
        """Evaluate Telegram DM/group/topic policy before forwarding inbound content."""
        chat = getattr(message, "chat", None)
        chat_type = getattr(chat, "type", None)
        is_group_like = chat_type in {"group", "supergroup", "channel"}
        direct_rule = self._resolve_direct_rule(message)
        group_rule = self._resolve_group_rule(message) if is_group_like else None
        rule_owner = group_rule if is_group_like else direct_rule
        topic_rule = self._resolve_topic_rule(rule_owner=rule_owner, message=message)

        if rule_owner is not None and getattr(rule_owner, "enabled", True) is False:
            return False
        if topic_rule is not None and getattr(topic_rule, "enabled", True) is False:
            return False

        if not is_group_like:
            dm_policy = self._effective_dm_policy(direct_rule=direct_rule, topic_rule=topic_rule)
            if dm_policy == "disabled":
                return False
            if dm_policy == "open":
                return True
            if self._is_linking_command(content):
                return True
            allow_entries = self._effective_dm_allow_from(direct_rule=direct_rule, topic_rule=topic_rule)
            if self._allow_entries_match(sender_id, allow_entries):
                return True
            if dm_policy == "pairing":
                await self._reply_pairing_required(message)
            return False

        group_policy = self._effective_group_policy(group_rule=group_rule, topic_rule=topic_rule)
        if group_policy == "disabled":
            return False
        if group_policy == "allowlist":
            allow_entries = self._effective_group_allow_from(group_rule=group_rule, topic_rule=topic_rule)
            if not allow_entries and not self._group_is_explicitly_allowlisted(
                group_rule=group_rule, topic_rule=topic_rule
            ):
                return False
            if allow_entries and not self._allow_entries_match(sender_id, allow_entries):
                return False
        if enforce_mention and self._effective_group_require_mention(group_rule=group_rule, topic_rule=topic_rule):
            return self._message_mentions_bot(message)
        return True

    async def _run_polling_loop(self, *, allowed_updates: list[str]) -> None:
        """Poll Telegram directly so transport behavior stays channel-owned."""
        if not self._app:
            return

        try:
            await self._app.bot.delete_webhook(drop_pending_updates=False)
        except Exception as exc:
            logger.debug("Telegram delete_webhook before polling failed: {}", exc)

        last_update_id = await read_telegram_update_offset(bot_token=self.config.token)
        retry_attempt = 0

        while self._running and not self._shutdown_event.is_set():
            offset = last_update_id + 1 if last_update_id is not None else None
            try:
                self._active_polling_request = asyncio.create_task(
                    self._app.bot.get_updates(
                        offset=offset,
                        timeout=30,
                        allowed_updates=allowed_updates,
                    )
                )
                if bool(getattr(self.config, "polling_stall_restart_enabled", True)):
                    stall_timeout_seconds = max(
                        1.0,
                        float(getattr(self.config, "polling_stall_timeout_seconds", 60.0) or 60.0),
                    )
                    updates = await asyncio.wait_for(
                        asyncio.shield(self._active_polling_request),
                        timeout=stall_timeout_seconds,
                    )
                else:
                    updates = await self._active_polling_request
                retry_attempt = 0
            except TimeoutError:
                logger.warning("Telegram polling stalled; retrying get_updates")
                if self._active_polling_request is not None:
                    self._active_polling_request.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._active_polling_request
                self._active_polling_request = None
                continue
            except asyncio.CancelledError:
                break
            except (TimedOut, NetworkError, OSError) as exc:
                retry_attempt += 1
                delay_seconds = min(30.0, float(max(1, retry_attempt)))
                logger.warning("Telegram polling error (attempt {}): {}", retry_attempt, exc)
                await asyncio.sleep(delay_seconds)
                continue
            finally:
                self._active_polling_request = None

            for update in updates or ():
                if not self._running or self._shutdown_event.is_set():
                    break
                await self._app.process_update(update)
                update_id = getattr(update, "update_id", None)
                if not isinstance(update_id, int):
                    continue
                last_update_id = update_id
                try:
                    await write_telegram_update_offset(update_id=update_id, bot_token=self.config.token)
                except Exception as exc:
                    logger.debug("Telegram offset persistence failed: {}", exc)

    @classmethod
    def _sender_id_for_message(cls, message, user) -> str:
        """Resolve sender identity for regular users, anonymous admins, and channel posts."""
        if user is not None:
            return cls._sender_id(user)
        sender_chat = getattr(message, "sender_chat", None)
        sender_chat_id = getattr(sender_chat, "id", None)
        username = getattr(sender_chat, "username", None)
        if sender_chat_id is None:
            sender_chat_id = getattr(message, "chat_id", None)
        if username:
            return f"chat:{sender_chat_id}|{username}"
        return f"chat:{sender_chat_id}"

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        keep_typing_after_send = self._should_keep_typing_for_outbound(msg)
        if not keep_typing_after_send:
            self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error("Invalid chat_id: {}", msg.chat_id)
            return

        metadata = msg.metadata or {}
        reply_to_mode = self._reply_to_mode()
        base_reply_params = self._reply_parameters_for_metadata(metadata, reply_to_mode)
        message_thread_id = self._resolve_outbound_message_thread_id(metadata)
        parse_mode = str(metadata.get("parse_mode", "HTML"))
        delivery_mode = str(metadata.get("delivery_mode", "text"))
        reply_markup = self._coerce_reply_markup(metadata.get("reply_markup"))
        if reply_markup is not None and not self._inline_buttons_allowed_for_outbound(
            chat_id=msg.chat_id,
            metadata=metadata,
        ):
            reply_markup = None
        cleanup_paths = [str(path) for path in metadata.get("cleanup_media_paths", []) if isinstance(path, str)]
        content_hash = str(metadata.get("content_hash", "")).strip()
        caption_value = str(metadata.get("caption", msg.content or ""))
        caption_sent = False
        media_success = True
        raw_media_attachments = metadata.get("media_attachments", [])
        media_attachment_map = {
            str(item.get("url", "") or ""): item
            for item in raw_media_attachments
            if isinstance(item, dict) and str(item.get("url", "") or "").strip()
        }
        allow_thread_fallback = message_thread_id is not None and not bool(metadata.get("is_forum"))
        reply_applied = self._any_lane_reply_applied(msg)
        action_reply_params = (
            base_reply_params
            if self._should_include_reply_for_send(reply_to_mode, reply_applied=reply_applied)
            else None
        )

        if await self._dispatch_telegram_action(
            msg,
            chat_id=chat_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            reply_parameters=action_reply_params,
            message_thread_id=message_thread_id,
            allow_thread_fallback=allow_thread_fallback,
        ):
            if keep_typing_after_send and msg.chat_id not in self._typing_tasks:
                self._start_typing(msg.chat_id)
            self._cleanup_temp_files(cleanup_paths)
            return

        if bool(metadata.get("_progress")) and bool(metadata.get("_telegram_stream")):
            if not self._is_stream_preview_message(msg):
                return
            preview_reply_params = (
                base_reply_params
                if self._should_include_reply_for_send(reply_to_mode, reply_applied=reply_applied)
                else None
            )
            await self._send_or_edit_preview(
                msg,
                chat_id=chat_id,
                parse_mode=parse_mode,
                reply_params=preview_reply_params,
                message_thread_id=message_thread_id,
                allow_thread_fallback=allow_thread_fallback,
            )
            if keep_typing_after_send and msg.chat_id not in self._typing_tasks:
                self._start_typing(msg.chat_id)
            return

        if self._has_preview_state(msg) or self._preview_base_key(msg) in self._archived_previews:
            preview_finalized = await self._finalize_preview_with_text(
                msg,
                chat_id=chat_id,
                parse_mode=parse_mode,
                delivery_mode=delivery_mode,
                reply_markup=reply_markup,
            )
            if preview_finalized:
                return
            await self._clear_preview(msg, chat_id=chat_id)

        # Send media files first. For document mode, caption is sent on the first document.
        for media_path in msg.media or []:
            try:
                attachment_metadata = media_attachment_map.get(media_path)
                media_type = self._get_media_type(media_path)
                current_reply_params = (
                    base_reply_params
                    if self._should_include_reply_for_send(reply_to_mode, reply_applied=reply_applied)
                    else None
                )
                sticker_metadata = (
                    attachment_metadata.get("metadata", {})
                    if isinstance(attachment_metadata, dict)
                    and str(attachment_metadata.get("type", "") or "").strip().lower() == "sticker"
                    else {}
                )
                telegram_sticker_metadata = (
                    sticker_metadata.get("telegram", {}) if isinstance(sticker_metadata, dict) else {}
                )
                sticker_file_id = (
                    str(telegram_sticker_metadata.get("file_id", "") or "").strip()
                    if isinstance(telegram_sticker_metadata, dict)
                    else ""
                )
                if sticker_file_id:
                    sticker_kwargs: dict[str, object] = {"chat_id": chat_id, "sticker": sticker_file_id}
                    if current_reply_params is not None:
                        sticker_kwargs["reply_parameters"] = current_reply_params
                    if message_thread_id is not None:
                        sticker_kwargs["message_thread_id"] = message_thread_id
                    if allow_thread_fallback:
                        response = await self._send_with_thread_fallback(self._app.bot.send_sticker, **sticker_kwargs)
                    else:
                        response = await self._send_with_retry(self._app.bot.send_sticker, **sticker_kwargs)
                    self._remember_sent_message(chat_id=chat_id, message_id=getattr(response, "message_id", None))
                    if current_reply_params is not None:
                        reply_applied = True
                    continue

                sender = {
                    "photo": self._app.bot.send_photo,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = (
                    "photo" if media_type == "photo" else media_type if media_type in ("voice", "audio") else "document"
                )

                send_kwargs: dict[str, object] = {
                    "chat_id": chat_id,
                }
                if current_reply_params is not None:
                    send_kwargs["reply_parameters"] = current_reply_params
                if message_thread_id is not None:
                    send_kwargs["message_thread_id"] = message_thread_id
                if media_type == "document" and not caption_sent and caption_value:
                    send_kwargs["caption"] = caption_value[:1024]
                    if reply_markup is not None:
                        send_kwargs["reply_markup"] = reply_markup
                    caption_sent = True

                if media_type == "document" and content_hash:
                    cached_file_id = await self._get_cached_pdf_file_id(content_hash)
                    if cached_file_id:
                        send_kwargs[param] = cached_file_id
                        await self._send_media_with_fallback(
                            sender=sender,
                            parse_mode=parse_mode,
                            caption_plain=caption_value[:1024] if caption_sent and caption_value else None,
                            allow_thread_fallback=allow_thread_fallback,
                            **send_kwargs,
                        )
                        if current_reply_params is not None:
                            reply_applied = True
                        continue

                if "://" in media_path:
                    send_kwargs[param] = media_path
                    response = await self._send_media_with_fallback(
                        sender=sender,
                        parse_mode=parse_mode,
                        caption_plain=caption_value[:1024] if caption_sent and caption_value else None,
                        allow_thread_fallback=allow_thread_fallback,
                        **send_kwargs,
                    )
                else:
                    # PTB expects a live file handle for local uploads during the awaited send call.
                    with open(media_path, "rb") as handle:  # noqa: ASYNC230
                        send_kwargs[param] = handle
                        response = await self._send_media_with_fallback(
                            sender=sender,
                            parse_mode=parse_mode,
                            caption_plain=caption_value[:1024] if caption_sent and caption_value else None,
                            allow_thread_fallback=allow_thread_fallback,
                            **send_kwargs,
                        )

                if current_reply_params is not None:
                    reply_applied = True

                if media_type == "document" and content_hash:
                    response_document = getattr(response, "document", None)
                    file_id = getattr(response_document, "file_id", None)
                    if isinstance(file_id, str) and file_id:
                        await self._store_cached_pdf_file_id(content_hash, file_id)
                self._remember_sent_message(chat_id=chat_id, message_id=getattr(response, "message_id", None))
            except Exception as exc:
                filename = media_path.rsplit("/", 1)[-1]
                media_success = False
                logger.error("Failed to send media {}: {}", media_path, exc)
                try:
                    await self._send_text_with_fallback(
                        sender=self._app.bot.send_message,
                        text=f"[Failed to send: {filename}]",
                        plain_text=f"[Failed to send: {filename}]",
                        chat_id=chat_id,
                        reply_parameters=current_reply_params,
                        message_thread_id=message_thread_id,
                        allow_thread_fallback=allow_thread_fallback,
                    )
                except Exception as fallback_exc:
                    logger.error("Failed to send Telegram media error notice: {}", fallback_exc)
                break

        should_send_text = bool(msg.content and msg.content != "[empty message]")
        if delivery_mode == "pdf_only" and caption_sent and media_success:
            should_send_text = False

        if should_send_text:
            max_chunks = max(1, int(getattr(self.config, "max_messages_per_batch", 5)))
            for index, chunk in enumerate(_split_message(msg.content)[:max_chunks]):
                try:
                    payload_text = _markdown_to_telegram_html(chunk) if parse_mode == "HTML" else chunk
                    current_reply_params = (
                        base_reply_params
                        if self._should_include_reply_for_send(reply_to_mode, reply_applied=reply_applied)
                        else None
                    )
                    response = await self._send_text_with_fallback(
                        sender=self._app.bot.send_message,
                        text=payload_text,
                        plain_text=chunk,
                        parse_mode=parse_mode if parse_mode == "HTML" else None,
                        chat_id=chat_id,
                        reply_parameters=current_reply_params,
                        reply_markup=reply_markup if index == 0 else None,
                        message_thread_id=message_thread_id,
                        allow_thread_fallback=allow_thread_fallback,
                    )
                    self._remember_sent_message(chat_id=chat_id, message_id=getattr(response, "message_id", None))
                    if current_reply_params is not None:
                        reply_applied = True
                except Exception as exc:
                    logger.error("Error sending Telegram text chunk: {}", exc)
                    break

        if keep_typing_after_send and msg.chat_id not in self._typing_tasks:
            self._start_typing(msg.chat_id)

        self._cleanup_temp_files(cleanup_paths)

    async def _dispatch_telegram_action(
        self,
        msg: OutboundMessage,
        *,
        chat_id: int,
        parse_mode: str,
        reply_markup: InlineKeyboardMarkup | None,
        reply_parameters: ReplyParameters | None,
        message_thread_id: int | None,
        allow_thread_fallback: bool,
    ) -> bool:
        """Dispatch Telegram-native actions embedded in outbound metadata."""
        if not self._app:
            return False

        metadata = msg.metadata or {}
        action = metadata.get("telegram_action")
        if not isinstance(action, dict):
            return False

        action_type = str(action.get("type", "") or "").strip().lower()
        message_id = self._normalize_message_id(action.get("message_id"))
        if not action_type:
            return False

        if action_type == "edit_text":
            if message_id is None:
                return False
            payload_text = _markdown_to_telegram_html(msg.content) if parse_mode == "HTML" else msg.content
            await self._send_text_with_fallback(
                sender=self._app.bot.edit_message_text,
                text=payload_text,
                plain_text=msg.content,
                parse_mode=parse_mode if parse_mode == "HTML" else None,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                ignore_not_modified=True,
            )
            return True

        if action_type == "edit_buttons":
            if message_id is None:
                return False
            try:
                await self._send_with_retry(
                    self._app.bot.edit_message_reply_markup,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=reply_markup,
                )
            except BadRequest as exc:
                if not self._is_message_not_modified_error(exc):
                    raise
            return True

        if action_type == "delete":
            if message_id is None:
                return False
            await self._send_with_retry(
                self._app.bot.delete_message,
                chat_id=chat_id,
                message_id=message_id,
            )
            return True

        if action_type == "react":
            if message_id is None:
                return False
            remove = bool(action.get("remove"))
            emoji = str(action.get("emoji", "") or "").strip()
            if remove:
                reaction: ReactionTypeEmoji | None = None
            elif emoji:
                reaction = ReactionTypeEmoji(emoji=emoji)
            else:
                return False

            await self._send_with_retry(
                self._app.bot.set_message_reaction,
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction,
            )
            return True

        if action_type == "poll":
            question = str(action.get("question", "") or "").strip()
            raw_options = action.get("options")
            if not question or not isinstance(raw_options, list):
                return False
            options = [str(option).strip() for option in raw_options if str(option).strip()]
            if len(options) < 2:
                return False
            poll_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "question": question,
                "options": options,
            }
            if "allows_multiple_answers" in action:
                poll_kwargs["allows_multiple_answers"] = bool(action.get("allows_multiple_answers"))
            if "is_anonymous" in action:
                poll_kwargs["is_anonymous"] = bool(action.get("is_anonymous"))
            open_period = self._normalize_message_id(action.get("open_period"))
            if open_period is not None:
                poll_kwargs["open_period"] = open_period
            if reply_parameters is not None:
                poll_kwargs["reply_parameters"] = reply_parameters
            if message_thread_id is not None:
                poll_kwargs["message_thread_id"] = message_thread_id
            if allow_thread_fallback:
                response = await self._send_with_thread_fallback(self._app.bot.send_poll, **poll_kwargs)
            else:
                response = await self._send_with_retry(self._app.bot.send_poll, **poll_kwargs)
            self._remember_sent_message(chat_id=chat_id, message_id=getattr(response, "message_id", None))
            return True

        if action_type == "topic_create":
            name = str(action.get("name", "") or "").strip()
            if not name:
                return False
            topic_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "name": name,
            }
            icon_color = self._normalize_message_id(action.get("icon_color"))
            if icon_color is not None:
                topic_kwargs["icon_color"] = icon_color
            icon_custom_emoji_id = str(action.get("icon_custom_emoji_id", "") or "").strip()
            if icon_custom_emoji_id:
                topic_kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id
            await self._send_with_retry(self._app.bot.create_forum_topic, **topic_kwargs)
            return True

        if action_type == "sticker":
            file_id = str(action.get("file_id", "") or "").strip()
            if not file_id:
                return False
            sticker_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "sticker": file_id,
            }
            if reply_parameters is not None:
                sticker_kwargs["reply_parameters"] = reply_parameters
            if message_thread_id is not None:
                sticker_kwargs["message_thread_id"] = message_thread_id
            if allow_thread_fallback:
                response = await self._send_with_thread_fallback(self._app.bot.send_sticker, **sticker_kwargs)
            else:
                response = await self._send_with_retry(self._app.bot.send_sticker, **sticker_kwargs)
            self._remember_sent_message(chat_id=chat_id, message_id=getattr(response, "message_id", None))
            return True

        if action_type == "pin":
            if message_id is None:
                return False
            pin_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "message_id": message_id,
            }
            if bool(action.get("disable_notification")):
                pin_kwargs["disable_notification"] = True
            await self._send_with_retry(self._app.bot.pin_chat_message, **pin_kwargs)
            return True

        if action_type == "unpin":
            if message_id is None:
                return False
            await self._send_with_retry(
                self._app.bot.unpin_chat_message,
                chat_id=chat_id,
                message_id=message_id,
            )
            return True

        return False

    async def _send_with_retry(self, sender, **kwargs):
        """Send with RetryAfter/transient retry handling."""
        max_attempts = max(1, int(getattr(self.config, "send_retry_max_attempts", 3)))
        base_delay = max(
            0.1,
            float(
                getattr(
                    self.config,
                    "send_retry_base_delay_seconds",
                    getattr(self.config, "rate_limit_cooldown_seconds", 3),
                )
            ),
        )
        max_delay = max(base_delay, float(getattr(self.config, "send_retry_max_delay_seconds", 30.0)))
        for attempt in range(max_attempts):
            try:
                return await sender(**kwargs)
            except BadRequest:
                raise
            except RetryAfter as exc:
                retry_after = exc.retry_after
                seconds = (
                    float(retry_after.total_seconds()) if hasattr(retry_after, "total_seconds") else float(retry_after)
                )
                wait_seconds = max(seconds, float(base_delay))
                logger.warning("Telegram rate limited, retrying in {}s", wait_seconds)
                await asyncio.sleep(wait_seconds)
            except (TimedOut, NetworkError, OSError) as exc:
                if attempt >= max_attempts - 1:
                    raise
                backoff = min(max_delay, float(base_delay * (attempt + 1)))
                logger.warning("Telegram transient send error (attempt {}): {}", attempt + 1, exc)
                await asyncio.sleep(backoff)
        raise RuntimeError("Telegram send retries exhausted")

    def _is_stream_preview_message(self, msg: OutboundMessage) -> bool:
        """Return whether an outbound is a streamed Telegram preview delta."""
        metadata = msg.metadata or {}
        return (
            self._normalize_streaming_mode(getattr(self.config, "streaming", "partial")) != "off"
            and bool(metadata.get("_progress"))
            and bool(metadata.get("_telegram_stream"))
        )

    def _has_preview_state(self, msg: OutboundMessage, *, lane: str = "answer") -> bool:
        """Return whether a non-finalized preview lifecycle exists for this outbound lane."""
        state = self._preview_states.get(self._preview_key(msg, lane=lane))
        return state is not None and not state.finalized

    def _has_any_preview_state(self, msg: OutboundMessage) -> bool:
        """Return True if any lane has a non-finalized preview."""
        return any(self._has_preview_state(msg, lane=lane) for lane in ("answer", "reasoning"))

    def _any_lane_reply_applied(self, msg: OutboundMessage) -> bool:
        """Return True if reply threading was already applied in any lane."""
        for lane in ("answer", "reasoning"):
            state = self._preview_states.get(self._preview_key(msg, lane=lane))
            if state is not None and state.reply_applied:
                return True
        return False

    def _preview_key(self, msg: OutboundMessage, *, lane: str = "answer") -> str:
        """Key preview state by chat, source message id, and delivery lane."""
        return f"{self._preview_base_key(msg)}:{lane}"

    @staticmethod
    def _preview_base_key(msg: OutboundMessage) -> str:
        """Base key (chat + source message) shared across all lanes."""
        metadata = msg.metadata or {}
        source_message_id = metadata.get("message_id")
        return f"{msg.chat_id}:{source_message_id or 'root'}"

    async def _send_or_edit_preview(
        self,
        msg: OutboundMessage,
        *,
        chat_id: int,
        parse_mode: str,
        reply_params: ReplyParameters | None,
        message_thread_id: int | None,
        allow_thread_fallback: bool,
    ) -> None:
        """Accumulate stream deltas into a single lane-aware preview message."""
        if not self._app:
            return

        lane = str((msg.metadata or {}).get("_telegram_stream_lane", "answer")).strip()
        key = self._preview_key(msg, lane=lane)
        state = self._preview_states.setdefault(key, _TelegramPreviewState())

        # Skip updates to a finalized lane (OpenClaw per-lane finalization)
        if state.finalized:
            return

        preview_override = (msg.metadata or {}).get("_telegram_stream_preview_text")
        if isinstance(preview_override, str):
            state.content = preview_override
        elif msg.content:
            state.content += msg.content

        is_final = bool((msg.metadata or {}).get("_telegram_stream_final"))
        if not state.content and is_final:
            if state.message_id is None:
                self._preview_states.pop(key, None)
            return

        rendered_text = self._render_preview_text(state.content, parse_mode=parse_mode)
        if not rendered_text or len(rendered_text) > 4000:
            return

        min_initial_chars = max(0, int(getattr(self.config, "streaming_min_initial_chars", 30)))
        if state.message_id is None and len(state.content) < min_initial_chars:
            return

        now = time.monotonic()
        throttle_seconds = max(0.0, float(getattr(self.config, "streaming_throttle_seconds", 1.0)))
        if (
            state.message_id is not None
            and not is_final
            and throttle_seconds > 0.0
            and now - state.last_sent_at < throttle_seconds
        ):
            return

        if rendered_text == state.last_text:
            return

        # Regressive update blocking: never shrink a visible preview (OpenClaw lane-delivery.ts:123-138)
        if state.message_id is not None and len(rendered_text) < len(state.last_text):
            return

        if state.message_id is None:
            sent_message = await self._send_text_with_fallback(
                sender=self._app.bot.send_message,
                text=rendered_text,
                plain_text=state.content,
                parse_mode=parse_mode if parse_mode == "HTML" else None,
                chat_id=chat_id,
                reply_parameters=reply_params,
                message_thread_id=message_thread_id,
                allow_thread_fallback=allow_thread_fallback,
            )
            sent_message_id = getattr(sent_message, "message_id", None)
            if isinstance(sent_message_id, int):
                state.message_id = sent_message_id
                self._remember_sent_message(chat_id=chat_id, message_id=sent_message_id)
            if reply_params is not None:
                state.reply_applied = True
        else:
            await self._send_text_with_fallback(
                sender=self._app.bot.edit_message_text,
                text=rendered_text,
                plain_text=state.content,
                parse_mode=parse_mode if parse_mode == "HTML" else None,
                chat_id=chat_id,
                message_id=state.message_id,
                ignore_not_modified=True,
            )

        state.last_text = rendered_text
        state.last_sent_at = now

    async def _finalize_preview_with_text(
        self,
        msg: OutboundMessage,
        *,
        chat_id: int,
        parse_mode: str,
        delivery_mode: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> bool:
        """Edit the answer-lane preview in place when the final reply is text-only.

        Also attempts archived-preview consumption (OpenClaw lane-delivery.ts:317-359):
        if no active answer preview exists but an archived preview is available,
        the archived message is edited in-place instead of creating a new message.
        """
        if not self._app:
            return False
        if msg.media or delivery_mode == "pdf_only":
            return False

        rendered_text = self._render_preview_text(msg.content, parse_mode=parse_mode)
        if not rendered_text or len(rendered_text) > 4000:
            return False

        answer_key = self._preview_key(msg, lane="answer")
        state = self._preview_states.get(answer_key)

        # Try active preview first
        target_message_id: int | None = state.message_id if state else None

        # Archived preview consumption: reuse an old preview message if no active one
        base_key = self._preview_base_key(msg)
        archived: _ArchivedPreview | None = None
        if target_message_id is None:
            archived_list = self._archived_previews.get(base_key)
            if archived_list:
                archived = archived_list.pop(0)
                target_message_id = archived.message_id
                if not archived_list:
                    self._archived_previews.pop(base_key, None)

        if target_message_id is None:
            return False

        # Check regressive blocking against the source text
        source_last_text = state.last_text if state else (archived.last_text if archived else "")
        if source_last_text and len(rendered_text) < len(source_last_text):
            # Still consumed — just don't shrink
            pass
        elif rendered_text != source_last_text:
            await self._send_text_with_fallback(
                sender=self._app.bot.edit_message_text,
                text=rendered_text,
                plain_text=msg.content,
                parse_mode=parse_mode if parse_mode == "HTML" else None,
                chat_id=chat_id,
                message_id=target_message_id,
                reply_markup=reply_markup,
                ignore_not_modified=True,
            )

        # Mark lane as finalized and clean up
        if state:
            state.finalized = True
        self._preview_states.pop(answer_key, None)
        return True

    async def _clear_preview(self, msg: OutboundMessage, *, chat_id: int) -> None:
        """Remove all lane preview states and delete visible preview messages."""
        for lane in ("answer", "reasoning"):
            key = self._preview_key(msg, lane=lane)
            state = self._preview_states.pop(key, None)
            if state is not None and state.message_id is not None:
                await self._delete_preview_message(chat_id=chat_id, message_id=state.message_id)

        # Clean up any remaining archived previews for this message
        base_key = self._preview_base_key(msg)
        archived_list = self._archived_previews.pop(base_key, None)
        if archived_list:
            for ap in archived_list:
                if ap.delete_if_unused:
                    await self._delete_preview_message(chat_id=chat_id, message_id=ap.message_id)

    def _force_new_preview(self, msg: OutboundMessage, *, lane: str = "answer") -> None:
        """Archive the current lane preview and prepare for a new generation.

        Mirrors OpenClaw ``draft-stream.ts`` ``forceNewMessage()`` — the
        generation counter increments so late-arriving edits from the old
        generation are silently ignored.  The old preview message is stored
        as an archived preview for potential consumption by final delivery.
        """
        key = self._preview_key(msg, lane=lane)
        state = self._preview_states.pop(key, None)
        if state is None:
            return
        if state.message_id is not None:
            base_key = self._preview_base_key(msg)
            self._archived_previews.setdefault(base_key, []).append(
                _ArchivedPreview(
                    message_id=state.message_id,
                    last_text=state.last_text,
                    delete_if_unused=True,
                )
            )
        # Next setdefault will create a fresh state with generation+1
        self._preview_states[key] = _TelegramPreviewState(generation=state.generation + 1)

    async def _delete_preview_message(self, *, chat_id: int, message_id: int) -> None:
        """Delete a visible preview message."""
        if not self._app:
            return
        await self._send_with_retry(
            self._app.bot.delete_message,
            chat_id=chat_id,
            message_id=message_id,
        )

    @staticmethod
    def _render_preview_text(text: str, *, parse_mode: str) -> str:
        """Render preview text using the same parse-mode rules as normal sends."""
        if parse_mode == "HTML":
            return _markdown_to_telegram_html(text)
        return text

    def _cleanup_temp_files(self, paths: list[str]) -> None:
        """Delete temporary generated files after send attempts."""
        for raw_path in paths:
            if not raw_path or "://" in raw_path:
                continue
            try:
                Path(raw_path).unlink(missing_ok=True)
            except Exception as exc:
                logger.debug("Failed to cleanup temp file {}: {}", raw_path, exc)

    async def _get_cached_pdf_file_id(self, content_hash: str) -> str | None:
        """Return cached Telegram file_id for a PDF content hash if still fresh."""
        if not content_hash:
            return None

        # Primary cache: Redis (24h TTL) for cross-process reuse.
        if getattr(self.config, "pdf_file_id_cache_redis_enabled", False):
            redis_key = f"telegram:pdf:file_id:{content_hash}"
            try:
                from app.infrastructure.storage.redis import get_redis

                cached = await get_redis().call("get", redis_key, max_retries=1)
                if isinstance(cached, str) and cached:
                    return cached
            except Exception as exc:
                logger.debug("Telegram Redis file_id cache lookup failed: {}", exc)

        # Fallback cache: in-process memory.
        cached = self._pdf_file_id_cache.get(content_hash)
        if not cached:
            return None
        file_id, expires_at = cached
        if time.time() >= expires_at:
            self._pdf_file_id_cache.pop(content_hash, None)
            return None
        return file_id

    async def _store_cached_pdf_file_id(self, content_hash: str, file_id: str) -> None:
        """Cache Telegram file_id for fast re-delivery of identical PDFs."""
        if not content_hash or not file_id:
            return

        if getattr(self.config, "pdf_file_id_cache_redis_enabled", False):
            redis_key = f"telegram:pdf:file_id:{content_hash}"
            try:
                from app.infrastructure.storage.redis import get_redis

                await get_redis().call(
                    "setex",
                    redis_key,
                    self._pdf_file_id_cache_ttl_seconds,
                    file_id,
                    max_retries=1,
                )
            except Exception as exc:
                logger.debug("Telegram Redis file_id cache store failed: {}", exc)

        expires_at = time.time() + self._pdf_file_id_cache_ttl_seconds
        self._pdf_file_id_cache[content_hash] = (file_id, expires_at)

    @staticmethod
    def _coerce_reply_markup(value: object) -> InlineKeyboardMarkup | None:
        """Convert metadata dict keyboard payloads into Telegram InlineKeyboardMarkup."""
        if isinstance(value, InlineKeyboardMarkup):
            return value
        if not isinstance(value, dict):
            return None
        keyboard = value.get("inline_keyboard")
        if not isinstance(keyboard, list):
            return None

        rows: list[list[InlineKeyboardButton]] = []
        for row in keyboard:
            if not isinstance(row, list):
                continue
            buttons: list[InlineKeyboardButton] = []
            for button in row:
                if not isinstance(button, dict):
                    continue
                text = str(button.get("text", "")).strip()
                if not text:
                    continue
                buttons.append(
                    InlineKeyboardButton(
                        text=text,
                        callback_data=button.get("callback_data"),
                        url=button.get("url"),
                    )
                )
            if buttons:
                rows.append(buttons)
        return InlineKeyboardMarkup(rows) if rows else None

    @staticmethod
    def _parse_follow_up_callback_data(value: str) -> tuple[str | None, int] | None:
        """Parse compact follow-up callback data into anchor/id parts."""
        if not value.startswith(_FOLLOW_UP_CALLBACK_PREFIX):
            return None
        payload = value[len(_FOLLOW_UP_CALLBACK_PREFIX) :]
        if ":" not in payload:
            return None
        anchor_event_id, index_raw = payload.rsplit(":", 1)
        try:
            index = int(index_raw)
        except ValueError:
            return None
        if index < 0:
            return None
        normalized_anchor = anchor_event_id.strip() or None
        return normalized_anchor, index

    @staticmethod
    def _button_attr(button: object, name: str) -> Any:
        """Read one inline button attribute from PTB objects or test doubles."""
        if isinstance(button, dict):
            return button.get(name)
        return getattr(button, name, None)

    @classmethod
    def _resolve_callback_button_text(cls, message: object, callback_data: str) -> str | None:
        """Find the clicked inline button text from the callback message keyboard."""
        reply_markup = getattr(message, "reply_markup", None)
        keyboard = getattr(reply_markup, "inline_keyboard", None)
        if not isinstance(keyboard, list):
            return None
        for row in keyboard:
            if not isinstance(row, list):
                continue
            for button in row:
                if str(cls._button_attr(button, "callback_data") or "").strip() != callback_data:
                    continue
                text = str(cls._button_attr(button, "text") or "").strip()
                if text:
                    return text
        return None

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        if self._should_skip_update(update):
            return
        metadata, session_key = self._build_inbound_delivery_context(update.message, update.effective_user)

        # PYTHINKER-PATCH: Telegram deep link `/start bind_<CODE>` must be
        # forwarded to the bus so MessageRouter can normalize it to `/link CODE`.
        if context.args:
            payload = " ".join(context.args).strip()
            if payload.lower().startswith("bind_"):
                await self._handle_message(
                    sender_id=self._sender_id(update.effective_user),
                    chat_id=str(update.message.chat_id),
                    content=f"/start {payload}",
                    metadata=metadata,
                    session_key=session_key,
                )
                return

        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm Pythinker.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command, bypassing ACL so all users can access it."""
        if not update.message:
            return
        if self._should_skip_update(update):
            return
        help_text, reply_markup = self._build_help_page(1)
        reply_kwargs = {"reply_markup": reply_markup} if reply_markup is not None else {}
        await update.message.reply_text(help_text, **reply_kwargs)

    async def _unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown slash commands with a help hint."""
        if not update.message:
            return
        if self._should_skip_update(update):
            return
        command_name = self._extract_command_name(update.message.text)
        if command_name is None:
            return
        # Known commands can still reach this callback because handlers run by group.
        # Ignore them here so users do not see a false "Unknown command" response.
        if command_name in self._KNOWN_SLASH_COMMANDS:
            return
        if command_name in self._all_known_slash_commands():
            await self._forward_command_message(update.message, update.effective_user)
            return
        await update.message.reply_text("Unknown command. Use /help to see available commands.")

    @staticmethod
    def _extract_command_name(text: str | None) -> str | None:
        """Parse slash command token, supporting optional `/cmd@BotName` form."""
        if not text or not text.startswith("/"):
            return None
        token = text.split(maxsplit=1)[0]
        command = token[1:].split("@", 1)[0].strip().lower()
        return command or None

    @staticmethod
    def _sender_id(user) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward slash commands to the bus for unified handling in AgentLoop."""
        del context
        if not update.message or not update.effective_user:
            return
        if self._should_skip_update(update):
            return
        await self._forward_command_message(update.message, update.effective_user)

    async def _forward_command_message(self, message, user) -> None:
        """Forward one already-authorized Telegram slash-command message to the bus."""
        if message is None or user is None:
            return
        if not await self._is_inbound_allowed(
            message=message,
            user=user,
            sender_id=self._sender_id(user),
            content=str(getattr(message, "text", "") or ""),
        ):
            return
        metadata, session_key = self._build_inbound_delivery_context(message, user)
        await self._handle_message(
            sender_id=self._sender_id(user),
            chat_id=str(message.chat_id),
            content=message.text,
            metadata=metadata,
            session_key=session_key,
        )

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard callbacks and forward supported actions to router."""
        del context
        callback = update.callback_query
        if callback is None:
            return
        if self._should_skip_update(update):
            return

        data = (callback.data or "").strip()
        await callback.answer()

        if not data:
            return

        user = callback.from_user
        if user is None or callback.message is None:
            return
        if not self._inline_buttons_allowed_for_message(callback.message):
            return

        commands_page = self._parse_commands_page_callback_data(data)
        if commands_page is not None:
            if commands_page == "noop":
                return
            if self._app is None:
                return
            help_text, reply_markup = self._build_help_page(int(commands_page))
            try:
                await self._app.bot.edit_message_text(
                    callback.message.chat_id,
                    callback.message.message_id,
                    help_text,
                    reply_markup=reply_markup,
                )
            except BadRequest as exc:
                if not self._is_message_not_modified_error(exc):
                    raise
            return

        metadata, session_key = self._build_inbound_delivery_context(callback.message, user)
        follow_up = self._parse_follow_up_callback_data(data)
        if data == "telegram:get_pdf:last":
            content = "/pdf"
        elif follow_up is not None:
            anchor_event_id, _index = follow_up
            selected_suggestion = self._resolve_callback_button_text(callback.message, data)
            content = selected_suggestion or data
            if selected_suggestion:
                metadata["follow_up"] = {
                    "selected_suggestion": selected_suggestion,
                    "source": "suggestion_click",
                    **({"anchor_event_id": anchor_event_id} if anchor_event_id else {}),
                }
        else:
            content = data
        if not await self._is_inbound_allowed(
            message=callback.message,
            user=user,
            sender_id=self._sender_id(user),
            content=content,
        ):
            return
        await self._handle_message(
            sender_id=self._sender_id(user),
            chat_id=str(callback.message.chat_id),
            content=content,
            metadata=metadata,
            session_key=session_key,
        )

    async def _on_message_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward Telegram emoji reactions as agent-visible system events."""
        del context
        if self._should_skip_update(update):
            return

        reaction = getattr(update, "message_reaction", None)
        if reaction is None:
            return

        user = getattr(reaction, "user", None)
        if user is None or bool(getattr(user, "is_bot", False)):
            return

        mode = self._reaction_notification_mode(getattr(self.config, "reaction_notifications", "own"))
        if mode == "off":
            return

        chat = getattr(reaction, "chat", None)
        chat_id = getattr(chat, "id", None)
        message_id = getattr(reaction, "message_id", None)
        if chat_id is None or not isinstance(message_id, int):
            return
        if mode == "own" and not self._was_sent_by_bot(chat_id=chat_id, message_id=message_id):
            return

        pseudo_message = SimpleNamespace(
            chat=chat,
            chat_id=chat_id,
            message_id=message_id,
            message_thread_id=None,
            reply_to_message=None,
            text=None,
            caption=None,
        )
        sender_id = self._sender_id(user)
        if not await self._is_inbound_allowed(
            message=pseudo_message,
            user=user,
            sender_id=sender_id,
            content="",
            enforce_mention=False,
        ):
            return

        old_emojis = {
            str(getattr(entry, "emoji", ""))
            for entry in (getattr(reaction, "old_reaction", None) or [])
            if getattr(entry, "type", None) == "emoji" and str(getattr(entry, "emoji", "")).strip()
        }
        added_emojis = [
            str(getattr(entry, "emoji", "")).strip()
            for entry in (getattr(reaction, "new_reaction", None) or [])
            if getattr(entry, "type", None) == "emoji"
            and str(getattr(entry, "emoji", "")).strip()
            and str(getattr(entry, "emoji", "")).strip() not in old_emojis
        ]
        if not added_emojis:
            return

        sender_label = self._reaction_sender_label(user)
        metadata, session_key = self._build_reaction_delivery_context(reaction, user)
        for emoji in added_emojis:
            reaction_metadata = dict(metadata)
            reaction_metadata.update(
                {
                    "telegram_reaction": {
                        "emoji": emoji,
                        "message_id": message_id,
                    },
                }
            )
            await self._handle_message(
                sender_id=sender_id,
                chat_id=str(chat_id),
                content=f"Telegram reaction added: {emoji} by {sender_label} on msg {message_id}",
                metadata=reaction_metadata,
                session_key=session_key,
            )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        del context
        message = self._message_like_from_update(update)
        if message is None:
            return
        if self._should_skip_update(update):
            return

        user = getattr(update, "effective_user", None) or getattr(message, "from_user", None)
        chat_id = message.chat_id
        sender_id = self._sender_id_for_message(message, user)

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        # Build content from text and/or media
        content_parts = []
        media_paths = []
        media_items: list[dict[str, object]] = []
        sticker_metadata: dict[str, object] | None = None

        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Handle media files
        media_file = None
        media_type = None

        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"
        elif getattr(message, "video", None):
            media_file = message.video
            media_type = "video"
        elif getattr(message, "video_note", None):
            media_file = message.video_note
            media_type = "video_note"
        elif getattr(message, "sticker", None):
            media_file = message.sticker
            media_type = "sticker"

        # Download media if present
        if media_file and self._app:
            file_path: str | None = None
            try:
                if media_type == "sticker":
                    sticker_metadata = {
                        "emoji": getattr(media_file, "emoji", None),
                        "file_id": getattr(media_file, "file_id", None),
                        "file_unique_id": getattr(media_file, "file_unique_id", None),
                        "is_animated": bool(getattr(media_file, "is_animated", False)),
                        "is_video": bool(getattr(media_file, "is_video", False)),
                        "set_name": getattr(media_file, "set_name", None),
                    }
                    if bool(getattr(media_file, "is_animated", False)) or bool(getattr(media_file, "is_video", False)):
                        logger.debug("Telegram skipping unsupported animated/video sticker payload")
                    else:
                        downloaded = await self._download_inbound_media(media_file, media_type=media_type)
                        if downloaded is not None:
                            file_path, media_item = downloaded
                            media_item["metadata"] = {
                                "telegram": {
                                    "emoji": sticker_metadata.get("emoji"),
                                    "file_id": sticker_metadata.get("file_id"),
                                    "file_unique_id": sticker_metadata.get("file_unique_id"),
                                    "set_name": sticker_metadata.get("set_name"),
                                }
                            }
                            media_paths.append(file_path)
                            media_items.append(media_item)
                            content_parts.append(f"[sticker: {file_path}]")
                else:
                    downloaded = await self._download_inbound_media(media_file, media_type=media_type)
                    if downloaded is None:
                        raise RuntimeError("media download unavailable")
                    file_path, media_item = downloaded
                    media_paths.append(file_path)
                    media_items.append(media_item)

                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from nanobot.providers.transcription import GroqTranscriptionProvider

                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info("Transcribed {}: {}...", media_type, transcription[:50])
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                elif media_type != "sticker":
                    content_parts.append(f"[{media_type}: {file_path}]")

                if file_path is not None:
                    logger.debug("Downloaded {} to {}", media_type, file_path)
            except Exception as e:
                logger.error("Failed to download media: {}", e)
                content_parts.append(f"[{media_type}: download failed]")

        if getattr(message, "sticker", None) is not None and not media_paths and not content_parts:
            logger.debug("Telegram skipping unsupported sticker-only message")
            return

        content = "\n".join(content_parts) if content_parts else "[empty message]"

        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)
        metadata, session_key = self._build_inbound_delivery_context(message, user)
        if media_items:
            metadata["media_attachments"] = media_items
            metadata["media_items"] = [
                {
                    "url": str(item.get("url", "") or ""),
                    "mime_type": str(item.get("content_type", "") or ""),
                    "filename": str(item.get("filename", "") or ""),
                    "size_bytes": item.get("size", 0) if isinstance(item.get("size", 0), int) else 0,
                }
                for item in media_items
            ]
        if sticker_metadata is not None:
            metadata["telegram_sticker"] = sticker_metadata
        if not await self._is_inbound_allowed(
            message=message,
            user=user,
            sender_id=sender_id,
            content=content,
        ):
            return

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_id := getattr(message, "media_group_id", None):
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                self._media_group_buffers[key] = {
                    "sender_id": sender_id,
                    "chat_id": str_chat_id,
                    "contents": [],
                    "media": [],
                    "media_items": [],
                    "media_attachments": [],
                    "metadata": metadata,
                    "session_key": session_key,
                }
                self._start_typing(str_chat_id)
            buf = self._media_group_buffers[key]
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)
            buf["media_items"].extend(media_items)
            buf["media_attachments"].extend(media_items)
            if key not in self._media_group_tasks:
                self._media_group_tasks[key] = asyncio.create_task(self._flush_media_group(key))
            return

        # Start typing indicator before processing
        self._start_typing(str_chat_id)

        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
            session_key=session_key,
        )

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        session_key: str | None = None,
    ) -> None:
        """Publish Telegram inbound messages after channel-local policy checks."""
        msg = BusInboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {},
            session_key_override=session_key,
        )
        await self.bus.publish_inbound(msg)

    async def _flush_media_group(self, key: str) -> None:
        """Wait briefly, then forward buffered media-group as one turn."""
        try:
            await asyncio.sleep(0.6)
            if not (buf := self._media_group_buffers.pop(key, None)):
                return
            content = "\n".join(buf["contents"]) or "[empty message]"
            metadata = dict(buf["metadata"])
            if buf["media_items"]:
                seen_urls: set[str] = set()
                attachments = [
                    item
                    for item in buf["media_items"]
                    if isinstance(item, dict)
                    and isinstance(item.get("url"), str)
                    and not (item["url"] in seen_urls or seen_urls.add(item["url"]))
                ]
                metadata["media_attachments"] = attachments
                metadata["media_items"] = [
                    {
                        "url": str(item.get("url", "") or ""),
                        "mime_type": str(item.get("content_type", "") or ""),
                        "filename": str(item.get("filename", "") or ""),
                        "size_bytes": item.get("size", 0) if isinstance(item.get("size", 0), int) else 0,
                    }
                    for item in attachments
                ]
            await self._handle_message(
                sender_id=buf["sender_id"],
                chat_id=buf["chat_id"],
                content=content,
                media=list(dict.fromkeys(buf["media"])),
                metadata=metadata,
                session_key=buf["session_key"],
            )
        finally:
            self._media_group_tasks.pop(key, None)

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        logger.error("Telegram error: {}", context.error)

    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "video/mp4": ".mp4",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {
            "image": ".jpg",
            "voice": ".ogg",
            "audio": ".mp3",
            "video": ".mp4",
            "video_note": ".mp4",
            "sticker": ".webp",
            "file": "",
        }
        return type_map.get(media_type, "")
