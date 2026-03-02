"""Tests for cost-aware search provider routing."""

import pytest

from app.domain.services.search.cost_router import (
    PROVIDER_COST,
    CostAwareSearchRouter,
    QuotaStatus,
)
from app.domain.services.search.intent_classifier import SearchIntent


@pytest.fixture()
def router():
    return CostAwareSearchRouter()


@pytest.fixture()
def full_quotas():
    """All providers at 100% remaining."""
    return {
        "tavily": QuotaStatus(used=0, limit=1000),
        "serper": QuotaStatus(used=0, limit=2500),
        "brave": QuotaStatus(used=0, limit=2000),
        "exa": QuotaStatus(used=0, limit=1000),
        "jina": QuotaStatus(used=0, limit=500),
        "duckduckgo": QuotaStatus(used=0, limit=0),  # unlimited
        "bing": QuotaStatus(used=0, limit=0),  # unlimited
    }


@pytest.fixture()
def healthy_providers():
    """All providers at 100% health."""
    return {
        "tavily": 1.0,
        "serper": 1.0,
        "brave": 1.0,
        "exa": 1.0,
        "jina": 1.0,
        "duckduckgo": 1.0,
        "bing": 1.0,
    }


class TestProviderCost:
    """Verify provider cost registry."""

    def test_tavily_basic_costs_1(self):
        assert PROVIDER_COST["tavily_basic"] == 1

    def test_tavily_advanced_costs_2(self):
        assert PROVIDER_COST["tavily_advanced"] == 2

    def test_free_scrapers_cost_0(self):
        assert PROVIDER_COST["duckduckgo"] == 0
        assert PROVIDER_COST["bing"] == 0


class TestQuotaStatus:
    """Test QuotaStatus helpers."""

    def test_remaining_ratio_full(self):
        q = QuotaStatus(used=0, limit=1000)
        assert q.remaining_ratio == 1.0

    def test_remaining_ratio_half(self):
        q = QuotaStatus(used=500, limit=1000)
        assert q.remaining_ratio == 0.5

    def test_remaining_ratio_unlimited(self):
        q = QuotaStatus(used=999, limit=0)
        assert q.remaining_ratio == 1.0  # unlimited always "full"


class TestSelectProvider:
    """Test provider selection for different intents."""

    def test_quick_prefers_free_scraper(self, router, full_quotas, healthy_providers):
        provider, depth = router.select_provider(SearchIntent.QUICK, full_quotas, healthy_providers)
        assert provider in ("duckduckgo", "bing")
        assert depth == "basic"

    def test_standard_picks_cheapest_paid(self, router, full_quotas, healthy_providers):
        provider, _depth = router.select_provider(SearchIntent.STANDARD, full_quotas, healthy_providers)
        # Should pick a paid provider (cost 1), not a free scraper
        assert provider in ("serper", "brave", "exa", "jina", "tavily")

    def test_deep_prefers_tavily(self, router, full_quotas, healthy_providers):
        provider, depth = router.select_provider(SearchIntent.DEEP, full_quotas, healthy_providers)
        assert provider == "tavily"
        assert depth == "advanced"

    def test_exhausted_provider_skipped(self, router, healthy_providers):
        quotas = {
            "tavily": QuotaStatus(used=1000, limit=1000),  # exhausted
            "serper": QuotaStatus(used=0, limit=2500),
            "duckduckgo": QuotaStatus(used=0, limit=0),
        }
        provider, _depth = router.select_provider(SearchIntent.DEEP, quotas, healthy_providers)
        assert provider != "tavily"

    def test_all_paid_exhausted_falls_to_free(self, router, healthy_providers):
        quotas = {
            "tavily": QuotaStatus(used=1000, limit=1000),
            "serper": QuotaStatus(used=2500, limit=2500),
            "brave": QuotaStatus(used=2000, limit=2000),
            "exa": QuotaStatus(used=1000, limit=1000),
            "jina": QuotaStatus(used=500, limit=500),
            "duckduckgo": QuotaStatus(used=0, limit=0),
            "bing": QuotaStatus(used=0, limit=0),
        }
        provider, depth = router.select_provider(SearchIntent.STANDARD, quotas, healthy_providers)
        assert provider in ("duckduckgo", "bing")
        assert depth == "basic"

    def test_unhealthy_provider_deprioritized(self, router, full_quotas):
        health = {
            "tavily": 0.1,  # very unhealthy
            "serper": 1.0,  # healthy
            "duckduckgo": 1.0,
        }
        provider, _depth = router.select_provider(SearchIntent.DEEP, full_quotas, health)
        # Serper should be preferred over unhealthy tavily
        assert provider == "serper"


class TestSelectDepth:
    """Test depth selection logic."""

    def test_quick_always_basic(self, router):
        assert router.select_depth("tavily", SearchIntent.QUICK, 1.0) == "basic"

    def test_standard_basic_when_budget_low(self, router):
        assert router.select_depth("tavily", SearchIntent.STANDARD, 0.5) == "basic"

    def test_standard_advanced_when_budget_high(self, router):
        assert router.select_depth("tavily", SearchIntent.STANDARD, 0.8) == "advanced"

    def test_deep_always_advanced(self, router):
        assert router.select_depth("tavily", SearchIntent.DEEP, 0.3) == "advanced"

    def test_non_tavily_always_basic(self, router):
        # Only Tavily has basic/advanced distinction
        assert router.select_depth("serper", SearchIntent.DEEP, 1.0) == "basic"
