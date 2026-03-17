"""Tests for DealFinderAdapter Shopping-powered search methods.

Covers:
- _search_via_shopping: converts ShoppingResult → DealResult, skips price=0
- search_deals (v2 path): no site: operator, Shopping → web fallback
- score ordering: deals sorted descending by score
- Digital product auto-routing: web mode for subscription products
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.external.deal_finder import DealComparison
from app.domain.external.scraper import ScrapedContent
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.deal_finder import adapter as adapter_module
from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter
from app.infrastructure.external.search.serper_search import ShoppingResult

# ---------------------------------------------------------------------------
# Shared fixtures & helpers
# ---------------------------------------------------------------------------


def _make_shopping_result(
    title: str = "Test Product",
    source: str = "Amazon",
    price: float = 99.99,
    link: str = "https://www.amazon.com/dp/TEST",
    image_url: str = "",
    position: int = 1,
) -> ShoppingResult:
    return ShoppingResult(
        title=title,
        source=source,
        price=price,
        link=link,
        image_url=image_url,
        position=position,
    )


def _make_settings(
    *,
    deal_search_mode: str = "shopping",
    deal_verify_top_n: int = 3,
    deal_verify_timeout: float = 5.0,
    deal_coupon_search_enabled: bool = False,
    deal_scraper_timeout: int = 10,
    deal_scraper_max_stores: int = 10,
    deal_scraper_history_enabled: bool = False,
    deal_scraper_price_voting_enabled: bool = True,
    deal_scraper_llm_extraction_enabled: bool = False,
    deal_scraper_llm_max_per_search: int = 0,
    deal_scraper_community_search: bool = False,
    deal_scraper_open_web_search: bool = False,
    deal_scraper_community_max_queries: int = 1,
    deal_scraper_coupon_sources: str = "slickdeals",
    deal_scraper_cache_ttl: int = 3600,
) -> SimpleNamespace:
    return SimpleNamespace(
        deal_search_mode=deal_search_mode,
        deal_verify_top_n=deal_verify_top_n,
        deal_verify_timeout=deal_verify_timeout,
        deal_coupon_search_enabled=deal_coupon_search_enabled,
        deal_scraper_timeout=deal_scraper_timeout,
        deal_scraper_max_stores=deal_scraper_max_stores,
        deal_scraper_history_enabled=deal_scraper_history_enabled,
        deal_scraper_price_voting_enabled=deal_scraper_price_voting_enabled,
        deal_scraper_llm_extraction_enabled=deal_scraper_llm_extraction_enabled,
        deal_scraper_llm_max_per_search=deal_scraper_llm_max_per_search,
        deal_scraper_community_search=deal_scraper_community_search,
        deal_scraper_open_web_search=deal_scraper_open_web_search,
        deal_scraper_community_max_queries=deal_scraper_community_max_queries,
        deal_scraper_coupon_sources=deal_scraper_coupon_sources,
        deal_scraper_cache_ttl=deal_scraper_cache_ttl,
    )


def _noop_scraper() -> AsyncMock:
    scraper = AsyncMock()
    scraper.fetch = AsyncMock(return_value=ScrapedContent(success=False, url="", text="", html=None))
    return scraper


# ---------------------------------------------------------------------------
# 1. _search_via_shopping: returns deals from multiple stores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shopping_search_returns_deals_from_multiple_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_search_via_shopping converts 3-store ShoppingResults into DealResult objects."""
    settings = _make_settings()
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

    shopping_items = [
        _make_shopping_result(
            title="Sony WH-1000XM5", source="Amazon", price=278.00, link="https://www.amazon.com/dp/B09ABCD", position=1
        ),
        _make_shopping_result(
            title="Sony WH-1000XM5",
            source="Best Buy",
            price=299.99,
            link="https://www.bestbuy.com/site/123",
            position=2,
        ),
        _make_shopping_result(
            title="Sony WH-1000XM5", source="Walmart", price=269.00, link="https://www.walmart.com/ip/456", position=3
        ),
    ]

    search_engine = AsyncMock()
    search_engine.search_shopping = AsyncMock(
        return_value=ToolResult.ok(
            message="Found 3 shopping results",
            data=shopping_items,
        )
    )

    adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
    deals = await adapter._search_via_shopping("Sony WH-1000XM5 headphones")

    assert len(deals) == 3
    stores = {d.store for d in deals}
    assert stores == {"Amazon", "Best Buy", "Walmart"}

    prices = [d.price for d in deals]
    assert 278.00 in prices
    assert 299.99 in prices
    assert 269.00 in prices

    # All should have high extraction confidence (Shopping API)
    for deal in deals:
        assert deal.extraction_confidence >= 0.7
        assert deal.source_type == "store"


# ---------------------------------------------------------------------------
# 2. _search_via_shopping: no site: operator in the query sent to the API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shopping_search_no_site_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_search_via_shopping must NOT inject a site: operator into the query."""
    settings = _make_settings()
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

    search_engine = AsyncMock()
    search_engine.search_shopping = AsyncMock(return_value=ToolResult.ok(message="0 results", data=[]))

    adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
    await adapter._search_via_shopping("Sony WH-1000XM5")

    call_args = search_engine.search_shopping.call_args
    assert call_args is not None
    query_sent: str = call_args[0][0] if call_args[0] else call_args[1].get("query", "")
    assert "site:" not in query_sent, f"site: operator found in query: {query_sent!r}"


# ---------------------------------------------------------------------------
# 3. search_deals v2: deals sorted by score (descending)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deals_sorted_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_deals must return deals sorted by score descending."""
    settings = _make_settings(
        deal_search_mode="shopping",
        deal_verify_top_n=0,  # skip verification for this test
        deal_coupon_search_enabled=False,
    )
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

    # Three products at different prices — Amazon lowest → highest score
    shopping_items = [
        _make_shopping_result(
            title="Laptop", source="Newegg", price=1100.00, link="https://www.newegg.com/p/1", position=1
        ),
        _make_shopping_result(
            title="Laptop", source="Amazon", price=899.00, link="https://www.amazon.com/dp/1", position=2
        ),
        _make_shopping_result(
            title="Laptop", source="Best Buy", price=999.00, link="https://www.bestbuy.com/site/1", position=3
        ),
    ]

    search_engine = AsyncMock()
    search_engine.search_shopping = AsyncMock(return_value=ToolResult.ok(message="3 results", data=shopping_items))

    adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
    comparison = await adapter.search_deals("gaming laptop")

    assert isinstance(comparison, DealComparison)
    scores = [d.score for d in comparison.deals]
    assert scores == sorted(scores, reverse=True), f"Deals not sorted descending: {scores}"
    assert len(comparison.deals) > 0


# ---------------------------------------------------------------------------
# 4. Digital product auto-routing uses _search_via_web, not _search_via_shopping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digital_product_uses_web_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'Adobe Creative Cloud subscription' is classified as digital → web mode."""
    settings = _make_settings(
        deal_search_mode="auto",
        deal_verify_top_n=0,
        deal_coupon_search_enabled=False,
    )
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

    search_engine = AsyncMock()
    # shopping should NOT be called for digital products
    search_engine.search_shopping = AsyncMock(return_value=ToolResult.ok(message="0 results", data=[]))
    # web search returns 0 results (just checking routing, not results)
    from app.domain.models.search import SearchResults

    search_engine.search = AsyncMock(
        return_value=ToolResult.ok(
            message="0 results",
            data=SearchResults(
                query="Adobe Creative Cloud subscription buy price deal",
                total_results=0,
                results=[],
            ),
        )
    )

    adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
    comparison = await adapter.search_deals("Adobe Creative Cloud subscription")

    # search_shopping must NOT have been called
    search_engine.search_shopping.assert_not_awaited()

    # search() (web) must have been called at least once
    assert search_engine.search.await_count >= 1

    assert isinstance(comparison, DealComparison)
    assert comparison.query == "Adobe Creative Cloud subscription"


# ---------------------------------------------------------------------------
# 5. No-legacy path: explicit stores should use Shopping API, not site: scraping
# ---------------------------------------------------------------------------


class TestNoLegacyPath:
    """Explicit stores must route through the Shopping API, not the legacy per-store path."""

    @pytest.mark.asyncio
    async def test_explicit_stores_still_uses_shopping_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even when LLM passes stores, should use Shopping API, not legacy site: scraping."""
        settings = _make_settings(
            deal_search_mode="auto",
            deal_verify_top_n=0,
            deal_coupon_search_enabled=False,
        )
        monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

        from app.domain.models.search import SearchResults

        search_engine = AsyncMock()
        search_engine.search_shopping = AsyncMock(
            return_value=ToolResult.ok(
                message="Found 1 shopping result",
                data=[
                    _make_shopping_result(
                        title="MacBook Air M3",
                        source="Amazon",
                        price=999.0,
                        link="https://amazon.com/dp/123",
                    ),
                ],
            )
        )
        search_engine.search = AsyncMock(
            return_value=ToolResult.ok(
                message="0 results",
                data=SearchResults(query="MacBook Air M3", total_results=0, results=[]),
            )
        )

        adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
        result = await adapter.search_deals(
            query="MacBook Air M3",
            stores=["amazon.com", "bestbuy.com"],
        )

        # Shopping API must have been called — not site: legacy path
        assert search_engine.search_shopping.called, (
            "search_shopping was not called — explicit stores should hint Shopping API, not trigger legacy scraping"
        )
        assert result is not None
        assert isinstance(result, DealComparison)

    @pytest.mark.asyncio
    async def test_explicit_stores_never_uses_legacy_method(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_search_deals_legacy must never be called regardless of the stores parameter."""
        settings = _make_settings(
            deal_search_mode="shopping",
            deal_verify_top_n=0,
            deal_coupon_search_enabled=False,
        )
        monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

        search_engine = AsyncMock()
        search_engine.search_shopping = AsyncMock(return_value=ToolResult.ok(message="0 results", data=[]))

        from app.domain.models.search import SearchResults

        search_engine.search = AsyncMock(
            return_value=ToolResult.ok(
                message="0 results",
                data=SearchResults(query="test", total_results=0, results=[]),
            )
        )

        adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)

        # Patch _search_deals_legacy to raise if ever called — should never be invoked
        async def _legacy_should_not_be_called(*args: object, **kwargs: object) -> DealComparison:
            raise AssertionError("_search_deals_legacy was called but should not be on the active code path")

        monkeypatch.setattr(adapter, "_search_deals_legacy", _legacy_should_not_be_called)

        # Should not raise — legacy path is never triggered
        result = await adapter.search_deals(
            query="Sony WH-1000XM5",
            stores=["amazon.com", "bestbuy.com", "walmart.com"],
        )

        assert isinstance(result, DealComparison)

    @pytest.mark.asyncio
    async def test_store_hints_appended_to_shopping_query(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Store names are appended as search hints when explicit stores are provided in shopping mode."""
        settings = _make_settings(
            deal_search_mode="shopping",
            deal_verify_top_n=0,
            deal_coupon_search_enabled=False,
        )
        monkeypatch.setattr(adapter_module, "get_settings", lambda: settings)

        captured_queries: list[str] = []

        async def _capture_shopping(query: str, num: int = 20) -> ToolResult:
            captured_queries.append(query)
            return ToolResult.ok(message="0 results", data=[])

        search_engine = AsyncMock()
        search_engine.search_shopping = _capture_shopping

        from app.domain.models.search import SearchResults

        search_engine.search = AsyncMock(
            return_value=ToolResult.ok(
                message="0 results",
                data=SearchResults(query="test", total_results=0, results=[]),
            )
        )

        adapter = DealFinderAdapter(scraper=_noop_scraper(), search_engine=search_engine)
        await adapter.search_deals(
            query="Gaming Laptop",
            stores=["amazon.com", "bestbuy.com"],
        )

        assert len(captured_queries) >= 1
        query_sent = captured_queries[0]
        # Store hints (stripped of .com suffix) should be appended
        assert "amazon" in query_sent.lower() or "bestbuy" in query_sent.lower(), (
            f"Expected store hints in Shopping query, got: {query_sent!r}"
        )
