"""Maximal Marginal Relevance (MMR) diversification.

Phase 3: Client-side MMR implementation for diversifying search results
by balancing relevance to query with diversity from already-selected items.

Uses numpy vectorized operations for efficient cosine similarity computation.
"""

import logging
from collections.abc import Callable
from typing import TypeVar

import numpy as np

logger = logging.getLogger(__name__)

T = TypeVar("T")


def cosine_similarity_matrix(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a query and all candidates vectorized.

    Args:
        query: Query vector (1D array of shape [d])
        candidates: Candidate matrix (2D array of shape [n, d])

    Returns:
        Similarity scores array of shape [n]
    """
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(len(candidates))

    cand_norms = np.linalg.norm(candidates, axis=1)
    # Avoid division by zero
    safe_norms = np.where(cand_norms == 0, 1.0, cand_norms)
    dots = candidates @ query
    return dots / (safe_norms * query_norm)


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

    # Pre-extract all embeddings and build numpy matrix
    query_vec = np.array(query_embedding, dtype=np.float32)
    embeddings: list[np.ndarray] = []
    valid_mask: list[bool] = []

    for c in candidates:
        try:
            emb = embedding_fn(c)
            if emb:
                embeddings.append(np.array(emb, dtype=np.float32))
                valid_mask.append(True)
            else:
                embeddings.append(np.zeros_like(query_vec))
                valid_mask.append(False)
        except Exception as e:
            logger.debug(f"Failed to extract embedding: {e}")
            embeddings.append(np.zeros_like(query_vec))
            valid_mask.append(False)

    cand_matrix = np.vstack(embeddings)  # shape [n, d]

    # Pre-compute relevance scores (query vs all candidates)
    relevance_scores = cosine_similarity_matrix(query_vec, cand_matrix)

    # Greedy MMR selection
    n = len(candidates)
    selected_indices: list[int] = []
    remaining = set(range(n))

    for _ in range(min(top_k, n)):
        if not remaining:
            break

        best_idx = -1
        best_score = float("-inf")

        remaining_list = sorted(remaining)

        if not selected_indices:
            # First iteration: pick highest relevance
            for idx in remaining_list:
                score = lambda_param * relevance_scores[idx] if valid_mask[idx] else 0.0
                if score > best_score:
                    best_score = score
                    best_idx = idx
        else:
            # Compute max similarity to selected set (vectorized)
            selected_matrix = cand_matrix[selected_indices]  # shape [k, d]
            for idx in remaining_list:
                if not valid_mask[idx]:
                    score = 0.0
                else:
                    # Vectorized similarity of this candidate vs all selected
                    sims = cosine_similarity_matrix(cand_matrix[idx], selected_matrix)
                    max_sim = float(np.max(sims)) if len(sims) > 0 else 0.0
                    score = lambda_param * relevance_scores[idx] - (1 - lambda_param) * max_sim

                if score > best_score:
                    best_score = score
                    best_idx = idx

        if best_idx < 0:
            break

        selected_indices.append(best_idx)
        remaining.discard(best_idx)

    return [candidates[i] for i in selected_indices]
