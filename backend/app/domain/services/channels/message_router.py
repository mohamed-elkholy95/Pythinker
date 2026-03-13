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
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
SLASH_COMMANDS = frozenset(
    {
        "/new",
        "/stop",
        "/help",
        "/commands",
        "/status",
        "/link",
        "/pdf",
        "/reasoning",
        "/think",
        "/thinking",
        "/t",
        "/verbose",
        "/v",
        "/elevated",
        "/elev",
        "/models",
    }
)
_REASONING_VISIBILITY_LEVELS = frozenset({"off", "on", "stream"})
_THINKING_LEVELS = frozenset({"off", "low", "medium", "high"})
_TOGGLE_LEVELS = frozenset({"off", "on"})

HELP_TEXT = (
    "Available commands:\n"
    "  /new       — Start a new conversation\n"
    "  /stop      — Cancel the current request\n"
    "  /status    — Show active session info\n"
    "  /link      — Link your Telegram to your web account\n"
    "  /pdf       — Send the last assistant response as a PDF\n"
    "  /reasoning — Set reasoning visibility (off, on, stream)\n"
    "  /think     — Set thinking level (off, low, medium, high)\n"
    "  /verbose   — Toggle verbose mode (off, on)\n"
    "  /elevated  — Toggle elevated mode (off, on)\n"
    "  /help      — Show this help message"
)

TELEGRAM_LINK_REQUIRED_TEXT = (
    "Please link your Telegram account first.\n\n"
    "1) Open Pythinker web UI → Settings → Link Telegram\n"
    "2) Generate a link code\n"
    "3) Send `/link CODE` to this bot"
)

# Event types that produce outbound messages (progress is heartbeat-only, not user-visible).
_OUTBOUND_EVENT_TYPES = frozenset({"message", "report", "error", "progress", "stream"})
_TELEGRAM_FOLLOW_UP_CALLBACK_PREFIX = "telegram:followup:"
_TELEGRAM_FOLLOW_UP_LABEL = "Follow-up options:"
_RESEARCH_REPORT_REQUEST_RE = re.compile(
    r"\bresearch\b[\s\S]{0,120}\breport\b|\breport\b[\s\S]{0,120}\bresearch\b",
    re.IGNORECASE,
)
_LONG_RESEARCH_SIGNAL_RE = re.compile(
    r"\b(comprehensive|deep|detailed|benchmark|compare|comparison|pricing|citations?|references?|coupons?|offers?|deals?|discounts?|promos?|reddit)\b",
    re.IGNORECASE,
)
_GENERIC_AGENT_ACK_PREFIX_RE = re.compile(r"^\s*got it!\s*", re.IGNORECASE)
_GENERIC_AGENT_ACK_ACTION_RE = re.compile(
    r"\b(i(?:'ll|\s+will)|let me)\b.*\b(search|research|compile|create|work on|look into|analy[sz]e|gather)\b",
    re.IGNORECASE,
)


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
        telegram_pdf_caption_enabled: bool = False,
        telegram_pdf_progress_ack_enabled: bool = False,
        telegram_pdf_async_threshold_chars: int = 10000,
        telegram_pdf_include_toc: bool = True,
        telegram_pdf_toc_min_sections: int = 3,
        telegram_pdf_unicode_font: str = "DejaVuSans",
        telegram_pdf_rate_limit_per_minute: int = 5,
        telegram_pdf_delivery_enabled: bool = True,
        telegram_pdf_force_long_text: bool = False,
        telegram_require_linked_account: bool = False,
        telegram_final_delivery_only: bool = True,
        telegram_final_delivery_allow_wait_prompts: bool = True,
        telegram_streaming: str = "partial",
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
        self._telegram_final_delivery_only = telegram_final_delivery_only
        self._telegram_final_delivery_allow_wait_prompts = telegram_final_delivery_allow_wait_prompts
        self._telegram_streaming = self._normalize_telegram_streaming_mode(telegram_streaming)
        self._telegram_delivery_policy = telegram_delivery_policy or TelegramDeliveryPolicy(
            pdf_delivery_enabled=telegram_pdf_delivery_enabled,
            message_min_chars=telegram_pdf_message_min_chars,
            report_min_chars=telegram_pdf_report_min_chars,
            caption_max_chars=telegram_pdf_caption_max_chars,
            pdf_caption_enabled=telegram_pdf_caption_enabled,
            pdf_progress_ack_enabled=telegram_pdf_progress_ack_enabled,
            async_threshold_chars=telegram_pdf_async_threshold_chars,
            include_toc=telegram_pdf_include_toc,
            toc_min_sections=telegram_pdf_toc_min_sections,
            unicode_font=telegram_pdf_unicode_font,
            rate_limit_per_minute=telegram_pdf_rate_limit_per_minute,
            force_long_text_pdf=telegram_pdf_force_long_text,
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

        # 6. Telegram UX: acknowledge long-running research-report requests immediately.
        suppress_first_generic_agent_ack = False
        if self._should_send_research_report_ack(message):
            ack = self._make_reply(message, self._build_research_report_ack(message.content))
            if message.channel == ChannelType.TELEGRAM:
                ack.metadata["_telegram_keep_typing"] = True
            await self._record_outbound_activity(user_id, message, ack.content)
            yield ack
            suppress_first_generic_agent_ack = True

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

        # 7. Stream agent events and convert to outbound messages
        telegram_final_delivery_mode = self._telegram_final_delivery_enabled(message.channel)
        last_telegram_message_event: object | None = None
        last_telegram_report_event: object | None = None
        last_telegram_wait_delivery_event: object | None = None
        try:
            attachments = self._build_agent_attachments(message)
            follow_up = self._extract_follow_up(message)
            agent_message = self._build_agent_message(message)
            async for event in self._agent_service.chat(
                session_id=session_id,
                user_id=user_id,
                message=agent_message,
                attachments=attachments,
                follow_up=follow_up,
            ):
                if self._should_suppress_generic_agent_ack_event(
                    event,
                    source=message,
                    suppression_enabled=suppress_first_generic_agent_ack,
                ):
                    suppress_first_generic_agent_ack = False
                    logger.info(
                        "telegram.research_ack.suppressed_generic_agent_ack chat=%s",
                        message.chat_id,
                    )
                    continue

                event_type = getattr(event, "type", None)
                if telegram_final_delivery_mode:
                    if event_type in {"message", "report"}:
                        self._remember_latest_response(user_id, message, event, event_type=event_type)
                        if event_type == "message":
                            role = getattr(event, "role", "assistant")
                            if role == "assistant":
                                last_telegram_message_event = event
                        else:
                            last_telegram_report_event = event
                        continue

                    if event_type == "wait" and self._telegram_final_delivery_allow_wait_prompts:
                        if last_telegram_message_event is None:
                            continue
                        outbounds = await self._event_to_outbounds(
                            last_telegram_message_event, message, user_id=user_id
                        )
                        if not outbounds:
                            continue
                        last_telegram_wait_delivery_event = last_telegram_message_event
                        for outbound in outbounds:
                            await self._persist_generated_outbound_artifacts(
                                user_id=user_id,
                                session_id=session_id,
                                outbound=outbound,
                            )
                            await self._record_outbound_activity(user_id, message, outbound.content)
                            yield outbound
                        continue

                    if event_type in {"stream", "suggestion"}:
                        pending_final_event = last_telegram_report_event or last_telegram_message_event
                        if (
                            pending_final_event is not None
                            and pending_final_event is not last_telegram_wait_delivery_event
                        ):
                            pending_type = getattr(pending_final_event, "type", None)
                            pending_outbounds = await self._event_to_outbounds(
                                pending_final_event,
                                message,
                                user_id=user_id,
                            )
                            if pending_outbounds:
                                self._remember_latest_response(
                                    user_id,
                                    message,
                                    pending_final_event,
                                    event_type=pending_type,
                                )
                                for outbound in pending_outbounds:
                                    await self._persist_generated_outbound_artifacts(
                                        user_id=user_id,
                                        session_id=session_id,
                                        outbound=outbound,
                                    )
                                    await self._record_outbound_activity(user_id, message, outbound.content)
                                    yield outbound
                            last_telegram_message_event = None
                            last_telegram_report_event = None
                        if event_type == "stream" and self._telegram_streaming_enabled(message.channel):
                            pass
                        elif event_type != "suggestion":
                            continue
                    elif event_type not in {"error", "progress"}:
                        continue

                outbounds = await self._event_to_outbounds(event, message, user_id=user_id)
                if not outbounds:
                    continue
                if not telegram_final_delivery_mode:
                    event_type = getattr(event, "type", None)
                if event_type in {"message", "report", "error"}:
                    suppress_first_generic_agent_ack = False
                self._remember_latest_response(user_id, message, event, event_type=event_type)
                for outbound in outbounds:
                    await self._persist_generated_outbound_artifacts(
                        user_id=user_id,
                        session_id=session_id,
                        outbound=outbound,
                    )
                    await self._record_outbound_activity(user_id, message, outbound.content)
                    yield outbound

            if telegram_final_delivery_mode:
                final_event = last_telegram_report_event or last_telegram_message_event
                if final_event is not None and final_event is not last_telegram_wait_delivery_event:
                    final_type = getattr(final_event, "type", None)
                    final_outbounds = await self._event_to_outbounds(final_event, message, user_id=user_id)
                    if final_outbounds:
                        self._remember_latest_response(user_id, message, final_event, event_type=final_type)
                        for outbound in final_outbounds:
                            await self._persist_generated_outbound_artifacts(
                                user_id=user_id,
                                session_id=session_id,
                                outbound=outbound,
                            )
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

        Only ``message``, ``report``, ``suggestion``, ``error``, and ``progress``
        events produce outbound messages.  Progress events carry no visible
        content — they serve as heartbeats to reset the gateway's stall tracker.
        All other event types (plan, step, tool, done, etc.) are silently
        dropped.
        """
        event_type = getattr(event, "type", None)

        if event_type == "message":
            text = getattr(event, "message", "") or ""
            # Skip user echo events (role == "user")
            role = getattr(event, "role", "assistant")
            if role == "user":
                return None
            delivery_metadata = getattr(event, "delivery_metadata", None)
            has_telegram_action = isinstance(delivery_metadata, dict) and isinstance(
                delivery_metadata.get("telegram_action"),
                dict,
            )
            if not text and not has_telegram_action:
                return None
            return self._make_reply(source, text, metadata=delivery_metadata)

        if event_type == "report":
            title = getattr(event, "title", "Report")
            content = getattr(event, "content", "")
            text = f"## {title}\n\n{content}" if title else content
            if not text:
                return None
            return self._make_reply(source, text)

        if event_type == "suggestion":
            return self._suggestion_event_to_outbound(event, source)

        if event_type == "error":
            error_msg = getattr(event, "error", "Unknown error")
            return self._make_reply(source, f"Error: {error_msg}")

        if event_type == "progress":
            # Progress heartbeat — no visible content, just resets the gateway's stall tracker
            return OutboundMessage(
                channel=source.channel,
                chat_id=source.chat_id,
                content="",  # No visible content
                reply_to=source.id,
                metadata={"_progress_heartbeat": True},
            )

        if event_type == "stream":
            if not self._telegram_streaming_enabled(source.channel):
                return None
            lane = str(getattr(event, "lane", "answer") or "answer").strip().lower()
            # Suppress reasoning lane for non-Telegram channels
            if lane == "reasoning" and source.channel != ChannelType.TELEGRAM:
                return None
            is_final = bool(getattr(event, "is_final", False))
            content = getattr(event, "content", "") or ""
            metadata = self._telegram_message_id_metadata(source)
            metadata.update(
                {
                    "_progress": True,
                    "_telegram_stream": True,
                    "_telegram_stream_phase": getattr(event, "phase", "thinking"),
                    "_telegram_stream_lane": lane,
                    "_telegram_stream_final": is_final,
                }
            )
            preview_text = self._telegram_stream_preview_text(event, content=content)
            if preview_text is not None:
                metadata["_telegram_stream_preview_text"] = preview_text
            return OutboundMessage(
                channel=source.channel,
                chat_id=source.chat_id,
                content=content,
                reply_to=source.id,
                metadata=metadata,
            )

        if event_type not in _OUTBOUND_EVENT_TYPES:
            return None

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

        if command in {"/help", "/commands"}:
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

        if command == "/reasoning":
            parts = content.split(maxsplit=1)
            level = parts[1].strip().lower() if len(parts) > 1 else ""
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if not level:
                current = await self._get_reasoning_visibility(session_id, user_id)
                yield self._make_reply(
                    message,
                    f"Current reasoning level: {current}.\nValid levels: off, on, stream",
                )
                return
            if level not in _REASONING_VISIBILITY_LEVELS:
                yield self._make_reply(
                    message,
                    f'Unrecognized reasoning level "{level}". Valid levels: off, on, stream.',
                )
                return
            await self._set_reasoning_visibility(session_id, user_id, level)
            if level == "off":
                ack = "Reasoning visibility disabled."
            elif level == "stream":
                ack = "Reasoning stream enabled (Telegram only)."
            else:
                ack = "Reasoning visibility enabled."
            yield self._make_reply(message, ack)
            return

        if command in {"/think", "/thinking", "/t"}:
            parts = content.split(maxsplit=1)
            level = parts[1].strip().lower() if len(parts) > 1 else ""
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if not level:
                current = await self._get_session_option(session_id, user_id, "thinking_level")
                yield self._make_reply(
                    message,
                    f"Current thinking level: {current}.\nValid levels: off, low, medium, high",
                )
                return
            if level not in _THINKING_LEVELS:
                yield self._make_reply(
                    message,
                    f'Unrecognized thinking level "{level}". Valid levels: off, low, medium, high.',
                )
                return
            await self._set_session_option(session_id, user_id, "thinking_level", level)
            ack = f"Thinking level set to {level}." if level != "off" else "Extended thinking disabled."
            yield self._make_reply(message, ack)
            return

        if command in {"/verbose", "/v"}:
            parts = content.split(maxsplit=1)
            level = parts[1].strip().lower() if len(parts) > 1 else ""
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if not level:
                current = await self._get_session_option(session_id, user_id, "verbose_mode")
                yield self._make_reply(message, f"Verbose mode: {current}.\nValid levels: off, on")
                return
            if level not in _TOGGLE_LEVELS:
                yield self._make_reply(
                    message,
                    f'Unrecognized verbose setting "{level}". Valid levels: off, on.',
                )
                return
            await self._set_session_option(session_id, user_id, "verbose_mode", level)
            ack = "Verbose mode enabled." if level == "on" else "Verbose mode disabled."
            yield self._make_reply(message, ack)
            return

        if command in {"/elevated", "/elev"}:
            parts = content.split(maxsplit=1)
            level = parts[1].strip().lower() if len(parts) > 1 else ""
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if not level:
                current = await self._get_session_option(session_id, user_id, "elevated_mode")
                yield self._make_reply(message, f"Elevated mode: {current}.\nValid levels: off, on")
                return
            if level not in _TOGGLE_LEVELS:
                yield self._make_reply(
                    message,
                    f'Unrecognized elevated setting "{level}". Valid levels: off, on.',
                )
                return
            await self._set_session_option(session_id, user_id, "elevated_mode", level)
            ack = "Elevated mode enabled." if level == "on" else "Elevated mode disabled."
            yield self._make_reply(message, ack)
            return

        if command == "/models":
            yield self._make_reply(message, self._build_model_info())
            return

        if command == "/link":
            parts = content.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                yield self._make_reply(
                    message,
                    "Usage: /link CODE (or /bind CODE)\n\nGenerate a link code from the web UI under Settings → Link Telegram.",
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
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            for outbound in outbounds:
                if session_id:
                    await self._persist_generated_outbound_artifacts(
                        user_id=user_id,
                        session_id=session_id,
                        outbound=outbound,
                    )
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

        if command in {":bind", "/bind"}:
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
            # The override is a *desired* session key — verify it still maps
            # to a live session.  If it does, reuse it.  Otherwise, fall
            # through and create a new session (storing the mapping under
            # the normal channel key so subsequent messages find it).
            session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)
            if session_id:
                session = await self._agent_service.get_session(session_id, user_id)
                if session is not None:
                    session_activity = await self._user_channel_repo.get_session_activity(
                        user_id, message.channel, message.chat_id
                    )
                    if self._should_reuse_session(message, session, session_activity):
                        return session_id
                    logger.info(
                        "Override session %s is terminal, creating new session for %s/%s",
                        session_id,
                        message.channel,
                        message.chat_id,
                    )
                else:
                    logger.info("Override session %s no longer exists, creating new one", session_id)
            # No reusable session — fall through to create a new one.

        else:
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
                    if self._should_reuse_session(message, session, session_activity):
                        return session_id
                    logger.info(
                        "Stored session %s is terminal, creating new session for %s/%s",
                        session_id,
                        message.channel,
                        message.chat_id,
                    )
                else:
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
                timestamps.append(MessageRouter._normalize_activity_timestamp(value))
        return max(timestamps) if timestamps else None

    @staticmethod
    def _normalize_activity_timestamp(value: datetime) -> datetime:
        """Normalize activity timestamps to timezone-aware UTC datetimes."""
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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

    def _get_generated_artifact_persistor(self) -> Any | None:
        """Resolve a concrete generated-artifact persistence hook without triggering mock auto-creation."""
        service_dict = getattr(self._agent_service, "__dict__", {})
        if "persist_generated_artifact" in service_dict:
            return service_dict["persist_generated_artifact"]

        method = getattr(type(self._agent_service), "persist_generated_artifact", None)
        if method is None:
            return None
        return method.__get__(self._agent_service, type(self._agent_service))

    @staticmethod
    def _build_generated_artifact_virtual_path(session_id: str, outbound: OutboundMessage, media: Any) -> str:
        """Build a stable virtual session path for generated delivery artifacts."""
        suffix = Path(getattr(media, "filename", "") or getattr(media, "url", "")).suffix or ".bin"
        content_hash = str(outbound.metadata.get("content_hash") or "").strip()
        if not content_hash:
            content_hash = hashlib.sha256(
                f"{getattr(media, 'filename', '')}:{getattr(media, 'url', '')}".encode()
            ).hexdigest()[:12]

        mime_type = str(getattr(media, "mime_type", "") or "").strip().lower()
        stem = "telegram_pdf" if mime_type == "application/pdf" else "telegram_artifact"
        return f"/channel-deliveries/{session_id}/{stem}_{content_hash}{suffix}"

    async def _persist_generated_outbound_artifacts(
        self,
        *,
        user_id: str,
        session_id: str,
        outbound: OutboundMessage,
    ) -> None:
        """Persist locally generated outbound media into session storage."""
        if outbound.channel != ChannelType.TELEGRAM or not outbound.media:
            return

        persistor = self._get_generated_artifact_persistor()
        if persistor is None:
            return

        for media in outbound.media:
            local_path = str(getattr(media, "url", "") or "").strip()
            if not local_path:
                continue

            path = Path(local_path)
            if not path.is_file():
                continue

            try:
                await persistor(
                    session_id=session_id,
                    user_id=user_id,
                    local_path=local_path,
                    filename=getattr(media, "filename", "") or path.name,
                    content_type=getattr(media, "mime_type", None),
                    virtual_path=self._build_generated_artifact_virtual_path(session_id, outbound, media),
                    metadata={
                        "delivery_channel": str(outbound.channel),
                        "delivery_mode": str(outbound.metadata.get("delivery_mode", "")),
                        "content_hash": str(outbound.metadata.get("content_hash", "")),
                        "event_type": str(outbound.metadata.get("event_type", "")),
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to persist generated outbound artifact for session %s chat=%s",
                    session_id,
                    outbound.chat_id,
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

    @staticmethod
    def _should_send_research_report_ack(message: InboundMessage) -> bool:
        """Return True when a Telegram prompt appears to request a research report."""
        if message.channel != ChannelType.TELEGRAM:
            return False
        content = (message.content or "").strip()
        if not content or content.startswith("/"):
            return False
        if not _RESEARCH_REPORT_REQUEST_RE.search(content):
            return False
        return len(content.split()) >= 6

    @staticmethod
    def _build_research_report_ack(content: str) -> str:
        """Build immediate Telegram acknowledgement for long-running report requests."""
        compact = " ".join((content or "").split()).strip()
        estimate = MessageRouter._estimate_research_duration(compact)
        return (
            "I'm working on the research report and will send it here when it's ready. "
            f"This should take about {estimate}."
        )

    @staticmethod
    def _estimate_research_duration(compact_content: str) -> str:
        """Return a human estimate for research completion time."""
        word_count = len(compact_content.split())
        if word_count >= 20 or _LONG_RESEARCH_SIGNAL_RE.search(compact_content):
            return "10-15 minutes"
        return "5-10 minutes"

    @staticmethod
    def _should_suppress_generic_agent_ack_event(
        event: object,
        *,
        source: InboundMessage,
        suppression_enabled: bool,
    ) -> bool:
        """Suppress generic first-step agent acknowledgements after router ETA ack."""
        if not suppression_enabled or source.channel != ChannelType.TELEGRAM:
            return False
        if getattr(event, "type", None) != "message":
            return False
        if getattr(event, "role", "assistant") == "user":
            return False

        text = (getattr(event, "message", "") or "").strip()
        if not text:
            return False
        if not _GENERIC_AGENT_ACK_PREFIX_RE.match(text):
            return False
        return bool(_GENERIC_AGENT_ACK_ACTION_RE.search(text))

    def _telegram_final_delivery_enabled(self, channel: ChannelType) -> bool:
        """Return whether Telegram final-only delivery mode is active for the channel."""
        return channel == ChannelType.TELEGRAM and self._telegram_final_delivery_only

    def _telegram_streaming_enabled(self, channel: ChannelType) -> bool:
        """Return whether Telegram preview streaming is active for the channel."""
        return channel == ChannelType.TELEGRAM and self._telegram_streaming != "off"

    @staticmethod
    def _normalize_telegram_streaming_mode(value: object) -> str:
        """Normalize Telegram preview streaming mode to the OpenClaw-compatible runtime set."""
        if isinstance(value, bool):
            return "partial" if value else "off"
        normalized = str(value or "").strip().lower()
        if normalized == "progress":
            return "partial"
        if normalized in {"off", "partial", "block"}:
            return normalized
        return "partial"

    @staticmethod
    def _telegram_stream_preview_text(event: object, *, content: str = "") -> str | None:
        """Return a small generic status string for Telegram preview streaming."""
        if content.strip():
            return None
        if bool(getattr(event, "is_final", False)):
            return None

        phase = str(getattr(event, "phase", "thinking") or "thinking").strip().lower()
        if phase in {"summarizing", "synthesizing", "finalizing"}:
            return "Preparing the final response..."
        return "Working on it..."

    @staticmethod
    def _build_agent_attachments(message: InboundMessage) -> list[dict[str, Any]] | None:
        """Convert inbound channel media into the AgentService attachment contract."""
        attachments: list[dict[str, Any]] = []
        for media in message.media:
            file_path = str(getattr(media, "url", "") or "").strip()
            filename = str(getattr(media, "filename", "") or "").strip()
            content_type = str(getattr(media, "mime_type", "") or "").strip()
            size = getattr(media, "size_bytes", 0)
            metadata = getattr(media, "metadata", {}) or {}
            if not file_path and not filename:
                continue
            if not isinstance(metadata, dict):
                metadata = {}
            attachment_type = str(metadata.get("type", "") or "").strip()
            extra_metadata = {key: value for key, value in metadata.items() if key != "type"}
            attachments.append(
                {
                    "file_path": file_path or None,
                    "filename": filename or None,
                    "content_type": content_type or None,
                    "size": size if isinstance(size, int) else None,
                    "type": attachment_type or None,
                    "metadata": extra_metadata,
                }
            )
        return attachments or None

    @staticmethod
    def _build_agent_message(message: InboundMessage) -> str:
        """Add compact untrusted Telegram reply context ahead of the user message when available."""
        prefix = MessageRouter._telegram_reply_context_prefix(message)
        if not prefix:
            return message.content
        if not message.content:
            return prefix
        return f"{prefix}\n\n{message.content}"

    @staticmethod
    def _telegram_reply_context_prefix(message: InboundMessage) -> str | None:
        """Render OpenClaw-style inbound context blocks for Telegram messages.

        Includes reply, forwarded, and location context when present.
        """
        if message.channel != ChannelType.TELEGRAM:
            return None
        metadata = getattr(message, "metadata", None)
        if not isinstance(metadata, dict):
            return None

        blocks: list[str] = []

        # Conversation info — only include when reply_to_id is present
        # (a bare message_id alone is noise, not useful agent context)
        reply_to_id = metadata.get("reply_to_id")
        if reply_to_id is not None:
            conversation_info: dict[str, Any] = {}
            if metadata.get("message_id") is not None:
                conversation_info["message_id"] = metadata["message_id"]
            conversation_info["reply_to_id"] = reply_to_id
            blocks.append(
                f"Conversation info (untrusted metadata):\n```json\n{json.dumps(conversation_info, indent=2)}\n```"
            )

        # Reply context
        reply_to_body = str(metadata.get("reply_to_body", "") or "").strip()
        if reply_to_body:
            replied_message: dict[str, Any] = {}
            reply_to_sender = str(metadata.get("reply_to_sender", "") or "").strip()
            if reply_to_sender:
                replied_message["sender_label"] = reply_to_sender
            if metadata.get("reply_to_is_quote") is True:
                replied_message["is_quote"] = True
            replied_message["body"] = reply_to_body
            blocks.append(
                f"Replied message (untrusted, for context):\n```json\n{json.dumps(replied_message, indent=2)}\n```"
            )

        # Forwarded message context
        if metadata.get("is_forwarded"):
            forward_info: dict[str, Any] = {"forwarded": True}
            if metadata.get("forward_from"):
                forward_info["from"] = metadata["forward_from"]
            if metadata.get("forward_from_chat"):
                forward_info["from_channel"] = metadata["forward_from_chat"]
            if metadata.get("forward_date"):
                forward_info["date"] = metadata["forward_date"]
            blocks.append(f"Forwarded message context (untrusted):\n```json\n{json.dumps(forward_info, indent=2)}\n```")

        # Location context
        if metadata.get("location") and isinstance(metadata["location"], dict):
            blocks.append(f"Location context:\n```json\n{json.dumps(metadata['location'], indent=2)}\n```")

        return "\n\n".join(blocks) if blocks else None

    @staticmethod
    def _extract_follow_up(message: InboundMessage) -> dict[str, str] | None:
        """Return normalized follow-up metadata for callback-driven user replies."""
        metadata = getattr(message, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        raw_follow_up = metadata.get("follow_up")
        if not isinstance(raw_follow_up, dict):
            return None

        selected_suggestion = str(raw_follow_up.get("selected_suggestion", "") or "").strip()
        source = str(raw_follow_up.get("source", "") or "").strip()
        anchor_event_id = str(raw_follow_up.get("anchor_event_id", "") or "").strip()
        if not selected_suggestion or not source:
            return None

        follow_up = {
            "selected_suggestion": selected_suggestion,
            "source": source,
        }
        if anchor_event_id:
            follow_up["anchor_event_id"] = anchor_event_id
        return follow_up

    @classmethod
    def _suggestion_event_to_outbound(cls, event: object, source: InboundMessage) -> OutboundMessage | None:
        """Render follow-up suggestions as native inline buttons.

        Currently suppressed for Telegram — follow-up questions are a
        web-UI concern and add noise to the Telegram conversation.
        """
        if source.channel == ChannelType.TELEGRAM:
            return None
        # Non-Telegram channels: no rendering implemented yet.
        return None

        raw_suggestions = getattr(event, "suggestions", None)
        if not isinstance(raw_suggestions, list):
            return None
        suggestions = [str(item).strip() for item in raw_suggestions if str(item).strip()]
        if not suggestions:
            return None

        anchor_event_id = str(getattr(event, "anchor_event_id", "") or "").strip()
        inline_keyboard: list[list[dict[str, str]]] = []
        for index, suggestion in enumerate(suggestions[:3]):
            inline_keyboard.append(
                [
                    {
                        "text": suggestion,
                        "callback_data": cls._telegram_follow_up_callback_data(anchor_event_id, index),
                    }
                ]
            )
        if not inline_keyboard:
            return None

        return cls._make_reply(
            source,
            _TELEGRAM_FOLLOW_UP_LABEL,
            metadata={"reply_markup": {"inline_keyboard": inline_keyboard}},
        )

    @staticmethod
    def _telegram_follow_up_callback_data(anchor_event_id: str, index: int) -> str:
        """Build a Telegram-safe callback token for a follow-up suggestion button."""
        safe_index = max(0, int(index))
        anchor = anchor_event_id.strip()
        candidate = f"{_TELEGRAM_FOLLOW_UP_CALLBACK_PREFIX}{anchor}:{safe_index}"
        if anchor and len(candidate.encode("utf-8")) <= 64:
            return candidate
        return f"{_TELEGRAM_FOLLOW_UP_CALLBACK_PREFIX}:{safe_index}"

    # ------------------------------------------------------------------
    # Session option persistence
    # ------------------------------------------------------------------

    async def _get_reasoning_visibility(self, session_id: str | None, user_id: str | None) -> str:
        """Return the current reasoning visibility level for the session, defaulting to ``"off"``."""
        return await self._get_session_option(session_id, user_id, "reasoning_visibility")

    async def _set_reasoning_visibility(self, session_id: str | None, user_id: str | None, level: str) -> None:
        """Persist *level* (``off | on | stream``) to the session document."""
        await self._set_session_option(session_id, user_id, "reasoning_visibility", level)

    async def _get_session_option(self, session_id: str | None, user_id: str | None, field: str) -> str:
        """Return a session option field value, defaulting to ``"off"``."""
        if not session_id or not user_id:
            return "off"
        session = await self._agent_service.get_session(session_id, user_id)
        if session is None:
            return "off"
        return getattr(session, field, None) or "off"

    async def _set_session_option(self, session_id: str | None, user_id: str | None, field: str, value: str) -> None:
        """Persist a single session option field."""
        if not session_id or not user_id:
            return
        await self._agent_service.update_session_fields(session_id, user_id, {field: value})

    @staticmethod
    def _build_model_info() -> str:
        """Render model configuration info for /models command."""
        try:
            from app.core.config import get_settings

            s = get_settings()
            lines = ["Model configuration:"]
            lines.append(f"  Default: {s.model_name}")
            if s.adaptive_model_selection_enabled:
                lines.append("  Adaptive routing: enabled")
                fast = s.fast_model or s.model_name
                balanced = s.balanced_model or s.model_name
                powerful = s.powerful_model or s.model_name
                lines.append(f"  Fast tier: {fast}")
                lines.append(f"  Balanced tier: {balanced}")
                lines.append(f"  Powerful tier: {powerful}")
            else:
                lines.append("  Adaptive routing: disabled")
            lines.append(f"  Provider: {s.llm_provider}")
            return "\n".join(lines)
        except Exception:
            return "Model information unavailable."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_reply(
        source: InboundMessage,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> OutboundMessage:
        """Build an ``OutboundMessage`` addressed to the sender of *source*."""
        reply_metadata = MessageRouter._telegram_message_id_metadata(source)
        if isinstance(metadata, dict):
            reply_metadata.update(metadata)
        return OutboundMessage(
            channel=source.channel,
            chat_id=source.chat_id,
            content=content,
            reply_to=source.id,
            metadata=reply_metadata,
        )

    @staticmethod
    def _telegram_message_id_metadata(source: InboundMessage) -> dict[str, Any]:
        """Preserve Telegram delivery context for downstream reply/edit routing."""
        if source.channel != ChannelType.TELEGRAM:
            return {}
        metadata = getattr(source, "metadata", None)
        if not isinstance(metadata, dict):
            return {}
        preserved: dict[str, Any] = {}
        if metadata.get("message_id") is not None:
            preserved["message_id"] = metadata["message_id"]
        if metadata.get("message_thread_id") is not None:
            preserved["message_thread_id"] = metadata["message_thread_id"]
        if "is_group" in metadata:
            preserved["is_group"] = bool(metadata["is_group"])
        if "is_forum" in metadata:
            preserved["is_forum"] = bool(metadata["is_forum"])
        return preserved
