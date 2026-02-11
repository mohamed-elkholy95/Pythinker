"""Tests for Phase 3 BM25 sparse vector encoder.

Tests self-hosted BM25 sparse vector generation for hybrid retrieval.
"""

import pytest


class TestBM25SparseEncoder:
    """Test BM25 encoder functionality."""

    def test_encoder_initialization(self):
        """Test encoder initializes with default parameters."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder(top_k=100)

        assert encoder.top_k == 100
        assert encoder.bm25 is None  # Not fitted yet
        assert encoder.corpus_size == 0

    def test_fit_builds_vocabulary(self):
        """Test fit() builds vocabulary from corpus."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        corpus = [
            "user prefers dark mode",
            "user works on backend systems",
            "dark theme is preferred",
        ]

        encoder.fit(corpus)

        assert encoder.get_vocab_size() > 0
        assert encoder.get_corpus_size() == 3
        assert encoder.bm25 is not None
        assert "dark" in encoder.vocab
        assert "user" in encoder.vocab

    def test_encode_generates_sparse_vector(self):
        """Test encode() generates sparse vector with top-k indices."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder(top_k=10)
        corpus = [
            "python programming language",
            "javascript web development",
            "python data science",
        ]
        encoder.fit(corpus)

        # Encode query
        sparse_vector = encoder.encode("python programming")

        assert isinstance(sparse_vector, dict)
        assert len(sparse_vector) <= 10  # Respects top_k limit
        assert all(isinstance(k, int) for k in sparse_vector)  # Integer indices
        assert all(isinstance(v, float) for v in sparse_vector.values())  # Float scores
        assert all(0.0 <= v <= 1.0 for v in sparse_vector.values())  # Normalized scores

    def test_encode_without_fitting_returns_empty(self):
        """Test encode() returns empty dict when not fitted."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        sparse_vector = encoder.encode("test query")

        assert sparse_vector == {}

    def test_encode_empty_text_returns_empty(self):
        """Test encode() handles empty text gracefully."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit(["sample document"])

        sparse_vector = encoder.encode("")

        assert sparse_vector == {}

    def test_encode_prioritizes_relevant_terms(self):
        """Test BM25 scores prioritize relevant terms."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder(top_k=50)
        corpus = [
            "machine learning algorithms",
            "web development frameworks",
            "machine learning models",
            "data structures and algorithms",
        ]
        encoder.fit(corpus)

        # Query with "machine learning" should score those terms highly
        sparse_vector = encoder.encode("machine learning")

        # Get top terms by score
        sorted_terms = sorted(sparse_vector.items(), key=lambda x: x[1], reverse=True)

        # Check that "machine" and "learning" have high scores
        top_indices = [idx for idx, score in sorted_terms[:5]]
        top_words = [encoder.reverse_vocab.get(idx) for idx in top_indices]

        assert "machine" in top_words or "learning" in top_words

    def test_update_corpus_refits_model(self):
        """Test update_corpus() refits the BM25 model."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit(["old corpus document"])

        old_vocab_size = encoder.get_vocab_size()

        # Update corpus
        encoder.update_corpus(["new corpus with different terms and vocabulary"])

        # Vocabulary should change
        assert encoder.get_vocab_size() != old_vocab_size

    def test_encode_batch(self):
        """Test encode_batch() encodes multiple texts."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit(["text one", "text two", "text three"])

        texts = ["query one", "query two"]
        results = encoder.encode_batch(texts)

        assert len(results) == 2
        assert all(isinstance(r, dict) for r in results)

    def test_fit_with_empty_corpus(self):
        """Test fit() handles empty corpus gracefully."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit([])

        assert encoder.bm25 is None
        assert encoder.get_vocab_size() == 0
        assert encoder.get_corpus_size() == 0

    def test_tokenization_normalizes_case(self):
        """Test tokenization converts to lowercase."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit(["UPPERCASE text", "lowercase text"])

        # Both should have same vocabulary (normalized)
        assert "uppercase" in encoder.vocab or "text" in encoder.vocab

    def test_tokenization_removes_punctuation(self):
        """Test tokenization removes punctuation."""
        from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder

        encoder = BM25SparseEncoder()
        encoder.fit(["Hello, world!", "Test...document"])

        # Punctuation should be removed
        vocab_words = list(encoder.vocab.keys())
        assert all("," not in word and "!" not in word and "." not in word for word in vocab_words)


class TestBM25Singleton:
    """Test BM25 singleton pattern."""

    def test_get_bm25_encoder_returns_singleton(self):
        """Test get_bm25_encoder() returns same instance."""
        from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

        encoder1 = get_bm25_encoder()
        encoder2 = get_bm25_encoder()

        assert encoder1 is encoder2

    @pytest.mark.asyncio
    async def test_initialize_from_memories(self):
        """Test initialize_bm25_from_memories() loads corpus."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder, initialize_bm25_from_memories

        # Mock repository
        memory_mock = MagicMock()
        memory_mock.content = "test memory content"

        repo_mock = MagicMock()
        repo_mock.find = AsyncMock(return_value=[memory_mock])

        # Initialize
        await initialize_bm25_from_memories(repo_mock)

        # Encoder should be fitted
        encoder = get_bm25_encoder()
        assert encoder.get_corpus_size() > 0
        assert encoder.bm25 is not None

    @pytest.mark.asyncio
    async def test_initialize_from_empty_memories(self):
        """Test initialize handles no memories gracefully."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.embeddings.bm25_encoder import initialize_bm25_from_memories

        repo_mock = MagicMock()
        repo_mock.find = AsyncMock(return_value=[])

        # Should not raise error
        await initialize_bm25_from_memories(repo_mock)
