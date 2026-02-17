"""MongoDB implementation of MemoriesCollectionProtocol.

Provides direct access to memory documents in MongoDB for
reconciliation and sync state management operations.
"""

import logging
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.domain.repositories.memories_collection import MemoriesCollectionProtocol
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class MongoMemoriesCollection(MemoriesCollectionProtocol):
    """MongoDB-backed implementation for direct memory document operations.

    Used by the reconciliation job to detect and repair sync
    inconsistencies between MongoDB and the vector store.
    """

    def __init__(self) -> None:
        self._mongodb = get_mongodb()
        self._collection: AsyncIOMotorCollection | None = None

    async def _ensure_collection(self) -> AsyncIOMotorCollection:
        """Lazily initialize the MongoDB collection.

        Services may be constructed before MongoDB is fully initialized.
        Resolve the collection handle at first use.
        """
        if self._collection is not None:
            return self._collection

        try:
            _ = self._mongodb.client
        except RuntimeError:
            await self._mongodb.initialize()

        self._collection = self._mongodb.database.memories
        return self._collection

    async def find_failed_memories(
        self,
        cutoff: datetime,
        max_sync_attempts: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Find failed memory documents eligible for sync retry."""
        collection = await self._ensure_collection()
        cursor = collection.find(
            {
                "sync_state": "failed",
                "last_sync_attempt": {"$lt": cutoff},
                "sync_attempts": {"$lt": max_sync_attempts},
            }
        ).limit(limit)

        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def find_synced_memories_needing_verification(
        self,
        since: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Find recently synced memories that should be verified in vector store."""
        collection = await self._ensure_collection()
        cursor = collection.find(
            {
                "sync_state": "synced",
                "updated_at": {"$gte": since},
                "embedding": {"$exists": True, "$ne": None},
            }
        ).limit(limit)

        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def update_sync_state(
        self,
        memory_id: str,
        sync_state: str,
        sync_attempts_increment: int = 0,
        last_sync_attempt: datetime | None = None,
    ) -> bool:
        """Update sync state fields on a memory document."""
        from bson import ObjectId

        collection = await self._ensure_collection()

        update_doc: dict[str, Any] = {"$set": {"sync_state": sync_state}}

        if last_sync_attempt is not None:
            update_doc["$set"]["last_sync_attempt"] = last_sync_attempt

        if sync_attempts_increment > 0:
            update_doc["$inc"] = {"sync_attempts": sync_attempts_increment}

        result = await collection.update_one(
            {"_id": ObjectId(memory_id)},
            update_doc,
        )
        return result.modified_count > 0

    async def aggregate_sync_states(self) -> dict[str, int]:
        """Aggregate memory documents by sync state."""
        collection = await self._ensure_collection()
        pipeline = [
            {"$group": {"_id": "$sync_state", "count": {"$sum": 1}}},
        ]

        sync_states: dict[str, int] = {}
        try:
            async for doc in collection.aggregate(pipeline):
                state = doc["_id"] or "unknown"
                sync_states[state] = doc["count"]
        except Exception as exc:
            logger.warning("Failed to aggregate memory sync states: %s", exc)

        return sync_states
