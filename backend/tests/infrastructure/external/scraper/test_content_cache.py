"""Tests for ContentCache."""

import pytest

from app.domain.external.stealth_types import FetchResult, StealthMode
from app.infrastructure.external.scraper.content_cache import ContentCache


class _FakeRedisCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.last_set: tuple[str, object, int | None] | None = None

    async def set(self, key: str, value: object, ttl: int | None = None) -> bool:
        self.last_set = (key, value, ttl)
        self.values[key] = value
        return True

    async def get(self, key: str) -> object | None:
        return self.values.get(key)

    async def delete(self, key: str) -> bool:
        return self.values.pop(key, None) is not None

    async def clear_pattern(self, pattern: str) -> int:
        count = len(self.values)
        self.values.clear()
        return count


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

    @pytest.mark.asyncio
    async def test_l2_cache_serializes_enum_values_and_restores_them(self) -> None:
        redis_cache = _FakeRedisCache()
        cache = ContentCache(
            l1_max_size=10,
            l2_ttl=60,
            include_mode_in_key=True,
            redis_client=redis_cache,
        )
        result = _make_result(mode=StealthMode.STEALTH)

        await cache.set("https://example.com", StealthMode.STEALTH, result)

        assert redis_cache.last_set is not None
        _, stored_value, _ = redis_cache.last_set
        assert isinstance(stored_value, dict)
        assert stored_value["mode_used"] == "stealth"

        restored = await cache.get("https://example.com", StealthMode.STEALTH)
        assert restored is not None
        assert restored["mode_used"] == StealthMode.STEALTH
