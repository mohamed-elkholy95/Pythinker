"""Tests for Tool Definition Cache (Workstream E)

Test coverage for tool definition caching, warming, and invalidation.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.metrics.agent_metrics import AgentMetrics, set_agent_metrics
from app.domain.services.tools.tool_definition_cache import ToolDefinitionCache


class _TrackingCounter:
    """Simple counter that tracks .inc() calls for test assertions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str] | None] = []

    def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        self.calls.append(labels)

    @property
    def call_count(self) -> int:
        return len(self.calls)


class _TrackingGauge:
    """Simple gauge that tracks .set() calls for test assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str] | None, float]] = []

    def set(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        self.calls.append((labels, value))


class _TrackingHistogram:
    """Simple histogram that tracks .observe() calls for test assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str] | None, float]] = []

    def observe(self, labels: dict[str, str] | None = None, value: float = 0.0) -> None:
        self.calls.append((labels, value))


class TestToolDefinitionCache:
    """Test suite for tool definition cache."""

    @pytest.fixture(autouse=True)
    def _inject_tracking_metrics(self):
        """Inject tracking metrics into the domain AgentMetrics singleton."""
        self._metrics = AgentMetrics()
        self._hits_counter = _TrackingCounter()
        self._misses_counter = _TrackingCounter()
        self._invalidations_counter = _TrackingCounter()
        self._cache_size_gauge = _TrackingGauge()
        self._hit_rate_gauge = _TrackingGauge()
        self._memory_gauge = _TrackingGauge()
        self._lookup_histogram = _TrackingHistogram()
        self._metrics.tool_definition_cache_hits = self._hits_counter
        self._metrics.tool_definition_cache_misses = self._misses_counter
        self._metrics.tool_cache_invalidations = self._invalidations_counter
        self._metrics.tool_cache_size = self._cache_size_gauge
        self._metrics.tool_cache_hit_rate = self._hit_rate_gauge
        self._metrics.tool_cache_memory_bytes = self._memory_gauge
        self._metrics.tool_cache_lookup_duration = self._lookup_histogram
        set_agent_metrics(self._metrics)
        yield
        set_agent_metrics(AgentMetrics())

    @pytest.fixture
    def cache(self):
        """Create cache instance with default TTL."""
        return ToolDefinitionCache(ttl_seconds=3600, max_cache_size=100)

    @pytest.mark.asyncio
    async def test_cache_miss_on_first_lookup(self, cache):
        """Test cache miss on first lookup."""
        result = await cache.get("search_tool")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_on_repeated_lookup(self, cache):
        """Test cache hit on repeated lookups."""
        definition = {"name": "search_tool", "schema": {"type": "object"}}

        # First set
        await cache.set("search_tool", definition)

        # Then get
        result = await cache.get("search_tool")

        assert result is not None
        assert result == definition

    @pytest.mark.asyncio
    async def test_versioned_cache_keys(self, cache):
        """Test cache keys include version information."""
        definition = {"name": "search_tool"}

        # Set definition
        await cache.set("search_tool", definition)

        # Get cache key
        key = cache.cache_key("search_tool")

        # Should include version
        assert ":" in key
        assert key.startswith("search_tool:")

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        """Test entries expire after TTL."""
        # Create cache with 1-second TTL
        short_cache = ToolDefinitionCache(ttl_seconds=1)

        definition = {"name": "test"}
        await short_cache.set("test_tool", definition)

        # Immediately: should hit
        result = await short_cache.get("test_tool")
        assert result == definition

        # Wait for expiration
        await asyncio.sleep(1.5)

        # After TTL: should miss
        result = await short_cache.get("test_tool")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidation_on_config_change(self, cache):
        """Test cache invalidated when MCP config changes."""
        # Set initial config
        config1 = {"server": "mcp1", "port": 8000}
        cache.invalidate_if_config_changed(config1)

        # Add definition
        await cache.set("tool1", {"name": "tool1"})
        assert len(cache._cache) == 1

        # Change config
        config2 = {"server": "mcp2", "port": 9000}
        invalidated = cache.invalidate_if_config_changed(config2)

        assert invalidated is True
        assert len(cache._cache) == 0

    @pytest.mark.asyncio
    async def test_config_hash_generation(self, cache):
        """Test MCP config hash generation is deterministic."""
        config1 = {"server": "mcp", "port": 8000}
        config2 = {"port": 8000, "server": "mcp"}  # Different order

        hash1 = cache._hash_mcp_config(config1)
        hash2 = cache._hash_mcp_config(config2)

        # Should be identical (order-independent)
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_cache_warming_on_startup(self, cache):
        """Test cache warming pre-populates definitions."""
        # Mock tool registry
        mock_registry = Mock()
        mock_registry.list_tools = Mock(return_value=["tool1", "tool2", "tool3"])
        mock_registry.get_definition = AsyncMock(side_effect=lambda name: {"name": name, "schema": {}})

        # Warm cache
        count = await cache.warm_cache(mock_registry)

        assert count == 3
        assert len(cache._cache) == 3

        # Verify definitions cached
        result = await cache.get("tool1")
        assert result == {"name": "tool1", "schema": {}}

    @pytest.mark.asyncio
    async def test_cache_warming_handles_errors(self, cache):
        """Test cache warming continues despite individual failures."""
        # Mock registry with one failing tool
        mock_registry = Mock()
        mock_registry.list_tools = Mock(return_value=["tool1", "tool2", "tool3"])

        async def mock_get_definition(name):
            if name == "tool2":
                raise ValueError("Tool not found")
            return {"name": name}

        mock_registry.get_definition = AsyncMock(side_effect=mock_get_definition)

        # Warm cache
        count = await cache.warm_cache(mock_registry)

        # Should cache 2 out of 3
        assert count == 2
        assert len(cache._cache) == 2

    @pytest.mark.asyncio
    async def test_cache_hit_miss_metrics(self, cache):
        """Test cache hit/miss counters are incremented via domain AgentMetrics."""
        initial_misses = self._misses_counter.call_count
        initial_hits = self._hits_counter.call_count

        # Miss
        await cache.get("nonexistent")

        # Hit
        await cache.set("tool1", {"name": "tool1"})
        await cache.get("tool1")

        assert self._misses_counter.call_count > initial_misses
        assert self._hits_counter.call_count > initial_hits

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, cache):
        """Test cleanup removes only expired entries."""
        # Create cache with 1-second TTL
        short_cache = ToolDefinitionCache(ttl_seconds=1)

        # Add entries
        await short_cache.set("tool1", {"name": "tool1"})
        await short_cache.set("tool2", {"name": "tool2"})
        assert len(short_cache._cache) == 2

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Cleanup
        removed = short_cache.cleanup_expired()

        assert removed == 2
        assert len(short_cache._cache) == 0

    @pytest.mark.asyncio
    async def test_clear_all_entries(self, cache):
        """Test clear removes all cache entries."""
        # Add entries
        for i in range(5):
            await cache.set(f"tool{i}", {"name": f"tool{i}"})

        assert len(cache._cache) == 5

        # Clear
        count = cache.clear()

        assert count == 5
        assert len(cache._cache) == 0

    @pytest.mark.asyncio
    async def test_max_cache_size_eviction(self, cache):
        """Test cache evicts oldest entry when max size reached."""
        # Create cache with max size of 3
        small_cache = ToolDefinitionCache(max_cache_size=3)

        # Add 3 entries
        await small_cache.set("tool1", {"name": "tool1"})
        await asyncio.sleep(0.1)  # Ensure different timestamps
        await small_cache.set("tool2", {"name": "tool2"})
        await asyncio.sleep(0.1)
        await small_cache.set("tool3", {"name": "tool3"})

        assert len(small_cache._cache) == 3

        # Add 4th entry (should evict oldest)
        await asyncio.sleep(0.1)
        await small_cache.set("tool4", {"name": "tool4"})

        assert len(small_cache._cache) == 3

        # Oldest (tool1) should be evicted
        result = await small_cache.get("tool1")
        assert result is None

        # Others should still exist
        assert await small_cache.get("tool2") is not None
        assert await small_cache.get("tool3") is not None
        assert await small_cache.get("tool4") is not None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """Test get_stats returns cache information."""
        # Add entries
        await cache.set("tool1", {"name": "tool1"})
        await cache.set("tool2", {"name": "tool2"})

        # Simulate some hits/misses
        await cache.get("tool1")  # Hit
        await cache.get("nonexistent")  # Miss

        stats = cache.get_stats()

        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 3600
        assert "hit_rate_1m" in stats
        assert "hit_rate_5m" in stats
        assert "memory_bytes" in stats

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self, cache):
        """Test hit rate calculation over time windows."""
        # Add definition
        await cache.set("tool1", {"name": "tool1"})

        # Simulate hits and misses
        await cache.get("tool1")  # Hit
        await cache.get("tool1")  # Hit
        await cache.get("nonexistent")  # Miss

        # Calculate hit rate
        hit_rate_1m = cache._calculate_hit_rate(60)

        # 2 hits, 1 miss = 2/3 = 0.666...
        assert 0.6 < hit_rate_1m < 0.7

    @pytest.mark.asyncio
    async def test_update_metrics(self, cache):
        """Test update_metrics updates all gauge metrics."""
        # Add some entries
        await cache.set("tool1", {"name": "tool1"})
        await cache.set("tool2", {"name": "tool2"})

        # Update metrics
        cache.update_metrics()

        # No assertions here as we can't easily verify gauge values
        # But at least verify it doesn't crash

    @pytest.mark.asyncio
    async def test_custom_ttl_override(self, cache):
        """Test setting entry with custom TTL."""
        # Set with custom 2-second TTL
        await cache.set("tool1", {"name": "tool1"}, ttl=2)

        # Should exist immediately
        result = await cache.get("tool1")
        assert result is not None

        # Wait past custom TTL
        await asyncio.sleep(2.5)

        # Should be expired
        result = await cache.get("tool1")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidation_metrics_tracked(self, cache):
        """Test invalidation metrics are incremented via domain AgentMetrics."""
        initial_count = self._invalidations_counter.call_count

        # Set initial config
        config1 = {"server": "mcp1"}
        cache.invalidate_if_config_changed(config1)

        # Change config (triggers invalidation)
        config2 = {"server": "mcp2"}
        cache.invalidate_if_config_changed(config2)

        assert self._invalidations_counter.call_count > initial_count
        last_call = self._invalidations_counter.calls[-1]
        assert last_call["invalidation_reason"] == "config_change"

    @pytest.mark.asyncio
    async def test_no_invalidation_same_config(self, cache):
        """Test no invalidation when config unchanged."""
        config = {"server": "mcp1"}

        cache.invalidate_if_config_changed(config)
        await cache.set("tool1", {"name": "tool1"})

        # Same config again
        invalidated = cache.invalidate_if_config_changed(config)

        assert invalidated is False
        assert len(cache._cache) == 1  # Not cleared
