"""Background sync worker for processing outbox entries.

Ensures reliable MongoDB → Qdrant synchronization with:
- Exponential backoff retry logic
- Dead-letter queue for permanent failures
- Graceful shutdown handling
- Configurable batch processing
"""

import asyncio
import logging
from contextlib import suppress
from typing import Any

from app.domain.models.sync_outbox import OutboxEntry, OutboxOperation, OutboxStatus
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository

logger = logging.getLogger(__name__)


class SyncWorker:
    """Background worker that processes sync outbox entries."""

    def __init__(
        self,
        outbox_repo: SyncOutboxRepository | None = None,
        qdrant_repo: QdrantMemoryRepository | None = None,
        poll_interval: float = 1.0,  # Poll every 1 second
        batch_size: int = 100,
    ):
        self.outbox_repo = outbox_repo or SyncOutboxRepository()
        self.qdrant_repo = qdrant_repo or QdrantMemoryRepository()
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background sync worker."""
        if self._running:
            logger.warning("Sync worker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Sync worker started")

    async def stop(self) -> None:
        """Stop the background sync worker gracefully."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

        logger.info("Sync worker stopped")

    async def _run_loop(self) -> None:
        """Main worker loop that processes outbox entries."""
        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"Error in sync worker loop: {e}", exc_info=True)

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)

    async def _process_batch(self) -> None:
        """Process a batch of pending outbox entries."""
        entries = await self.outbox_repo.get_pending_entries(limit=self.batch_size)

        if not entries:
            return

        logger.debug(f"Processing {len(entries)} outbox entries")

        for entry in entries:
            await self._process_entry(entry)

    async def _process_entry(self, entry: OutboxEntry) -> None:
        """Process a single outbox entry.

        Args:
            entry: Outbox entry to process
        """
        if not entry.id:
            logger.error("Outbox entry missing ID, skipping")
            return

        # Mark as processing
        await self.outbox_repo.mark_processing(entry.id)

        try:
            # Execute the operation
            await self._execute_operation(entry)

            # Mark as completed
            await self.outbox_repo.mark_completed(entry.id)
            logger.debug(f"Successfully synced outbox entry {entry.id}")

        except Exception as e:
            # Handle failure with retry logic
            await self._handle_failure(entry, str(e))

    async def _execute_operation(self, entry: OutboxEntry) -> None:
        """Execute the sync operation based on entry type.

        Args:
            entry: Outbox entry containing operation details

        Raises:
            Exception: If operation fails
        """
        payload = entry.payload

        if entry.operation == OutboxOperation.UPSERT:
            await self._execute_upsert(payload)

        elif entry.operation == OutboxOperation.DELETE:
            await self._execute_delete(payload)

        elif entry.operation == OutboxOperation.BATCH_UPSERT:
            await self._execute_batch_upsert(payload)

        elif entry.operation == OutboxOperation.BATCH_DELETE:
            await self._execute_batch_delete(payload)

        else:
            raise ValueError(f"Unknown operation type: {entry.operation}")

    async def _execute_upsert(self, payload: dict[str, Any]) -> None:
        """Execute single memory upsert to Qdrant."""
        from datetime import datetime

        # Parse created_at if it's a string (ISO format)
        created_at = payload.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        await self.qdrant_repo.upsert_memory(
            memory_id=payload["memory_id"],
            user_id=payload["user_id"],
            embedding=payload["embedding"],
            memory_type=payload["memory_type"],
            importance=payload["importance"],
            tags=payload.get("tags"),
            sparse_vector=payload.get("sparse_vector"),
            session_id=payload.get("session_id"),
            created_at=created_at,
        )

    async def _execute_delete(self, payload: dict[str, Any]) -> None:
        """Execute single memory deletion from Qdrant."""
        await self.qdrant_repo.delete_memory(payload["memory_id"])

    async def _execute_batch_upsert(self, payload: dict[str, Any]) -> None:
        """Execute batch memory upsert to Qdrant."""
        await self.qdrant_repo.upsert_memories_batch(payload["memories"])

    async def _execute_batch_delete(self, payload: dict[str, Any]) -> None:
        """Execute batch memory deletion from Qdrant."""
        await self.qdrant_repo.delete_memories_batch(payload["memory_ids"])

    async def _handle_failure(self, entry: OutboxEntry, error: str) -> None:
        """Handle failed sync operation with retry logic.

        Args:
            entry: Failed outbox entry
            error: Error message
        """
        if not entry.id:
            return

        # Update retry count and calculate next retry
        entry.mark_failed(error)

        if entry.status == OutboxStatus.FAILED:
            # Exceeded max retries, move to DLQ
            await self.outbox_repo.move_to_dead_letter_queue(entry)
            logger.error(f"Outbox entry {entry.id} moved to DLQ after {entry.retry_count} retries. Error: {error}")
        else:
            # Update with retry info
            await self.outbox_repo.mark_failed(
                entry.id,
                error,
                entry.retry_count,
                entry.next_retry_at,
            )
            logger.warning(
                f"Outbox entry {entry.id} failed (attempt {entry.retry_count}). "
                f"Next retry at {entry.next_retry_at}. Error: {error}"
            )

    async def get_stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        return {
            "running": self._running,
            "poll_interval": self.poll_interval,
            "batch_size": self.batch_size,
            **await self.outbox_repo.get_stats(),
        }


# Global worker instance
_worker: SyncWorker | None = None


async def get_sync_worker() -> SyncWorker:
    """Get or create the global sync worker instance."""
    global _worker
    if _worker is None:
        _worker = SyncWorker()
    return _worker


async def start_sync_worker() -> None:
    """Start the global sync worker."""
    worker = await get_sync_worker()
    await worker.start()


async def stop_sync_worker() -> None:
    """Stop the global sync worker."""
    global _worker
    if _worker:
        await _worker.stop()
        _worker = None
