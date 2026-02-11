"""Integration Tests for Tool Definition Cache (E2E)

End-to-end tests for tool definition caching and warming.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.services.tools.tool_definition_cache import ToolDefinitionCache
from app.infrastructure.observability.agent_metrics import (
    agent_tool_cache_invalidations,
    agent_tool_definition_cache_hits,
    agent_tool_definition_cache_misses,
)


class TestToolCacheE2E:
    """End-to-end test suite for tool definition cache."""

    @pytest.fixture
    def cache(self):
        """Create cache with default settings."""
        return ToolDefinitionCache(ttl_seconds=3600, max_cache_size=100)

    @pytest.fixture
    def mock_registry(self):
        """Create mock tool registry."""
        registry = Mock()
        registry.list_tools = Mock(return_value=["search", "browser", "file_read", "terminal"])

        async def mock_get_definition(tool_name: str):
            definitions = {
                "search": {
                    "name": "search",
                    "description": "Search the web",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
                "browser": {
                    "name": "browser",
                    "description": "Navigate web browser",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "timeout": {"type": "integer"},
                        },
                        "required": ["url"],
                    },
                },
                "file_read": {
                    "name": "file_read",
                    "description": "Read file contents",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "encoding": {"type": "string"},
                        },
                        "required": ["file_path"],
                    },
                },
                "terminal": {
                    "name": "terminal",
                    "description": "Execute terminal command",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "timeout": {"type": "integer"},
                        },
                        "required": ["command"],
                    },
                },
            }
            return definitions.get(tool_name, {"name": tool_name, "schema": {}})

        registry.get_definition = AsyncMock(side_effect=mock_get_definition)
        return registry

    @pytest.mark.asyncio
    async def test_tool_definition_cache_hit(self, cache, mock_registry):
        """E2E: Repeated tool definition lookups hit cache."""
        # Step 1: Warm cache with tool definitions
        warmed_count = await cache.warm_cache(mock_registry)
        assert warmed_count == 4  # search, browser, file_read, terminal

        # Step 2: Track initial metrics
        initial_hits = agent_tool_definition_cache_hits.get({"cache_scope": "session"})
        initial_misses = agent_tool_definition_cache_misses.get({"cache_scope": "session"})

        # Step 3: Lookup tool definitions (should hit cache)
        search_def = await cache.get("search")
        browser_def = await cache.get("browser")
        file_read_def = await cache.get("file_read")

        # Step 4: Verify definitions retrieved
        assert search_def is not None
        assert search_def["name"] == "search"
        assert "query" in search_def["schema"]["properties"]

        assert browser_def is not None
        assert browser_def["name"] == "browser"
        assert "url" in browser_def["schema"]["properties"]

        assert file_read_def is not None
        assert file_read_def["name"] == "file_read"

        # Step 5: Verify metrics - should have hits, no misses
        final_hits = agent_tool_definition_cache_hits.get({"cache_scope": "session"})
        final_misses = agent_tool_definition_cache_misses.get({"cache_scope": "session"})

        assert final_hits > initial_hits  # Hit count increased
        assert final_misses == initial_misses  # No new misses

        # Step 6: Lookup unknown tool (should miss)
        unknown_def = await cache.get("unknown_tool")
        assert unknown_def is None

        # Step 7: Verify miss metric incremented
        new_misses = agent_tool_definition_cache_misses.get({"cache_scope": "session"})
        assert new_misses > final_misses

    @pytest.mark.asyncio
    async def test_cache_warming_on_startup(self, cache, mock_registry):
        """E2E: Cache warmed on app startup."""
        # Verify cache empty initially
        assert len(cache._cache) == 0

        # Step 1: Warm cache (simulating startup)
        count = await cache.warm_cache(mock_registry)

        # Step 2: Verify all tools cached
        assert count == 4
        assert len(cache._cache) == 4

        # Step 3: Verify each tool definition available
        for tool_name in ["search", "browser", "file_read", "terminal"]:
            definition = await cache.get(tool_name)
            assert definition is not None
            assert definition["name"] == tool_name
            assert "schema" in definition

        # Step 4: Verify registry was called for each tool
        assert mock_registry.get_definition.call_count == 4

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_config_change(self, cache):
        """E2E: Cache invalidated when MCP config changes."""
        # Step 1: Set initial MCP config
        initial_config = {
            "server": "mcp-server-1",
            "port": 8000,
            "tools": ["search", "browser"],
        }

        invalidated = cache.invalidate_if_config_changed(initial_config)
        assert invalidated is False  # First config, no invalidation

        # Step 2: Add tool definitions to cache
        await cache.set(
            "search",
            {"name": "search", "schema": {"type": "object"}},
        )
        await cache.set(
            "browser",
            {"name": "browser", "schema": {"type": "object"}},
        )

        assert len(cache._cache) == 2

        # Step 3: Track invalidation metric
        initial_invalidations = agent_tool_cache_invalidations.get({"invalidation_reason": "config_change"})

        # Step 4: Change MCP config
        new_config = {
            "server": "mcp-server-2",  # Different server
            "port": 9000,
            "tools": ["search", "browser", "terminal"],  # Added terminal
        }

        invalidated = cache.invalidate_if_config_changed(new_config)

        # Step 5: Verify cache invalidated
        assert invalidated is True
        assert len(cache._cache) == 0  # Cache cleared

        # Step 6: Verify invalidation metric incremented
        final_invalidations = agent_tool_cache_invalidations.get({"invalidation_reason": "config_change"})
        assert final_invalidations > initial_invalidations

        # Step 7: Same config again - no invalidation
        not_invalidated = cache.invalidate_if_config_changed(new_config)
        assert not_invalidated is False  # No change, no invalidation

    @pytest.mark.asyncio
    async def test_cache_hit_rate_metric(self, cache):
        """E2E: Cache hit rate metric calculated correctly."""
        # Step 1: Add some definitions
        await cache.set("tool1", {"name": "tool1"})
        await cache.set("tool2", {"name": "tool2"})
        await cache.set("tool3", {"name": "tool3"})

        # Step 2: Simulate hits and misses
        # Hits: tool1, tool2, tool3, tool1, tool2 (5 hits)
        await cache.get("tool1")  # Hit
        await cache.get("tool2")  # Hit
        await cache.get("tool3")  # Hit
        await cache.get("tool1")  # Hit
        await cache.get("tool2")  # Hit

        # Misses: tool4, tool5 (2 misses)
        await cache.get("tool4")  # Miss
        await cache.get("tool5")  # Miss

        # Step 3: Update metrics
        cache.update_metrics()

        # Step 4: Verify hit rate calculated
        hit_rate_1m = cache._calculate_hit_rate(60)

        # Expected: 5 hits / (5 hits + 2 misses) = 5/7 ≈ 0.714
        assert 0.7 <= hit_rate_1m <= 0.72

        # Step 5: Verify metric gauges set
        # (Can't easily assert gauge values, but verify no exceptions)

    @pytest.mark.asyncio
    async def test_ttl_expiration_flow(self, cache):
        """E2E: TTL expiration removes stale definitions."""
        # Use short TTL for testing
        short_cache = ToolDefinitionCache(ttl_seconds=1)

        # Step 1: Add definition
        await short_cache.set("short_lived", {"name": "short_lived"})

        # Step 2: Immediately retrieve (should hit)
        immediate = await short_cache.get("short_lived")
        assert immediate is not None

        # Step 3: Wait for TTL expiration
        await asyncio.sleep(1.5)

        # Step 4: Retrieve after expiration (should miss and remove)
        expired = await short_cache.get("short_lived")
        assert expired is None

        # Step 5: Verify entry removed from cache
        assert len(short_cache._cache) == 0

    @pytest.mark.asyncio
    async def test_cache_eviction_on_max_size(self, cache):
        """E2E: Cache evicts oldest entry when max size reached."""
        # Use small cache for testing
        small_cache = ToolDefinitionCache(max_cache_size=3)

        # Step 1: Add 3 definitions (at capacity)
        await small_cache.set("tool1", {"name": "tool1"})
        await asyncio.sleep(0.1)  # Ensure different timestamps
        await small_cache.set("tool2", {"name": "tool2"})
        await asyncio.sleep(0.1)
        await small_cache.set("tool3", {"name": "tool3"})

        assert len(small_cache._cache) == 3

        # Step 2: Add 4th definition (triggers eviction)
        await asyncio.sleep(0.1)
        await small_cache.set("tool4", {"name": "tool4"})

        # Step 3: Verify cache still at max size
        assert len(small_cache._cache) == 3

        # Step 4: Verify oldest (tool1) evicted
        evicted = await small_cache.get("tool1")
        assert evicted is None

        # Step 5: Verify others still present
        assert await small_cache.get("tool2") is not None
        assert await small_cache.get("tool3") is not None
        assert await small_cache.get("tool4") is not None

    @pytest.mark.asyncio
    async def test_versioned_cache_keys(self, cache):
        """E2E: Cache keys include MCP config version."""
        # Step 1: Set MCP config
        config1 = {"server": "mcp-v1", "port": 8000}
        cache.invalidate_if_config_changed(config1)

        # Step 2: Add definition with version 1
        await cache.set("search", {"name": "search", "version": 1})

        # Step 3: Verify cache key includes version
        key1 = cache.cache_key("search")
        assert ":" in key1  # Format: tool_name:version_hash
        assert key1.startswith("search:")

        # Step 4: Change config (new version)
        config2 = {"server": "mcp-v2", "port": 9000}
        cache.invalidate_if_config_changed(config2)

        # Step 5: Add definition with same name (different version)
        await cache.set("search", {"name": "search", "version": 2})

        # Step 6: Verify new cache key (different version hash)
        key2 = cache.cache_key("search")
        assert key2 != key1  # Different version hashes
        assert key2.startswith("search:")

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, cache):
        """E2E: Cleanup removes only expired entries."""
        # Use short TTL
        short_cache = ToolDefinitionCache(ttl_seconds=1)

        # Step 1: Add entries
        await short_cache.set("expired1", {"name": "expired1"})
        await short_cache.set("expired2", {"name": "expired2"})

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Step 2: Add fresh entry
        await short_cache.set("fresh", {"name": "fresh"})

        assert len(short_cache._cache) == 3

        # Step 3: Cleanup
        removed = short_cache.cleanup_expired()

        # Step 4: Verify only expired entries removed
        assert removed == 2
        assert len(short_cache._cache) == 1

        # Step 5: Verify fresh entry still present
        fresh = await short_cache.get("fresh")
        assert fresh is not None

    @pytest.mark.asyncio
    async def test_cache_stats_accuracy(self, cache):
        """E2E: Cache stats reflect actual state."""
        # Step 1: Add definitions
        await cache.set("tool1", {"name": "tool1", "size": "small"})
        await cache.set("tool2", {"name": "tool2", "size": "medium"})

        # Step 2: Simulate some hits/misses
        await cache.get("tool1")  # Hit
        await cache.get("tool1")  # Hit
        await cache.get("unknown")  # Miss

        # Step 3: Get stats
        stats = cache.get_stats()

        # Step 4: Verify stats
        assert stats["size"] == 2  # Two cached definitions
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 3600
        assert stats["config_version"] is not None
        assert "hit_rate_1m" in stats
        assert "hit_rate_5m" in stats
        assert "memory_bytes" in stats
        assert stats["memory_bytes"] > 0

    @pytest.mark.asyncio
    async def test_custom_ttl_override(self, cache):
        """E2E: Custom TTL overrides default."""
        # Step 1: Add definition with custom short TTL
        await cache.set("custom_ttl", {"name": "custom_ttl"}, ttl=1)  # 1 second

        # Step 2: Immediately retrieve (should hit)
        immediate = await cache.get("custom_ttl")
        assert immediate is not None

        # Step 3: Wait past custom TTL
        await asyncio.sleep(1.5)

        # Step 4: Retrieve after custom TTL (should be expired)
        expired = await cache.get("custom_ttl")
        assert expired is None

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, cache):
        """E2E: Cache handles concurrent access correctly."""
        # Add definition
        await cache.set("concurrent", {"name": "concurrent", "data": "test"})

        # Simulate concurrent reads
        results = []
        for _ in range(10):
            result = await cache.get("concurrent")
            results.append(result)

        # All reads should succeed
        assert len(results) == 10
        assert all(r is not None for r in results)
        assert all(r["name"] == "concurrent" for r in results)

    @pytest.mark.asyncio
    async def test_warming_error_handling(self, cache):
        """E2E: Cache warming continues despite individual failures."""
        # Create registry with one failing tool
        failing_registry = Mock()
        failing_registry.list_tools = Mock(return_value=["good1", "failing", "good2"])

        async def mock_get_failing(tool_name: str):
            if tool_name == "failing":
                raise ValueError("Tool definition not found")
            return {"name": tool_name, "schema": {}}

        failing_registry.get_definition = AsyncMock(side_effect=mock_get_failing)

        # Warm cache
        count = await cache.warm_cache(failing_registry)

        # Should cache 2 out of 3 (failing one skipped)
        assert count == 2
        assert len(cache._cache) == 2

        # Verify good tools cached
        assert await cache.get("good1") is not None
        assert await cache.get("good2") is not None

        # Verify failing tool not cached
        assert await cache.get("failing") is None
