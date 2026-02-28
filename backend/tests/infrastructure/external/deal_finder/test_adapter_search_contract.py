"""Regression tests for DealFinderAdapter search contract handling.

These tests lock behavior at the SearchEngine contract boundary:
SearchEngine.search() returns ToolResult[SearchResults], and the adapter
must unwrap the envelope correctly before processing results.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.external.deal_finder import EmptyReason
from app.domain.external.scraper import ScrapedContent
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.deal_finder import adapter as adapter_module
from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter


def _mock_settings() -> SimpleNamespace:
    """Settings stub for adapter internals used by tested methods."""
    return SimpleNamespace(
        deal_scraper_price_voting_enabled=True,
        deal_scraper_llm_extraction_enabled=False,
        deal_scraper_llm_max_per_search=0,
        deal_scraper_community_max_queries=1,
        deal_scraper_community_search=True,
        deal_scraper_open_web_search=False,
    )


def _mock_search_deals_settings() -> SimpleNamespace:
    """Settings stub for adapter.search_deals()."""
    return SimpleNamespace(
        deal_scraper_timeout=5,
        deal_scraper_max_stores=10,
        deal_scraper_coupon_sources="slickdeals,retailmenot,couponscom",
        deal_scraper_community_search=False,
        deal_scraper_open_web_search=False,
        deal_scraper_community_max_queries=1,
        deal_scraper_cache_ttl=3600,
        deal_scraper_history_enabled=False,
        deal_scraper_price_voting_enabled=True,
        deal_scraper_llm_extraction_enabled=False,
        deal_scraper_llm_max_per_search=0,
    )


@pytest.mark.asyncio
async def test_search_store_reads_toolresult_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """_search_store must unwrap ToolResult.data and extract at least one deal."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_settings())

    search_engine = AsyncMock()
    search_engine.search = AsyncMock(
        return_value=ToolResult.ok(
            data=SearchResults(
                query="rtx 5090 site:amazon.com",
                total_results=1,
                results=[
                    SearchResultItem(
                        title="NVIDIA RTX 5090 Graphics Card",
                        link="https://www.amazon.com/dp/B0TEST5090",
                        snippet="Now $1999.99 with limited stock",
                    )
                ],
            )
        )
    )

    scraper = AsyncMock()
    scraper.fetch_with_escalation = AsyncMock(
        return_value=ScrapedContent(
            success=True,
            url="https://www.amazon.com/dp/B0TEST5090",
            text="NVIDIA RTX 5090 $1999.99",
            html=(
                '<script type="application/ld+json">'
                '{"@type":"Product","name":"NVIDIA RTX 5090",'
                '"offers":{"price":1999.99,"availability":"InStock"}}'
                "</script>"
            ),
        )
    )

    adapter = DealFinderAdapter(scraper=scraper, search_engine=search_engine)
    deals = await adapter._search_store("rtx 5090 site:amazon.com", "amazon.com", timeout=5)

    assert len(deals) > 0
    assert deals[0].price > 0
    search_engine.search.assert_awaited_once_with("rtx 5090 site:amazon.com")


@pytest.mark.asyncio
async def test_search_community_reads_toolresult_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """_search_community must unwrap ToolResult.data before snippet parsing."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_settings())

    search_engine = AsyncMock()
    search_engine.search = AsyncMock(
        return_value=ToolResult.ok(
            data=SearchResults(
                query="rtx 5090 deal reddit",
                total_results=1,
                results=[
                    SearchResultItem(
                        title="RTX 5090 deal thread",
                        link="https://reddit.com/r/buildapcsales/comments/abc123",
                        snippet="Found one for $1499.99 this morning",
                    )
                ],
            )
        )
    )

    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=search_engine)
    deals = await adapter._search_community("rtx 5090", timeout=5)

    assert len(deals) > 0
    assert deals[0].source_type == "community"
    assert deals[0].price == 1499.99
    assert search_engine.search.await_count == 1


@pytest.mark.asyncio
async def test_search_store_returns_empty_on_unsuccessful_toolresult(monkeypatch: pytest.MonkeyPatch) -> None:
    """_search_store should degrade gracefully on ToolResult.success=False."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_settings())

    search_engine = AsyncMock()
    search_engine.search = AsyncMock(return_value=ToolResult.error("Rate limited"))

    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=search_engine)
    deals = await adapter._search_store("rtx 5090 site:amazon.com", "amazon.com", timeout=5)

    assert deals == []


@pytest.mark.asyncio
async def test_search_community_returns_empty_on_unsuccessful_toolresult(monkeypatch: pytest.MonkeyPatch) -> None:
    """_search_community should degrade gracefully on ToolResult.success=False."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_settings())

    search_engine = AsyncMock()
    search_engine.search = AsyncMock(return_value=ToolResult.error("Rate limited"))

    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=search_engine)
    deals = await adapter._search_community("rtx 5090", timeout=5)

    assert deals == []


@pytest.mark.asyncio
async def test_search_deals_sets_search_unavailable_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_deals should classify missing search engine as SEARCH_UNAVAILABLE."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_search_deals_settings())

    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=None)
    comparison = await adapter.search_deals("rtx 5090")

    assert comparison.empty_reason == EmptyReason.SEARCH_UNAVAILABLE
    assert comparison.error is None


@pytest.mark.asyncio
async def test_search_deals_sets_all_store_failures_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """If every store errors, search_deals should classify ALL_STORE_FAILURES."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_search_deals_settings())
    monkeypatch.setattr(adapter_module, "aggregate_coupons", AsyncMock(return_value=([], [])))

    search_engine = AsyncMock()
    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=search_engine)
    adapter._search_store = AsyncMock(side_effect=RuntimeError("provider timeout"))  # type: ignore[method-assign]

    comparison = await adapter.search_deals("rtx 5090", stores=["amazon.com", "walmart.com"])

    assert comparison.deals == []
    assert comparison.empty_reason == EmptyReason.ALL_STORE_FAILURES
    assert len(comparison.store_errors) == 2


@pytest.mark.asyncio
async def test_search_deals_sets_no_matches_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no deals and not all stores fail, search_deals should classify NO_MATCHES."""
    monkeypatch.setattr(adapter_module, "get_settings", lambda: _mock_search_deals_settings())
    monkeypatch.setattr(adapter_module, "aggregate_coupons", AsyncMock(return_value=([], [])))

    search_engine = AsyncMock()
    adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=search_engine)
    adapter._search_store = AsyncMock(return_value=[])  # type: ignore[method-assign]

    comparison = await adapter.search_deals("rtx 5090", stores=["amazon.com", "walmart.com"])

    assert comparison.deals == []
    assert comparison.empty_reason == EmptyReason.NO_MATCHES
