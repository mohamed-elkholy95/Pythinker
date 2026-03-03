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
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pymongo import ReturnDocument

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
        self._session_docs: Any = db["sessions"]

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
        channel_value = str(channel)
        doc = await self._links.find_one(
            {"channel": channel_value, "sender_id": sender_id},
            {"user_id": 1},
        )
        if doc is None and channel_value == ChannelType.TELEGRAM.value:
            sender_prefix = self._telegram_sender_prefix(sender_id)
            if sender_prefix and sender_prefix != sender_id:
                doc = await self._links.find_one(
                    {
                        "channel": channel_value,
                        "$or": [
                            {"sender_id": sender_prefix},
                            {"sender_id": {"$regex": f"^{re.escape(sender_prefix)}\\|"}},
                        ],
                    },
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

    async def link_channel_to_user(
        self,
        channel: ChannelType,
        sender_id: str,
        web_user_id: str,
    ) -> str | None:
        """Link a channel identity to an existing Pythinker web account.

        Performs an atomic upsert on the ``user_channel_links`` collection.
        If a document for *(channel, sender_id)* already exists the
        ``user_id`` field is overwritten with *web_user_id*; otherwise a
        new document is created.

        Parameters
        ----------
        channel:
            The external channel type (e.g. ``ChannelType.TELEGRAM``).
        sender_id:
            The channel-specific user identifier (e.g. a Telegram user ID).
        web_user_id:
            The Pythinker web account ``user_id`` to link to.

        Returns
        -------
        str | None
            The *previous* ``user_id`` stored in the document before the
            update (useful for session migration), or ``None`` if this was
            a fresh insert.
        """
        now = datetime.now(UTC)
        channel_value = str(channel)
        sender_prefix = self._telegram_sender_prefix(sender_id) if channel_value == ChannelType.TELEGRAM.value else ""

        filter_doc: dict[str, Any]
        set_on_insert_sender_id = sender_id
        if sender_prefix and sender_prefix != sender_id:
            filter_doc = {
                "channel": channel_value,
                "$or": [
                    {"sender_id": sender_id},
                    {"sender_id": sender_prefix},
                    {"sender_id": {"$regex": f"^{re.escape(sender_prefix)}\\|"}},
                ],
            }
            set_on_insert_sender_id = sender_prefix
        else:
            filter_doc = {
                "channel": channel_value,
                "sender_id": sender_id,
            }

        old_doc = await self._links.find_one_and_update(
            filter_doc,
            {
                "$set": {
                    "user_id": web_user_id,
                    "linked_at": now,
                },
                "$setOnInsert": {
                    "channel": channel_value,
                    "sender_id": set_on_insert_sender_id,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.BEFORE,
        )
        old_user_id: str | None = old_doc.get("user_id") if old_doc is not None else None
        logger.info(
            "Linked channel %s/%s to web user %s (previous=%s)",
            channel,
            sender_id,
            web_user_id,
            old_user_id,
        )
        return old_user_id

    async def get_linked_channels(self, user_id: str) -> list[dict[str, Any]]:
        """Return all channel identities linked to *user_id*.

        Parameters
        ----------
        user_id:
            The Pythinker web account ``user_id``.

        Returns
        -------
        list[dict[str, Any]]
            Each element contains ``channel``, ``sender_id``, and
            ``linked_at`` fields.  Limited to 50 results.
        """
        cursor = self._links.find(
            {"user_id": user_id, "linked_at": {"$exists": True}},
            {"_id": 0, "channel": 1, "sender_id": 1, "linked_at": 1},
        )
        return await cursor.to_list(length=50)

    async def unlink_channel(self, user_id: str, channel: ChannelType) -> None:
        """Remove the link between *user_id* and a channel identity.

        Parameters
        ----------
        user_id:
            The Pythinker web account ``user_id``.
        channel:
            The channel type to unlink.
        """
        result = await self._links.delete_one({"user_id": user_id, "channel": str(channel)})
        if result.deleted_count:
            logger.info("Unlinked channel %s from user %s", channel, user_id)
        else:
            logger.warning(
                "unlink_channel called but no link found for user=%s channel=%s",
                user_id,
                channel,
            )

    async def migrate_sessions(
        self,
        old_user_id: str,
        new_user_id: str,
        channel: ChannelType,
    ) -> None:
        """Re-assign all channel sessions from *old_user_id* to *new_user_id*.

        Called after ``link_channel_to_user`` when an existing channel-only
        account is merged into a web account.  Updates the ``channel_sessions``
        collection so that in-flight sessions continue under the new identity.

        Parameters
        ----------
        old_user_id:
            The previous ``user_id`` (e.g. ``channel-<hex>``).
        new_user_id:
            The Pythinker web account ``user_id`` to migrate sessions to.
        channel:
            The channel type whose sessions should be migrated.
        """
        await self._sessions.update_many(
            {"user_id": old_user_id, "channel": str(channel)},
            {
                "$set": {
                    "user_id": new_user_id,
                    "updated_at": datetime.now(UTC),
                },
            },
        )
        logger.info(
            "Migrated sessions for channel %s from %s to %s",
            channel,
            old_user_id,
            new_user_id,
        )

    async def migrate_session_ownership(self, old_user_id: str, new_user_id: str) -> None:
        """Re-assign persisted session documents from *old_user_id* to *new_user_id*.

        This is required when linking a channel-only user to a web account so
        historical sessions appear in the web UI (which lists by ``user_id``).
        """
        now = datetime.now(UTC)
        await self._session_docs.update_many(
            {"user_id": old_user_id},
            {
                "$set": {
                    "user_id": new_user_id,
                    "updated_at": now,
                },
            },
        )
        logger.info(
            "Migrated session ownership from %s to %s",
            old_user_id,
            new_user_id,
        )

    @staticmethod
    def _telegram_sender_prefix(sender_id: str) -> str:
        """Return stable Telegram numeric ID from ``<id>|<username>`` sender IDs."""
        return sender_id.split("|", 1)[0].strip()

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
