"""Test that Slickdeals feed cache uses asyncio.Lock to prevent duplicate requests."""
from __future__ import annotations

import asyncio
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.domain.external.scraper import ScrapedContent
from app.infrastructure.external.deal_finder import coupon_aggregator
from app.infrastructure.external.deal_finder.coupon_aggregator import fetch_slickdeals_coupons


@contextmanager
def _stub_feedparser():
    """Inject a minimal feedparser stub so cache logic is exercised even when
    feedparser is not installed in the current environment."""

    class _FakeFeed:
        entries: list = []

    module = types.ModuleType("feedparser")
    module.parse = MagicMock(return_value=_FakeFeed())  # type: ignore[attr-defined]

    original = sys.modules.get("feedparser")
    sys.modules["feedparser"] = module
    try:
        yield module
    finally:
        if original is None:
            sys.modules.pop("feedparser", None)
        else:
            sys.modules["feedparser"] = original


class TestFeedCacheLock:
    @pytest.mark.asyncio
    async def test_concurrent_slickdeals_fetches_deduplicated(self):
        """10 concurrent calls should produce at most 4 HTTP requests, not 20.

        SLICKDEALS_FEEDS has 2 entries (frontpage + popular).
        With 10 concurrent coroutines and the per-URL lock, only the first
        coroutine per feed URL should actually fetch — the rest wait, then
        read from cache. So the maximum is 2 requests total (one per feed).
        The threshold of ≤4 gives headroom in case of a benign warm/cold split
        but still catches the unguarded race (which would yield 20 requests).
        """
        fetch_count = 0

        async def mock_fetch(url: str, **kwargs: object) -> ScrapedContent:
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.01)  # Simulate network latency to trigger concurrent access
            return ScrapedContent(
                success=True,
                url=url,
                text="<rss><channel></channel></rss>",
            )

        mock_scraper = MagicMock()
        mock_scraper.fetch = mock_fetch

        # Clear both caches to ensure a fresh race-condition test
        coupon_aggregator._feed_cache.clear()
        coupon_aggregator._feed_cache_locks.clear()

        with _stub_feedparser():
            tasks = [
                fetch_slickdeals_coupons(mock_scraper, f"store_{i}")
                for i in range(10)
            ]
            await asyncio.gather(*tasks)

        assert fetch_count <= 4, (
            f"Expected ≤4 HTTP requests but got {fetch_count} — "
            f"feed cache lock is not preventing duplicate fetches"
        )

    @pytest.mark.asyncio
    async def test_feed_cache_reused_after_first_fetch(self):
        """Second call for the same feed URL should not trigger another HTTP request."""
        fetch_count = 0

        async def mock_fetch(url: str, **kwargs: object) -> ScrapedContent:
            nonlocal fetch_count
            fetch_count += 1
            return ScrapedContent(
                success=True,
                url=url,
                text="<rss><channel></channel></rss>",
            )

        mock_scraper = MagicMock()
        mock_scraper.fetch = mock_fetch

        coupon_aggregator._feed_cache.clear()
        coupon_aggregator._feed_cache_locks.clear()

        with _stub_feedparser():
            await fetch_slickdeals_coupons(mock_scraper, "amazon")
            fetch_count_after_first = fetch_count

            await fetch_slickdeals_coupons(mock_scraper, "walmart")
            fetch_count_after_second = fetch_count

        # First call fetches both feeds (2 requests); second call reuses cache (0 new requests)
        assert fetch_count_after_first == 2, (
            f"First call should fetch exactly 2 feeds but fetched {fetch_count_after_first}"
        )
        assert fetch_count_after_second == 2, (
            f"Second call should reuse cache (no new fetches) but total is {fetch_count_after_second}"
        )

    @pytest.mark.asyncio
    async def test_failed_fetch_does_not_poison_cache(self):
        """A fetch that returns success=False should not populate the feed cache."""
        async def mock_fetch_fail(url: str, **kwargs: object) -> ScrapedContent:
            return ScrapedContent(success=False, url=url, text="")

        mock_scraper = MagicMock()
        mock_scraper.fetch = mock_fetch_fail

        coupon_aggregator._feed_cache.clear()
        coupon_aggregator._feed_cache_locks.clear()

        with _stub_feedparser():
            result = await fetch_slickdeals_coupons(mock_scraper, "bestbuy")

        assert result == [], "Failed fetches should return empty coupon list"
        assert len(coupon_aggregator._feed_cache) == 0, (
            "Failed fetches must not populate _feed_cache"
        )

    @pytest.mark.asyncio
    async def test_get_feed_lock_returns_same_lock_for_same_url(self):
        """_get_feed_lock should return the identical Lock instance for the same URL."""
        coupon_aggregator._feed_cache_locks.clear()

        url = "https://slickdeals.net/rss/test"
        lock_a = await coupon_aggregator._get_feed_lock(url)
        lock_b = await coupon_aggregator._get_feed_lock(url)

        assert lock_a is lock_b, "Same URL must always return the same Lock instance"

    @pytest.mark.asyncio
    async def test_get_feed_lock_returns_different_locks_for_different_urls(self):
        """_get_feed_lock should return distinct Lock instances for different URLs."""
        coupon_aggregator._feed_cache_locks.clear()

        lock_a = await coupon_aggregator._get_feed_lock("https://slickdeals.net/rss/frontpage")
        lock_b = await coupon_aggregator._get_feed_lock("https://slickdeals.net/rss/popular")

        assert lock_a is not lock_b, "Different URLs must get different Lock instances"
