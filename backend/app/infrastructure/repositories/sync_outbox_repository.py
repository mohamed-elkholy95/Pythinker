"""MongoDB repository for sync outbox pattern."""

import logging
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.domain.models.sync_outbox import (
    DeadLetterEntry,
    OutboxCreate,
    OutboxEntry,
    OutboxStatus,
    OutboxUpdate,
)
from app.domain.repositories.sync_outbox_repository import SyncOutboxRepositoryProtocol
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class SyncOutboxRepository(SyncOutboxRepositoryProtocol):
    """Repository for managing sync outbox entries."""

    def __init__(self):
        self._mongodb = get_mongodb()
        self._collection: AsyncIOMotorCollection | None = None
        self._dlq_collection: AsyncIOMotorCollection | None = None

    async def _ensure_collections(self) -> tuple[AsyncIOMotorCollection, AsyncIOMotorCollection]:
        """Lazily initialize MongoDB collections.

        Sync worker services may be constructed before app startup has fully initialized
        MongoDB. Resolve handles at first use so construction remains safe.
        """
        if self._collection is not None and self._dlq_collection is not None:
            return self._collection, self._dlq_collection

        try:
            _ = self._mongodb.client
        except RuntimeError:
            await self._mongodb.initialize()

        db = self._mongodb.database
        self._collection = db.sync_outbox
        self._dlq_collection = db.dead_letter_queue
        return self._collection, self._dlq_collection

    async def create(self, entry: OutboxCreate) -> OutboxEntry:
        """Create a new outbox entry."""
        collection, _ = await self._ensure_collections()
        outbox_entry = OutboxEntry(
            operation=entry.operation,
            collection_name=entry.collection_name,
            payload=entry.payload,
            max_retries=entry.max_retries,
        )

        doc = self._normalize_for_mongodb(outbox_entry.model_dump(exclude={"id"}))
        result = await collection.insert_one(doc)

        outbox_entry.id = str(result.inserted_id)
        logger.debug(f"Created outbox entry {outbox_entry.id} for {entry.operation}")
        return outbox_entry

    async def get_pending_entries(self, limit: int = 100) -> list[OutboxEntry]:
        """Get pending outbox entries ready for processing.

        Returns entries that are:
        - Status PENDING
        - Either no next_retry_at or next_retry_at <= now
        - Ordered by created_at (FIFO)
        """
        collection, _ = await self._ensure_collections()
        now = datetime.now(UTC)
        cursor = (
            collection.find(
                {
                    "status": OutboxStatus.PENDING.value,
                    "$or": [
                        {"next_retry_at": None},
                        {"next_retry_at": {"$lte": now}},
                    ],
                }
            )
            .sort("created_at", 1)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            entries.append(OutboxEntry(**doc))

        return entries

    async def update(self, entry_id: str, update: OutboxUpdate) -> bool:
        """Update an outbox entry."""
        collection, _ = await self._ensure_collections()
        update_data = self._normalize_for_mongodb(dict(update.model_dump(exclude_none=True)))
        update_data["updated_at"] = datetime.now(UTC)

        result = await collection.update_one(
            {"_id": self._to_object_id(entry_id)},
            {"$set": update_data},
        )

        return result.modified_count > 0

    async def mark_processing(self, entry_id: str) -> bool:
        """Mark entry as currently being processed."""
        return await self.update(entry_id, OutboxUpdate(status=OutboxStatus.PROCESSING))

    async def mark_completed(self, entry_id: str) -> bool:
        """Mark entry as successfully completed."""
        return await self.update(
            entry_id,
            OutboxUpdate(
                status=OutboxStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            ),
        )

    async def mark_failed(self, entry_id: str, error: str, retry_count: int, next_retry_at: datetime | None) -> bool:
        """Mark entry as failed with retry information."""
        return await self.update(
            entry_id,
            OutboxUpdate(
                status=OutboxStatus.PENDING if next_retry_at else OutboxStatus.FAILED,
                error_message=error,
                last_error_at=datetime.now(UTC),
                retry_count=retry_count,
                next_retry_at=next_retry_at,
            ),
        )

    async def move_to_dead_letter_queue(self, entry: OutboxEntry) -> DeadLetterEntry:
        """Move failed entry to dead-letter queue."""
        _, dlq_collection = await self._ensure_collections()
        dlq_entry = DeadLetterEntry(
            original_outbox_id=entry.id or "",
            operation=entry.operation,
            collection_name=entry.collection_name,
            payload=entry.payload,
            retry_count=entry.retry_count,
            final_error=entry.error_message or "Unknown error",
            error_history=[
                {
                    "error": entry.error_message,
                    "timestamp": entry.last_error_at,
                    "retry_count": entry.retry_count,
                }
            ],
            original_created_at=entry.created_at,
        )

        doc = dlq_entry.model_dump(exclude={"id"})
        doc = self._normalize_for_mongodb(doc)
        result = await dlq_collection.insert_one(doc)
        dlq_entry.id = str(result.inserted_id)

        # Mark original entry as FAILED
        await self.update(entry.id or "", OutboxUpdate(status=OutboxStatus.FAILED))

        logger.warning(
            f"Moved outbox entry {entry.id} to DLQ after {entry.retry_count} retries. Error: {entry.error_message}"
        )

        return dlq_entry

    async def get_stats(self) -> dict[str, Any]:
        """Get outbox statistics."""
        collection, dlq_collection = await self._ensure_collections()
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]

        stats = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
        }

        try:
            async for doc in collection.aggregate(pipeline):
                status = doc["_id"]
                count = doc["count"]
                stats[status] = count
        except Exception as exc:
            logger.warning("Failed to aggregate outbox stats: %s", exc)

        # DLQ stats
        try:
            dlq_count = await dlq_collection.count_documents({})
        except Exception as exc:
            logger.warning("Failed to count DLQ documents: %s", exc)
            dlq_count = 0
        stats["dead_letter_queue"] = dlq_count

        return stats

    async def cleanup_old_completed(self, days: int = 7) -> int:
        """Delete completed entries older than specified days.

        Args:
            days: Delete completed entries older than this many days

        Returns:
            Number of deleted entries
        """
        collection, _ = await self._ensure_collections()
        from datetime import UTC, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await collection.delete_many(
            {
                "status": OutboxStatus.COMPLETED.value,
                "completed_at": {"$lt": cutoff},
            }
        )

        if result.deleted_count > 0:
            logger.info(f"Cleaned up {result.deleted_count} completed outbox entries older than {days} days")

        return result.deleted_count

    def _to_object_id(self, id_str: str):
        """Convert string ID to MongoDB ObjectId."""
        from bson import ObjectId

        return ObjectId(id_str)

    def _normalize_for_mongodb(self, value: Any) -> Any:
        """Recursively normalize values for BSON serialization.

        MongoDB requires document keys to be strings. Some payload producers
        (for example sparse vectors) use integer keys, so normalize nested
        mapping keys to strings before writes.
        """
        if isinstance(value, dict):
            return {str(key): self._normalize_for_mongodb(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._normalize_for_mongodb(item) for item in value]
        if isinstance(value, tuple):
            return [self._normalize_for_mongodb(item) for item in value]
        return value
