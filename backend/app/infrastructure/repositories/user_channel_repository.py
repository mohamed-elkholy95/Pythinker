"""MongoDB-backed repository for user-channel identity mappings.

Stores the link between external channel identities (Telegram user ID,
Discord user ID, etc.) and internal Pythinker user IDs, as well as
per-user/channel/chat active session state.

Collections used:
    ``user_channel_links`` — one document per (channel, sender_id) pair
    ``channel_sessions``   — one document per (user_id, channel, chat_id) triple

Implements the ``UserChannelRepository`` protocol defined in
``app.domain.services.channels.message_router``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.domain.models.channel import ChannelType

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class MongoUserChannelRepository:
    """MongoDB implementation of ``UserChannelRepository``.

    Parameters
    ----------
    db:
        A Motor ``AsyncIOMotorDatabase`` instance.  The repository creates
        / manages two collections: ``user_channel_links`` and
        ``channel_sessions``.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._links: Any = db["user_channel_links"]
        self._sessions: Any = db["channel_sessions"]

    # ------------------------------------------------------------------
    # Ensure indexes (call once at startup)
    # ------------------------------------------------------------------

    async def ensure_indexes(self) -> None:
        """Create compound indexes for efficient lookups.

        Safe to call multiple times — ``create_index`` is idempotent.
        """
        await self._links.create_index(
            [("channel", 1), ("sender_id", 1)],
            unique=True,
            name="ux_channel_sender",
        )
        await self._sessions.create_index(
            [("user_id", 1), ("channel", 1), ("chat_id", 1)],
            unique=True,
            name="ux_user_channel_chat",
        )
        logger.info("UserChannelRepository indexes ensured")

    # ------------------------------------------------------------------
    # User-channel link operations
    # ------------------------------------------------------------------

    async def get_user_by_channel(self, channel: ChannelType, sender_id: str) -> str | None:
        """Return the Pythinker ``user_id`` linked to *sender_id* on *channel*.

        Returns ``None`` if no link exists.
        """
        doc = await self._links.find_one(
            {"channel": str(channel), "sender_id": sender_id},
            {"user_id": 1},
        )
        if doc is None:
            return None
        return doc["user_id"]

    async def create_channel_user(self, channel: ChannelType, sender_id: str, chat_id: str) -> str:
        """Auto-register a new Pythinker user for the given channel identity.

        Generates a ``user_id`` of the form ``channel-<12-hex-chars>`` and
        inserts a link document.  Returns the newly created ``user_id``.
        """
        user_id = f"channel-{uuid.uuid4().hex[:12]}"
        await self._links.insert_one(
            {
                "user_id": user_id,
                "channel": str(channel),
                "sender_id": sender_id,
                "chat_id": chat_id,
                "created_at": datetime.now(UTC),
            }
        )
        logger.info(
            "Created channel user %s for %s/%s",
            user_id,
            channel,
            sender_id,
        )
        return user_id

    # ------------------------------------------------------------------
    # Session key operations
    # ------------------------------------------------------------------

    async def get_session_key(self, user_id: str, channel: ChannelType, chat_id: str) -> str | None:
        """Return the active session ID for (user, channel, chat), or ``None``."""
        doc = await self._sessions.find_one(
            {
                "user_id": user_id,
                "channel": str(channel),
                "chat_id": chat_id,
            },
            {"session_id": 1},
        )
        if doc is None:
            return None
        return doc.get("session_id")

    async def set_session_key(
        self,
        user_id: str,
        channel: ChannelType,
        chat_id: str,
        session_id: str,
    ) -> None:
        """Store (or overwrite) the active session ID for (user, channel, chat)."""
        await self._sessions.update_one(
            {
                "user_id": user_id,
                "channel": str(channel),
                "chat_id": chat_id,
            },
            {
                "$set": {
                    "session_id": session_id,
                    "updated_at": datetime.now(UTC),
                },
                "$setOnInsert": {
                    "user_id": user_id,
                    "channel": str(channel),
                    "chat_id": chat_id,
                    "created_at": datetime.now(UTC),
                },
            },
            upsert=True,
        )
        logger.debug(
            "Set session key for user=%s channel=%s chat=%s -> %s",
            user_id,
            channel,
            chat_id,
            session_id,
        )

    async def clear_session_key(self, user_id: str, channel: ChannelType, chat_id: str) -> None:
        """Remove the active session mapping for (user, channel, chat).

        Sets ``session_id`` to ``None`` rather than deleting the document,
        preserving the mapping metadata for audit purposes.
        """
        await self._sessions.update_one(
            {
                "user_id": user_id,
                "channel": str(channel),
                "chat_id": chat_id,
            },
            {
                "$set": {
                    "session_id": None,
                    "updated_at": datetime.now(UTC),
                },
            },
        )
        logger.debug(
            "Cleared session key for user=%s channel=%s chat=%s",
            user_id,
            channel,
            chat_id,
        )
