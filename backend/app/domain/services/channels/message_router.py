"""MessageRouter — central bridge between channel gateways and AgentService.

Receives InboundMessage from any channel adapter, resolves user identity,
manages session lifecycle, and converts agent events into OutboundMessage
objects that the channel adapter can deliver.

Slash commands (/new, /stop, /help, /status, /link) are intercepted and
handled locally without reaching the agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.core import prometheus_metrics as pm
from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage
from app.domain.services.channels.telegram_delivery_policy import TelegramDeliveryPolicy

if TYPE_CHECKING:
    from app.application.services.agent_service import AgentService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slash-command constants
# ---------------------------------------------------------------------------
SLASH_COMMANDS = frozenset({"/new", "/stop", "/help", "/status", "/link", "/pdf"})

HELP_TEXT = (
    "Available commands:\n"
    "  /new    — Start a new conversation\n"
    "  /stop   — Cancel the current request\n"
    "  /status — Show active session info\n"
    "  /link   — Link your Telegram to your web account\n"
    "  /pdf    — Send the last assistant response as a PDF\n"
    "  :bind   — Alias of /link (works in Telegram deep-link flow)\n"
    "  /help   — Show this help message"
)

TELEGRAM_LINK_REQUIRED_TEXT = (
    "Please link your Telegram account first.\n\n"
    "1) Open Pythinker web UI → Settings → Link Telegram\n"
    "2) Generate a link code\n"
    "3) Send `/link CODE` to this bot"
)

# Event types that produce user-visible outbound messages.
_OUTBOUND_EVENT_TYPES = frozenset({"message", "report", "error"})


# ---------------------------------------------------------------------------
# Repository protocol for user-channel identity mapping
# ---------------------------------------------------------------------------
@runtime_checkable
class UserChannelRepository(Protocol):
    """Repository for user-channel identity mapping.

    Implementations may be backed by MongoDB, Redis, or an in-memory dict
    (for testing).  The MessageRouter depends only on this protocol.
    """

    async def get_user_by_channel(self, channel: ChannelType, sender_id: str) -> str | None:
        """Return the Pythinker ``user_id`` linked to *sender_id* on *channel*, or ``None``."""
        ...

    async def create_channel_user(self, channel: ChannelType, sender_id: str, chat_id: str) -> str:
        """Auto-register a new Pythinker user for the given channel identity.

        Returns the newly created ``user_id``.
        """
        ...

    async def get_session_key(self, user_id: str, channel: ChannelType, chat_id: str) -> str | None:
        """Return the active session ID for (user, channel, chat), or ``None``."""
        ...

    async def set_session_key(self, user_id: str, channel: ChannelType, chat_id: str, session_id: str) -> None:
        """Store (or overwrite) the active session ID for (user, channel, chat)."""
        ...

    async def clear_session_key(self, user_id: str, channel: ChannelType, chat_id: str) -> None:
        """Remove the active session mapping for (user, channel, chat)."""
        ...

    async def link_channel_to_user(self, channel: ChannelType, sender_id: str, web_user_id: str) -> str | None:
        """Link a channel identity to a web user_id. Returns previous user_id."""
        ...

    async def migrate_sessions(self, old_user_id: str, new_user_id: str, channel: ChannelType) -> None:
        """Re-assign sessions from old to new user_id."""
        ...

    async def migrate_session_ownership(self, old_user_id: str, new_user_id: str) -> None:
        """Re-assign persisted session documents from old to new user_id."""
        ...

    async def touch_last_inbound_at(self, user_id: str, channel: ChannelType, chat_id: str) -> None:
        """Update ``last_inbound_at`` for (user, channel, chat)."""
        ...

    async def touch_last_outbound_at(self, user_id: str, channel: ChannelType, chat_id: str) -> None:
        """Update ``last_outbound_at`` for (user, channel, chat)."""
        ...

    async def get_session_activity(self, user_id: str, channel: ChannelType, chat_id: str) -> dict[str, Any] | None:
        """Return session activity metadata for (user, channel, chat)."""
        ...

    async def set_session_context_summary(
        self,
        user_id: str,
        channel: ChannelType,
        chat_id: str,
        context_turn_count: int,
        context_summary: str | None,
    ) -> None:
        """Persist context summary metadata for (user, channel, chat)."""
        ...


class LinkCodeStore(Protocol):
    """Abstraction for link-code storage (Redis-backed in production).

    Injected into MessageRouter to keep the domain layer free of
    infrastructure imports.
    """

    async def get(self, key: str) -> str | None:
        """Return the value for *key*, or ``None`` if missing / expired."""
        ...

    async def delete(self, key: str) -> Any:
        """Remove *key* from the store."""
        ...


# ---------------------------------------------------------------------------
# MessageRouter
# ---------------------------------------------------------------------------
class MessageRouter:
    """Route inbound channel messages to Pythinker's AgentService.

    Lifecycle per inbound message:
    1. Resolve user identity (auto-register unknown senders).
    2. Intercept slash commands and reply locally.
    3. Get or create an agent session.
    4. Forward the message via ``AgentService.chat()`` and stream events.
    5. Convert relevant agent events into ``OutboundMessage``.
    """

    def __init__(
        self,
        agent_service: AgentService,
        user_channel_repo: UserChannelRepository,
        link_code_store: LinkCodeStore | None = None,
        telegram_delivery_policy: TelegramDeliveryPolicy | None = None,
        *,
        telegram_reuse_completed_sessions: bool = True,
        telegram_session_idle_timeout_hours: int = 168,
        telegram_max_context_turns: int = 50,
        telegram_context_summarization_enabled: bool = True,
        telegram_context_summarization_threshold_turns: int = 50,
        telegram_pdf_message_min_chars: int = 3500,
        telegram_pdf_report_min_chars: int = 2000,
        telegram_pdf_caption_max_chars: int = 900,
        telegram_pdf_async_threshold_chars: int = 10000,
        telegram_pdf_include_toc: bool = True,
        telegram_pdf_toc_min_sections: int = 3,
        telegram_pdf_unicode_font: str = "DejaVuSans",
        telegram_pdf_rate_limit_per_minute: int = 5,
        telegram_pdf_delivery_enabled: bool = True,
        telegram_require_linked_account: bool = False,
    ) -> None:
        self._agent_service = agent_service
        self._user_channel_repo = user_channel_repo
        self._link_code_store = link_code_store
        self._telegram_require_linked_account = telegram_require_linked_account
        self._telegram_reuse_completed_sessions = telegram_reuse_completed_sessions
        self._telegram_session_idle_timeout_hours = telegram_session_idle_timeout_hours
        self._telegram_max_context_turns = telegram_max_context_turns
        self._telegram_context_summarization_enabled = telegram_context_summarization_enabled
        self._telegram_context_summarization_threshold_turns = telegram_context_summarization_threshold_turns
        self._telegram_delivery_policy = telegram_delivery_policy or TelegramDeliveryPolicy(
            pdf_delivery_enabled=telegram_pdf_delivery_enabled,
            message_min_chars=telegram_pdf_message_min_chars,
            report_min_chars=telegram_pdf_report_min_chars,
            caption_max_chars=telegram_pdf_caption_max_chars,
            async_threshold_chars=telegram_pdf_async_threshold_chars,
            include_toc=telegram_pdf_include_toc,
            toc_min_sections=telegram_pdf_toc_min_sections,
            unicode_font=telegram_pdf_unicode_font,
            rate_limit_per_minute=telegram_pdf_rate_limit_per_minute,
        )
        self._latest_responses: dict[tuple[str, str, str], dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route_inbound(self, message: InboundMessage) -> AsyncGenerator[OutboundMessage, None]:
        """Process an inbound message and yield outbound replies.

        Yields zero or more ``OutboundMessage`` objects.  Internal agent events
        (plan, step, tool, etc.) are silently discarded.
        """
        # 1. Normalize command aliases before identity policy checks.
        content = self._normalize_command_alias(message.content.strip())
        command = content.split()[0].lower() if content else ""

        # 2. Resolve user identity.
        # Telegram strict mode can require a pre-linked account and disable
        # auto-registration for unlinked senders.
        user_id: str | None
        if self._telegram_require_linked_account and message.channel == ChannelType.TELEGRAM:
            user_id = await self._user_channel_repo.get_user_by_channel(message.channel, message.sender_id)
            if user_id is None:
                if command == "/link":
                    async for reply in self._handle_slash_command(content, message, user_id=None):
                        yield reply
                    return
                yield self._make_reply(message, TELEGRAM_LINK_REQUIRED_TEXT)
                return
        else:
            user_id = await self._resolve_user(message)

        # 3. Track inbound activity for resolved users.
        if user_id is not None:
            await self._record_inbound_activity(user_id, message)

        # 4. Handle slash commands locally
        if command in SLASH_COMMANDS:
            async for reply in self._handle_slash_command(content, message, user_id):
                if user_id is not None:
                    await self._record_outbound_activity(user_id, message, reply.content)
                yield reply
            return

        # 5. Get or create session
        if user_id is None:
            yield self._make_reply(message, TELEGRAM_LINK_REQUIRED_TEXT)
            return

        try:
            session_id = await self._get_or_create_session(message, user_id)
        except Exception:
            logger.exception(
                "Failed to get or create session for user %s on %s/%s",
                user_id,
                message.channel,
                message.chat_id,
            )
            yield self._make_reply(
                message,
                "Sorry, I could not start a session. Please try again later.",
            )
            return

        # 6. Stream agent events and convert to outbound messages
        try:
            async for event in self._agent_service.chat(
                session_id=session_id,
                user_id=user_id,
                message=message.content,
            ):
                outbounds = await self._event_to_outbounds(event, message, user_id=user_id)
                if not outbounds:
                    continue
                event_type = getattr(event, "type", None)
                self._remember_latest_response(user_id, message, event, event_type=event_type)
                for outbound in outbounds:
                    await self._record_outbound_activity(user_id, message, outbound.content)
                    yield outbound
        except Exception:
            logger.exception("Agent error for session %s (user %s)", session_id, user_id)
            error_reply = self._make_reply(
                message,
                "An error occurred while processing your request. Please try again.",
            )
            await self._record_outbound_activity(user_id, message, error_reply.content)
            yield error_reply

    # ------------------------------------------------------------------
    # Event conversion
    # ------------------------------------------------------------------

    async def _event_to_outbounds(
        self,
        event: object,
        source: InboundMessage,
        *,
        user_id: str,
    ) -> list[OutboundMessage]:
        """Convert one event into zero or more outbounds with channel-specific policies."""
        event_type = getattr(event, "type", None)
        if source.channel == ChannelType.TELEGRAM and event_type in {"message", "report"}:
            return await self._telegram_delivery_policy.build_for_event(event, source, user_id=user_id)

        outbound = self._event_to_outbound(event, source)
        if outbound is None:
            return []
        return [outbound]

    def _event_to_outbound(self, event: object, source: InboundMessage) -> OutboundMessage | None:
        """Convert an agent event to an OutboundMessage, or ``None`` for internal events.

        Only ``message``, ``report``, and ``error`` events produce outbound
        messages.  All other event types (plan, step, tool, done, progress,
        etc.) are silently dropped — they are internal to the agent pipeline.
        """
        event_type = getattr(event, "type", None)
        if event_type not in _OUTBOUND_EVENT_TYPES:
            return None

        if event_type == "message":
            text = getattr(event, "message", "") or ""
            # Skip user echo events (role == "user")
            role = getattr(event, "role", "assistant")
            if role == "user":
                return None
            if not text:
                return None
            return self._make_reply(source, text)

        if event_type == "report":
            title = getattr(event, "title", "Report")
            content = getattr(event, "content", "")
            text = f"## {title}\n\n{content}" if title else content
            if not text:
                return None
            return self._make_reply(source, text)

        if event_type == "error":
            error_msg = getattr(event, "error", "Unknown error")
            return self._make_reply(source, f"Error: {error_msg}")

        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    async def _handle_slash_command(
        self,
        content: str,
        message: InboundMessage,
        user_id: str | None,
    ) -> AsyncGenerator[OutboundMessage, None]:
        """Intercept and respond to slash commands."""
        command = content.split()[0].lower()

        if command == "/help":
            yield self._make_reply(message, HELP_TEXT)
            return

        if user_id is None and command != "/link":
            yield self._make_reply(message, TELEGRAM_LINK_REQUIRED_TEXT)
            return

        if command == "/new":
            await self._user_channel_repo.clear_session_key(user_id, message.channel, message.chat_id)
            yield self._make_reply(message, "Session cleared. Send a message to start a new conversation.")
            return

        if command == "/status":
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if session_id:
                session = await self._agent_service.get_session(session_id, user_id)
                if session:
                    yield self._make_reply(
                        message,
                        f"Active session: {session.id}\n"
                        f"Status: {session.status.value}\n"
                        f"Created: {session.created_at.isoformat()}",
                    )
                    return
            yield self._make_reply(message, "No active session.")
            return

        if command == "/stop":
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if session_id:
                try:
                    await self._agent_service.stop_session(session_id, user_id)
                    yield self._make_reply(message, "Session stopped.")
                except Exception:
                    logger.exception(
                        "Failed to stop session %s for user %s",
                        session_id,
                        user_id,
                    )
                    yield self._make_reply(message, "Failed to stop the session.")
            else:
                yield self._make_reply(message, "No active session to stop.")
            return

        if command == "/link":
            parts = content.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                yield self._make_reply(
                    message,
                    "Usage: /link CODE (or :bind CODE)\n\nGenerate a link code from the web UI under Settings → Link Telegram.",
                )
                return

            link_code = parts[1].strip().upper()
            redis_key = f"channel_link:{link_code}"
            code_prefix = link_code[:4]
            code_sha256_12 = hashlib.sha256(link_code.encode("utf-8")).hexdigest()[:12]

            if self._link_code_store is None:
                pm.record_channel_link_redeem_failed("store_unavailable")
                yield self._make_reply(
                    message,
                    "Account linking is not configured. Please contact the administrator.",
                )
                return

            try:
                raw_value = await self._link_code_store.get(redis_key)

                if raw_value is None:
                    pm.record_channel_link_redeem_failed("not_found_or_expired")
                    logger.info(
                        "Channel link redeem failed: reason=not_found_or_expired channel=%s sender=%s code_prefix=%s code_sha256_12=%s",
                        message.channel.value,
                        message.sender_id,
                        code_prefix,
                        code_sha256_12,
                    )
                    yield self._make_reply(
                        message,
                        "Invalid or expired link code. Please generate a new one from the web UI.",
                    )
                    return

                payload: dict[str, str] = json.loads(raw_value)
                web_user_id: str = payload["user_id"]
                expected_channel = payload.get("channel")
                if expected_channel and expected_channel != message.channel.value:
                    pm.record_channel_link_redeem_failed("channel_mismatch")
                    logger.info(
                        "Channel link redeem failed: reason=channel_mismatch expected_channel=%s actual_channel=%s sender=%s code_prefix=%s code_sha256_12=%s",
                        expected_channel,
                        message.channel.value,
                        message.sender_id,
                        code_prefix,
                        code_sha256_12,
                    )
                    yield self._make_reply(
                        message,
                        "This link code was generated for a different channel. Please create a new Telegram code.",
                    )
                    return

                old_user_id = await self._user_channel_repo.link_channel_to_user(
                    message.channel,
                    message.sender_id,
                    web_user_id,
                )

                if old_user_id is not None and old_user_id != web_user_id:
                    await self._user_channel_repo.migrate_sessions(
                        old_user_id,
                        web_user_id,
                        message.channel,
                    )
                    await self._user_channel_repo.migrate_session_ownership(
                        old_user_id,
                        web_user_id,
                    )

                # Single-use: delete the code immediately after successful link.
                await self._link_code_store.delete(redis_key)
                pm.record_channel_link_redeemed(message.channel.value)
                logger.info(
                    "Channel link redeemed: channel=%s sender=%s linked_user_id=%s code_prefix=%s code_sha256_12=%s",
                    message.channel.value,
                    message.sender_id,
                    web_user_id,
                    code_prefix,
                    code_sha256_12,
                )

                yield self._make_reply(
                    message,
                    "Account linked! Your Telegram sessions will now appear in the web UI.",
                )
            except Exception:
                pm.record_channel_link_redeem_failed("internal_error")
                logger.exception("Failed to process /link command for sender %s", message.sender_id)
                yield self._make_reply(
                    message,
                    "An error occurred while linking your account. Please try again later.",
                )
            return

        if command == "/pdf":
            if message.channel != ChannelType.TELEGRAM:
                yield self._make_reply(message, "PDF delivery is currently available only in Telegram.")
                return

            response = self._latest_responses.get(self._response_key(user_id, message.channel, message.chat_id))
            if response is None:
                yield self._make_reply(message, "No recent assistant response is available for PDF export.")
                return

            outbounds = await self._telegram_delivery_policy.build_for_content(
                event_type=response["type"],
                title=response["title"],
                content=response["content"],
                source=message,
                user_id=user_id,
                sources=response.get("sources"),
                force_pdf=True,
            )
            for outbound in outbounds:
                yield outbound
            return

        # Unknown command — should not happen due to SLASH_COMMANDS guard.
        yield self._make_reply(  # pragma: no cover
            message, f"Unknown command: {command}. Type /help for available commands."
        )

    @staticmethod
    def _normalize_command_alias(content: str) -> str:
        """Normalize Telegram bind/deep-link aliases to ``/link``."""
        if not content:
            return content

        parts = content.split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""

        if command == ":bind":
            return f"/link {argument}".strip()

        # Telegram deep-link starts as: /start bind_<CODE>
        if command == "/start" and argument.lower().startswith("bind_"):
            bind_code = argument[5:].strip()
            return f"/link {bind_code}".strip() if bind_code else "/link"

        return content

    # ------------------------------------------------------------------
    # User resolution
    # ------------------------------------------------------------------

    async def _resolve_user(self, message: InboundMessage) -> str:
        """Resolve or auto-register the sender as a Pythinker user."""
        user_id = await self._user_channel_repo.get_user_by_channel(message.channel, message.sender_id)
        if user_id is not None:
            return user_id

        # Auto-register unknown sender
        logger.info(
            "Auto-registering new user for %s sender_id=%s chat_id=%s",
            message.channel,
            message.sender_id,
            message.chat_id,
        )
        return await self._user_channel_repo.create_channel_user(message.channel, message.sender_id, message.chat_id)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_or_create_session(self, message: InboundMessage, user_id: str) -> str:
        """Return an existing session ID or create a new one.

        Uses ``session_key_override`` from the inbound message if provided,
        otherwise falls back to the channel-level session mapping.
        Reuses existing sessions only while they are non-terminal.
        """
        if message.session_key_override:
            return message.session_key_override

        session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)

        # If we have a stored session, verify it still exists and is reusable.
        if session_id:
            session = await self._agent_service.get_session(session_id, user_id)
            if session is not None:
                session_activity = await self._user_channel_repo.get_session_activity(
                    user_id,
                    message.channel,
                    message.chat_id,
                )
                if not self._should_reuse_session(message, session, session_activity):
                    logger.info(
                        "Stored session %s is terminal, creating a new session for %s/%s",
                        session_id,
                        message.channel,
                        message.chat_id,
                    )
                else:
                    return session_id
            else:
                # Session was deleted — fall through and create a new one
                logger.info("Stored session %s no longer exists, creating new one", session_id)

        # Create a new session
        session = await self._agent_service.create_session(
            user_id=user_id,
            source=message.channel.value,
            initial_message=message.content,
            require_fresh_sandbox=True,
        )
        await self._user_channel_repo.set_session_key(user_id, message.channel, message.chat_id, session.id)
        logger.info(
            "Created new session %s for user %s on %s/%s",
            session.id,
            user_id,
            message.channel,
            message.chat_id,
        )
        return session.id

    def _should_reuse_session(
        self,
        message: InboundMessage,
        session: object,
        session_activity: dict[str, Any] | None,
    ) -> bool:
        """Return True when an existing session should be reused for this message."""
        status = self._normalized_status(session)
        if status in {"failed", "cancelled"}:
            pm.telegram_session_rotated_total.inc({"reason": status})
            return False

        if message.channel != ChannelType.TELEGRAM:
            return status not in {"completed", "failed", "cancelled"}

        # Telegram continuity policy: completed sessions are reused by default.
        if status == "completed":
            if not self._telegram_reuse_completed_sessions:
                pm.telegram_session_rotated_total.inc({"reason": "completed_reuse_disabled"})
                return False
            if self._is_idle_session(session_activity):
                pm.telegram_session_rotated_total.inc({"reason": "idle_timeout"})
                return False
            pm.telegram_session_reused_total.inc()
            return True

        pm.telegram_session_reused_total.inc()
        return True

    def _is_idle_session(self, session_activity: dict[str, Any] | None) -> bool:
        """Return True when activity exceeds configured idle timeout."""
        if self._telegram_session_idle_timeout_hours <= 0:
            return False
        if not session_activity:
            return False

        last_seen = self._latest_activity_timestamp(session_activity)
        if last_seen is None:
            return False

        timeout = timedelta(hours=self._telegram_session_idle_timeout_hours)
        return datetime.now(UTC) - last_seen > timeout

    @staticmethod
    def _latest_activity_timestamp(session_activity: dict[str, Any]) -> datetime | None:
        timestamps: list[datetime] = []
        for key in ("last_inbound_at", "last_outbound_at", "updated_at"):
            value = session_activity.get(key)
            if isinstance(value, datetime):
                timestamps.append(value)
        return max(timestamps) if timestamps else None

    @staticmethod
    def _normalized_status(session: object) -> str:
        """Normalize session status to a lowercase string."""
        status = getattr(session, "status", None)
        raw_value = getattr(status, "value", status)
        return str(raw_value).strip().lower() if raw_value is not None else ""

    async def _record_inbound_activity(self, user_id: str, message: InboundMessage) -> None:
        """Best-effort session activity tracking for inbound messages."""
        try:
            await self._user_channel_repo.touch_last_inbound_at(user_id, message.channel, message.chat_id)
        except Exception:
            logger.exception(
                "Failed to update last_inbound_at for user=%s channel=%s chat=%s",
                user_id,
                message.channel,
                message.chat_id,
            )

    async def _record_outbound_activity(self, user_id: str, source: InboundMessage, content: str) -> None:
        """Best-effort session activity tracking for outbound replies."""
        try:
            await self._user_channel_repo.touch_last_outbound_at(user_id, source.channel, source.chat_id)
            if source.channel == ChannelType.TELEGRAM:
                await self._update_context_summary_if_needed(user_id, source, content)
        except Exception:
            logger.exception(
                "Failed to update last_outbound_at for user=%s channel=%s chat=%s",
                user_id,
                source.channel,
                source.chat_id,
            )

    async def _update_context_summary_if_needed(self, user_id: str, source: InboundMessage, content: str) -> None:
        """Persist rolling summary metadata for long Telegram conversations."""
        activity = await self._user_channel_repo.get_session_activity(user_id, source.channel, source.chat_id)
        current_turns = int(activity.get("context_turn_count", 0)) if activity else 0
        context_turn_count = min(current_turns + 1, max(self._telegram_max_context_turns, 1))

        summary: str | None = activity.get("context_summary") if activity else None
        if (
            self._telegram_context_summarization_enabled
            and context_turn_count >= self._telegram_context_summarization_threshold_turns
        ):
            snippet = (content or "").strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = f"{snippet[:197].rstrip()}..."
            summary = f"Conversation has {context_turn_count} turns. Latest assistant summary: {snippet}"

        await self._user_channel_repo.set_session_context_summary(
            user_id=user_id,
            channel=source.channel,
            chat_id=source.chat_id,
            context_turn_count=context_turn_count,
            context_summary=summary,
        )

    def _remember_latest_response(
        self,
        user_id: str,
        message: InboundMessage,
        event: object,
        *,
        event_type: str | None,
    ) -> None:
        """Cache the latest assistant response for slash-command follow-ups like /pdf."""
        if event_type not in {"message", "report"}:
            return

        if event_type == "message":
            role = getattr(event, "role", "assistant")
            if role == "user":
                return
            payload = {
                "type": "message",
                "title": "Response",
                "content": (getattr(event, "message", "") or "").strip(),
                "sources": None,
            }
        else:
            payload = {
                "type": "report",
                "title": (getattr(event, "title", "Report") or "Report").strip(),
                "content": (getattr(event, "content", "") or "").strip(),
                "sources": getattr(event, "sources", None),
            }
        if not payload["content"]:
            return
        self._latest_responses[self._response_key(user_id, message.channel, message.chat_id)] = payload

    @staticmethod
    def _response_key(user_id: str, channel: ChannelType, chat_id: str) -> tuple[str, str, str]:
        return user_id, str(channel), chat_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_reply(source: InboundMessage, content: str) -> OutboundMessage:
        """Build an ``OutboundMessage`` addressed to the sender of *source*."""
        return OutboundMessage(
            channel=source.channel,
            chat_id=source.chat_id,
            content=content,
            reply_to=source.id,
        )
