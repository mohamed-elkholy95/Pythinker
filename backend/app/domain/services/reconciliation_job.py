"""Reconciliation job for MongoDB ↔ Qdrant consistency.

Ensures data consistency by:
- Retrying failed sync operations
- Detecting missing vectors in Qdrant
- Detecting orphaned vectors in Qdrant
- Reporting inconsistencies for monitoring
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.models.sync_outbox import OutboxCreate, OutboxOperation
from app.domain.repositories.memories_collection import MemoriesCollectionProtocol
from app.domain.repositories.sync_outbox_repository import SyncOutboxRepository
from app.domain.repositories.vector_memory_repository import VectorMemoryRepository

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
        outbox_repo: SyncOutboxRepository,
        qdrant_repo: VectorMemoryRepository,
        memories_collection: MemoriesCollectionProtocol,
        retry_failed_after_hours: int = 1,  # Retry failed syncs after 1 hour
        max_retries_per_run: int = 100,
    ):
        self.outbox_repo = outbox_repo
        self.qdrant_repo = qdrant_repo
        self.memories_collection = memories_collection
        self.retry_failed_after_hours = retry_failed_after_hours
        self.max_retries_per_run = max_retries_per_run

    async def run_reconciliation(self) -> dict[str, Any]:
        """Run full reconciliation cycle.

        Returns:
            Statistics about the reconciliation run
        """
        logger.debug("Starting reconciliation job")
        start_time = datetime.now(UTC)

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

        except Exception as e:
            logger.error(f"Reconciliation job failed: {e}", exc_info=True)
            stats["errors"].append(str(e))

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()
        stats["completed_at"] = end_time.isoformat()
        stats["duration_seconds"] = duration

        # Log at info only when work was done, debug otherwise to reduce noise
        log_fn = logger.info if (stats["failed_retried"] > 0 or stats["missing_vectors_found"] > 0) else logger.debug
        log_fn(
            "Reconciliation job completed in %.2fs: retried=%d, missing=%d",
            duration,
            stats["failed_retried"],
            stats["missing_vectors_found"],
        )

        return stats

    async def _retry_failed_syncs(self) -> int:
        """Retry failed sync operations that are eligible for retry.

        Finds memories with sync_state='failed' that were last attempted
        more than retry_failed_after_hours ago, and creates new outbox entries.

        Returns:
            Number of failed syncs retried
        """
        cutoff = datetime.now(UTC) - timedelta(hours=self.retry_failed_after_hours)

        # Find failed memories eligible for retry
        failed_memories = await self.memories_collection.find_failed_memories(
            cutoff=cutoff,
            max_sync_attempts=10,
            limit=self.max_retries_per_run,
        )

        retried_count = 0

        for memory_doc in failed_memories:
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
                await self.memories_collection.update_sync_state(
                    memory_id=memory_id,
                    sync_state="pending",
                    sync_attempts_increment=1,
                    last_sync_attempt=datetime.now(UTC),
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
        recent_cutoff = datetime.now(UTC) - timedelta(hours=24)

        synced_memories = await self.memories_collection.find_synced_memories_needing_verification(
            since=recent_cutoff,
            limit=100,
        )

        missing_count = 0

        for memory_doc in synced_memories:
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
                    await self.memories_collection.update_sync_state(
                        memory_id=memory_id,
                        sync_state="pending",
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
        sync_states = await self.memories_collection.aggregate_sync_states()

        # Get outbox stats
        outbox_stats = await self.outbox_repo.get_stats()

        return {
            "memory_sync_states": sync_states,
            "outbox_stats": outbox_stats,
        }


# Global reconciliation job instance
_reconciliation_job: ReconciliationJob | None = None


def set_reconciliation_job(job: ReconciliationJob) -> None:
    """Set the global reconciliation job instance.

    Called from the composition root (main.py) to inject
    the job with concrete infrastructure dependencies.

    Args:
        job: Fully configured ReconciliationJob instance
    """
    global _reconciliation_job
    _reconciliation_job = job


async def get_reconciliation_job() -> ReconciliationJob:
    """Get the global reconciliation job instance.

    Returns:
        The configured ReconciliationJob

    Raises:
        RuntimeError: If job has not been initialized via set_reconciliation_job
    """
    if _reconciliation_job is None:
        raise RuntimeError(
            "ReconciliationJob not initialized. Call set_reconciliation_job() from the composition root."
        )
    return _reconciliation_job


async def run_reconciliation() -> dict[str, Any]:
    """Run reconciliation job.

    Returns:
        Reconciliation statistics
    """
    job = await get_reconciliation_job()
    return await job.run_reconciliation()
