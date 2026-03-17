"""Test URL deduplication in verification scrape."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.external.deal_finder import DealResult
from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter


def _make_deal(url: str, store: str = "Store", price: float = 99.0, i: int = 0) -> DealResult:
    return DealResult(
        product_name=f"Product {i}",
        store=store,
        price=price,
        url=url,
        score=80 - i,
        in_stock=True,
        item_category="physical",
        source_type="store",
    )


class TestVerifyDedup:
    @pytest.mark.asyncio
    async def test_duplicate_urls_only_scraped_once(self):
        """Same URL appearing in multiple deals should only be scraped once."""
        fetch_count = 0

        async def counting_fetch(url: str, **kwargs):  # type: ignore[return]
            nonlocal fetch_count
            fetch_count += 1
            return  # trigger AttributeError → caught by except block

        mock_scraper = MagicMock()
        mock_scraper.fetch = counting_fetch

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=AsyncMock())

        # 3 deals all pointing to the same URL
        deals = [_make_deal("https://same-store.com/product/123", store=f"Store {i}", i=i) for i in range(3)]

        result = await adapter._verify_top_deals(deals, top_n=3, timeout=5.0)

        assert fetch_count <= 1, f"Same URL scraped {fetch_count} times instead of ≤1"
        assert len(result) == 3  # All deals preserved

    @pytest.mark.asyncio
    async def test_unique_urls_each_scraped(self):
        """Distinct URLs should each be scraped exactly once."""
        fetched_urls: list[str] = []

        async def tracking_fetch(url: str, **kwargs):  # type: ignore[return]
            fetched_urls.append(url)
            return  # trigger exception path

        mock_scraper = MagicMock()
        mock_scraper.fetch = tracking_fetch

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=AsyncMock())

        deals = [_make_deal(f"https://store-{i}.com/product", store=f"Store {i}", i=i) for i in range(3)]

        result = await adapter._verify_top_deals(deals, top_n=3, timeout=5.0)

        assert len(fetched_urls) == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_google_redirect_urls_skipped(self):
        """Google Shopping redirect URLs must not be scraped."""
        fetch_count = 0

        async def counting_fetch(url: str, **kwargs):  # type: ignore[return]
            nonlocal fetch_count
            fetch_count += 1
            return

        mock_scraper = MagicMock()
        mock_scraper.fetch = counting_fetch

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=AsyncMock())

        deals = [
            _make_deal("https://www.google.com/aclk?sa=L&ai=abc", i=0),
            _make_deal("https://www.google.com/search?q=test", i=1),
        ]

        result = await adapter._verify_top_deals(deals, top_n=2, timeout=5.0)

        assert fetch_count == 0, "Google redirect URLs should not be scraped"
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_deals_returns_empty(self):
        """Empty input list should return empty list without errors."""
        mock_scraper = MagicMock()
        mock_scraper.fetch = AsyncMock()

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=AsyncMock())

        result = await adapter._verify_top_deals([], top_n=5, timeout=5.0)

        assert result == []
        mock_scraper.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_remainder_deals_not_scraped(self):
        """Deals beyond top_n should be returned unchanged without scraping."""
        fetched_urls: list[str] = []

        async def tracking_fetch(url: str, **kwargs):  # type: ignore[return]
            fetched_urls.append(url)
            return

        mock_scraper = MagicMock()
        mock_scraper.fetch = tracking_fetch

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=AsyncMock())

        deals = [_make_deal(f"https://store-{i}.com/product", store=f"Store {i}", i=i) for i in range(5)]

        result = await adapter._verify_top_deals(deals, top_n=2, timeout=5.0)

        assert len(fetched_urls) == 2
        assert len(result) == 5  # top 2 verified + 3 unchanged


class TestSearchViaShoppingCheckpoint:
    @pytest.mark.asyncio
    async def test_progress_callback_receives_store_checkpoint(self):
        """progress callback should receive store counts grouped by store name."""
        mock_search_engine = MagicMock()
        mock_search_engine.search_shopping = AsyncMock()

        # Build mock shopping items
        shopping_item_a = MagicMock()
        shopping_item_a.price = 49.99
        shopping_item_a.source = "Amazon"
        shopping_item_a.link = "https://amazon.com/dp/B001"
        shopping_item_a.title = "Widget A"
        shopping_item_a.image_url = None

        shopping_item_b = MagicMock()
        shopping_item_b.price = 55.00
        shopping_item_b.source = "Amazon"
        shopping_item_b.link = "https://amazon.com/dp/B002"
        shopping_item_b.title = "Widget B"
        shopping_item_b.image_url = None

        shopping_item_c = MagicMock()
        shopping_item_c.price = 52.00
        shopping_item_c.source = "BestBuy"
        shopping_item_c.link = "https://bestbuy.com/sku/123"
        shopping_item_c.title = "Widget C"
        shopping_item_c.image_url = None

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.data = [shopping_item_a, shopping_item_b, shopping_item_c]

        mock_search_engine.search_shopping.return_value = tool_result

        adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=mock_search_engine)

        progress_calls: list[tuple] = []

        async def capture_progress(msg: str, completed: int, total: int | None, checkpoint_data: dict | None) -> None:
            progress_calls.append((msg, completed, total, checkpoint_data))

        result = await adapter._search_via_shopping("widget", progress=capture_progress)

        assert len(result) == 3
        assert len(progress_calls) == 1

        msg, completed, total, checkpoint_data = progress_calls[0]
        assert "3 deals" in msg
        assert completed == 3
        assert total == 3
        assert checkpoint_data is not None

        store_statuses = checkpoint_data["store_statuses"]
        store_map = {s["store"]: s["result_count"] for s in store_statuses}
        assert store_map["Amazon"] == 2
        assert store_map["BestBuy"] == 1
        assert checkpoint_data["query"] == "widget"

    @pytest.mark.asyncio
    async def test_progress_not_called_when_no_deals(self):
        """progress callback must not be called when search returns no results."""
        mock_search_engine = MagicMock()
        mock_search_engine.search_shopping = AsyncMock()

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.data = []  # empty

        mock_search_engine.search_shopping.return_value = tool_result

        adapter = DealFinderAdapter(scraper=AsyncMock(), search_engine=mock_search_engine)

        progress_mock = AsyncMock()

        result = await adapter._search_via_shopping("widget", progress=progress_mock)

        assert result == []
        progress_mock.assert_not_called()
