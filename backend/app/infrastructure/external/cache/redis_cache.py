import asyncio
import json
import logging
from typing import Any

from app.core.config import get_settings
from app.infrastructure.storage.redis import get_cache_redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis implementation of Cache interface with lazy initialization.

    Uses a single initialization with lock to avoid repeated initialize() calls
    on every operation, reducing overhead and connection pool pressure.
    """

    def __init__(self):
        self.redis_client = get_cache_redis()  # None when redis_cache_enabled=False
        self._initialized = False
        self._init_lock = asyncio.Lock()
        try:
            settings = get_settings()
            self._scan_count = max(1, settings.redis_scan_count)
        except Exception:
            self._scan_count = 1000

    @property
    def available(self) -> bool:
        """Whether cache Redis is configured and available."""
        return self.redis_client is not None

    async def _ensure_initialized(self) -> None:
        """Ensure Redis is initialized (lazy, thread-safe).

        Only calls initialize() once, subsequent calls are fast no-ops.
        Returns immediately when cache Redis is disabled.
        """
        if self.redis_client is None:
            return
        if self._initialized:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if not self._initialized:
                await self.redis_client.initialize()
                self._initialized = True

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store a value with optional TTL."""
        if not self.available:
            return False
        try:
            await self._ensure_initialized()

            # Serialize value to JSON
            serialized_value = json.dumps(value)

            if ttl is not None:
                result = await self.redis_client.call("setex", key, ttl, serialized_value)
            else:
                result = await self.redis_client.call("set", key, serialized_value)

            return result is not None

        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e!s}")
            # Mark as uninitialized to allow reconnection on next operation
            self._initialized = False
            return False

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from cache."""
        if not self.available:
            return None
        try:
            await self._ensure_initialized()

            value = await self.redis_client.call("get", key)
            if value is None:
                return None

            return json.loads(value)

        except json.JSONDecodeError:
            logger.error(f"Failed to deserialize cache value for key {key}")
            await self.delete(key)
            return None
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e!s}")
            self._initialized = False
            return None

    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        if not self.available:
            return False
        try:
            await self._ensure_initialized()

            result = await self.redis_client.call("delete", key)
            return result > 0

        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e!s}")
            self._initialized = False
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if not self.available:
            return False
        try:
            await self._ensure_initialized()

            result = await self.redis_client.call("exists", key)
            return result > 0

        except Exception as e:
            logger.error(f"Failed to check existence of cache key {key}: {e!s}")
            self._initialized = False
            return False

    async def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key."""
        if not self.available:
            return None
        try:
            await self._ensure_initialized()

            ttl = await self.redis_client.call("ttl", key)

            if ttl == -2:
                return None  # Key doesn't exist
            if ttl == -1:
                return None  # Key exists but has no expiration
            return ttl

        except Exception as e:
            logger.error(f"Failed to get TTL for cache key {key}: {e!s}")
            self._initialized = False
            return None

    async def keys(self, pattern: str) -> list[str]:
        """Get all keys matching a pattern using SCAN (non-blocking)."""
        if not self.available:
            return []
        try:
            await self._ensure_initialized()

            cursor: int | str = 0
            matched_keys: list[str] = []
            while True:
                cursor, batch = await self.redis_client.call(
                    "scan",
                    cursor=cursor,
                    match=pattern,
                    count=self._scan_count,
                )
                if batch:
                    matched_keys.extend(batch)
                if cursor in (0, "0"):
                    break

            return matched_keys

        except Exception as e:
            logger.error(f"Failed to get keys with pattern {pattern}: {e!s}")
            self._initialized = False
            return []

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern using SCAN + UNLINK/DEL."""
        if not self.available:
            return 0
        try:
            await self._ensure_initialized()

            cursor: int | str = 0
            deleted_total = 0

            while True:
                cursor, batch = await self.redis_client.call(
                    "scan",
                    cursor=cursor,
                    match=pattern,
                    count=self._scan_count,
                )
                if batch:
                    try:
                        deleted_total += await self.redis_client.call("unlink", *batch)
                    except Exception:
                        # Fallback for Redis builds/ACLs where UNLINK is unavailable.
                        deleted_total += await self.redis_client.call("delete", *batch)
                if cursor in (0, "0"):
                    break

            return deleted_total

        except Exception as e:
            logger.error(f"Failed to clear keys with pattern {pattern}: {e!s}")
            self._initialized = False
            return 0
