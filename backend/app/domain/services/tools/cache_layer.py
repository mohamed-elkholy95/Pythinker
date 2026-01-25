"""Tool Result Caching Layer

Provides caching for tool execution results to improve performance
by avoiding redundant API calls and computations.

Features:
- Configurable TTL per tool type
- Hash-based cache key generation
- Selective caching (some tools excluded)
- Cache statistics and management
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolCacheConfig:
    """Configuration for tool result caching."""

    # Global cache enable/disable
    enabled: bool = True

    # Default TTL in seconds (1 hour)
    default_ttl: int = 3600

    # TTL overrides per tool name
    ttl_by_tool: Dict[str, int] = field(default_factory=lambda: {
        # Read operations - shorter TTL as content may change
        "file_read": 300,           # 5 minutes
        "file_list_directory": 300,  # 5 minutes

        # Search operations - moderate TTL
        "info_search_web": 1800,    # 30 minutes

        # Browser operations - shorter TTL for dynamic content
        "browser_extract": 600,     # 10 minutes
        "browser_read_page_content": 600,

        # MCP tools - moderate TTL
        "mcp_call_tool": 900,       # 15 minutes
    })

    # Tools that should never be cached (write operations, side effects)
    exclude_tools: Set[str] = field(default_factory=lambda: {
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
    })

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


def _generate_cache_key(tool_name: str, kwargs: Dict[str, Any]) -> str:
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
        kwargs_json = kwargs_json[:config.max_key_size]

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

    if tool_name in config.exclude_tools:
        return False

    return True


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

    def to_dict(self) -> Dict[str, Any]:
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


def cacheable_tool(ttl: Optional[int] = None):
    """Decorator for making tool methods cacheable.

    This decorator wraps async tool methods to add caching behavior.
    Cache results are stored in Redis with configurable TTL.

    Args:
        ttl: Optional custom TTL override (seconds)

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
            tool_name = getattr(func, '_function_name', func.__name__)

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
            all_kwargs.pop('self', None)

            # Generate cache key
            cache_key = _generate_cache_key(tool_name, all_kwargs)

            # Try to get from cache
            try:
                from app.infrastructure.external.cache import get_cache
                cache = get_cache()

                cached_value = await cache.get(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit for {tool_name}: {cache_key}")
                    _cache_stats.record_hit()

                    # Reconstruct ToolResult from cached dict
                    from app.domain.models.tool_result import ToolResult
                    return ToolResult(**cached_value)

            except Exception as e:
                logger.warning(f"Cache get failed for {tool_name}: {e}")
                _cache_stats.record_error()

            # Cache miss - execute the function
            _cache_stats.record_miss()
            result = await func(self, *args, **kwargs)

            # Store in cache (only if successful)
            if result.success:
                try:
                    # Determine TTL
                    actual_ttl = ttl if ttl is not None else _get_tool_ttl(tool_name)

                    # Convert ToolResult to dict for caching
                    cache_value = {
                        "success": result.success,
                        "message": result.message,
                        "data": result.data if not hasattr(result.data, 'model_dump') else result.data.model_dump() if result.data else None,
                    }

                    await cache.set(cache_key, cache_value, ttl=actual_ttl)
                    logger.debug(f"Cached {tool_name} result for {actual_ttl}s: {cache_key}")

                except Exception as e:
                    logger.warning(f"Cache set failed for {tool_name}: {e}")
                    _cache_stats.record_error()

            return result

        return wrapper
    return decorator


async def clear_tool_cache(tool_name: Optional[str] = None) -> int:
    """Clear cached tool results.

    Args:
        tool_name: Specific tool name to clear, or None for all tools

    Returns:
        Number of keys cleared
    """
    try:
        from app.infrastructure.external.cache import get_cache
        cache = get_cache()

        if tool_name:
            pattern = f"tool:{tool_name}:*"
        else:
            pattern = "tool:*"

        cleared = await cache.clear_pattern(pattern)
        logger.info(f"Cleared {cleared} cached tool results matching '{pattern}'")
        return cleared

    except Exception as e:
        logger.error(f"Failed to clear tool cache: {e}")
        return 0


async def get_cached_keys(tool_name: Optional[str] = None) -> list[str]:
    """Get list of cached tool result keys.

    Args:
        tool_name: Specific tool name filter, or None for all

    Returns:
        List of cache keys
    """
    try:
        from app.infrastructure.external.cache import get_cache
        cache = get_cache()

        if tool_name:
            pattern = f"tool:{tool_name}:*"
        else:
            pattern = "tool:*"

        return await cache.keys(pattern)

    except Exception as e:
        logger.error(f"Failed to get cached keys: {e}")
        return []
