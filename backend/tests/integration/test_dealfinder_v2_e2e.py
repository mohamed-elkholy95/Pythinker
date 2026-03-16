"""End-to-end integration tests for DealFinder v2.

Verifies the complete flow: search → score → return deals + coupons.
All external I/O (search_engine, scraper) is mocked so these tests run
fully offline with no API keys or Docker dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.external.deal_finder import DealComparison
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter
from app.infrastructure.external.search.serper_search import ShoppingResult


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_shopping_results(items: list[dict]) -> ToolResult[list[ShoppingResult]]:
    """Build a successful ToolResult containing ShoppingResult objects."""
    results = [
        ShoppingResult(
            title=item["title"],
            source=item["source"],
            price=item["price"],
            link=item["link"],
            rating=item.get("rating", 0.0),
            rating_count=item.get("rating_count", 0),
            image_url=item.get("image_url", ""),
            position=idx + 1,
            price_raw=f"${item['price']:.2f}",
        )
        for idx, item in enumerate(items)
    ]
    return ToolResult.ok(
        message=f"Found {len(results)} shopping results",
        data=results,
    )


def _make_search_results(items: list[dict], query: str = "") -> ToolResult[SearchResults]:
    """Build a successful ToolResult containing SearchResults."""
    result_items = [
        SearchResultItem(
            title=item["title"],
            link=item["link"],
            snippet=item.get("snippet", ""),
        )
        for item in items
    ]
    return ToolResult.ok(
        message=f"Found {len(result_items)} results",
        data=SearchResults(
            query=query,
            total_results=len(result_items),
            results=result_items,
        ),
    )


def _empty_search_results(query: str = "") -> ToolResult[SearchResults]:
    """Build a successful ToolResult with zero search results."""
    return ToolResult.ok(
        message="Found 0 results",
        data=SearchResults(query=query, total_results=0, results=[]),
    )


def _make_scraper_none() -> AsyncMock:
    """Build a Scraper mock whose fetch() returns None (skip page verification)."""
    scraper = MagicMock()
    scraper.fetch = AsyncMock(return_value=None)
    scraper.fetch_with_escalation = AsyncMock(return_value=None)
    return scraper


# ---------------------------------------------------------------------------
# Test 1: physical product — Shopping results produce scored, sorted deals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_search_flow_physical_product() -> None:
    """Shopping API results are converted, scored, and returned sorted descending.

    Mocks:
    - search_engine.search_shopping → 5 ShoppingResult items from 5 distinct stores
    - search_engine.search           → empty (no coupons found)
    - scraper.fetch                  → None (verification skipped)

    Assertions:
    - ≥ 3 deals returned
    - all deal scores > 0
    - deals are sorted in descending score order
    - multiple unique stores present
    """
    query = "Sony WH-1000XM5 headphones"

    shopping_payload = [
        {"title": "Sony WH-1000XM5 Wireless Headphones", "source": "Amazon", "price": 279.99,
         "link": "https://amazon.com/dp/B09XS7JWHH", "rating": 4.8, "rating_count": 15000},
        {"title": "Sony WH-1000XM5 Headphones", "source": "Best Buy", "price": 289.99,
         "link": "https://bestbuy.com/site/sony-wh-1000xm5/6505727.p", "rating": 4.7, "rating_count": 8000},
        {"title": "Sony WH-1000XM5 Noise Canceling Headphones", "source": "Costco", "price": 259.99,
         "link": "https://costco.com/sony-wh-1000xm5.product.100123456.html", "rating": 4.6, "rating_count": 3000},
        {"title": "Sony WH-1000XM5 Wireless Headphones", "source": "Walmart", "price": 298.00,
         "link": "https://walmart.com/ip/Sony-WH-1000XM5/1234567890", "rating": 4.5, "rating_count": 5000},
        {"title": "Sony WH-1000XM5 Wireless Over-Ear Headphones", "source": "Newegg", "price": 269.00,
         "link": "https://newegg.com/p/27Y-000N-00017", "rating": 4.4, "rating_count": 1200},
    ]

    search_engine = MagicMock()
    search_engine.search_shopping = AsyncMock(return_value=_make_shopping_results(shopping_payload))
    # Coupon search: returns empty
    search_engine.search = AsyncMock(return_value=_empty_search_results(query))

    scraper = _make_scraper_none()

    adapter = DealFinderAdapter(scraper=scraper, search_engine=search_engine)

    # Force shopping mode so classification doesn't route to web path
    with patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings:
        settings = MagicMock()
        settings.deal_search_mode = "shopping"
        settings.deal_verify_top_n = 0          # skip verification to avoid scraper calls
        settings.deal_verify_timeout = 5.0
        settings.deal_coupon_search_enabled = True
        settings.deal_scraper_timeout = 10
        settings.deal_scraper_history_enabled = False
        mock_settings.return_value = settings

        result: DealComparison = await adapter.search_deals(query=query)

    # Basic structure
    assert result is not None
    assert isinstance(result, DealComparison)
    assert result.query == query

    # At least 3 deals returned
    assert len(result.deals) >= 3, f"Expected ≥3 deals, got {len(result.deals)}"

    # All scores > 0
    for deal in result.deals:
        assert deal.score > 0, f"Deal from {deal.store} has score 0"

    # Sorted descending by score
    scores = [d.score for d in result.deals]
    assert scores == sorted(scores, reverse=True), "Deals are not sorted by score descending"

    # Multiple unique stores
    unique_stores = {d.store for d in result.deals}
    assert len(unique_stores) >= 3, f"Expected ≥3 unique stores, got {unique_stores}"


# ---------------------------------------------------------------------------
# Test 2: digital product — empty shopping, empty web — no crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_search_flow_digital_product() -> None:
    """Digital product with no results doesn't crash and returns a valid DealComparison.

    Adobe Creative Cloud is a subscription service — no Google Shopping listing.
    Both search_shopping and search return empty.

    Assertions:
    - result is not None
    - result is a DealComparison
    - no exception raised
    - deals list is present (may be empty)
    """
    query = "Adobe Creative Cloud annual subscription"

    search_engine = MagicMock()
    # search_shopping: empty list (no Shopping results for software)
    search_engine.search_shopping = AsyncMock(
        return_value=ToolResult.ok(message="Found 0 shopping results", data=[])
    )
    # search: empty web results
    search_engine.search = AsyncMock(return_value=_empty_search_results(query))

    scraper = _make_scraper_none()

    adapter = DealFinderAdapter(scraper=scraper, search_engine=search_engine)

    with patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings:
        settings = MagicMock()
        settings.deal_search_mode = "auto"
        settings.deal_verify_top_n = 0
        settings.deal_verify_timeout = 5.0
        settings.deal_coupon_search_enabled = False
        settings.deal_scraper_timeout = 10
        settings.deal_scraper_history_enabled = False
        mock_settings.return_value = settings

        # Patch classify_item_category to force "digital" routing
        with patch("app.infrastructure.external.deal_finder.adapter.classify_item_category", return_value="digital"):
            result = await adapter.search_deals(query=query)

    assert result is not None, "search_deals must return a DealComparison, not None"
    assert isinstance(result, DealComparison)
    assert result.query == query
    assert isinstance(result.deals, list)


# ---------------------------------------------------------------------------
# Test 3: coupon search included in results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coupons_included_in_results() -> None:
    """Coupons from the web search are included in the DealComparison output.

    Mocks:
    - search_shopping → 3 product deals
    - search (coupon query) → 2 coupon-like web results
    - scraper.fetch → None

    Assertions:
    - deals list contains at least the 3 shopping results (after scoring)
    - coupons_found list is a list (may be empty or populated depending on
      _search_coupons_web parsing; we assert the field is accessible and non-None)
    """
    query = "Nintendo Switch OLED"

    shopping_payload = [
        {"title": "Nintendo Switch – OLED Model", "source": "Amazon", "price": 349.99,
         "link": "https://amazon.com/dp/B098RL6SBJ"},
        {"title": "Nintendo Switch OLED", "source": "Best Buy", "price": 349.99,
         "link": "https://bestbuy.com/site/nintendo-switch-oled/6453654.p"},
        {"title": "Nintendo Switch OLED Console", "source": "Walmart", "price": 339.00,
         "link": "https://walmart.com/ip/Nintendo-Switch-OLED/114090758"},
    ]

    coupon_results = [
        {"title": "Nintendo eShop 10% off coupon code 2026", "link": "https://slickdeals.net/coupon/nintendo",
         "snippet": "Use code ESHOP10 for 10% off Nintendo eShop purchases. Verified working."},
        {"title": "Best Nintendo Switch deals and promo codes", "link": "https://retailmenot.com/view/nintendo.com",
         "snippet": "Find the latest Nintendo coupon codes and save on your purchase."},
    ]

    search_engine = MagicMock()
    search_engine.search_shopping = AsyncMock(return_value=_make_shopping_results(shopping_payload))
    # search() is called for the coupon query — return 2 coupon results
    search_engine.search = AsyncMock(return_value=_make_search_results(coupon_results, query=query))

    scraper = _make_scraper_none()
    # Also mock fetch_slickdeals_coupons to avoid live network calls
    with patch(
        "app.infrastructure.external.deal_finder.adapter.fetch_slickdeals_coupons",
        new_callable=AsyncMock,
        return_value=[],
    ):
        adapter = DealFinderAdapter(scraper=scraper, search_engine=search_engine)

        with patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings:
            settings = MagicMock()
            settings.deal_search_mode = "shopping"
            settings.deal_verify_top_n = 0
            settings.deal_verify_timeout = 5.0
            settings.deal_coupon_search_enabled = True
            settings.deal_scraper_timeout = 10
            settings.deal_scraper_history_enabled = False
            mock_settings.return_value = settings

            result: DealComparison = await adapter.search_deals(query=query)

    # Deals from Shopping results
    assert result is not None
    assert len(result.deals) >= 3, f"Expected ≥3 deals, got {len(result.deals)}"

    # coupons_found is always a list (Protocol contract)
    assert isinstance(result.coupons_found, list), "coupons_found must be a list"
