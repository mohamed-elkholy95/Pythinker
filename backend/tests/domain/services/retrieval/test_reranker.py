"""Tests for reranker backward-compatibility stub.

SelfHostedReranker has been removed (torch/sentence-transformers deps eliminated).
The module now exports a no-op stub for backward-compatible import paths.
"""

from app.domain.services.retrieval.reranker import get_reranker


class TestNoopReranker:
    """Test the no-op reranker stub."""

    def test_singleton_returns_instance(self):
        """get_reranker() returns the singleton no-op stub."""
        reranker = get_reranker()
        assert reranker is get_reranker()

    def test_is_available_returns_false(self):
        """No-op reranker is never available."""
        reranker = get_reranker()
        assert reranker.is_available() is False

    def test_rerank_returns_candidates_with_dummy_scores(self):
        """No-op reranker returns candidates unchanged with 0.5 score."""
        reranker = get_reranker()
        candidates = [
            ("Python is a programming language", {"id": "1"}),
            ("JavaScript for web dev", {"id": "2"}),
            ("ML with Python", {"id": "3"}),
        ]

        results = reranker.rerank(query="Python programming", candidates=candidates, top_k=2)

        assert len(results) == 2
        assert all(score == 0.5 for _, _, score in results)

    def test_rerank_empty_candidates(self):
        """No-op reranker handles empty candidates."""
        reranker = get_reranker()
        results = reranker.rerank(query="test", candidates=[], top_k=10)
        assert results == []
