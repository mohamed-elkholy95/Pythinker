import asyncio
import json
import logging
from typing import Any

from app.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis implementation of Cache interface with lazy initialization.

    Uses a single initialization with lock to avoid repeated initialize() calls
    on every operation, reducing overhead and connection pool pressure.
    """

    def __init__(self):
        self.redis_client = get_redis()
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self) -> None:
        """Ensure Redis is initialized (lazy, thread-safe).

        Only calls initialize() once, subsequent calls are fast no-ops.
        """
        if self._initialized:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if not self._initialized:
                await self.redis_client.initialize()
                self._initialized = True

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store a value with optional TTL."""
        try:
            await self._ensure_initialized()

            # Serialize value to JSON
            serialized_value = json.dumps(value)

            if ttl is not None:
                result = await self.redis_client.client.setex(key, ttl, serialized_value)
            else:
                result = await self.redis_client.client.set(key, serialized_value)

            return result is not None

        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e!s}")
            # Mark as uninitialized to allow reconnection on next operation
            self._initialized = False
            return False

    async def get(self, key: str) -> Any | None:
        """Retrieve a value from cache."""
        try:
            await self._ensure_initialized()

            value = await self.redis_client.client.get(key)
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
        try:
            await self._ensure_initialized()

            result = await self.redis_client.client.delete(key)
            return result > 0

        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e!s}")
            self._initialized = False
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        try:
            await self._ensure_initialized()

            result = await self.redis_client.client.exists(key)
            return result > 0

        except Exception as e:
            logger.error(f"Failed to check existence of cache key {key}: {e!s}")
            self._initialized = False
            return False

    async def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key."""
        try:
            await self._ensure_initialized()

            ttl = await self.redis_client.client.ttl(key)

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
        """Get all keys matching a pattern."""
        try:
            await self._ensure_initialized()

            keys = await self.redis_client.client.keys(pattern)
            return keys if keys else []

        except Exception as e:
            logger.error(f"Failed to get keys with pattern {pattern}: {e!s}")
            self._initialized = False
            return []

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern."""
        try:
            await self._ensure_initialized()

            keys = await self.keys(pattern)
            if not keys:
                return 0

            return await self.redis_client.client.delete(*keys)

        except Exception as e:
            logger.error(f"Failed to clear keys with pattern {pattern}: {e!s}")
            self._initialized = False
            return 0
