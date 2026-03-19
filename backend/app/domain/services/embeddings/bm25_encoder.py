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
from inspect import isawaitable
from typing import ClassVar

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

    def __init__(self, top_k: int = 100, max_corpus_documents: int | None = None):
        """Initialize BM25 encoder.

        Args:
            top_k: Number of top-scoring indices to keep (default 100)
            max_corpus_documents: Sliding window size for retained corpus.
                When set (>0), only the latest N documents are kept.
        """
        self.bm25: BM25Okapi | None = None
        self.vocab: dict[str, int] = {}  # word -> index mapping
        self.reverse_vocab: dict[int, str] = {}  # index -> word mapping
        self.top_k = top_k
        self.max_corpus_documents = max(0, max_corpus_documents if max_corpus_documents is not None else 200)
        self.corpus_size = 0
        self._corpus_texts: list[str] = []  # Retained for incremental updates

    def _apply_corpus_window(self, corpus: list[str]) -> list[str]:
        """Apply sliding-window retention if max corpus size is configured."""
        if self.max_corpus_documents <= 0:
            return corpus
        if len(corpus) <= self.max_corpus_documents:
            return corpus
        return corpus[-self.max_corpus_documents :]

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
        text = re.sub(r"[^\w\s]", " ", text.lower())
        # Split on whitespace and filter empty strings
        return [t for t in text.split() if t]

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

        logger.debug("Built vocabulary with %d unique terms", len(self.vocab))

    def fit(self, corpus: list[str]) -> None:
        """Fit BM25 model on a corpus of documents.

        This should be called during initialization or when updating the corpus.
        For production, consider periodic retraining as corpus grows.

        Args:
            corpus: List of document strings
        """
        corpus = self._apply_corpus_window(corpus)

        if not corpus:
            logger.warning("Empty corpus provided to BM25 encoder")
            self.bm25 = None
            self.vocab = {}
            self.reverse_vocab = {}
            self.corpus_size = 0
            self._corpus_texts = []
            return

        # Tokenize corpus
        tokenized_corpus = [self._tokenize(doc) for doc in corpus]

        # Build vocabulary
        self._build_vocab(tokenized_corpus)

        # Fit BM25 model
        self.bm25 = BM25Okapi(tokenized_corpus)
        self.corpus_size = len(corpus)
        self._corpus_texts = list(corpus)  # Store for incremental updates

        logger.debug("BM25 encoder fitted on %d documents", self.corpus_size)

    # Seed corpus for lazy-fit: covers common query patterns in agent systems.
    # Provides minimal vocabulary so BM25 always produces non-empty sparse
    # vectors, even on first boot with empty memory. Real documents added
    # via update_corpus() / incremental update will improve quality.
    _SEED_CORPUS: ClassVar[list[str]] = [
        "user preference setting configuration",
        "search query web research information",
        "code implementation function class method",
        "error bug fix debug troubleshoot",
        "file document report summary analysis",
        "task plan step workflow process",
    ]

    def encode(self, text: str) -> dict[int, float]:
        """Generate sparse vector from text using BM25 document scores.

        Uses BM25Okapi.get_scores() to compute proper BM25 relevance scores
        across all corpus documents, then aggregates per-term IDF weights
        from the fitted model for the sparse vector representation.

        Lazy-fits on a seed corpus if unfitted to ensure non-empty results.

        Args:
            text: Query or document text

        Returns:
            Sparse vector as {index: score} dict with top-k non-zero entries
        """
        if self.bm25 is None:
            logger.info(
                "BM25 encoder unfitted — lazy-fitting on seed corpus (%d docs)",
                len(self._SEED_CORPUS),
            )
            self.fit(self._SEED_CORPUS)

        if self.bm25 is None:
            # fit() failed — graceful degradation
            return {}

        tokens = self._tokenize(text)
        if not tokens:
            return {}

        # Use BM25's actual per-term IDF values from the fitted model
        # bm25.idf is a dict mapping word -> IDF score computed during fit()
        term_scores: dict[int, float] = {}
        seen_tokens: set[str] = set()

        # Some terms can have IDF <= 0 (e.g. appears in ~50% of documents),
        # which should not erase the sparse signal entirely. Use a small
        # positive fallback derived from BM25's epsilon floor.
        fallback_idf = max(self.bm25.epsilon * self.bm25.average_idf, 1e-9)

        for token in tokens:
            if token in self.vocab and token not in seen_tokens:
                seen_tokens.add(token)
                idx = self.vocab[token]

                # Get actual IDF from BM25Okapi model and guard against
                # zero/negative values that would collapse sparse vectors.
                idf = float(self.bm25.idf.get(token, 0.0))
                if idf <= 0:
                    idf = fallback_idf

                # Weight by query term frequency * IDF
                tf = tokens.count(token)
                term_scores[idx] = float(tf * idf)

        if not term_scores:
            return {}

        # Keep only top-k scores
        sorted_scores = sorted(term_scores.items(), key=lambda x: -x[1])
        top_scores = dict(sorted_scores[: self.top_k])

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
        """Incrementally update BM25 model with new documents.

        Appends new documents to the existing corpus and refits.
        If corpus is empty or not fitted, just fits on new docs.

        Args:
            new_documents: New documents to add to corpus
        """
        if not new_documents:
            return

        logger.debug("Updating BM25 corpus with %d new documents", len(new_documents))

        # If BM25 is already fitted, rebuild with combined corpus
        # We reconstruct the old corpus from the vocabulary (approximate)
        # For a true incremental update, we'd need to store the original corpus
        if self.bm25 is not None and self._corpus_texts:
            combined = self._apply_corpus_window(self._corpus_texts + new_documents)
            self.fit(combined)
        else:
            self.fit(self._apply_corpus_window(new_documents))

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
        # Import settings at factory level (not in domain class) to maintain DDD boundary
        try:
            from app.core.config import get_settings

            max_docs = get_settings().bm25_corpus_max_documents
        except Exception:
            max_docs = 200
        _encoder = BM25SparseEncoder(top_k=100, max_corpus_documents=max_docs)
        logger.info("BM25 encoder singleton created (max_corpus=%d)", max_docs)
    return _encoder


async def initialize_bm25_from_memories(
    memory_repository,
    conversation_context_repository=None,
) -> None:
    """Initialize BM25 encoder from existing memories and conversation turns.

    This should be called on application startup to load the corpus
    from stored memories in MongoDB and recent conversation context from Qdrant.

    Args:
        memory_repository: MemoryRepository instance to fetch memories from
        conversation_context_repository: Optional ConversationContextRepository for recent turns
    """
    encoder = get_bm25_encoder()

    corpus: list[str] = []

    # Preferred repository contract
    get_all_content = getattr(memory_repository, "get_all_content", None)
    if callable(get_all_content):
        content_result = get_all_content(limit=10000)
        if isawaitable(content_result):
            content_result = await content_result
        if isinstance(content_result, list):
            corpus = [item for item in content_result if isinstance(item, str) and item]

    # Backwards-compatible fallback used by legacy tests/mocks
    if not corpus:
        find = getattr(memory_repository, "find", None)
        if callable(find):
            records = find()
            if isawaitable(records):
                records = await records
            if isinstance(records, list):
                corpus = [str(content) for item in records if (content := getattr(item, "content", ""))]

    # Include recent conversation context turns for keyword coverage
    if conversation_context_repository is not None:
        try:
            get_recent_content = getattr(conversation_context_repository, "get_all_content", None)
            if callable(get_recent_content):
                conv_content = get_recent_content(limit=5000)
                if isawaitable(conv_content):
                    conv_content = await conv_content
                if isinstance(conv_content, list):
                    conv_texts = [item for item in conv_content if isinstance(item, str) and item]
                    corpus.extend(conv_texts)
                    if conv_texts:
                        logger.info(f"Added {len(conv_texts)} conversation turns to BM25 corpus")
        except Exception:
            logger.debug("Failed to load conversation turns for BM25 corpus", exc_info=True)

    if not corpus:
        logger.info("No existing memories found, BM25 encoder will be trained on first write")
        return

    encoder.fit(corpus)

    logger.info(f"BM25 encoder initialized with {len(corpus)} documents (memories + conversation turns)")
