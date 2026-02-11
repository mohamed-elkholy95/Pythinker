"""Tool Result Caching Layer

Provides multi-tier caching for tool execution results to improve performance
by avoiding redundant API calls and computations.

Features:
- L1 (in-memory) + L2 (Redis) multi-tier caching
- Configurable TTL per tool type
- Hash-based cache key generation
- Selective caching (some tools excluded)
- Cache statistics and management
- Automatic L1 eviction and promotion
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class L1CacheEntry:
    """In-memory cache entry with metadata."""

    value: Any
    created_at: float
    ttl: int
    hits: int = 0

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl


class L1Cache:
    """Fast in-memory cache (L1) for hot tool results.

    Features:
    - Sub-millisecond access times
    - Automatic expiration
    - LRU-style eviction when full
    - Hit tracking for cache promotion
    """

    def __init__(self, max_size: int = 500, default_ttl: int = 300):
        """Initialize L1 cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds (5 minutes)
        """
        self._cache: dict[str, L1CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Get value from L1 cache.

        Returns:
            Cached value or None if not found/expired
        """
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None

        entry.hits += 1
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store value in L1 cache.

        Args:
            key: Cache key
            value: Value to store
            ttl: TTL in seconds (uses default if not specified)
        """
        # Evict if at capacity
        if len(self._cache) >= self._max_size:
            self._evict_lru()

        self._cache[key] = L1CacheEntry(value=value, created_at=time.time(), ttl=ttl or self._default_ttl)

    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def _evict_lru(self) -> None:
        """Evict least recently used entries (lowest hit count + oldest)."""
        if not self._cache:
            return

        # Remove expired entries first
        expired = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired:
            del self._cache[key]

        # If still over capacity, evict by LRU score
        if len(self._cache) >= self._max_size:
            # Score = hits / age_seconds (lower is more evictable)
            now = time.time()
            scored = [(k, v.hits / max(now - v.created_at, 1)) for k, v in self._cache.items()]
            scored.sort(key=lambda x: x[1])

            # Evict bottom 10%
            to_evict = max(1, len(scored) // 10)
            for key, _ in scored[:to_evict]:
                del self._cache[key]

    def clear(self) -> int:
        """Clear all entries."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }


# Global L1 cache instance
_l1_cache = L1Cache()


@dataclass
class ToolCacheConfig:
    """Configuration for tool result caching."""

    # Global cache enable/disable
    enabled: bool = True

    # Default TTL in seconds (1 hour)
    default_ttl: int = 3600

    # TTL overrides per tool name
    ttl_by_tool: dict[str, int] = field(
        default_factory=lambda: {
            # Read operations - shorter TTL as content may change
            "file_read": 300,  # 5 minutes
            "file_list_directory": 300,  # 5 minutes
            # Search operations - moderate TTL
            "info_search_web": 1800,  # 30 minutes
            # Browser operations - shorter TTL for dynamic content
            "browser_extract": 600,  # 10 minutes
            "browser_read_page_content": 600,
            # MCP tools - moderate TTL
            "mcp_call_tool": 900,  # 15 minutes
        }
    )

    # Tools that should never be cached (write operations, side effects)
    exclude_tools: set[str] = field(
        default_factory=lambda: {
            # Write operations
            "file_write",
            "file_create_directory",
            "file_copy",
            "file_move",
            "file_delete",
            # Shell operations (side effects)
            "shell_execute",
            # Browser actions (side effects)
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_agent_navigate",
            "browser_agent_click",
            "browser_agent_type",
            "browser_agent_interact",
            # Message operations
            "message_notify_user",
        }
    )

    # Maximum size for cache key arguments (prevents huge keys)
    max_key_size: int = 10000


# Global cache config
_cache_config = ToolCacheConfig()


def get_cache_config() -> ToolCacheConfig:
    """Get the global cache configuration."""
    return _cache_config


def set_cache_config(config: ToolCacheConfig) -> None:
    """Set the global cache configuration."""
    global _cache_config
    _cache_config = config


def _generate_cache_key(tool_name: str, kwargs: dict[str, Any]) -> str:
    """Generate a deterministic cache key from tool name and arguments.

    Args:
        tool_name: Name of the tool
        kwargs: Tool arguments

    Returns:
        Cache key string
    """
    # Filter out None values and sort for consistency
    filtered_kwargs = {k: v for k, v in sorted(kwargs.items()) if v is not None}

    # Serialize to JSON for hashing
    try:
        kwargs_json = json.dumps(filtered_kwargs, sort_keys=True, default=str)
    except (TypeError, ValueError):
        # Fallback for non-serializable objects
        kwargs_json = str(filtered_kwargs)

    # Truncate if too large
    config = get_cache_config()
    if len(kwargs_json) > config.max_key_size:
        kwargs_json = kwargs_json[: config.max_key_size]

    # Create hash
    key_hash = hashlib.sha256(kwargs_json.encode()).hexdigest()[:16]

    return f"tool:{tool_name}:{key_hash}"


def _should_cache_tool(tool_name: str) -> bool:
    """Check if a tool should be cached.

    Args:
        tool_name: Name of the tool

    Returns:
        True if tool results should be cached
    """
    config = get_cache_config()

    if not config.enabled:
        return False

    return tool_name not in config.exclude_tools


def _get_tool_ttl(tool_name: str) -> int:
    """Get the cache TTL for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        TTL in seconds
    """
    config = get_cache_config()
    return config.ttl_by_tool.get(tool_name, config.default_ttl)


class ToolCacheStats:
    """Track cache hit/miss statistics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.skipped = 0  # Tools excluded from caching
        self.errors = 0

    def record_hit(self):
        self.hits += 1

    def record_miss(self):
        self.misses += 1

    def record_skip(self):
        self.skipped += 1

    def record_error(self):
        self.errors += 1

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "skipped": self.skipped,
            "errors": self.errors,
            "hit_rate": round(self.hit_rate, 4),
        }

    def reset(self):
        """Reset all statistics."""
        self.hits = 0
        self.misses = 0
        self.skipped = 0
        self.errors = 0


# Global cache stats
_cache_stats = ToolCacheStats()


def get_cache_stats() -> ToolCacheStats:
    """Get the global cache statistics."""
    return _cache_stats


def get_l1_cache() -> L1Cache:
    """Get the global L1 cache instance."""
    return _l1_cache


def cacheable_tool(ttl: int | None = None, use_l1: bool = True):
    """Decorator for making tool methods cacheable with multi-tier caching.

    This decorator wraps async tool methods to add caching behavior.
    Uses L1 (in-memory) for hot data and L2 (Redis) for persistence.

    Cache lookup order:
    1. L1 (in-memory) - sub-millisecond access
    2. L2 (Redis) - persistent storage
    3. Execute function on miss

    On cache hit from L2, the value is promoted to L1 for faster future access.

    Args:
        ttl: Optional custom TTL override (seconds)
        use_l1: Whether to use L1 cache (default: True)

    Returns:
        Decorator function

    Example:
        @tool(name="file_read", ...)
        @cacheable_tool(ttl=300)
        async def file_read(self, path: str) -> ToolResult:
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Get tool name from decorated function
            tool_name = getattr(func, "_function_name", func.__name__)

            # Check if this tool should be cached
            if not _should_cache_tool(tool_name):
                _cache_stats.record_skip()
                return await func(self, *args, **kwargs)

            # Convert args to kwargs for cache key
            import inspect

            sig = inspect.signature(func)
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()
            all_kwargs = dict(bound.arguments)
            all_kwargs.pop("self", None)

            # Generate cache key
            cache_key = _generate_cache_key(tool_name, all_kwargs)

            # Determine TTL
            actual_ttl = ttl if ttl is not None else _get_tool_ttl(tool_name)

            # L1 LOOKUP (fast in-memory)
            if use_l1:
                l1_value = _l1_cache.get(cache_key)
                if l1_value is not None:
                    logger.debug(f"L1 cache hit for {tool_name}: {cache_key}")
                    _cache_stats.record_hit()
                    from app.domain.models.tool_result import ToolResult

                    return ToolResult(**l1_value)

            # L2 LOOKUP (Redis)
            try:
                from app.domain.external.cache import get_cache

                cache = get_cache()

                cached_value = await cache.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"L2 cache hit for {tool_name}: {cache_key}")
                    _cache_stats.record_hit()

                    # Promote to L1 for faster future access
                    if use_l1:
                        _l1_cache.set(cache_key, cached_value, ttl=actual_ttl)

                    # Reconstruct ToolResult from cached dict
                    from app.domain.models.tool_result import ToolResult

                    return ToolResult(**cached_value)

            except Exception as e:
                logger.warning(f"L2 cache get failed for {tool_name}: {e}")
                _cache_stats.record_error()

            # Cache miss - execute the function
            _cache_stats.record_miss()
            result = await func(self, *args, **kwargs)

            # Store in cache (only if successful)
            if result.success:
                try:
                    # Convert ToolResult to dict for caching
                    cache_value = {
                        "success": result.success,
                        "message": result.message,
                        "data": result.data
                        if not hasattr(result.data, "model_dump")
                        else result.data.model_dump()
                        if result.data
                        else None,
                    }

                    if use_l1:
                        _l1_cache.set(cache_key, cache_value, ttl=actual_ttl)

                    await cache.set(cache_key, cache_value, ttl=actual_ttl)
                    logger.debug(f"Cached {tool_name} result in L1+L2 for {actual_ttl}s: {cache_key}")

                except Exception as e:
                    logger.warning(f"Cache set failed for {tool_name}: {e}")
                    _cache_stats.record_error()

            return result

        return wrapper

    return decorator


async def clear_tool_cache(tool_name: str | None = None, clear_l1: bool = True) -> tuple[int, int]:
    """Clear cached tool results from both L1 and L2 caches.

    Args:
        tool_name: Specific tool name to clear, or None for all tools
        clear_l1: Whether to clear L1 cache (default: True)

    Returns:
        Tuple of (L1 keys cleared, L2 keys cleared)
    """
    l1_cleared = 0
    l2_cleared = 0

    # Clear L1
    if clear_l1:
        l1_cleared = _l1_cache.clear()

    # Clear L2 (Redis)
    try:
        from app.domain.external.cache import get_cache

        cache = get_cache()

        pattern = f"tool:{tool_name}:*" if tool_name else "tool:*"

        l2_cleared = await cache.clear_pattern(pattern)
        logger.info(f"Cleared cache: L1={l1_cleared}, L2={l2_cleared} matching '{pattern}'")

    except Exception as e:
        logger.error(f"Failed to clear L2 tool cache: {e}")

    return l1_cleared, l2_cleared


async def get_cached_keys(tool_name: str | None = None) -> list[str]:
    """Get list of cached tool result keys from L2 (Redis).

    Args:
        tool_name: Specific tool name filter, or None for all

    Returns:
        List of cache keys
    """
    try:
        from app.domain.external.cache import get_cache

        cache = get_cache()

        pattern = f"tool:{tool_name}:*" if tool_name else "tool:*"

        return await cache.keys(pattern)

    except Exception as e:
        logger.error(f"Failed to get cached keys: {e}")
        return []


def get_combined_cache_stats() -> dict[str, Any]:
    """Get combined statistics for L1 and L2 caches.

    Returns:
        Dictionary with L1, L2, and combined statistics
    """
    l1_stats = _l1_cache.get_stats()
    l2_stats = _cache_stats.to_dict()

    total_hits = l1_stats["hits"] + l2_stats["hits"]
    total_misses = l1_stats["misses"] + l2_stats["misses"]
    total = total_hits + total_misses

    return {
        "l1": l1_stats,
        "l2": l2_stats,
        "combined": {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "combined_hit_rate": round(total_hits / total, 4) if total > 0 else 0.0,
        },
    }


async def warmup_common_tools() -> dict[str, bool]:
    """Warmup cache with common tool patterns.

    Pre-executes common read operations to populate L1 cache
    for faster subsequent access.

    Returns:
        Dict of warmup task names to success status
    """
    from app.domain.services.tools.dynamic_toolset import get_warmup_manager

    warmup_manager = get_warmup_manager()

    # Register cache-specific warmup tasks
    if not warmup_manager.is_warmed_up:
        # These are lightweight tasks that help prime the cache infrastructure
        async def prime_l1_cache():
            """Prime L1 cache with placeholder to ensure it's initialized."""
            _l1_cache.set("_warmup_test", {"status": "ready"}, ttl=60)
            _l1_cache.get("_warmup_test")
            _l1_cache.delete("_warmup_test")

        warmup_manager.register_warmup_task(name="l1_cache_prime", coroutine_factory=prime_l1_cache, priority=1)

        async def check_l2_connection():
            """Verify L2 (Redis) connection is available."""
            try:
                from app.domain.external.cache import get_cache

                cache = get_cache()
                await cache.set("_warmup_test", {"status": "ready"}, ttl=60)
                await cache.get("_warmup_test")
                await cache.delete("_warmup_test")
                return True
            except Exception:
                return False

        warmup_manager.register_warmup_task(
            name="l2_cache_connection", coroutine_factory=check_l2_connection, priority=2
        )

    return await warmup_manager.warmup()
