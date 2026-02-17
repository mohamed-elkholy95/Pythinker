"""Tool Definition Caching Service

Caches tool definitions with versioning and TTL-based expiration.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.domain.metrics.agent_metrics import get_agent_metrics

logger = logging.getLogger(__name__)


@dataclass
class CachedDefinition:
    """Cached tool definition with metadata."""

    tool_name: str
    definition: dict[str, Any]
    cached_at: float
    config_version: str
    ttl_seconds: int

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        age = time.time() - self.cached_at
        return age > self.ttl_seconds


class ToolDefinitionCache:
    """Service for caching tool definitions.

    Implements:
    - Versioned cache keys (MCP config hash)
    - Cache warming on startup
    - TTL-based expiration (1 hour default)
    - Hit/miss metrics
    - Cache stats gauges
    """

    def __init__(
        self,
        ttl_seconds: int = 3600,  # 1 hour
        max_cache_size: int = 1000,
    ):
        """Initialize tool definition cache.

        Args:
            ttl_seconds: Time-to-live for cache entries
            max_cache_size: Maximum number of cached definitions
        """
        self.ttl_seconds = ttl_seconds
        self.max_cache_size = max_cache_size

        self._cache: dict[str, CachedDefinition] = {}
        self._mcp_config_hash: str | None = None

        # Hit/miss tracking for rate calculation
        self._hits_window: list[float] = []
        self._misses_window: list[float] = []

    def _hash_mcp_config(self, config: dict[str, Any] | None = None) -> str:
        """Generate hash of MCP configuration.

        Args:
            config: MCP config dict (if None, returns default hash)

        Returns:
            str: SHA256 hash of config
        """
        if config is None:
            return "default"

        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def cache_key(self, tool_name: str) -> str:
        """Generate versioned cache key.

        Args:
            tool_name: Name of the tool

        Returns:
            str: Cache key with version
        """
        version = self._mcp_config_hash or "default"
        return f"{tool_name}:{version}"

    async def get(self, tool_name: str) -> dict[str, Any] | None:
        """Get tool definition from cache.

        Args:
            tool_name: Name of the tool

        Returns:
            dict | None: Cached definition or None if not found/expired
        """
        start_time = time.time()
        key = self.cache_key(tool_name)

        if key in self._cache:
            cached = self._cache[key]

            # Check expiration
            if cached.is_expired():
                logger.debug(f"Cache entry expired: {tool_name}")
                del self._cache[key]

                # Track miss
                get_agent_metrics().tool_definition_cache_misses.inc(labels={"cache_scope": "session"})
                self._track_miss()

                # Track lookup duration
                duration = time.time() - start_time
                get_agent_metrics().tool_cache_lookup_duration.observe(
                    labels={"cache_hit": "false"},
                    value=duration,
                )

                return None

            # Cache hit
            logger.debug(f"Cache hit: {tool_name}")
            get_agent_metrics().tool_definition_cache_hits.inc(labels={"cache_scope": "session"})
            self._track_hit()

            # Track lookup duration
            duration = time.time() - start_time
            get_agent_metrics().tool_cache_lookup_duration.observe(
                labels={"cache_hit": "true"},
                value=duration,
            )

            return cached.definition

        # Cache miss
        logger.debug(f"Cache miss: {tool_name}")
        get_agent_metrics().tool_definition_cache_misses.inc(labels={"cache_scope": "session"})
        self._track_miss()

        # Track lookup duration
        duration = time.time() - start_time
        get_agent_metrics().tool_cache_lookup_duration.observe(
            labels={"cache_hit": "false"},
            value=duration,
        )

        return None

    async def set(
        self,
        tool_name: str,
        definition: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Set tool definition in cache.

        Args:
            tool_name: Name of the tool
            definition: Tool definition dict
            ttl: Optional TTL override (uses default if None)
        """
        key = self.cache_key(tool_name)
        ttl_seconds = ttl or self.ttl_seconds

        # Check cache size limit
        if len(self._cache) >= self.max_cache_size:
            # Remove oldest entry
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].cached_at)
            del self._cache[oldest_key]
            logger.debug(f"Evicted oldest cache entry: {oldest_key}")

        # Cache the definition
        cached = CachedDefinition(
            tool_name=tool_name,
            definition=definition,
            cached_at=time.time(),
            config_version=self._mcp_config_hash or "default",
            ttl_seconds=ttl_seconds,
        )

        self._cache[key] = cached
        logger.debug(f"Cached tool definition: {tool_name} (TTL: {ttl_seconds}s)")

        # Update cache size gauge
        self._update_size_metrics()

    async def warm_cache(self, tool_registry: Any) -> int:
        """Pre-populate cache on startup.

        Args:
            tool_registry: Tool registry to fetch definitions from

        Returns:
            int: Number of definitions cached
        """
        logger.info("Warming tool definition cache...")

        count = 0
        tool_names = getattr(tool_registry, "list_tools", lambda: [])()

        for tool_name in tool_names:
            try:
                definition = await tool_registry.get_definition(tool_name)
                await self.set(tool_name, definition)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to warm cache for {tool_name}: {e}")

        logger.info(f"Cache warmed with {count} tool definitions")
        return count

    def invalidate_if_config_changed(self, new_config: dict[str, Any]) -> bool:
        """Check config hash and invalidate if changed.

        Args:
            new_config: New MCP configuration

        Returns:
            bool: True if cache was invalidated
        """
        new_hash = self._hash_mcp_config(new_config)

        if self._mcp_config_hash and new_hash != self._mcp_config_hash:
            logger.info(f"MCP config changed, invalidating cache (old={self._mcp_config_hash}, new={new_hash})")

            self.clear()
            self._mcp_config_hash = new_hash

            # Track invalidation
            get_agent_metrics().tool_cache_invalidations.inc(labels={"invalidation_reason": "config_change"})

            return True

        self._mcp_config_hash = new_hash
        return False

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            int: Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cache entries")

        self._update_size_metrics()
        return count

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            int: Number of entries removed
        """
        expired_keys = [key for key, cached in self._cache.items() if cached.is_expired()]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
            self._update_size_metrics()

        return len(expired_keys)

    def _track_hit(self) -> None:
        """Track cache hit for rate calculation."""
        current_time = time.time()
        self._hits_window.append(current_time)

        # Keep only last 5 minutes
        cutoff = current_time - 300
        self._hits_window = [t for t in self._hits_window if t > cutoff]

    def _track_miss(self) -> None:
        """Track cache miss for rate calculation."""
        current_time = time.time()
        self._misses_window.append(current_time)

        # Keep only last 5 minutes
        cutoff = current_time - 300
        self._misses_window = [t for t in self._misses_window if t > cutoff]

    def _calculate_hit_rate(self, window_seconds: int) -> float:
        """Calculate hit rate over time window.

        Args:
            window_seconds: Time window in seconds

        Returns:
            float: Hit rate (0-1)
        """
        current_time = time.time()
        cutoff = current_time - window_seconds

        hits = len([t for t in self._hits_window if t > cutoff])
        misses = len([t for t in self._misses_window if t > cutoff])

        total = hits + misses
        return hits / total if total > 0 else 0.0

    def _update_size_metrics(self) -> None:
        """Update cache size gauge metrics."""
        metrics = get_agent_metrics()
        # Update size gauge
        metrics.tool_cache_size.set(
            labels={"cache_type": "definitions"},
            value=float(len(self._cache)),
        )

        # Estimate memory usage (rough)
        memory_bytes = sum(len(json.dumps(cached.definition)) for cached in self._cache.values())
        metrics.tool_cache_memory_bytes.set(
            labels={"cache_type": "definitions"},
            value=float(memory_bytes),
        )

    def update_metrics(self) -> None:
        """Update all metrics (call periodically)."""
        self._update_size_metrics()

        # Update hit rate gauges
        metrics = get_agent_metrics()

        hit_rate_1m = self._calculate_hit_rate(60)
        hit_rate_5m = self._calculate_hit_rate(300)

        metrics.tool_cache_hit_rate.set(
            labels={"window": "1m"},
            value=hit_rate_1m,
        )
        metrics.tool_cache_hit_rate.set(
            labels={"window": "5m"},
            value=hit_rate_5m,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            dict: Cache stats
        """
        return {
            "size": len(self._cache),
            "max_size": self.max_cache_size,
            "ttl_seconds": self.ttl_seconds,
            "config_version": self._mcp_config_hash or "default",
            "hit_rate_1m": self._calculate_hit_rate(60),
            "hit_rate_5m": self._calculate_hit_rate(300),
            "memory_bytes": sum(len(json.dumps(cached.definition)) for cached in self._cache.values()),
        }
