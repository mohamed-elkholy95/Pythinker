"""Tests for sync worker background processing.

Phase 2: Tests outbox pattern, retry logic, and dead-letter queue.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from app.domain.models.sync_outbox import OutboxCreate, OutboxOperation, OutboxStatus
from app.domain.services.sync_worker import SyncWorker
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository
from app.infrastructure.storage.qdrant import get_qdrant


@pytest.fixture(scope="function")
async def qdrant_repo():
    """Initialize Qdrant and return repository with cleanup."""
    qdrant = get_qdrant()
    await qdrant.initialize()
    repo = QdrantMemoryRepository()
    yield repo
    await qdrant.shutdown()


@pytest.fixture(scope="function")
async def outbox_repo():
    """Create outbox repository with cleanup."""
    repo = SyncOutboxRepository()
    yield repo
    # Cleanup: delete all test outbox entries
    try:
        await repo._collection.delete_many({})
        await repo._dlq_collection.delete_many({})
    except Exception:
        pass


@pytest.mark.asyncio
class TestSyncWorkerBasics:
    """Test basic sync worker operations."""

    async def test_worker_start_stop(self):
        """Test starting and stopping sync worker."""
        worker = SyncWorker(poll_interval=0.1, batch_size=10)

        assert not worker._running

        await worker.start()
        assert worker._running

        # Give it a moment to run
        await asyncio.sleep(0.2)

        await worker.stop()
        assert not worker._running

    async def test_worker_processes_pending_entries(self, outbox_repo, qdrant_repo):
        """Test worker processes pending outbox entries."""
        # Create a pending entry
        memory_id = str(uuid.uuid4())
        entry = await outbox_repo.create(
            OutboxCreate(
                operation=OutboxOperation.UPSERT,
                collection_name="user_knowledge",
                payload={
                    "memory_id": memory_id,
                    "user_id": "test-user",
                    "embedding": [0.1] * 1536,
                    "memory_type": "fact",
                    "importance": "medium",
                    "tags": ["test"],
                    "sparse_vector": {0: 0.5},
                    "session_id": "session-1",
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
        )

        # Start worker
        worker = SyncWorker(outbox_repo=outbox_repo, qdrant_repo=qdrant_repo, poll_interval=0.1)
        await worker.start()

        # Wait for processing
        await asyncio.sleep(0.5)

        await worker.stop()

        # Verify entry was completed
        stats = await outbox_repo.get_stats()
        assert stats["completed"] > 0

        # Verify memory exists in Qdrant
        exists = await qdrant_repo.memory_exists(memory_id)
        assert exists

        # Cleanup
        await qdrant_repo.delete_memory(memory_id)


@pytest.mark.asyncio
class TestRetryLogic:
    """Test exponential backoff retry logic."""

    async def test_failed_entry_retries(self, outbox_repo):
        """Test that failed entries are retried with backoff."""
        # Create entry that will fail (invalid collection)
        entry = await outbox_repo.create(
            OutboxCreate(
                operation=OutboxOperation.UPSERT,
                collection_name="nonexistent_collection",
                payload={"memory_id": "test-id", "user_id": "test-user", "embedding": [0.1] * 1536},
                max_retries=3,
            )
        )

        # Manually mark as failed once
        await outbox_repo.mark_failed(
            entry.id,
            error="Collection not found",
            retry_count=1,
            next_retry_at=datetime.utcnow() + timedelta(seconds=1),
        )

        # Verify retry scheduled
        updated_entry = (await outbox_repo.get_pending_entries(limit=1))[0] if await outbox_repo.get_pending_entries(limit=1) else None

        # Entry should not be pending yet (next_retry_at is in future)
        assert updated_entry is None or updated_entry.id != entry.id

    async def test_max_retries_moves_to_dlq(self, outbox_repo):
        """Test that entries exceeding max retries move to DLQ."""
        entry = await outbox_repo.create(
            OutboxCreate(
                operation=OutboxOperation.UPSERT,
                collection_name="user_knowledge",
                payload={"memory_id": "test-id"},
                max_retries=2,
            )
        )

        # Simulate failures up to max retries
        for i in range(1, 3):
            await outbox_repo.mark_failed(
                entry.id, error=f"Failure {i}", retry_count=i, next_retry_at=datetime.utcnow() + timedelta(seconds=1)
            )

        # Final failure should trigger DLQ move
        # Fetch latest entry state
        from bson import ObjectId

        entry_doc = await outbox_repo._collection.find_one({"_id": ObjectId(entry.id)})
        from app.domain.models.sync_outbox import OutboxEntry

        entry_obj = OutboxEntry(**{**entry_doc, "id": str(entry_doc["_id"])})

        dlq_entry = await outbox_repo.move_to_dead_letter_queue(entry_obj)

        assert dlq_entry.id is not None
        assert dlq_entry.retry_count >= 2

        # Verify original entry marked as FAILED
        stats = await outbox_repo.get_stats()
        assert stats["failed"] > 0
        assert stats["dead_letter_queue"] > 0


@pytest.mark.asyncio
class TestBatchOperations:
    """Test batch upsert and delete operations."""

    async def test_batch_upsert(self, outbox_repo, qdrant_repo):
        """Test batch memory upsert."""
        memory_ids = [str(uuid.uuid4()) for _ in range(3)]
        memories = [
            {
                "memory_id": memory_ids[i],
                "user_id": "test-user",
                "embedding": [float(i) / 100] * 1536,
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["batch"],
                "sparse_vector": {0: 0.5 + i * 0.1},
                "session_id": "session-batch",
                "created_at": datetime.utcnow().isoformat(),
            }
            for i in range(3)
        ]

        entry = await outbox_repo.create(
            OutboxCreate(
                operation=OutboxOperation.BATCH_UPSERT, collection_name="user_knowledge", payload={"memories": memories}
            )
        )

        # Process entry
        worker = SyncWorker(outbox_repo=outbox_repo, qdrant_repo=qdrant_repo, poll_interval=0.1)
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()

        # Verify all memories exist
        for memory_id in memory_ids:
            exists = await qdrant_repo.memory_exists(memory_id)
            assert exists

        # Cleanup
        await qdrant_repo.delete_memories_batch(memory_ids)

    async def test_batch_delete(self, outbox_repo, qdrant_repo):
        """Test batch memory deletion."""
        memory_ids = [str(uuid.uuid4()) for _ in range(3)]

        # First, insert memories
        for i, memory_id in enumerate(memory_ids):
            await qdrant_repo.upsert_memory(
                memory_id=memory_id,
                user_id="test-user",
                embedding=[float(i) / 100] * 1536,
                memory_type="fact",
                importance="medium",
                tags=["batch-delete"],
                sparse_vector={0: 0.5},
            )

        # Create batch delete entry
        entry = await outbox_repo.create(
            OutboxCreate(
                operation=OutboxOperation.BATCH_DELETE, collection_name="user_knowledge", payload={"memory_ids": memory_ids}
            )
        )

        # Process entry
        worker = SyncWorker(outbox_repo=outbox_repo, qdrant_repo=qdrant_repo, poll_interval=0.1)
        await worker.start()
        await asyncio.sleep(0.5)
        await worker.stop()

        # Verify all memories deleted
        for memory_id in memory_ids:
            exists = await qdrant_repo.memory_exists(memory_id)
            assert not exists


@pytest.mark.asyncio
class TestWorkerStats:
    """Test worker statistics reporting."""

    async def test_get_worker_stats(self, outbox_repo):
        """Test worker statistics."""
        worker = SyncWorker(outbox_repo=outbox_repo, poll_interval=0.1, batch_size=50)

        stats = await worker.get_stats()

        assert "running" in stats
        assert "poll_interval" in stats
        assert "batch_size" in stats
        assert "pending" in stats
        assert stats["poll_interval"] == 0.1
        assert stats["batch_size"] == 50
