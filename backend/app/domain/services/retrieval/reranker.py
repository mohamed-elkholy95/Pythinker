"""Self-hosted reranking using Sentence Transformers cross-encoder.

Phase 3: Improves retrieval quality by reranking search results with
a cross-encoder model that directly scores query-document pairs.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SelfHostedReranker:
    """Self-hosted cross-encoder reranker using Sentence Transformers.

    Uses a pre-trained cross-encoder model to rerank search results.
    Runs completely locally with no external API dependencies.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """Initialize reranker.

        Args:
            model_name: HuggingFace model ID (runs locally, no API calls)
                       Default: ms-marco-MiniLM-L-6-v2 (90MB, fast inference)
        """
        self.model_name = model_name
        self._model = None
        self._is_available = False

        # Try to load model
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(model_name)
            self._is_available = True
            logger.info(f"Reranker loaded: {model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Reranking disabled. "
                "Install with: pip install sentence-transformers torch"
            )
        except Exception as e:
            logger.warning(f"Failed to load reranker model: {e}. Reranking disabled.")

    def is_available(self) -> bool:
        """Check if reranker is available."""
        return self._is_available

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, dict[str, Any]]],  # (text, metadata)
        top_k: int = 10,
    ) -> list[tuple[str, dict[str, Any], float]]:
        """Rerank candidates using cross-encoder.

        Args:
            query: Search query
            candidates: List of (text, metadata) tuples
            top_k: Number of top results to return

        Returns:
            List of (text, metadata, rerank_score) tuples, sorted by score
        """
        if not self._is_available or not self._model:
            # Reranking not available, return candidates with dummy scores
            logger.debug("Reranker not available, returning candidates unchanged")
            return [(text, meta, 0.5) for text, meta in candidates[:top_k]]

        if not candidates:
            return []

        # Prepare pairs for cross-encoder
        pairs = [(query, text) for text, _ in candidates]

        # Get rerank scores
        scores = self._model.predict(pairs)

        # Combine with metadata and sort
        results = [(text, meta, float(score)) for (text, meta), score in zip(candidates, scores, strict=False)]
        results.sort(key=lambda x: x[2], reverse=True)

        return results[:top_k]


# Singleton instance
_reranker: SelfHostedReranker | None = None


def get_reranker() -> SelfHostedReranker:
    """Get singleton reranker instance."""
    global _reranker
    if _reranker is None:
        _reranker = SelfHostedReranker()
    return _reranker
