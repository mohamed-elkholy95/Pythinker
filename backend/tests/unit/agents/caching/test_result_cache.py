"""Tests for ResultCache and CachedResult."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.services.agents.caching.result_cache import (
    DEFAULT_TTLS,
    CachedResult,
    CacheStatistics,
    ResultCache,
    get_result_cache,
    reset_result_cache,
)

# ---------------------------------------------------------------------------
# CachedResult dataclass
# ---------------------------------------------------------------------------


class TestCachedResult:
    def test_defaults(self):
        cr = CachedResult(
            cache_key="k",
            tool_name="search",
            result_data={"foo": "bar"},
            result_hash="abc123",
        )
        assert cr.hit_count == 0
        assert cr.last_hit is None
        assert cr.metadata == {}
        assert isinstance(cr.created_at, datetime)
        assert isinstance(cr.expires_at, datetime)

    def test_is_expired_false(self):
        cr = CachedResult(
            cache_key="k",
            tool_name="t",
            result_data="r",
            result_hash="h",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert cr.is_expired() is False

    def test_is_expired_true(self):
        cr = CachedResult(
            cache_key="k",
            tool_name="t",
            result_data="r",
            result_hash="h",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert cr.is_expired() is True

    def test_is_valid_mirrors_expired(self):
        cr = CachedResult(
            cache_key="k",
            tool_name="t",
            result_data="r",
            result_hash="h",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert cr.is_valid() is True

    def test_record_hit(self):
        cr = CachedResult(
            cache_key="k",
            tool_name="t",
            result_data="r",
            result_hash="h",
        )
        cr.record_hit()
        assert cr.hit_count == 1
        assert cr.last_hit is not None
        cr.record_hit()
        assert cr.hit_count == 2


# ---------------------------------------------------------------------------
# CacheStatistics
# ---------------------------------------------------------------------------


class TestCacheStatistics:
    def test_defaults(self):
        s = CacheStatistics()
        assert s.total_entries == 0
        assert s.total_hits == 0
        assert s.total_misses == 0
        assert s.total_evictions == 0

    def test_hit_rate_zero(self):
        s = CacheStatistics()
        assert s.hit_rate == 0.0

    def test_hit_rate_computed(self):
        s = CacheStatistics(total_hits=3, total_misses=7)
        assert s.hit_rate == pytest.approx(0.3)

    def test_hit_rate_all_hits(self):
        s = CacheStatistics(total_hits=10, total_misses=0)
        assert s.hit_rate == 1.0


# ---------------------------------------------------------------------------
# ResultCache
# ---------------------------------------------------------------------------


class TestResultCache:
    def test_init_defaults(self):
        cache = ResultCache()
        assert cache._max_entries == 1000
        assert "search" in cache._ttls
        assert "default" in cache._ttls

    def test_init_custom_ttls(self):
        cache = ResultCache(custom_ttls={"my_tool": 999})
        assert cache._ttls["my_tool"] == 999
        assert cache._ttls["search"] == DEFAULT_TTLS["search"]

    def test_init_custom_max_entries(self):
        cache = ResultCache(max_entries=50)
        assert cache._max_entries == 50

    def test_put_and_get(self):
        cache = ResultCache()
        cache.put("search", {"q": "test"}, "search result")
        result = cache.get("search", {"q": "test"})
        assert result == "search result"

    def test_get_miss_returns_none(self):
        cache = ResultCache()
        assert cache.get("search", {"q": "missing"}) is None

    def test_get_expired_returns_none(self):
        cache = ResultCache()
        cached = cache.put("search", {"q": "test"}, "result")
        cached.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert cache.get("search", {"q": "test"}) is None

    def test_get_increments_hits(self):
        cache = ResultCache()
        cache.put("search", {"q": "t"}, "r")
        cache.get("search", {"q": "t"})
        assert cache._stats.total_hits == 1

    def test_get_miss_increments_misses(self):
        cache = ResultCache()
        cache.get("search", {"q": "nope"})
        assert cache._stats.total_misses == 1

    def test_put_returns_cached_result(self):
        cache = ResultCache()
        cr = cache.put("search", {"q": "t"}, "result")
        assert isinstance(cr, CachedResult)
        assert cr.tool_name == "search"

    def test_put_custom_ttl(self):
        cache = ResultCache()
        cr = cache.put("search", {"q": "t"}, "r", ttl_seconds=10)
        diff = (cr.expires_at - cr.created_at).total_seconds()
        assert 8 < diff < 12

    def test_put_too_large_returns_none(self):
        cache = ResultCache()
        huge = "x" * (ResultCache.MAX_ENTRY_SIZE + 1)
        result = cache.put("search", {"q": "t"}, huge)
        assert result is None

    def test_put_evicts_when_full(self):
        cache = ResultCache(max_entries=2)
        cache.put("t1", {"a": 1}, "r1")
        cache.put("t2", {"a": 2}, "r2")
        cache.put("t3", {"a": 3}, "r3")
        assert len(cache._cache) == 2

    def test_put_with_metadata(self):
        cache = ResultCache()
        cr = cache.put("search", {"q": "t"}, "r", metadata={"source": "web"})
        assert cr.metadata == {"source": "web"}

    def test_invalidate_specific(self):
        cache = ResultCache()
        cache.put("search", {"q": "a"}, "r1")
        cache.put("search", {"q": "b"}, "r2")
        removed = cache.invalidate("search", {"q": "a"})
        assert removed == 1
        assert cache.get("search", {"q": "a"}) is None
        assert cache.get("search", {"q": "b"}) == "r2"

    def test_invalidate_all_for_tool(self):
        cache = ResultCache()
        cache.put("search", {"q": "a"}, "r1")
        cache.put("search", {"q": "b"}, "r2")
        cache.put("file_read", {"path": "x"}, "r3")
        removed = cache.invalidate("search")
        assert removed == 2
        assert cache.get("file_read", {"path": "x"}) == "r3"

    def test_invalidate_missing(self):
        cache = ResultCache()
        removed = cache.invalidate("search", {"q": "nope"})
        assert removed == 0

    def test_invalidate_pattern(self):
        cache = ResultCache()
        cache.put("web_search", {"q": "a"}, "r1")
        cache.put("file_search", {"q": "b"}, "r2")
        cache.put("file_read", {"p": "c"}, "r3")
        removed = cache.invalidate_pattern("search")
        assert removed == 2
        assert len(cache._cache) == 1

    def test_clear(self):
        cache = ResultCache()
        cache.put("t1", {"a": 1}, "r1")
        cache.put("t2", {"a": 2}, "r2")
        count = cache.clear()
        assert count == 2
        assert len(cache._cache) == 0
        assert cache._stats.total_entries == 0

    def test_cleanup_expired(self):
        cache = ResultCache()
        cr1 = cache.put("t1", {"a": 1}, "r1")
        cache.put("t2", {"a": 2}, "r2")
        cr1.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        removed = cache.cleanup_expired()
        assert removed == 1
        assert len(cache._cache) == 1

    def test_get_statistics(self):
        cache = ResultCache()
        cache.put("search", {"q": "a"}, "r")
        cache.get("search", {"q": "a"})
        cache.get("search", {"q": "missing"})
        stats = cache.get_statistics()
        assert stats["total_entries"] == 1
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["hit_rate"] == pytest.approx(0.5)
        assert stats["entries_by_tool"] == {"search": 1}

    def test_generate_key_deterministic(self):
        cache = ResultCache()
        k1 = cache._generate_key("search", {"q": "a", "n": 10})
        k2 = cache._generate_key("search", {"n": 10, "q": "a"})
        assert k1 == k2

    def test_generate_key_different_for_different_args(self):
        cache = ResultCache()
        k1 = cache._generate_key("search", {"q": "a"})
        k2 = cache._generate_key("search", {"q": "b"})
        assert k1 != k2

    def test_get_ttl_exact_match(self):
        cache = ResultCache(custom_ttls={"my_tool": 42})
        assert cache._get_ttl("my_tool") == 42

    def test_get_ttl_category_match(self):
        cache = ResultCache()
        assert cache._get_ttl("info_search_web") == DEFAULT_TTLS["search"]

    def test_get_ttl_default_fallback(self):
        cache = ResultCache()
        assert cache._get_ttl("completely_unknown_tool") == DEFAULT_TTLS["default"]

    def test_evict_lru_removes_oldest(self):
        cache = ResultCache(max_entries=2)
        cr1 = cache.put("t1", {"a": 1}, "r1")
        cr1.last_hit = datetime.now(UTC) - timedelta(hours=2)
        cr2 = cache.put("t2", {"a": 2}, "r2")
        cr2.last_hit = datetime.now(UTC)
        # Third put triggers eviction of cr1
        cache.put("t3", {"a": 3}, "r3")
        assert cache.get("t1", {"a": 1}) is None

    def test_count_by_tool(self):
        cache = ResultCache()
        cache.put("search", {"q": "a"}, "r1")
        cache.put("search", {"q": "b"}, "r2")
        cache.put("file_read", {"p": "c"}, "r3")
        counts = cache._count_by_tool()
        assert counts["search"] == 2
        assert counts["file_read"] == 1


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_result_cache()

    def teardown_method(self):
        reset_result_cache()

    def test_get_result_cache_returns_same_instance(self):
        c1 = get_result_cache()
        c2 = get_result_cache()
        assert c1 is c2

    def test_reset_result_cache_creates_new(self):
        c1 = get_result_cache()
        reset_result_cache()
        c2 = get_result_cache()
        assert c1 is not c2

    def test_get_result_cache_custom_ttls(self):
        c = get_result_cache(custom_ttls={"custom": 999})
        assert c._ttls["custom"] == 999
