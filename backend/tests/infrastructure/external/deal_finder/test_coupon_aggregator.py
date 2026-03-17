"""Tests for coupon aggregator web-research expansion and item categorization."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.deal_finder.coupon_aggregator import (
    aggregate_coupons,
    build_coupon_source_urls,
)


@pytest.mark.asyncio
async def test_aggregate_coupons_web_research_categorizes_digital_and_physical() -> None:
    """Web research source should return categorized coupons from latest web results."""
    search_engine = AsyncMock()
    search_engine.search = AsyncMock(
        return_value=ToolResult.ok(
            data=SearchResults(
                query="target coupon code",
                total_results=2,
                results=[
                    SearchResultItem(
                        title="AppSumo Promo Code SAVE40 for AI Writing Tool",
                        link="https://appsumo.com/products/ai-writer/",
                        snippet="Use code SAVE40 for 40% off annual software plan",
                    ),
                    SearchResultItem(
                        title="Target Coupons and Sales",
                        link="https://www.groupon.com/coupons/stores/target.com",
                        snippet="Latest coupons for home and electronics deals",
                    ),
                ],
            )
        )
    )

    coupons, failures = await aggregate_coupons(
        scraper=AsyncMock(),
        store="Target",
        sources=["web_research"],
        search_engine=search_engine,
    )

    assert failures == []
    assert len(coupons) >= 2
    categories = {coupon.item_category for coupon in coupons}
    assert "digital" in categories
    assert "physical" in categories
    assert any(coupon.source == "appsumo" for coupon in coupons)
    assert any(coupon.source == "groupon" for coupon in coupons)


def test_build_coupon_source_urls_includes_web_research_domains() -> None:
    """URL diagnostics should expose expanded web-research sources."""
    urls = build_coupon_source_urls("Adobe", ["retailmenot", "couponscom", "web_research"])

    assert "https://www.retailmenot.com/view/adobe.com" in urls
    assert "https://www.coupons.com/coupon-codes/adobe" in urls
    assert "https://www.dealnews.com" in urls
    assert "https://www.couponfollow.com" in urls
    assert "https://www.appsumo.com" in urls


@pytest.mark.asyncio
async def test_aggregate_coupons_web_research_requires_search_engine() -> None:
    """Web research source should provide a clear failure when search is unavailable."""
    coupons, failures = await aggregate_coupons(
        scraper=AsyncMock(),
        store="Notion",
        sources=["web_research"],
        search_engine=None,
    )

    assert coupons == []
    assert failures
    assert failures[0]["source"] == "web_research"
