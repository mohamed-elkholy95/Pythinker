"""MessageRouter — central bridge between channel gateways and AgentService.

Receives InboundMessage from any channel adapter, resolves user identity,
manages session lifecycle, and converts agent events into OutboundMessage
objects that the channel adapter can deliver.

Slash commands (/new, /stop, /help, /status) are intercepted and handled
locally without reaching the agent.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from app.application.services.agent_service import AgentService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slash-command constants
# ---------------------------------------------------------------------------
SLASH_COMMANDS = frozenset({"/new", "/stop", "/help", "/status"})

HELP_TEXT = (
    "Available commands:\n"
    "  /new    — Start a new conversation\n"
    "  /stop   — Cancel the current request\n"
    "  /status — Show active session info\n"
    "  /help   — Show this help message"
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
    ) -> None:
        self._agent_service = agent_service
        self._user_channel_repo = user_channel_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def route_inbound(self, message: InboundMessage) -> AsyncGenerator[OutboundMessage, None]:
        """Process an inbound message and yield outbound replies.

        Yields zero or more ``OutboundMessage`` objects.  Internal agent events
        (plan, step, tool, etc.) are silently discarded.
        """
        # 1. Resolve user (auto-register if unknown)
        user_id = await self._resolve_user(message)

        # 2. Handle slash commands locally
        content = message.content.strip()
        if content.split()[0].lower() in SLASH_COMMANDS if content else False:
            async for reply in self._handle_slash_command(content, message, user_id):
                yield reply
            return

        # 3. Get or create session
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

        # 4. Stream agent events and convert to outbound messages
        try:
            async for event in self._agent_service.chat(
                session_id=session_id,
                user_id=user_id,
                message=message.content,
            ):
                outbound = self._event_to_outbound(event, message)
                if outbound is not None:
                    yield outbound
        except Exception:
            logger.exception("Agent error for session %s (user %s)", session_id, user_id)
            yield self._make_reply(
                message,
                "An error occurred while processing your request. Please try again.",
            )

    # ------------------------------------------------------------------
    # Event conversion
    # ------------------------------------------------------------------

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
        user_id: str,
    ) -> AsyncGenerator[OutboundMessage, None]:
        """Intercept and respond to slash commands."""
        command = content.split()[0].lower()

        if command == "/help":
            yield self._make_reply(message, HELP_TEXT)
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

        # Unknown command — should not happen due to SLASH_COMMANDS guard.
        yield self._make_reply(  # pragma: no cover
            message, f"Unknown command: {command}. Type /help for available commands."
        )

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
        """
        if message.session_key_override:
            return message.session_key_override

        session_id = await self._user_channel_repo.get_session_key(user_id, message.channel, message.chat_id)

        # If we have a stored session, verify it still exists
        if session_id:
            session = await self._agent_service.get_session(session_id, user_id)
            if session is not None:
                return session_id
            # Session was deleted — fall through and create a new one
            logger.info("Stored session %s no longer exists, creating new one", session_id)

        # Create a new session
        session = await self._agent_service.create_session(
            user_id=user_id,
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
