"""
Intelligent Result Caching module.

This module provides caching for tool results and LLM responses
to avoid redundant operations and reduce latency.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Default TTLs by tool category (in seconds)
DEFAULT_TTLS = {
    "search": 300,  # 5 minutes - search results change frequently
    "file_read": 3600,  # 1 hour - files don't change often during a session
    "file_list": 600,  # 10 minutes
    "browser": 300,  # 5 minutes - web content can change
    "shell_read": 300,  # 5 minutes for read-only shell commands
    "api": 600,  # 10 minutes for external APIs
    "default": 300,  # Default 5 minutes
}


@dataclass
class CachedResult:
    """A cached tool or LLM result."""

    cache_key: str
    tool_name: str
    result_data: Any
    result_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=300))
    hit_count: int = 0
    last_hit: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if the cached result has expired."""
        return datetime.now(UTC) > self.expires_at

    def is_valid(self) -> bool:
        """Check if the cached result is still valid."""
        return not self.is_expired()

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hit_count += 1
        self.last_hit = datetime.now(UTC)


@dataclass
class CacheStatistics:
    """Statistics for the result cache."""

    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_evictions: int = 0
    memory_usage_estimate: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate the cache hit rate."""
        total = self.total_hits + self.total_misses
        if total == 0:
            return 0.0
        return self.total_hits / total


class ResultCache:
    """Cache for tool results and LLM responses.

    Provides intelligent caching with:
    - Tool-specific TTLs
    - Content-based deduplication
    - LRU eviction policy
    - Hit rate tracking
    """

    # Maximum cache entries
    MAX_ENTRIES = 1000
    # Maximum size per entry (bytes)
    MAX_ENTRY_SIZE = 1024 * 1024  # 1MB

    def __init__(
        self,
        custom_ttls: dict[str, int] | None = None,
        max_entries: int | None = None,
    ) -> None:
        """Initialize the result cache.

        Args:
            custom_ttls: Custom TTLs by tool name/category
            max_entries: Maximum cache entries
        """
        self._cache: dict[str, CachedResult] = {}
        self._ttls = {**DEFAULT_TTLS, **(custom_ttls or {})}
        self._max_entries = max_entries or self.MAX_ENTRIES
        self._stats = CacheStatistics()

    def get(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> Any | None:
        """Get a cached result.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            Cached result data if found and valid, None otherwise
        """
        cache_key = self._generate_key(tool_name, args)

        if cache_key not in self._cache:
            self._stats.total_misses += 1
            return None

        cached = self._cache[cache_key]

        if cached.is_expired():
            # Remove expired entry
            del self._cache[cache_key]
            self._stats.total_misses += 1
            self._stats.total_evictions += 1
            return None

        # Record hit and return
        cached.record_hit()
        self._stats.total_hits += 1

        logger.debug(f"Cache hit for {tool_name}: {cache_key[:20]}...")
        return cached.result_data

    def put(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CachedResult:
        """Store a result in the cache.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Result to cache
            ttl_seconds: Optional custom TTL
            metadata: Optional metadata

        Returns:
            The cached result entry
        """
        # Check entry size
        result_str = str(result)
        if len(result_str) > self.MAX_ENTRY_SIZE:
            logger.debug(f"Result too large to cache: {len(result_str)} bytes")
            return None

        # Evict if needed
        if len(self._cache) >= self._max_entries:
            self._evict_lru()

        cache_key = self._generate_key(tool_name, args)
        result_hash = self._hash_result(result)

        # Determine TTL
        if ttl_seconds is None:
            ttl_seconds = self._get_ttl(tool_name)

        cached = CachedResult(
            cache_key=cache_key,
            tool_name=tool_name,
            result_data=result,
            result_hash=result_hash,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            metadata=metadata or {},
        )

        self._cache[cache_key] = cached
        self._stats.total_entries = len(self._cache)

        logger.debug(f"Cached result for {tool_name}, TTL={ttl_seconds}s")
        return cached

    def invalidate(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> int:
        """Invalidate cached results.

        Args:
            tool_name: Name of the tool
            args: Optional specific arguments (if None, invalidates all for tool)

        Returns:
            Number of entries invalidated
        """
        if args:
            # Invalidate specific entry
            cache_key = self._generate_key(tool_name, args)
            if cache_key in self._cache:
                del self._cache[cache_key]
                return 1
            return 0

        # Invalidate all entries for tool
        to_remove = [key for key, cached in self._cache.items() if cached.tool_name == tool_name]

        for key in to_remove:
            del self._cache[key]

        self._stats.total_entries = len(self._cache)
        return len(to_remove)

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate entries matching a pattern.

        Args:
            pattern: Pattern to match against tool names

        Returns:
            Number of entries invalidated
        """
        to_remove = [key for key, cached in self._cache.items() if pattern.lower() in cached.tool_name.lower()]

        for key in to_remove:
            del self._cache[key]

        self._stats.total_entries = len(self._cache)
        return len(to_remove)

    def clear(self) -> int:
        """Clear all cached entries.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        self._stats.total_entries = 0
        return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired = [key for key, cached in self._cache.items() if cached.is_expired()]

        for key in expired:
            del self._cache[key]

        self._stats.total_entries = len(self._cache)
        self._stats.total_evictions += len(expired)
        return len(expired)

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "total_entries": self._stats.total_entries,
            "total_hits": self._stats.total_hits,
            "total_misses": self._stats.total_misses,
            "total_evictions": self._stats.total_evictions,
            "hit_rate": self._stats.hit_rate,
            "entries_by_tool": self._count_by_tool(),
        }

    def _generate_key(self, tool_name: str, args: dict[str, Any]) -> str:
        """Generate a cache key from tool name and arguments."""
        # Sort args for consistent key generation
        sorted_args = sorted(args.items())
        args_str = str(sorted_args)

        # Hash the combination
        combined = f"{tool_name}:{args_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _hash_result(self, result: Any) -> str:
        """Generate a hash of the result for deduplication."""
        result_str = str(result)
        return hashlib.md5(result_str.encode()).hexdigest()  # noqa: S324 - MD5 used for non-security cache key, not cryptographic

    def _get_ttl(self, tool_name: str) -> int:
        """Get the TTL for a tool."""
        # Check exact match
        if tool_name in self._ttls:
            return self._ttls[tool_name]

        # Check category match
        tool_lower = tool_name.lower()
        for category, ttl in self._ttls.items():
            if category in tool_lower:
                return ttl

        return self._ttls.get("default", 300)

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._cache:
            return

        # Find entry with oldest last_hit (or created_at if never hit)
        oldest_key = None
        oldest_time = datetime.now(UTC)

        for key, cached in self._cache.items():
            check_time = cached.last_hit or cached.created_at
            if check_time <= oldest_time:
                oldest_time = check_time
                oldest_key = key

        if oldest_key:
            del self._cache[oldest_key]
            self._stats.total_evictions += 1

    def _count_by_tool(self) -> dict[str, int]:
        """Count entries by tool name."""
        counts: dict[str, int] = {}
        for cached in self._cache.values():
            counts[cached.tool_name] = counts.get(cached.tool_name, 0) + 1
        return counts


# Global result cache instance
_cache: ResultCache | None = None


def get_result_cache(
    custom_ttls: dict[str, int] | None = None,
) -> ResultCache:
    """Get or create the global result cache."""
    global _cache
    if _cache is None:
        _cache = ResultCache(custom_ttls)
    return _cache


def reset_result_cache() -> None:
    """Reset the global result cache."""
    global _cache
    _cache = None
