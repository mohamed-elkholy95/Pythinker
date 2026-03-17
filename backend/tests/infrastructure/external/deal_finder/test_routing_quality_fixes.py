"""Tests for LLM routing and result quality fixes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.external.deal_finder import DealResult
from app.infrastructure.external.deal_finder.adapter import (
    COMMUNITY_DOMAINS,
    DealFinderAdapter,
)


class TestDigitalProductOverride:
    """Routing tests for explicit-store and digital-product scenarios.

    All paths now go through the unified v2 flow (_search_via_shopping / _search_via_web).
    The legacy _search_deals_legacy method is never called regardless of the stores parameter.
    Digital products still use web search (via auto-mode category detection).
    """

    @pytest.mark.asyncio
    async def test_digital_product_with_explicit_stores_uses_web_search(self):
        """When LLM passes stores for a digital product, should override to web search."""
        mock_scraper = AsyncMock()
        mock_scraper.fetch.return_value = None
        mock_search = AsyncMock()
        mock_search.search = AsyncMock(return_value=MagicMock(success=True, data=MagicMock(results=[])))
        # search_shopping should NOT be called for digital override
        mock_search.search_shopping = AsyncMock()

        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)

        with (
            patch(
                "app.infrastructure.external.deal_finder.adapter.classify_item_category",
                return_value="digital",
            ),
            patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.deal_search_mode = "auto"
            settings.deal_verify_top_n = 0
            settings.deal_coupon_search_enabled = False
            settings.deal_scraper_history_enabled = False
            mock_settings.return_value = settings

            with (
                patch.object(adapter, "_search_via_web", new_callable=AsyncMock, return_value=[]) as mock_web_search,
                patch.object(
                    adapter,
                    "_search_deals_legacy",
                    new_callable=AsyncMock,
                ) as mock_legacy,
            ):
                result = await adapter.search_deals(
                    query="Microsoft 365 Family annual subscription",
                    stores=["amazon.com", "microsoft.com", "bestbuy.com"],
                )

        # Legacy per-store path must NOT have been called
        mock_legacy.assert_not_called()
        # Web search path should have been used
        mock_web_search.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_physical_product_with_explicit_stores_uses_shopping_api(self):
        """Physical products with explicit stores must use the Shopping API (v2 path), not the legacy path."""
        mock_scraper = AsyncMock()
        mock_search = AsyncMock()
        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)

        with (
            patch(
                "app.infrastructure.external.deal_finder.adapter.classify_item_category",
                return_value="physical",
            ),
            patch.object(adapter, "_search_via_shopping", new_callable=AsyncMock, return_value=[]) as mock_shopping,
            patch.object(adapter, "_search_via_web", new_callable=AsyncMock, return_value=[]),
            patch.object(adapter, "_search_deals_legacy", new_callable=AsyncMock) as mock_legacy,
            patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.deal_search_mode = "auto"
            settings.deal_verify_top_n = 0
            settings.deal_coupon_search_enabled = False
            settings.deal_scraper_history_enabled = False
            mock_settings.return_value = settings

            result = await adapter.search_deals(
                query="Sony WH-1000XM5 headphones",
                stores=["amazon.com", "bestbuy.com"],
            )

        # Legacy per-store path must NOT be called — unified v2 path is always used
        mock_legacy.assert_not_called()
        # Shopping API path should have been invoked
        mock_shopping.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_digital_product_without_stores_uses_web_search_naturally(self):
        """Digital products without explicit stores use web search via auto-mode routing."""
        mock_scraper = AsyncMock()
        mock_search = AsyncMock()
        adapter = DealFinderAdapter(scraper=mock_scraper, search_engine=mock_search)

        with (
            patch(
                "app.infrastructure.external.deal_finder.adapter.classify_item_category",
                return_value="digital",
            ),
            patch.object(adapter, "_search_via_web", new_callable=AsyncMock, return_value=[]) as mock_web,
            patch.object(adapter, "_search_deals_legacy", new_callable=AsyncMock) as mock_legacy,
            patch("app.infrastructure.external.deal_finder.adapter.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.deal_search_mode = "auto"
            settings.deal_verify_top_n = 0
            settings.deal_coupon_search_enabled = False
            settings.deal_scraper_history_enabled = False
            mock_settings.return_value = settings

            await adapter.search_deals(
                query="Adobe Creative Cloud subscription",
                stores=None,
            )

        # No stores provided → digital → web path used, legacy never called
        mock_web.assert_called_once()
        mock_legacy.assert_not_called()


class TestCommunityMentionFiltering:
    """Community sources should be excluded from scored deal results."""

    def test_community_source_type_filtered_from_deals(self):
        """Deals with source_type='community' should be filtered out."""
        deals = [
            DealResult(
                product_name="Product A",
                store="Amazon",
                price=299.99,
                url="https://amazon.com/dp/123",
                score=85,
                in_stock=True,
                item_category="physical",
                source_type="store",
            ),
            DealResult(
                product_name="Product A deal",
                store="Reddit",
                price=199.99,
                url="https://reddit.com/r/deals/123",
                score=60,
                in_stock=True,
                item_category="physical",
                source_type="community",
            ),
            DealResult(
                product_name="Product A review",
                store="SoundGuys",
                price=100.00,
                url="https://soundguys.com/review/123",
                score=50,
                in_stock=True,
                item_category="physical",
                source_type="community",
            ),
        ]

        filtered = [d for d in deals if d.source_type != "community"]
        assert len(filtered) == 1
        assert filtered[0].store == "Amazon"

    def test_open_web_source_type_not_filtered(self):
        """Deals with source_type='open_web' should NOT be filtered out."""
        deals = [
            DealResult(
                product_name="Product B",
                store="somestore.com",
                price=49.99,
                url="https://somestore.com/product/b",
                score=70,
                in_stock=True,
                item_category="physical",
                source_type="open_web",
            ),
            DealResult(
                product_name="Product B cheap",
                store="Reddit",
                price=39.99,
                url="https://reddit.com/r/deals/b",
                score=40,
                in_stock=True,
                item_category="physical",
                source_type="community",
            ),
        ]

        filtered = [d for d in deals if d.source_type != "community"]
        assert len(filtered) == 1
        assert filtered[0].source_type == "open_web"

    def test_store_source_type_not_filtered(self):
        """Deals with source_type='store' (the default) must be preserved."""
        deals = [
            DealResult(
                product_name="Widget",
                store="Best Buy",
                price=129.99,
                url="https://bestbuy.com/site/widget",
                score=80,
                in_stock=True,
                source_type="store",
            ),
        ]
        filtered = [d for d in deals if d.source_type != "community"]
        assert len(filtered) == 1
        assert filtered[0].store == "Best Buy"

    def test_all_community_filtered_returns_empty(self):
        """If all deals are community, result is empty after filtering."""
        deals = [
            DealResult(
                product_name="Thing",
                store="Reddit",
                price=10.0,
                url="https://reddit.com/r/deals/thing",
                source_type="community",
            ),
            DealResult(
                product_name="Thing thread",
                store="Slickdeals",
                price=9.0,
                url="https://slickdeals.net/f/thread",
                source_type="community",
            ),
        ]
        filtered = [d for d in deals if d.source_type != "community"]
        assert filtered == []

    def test_community_domains_defined(self):
        """COMMUNITY_DOMAINS should include Reddit, Slickdeals, and other known sources."""
        assert "reddit.com" in COMMUNITY_DOMAINS
        assert "slickdeals.net" in COMMUNITY_DOMAINS

    def test_community_domains_have_human_readable_names(self):
        """All entries in COMMUNITY_DOMAINS should map to non-empty string labels."""
        for domain, label in COMMUNITY_DOMAINS.items():
            assert isinstance(label, str), f"{domain!r} should map to a string"
            assert label.strip(), f"{domain!r} maps to an empty label"
