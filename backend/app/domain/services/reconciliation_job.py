"""Reconciliation job for MongoDB ↔ Qdrant consistency.

Ensures data consistency by:
- Retrying failed sync operations
- Detecting missing vectors in Qdrant
- Detecting orphaned vectors in Qdrant
- Reporting inconsistencies for monitoring
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.domain.models.sync_outbox import OutboxCreate, OutboxOperation
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class ReconciliationJob:
    """Periodic job to reconcile MongoDB and Qdrant state.

    Runs on a schedule to detect and fix:
    - MongoDB memories without Qdrant vectors
    - Qdrant vectors without MongoDB memories (orphans)
    - Stale failed sync operations
    """

    def __init__(
        self,
        outbox_repo: SyncOutboxRepository | None = None,
        qdrant_repo: QdrantMemoryRepository | None = None,
        retry_failed_after_hours: int = 1,  # Retry failed syncs after 1 hour
        max_retries_per_run: int = 100,
    ):
        self.outbox_repo = outbox_repo or SyncOutboxRepository()
        self.qdrant_repo = qdrant_repo or QdrantMemoryRepository()
        self.retry_failed_after_hours = retry_failed_after_hours
        self.max_retries_per_run = max_retries_per_run

        # Lazily resolve MongoDB handles so construction is safe before startup init.
        self._mongodb = get_mongodb()
        self._memories_collection = None

    async def _get_memories_collection(self):
        """Return initialized memories collection."""
        if self._memories_collection is not None:
            return self._memories_collection

        try:
            _ = self._mongodb.client
        except RuntimeError:
            await self._mongodb.initialize()

        self._memories_collection = self._mongodb.database.memories
        return self._memories_collection

    async def run_reconciliation(self) -> dict[str, Any]:
        """Run full reconciliation cycle.

        Returns:
            Statistics about the reconciliation run
        """
        logger.info("Starting reconciliation job")
        start_time = datetime.utcnow()

        stats = {
            "started_at": start_time.isoformat(),
            "failed_retried": 0,
            "missing_vectors_found": 0,
            "orphaned_vectors_found": 0,
            "errors": [],
        }

        try:
            # Step 1: Retry failed sync operations
            failed_retried = await self._retry_failed_syncs()
            stats["failed_retried"] = failed_retried

            # Step 2: Find MongoDB memories without Qdrant vectors
            missing_count = await self._find_missing_vectors()
            stats["missing_vectors_found"] = missing_count

            # Step 3: Find orphaned Qdrant vectors (optional, expensive)
            # Disabled by default as it requires scanning all Qdrant vectors
            # orphaned_count = await self._find_orphaned_vectors()
            # stats["orphaned_vectors_found"] = orphaned_count

        except Exception as e:
            logger.error(f"Reconciliation job failed: {e}", exc_info=True)
            stats["errors"].append(str(e))

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        stats["completed_at"] = end_time.isoformat()
        stats["duration_seconds"] = duration

        logger.info(
            f"Reconciliation job completed in {duration:.2f}s: "
            f"retried={stats['failed_retried']}, "
            f"missing={stats['missing_vectors_found']}"
        )

        return stats

    async def _retry_failed_syncs(self) -> int:
        """Retry failed sync operations that are eligible for retry.

        Finds memories with sync_state='failed' that were last attempted
        more than retry_failed_after_hours ago, and creates new outbox entries.

        Returns:
            Number of failed syncs retried
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.retry_failed_after_hours)

        # Find failed memories eligible for retry
        memories_collection = await self._get_memories_collection()
        cursor = memories_collection.find(
            {
                "sync_state": "failed",
                "last_sync_attempt": {"$lt": cutoff},
                "sync_attempts": {"$lt": 10},  # Stop after 10 total attempts
            }
        ).limit(self.max_retries_per_run)

        retried_count = 0

        async for memory_doc in cursor:
            memory_id = str(memory_doc["_id"])

            try:
                # Create new outbox entry to retry sync
                await self.outbox_repo.create(
                    OutboxCreate(
                        operation=OutboxOperation.UPSERT,
                        collection_name="user_knowledge",
                        payload={
                            "memory_id": memory_id,
                            "user_id": memory_doc.get("user_id"),
                            "embedding": memory_doc.get("embedding"),
                            "memory_type": memory_doc.get("memory_type"),
                            "importance": memory_doc.get("importance"),
                            "tags": memory_doc.get("tags", []),
                            "sparse_vector": memory_doc.get("sparse_vector"),
                            "session_id": memory_doc.get("session_id"),
                            "created_at": memory_doc.get("created_at").isoformat()
                            if memory_doc.get("created_at")
                            else None,
                        },
                        max_retries=3,  # Lower retries for reconciliation (already failed once)
                    )
                )

                # Update memory to indicate retry
                await memories_collection.update_one(
                    {"_id": memory_doc["_id"]},
                    {
                        "$set": {
                            "sync_state": "pending",
                            "last_sync_attempt": datetime.utcnow(),
                        },
                        "$inc": {"sync_attempts": 1},
                    },
                )

                retried_count += 1
                logger.debug(f"Retrying failed sync for memory {memory_id}")

            except Exception as e:
                logger.warning(f"Failed to retry sync for memory {memory_id}: {e}")

        if retried_count > 0:
            logger.info(f"Retried {retried_count} failed sync operations")

        return retried_count

    async def _find_missing_vectors(self) -> int:
        """Find MongoDB memories without corresponding Qdrant vectors.

        Checks memories with sync_state='synced' to verify the vector exists.
        If missing, creates outbox entry to re-sync.

        Returns:
            Number of missing vectors detected
        """
        # Sample recently synced memories to verify
        recent_cutoff = datetime.utcnow() - timedelta(hours=24)

        memories_collection = await self._get_memories_collection()
        cursor = memories_collection.find(
            {
                "sync_state": "synced",
                "updated_at": {"$gte": recent_cutoff},
                "embedding": {"$exists": True, "$ne": None},
            }
        ).limit(100)  # Check up to 100 recent memories per run

        missing_count = 0

        async for memory_doc in cursor:
            memory_id = str(memory_doc["_id"])

            try:
                # Check if vector exists in Qdrant
                exists = await self.qdrant_repo.memory_exists(memory_id)

                if not exists:
                    logger.warning(f"Memory {memory_id} marked as synced but vector missing in Qdrant")

                    # Create outbox entry to re-sync
                    await self.outbox_repo.create(
                        OutboxCreate(
                            operation=OutboxOperation.UPSERT,
                            collection_name="user_knowledge",
                            payload={
                                "memory_id": memory_id,
                                "user_id": memory_doc.get("user_id"),
                                "embedding": memory_doc.get("embedding"),
                                "memory_type": memory_doc.get("memory_type"),
                                "importance": memory_doc.get("importance"),
                                "tags": memory_doc.get("tags", []),
                                "sparse_vector": memory_doc.get("sparse_vector"),
                                "session_id": memory_doc.get("session_id"),
                                "created_at": memory_doc.get("created_at").isoformat()
                                if memory_doc.get("created_at")
                                else None,
                            },
                        )
                    )

                    # Update sync state
                    await memories_collection.update_one(
                        {"_id": memory_doc["_id"]},
                        {"$set": {"sync_state": "pending"}},
                    )

                    missing_count += 1

            except Exception as e:
                logger.debug(f"Error checking vector existence for {memory_id}: {e}")

        if missing_count > 0:
            logger.warning(f"Found {missing_count} missing vectors in Qdrant")

        return missing_count

    async def _find_orphaned_vectors(self) -> int:
        """Find Qdrant vectors without corresponding MongoDB memories.

        WARNING: This is expensive and should be run rarely (e.g., weekly).
        Requires scrolling through all Qdrant points.

        Returns:
            Number of orphaned vectors detected
        """
        # This would require implementing scroll_points in QdrantMemoryRepository
        # and checking each point against MongoDB
        # Skipped for Phase 2 - can be added later if needed
        logger.info("Orphaned vector detection not implemented (expensive operation)")
        return 0

    async def get_reconciliation_stats(self) -> dict[str, Any]:
        """Get current reconciliation statistics.

        Returns:
            Current state of sync operations
        """
        # Count memories by sync state
        pipeline = [
            {"$group": {"_id": "$sync_state", "count": {"$sum": 1}}},
        ]

        sync_states = {}
        memories_collection = await self._get_memories_collection()
        async for doc in memories_collection.aggregate(pipeline):
            state = doc["_id"] or "unknown"
            count = doc["count"]
            sync_states[state] = count

        # Get outbox stats
        outbox_stats = await self.outbox_repo.get_stats()

        return {
            "memory_sync_states": sync_states,
            "outbox_stats": outbox_stats,
        }


# Global reconciliation job instance
_reconciliation_job: ReconciliationJob | None = None


async def get_reconciliation_job() -> ReconciliationJob:
    """Get or create the global reconciliation job instance."""
    global _reconciliation_job
    if _reconciliation_job is None:
        _reconciliation_job = ReconciliationJob()
    return _reconciliation_job


async def run_reconciliation() -> dict[str, Any]:
    """Run reconciliation job.

    Returns:
        Reconciliation statistics
    """
    job = await get_reconciliation_job()
    return await job.run_reconciliation()
