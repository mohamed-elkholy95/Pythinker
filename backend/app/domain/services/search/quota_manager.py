"""Central search orchestrator that minimizes credit consumption.

Wires together intent classification, dedup, routing, and quota tracking.

Responsibilities:
- Classify query intent (QUICK/STANDARD/DEEP)
- Check semantic dedup before executing
- Route to cheapest healthy provider with remaining quota
- Select search depth based on intent + remaining budget
- Track per-provider monthly usage (Redis or in-memory fallback)
- Auto-degrade when budget runs low

Redis keys:
- search_quota:{provider}:{YYYY-MM} — monthly credit counter
- TTL: 32 days (auto-expire after month ends)
- Graceful fallback: in-memory defaultdict when Redis unavailable
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.domain.models.search import SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.search.cost_router import (
    PROVIDER_COST,
    CostAwareSearchRouter,
    QuotaStatus,
)
from app.domain.services.search.dedup_enhanced import EnhancedDedup
from app.domain.services.search.intent_classifier import QueryIntentClassifier

logger = logging.getLogger(__name__)

# Singleton instance
_instance: "SearchQuotaManager | None" = None

# Provider quota setting names mapping
_PROVIDER_QUOTA_SETTINGS: dict[str, str] = {
    "tavily": "search_quota_tavily",
    "serper": "search_quota_serper",
    "brave": "search_quota_brave",
    "exa": "search_quota_exa",
    "jina": "search_quota_jina",
    "duckduckgo": "",  # unlimited
    "bing": "",  # unlimited
}


class SearchQuotaManager:
    """Central search orchestrator that minimizes credit consumption
    while maintaining result quality.
    """

    def __init__(
        self,
        redis_client: Any | None,
        intent_classifier: QueryIntentClassifier,
        cost_router: CostAwareSearchRouter,
        dedup: EnhancedDedup,
    ) -> None:
        self._redis = redis_client
        self._classifier = intent_classifier
        self._router = cost_router
        self._dedup = dedup

        # In-memory fallback counters (used when Redis unavailable)
        self._usage_counters: defaultdict[str, int] = defaultdict(int)

        # Session-scoped query history for dedup
        self._session_queries: list[str] = []

    async def route(
        self,
        query: str,
        search_engine: Any,
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Route a search query through the optimization pipeline.

        Pipeline:
        1. Classify intent (QUICK/STANDARD/DEEP)
        2. Check dedup (skip if duplicate)
        3. Get quota status for all providers
        4. Route to cheapest healthy provider
        5. Execute search
        6. Record usage
        7. Return result with metadata

        Args:
            query: Search query string.
            search_engine: Fallback search engine (existing SearchEngine instance).
            context: Optional context (e.g., health scores).

        Returns:
            ToolResult with search results and provider metadata.
        """
        settings = get_settings()

        # 1. Get quota status
        quotas = await self.get_quota_status()

        # Compute aggregate remaining ratio for budget-aware classification
        aggregate_ratio = self._aggregate_remaining_ratio(quotas)

        # 2. Classify intent with budget awareness
        intent = self._classifier.classify(query, quota_remaining_ratio=aggregate_ratio)
        logger.info("Query intent: %s (aggregate budget: %.1f%%)", intent, aggregate_ratio * 100)

        # 3. Check dedup
        if settings.search_enhanced_dedup_enabled and self._dedup.is_duplicate(query, self._session_queries):
            logger.info("Dedup: query '%s' is duplicate, skipping API call", query[:80])
            return ToolResult(
                success=False,
                message="Search already executed for a similar query. Use existing results.",
                data=SearchResults(query=query),
            )

        # 4. Get health scores
        health_scores = self._get_health_scores(context)

        # 5. Route to provider
        provider, depth = self._router.select_provider(intent, quotas, health_scores)
        logger.info("Routing to provider=%s depth=%s for intent=%s", provider, depth, intent)

        # 6. Execute search via the existing engine
        result = await search_engine.search(query)

        # 7. Record usage
        credit_cost = PROVIDER_COST.get(f"{provider}_{depth}", PROVIDER_COST.get(provider, 1))
        await self._record_usage(provider, credit_cost)

        # Record query for dedup
        self._session_queries.append(query)

        return result

    async def get_quota_status(self) -> dict[str, QuotaStatus]:
        """Get current quota status for all providers.

        Tries Redis first, falls back to in-memory counters.

        Returns:
            Dict mapping provider name to QuotaStatus.
        """
        settings = get_settings()
        result: dict[str, QuotaStatus] = {}

        for provider, setting_name in _PROVIDER_QUOTA_SETTINGS.items():
            limit = getattr(settings, setting_name, 0) if setting_name else 0
            used = await self._get_usage(provider)
            result[provider] = QuotaStatus(used=used, limit=limit)

        return result

    async def _get_usage(self, provider: str) -> int:
        """Get current month's usage for a provider."""
        month_key = datetime.now(tz=UTC).strftime("%Y-%m")

        if self._redis:
            try:
                redis_key = f"search_quota:{provider}:{month_key}"
                val = await self._redis.get(redis_key)
                return int(val) if val else 0
            except Exception:
                logger.debug("Redis unavailable for quota read, using in-memory fallback")

        return self._usage_counters.get(provider, 0)

    async def _record_usage(self, provider: str, credits: int) -> None:
        """Record credit usage for a provider."""
        month_key = datetime.now(tz=UTC).strftime("%Y-%m")

        # Always update in-memory counter
        self._usage_counters[provider] += credits

        if self._redis:
            try:
                redis_key = f"search_quota:{provider}:{month_key}"
                await self._redis.incrby(redis_key, credits)
                # Set TTL to 32 days if not already set
                ttl = await self._redis.ttl(redis_key)
                if ttl < 0:
                    await self._redis.expire(redis_key, 32 * 86400)
            except Exception:
                logger.debug("Redis unavailable for quota write, in-memory only")

    @staticmethod
    def _aggregate_remaining_ratio(quotas: dict[str, QuotaStatus]) -> float:
        """Compute weighted aggregate remaining ratio across paid providers."""
        total_limit = 0
        total_remaining = 0
        for quota in quotas.values():
            if quota.limit > 0:
                total_limit += quota.limit
                total_remaining += max(0, quota.limit - quota.used)
        if total_limit == 0:
            return 1.0
        return total_remaining / total_limit

    @staticmethod
    def _get_health_scores(context: dict[str, Any] | None) -> dict[str, float]:
        """Extract health scores from context, or default to 1.0 for all."""
        if context and "health_scores" in context:
            return context["health_scores"]

        # Try to get from provider health ranker singleton
        try:
            from app.infrastructure.external.search.provider_health_ranker import (
                get_provider_health_ranker,
            )

            ranker = get_provider_health_ranker()
            return {name: ranker.health_score(name) for name in _PROVIDER_QUOTA_SETTINGS}
        except Exception:
            logger.debug("Provider health ranker unavailable, defaulting health scores to 1.0")

        return dict.fromkeys(_PROVIDER_QUOTA_SETTINGS, 1.0)


def get_search_quota_manager(redis_client: Any | None = None) -> SearchQuotaManager:
    """Get or create the SearchQuotaManager singleton.

    Consistent with existing get_*() singleton patterns in the codebase.
    """
    global _instance
    if _instance is None:
        settings = get_settings()
        _instance = SearchQuotaManager(
            redis_client=redis_client,
            intent_classifier=QueryIntentClassifier(),
            cost_router=CostAwareSearchRouter(),
            dedup=EnhancedDedup(similarity_threshold=settings.search_dedup_jaccard_threshold),
        )
    return _instance
