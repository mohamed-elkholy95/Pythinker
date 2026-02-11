"""Tests for self-hosted reranker.

Phase 3: Tests cross-encoder reranking functionality.
"""

import pytest

from app.domain.services.retrieval.reranker import SelfHostedReranker, get_reranker


class TestSelfHostedReranker:
    """Test self-hosted reranker functionality."""

    def test_reranker_initialization(self):
        """Test reranker can be initialized."""
        reranker = SelfHostedReranker()

        assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        # Check availability (may fail if sentence-transformers not installed)
        # This is OK - reranker should gracefully degrade

    def test_reranker_graceful_degradation(self):
        """Test reranker returns results even if not available."""
        reranker = SelfHostedReranker()

        candidates = [
            ("Python is a programming language", {"id": "1"}),
            ("JavaScript is used for web development", {"id": "2"}),
            ("Machine learning with Python", {"id": "3"}),
        ]

        results = reranker.rerank(query="Python programming", candidates=candidates, top_k=2)

        # Should return results even if model not loaded
        assert len(results) <= 2
        assert all(len(r) == 3 for r in results)  # (text, metadata, score)

    def test_reranker_singleton(self):
        """Test reranker singleton pattern."""
        reranker1 = get_reranker()
        reranker2 = get_reranker()

        assert reranker1 is reranker2

    def test_reranker_empty_candidates(self):
        """Test reranker handles empty candidates."""
        reranker = SelfHostedReranker()

        results = reranker.rerank(query="test query", candidates=[], top_k=10)

        assert results == []

    @pytest.mark.skipif(
        not SelfHostedReranker().is_available(),
        reason="sentence-transformers not installed",
    )
    def test_reranker_scoring(self):
        """Test reranker actually scores and ranks candidates."""
        reranker = SelfHostedReranker()

        candidates = [
            ("The quick brown fox jumps over the lazy dog", {"id": "1"}),
            ("Python is a high-level programming language", {"id": "2"}),
            ("Machine learning with neural networks", {"id": "3"}),
        ]

        results = reranker.rerank(query="Python programming language", candidates=candidates, top_k=3)

        # Should have 3 results
        assert len(results) == 3

        # Scores should be in descending order
        scores = [score for _, _, score in results]
        assert scores == sorted(scores, reverse=True)

        # Python-related candidate should rank higher
        top_text = results[0][0]
        assert "Python" in top_text or "programming" in top_text
