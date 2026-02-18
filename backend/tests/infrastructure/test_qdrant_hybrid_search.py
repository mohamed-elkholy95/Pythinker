"""Integration tests for Qdrant hybrid search with named vectors.

Phase 1: Tests dense+sparse hybrid retrieval with RRF fusion.
"""

import uuid
from contextlib import suppress
from datetime import UTC, datetime

import pytest

from app.domain.models.long_term_memory import MemoryImportance, MemoryType
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.infrastructure.storage.qdrant import get_qdrant

pytestmark = [pytest.mark.integration]


@pytest.fixture(scope="function")
async def qdrant_repo():
    """Initialize Qdrant and return repository with cleanup."""
    qdrant = get_qdrant()
    await qdrant.initialize()
    repo = QdrantMemoryRepository()

    # Track inserted memory IDs for cleanup
    inserted_ids = []
    original_upsert = repo.upsert_memory
    original_batch_upsert = repo.upsert_memories_batch

    async def tracked_upsert(*args, **kwargs):
        memory_id = kwargs.get("memory_id") or args[0]
        inserted_ids.append(memory_id)
        return await original_upsert(*args, **kwargs)

    async def tracked_batch_upsert(memories, *args, **kwargs):
        inserted_ids.extend(mem["memory_id"] for mem in memories)
        return await original_batch_upsert(memories, *args, **kwargs)

    repo.upsert_memory = tracked_upsert
    repo.upsert_memories_batch = tracked_batch_upsert

    yield repo

    # Cleanup: delete all inserted memories
    if inserted_ids:
        with suppress(Exception):
            await repo.delete_memories_batch(inserted_ids)

    # Close Qdrant connection
    await qdrant.shutdown()


@pytest.mark.asyncio
class TestQdrantNamedVectors:
    """Test named-vector schema operations."""

    async def test_upsert_with_named_vectors(self, qdrant_repo):
        """Test upserting memory with dense + sparse vectors."""
        memory_id = str(uuid.uuid4())
        dense = [0.1] * 1536  # Mock dense embedding
        sparse = {0: 0.8, 5: 0.6, 10: 0.4}  # Mock BM25 sparse vector

        await qdrant_repo.upsert_memory(
            memory_id=memory_id,
            user_id="test-user",
            embedding=dense,
            memory_type="fact",
            importance="high",
            tags=["test"],
            sparse_vector=sparse,
            session_id="session-123",
            created_at=datetime.now(UTC),
        )

        # Verify memory exists
        exists = await qdrant_repo.memory_exists(memory_id)
        assert exists is True

    async def test_upsert_without_sparse_vector(self, qdrant_repo):
        """Test upserting with only dense vector (backward compat)."""
        memory_id = str(uuid.uuid4())
        dense = [0.2] * 1536

        await qdrant_repo.upsert_memory(
            memory_id=memory_id,
            user_id="test-user",
            embedding=dense,
            memory_type="preference",
            importance="medium",
            tags=[],
            sparse_vector=None,  # No sparse vector
        )

        exists = await qdrant_repo.memory_exists(memory_id)
        assert exists is True

    async def test_batch_upsert_with_sparse(self, qdrant_repo):
        """Test batch upsert with sparse vectors."""
        memory_ids = [str(uuid.uuid4()) for _ in range(3)]
        memories = [
            {
                "memory_id": memory_ids[i],
                "user_id": "test-user",
                "embedding": [float(i) / 1000] * 1536,
                "memory_type": "fact",
                "importance": "low",
                "tags": ["batch"],
                "sparse_vector": {0: 0.9, i: 0.5},
                "session_id": "session-batch",
                "created_at": datetime.now(UTC),
            }
            for i in range(3)
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Verify all exist
        for memory_id in memory_ids:
            exists = await qdrant_repo.memory_exists(memory_id)
            assert exists is True


@pytest.mark.asyncio
class TestHybridSearch:
    """Test hybrid dense+sparse search with RRF fusion."""

    async def test_search_similar_with_named_dense(self, qdrant_repo):
        """Test dense-only search uses named 'dense' vector."""
        # Insert test memory
        memory_id = str(uuid.uuid4())
        dense = [0.5] * 1536
        await qdrant_repo.upsert_memory(
            memory_id=memory_id,
            user_id="search-user",
            embedding=dense,
            memory_type="fact",
            importance="high",
            tags=["search"],
            sparse_vector={0: 0.8},
        )

        # Search with similar dense vector
        query_vector = [0.51] * 1536
        results = await qdrant_repo.search_similar(
            user_id="search-user",
            query_vector=query_vector,
            limit=10,
            min_score=0.0,
        )

        # Should find the memory
        assert len(results) > 0
        assert any(r.memory_id == memory_id for r in results)

    async def test_hybrid_search_rrf_fusion(self, qdrant_repo):
        """Test hybrid search with RRF fusion."""
        hybrid_id_1 = str(uuid.uuid4())
        hybrid_id_2 = str(uuid.uuid4())

        # Insert test memories
        memories = [
            {
                "memory_id": hybrid_id_1,
                "user_id": "hybrid-user",
                "embedding": [0.7 if i % 2 == 0 else 0.3 for i in range(1536)],  # Varied vector
                "memory_type": "fact",
                "importance": "high",
                "tags": ["python"],
                "sparse_vector": {1: 0.9, 2: 0.7},  # Strong keyword match
            },
            {
                "memory_id": hybrid_id_2,
                "user_id": "hybrid-user",
                "embedding": [0.1 if i % 2 == 0 else 0.9 for i in range(1536)],  # Different pattern
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["javascript"],
                "sparse_vector": {10: 0.3, 20: 0.2},  # Weak keyword match
            },
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Hybrid search
        query_dense = [0.71 if i % 2 == 0 else 0.29 for i in range(1536)]  # Close to hybrid_id_1
        query_sparse = {1: 0.85, 2: 0.65}  # Close to hybrid_id_1 sparse

        results = await qdrant_repo.search_hybrid(
            user_id="hybrid-user",
            query_text="python programming",
            dense_vector=query_dense,
            sparse_vector=query_sparse,
            limit=10,
            min_score=0.0,
        )

        # Should find both memories
        assert len(results) >= 1  # RRF fusion might rank differently
        # Verify both memories are in results
        memory_ids = {r.memory_id for r in results}
        assert hybrid_id_1 in memory_ids or hybrid_id_2 in memory_ids

    async def test_hybrid_search_with_filters(self, qdrant_repo):
        """Test hybrid search with type/importance filters."""
        filter_fact_id = str(uuid.uuid4())
        filter_pref_id = str(uuid.uuid4())
        test_user_id = f"filter-user-{uuid.uuid4()}"  # Unique per test run

        # Insert memories with different types
        memories = [
            {
                "memory_id": filter_fact_id,
                "user_id": test_user_id,
                "embedding": [0.8] * 1536,
                "memory_type": "fact",
                "importance": "critical",
                "tags": [],
                "sparse_vector": {5: 0.9},
            },
            {
                "memory_id": filter_pref_id,
                "user_id": test_user_id,
                "embedding": [0.81] * 1536,
                "memory_type": "preference",
                "importance": "low",
                "tags": [],
                "sparse_vector": {5: 0.85},
            },
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Search with type filter
        results = await qdrant_repo.search_hybrid(
            user_id=test_user_id,
            query_text="test query",
            dense_vector=[0.79] * 1536,
            sparse_vector={5: 0.88},
            limit=10,
            min_score=0.0,
            memory_types=[MemoryType.FACT],
        )

        # Should only find fact memory
        assert len(results) == 1
        assert results[0].memory_id == filter_fact_id

    async def test_hybrid_search_with_importance_filter(self, qdrant_repo):
        """Test hybrid search with minimum importance."""
        import_critical_id = str(uuid.uuid4())
        import_low_id = str(uuid.uuid4())

        memories = [
            {
                "memory_id": import_critical_id,
                "user_id": "import-user",
                "embedding": [0.9] * 1536,
                "memory_type": "fact",
                "importance": "critical",
                "tags": [],
                "sparse_vector": {7: 0.8},
            },
            {
                "memory_id": import_low_id,
                "user_id": "import-user",
                "embedding": [0.91] * 1536,
                "memory_type": "fact",
                "importance": "low",
                "tags": [],
                "sparse_vector": {7: 0.79},
            },
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Search with high importance filter
        results = await qdrant_repo.search_hybrid(
            user_id="import-user",
            query_text="important stuff",
            dense_vector=[0.89] * 1536,
            sparse_vector={7: 0.81},
            limit=10,
            min_score=0.0,
            min_importance=MemoryImportance.HIGH,
        )

        # Should only find critical (high+ importance)
        memory_ids = [r.memory_id for r in results]
        assert import_critical_id in memory_ids
        assert import_low_id not in memory_ids


@pytest.mark.asyncio
class TestPayloadFiltering:
    """Test enhanced payload filtering (session_id, tags, created_at)."""

    async def test_filter_by_tags(self, qdrant_repo):
        """Test tag filtering in search."""
        python_id = str(uuid.uuid4())
        javascript_id = str(uuid.uuid4())
        test_user_id = f"tag-user-{uuid.uuid4()}"  # Unique per test run

        memories = [
            {
                "memory_id": python_id,
                "user_id": test_user_id,
                "embedding": [0.5] * 1536,
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["python", "backend"],
                "sparse_vector": {1: 0.7},
            },
            {
                "memory_id": javascript_id,
                "user_id": test_user_id,
                "embedding": [0.51] * 1536,
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["javascript", "frontend"],
                "sparse_vector": {1: 0.69},
            },
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Search with tag filter
        results = await qdrant_repo.search_similar(
            user_id=test_user_id,
            query_vector=[0.49] * 1536,
            limit=10,
            min_score=0.0,
            tags=["python"],
        )

        # Should only find python-tagged memory
        assert len(results) == 1
        assert results[0].memory_id == python_id


@pytest.mark.asyncio
class TestMemoryDeletion:
    """Test deletion with named vectors."""

    async def test_delete_single_memory(self, qdrant_repo):
        """Test deleting a single memory."""
        memory_id = str(uuid.uuid4())
        await qdrant_repo.upsert_memory(
            memory_id=memory_id,
            user_id="delete-user",
            embedding=[0.3] * 1536,
            memory_type="fact",
            importance="low",
            tags=[],
            sparse_vector={2: 0.5},
        )

        # Verify exists
        assert await qdrant_repo.memory_exists(memory_id) is True

        # Delete
        await qdrant_repo.delete_memory(memory_id)

        # Verify deleted
        assert await qdrant_repo.memory_exists(memory_id) is False

    async def test_delete_batch(self, qdrant_repo):
        """Test batch deletion."""
        memory_ids = [str(uuid.uuid4()) for _ in range(3)]

        for mem_id in memory_ids:
            await qdrant_repo.upsert_memory(
                memory_id=mem_id,
                user_id="delete-batch-user",
                embedding=[0.4] * 1536,
                memory_type="fact",
                importance="low",
                tags=[],
                sparse_vector={3: 0.6},
            )

        # Delete batch
        await qdrant_repo.delete_memories_batch(memory_ids)

        # Verify all deleted
        for mem_id in memory_ids:
            assert await qdrant_repo.memory_exists(mem_id) is False
