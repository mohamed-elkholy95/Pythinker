"""Tests for batched retrieval.

Phase 3: Tests parallel memory retrieval functionality.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.long_term_memory import MemoryEntry, MemoryImportance, MemorySearchResult, MemoryType
from app.domain.services.retrieval.batch_retrieval import batch_retrieve, batch_retrieve_deduped


@pytest.mark.asyncio
class TestBatchRetrieval:
    """Test batched memory retrieval."""

    async def test_batch_retrieve_multiple_queries(self):
        """Test batch retrieval for multiple queries."""
        # Mock memory service
        memory_service = MagicMock()
        memory_service.retrieve_relevant = AsyncMock()

        # Create mock results for each query
        def mock_retrieve(user_id, context, **kwargs):
            return [
                MemorySearchResult(
                    memory=MemoryEntry(
                        id=f"mem-{context[:5]}",
                        user_id=user_id,
                        content=f"Memory for {context}",
                        memory_type=MemoryType.FACT,
                        importance=MemoryImportance.MEDIUM,
                        keywords=[],
                        tags=[],
                        entities=[],
                    ),
                    relevance_score=0.9,
                    match_type="semantic",
                )
            ]

        memory_service.retrieve_relevant = AsyncMock(side_effect=mock_retrieve)

        queries = ["query 1", "query 2", "query 3"]

        results = await batch_retrieve(
            memory_service=memory_service,
            user_id="test-user",
            queries=queries,
            limit_per_query=5,
        )

        # Should have results for all queries
        assert len(results) == 3
        assert all(q in results for q in queries)

        # Each query should have results
        for query in queries:
            assert len(results[query]) > 0

        # Memory service should have been called for each query
        assert memory_service.retrieve_relevant.call_count == 3

    async def test_batch_retrieve_empty_queries(self):
        """Test batch retrieval with empty queries."""
        memory_service = MagicMock()

        results = await batch_retrieve(
            memory_service=memory_service,
            user_id="test-user",
            queries=[],
            limit_per_query=5,
        )

        assert results == {}

    async def test_batch_retrieve_handles_errors(self):
        """Test batch retrieval handles individual query errors."""
        memory_service = MagicMock()

        async def mock_retrieve_with_error(user_id, context, **kwargs):
            if context == "query 2":
                raise Exception("Retrieval failed")
            return [
                MemorySearchResult(
                    memory=MemoryEntry(
                        id=f"mem-{context[:5]}",
                        user_id=user_id,
                        content=f"Memory for {context}",
                        memory_type=MemoryType.FACT,
                        importance=MemoryImportance.MEDIUM,
                        keywords=[],
                        tags=[],
                        entities=[],
                    ),
                    relevance_score=0.9,
                    match_type="semantic",
                )
            ]

        memory_service.retrieve_relevant = AsyncMock(side_effect=mock_retrieve_with_error)

        queries = ["query 1", "query 2", "query 3"]

        results = await batch_retrieve(
            memory_service=memory_service,
            user_id="test-user",
            queries=queries,
            limit_per_query=5,
        )

        # Should have results for queries 1 and 3, empty for query 2
        assert len(results) == 3
        assert len(results["query 1"]) > 0
        assert len(results["query 2"]) == 0  # Error case
        assert len(results["query 3"]) > 0


@pytest.mark.asyncio
class TestBatchRetrieveDeduped:
    """Test deduplicated batch retrieval."""

    async def test_batch_retrieve_deduped_removes_duplicates(self):
        """Test deduplication removes duplicate memories across queries."""
        memory_service = MagicMock()

        # Create shared memory that appears in multiple query results
        shared_memory = MemoryEntry(
            id="shared-mem-1",
            user_id="test-user",
            content="Shared knowledge",
            memory_type=MemoryType.FACT,
            importance=MemoryImportance.HIGH,
            keywords=[],
            tags=[],
            entities=[],
        )

        # Mock results with duplicates
        def mock_retrieve(user_id, context, **kwargs):
            if context == "query 1":
                return [
                    MemorySearchResult(memory=shared_memory, relevance_score=0.9, match_type="semantic"),
                    MemorySearchResult(
                        memory=MemoryEntry(
                            id="mem-unique-1",
                            user_id=user_id,
                            content="Unique to query 1",
                            memory_type=MemoryType.FACT,
                            importance=MemoryImportance.MEDIUM,
                            keywords=[],
                            tags=[],
                            entities=[],
                        ),
                        relevance_score=0.7,
                        match_type="semantic",
                    ),
                ]
            else:  # query 2
                return [
                    MemorySearchResult(memory=shared_memory, relevance_score=0.85, match_type="semantic"),
                    MemorySearchResult(
                        memory=MemoryEntry(
                            id="mem-unique-2",
                            user_id=user_id,
                            content="Unique to query 2",
                            memory_type=MemoryType.FACT,
                            importance=MemoryImportance.MEDIUM,
                            keywords=[],
                            tags=[],
                            entities=[],
                        ),
                        relevance_score=0.6,
                        match_type="semantic",
                    ),
                ]

        memory_service.retrieve_relevant = AsyncMock(side_effect=mock_retrieve)

        queries = ["query 1", "query 2"]

        results = await batch_retrieve_deduped(
            memory_service=memory_service,
            user_id="test-user",
            queries=queries,
            limit_total=10,
        )

        # Should have 3 unique memories (1 shared + 2 unique)
        assert len(results) == 3

        # Shared memory should appear only once with best score
        shared_results = [r for r in results if r.memory.id == "shared-mem-1"]
        assert len(shared_results) == 1
        assert shared_results[0].relevance_score == 0.9  # Higher score from query 1

    async def test_batch_retrieve_deduped_respects_limit(self):
        """Test deduplication respects total limit."""
        memory_service = MagicMock()

        def mock_retrieve(user_id, context, **kwargs):
            return [
                MemorySearchResult(
                    memory=MemoryEntry(
                        id=f"mem-{context}-{i}",
                        user_id=user_id,
                        content=f"Memory {i} for {context}",
                        memory_type=MemoryType.FACT,
                        importance=MemoryImportance.MEDIUM,
                        keywords=[],
                        tags=[],
                        entities=[],
                    ),
                    relevance_score=0.9 - i * 0.1,
                    match_type="semantic",
                )
                for i in range(10)
            ]

        memory_service.retrieve_relevant = AsyncMock(side_effect=mock_retrieve)

        queries = ["query 1", "query 2"]

        results = await batch_retrieve_deduped(
            memory_service=memory_service,
            user_id="test-user",
            queries=queries,
            limit_total=5,
        )

        # Should have exactly 5 results
        assert len(results) == 5

        # Should be sorted by score
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)
