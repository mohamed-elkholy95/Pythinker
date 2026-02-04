from typing import Any, Protocol


class Cache(Protocol):
    """Cache storage interface for temporary data storage"""

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store a value with optional TTL (time to live)

        Args:
            key: The cache key
            value: The value to store (will be JSON serialized)
            ttl: Time to live in seconds, None means no expiration

        Returns:
            bool: True if stored successfully, False otherwise
        """
        ...

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from cache

        Args:
            key: The cache key

        Returns:
            Any: The stored value (JSON deserialized), None if not found or expired
        """
        ...

    async def delete(self, key: str) -> bool:
        """Delete a value from cache

        Args:
            key: The cache key

        Returns:
            bool: True if deleted successfully, False if key didn't exist
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache

        Args:
            key: The cache key

        Returns:
            bool: True if key exists and not expired, False otherwise
        """
        ...

    async def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key

        Args:
            key: The cache key

        Returns:
            int: Remaining TTL in seconds, None if key doesn't exist or has no expiration
        """
        ...

    async def keys(self, pattern: str) -> list[str]:
        """Get all keys matching a pattern

        Args:
            pattern: Pattern to match (implementation specific)

        Returns:
            list[str]: List of matching keys
        """
        ...

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern

        Args:
            pattern: Pattern to match

        Returns:
            int: Number of keys deleted
        """
        ...


# ===== Null Implementation =====


class NullCache:
    """Null implementation of Cache that does nothing.

    Use this when cache is not configured or in tests.
    """

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return False

    async def get(self, key: str) -> Any | None:
        return None

    async def delete(self, key: str) -> bool:
        return False

    async def exists(self, key: str) -> bool:
        return False

    async def get_ttl(self, key: str) -> int | None:
        return None

    async def keys(self, pattern: str) -> list[str]:
        return []

    async def clear_pattern(self, pattern: str) -> int:
        return 0


# ===== Module-level Cache Singleton =====

_cache: Cache | None = None
_null_cache: NullCache | None = None


def get_null_cache() -> NullCache:
    """Get singleton null cache instance."""
    global _null_cache
    if _null_cache is None:
        _null_cache = NullCache()
    return _null_cache


def set_cache(cache: Cache) -> None:
    """Set the global cache instance.

    This should be called during application startup to inject the
    infrastructure cache implementation.

    Args:
        cache: Cache implementation to use globally
    """
    global _cache
    _cache = cache


def get_cache() -> Cache:
    """Get the global cache instance.

    Returns the configured cache or a null cache if none is configured.
    Domain services should use this function to access caching.

    Returns:
        Cache implementation
    """
    global _cache
    if _cache is None:
        return get_null_cache()
    return _cache
