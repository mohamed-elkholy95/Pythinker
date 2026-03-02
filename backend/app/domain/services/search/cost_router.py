"""Cost-aware search provider routing.

Replaces static fallback chain with dynamic cost-optimized routing.
Routes queries to the cheapest healthy provider with remaining monthly quota.

Routing score formula:
    score = (1 - quota_usage_ratio) * health_score * (1 / cost_per_query)

Free scrapers (DuckDuckGo, Bing) used for:
- QUICK intent queries (when search_prefer_free_scrapers_for_quick=True)
- All queries when paid provider quotas are exhausted
- Fallback when all paid providers are unhealthy
"""

import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.domain.services.search.intent_classifier import SearchIntent

logger = logging.getLogger(__name__)

PROVIDER_COST: dict[str, int] = {
    "tavily_basic": 1,
    "tavily_advanced": 2,
    "serper": 1,
    "brave": 1,
    "exa": 1,
    "jina": 1,
    "duckduckgo": 0,
    "bing": 0,
}

FREE_SCRAPERS: frozenset[str] = frozenset({"duckduckgo", "bing"})

# Providers that support depth selection (basic/advanced)
_DEPTH_PROVIDERS: frozenset[str] = frozenset({"tavily"})


@dataclass
class QuotaStatus:
    """Per-provider monthly quota status."""

    used: int
    limit: int  # 0 = unlimited

    @property
    def remaining_ratio(self) -> float:
        """Fraction of quota remaining (0.0-1.0). Unlimited = always 1.0."""
        if self.limit <= 0:
            return 1.0
        remaining = max(0, self.limit - self.used)
        return remaining / self.limit


class CostAwareSearchRouter:
    """Routes search queries to the cheapest healthy provider with remaining quota."""

    def select_provider(
        self,
        intent: SearchIntent,
        quotas: dict[str, QuotaStatus],
        health_scores: dict[str, float],
    ) -> tuple[str, str]:
        """Select the best provider and search depth for a query.

        Args:
            intent: Classified search intent (QUICK/STANDARD/DEEP).
            quotas: Per-provider monthly quota status.
            health_scores: Per-provider health scores (0.0-1.0).

        Returns:
            Tuple of (provider_name, search_depth).
        """
        settings = get_settings()

        # QUICK intent: prefer free scrapers
        if intent == SearchIntent.QUICK and settings.search_prefer_free_scrapers_for_quick:
            free = self._best_free_scraper(quotas, health_scores)
            if free:
                return free, "basic"

        # DEEP intent: prefer Tavily (advanced has better quality)
        if intent == SearchIntent.DEEP:
            tavily_quota = quotas.get("tavily")
            tavily_health = health_scores.get("tavily", 0.0)
            if tavily_quota and tavily_quota.remaining_ratio > 0.05 and tavily_health > 0.3:
                depth = self.select_depth("tavily", intent, tavily_quota.remaining_ratio)
                return "tavily", depth

        # Score all paid providers
        scored: list[tuple[float, str]] = []
        for provider, quota in quotas.items():
            if provider in FREE_SCRAPERS:
                continue
            if quota.limit > 0 and quota.remaining_ratio <= 0.0:
                continue  # exhausted

            health = health_scores.get(provider, 0.5)
            cost = PROVIDER_COST.get(f"{provider}_basic", PROVIDER_COST.get(provider, 1))
            cost_factor = 1.0 / max(cost, 0.1)

            score = quota.remaining_ratio * health * cost_factor
            scored.append((score, provider))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_provider = scored[0][1]
            best_quota = quotas.get(best_provider)
            ratio = best_quota.remaining_ratio if best_quota else 1.0
            depth = self.select_depth(best_provider, intent, ratio)
            return best_provider, depth

        # All paid providers exhausted/unhealthy → free scraper fallback
        free = self._best_free_scraper(quotas, health_scores)
        if free:
            return free, "basic"

        # Absolute last resort
        logger.warning("No search providers available — returning duckduckgo as last resort")
        return "duckduckgo", "basic"

    def select_depth(
        self,
        provider: str,
        intent: SearchIntent,
        quota_remaining_ratio: float,
    ) -> str:
        """Select basic or advanced depth based on intent and budget.

        Only Tavily supports advanced depth. All other providers always return basic.

        Args:
            provider: Provider name.
            intent: Search intent tier.
            quota_remaining_ratio: Fraction of monthly quota remaining.

        Returns:
            "basic" or "advanced".
        """
        if provider not in _DEPTH_PROVIDERS:
            return "basic"

        if intent == SearchIntent.QUICK:
            return "basic"

        if intent == SearchIntent.DEEP:
            return "advanced"

        # STANDARD: upgrade to advanced only if budget is healthy
        settings = get_settings()
        if quota_remaining_ratio >= settings.search_upgrade_depth_threshold:
            return "advanced"

        return "basic"

    @staticmethod
    def _best_free_scraper(
        quotas: dict[str, QuotaStatus],
        health_scores: dict[str, float],
    ) -> str | None:
        """Pick the healthiest free scraper."""
        best: tuple[float, str] | None = None
        for provider in FREE_SCRAPERS:
            if provider not in quotas and provider not in health_scores:
                # Provider not tracked — use it (it's free)
                return provider
            health = health_scores.get(provider, 0.5)
            if best is None or health > best[0]:
                best = (health, provider)
        return best[1] if best else None
