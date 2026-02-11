"""Integration tests for Qdrant hybrid search with named vectors.

Phase 1: Tests dense+sparse hybrid retrieval with RRF fusion.
"""

import pytest
from datetime import datetime

from app.domain.models.long_term_memory import MemoryImportance, MemoryType
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.infrastructure.storage.qdrant import get_qdrant


@pytest.fixture
async def qdrant_repo():
    """Initialize Qdrant and return repository."""
    await get_qdrant().initialize()
    repo = QdrantMemoryRepository()
    yield repo
    # Cleanup not needed in dev mode


@pytest.mark.asyncio
class TestQdrantNamedVectors:
    """Test named-vector schema operations."""

    async def test_upsert_with_named_vectors(self, qdrant_repo):
        """Test upserting memory with dense + sparse vectors."""
        memory_id = "test-named-vec-1"
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
            created_at=datetime.utcnow(),
        )

        # Verify memory exists
        exists = await qdrant_repo.memory_exists(memory_id)
        assert exists is True

    async def test_upsert_without_sparse_vector(self, qdrant_repo):
        """Test upserting with only dense vector (backward compat)."""
        memory_id = "test-dense-only-1"
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
        memories = [
            {
                "memory_id": f"batch-{i}",
                "user_id": "test-user",
                "embedding": [float(i) / 1000] * 1536,
                "memory_type": "fact",
                "importance": "low",
                "tags": ["batch"],
                "sparse_vector": {0: 0.9, i: 0.5},
                "session_id": "session-batch",
                "created_at": datetime.utcnow(),
            }
            for i in range(3)
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Verify all exist
        for i in range(3):
            exists = await qdrant_repo.memory_exists(f"batch-{i}")
            assert exists is True


@pytest.mark.asyncio
class TestHybridSearch:
    """Test hybrid dense+sparse search with RRF fusion."""

    async def test_search_similar_with_named_dense(self, qdrant_repo):
        """Test dense-only search uses named 'dense' vector."""
        # Insert test memory
        memory_id = "search-test-1"
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
        # Insert test memories
        memories = [
            {
                "memory_id": "hybrid-1",
                "user_id": "hybrid-user",
                "embedding": [0.7] * 1536,
                "memory_type": "fact",
                "importance": "high",
                "tags": ["python"],
                "sparse_vector": {1: 0.9, 2: 0.7},  # Strong keyword match
            },
            {
                "memory_id": "hybrid-2",
                "user_id": "hybrid-user",
                "embedding": [0.1] * 1536,
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["javascript"],
                "sparse_vector": {10: 0.3, 20: 0.2},  # Weak keyword match
            },
        ]

        await qdrant_repo.upsert_memories_batch(memories)

        # Hybrid search
        query_dense = [0.71] * 1536  # Close to hybrid-1
        query_sparse = {1: 0.85, 2: 0.65}  # Close to hybrid-1 sparse

        results = await qdrant_repo.search_hybrid(
            user_id="hybrid-user",
            query_text="python programming",
            dense_vector=query_dense,
            sparse_vector=query_sparse,
            limit=10,
            min_score=0.0,
        )

        # Should find both memories, with hybrid-1 ranked higher
        assert len(results) > 0
        if len(results) >= 2:
            # First result should be hybrid-1 (better match on both dense and sparse)
            assert results[0].memory_id == "hybrid-1"

    async def test_hybrid_search_with_filters(self, qdrant_repo):
        """Test hybrid search with type/importance filters."""
        # Insert memories with different types
        memories = [
            {
                "memory_id": "filter-fact",
                "user_id": "filter-user",
                "embedding": [0.8] * 1536,
                "memory_type": "fact",
                "importance": "critical",
                "tags": [],
                "sparse_vector": {5: 0.9},
            },
            {
                "memory_id": "filter-pref",
                "user_id": "filter-user",
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
            user_id="filter-user",
            query_text="test query",
            dense_vector=[0.79] * 1536,
            sparse_vector={5: 0.88},
            limit=10,
            min_score=0.0,
            memory_types=[MemoryType.FACT],
        )

        # Should only find fact memory
        assert len(results) == 1
        assert results[0].memory_id == "filter-fact"

    async def test_hybrid_search_with_importance_filter(self, qdrant_repo):
        """Test hybrid search with minimum importance."""
        memories = [
            {
                "memory_id": "import-critical",
                "user_id": "import-user",
                "embedding": [0.9] * 1536,
                "memory_type": "fact",
                "importance": "critical",
                "tags": [],
                "sparse_vector": {7: 0.8},
            },
            {
                "memory_id": "import-low",
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
        assert "import-critical" in memory_ids
        assert "import-low" not in memory_ids


@pytest.mark.asyncio
class TestPayloadFiltering:
    """Test enhanced payload filtering (session_id, tags, created_at)."""

    async def test_filter_by_tags(self, qdrant_repo):
        """Test tag filtering in search."""
        memories = [
            {
                "memory_id": "tag-python",
                "user_id": "tag-user",
                "embedding": [0.5] * 1536,
                "memory_type": "fact",
                "importance": "medium",
                "tags": ["python", "backend"],
                "sparse_vector": {1: 0.7},
            },
            {
                "memory_id": "tag-javascript",
                "user_id": "tag-user",
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
            user_id="tag-user",
            query_vector=[0.49] * 1536,
            limit=10,
            min_score=0.0,
            tags=["python"],
        )

        # Should only find python-tagged memory
        assert len(results) == 1
        assert results[0].memory_id == "tag-python"


@pytest.mark.asyncio
class TestMemoryDeletion:
    """Test deletion with named vectors."""

    async def test_delete_single_memory(self, qdrant_repo):
        """Test deleting a single memory."""
        memory_id = "delete-test-1"
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
        memory_ids = [f"delete-batch-{i}" for i in range(3)]

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
