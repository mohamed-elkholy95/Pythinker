"""Tests for Phase 3 hybrid retrieval components.

Tests reranker, MMR diversification, and batched retrieval.
"""

import pytest


class TestSelfHostedReranker:
    """Test self-hosted cross-encoder reranker."""

    def test_reranker_initialization(self):
        """Test reranker initializes correctly."""
        from app.domain.services.retrieval.reranker import SelfHostedReranker

        reranker = SelfHostedReranker()

        assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def test_rerank_without_model_returns_unchanged(self):
        """Test reranker returns candidates when model unavailable."""
        from app.domain.services.retrieval.reranker import SelfHostedReranker

        reranker = SelfHostedReranker()
        reranker._is_available = False  # Simulate unavailable model

        candidates = [("doc1", {"id": "1"}), ("doc2", {"id": "2"})]
        results = reranker.rerank("query", candidates, top_k=2)

        assert len(results) == 2
        assert all(len(r) == 3 for r in results)  # (text, meta, score)

    def test_rerank_empty_candidates(self):
        """Test reranker handles empty candidates."""
        from app.domain.services.retrieval.reranker import SelfHostedReranker

        reranker = SelfHostedReranker()
        results = reranker.rerank("query", [], top_k=10)

        assert results == []

    def test_get_reranker_singleton(self):
        """Test get_reranker() returns singleton instance."""
        from app.domain.services.retrieval.reranker import get_reranker

        reranker1 = get_reranker()
        reranker2 = get_reranker()

        assert reranker1 is reranker2


class TestMMRDiversification:
    """Test Maximal Marginal Relevance diversification."""

    def test_mmr_empty_candidates(self):
        """Test MMR handles empty candidate list."""
        from app.domain.services.retrieval.mmr import mmr_rerank

        query_emb = [1.0, 0.0, 0.0]
        result = mmr_rerank(query_emb, [], lambda x: x, top_k=5)

        assert result == []

    def test_mmr_fewer_candidates_than_top_k(self):
        """Test MMR returns all candidates when fewer than top_k."""
        from app.domain.services.retrieval.mmr import mmr_rerank

        query_emb = [1.0, 0.0, 0.0]
        candidates = [[0.9, 0.1, 0.0], [0.8, 0.2, 0.0]]

        result = mmr_rerank(query_emb, candidates, lambda x: x, top_k=5)

        assert len(result) == 2

    def test_mmr_selects_top_k_candidates(self):
        """Test MMR selects exactly top_k candidates."""
        from app.domain.services.retrieval.mmr import mmr_rerank

        query_emb = [1.0, 0.0, 0.0]
        candidates = [[0.9, 0.1, 0.0], [0.8, 0.2, 0.0], [0.7, 0.3, 0.0], [0.6, 0.4, 0.0]]

        result = mmr_rerank(query_emb, candidates, lambda x: x, lambda_param=0.7, top_k=2)

        assert len(result) == 2

    def test_mmr_lambda_affects_selection(self):
        """Test lambda parameter affects relevance vs diversity balance."""
        from app.domain.services.retrieval.mmr import mmr_rerank

        query_emb = [1.0, 0.0, 0.0]
        # Two very similar candidates + one dissimilar
        candidates = [
            [0.95, 0.05, 0.0],  # Very relevant, similar to each other
            [0.94, 0.06, 0.0],
            [0.5, 0.0, 0.5],  # Less relevant, but diverse
        ]

        # High lambda (favor relevance): should pick both similar candidates
        relevance_result = mmr_rerank(query_emb, candidates, lambda x: x, lambda_param=0.9, top_k=2)

        # Low lambda (favor diversity): should pick one similar + one diverse
        diversity_result = mmr_rerank(query_emb, candidates, lambda x: x, lambda_param=0.3, top_k=2)

        # Results should differ based on lambda
        assert len(relevance_result) == 2
        assert len(diversity_result) == 2

    def test_cosine_similarity(self):
        """Test cosine similarity computation."""
        from app.domain.services.retrieval.mmr import cosine_similarity

        # Identical vectors
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

        # Orthogonal vectors
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

        # Opposite vectors
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity handles zero vectors."""
        from app.domain.services.retrieval.mmr import cosine_similarity

        result = cosine_similarity([0.0, 0.0], [1.0, 1.0])

        assert result == 0.0


class TestBatchedRetrieval:
    """Test batched parallel retrieval."""

    @pytest.mark.asyncio
    async def test_batch_retrieve_empty_queries(self):
        """Test batch_retrieve handles empty query list."""
        from unittest.mock import MagicMock

        from app.domain.services.retrieval.batch_retrieval import batch_retrieve

        memory_service_mock = MagicMock()

        result = await batch_retrieve(memory_service_mock, "user-123", [], limit_per_query=5)

        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_retrieve_multiple_queries(self):
        """Test batch_retrieve executes queries in parallel."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.retrieval.batch_retrieval import batch_retrieve

        memory_service_mock = MagicMock()
        memory_service_mock.retrieve_relevant = AsyncMock(return_value=[MagicMock()])

        queries = ["query1", "query2", "query3"]
        result = await batch_retrieve(memory_service_mock, "user-123", queries, limit_per_query=5)

        assert len(result) == 3
        assert "query1" in result
        assert "query2" in result
        assert "query3" in result

        # Verify retrieve_relevant was called for each query
        assert memory_service_mock.retrieve_relevant.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_retrieve_handles_failures_gracefully(self):
        """Test batch_retrieve continues despite individual query failures."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.retrieval.batch_retrieval import batch_retrieve

        memory_service_mock = MagicMock()

        # First call succeeds, second fails, third succeeds
        memory_service_mock.retrieve_relevant = AsyncMock(side_effect=[
            [MagicMock()],  # Success
            Exception("Retrieval error"),  # Failure
            [MagicMock()],  # Success
        ])

        queries = ["query1", "query2", "query3"]
        result = await batch_retrieve(memory_service_mock, "user-123", queries)

        # Should return results for successful queries
        assert "query1" in result
        assert "query2" in result  # Failed query returns empty list
        assert "query3" in result

    @pytest.mark.asyncio
    async def test_batch_retrieve_deduped(self):
        """Test batch_retrieve_deduped removes duplicates across queries."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.retrieval.batch_retrieval import batch_retrieve_deduped

        # Create mock memories with IDs
        memory1 = MagicMock()
        memory1.id = "mem-1"

        memory2 = MagicMock()
        memory2.id = "mem-2"

        # Same memory returned by multiple queries
        result1 = MagicMock()
        result1.memory = memory1
        result1.relevance_score = 0.8

        result2 = MagicMock()
        result2.memory = memory1  # Duplicate
        result2.relevance_score = 0.9  # Higher score

        result3 = MagicMock()
        result3.memory = memory2
        result3.relevance_score = 0.7

        memory_service_mock = MagicMock()
        memory_service_mock.retrieve_relevant = AsyncMock(side_effect=[
            [result1, result3],  # Query 1
            [result2],  # Query 2 (has duplicate of mem-1)
        ])

        queries = ["query1", "query2"]
        deduped = await batch_retrieve_deduped(memory_service_mock, "user-123", queries, limit_total=10)

        # Should have 2 unique memories (mem-1 and mem-2)
        assert len(deduped) == 2

        # mem-1 should have higher score (0.9, not 0.8)
        mem1_result = next(r for r in deduped if r.memory.id == "mem-1")
        assert mem1_result.relevance_score == 0.9
