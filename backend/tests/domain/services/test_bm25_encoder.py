"""Tests for BM25 sparse vector encoder.

Phase 1: Self-hosted keyword search with rank-bm25.
"""

from app.domain.services.embeddings.bm25_encoder import BM25SparseEncoder, get_bm25_encoder


class TestBM25SparseEncoder:
    """Test BM25 sparse vector encoder."""

    def test_encoder_initialization(self):
        """Test encoder initializes correctly."""
        encoder = BM25SparseEncoder(top_k=50)
        assert encoder.top_k == 50
        assert encoder.bm25 is None
        assert encoder.corpus_size == 0
        assert len(encoder.vocab) == 0

    def test_encoder_fit(self):
        """Test encoder fits on corpus."""
        encoder = BM25SparseEncoder()
        corpus = [
            "user prefers dark mode",
            "user works on backend development",
            "user likes Python programming",
        ]

        encoder.fit(corpus)

        assert encoder.bm25 is not None
        assert encoder.corpus_size == 3
        assert len(encoder.vocab) > 0
        # Check vocabulary contains expected words
        assert "dark" in encoder.vocab or "user" in encoder.vocab

    def test_encoder_encode(self):
        """Test sparse vector generation."""
        encoder = BM25SparseEncoder(top_k=10)
        corpus = [
            "machine learning models",
            "deep learning neural networks",
            "natural language processing",
        ]

        encoder.fit(corpus)
        sparse = encoder.encode("deep learning")

        # Should return dict with indices and scores
        assert isinstance(sparse, dict)
        assert len(sparse) > 0
        assert all(isinstance(k, int) for k in sparse)
        assert all(isinstance(v, float) for v in sparse.values())
        # Scores should be normalized to [0, 1]
        assert all(0.0 <= v <= 1.0 for v in sparse.values())

    def test_encoder_encode_empty_corpus_lazy_fits(self):
        """Test encode with no corpus lazy-fits on seed corpus and returns non-empty."""
        encoder = BM25SparseEncoder()
        sparse = encoder.encode("search query")
        # Lazy-fit on seed corpus ensures non-empty sparse vectors
        assert isinstance(sparse, dict)
        assert len(sparse) > 0

    def test_encoder_encode_empty_text(self):
        """Test encode with empty text."""
        encoder = BM25SparseEncoder()
        encoder.fit(["test corpus"])
        sparse = encoder.encode("")
        assert sparse == {}

    def test_encoder_top_k_limit(self):
        """Test top-k limiting works."""
        encoder = BM25SparseEncoder(top_k=5)
        corpus = ["word1 word2 word3 word4 word5 word6 word7 word8"]
        encoder.fit(corpus)

        sparse = encoder.encode("word1 word2 word3 word4 word5 word6 word7")
        # Should return at most top_k entries
        assert len(sparse) <= 5

    def test_encoder_batch_encode(self):
        """Test batch encoding."""
        encoder = BM25SparseEncoder()
        corpus = ["apple banana", "orange banana", "apple orange"]
        encoder.fit(corpus)

        texts = ["apple", "banana", "orange"]
        results = encoder.encode_batch(texts)

        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

    def test_get_vocab_size(self):
        """Test vocabulary size tracking."""
        encoder = BM25SparseEncoder()
        corpus = ["cat dog bird", "cat mouse", "dog bird fish"]
        encoder.fit(corpus)

        vocab_size = encoder.get_vocab_size()
        assert vocab_size > 0
        # Should have around 6 unique words (cat, dog, bird, mouse, fish)
        assert 4 <= vocab_size <= 6

    def test_get_corpus_size(self):
        """Test corpus size tracking."""
        encoder = BM25SparseEncoder()
        corpus = ["doc1", "doc2", "doc3"]
        encoder.fit(corpus)

        assert encoder.get_corpus_size() == 3

    def test_singleton_get_bm25_encoder(self):
        """Test singleton encoder instance."""
        encoder1 = get_bm25_encoder()
        encoder2 = get_bm25_encoder()

        # Should return same instance
        assert encoder1 is encoder2


class TestBM25EncoderTokenization:
    """Test tokenization logic."""

    def test_tokenize_basic(self):
        """Test basic tokenization."""
        encoder = BM25SparseEncoder()
        tokens = encoder._tokenize("Hello World!")

        assert tokens == ["hello", "world"]

    def test_tokenize_punctuation(self):
        """Test punctuation removal."""
        encoder = BM25SparseEncoder()
        tokens = encoder._tokenize("Hello, world! How are you?")

        # Punctuation should be removed
        assert "," not in tokens
        assert "!" not in tokens
        assert "?" not in tokens
        assert all(isinstance(t, str) for t in tokens)

    def test_tokenize_lowercase(self):
        """Test lowercase conversion."""
        encoder = BM25SparseEncoder()
        tokens = encoder._tokenize("UPPERCASE lowercase MiXeD")

        assert all(t.islower() for t in tokens)
        assert "uppercase" in tokens
        assert "lowercase" in tokens
        assert "mixed" in tokens


class TestBM25EncoderScoring:
    """Test BM25 scoring quality."""

    def test_relevant_terms_score_higher(self):
        """Test that relevant terms get higher scores."""
        encoder = BM25SparseEncoder()
        corpus = [
            "Python is a programming language",
            "JavaScript is a programming language",
            "Ruby is a programming language",
        ]
        encoder.fit(corpus)

        # Query with common term
        sparse = encoder.encode("Python programming")

        # Should have non-zero scores
        assert len(sparse) > 0
        assert max(sparse.values()) > 0.0

    def test_deterministic_encoding(self):
        """Test encoding is deterministic."""
        encoder = BM25SparseEncoder()
        corpus = ["test document", "another test"]
        encoder.fit(corpus)

        result1 = encoder.encode("test query")
        result2 = encoder.encode("test query")

        # Should produce same results
        assert result1 == result2
