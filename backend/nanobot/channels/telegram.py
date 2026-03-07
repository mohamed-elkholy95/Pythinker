"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters, Update
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import TelegramConfig


@dataclass(slots=True)
class _TelegramPreviewState:
    """Tracks the lifecycle of a streamed Telegram preview message."""

    content: str = ""
    message_id: int | None = None
    last_sent_at: float = 0.0
    last_text: str = ""


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

    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # 3. Headers # Title -> just the title text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)

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
        pos = cut.rfind('\n')
        if pos == -1:
            pos = cut.rfind(' ')
        if pos == -1:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.

    Simple and reliable - no webhook/public IP needed.
    """

    name = "telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("stop", "Stop the current task"),
        BotCommand("status", "Show current session status"),
        BotCommand("pdf", "Get the last response as a PDF"),
        BotCommand("link", "Link your account with a code"),
        BotCommand("bind", "Alias of /link for link codes"),
        BotCommand("help", "Show available commands"),
    ]
    _KNOWN_SLASH_COMMANDS = frozenset({"start", "new", "stop", "status", "pdf", "link", "bind", "help"})

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

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True

        # Build the application with larger connection pool to avoid pool-timeout on long runs
        req = HTTPXRequest(connection_pool_size=16, pool_timeout=5.0, connect_timeout=30.0, read_timeout=30.0)
        builder = Application.builder().token(self.config.token).request(req).get_updates_request(req)
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
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
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query, pattern=r"^telegram:get_pdf:last$"))

        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL)
                & ~filters.COMMAND,
                self._on_message
            )
        )
        # PYTHINKER-PATCH: unknown slash commands should return a help hint.
        self._app.add_handler(
            MessageHandler(filters.COMMAND, self._unknown_command),
            group=1,
        )

        logger.info("Starting Telegram bot (polling mode)...")

        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()

        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        logger.info("Telegram bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning("Failed to register bot commands: {}", e)

        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True  # Ignore old messages on startup
        )

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False

        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()
        self._preview_states.clear()

        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

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

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error("Invalid chat_id: {}", msg.chat_id)
            return

        metadata = msg.metadata or {}
        reply_params = None
        if self.config.reply_to_message:
            reply_to_message_id = metadata.get("message_id")
            if reply_to_message_id:
                reply_params = ReplyParameters(
                    message_id=reply_to_message_id,
                    allow_sending_without_reply=True
                )

        parse_mode = str(metadata.get("parse_mode", "HTML"))
        delivery_mode = str(metadata.get("delivery_mode", "text"))
        reply_markup = self._coerce_reply_markup(metadata.get("reply_markup"))
        cleanup_paths = [str(path) for path in metadata.get("cleanup_media_paths", []) if isinstance(path, str)]
        content_hash = str(metadata.get("content_hash", "")).strip()
        caption_value = str(metadata.get("caption", msg.content or ""))
        caption_sent = False
        media_success = True

        if self._is_stream_preview_message(msg):
            await self._send_or_edit_preview(
                msg,
                chat_id=chat_id,
                parse_mode=parse_mode,
                reply_params=reply_params,
            )
            return

        if self._has_preview_state(msg):
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
        for media_path in (msg.media or []):
            try:
                media_type = self._get_media_type(media_path)
                sender = {
                    "photo": self._app.bot.send_photo,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = "photo" if media_type == "photo" else media_type if media_type in ("voice", "audio") else "document"

                send_kwargs: dict[str, object] = {
                    "chat_id": chat_id,
                    "reply_parameters": reply_params,
                }
                if media_type == "document" and not caption_sent and caption_value:
                    send_kwargs["caption"] = caption_value[:1024]
                    send_kwargs["parse_mode"] = parse_mode
                    if reply_markup is not None:
                        send_kwargs["reply_markup"] = reply_markup
                    caption_sent = True

                if media_type == "document" and content_hash:
                    cached_file_id = await self._get_cached_pdf_file_id(content_hash)
                    if cached_file_id:
                        send_kwargs[param] = cached_file_id
                        await self._send_with_retry(sender, **send_kwargs)
                        continue

                if "://" in media_path:
                    send_kwargs[param] = media_path
                    response = await self._send_with_retry(sender, **send_kwargs)
                else:
                    with open(media_path, "rb") as handle:
                        send_kwargs[param] = handle
                        response = await self._send_with_retry(sender, **send_kwargs)

                if media_type == "document" and content_hash:
                    response_document = getattr(response, "document", None)
                    file_id = getattr(response_document, "file_id", None)
                    if isinstance(file_id, str) and file_id:
                        await self._store_cached_pdf_file_id(content_hash, file_id)
            except Exception as exc:
                filename = media_path.rsplit("/", 1)[-1]
                media_success = False
                logger.error("Failed to send media {}: {}", media_path, exc)
                try:
                    await self._send_with_retry(
                        self._app.bot.send_message,
                        chat_id=chat_id,
                        text=f"[Failed to send: {filename}]",
                        reply_parameters=reply_params,
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
                    if parse_mode == "HTML":
                        payload_text = _markdown_to_telegram_html(chunk)
                        await self._send_with_retry(
                            self._app.bot.send_message,
                            chat_id=chat_id,
                            text=payload_text,
                            parse_mode="HTML",
                            reply_parameters=reply_params,
                            reply_markup=reply_markup if index == 0 else None,
                        )
                    else:
                        await self._send_with_retry(
                            self._app.bot.send_message,
                            chat_id=chat_id,
                            text=chunk,
                            reply_parameters=reply_params,
                            reply_markup=reply_markup if index == 0 else None,
                        )
                except Exception as exc:
                    logger.error("Error sending Telegram text chunk: {}", exc)
                    break

        self._cleanup_temp_files(cleanup_paths)

    async def _send_with_retry(self, sender, **kwargs):  # noqa: ANN001, ANN202
        """Send with RetryAfter/transient retry handling."""
        max_attempts = 3
        base_delay = max(1, int(getattr(self.config, "rate_limit_cooldown_seconds", 3)))
        for attempt in range(max_attempts):
            try:
                return await sender(**kwargs)
            except RetryAfter as exc:
                retry_after = exc.retry_after
                seconds = float(retry_after.total_seconds()) if hasattr(retry_after, "total_seconds") else float(retry_after)
                wait_seconds = max(seconds, float(base_delay))
                logger.warning("Telegram rate limited, retrying in {}s", wait_seconds)
                await asyncio.sleep(wait_seconds)
            except (TimedOut, NetworkError, OSError) as exc:
                if attempt >= max_attempts - 1:
                    raise
                backoff = float(base_delay * (attempt + 1))
                logger.warning("Telegram transient send error (attempt {}): {}", attempt + 1, exc)
                await asyncio.sleep(backoff)
        raise RuntimeError("Telegram send retries exhausted")

    def _is_stream_preview_message(self, msg: OutboundMessage) -> bool:
        """Return whether an outbound is a streamed Telegram preview delta."""
        metadata = msg.metadata or {}
        return (
            str(getattr(self.config, "streaming", "partial")).lower() != "off"
            and bool(metadata.get("_progress"))
            and bool(metadata.get("_telegram_stream"))
        )

    def _has_preview_state(self, msg: OutboundMessage) -> bool:
        """Return whether a preview lifecycle exists for this outbound."""
        return self._preview_key(msg) in self._preview_states

    def _preview_key(self, msg: OutboundMessage) -> str:
        """Key preview state by chat and source Telegram message id."""
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
    ) -> None:
        """Accumulate stream deltas into a single preview message."""
        if not self._app:
            return

        state = self._preview_states.setdefault(self._preview_key(msg), _TelegramPreviewState())
        if msg.content:
            state.content += msg.content

        is_final = bool((msg.metadata or {}).get("_telegram_stream_final"))
        if not state.content and is_final:
            if state.message_id is None:
                self._preview_states.pop(self._preview_key(msg), None)
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

        if state.message_id is None:
            send_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "text": rendered_text,
                "reply_parameters": reply_params,
            }
            if parse_mode == "HTML":
                send_kwargs["parse_mode"] = "HTML"
            sent_message = await self._send_with_retry(
                self._app.bot.send_message,
                **send_kwargs,
            )
            sent_message_id = getattr(sent_message, "message_id", None)
            if isinstance(sent_message_id, int):
                state.message_id = sent_message_id
        else:
            edit_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "message_id": state.message_id,
                "text": rendered_text,
            }
            if parse_mode == "HTML":
                edit_kwargs["parse_mode"] = "HTML"
            await self._send_with_retry(
                self._app.bot.edit_message_text,
                **edit_kwargs,
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
        """Edit the preview in place when the final reply is text-only and eligible."""
        if not self._app:
            return False

        state = self._preview_states.get(self._preview_key(msg))
        if state is None or state.message_id is None:
            return False
        if msg.media or delivery_mode == "pdf_only":
            return False

        rendered_text = self._render_preview_text(msg.content, parse_mode=parse_mode)
        if not rendered_text or len(rendered_text) > 4000:
            return False

        if rendered_text != state.last_text:
            edit_kwargs: dict[str, object] = {
                "chat_id": chat_id,
                "message_id": state.message_id,
                "text": rendered_text,
                "reply_markup": reply_markup,
            }
            if parse_mode == "HTML":
                edit_kwargs["parse_mode"] = "HTML"
            await self._send_with_retry(
                self._app.bot.edit_message_text,
                **edit_kwargs,
            )

        self._preview_states.pop(self._preview_key(msg), None)
        return True

    async def _clear_preview(self, msg: OutboundMessage, *, chat_id: int) -> None:
        """Remove any preview state and delete the visible preview message if present."""
        state = self._preview_states.pop(self._preview_key(msg), None)
        if state is None or state.message_id is None:
            return
        await self._delete_preview_message(chat_id=chat_id, message_id=state.message_id)

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
            except Exception:
                pass

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
            except Exception:
                pass

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

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        # PYTHINKER-PATCH: Telegram deep link `/start bind_<CODE>` must be
        # forwarded to the bus so MessageRouter can normalize it to `/link CODE`.
        if context.args:
            payload = " ".join(context.args).strip()
            if payload.lower().startswith("bind_"):
                await self._handle_message(
                    sender_id=self._sender_id(update.effective_user),
                    chat_id=str(update.message.chat_id),
                    content=f"/start {payload}",
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
        await update.message.reply_text(
            "🤖 Pythinker commands:\n"
            "/new — Start a new conversation\n"
            "/stop — Stop the current task\n"
            "/status — Show current session status\n"
            "/pdf — Get the last response as a PDF\n"
            "/link <CODE> — Link your web account\n"
            "/bind <CODE> — Alias of /link\n"
            "/help — Show available commands"
        )

    async def _unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown slash commands with a help hint."""
        if not update.message:
            return
        command_name = self._extract_command_name(update.message.text)
        if command_name is None:
            return
        # Known commands can still reach this callback because handlers run by group.
        # Ignore them here so users do not see a false "Unknown command" response.
        if command_name in self._KNOWN_SLASH_COMMANDS:
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
        if not update.message or not update.effective_user:
            return
        await self._handle_message(
            sender_id=self._sender_id(update.effective_user),
            chat_id=str(update.message.chat_id),
            content=update.message.text,
        )

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard callbacks and forward supported actions to router."""
        del context
        callback = update.callback_query
        if callback is None:
            return

        data = (callback.data or "").strip()
        await callback.answer()

        if data != "telegram:get_pdf:last":
            return

        user = callback.from_user
        if user is None or callback.message is None:
            return

        await self._handle_message(
            sender_id=self._sender_id(user),
            chat_id=str(callback.message.chat_id),
            content="/pdf",
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        # Build content from text and/or media
        content_parts = []
        media_paths = []

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

        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type, getattr(media_file, 'mime_type', None))

                # Save to workspace/media/
                from pathlib import Path
                media_dir = Path.home() / ".nanobot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)

                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))

                media_paths.append(str(file_path))

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
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")

                logger.debug("Downloaded {} to {}", media_type, file_path)
            except Exception as e:
                logger.error("Failed to download media: {}", e)
                content_parts.append(f"[{media_type}: download failed]")

        content = "\n".join(content_parts) if content_parts else "[empty message]"

        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_id := getattr(message, "media_group_id", None):
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                self._media_group_buffers[key] = {
                    "sender_id": sender_id, "chat_id": str_chat_id,
                    "contents": [], "media": [],
                    "metadata": {
                        "message_id": message.message_id, "user_id": user.id,
                        "username": user.username, "first_name": user.first_name,
                        "is_group": message.chat.type != "private",
                    },
                }
                self._start_typing(str_chat_id)
            buf = self._media_group_buffers[key]
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)
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
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private"
            }
        )

    async def _flush_media_group(self, key: str) -> None:
        """Wait briefly, then forward buffered media-group as one turn."""
        try:
            await asyncio.sleep(0.6)
            if not (buf := self._media_group_buffers.pop(key, None)):
                return
            content = "\n".join(buf["contents"]) or "[empty message]"
            await self._handle_message(
                sender_id=buf["sender_id"], chat_id=buf["chat_id"],
                content=content, media=list(dict.fromkeys(buf["media"])),
                metadata=buf["metadata"],
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
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")
