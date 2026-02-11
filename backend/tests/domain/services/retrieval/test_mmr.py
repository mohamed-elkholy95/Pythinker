"""Tests for MMR diversification.

Phase 3: Tests Maximal Marginal Relevance diversification.
"""

import pytest

from app.domain.services.retrieval.mmr import cosine_similarity, mmr_rerank


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        vec = [1.0, 0.5, 0.3]
        similarity = cosine_similarity(vec, vec)

        assert pytest.approx(similarity, abs=0.01) == 1.0

    def test_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = cosine_similarity(vec1, vec2)

        assert pytest.approx(similarity, abs=0.01) == 0.0

    def test_opposite_vectors(self):
        """Test cosine similarity of opposite vectors."""
        vec1 = [1.0, 0.5, 0.3]
        vec2 = [-1.0, -0.5, -0.3]
        similarity = cosine_similarity(vec1, vec2)

        assert pytest.approx(similarity, abs=0.01) == -1.0

    def test_zero_vector(self):
        """Test cosine similarity with zero vector."""
        vec1 = [1.0, 0.5]
        vec2 = [0.0, 0.0]
        similarity = cosine_similarity(vec1, vec2)

        assert similarity == 0.0


class DummyCandidate:
    """Dummy candidate for testing MMR."""

    def __init__(self, embedding: list[float], content: str):
        self.embedding = embedding
        self.content = content


class TestMMRRerank:
    """Test MMR diversification algorithm."""

    def test_mmr_returns_top_k(self):
        """Test MMR returns exactly top_k results."""
        query_embedding = [1.0, 0.0, 0.0]
        candidates = [
            DummyCandidate([1.0, 0.1, 0.0], "doc1"),
            DummyCandidate([1.0, 0.2, 0.0], "doc2"),
            DummyCandidate([1.0, 0.3, 0.0], "doc3"),
            DummyCandidate([1.0, 0.4, 0.0], "doc4"),
            DummyCandidate([1.0, 0.5, 0.0], "doc5"),
        ]

        results = mmr_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            embedding_fn=lambda c: c.embedding,
            lambda_param=0.5,
            top_k=3,
        )

        assert len(results) == 3

    def test_mmr_balances_relevance_and_diversity(self):
        """Test MMR balances relevance vs diversity with lambda."""
        query_embedding = [1.0, 0.0, 0.0]

        # Create candidates with varying relevance and diversity
        candidates = [
            DummyCandidate([1.0, 0.0, 0.0], "most_relevant_but_similar"),
            DummyCandidate([0.9, 0.0, 0.0], "relevant_and_similar"),
            DummyCandidate([0.5, 0.5, 0.0], "less_relevant_but_diverse"),
            DummyCandidate([0.0, 1.0, 0.0], "least_relevant_most_diverse"),
        ]

        # High lambda (favor relevance)
        results_relevant = mmr_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            embedding_fn=lambda c: c.embedding,
            lambda_param=0.9,  # Favor relevance
            top_k=3,
        )

        # Low lambda (favor diversity)
        results_diverse = mmr_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            embedding_fn=lambda c: c.embedding,
            lambda_param=0.1,  # Favor diversity
            top_k=3,
        )

        # Results should be different
        assert results_relevant != results_diverse

        # High lambda should prioritize more relevant items
        # (items with embeddings closer to [1.0, 0.0, 0.0])
        assert results_relevant[0].content in ["most_relevant_but_similar", "relevant_and_similar"]

        # Low lambda should include more diverse items
        # (items with embeddings further from [1.0, 0.0, 0.0])
        diverse_contents = [r.content for r in results_diverse]
        assert any("diverse" in content for content in diverse_contents)

    def test_mmr_empty_candidates(self):
        """Test MMR handles empty candidates."""
        query_embedding = [1.0, 0.0]
        candidates = []

        results = mmr_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            embedding_fn=lambda c: c.embedding,
            top_k=5,
        )

        assert results == []

    def test_mmr_fewer_candidates_than_top_k(self):
        """Test MMR when candidates < top_k."""
        query_embedding = [1.0, 0.0]
        candidates = [
            DummyCandidate([1.0, 0.0], "doc1"),
            DummyCandidate([0.5, 0.5], "doc2"),
        ]

        results = mmr_rerank(
            query_embedding=query_embedding,
            candidates=candidates,
            embedding_fn=lambda c: c.embedding,
            top_k=5,
        )

        assert len(results) == 2  # Returns all candidates
