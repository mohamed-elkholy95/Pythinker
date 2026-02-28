"""Tests for DealScraperTool empty-reason propagation in no-deal outcomes."""

from __future__ import annotations

import pytest

from app.domain.external.deal_finder import (
    CouponSearchResult,
    DealComparison,
    DealResult,
    EmptyReason,
)
from app.domain.services.tools.deal_scraper import DealScraperTool


class StubDealFinder:
    """Minimal deal finder stub for testing DealScraperTool behavior."""

    def __init__(self, comparison: DealComparison):
        self._comparison = comparison

    async def search_deals(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
        progress=None,
    ) -> DealComparison:
        return self._comparison

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress=None,
    ) -> CouponSearchResult:
        return CouponSearchResult(coupons=[])

    async def compare_prices(self, product_urls: list[str], progress=None) -> DealComparison:
        return DealComparison(query="compare", deals=[])


@pytest.mark.asyncio
async def test_no_deals_response_includes_no_matches_reason() -> None:
    comparison = DealComparison(
        query="sony wh-1000xm5",
        deals=[],
        searched_stores=["Amazon", "Best Buy"],
        store_errors=[],
        empty_reason=EmptyReason.NO_MATCHES,
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison))

    result = await tool.deal_search("sony wh-1000xm5", stores=["amazon.com", "bestbuy.com"])

    assert result.success is True
    assert result.data is not None
    assert result.data["empty_reason"] == "no_matches"
    assert result.data["stores_attempted"] == 2


@pytest.mark.asyncio
async def test_no_deals_response_includes_all_store_failures_reason() -> None:
    comparison = DealComparison(
        query="rtx 5090",
        deals=[],
        searched_stores=[],
        store_errors=[{"store": "Amazon", "error": "timeout"}],
        empty_reason=EmptyReason.ALL_STORE_FAILURES,
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison))

    result = await tool.deal_search("rtx 5090", stores=["amazon.com"])

    assert result.success is True
    assert result.data is not None
    assert result.data["empty_reason"] == "all_store_failures"
    assert result.data["stores_attempted"] == 1


@pytest.mark.asyncio
async def test_no_deals_response_includes_search_unavailable_reason() -> None:
    comparison = DealComparison(
        query="rtx 5090",
        deals=[],
        searched_stores=[],
        store_errors=[],
        empty_reason=EmptyReason.SEARCH_UNAVAILABLE,
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison))

    result = await tool.deal_search("rtx 5090")

    assert result.success is True
    assert result.data is not None
    assert result.data["empty_reason"] == "search_unavailable"
    assert isinstance(result.data["stores_attempted"], int)
    assert result.data["stores_attempted"] >= 0


@pytest.mark.asyncio
async def test_deals_response_omits_empty_reason_when_deals_exist() -> None:
    comparison = DealComparison(
        query="sony wh-1000xm5",
        deals=[
            DealResult(
                product_name="Sony WH-1000XM5",
                store="Amazon",
                price=299.99,
                url="https://amazon.com/dp/example",
            )
        ],
        empty_reason=None,
    )
    tool = DealScraperTool(deal_finder=StubDealFinder(comparison))

    result = await tool.deal_search("sony wh-1000xm5")

    assert result.success is True
    assert result.data is not None
    assert "empty_reason" not in result.data
