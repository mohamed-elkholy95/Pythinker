"""Batched retrieval for improved performance.

Phase 3: Parallel memory retrieval across multiple queries for
performance optimization in planner/executor/reflection flows.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.long_term_memory import MemorySearchResult
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


async def batch_retrieve(
    memory_service: "MemoryService",
    user_id: str,
    queries: list[str],
    limit_per_query: int = 5,
    enable_reranking: bool = True,
    enable_mmr: bool = False,
) -> dict[str, list["MemorySearchResult"]]:
    """Batch retrieval for multiple queries (parallel execution).

    Executes multiple memory retrieval queries in parallel for improved
    performance when retrieving context for multiple steps/tools.

    Args:
        memory_service: Memory service instance
        user_id: User ID to scope retrieval
        queries: List of query strings
        limit_per_query: Maximum results per query
        enable_reranking: Whether to use cross-encoder reranking
        enable_mmr: Whether to use MMR diversification

    Returns:
        Dictionary mapping query to list of search results
    """
    if not queries:
        return {}

    async def retrieve_one(query: str) -> list["MemorySearchResult"]:
        """Retrieve memories for a single query."""
        try:
            return await memory_service.retrieve_relevant(
                user_id=user_id,
                context=query,
                limit=limit_per_query,
                enable_reranking=enable_reranking,
                enable_mmr=enable_mmr,
            )
        except Exception as e:
            logger.warning(f"Batch retrieval failed for query '{query[:50]}...': {e}")
            return []

    # Execute in parallel
    from app.core.async_utils import gather_compat

    results = await gather_compat(*[retrieve_one(q) for q in queries], return_exceptions=False)

    return dict(zip(queries, results, strict=False))


async def batch_retrieve_deduped(
    memory_service: "MemoryService",
    user_id: str,
    queries: list[str],
    limit_total: int = 20,
    **kwargs,
) -> list["MemorySearchResult"]:
    """Batch retrieval with deduplication across queries.

    Useful when queries overlap and you want unique results.

    Args:
        memory_service: Memory service instance
        user_id: User ID to scope retrieval
        queries: List of query strings
        limit_total: Maximum total unique results
        **kwargs: Additional arguments for retrieve_relevant

    Returns:
        Deduplicated list of search results, sorted by best score
    """
    # Get results for each query
    batch_results = await batch_retrieve(
        memory_service=memory_service,
        user_id=user_id,
        queries=queries,
        limit_per_query=limit_total,  # Fetch more for better dedup
        **kwargs,
    )

    # Deduplicate by memory ID, keeping highest score
    seen_ids: dict[str, MemorySearchResult] = {}

    for query_results in batch_results.values():
        for result in query_results:
            mem_id = result.memory.id
            if mem_id not in seen_ids or result.relevance_score > seen_ids[mem_id].relevance_score:
                seen_ids[mem_id] = result

    # Sort by score and limit
    deduped = list(seen_ids.values())
    deduped.sort(key=lambda r: r.relevance_score, reverse=True)

    return deduped[:limit_total]
