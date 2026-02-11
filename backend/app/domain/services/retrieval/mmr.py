"""Maximal Marginal Relevance (MMR) diversification.

Phase 3: Client-side MMR implementation for diversifying search results
by balancing relevance to query with diversity from already-selected items.
"""

import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score (-1 to 1)
    """
    try:
        import numpy as np

        v1 = np.array(vec1)
        v2 = np.array(vec2)

        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)

        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0

        return float(dot_product / (norm_v1 * norm_v2))
    except ImportError:
        # Fallback without numpy
        logger.warning("numpy not available, using fallback cosine similarity")
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)


def mmr_rerank(
    query_embedding: list[float],
    candidates: list[T],
    embedding_fn: Callable[[T], list[float]],
    lambda_param: float = 0.5,
    top_k: int = 10,
) -> list[T]:
    """Maximal Marginal Relevance (MMR) diversification.

    Balances relevance to query with diversity from already-selected items.

    MMR formula:
    MMR = λ * sim(q, d) - (1 - λ) * max(sim(d, s) for s in selected)

    Where:
    - λ (lambda_param) controls relevance vs diversity trade-off
    - sim(q, d) is similarity between query and candidate
    - sim(d, s) is similarity between candidate and selected items

    Args:
        query_embedding: Query vector
        candidates: List of candidates to rerank
        embedding_fn: Function to extract embedding from candidate
        lambda_param: Trade-off between relevance (1.0) and diversity (0.0)
                     0.7 = favor relevance (default for accuracy)
                     0.5 = balanced
                     0.3 = favor diversity (useful for exploration)
        top_k: Number of results to return

    Returns:
        Diversified list of candidates, sorted by MMR score
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        return candidates

    selected: list[T] = []
    remaining = candidates.copy()

    while len(selected) < top_k and remaining:
        mmr_scores = []

        for candidate in remaining:
            try:
                cand_emb = embedding_fn(candidate)

                if not cand_emb:
                    # No embedding available, use low score
                    mmr_scores.append((0.0, candidate))
                    continue

                # Relevance to query
                relevance = cosine_similarity(query_embedding, cand_emb)

                # Max similarity to already-selected items
                if selected:
                    similarities = []
                    for s in selected:
                        s_emb = embedding_fn(s)
                        if s_emb:
                            sim = cosine_similarity(cand_emb, s_emb)
                            similarities.append(sim)

                    max_similarity = max(similarities) if similarities else 0.0
                else:
                    max_similarity = 0.0

                # MMR score: balance relevance and diversity
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_similarity
                mmr_scores.append((mmr_score, candidate))

            except Exception as e:
                logger.debug(f"MMR scoring failed for candidate: {e}")
                mmr_scores.append((0.0, candidate))

        if not mmr_scores:
            break

        # Select candidate with highest MMR score
        best = max(mmr_scores, key=lambda x: x[0])
        selected.append(best[1])
        remaining.remove(best[1])

    return selected
