"""Tests for ContentCache."""

import pytest

from app.domain.external.stealth_types import FetchResult, StealthMode
from app.infrastructure.external.scraper.content_cache import ContentCache


@pytest.fixture
def cache() -> ContentCache:
    return ContentCache(
        l1_max_size=10,
        l2_ttl=60,
        include_mode_in_key=True,
        redis_client=None,
    )


def _make_result(content: str = "<html>test</html>", mode: StealthMode = StealthMode.HTTP) -> FetchResult:
    return FetchResult(
        content=content,
        url="https://example.com",
        final_url="https://example.com",
        mode_used=mode,
        proxy_used=None,
        response_time_ms=100.0,
        from_cache=False,
        cloudflare_solved=False,
        error=None,
    )


class TestContentCache:
    """Test suite for ContentCache."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: ContentCache) -> None:
        """Test basic set and get operations."""
        result = _make_result()
        await cache.set("https://example.com", StealthMode.HTTP, result)

        cached = await cache.get("https://example.com", StealthMode.HTTP)

        assert cached is not None
        assert cached["content"] == "<html>test</html>"
        assert cached["mode_used"] == StealthMode.HTTP

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, cache: ContentCache) -> None:
        """Test that cache miss returns None."""
        cached = await cache.get("https://notcached.com", StealthMode.HTTP)
        assert cached is None

    @pytest.mark.asyncio
    async def test_different_modes_have_separate_cache(self, cache: ContentCache) -> None:
        """Test that different modes don't share cache entries."""
        result_http = _make_result(content="http content", mode=StealthMode.HTTP)
        result_stealth = _make_result(content="stealth content", mode=StealthMode.STEALTH)

        await cache.set("https://example.com", StealthMode.HTTP, result_http)
        await cache.set("https://example.com", StealthMode.STEALTH, result_stealth)

        cached_http = await cache.get("https://example.com", StealthMode.HTTP)
        cached_stealth = await cache.get("https://example.com", StealthMode.STEALTH)

        assert cached_http is not None
        assert cached_stealth is not None
        assert cached_http["content"] == "http content"
        assert cached_stealth["content"] == "stealth content"

    @pytest.mark.asyncio
    async def test_lru_eviction(self) -> None:
        """Test that LRU eviction works."""
        cache = ContentCache(l1_max_size=3, l2_ttl=60, include_mode_in_key=True, redis_client=None)

        for i in range(4):
            result = _make_result(content=f"content {i}")
            await cache.set(f"https://example{i}.com", StealthMode.HTTP, result)

        cached = await cache.get("https://example0.com", StealthMode.HTTP)
        assert cached is None

        for i in range(1, 4):
            cached = await cache.get(f"https://example{i}.com", StealthMode.HTTP)
            assert cached is not None

    @pytest.mark.asyncio
    async def test_invalidate_specific_url(self, cache: ContentCache) -> None:
        """Test invalidating a specific URL."""
        result = _make_result()
        await cache.set("https://example.com", StealthMode.HTTP, result)

        count = await cache.invalidate("https://example.com")
        assert count >= 1

        cached = await cache.get("https://example.com", StealthMode.HTTP)
        assert cached is None
