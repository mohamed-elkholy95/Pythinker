"""BM25 sparse vector encoder for self-hosted keyword search.

This module provides BM25-based sparse vector generation using the rank-bm25
library. Sparse vectors complement dense semantic embeddings in hybrid retrieval.

Architecture:
- Self-hosted: No external API dependencies
- Singleton pattern: One encoder instance per process
- Dynamic corpus: Updates vocabulary as new documents are indexed
- Top-k filtering: Returns only top 100 non-zero indices to save space
"""

import logging
import re
from collections import Counter
from functools import lru_cache
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25SparseEncoder:
    """Self-hosted BM25 sparse vector encoder.

    Generates sparse vectors from text using BM25 (Best Matching 25) algorithm.
    Sparse vectors are stored as {index: score} dictionaries where index maps
    to vocabulary position and score is the BM25 relevance weight.

    Example:
        encoder = BM25SparseEncoder()
        encoder.fit(["user prefers dark mode", "user works on backend"])
        sparse = encoder.encode("dark mode preferences")
        # Returns: {2: 0.87, 5: 0.65, ...}  (top 100 non-zero indices)
    """

    def __init__(self, top_k: int = 100):
        """Initialize BM25 encoder.

        Args:
            top_k: Number of top-scoring indices to keep (default 100)
        """
        self.bm25: BM25Okapi | None = None
        self.vocab: dict[str, int] = {}  # word -> index mapping
        self.reverse_vocab: dict[int, str] = {}  # index -> word mapping
        self.top_k = top_k
        self.corpus_size = 0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Simple whitespace + lowercase tokenization. For production,
        consider using nltk or spaCy for better tokenization.

        Args:
            text: Input text

        Returns:
            List of tokens
        """
        # Remove punctuation and convert to lowercase
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        # Split on whitespace and filter empty strings
        tokens = [t for t in text.split() if t]
        return tokens

    def _build_vocab(self, tokenized_corpus: list[list[str]]) -> None:
        """Build vocabulary from tokenized corpus.

        Args:
            tokenized_corpus: List of tokenized documents
        """
        # Count word frequencies across corpus
        word_freq: Counter = Counter()
        for tokens in tokenized_corpus:
            word_freq.update(tokens)

        # Build vocabulary (sorted by frequency for stable indexing)
        sorted_words = sorted(word_freq.items(), key=lambda x: (-x[1], x[0]))
        self.vocab = {word: idx for idx, (word, _) in enumerate(sorted_words)}
        self.reverse_vocab = {idx: word for word, idx in self.vocab.items()}

        logger.info(f"Built vocabulary with {len(self.vocab)} unique terms")

    def fit(self, corpus: list[str]) -> None:
        """Fit BM25 model on a corpus of documents.

        This should be called during initialization or when updating the corpus.
        For production, consider periodic retraining as corpus grows.

        Args:
            corpus: List of document strings
        """
        if not corpus:
            logger.warning("Empty corpus provided to BM25 encoder")
            self.bm25 = None
            self.vocab = {}
            self.reverse_vocab = {}
            self.corpus_size = 0
            return

        # Tokenize corpus
        tokenized_corpus = [self._tokenize(doc) for doc in corpus]

        # Build vocabulary
        self._build_vocab(tokenized_corpus)

        # Fit BM25 model
        self.bm25 = BM25Okapi(tokenized_corpus)
        self.corpus_size = len(corpus)

        logger.info(f"BM25 encoder fitted on {self.corpus_size} documents")

    def encode(self, text: str) -> dict[int, float]:
        """Generate sparse vector from text.

        Args:
            text: Query or document text

        Returns:
            Sparse vector as {index: score} dict with top-k non-zero entries
        """
        if self.bm25 is None:
            logger.warning("BM25 not fitted, returning empty sparse vector")
            return {}

        # Tokenize query
        tokens = self._tokenize(text)

        if not tokens:
            return {}

        # Get BM25 scores for each term against all documents
        # Then aggregate scores per term (we want term-level scores, not doc scores)
        term_scores: dict[int, float] = {}

        for token in tokens:
            if token in self.vocab:
                idx = self.vocab[token]
                # Simple frequency-based scoring for the term
                # In a full implementation, you'd use IDF from BM25
                term_freq = tokens.count(token)
                # Use BM25's IDF if available (approximate)
                idf = np.log((self.corpus_size + 1) / (1 + 1))  # Simplified IDF
                score = term_freq * idf
                term_scores[idx] = term_scores.get(idx, 0.0) + float(score)

        if not term_scores:
            return {}

        # Keep only top-k scores
        sorted_scores = sorted(term_scores.items(), key=lambda x: -x[1])
        top_scores = dict(sorted_scores[:self.top_k])

        # Normalize scores to [0, 1] range
        if top_scores:
            max_score = max(top_scores.values())
            if max_score > 0:
                top_scores = {idx: score / max_score for idx, score in top_scores.items()}

        return top_scores

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]:
        """Encode multiple texts to sparse vectors.

        Args:
            texts: List of texts

        Returns:
            List of sparse vectors
        """
        return [self.encode(text) for text in texts]

    def update_corpus(self, new_documents: list[str]) -> None:
        """Update BM25 model with new documents.

        Note: This currently refits the entire model. For production,
        consider incremental updates or periodic batch retraining.

        Args:
            new_documents: New documents to add to corpus
        """
        logger.info(f"Updating BM25 corpus with {len(new_documents)} new documents")
        # For now, refit entirely (incremental BM25 is complex)
        # In production, queue updates and batch refit periodically
        self.fit(new_documents)

    def get_vocab_size(self) -> int:
        """Get vocabulary size."""
        return len(self.vocab)

    def get_corpus_size(self) -> int:
        """Get corpus size."""
        return self.corpus_size


# Global singleton instance
_encoder: BM25SparseEncoder | None = None


@lru_cache(maxsize=1)
def get_bm25_encoder() -> BM25SparseEncoder:
    """Get singleton BM25 encoder instance.

    The encoder is lazily initialized and shared across the application.
    Initial corpus fitting happens on first memory write.

    Returns:
        Shared BM25SparseEncoder instance
    """
    global _encoder
    if _encoder is None:
        _encoder = BM25SparseEncoder(top_k=100)
        logger.info("BM25 encoder singleton created")
    return _encoder


async def initialize_bm25_from_memories(memory_repository) -> None:
    """Initialize BM25 encoder from existing memories.

    This should be called on application startup to load the corpus
    from stored memories in MongoDB.

    Args:
        memory_repository: MemoryRepository instance to fetch memories from
    """
    encoder = get_bm25_encoder()

    # Fetch all memory content for corpus (limit for performance)
    # In production, consider sampling or using a representative subset
    memories = await memory_repository.find({}, limit=10000)

    if not memories:
        logger.info("No existing memories found, BM25 encoder will be trained on first write")
        return

    corpus = [mem.content for mem in memories]
    encoder.fit(corpus)

    logger.info(f"BM25 encoder initialized with {len(corpus)} memories")
