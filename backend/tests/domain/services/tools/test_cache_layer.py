"""Tests for tool result caching layer (L1Cache, ToolCacheConfig, ToolCacheStats, helpers)."""

import time

from app.domain.services.tools.cache_layer import (
    L1Cache,
    L1CacheEntry,
    ToolCacheConfig,
    ToolCacheStats,
    _generate_cache_key,
    _get_tool_ttl,
    _should_cache_tool,
    get_cache_config,
    get_combined_cache_stats,
    set_cache_config,
)

# ---------------------------------------------------------------------------
# L1CacheEntry
# ---------------------------------------------------------------------------


class TestL1CacheEntryIsExpired:
    def test_fresh_entry_is_not_expired(self) -> None:
        entry = L1CacheEntry(value="data", created_at=time.time(), ttl=300)
        assert entry.is_expired() is False

    def test_old_entry_is_expired(self) -> None:
        # created_at far in the past
        entry = L1CacheEntry(value="data", created_at=time.time() - 400, ttl=300)
        assert entry.is_expired() is True

    def test_entry_at_exact_ttl_boundary_is_expired(self, monkeypatch) -> None:
        # is_expired uses >  (strict greater-than), so age == ttl is NOT expired
        now = 1_000_000.0
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now)
        entry = L1CacheEntry(value="x", created_at=now - 300, ttl=300)
        # age == ttl → not expired (time.time() - created_at == ttl, not > ttl)
        assert entry.is_expired() is False

    def test_entry_one_second_past_ttl_is_expired(self, monkeypatch) -> None:
        now = 1_000_000.0
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now)
        entry = L1CacheEntry(value="x", created_at=now - 301, ttl=300)
        assert entry.is_expired() is True

    def test_default_hits_is_zero(self) -> None:
        entry = L1CacheEntry(value=42, created_at=time.time(), ttl=60)
        assert entry.hits == 0


# ---------------------------------------------------------------------------
# L1Cache
# ---------------------------------------------------------------------------


class TestL1CacheGet:
    def test_get_returns_none_for_missing_key(self) -> None:
        cache = L1Cache()
        assert cache.get("no-such-key") is None

    def test_get_returns_value_for_existing_key(self) -> None:
        cache = L1Cache()
        cache.set("k", {"result": True})
        assert cache.get("k") == {"result": True}

    def test_get_increments_hits_counter(self) -> None:
        cache = L1Cache()
        cache.set("k", "v")
        cache.get("k")
        assert cache._hits == 1

    def test_get_increments_misses_for_missing_key(self) -> None:
        cache = L1Cache()
        cache.get("missing")
        assert cache._misses == 1

    def test_get_removes_and_misses_expired_entry(self, monkeypatch) -> None:
        cache = L1Cache()
        now = 1_000_000.0
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now)
        cache.set("k", "v", ttl=10)

        # Advance time past TTL
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now + 20)
        result = cache.get("k")

        assert result is None
        assert "k" not in cache._cache
        assert cache._misses == 1

    def test_get_increments_entry_hits(self) -> None:
        cache = L1Cache()
        cache.set("k", "v")
        cache.get("k")
        cache.get("k")
        assert cache._cache["k"].hits == 2


class TestL1CacheSet:
    def test_set_stores_value(self) -> None:
        cache = L1Cache()
        cache.set("key", [1, 2, 3])
        assert cache._cache["key"].value == [1, 2, 3]

    def test_set_uses_custom_ttl(self) -> None:
        cache = L1Cache(default_ttl=600)
        cache.set("key", "v", ttl=30)
        assert cache._cache["key"].ttl == 30

    def test_set_uses_default_ttl_when_none(self) -> None:
        cache = L1Cache(default_ttl=600)
        cache.set("key", "v")
        assert cache._cache["key"].ttl == 600

    def test_set_triggers_eviction_at_capacity(self) -> None:
        cache = L1Cache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Fourth entry must trigger eviction; cache should stay within max_size
        cache.set("d", 4)
        assert len(cache._cache) <= 3


class TestL1CacheDelete:
    def test_delete_existing_key_returns_true(self) -> None:
        cache = L1Cache()
        cache.set("k", "v")
        assert cache.delete("k") is True

    def test_delete_existing_key_removes_entry(self) -> None:
        cache = L1Cache()
        cache.set("k", "v")
        cache.delete("k")
        assert "k" not in cache._cache

    def test_delete_missing_key_returns_false(self) -> None:
        cache = L1Cache()
        assert cache.delete("ghost") is False


class TestL1CacheClear:
    def test_clear_returns_count(self) -> None:
        cache = L1Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.clear() == 3

    def test_clear_empties_cache(self) -> None:
        cache = L1Cache()
        cache.set("a", 1)
        cache.clear()
        assert len(cache._cache) == 0

    def test_clear_on_empty_cache_returns_zero(self) -> None:
        cache = L1Cache()
        assert cache.clear() == 0


class TestL1CacheGetStats:
    def test_stats_initial_state(self) -> None:
        cache = L1Cache(max_size=100)
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_reflect_hits_and_misses(self) -> None:
        cache = L1Cache()
        cache.set("k", "v")
        cache.get("k")  # hit
        cache.get("missing")  # miss
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_stats_size_matches_entries(self) -> None:
        cache = L1Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.get_stats()["size"] == 2


class TestL1CacheEvictLru:
    def test_eviction_prefers_expired_entries(self, monkeypatch) -> None:
        now = 1_000_000.0
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now)

        cache = L1Cache(max_size=2)
        cache.set("old", "value", ttl=5)  # will be expired
        cache.set("new", "value", ttl=600)  # still fresh

        # Advance time so "old" expires
        monkeypatch.setattr("app.domain.services.tools.cache_layer.time.time", lambda: now + 10)

        # Adding a third entry triggers eviction
        cache.set("another", "value", ttl=600)

        # "old" should have been removed (expired); "new" and "another" survive
        assert "old" not in cache._cache


# ---------------------------------------------------------------------------
# ToolCacheConfig
# ---------------------------------------------------------------------------


class TestToolCacheConfig:
    def test_defaults(self) -> None:
        config = ToolCacheConfig()
        assert config.enabled is True
        assert config.default_ttl == 3600
        assert config.max_key_size == 10000

    def test_exclude_tools_contains_write_operations(self) -> None:
        config = ToolCacheConfig()
        assert "file_write" in config.exclude_tools
        assert "shell_execute" in config.exclude_tools
        assert "browser_navigate" in config.exclude_tools
        assert "message_notify_user" in config.exclude_tools

    def test_ttl_by_tool_has_expected_entries(self) -> None:
        config = ToolCacheConfig()
        assert config.ttl_by_tool["file_read"] == 300
        assert config.ttl_by_tool["info_search_web"] == 1800
        assert config.ttl_by_tool["browser_extract"] == 600

    def test_custom_exclude_tools(self) -> None:
        config = ToolCacheConfig(exclude_tools={"my_tool"})
        assert "my_tool" in config.exclude_tools

    def test_disabled_config(self) -> None:
        config = ToolCacheConfig(enabled=False)
        assert config.enabled is False


# ---------------------------------------------------------------------------
# ToolCacheStats
# ---------------------------------------------------------------------------


class TestToolCacheStats:
    def test_initial_values_are_zero(self) -> None:
        stats = ToolCacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.skipped == 0
        assert stats.errors == 0

    def test_record_hit_increments_hits(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_hit()
        assert stats.hits == 2

    def test_record_miss_increments_misses(self) -> None:
        stats = ToolCacheStats()
        stats.record_miss()
        assert stats.misses == 1

    def test_record_skip_increments_skipped(self) -> None:
        stats = ToolCacheStats()
        stats.record_skip()
        stats.record_skip()
        assert stats.skipped == 2

    def test_record_error_increments_errors(self) -> None:
        stats = ToolCacheStats()
        stats.record_error()
        assert stats.errors == 1

    def test_hit_rate_zero_when_no_requests(self) -> None:
        stats = ToolCacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_hit()
        stats.record_miss()
        # 2 hits / 3 total
        assert abs(stats.hit_rate - 2 / 3) < 1e-9

    def test_hit_rate_all_hits(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_hit()
        assert stats.hit_rate == 1.0

    def test_to_dict_contains_all_fields(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_miss()
        stats.record_skip()
        stats.record_error()
        d = stats.to_dict()
        assert d["hits"] == 1
        assert d["misses"] == 1
        assert d["skipped"] == 1
        assert d["errors"] == 1
        assert "hit_rate" in d

    def test_to_dict_hit_rate_rounded(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_miss()
        stats.record_miss()
        # hit_rate = 1/3 ≈ 0.3333, rounded to 4 decimal places
        assert stats.to_dict()["hit_rate"] == round(1 / 3, 4)

    def test_reset_clears_all_counters(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.record_miss()
        stats.record_skip()
        stats.record_error()
        stats.reset()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.skipped == 0
        assert stats.errors == 0

    def test_hit_rate_after_reset_is_zero(self) -> None:
        stats = ToolCacheStats()
        stats.record_hit()
        stats.reset()
        assert stats.hit_rate == 0.0


# ---------------------------------------------------------------------------
# _generate_cache_key
# ---------------------------------------------------------------------------


class TestGenerateCacheKey:
    def test_key_is_deterministic(self) -> None:
        key1 = _generate_cache_key("file_read", {"path": "/tmp/x.txt"})
        key2 = _generate_cache_key("file_read", {"path": "/tmp/x.txt"})
        assert key1 == key2

    def test_key_prefixed_with_tool_name(self) -> None:
        key = _generate_cache_key("info_search_web", {"query": "hello"})
        assert key.startswith("tool:info_search_web:")

    def test_different_args_produce_different_keys(self) -> None:
        key_a = _generate_cache_key("file_read", {"path": "/a.txt"})
        key_b = _generate_cache_key("file_read", {"path": "/b.txt"})
        assert key_a != key_b

    def test_different_tool_names_produce_different_keys(self) -> None:
        key_a = _generate_cache_key("tool_a", {"x": 1})
        key_b = _generate_cache_key("tool_b", {"x": 1})
        assert key_a != key_b

    def test_none_values_are_filtered_out(self) -> None:
        key_with_none = _generate_cache_key("tool", {"a": "value", "b": None})
        key_without_none = _generate_cache_key("tool", {"a": "value"})
        # None-filtered key should equal key built without the None arg
        assert key_with_none == key_without_none

    def test_arg_order_does_not_affect_key(self) -> None:
        key1 = _generate_cache_key("tool", {"z": 1, "a": 2})
        key2 = _generate_cache_key("tool", {"a": 2, "z": 1})
        assert key1 == key2

    def test_key_truncated_when_args_exceed_max_key_size(self) -> None:
        # Override config to a tiny max_key_size
        original = get_cache_config()
        small_config = ToolCacheConfig(max_key_size=10)
        set_cache_config(small_config)
        try:
            # Large payload that will be truncated
            big_args = {"data": "x" * 10_000}
            key = _generate_cache_key("tool", big_args)
            # Key must still be generated without raising
            assert key.startswith("tool:tool:")
        finally:
            set_cache_config(original)


# ---------------------------------------------------------------------------
# _should_cache_tool
# ---------------------------------------------------------------------------


class TestShouldCacheTool:
    def test_returns_true_for_cacheable_tool(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig(enabled=True))
        try:
            assert _should_cache_tool("file_read") is True
        finally:
            set_cache_config(original)

    def test_returns_false_for_excluded_tool(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig(enabled=True))
        try:
            assert _should_cache_tool("file_write") is False
        finally:
            set_cache_config(original)

    def test_returns_false_when_cache_disabled(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig(enabled=False))
        try:
            assert _should_cache_tool("file_read") is False
        finally:
            set_cache_config(original)

    def test_returns_false_for_shell_execute(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig(enabled=True))
        try:
            assert _should_cache_tool("shell_execute") is False
        finally:
            set_cache_config(original)

    def test_unknown_tool_is_cacheable_by_default(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig(enabled=True))
        try:
            assert _should_cache_tool("some_custom_tool") is True
        finally:
            set_cache_config(original)


# ---------------------------------------------------------------------------
# _get_tool_ttl
# ---------------------------------------------------------------------------


class TestGetToolTtl:
    def test_returns_specific_ttl_for_known_tool(self) -> None:
        original = get_cache_config()
        set_cache_config(ToolCacheConfig())
        try:
            assert _get_tool_ttl("file_read") == 300
            assert _get_tool_ttl("info_search_web") == 1800
            assert _get_tool_ttl("mcp_call_tool") == 900
        finally:
            set_cache_config(original)

    def test_returns_default_ttl_for_unknown_tool(self) -> None:
        original = get_cache_config()
        config = ToolCacheConfig(default_ttl=9999)
        set_cache_config(config)
        try:
            assert _get_tool_ttl("unknown_tool_xyz") == 9999
        finally:
            set_cache_config(original)

    def test_custom_ttl_by_tool_overrides_default(self) -> None:
        original = get_cache_config()
        config = ToolCacheConfig(
            default_ttl=3600,
            ttl_by_tool={"special_tool": 42},
        )
        set_cache_config(config)
        try:
            assert _get_tool_ttl("special_tool") == 42
        finally:
            set_cache_config(original)


# ---------------------------------------------------------------------------
# get_combined_cache_stats
# ---------------------------------------------------------------------------


class TestGetCombinedCacheStats:
    def test_returns_l1_l2_and_combined_keys(self) -> None:
        result = get_combined_cache_stats()
        assert "l1" in result
        assert "l2" in result
        assert "combined" in result

    def test_combined_section_has_required_fields(self) -> None:
        result = get_combined_cache_stats()
        combined = result["combined"]
        assert "total_hits" in combined
        assert "total_misses" in combined
        assert "combined_hit_rate" in combined

    def test_combined_hit_rate_is_float(self) -> None:
        result = get_combined_cache_stats()
        assert isinstance(result["combined"]["combined_hit_rate"], float)

    def test_l1_section_matches_l1_cache_stats_structure(self) -> None:
        result = get_combined_cache_stats()
        l1 = result["l1"]
        assert "hits" in l1
        assert "misses" in l1
        assert "hit_rate" in l1
        assert "size" in l1
        assert "max_size" in l1

    def test_combined_hit_rate_zero_when_no_requests(self) -> None:
        # Fresh stats objects give 0.0
        from app.domain.services.tools.cache_layer import _cache_stats, _l1_cache

        _l1_cache.clear()
        _l1_cache._hits = 0
        _l1_cache._misses = 0
        _cache_stats.reset()

        result = get_combined_cache_stats()
        assert result["combined"]["combined_hit_rate"] == 0.0
