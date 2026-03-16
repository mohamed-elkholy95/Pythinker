import asyncio
import json
import logging
import secrets
import time
from typing import Any

from app.core.config import get_settings
from app.infrastructure.storage.redis import get_cache_redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis implementation of Cache interface with lazy initialization.

    Uses a single initialization with lock to avoid repeated initialize() calls
    on every operation, reducing overhead and connection pool pressure.

    Features:
    - TTL jitter to prevent thundering herd on mass cache expiry
    - Stale-while-revalidate (SWR) pattern for latency-sensitive reads
    - Pipeline-based bulk key deletion for efficient pattern clearing
    """

    def __init__(self):
        self.redis_client = get_cache_redis()  # None when redis_cache_enabled=False
        self._initialized = False
        self._init_lock = asyncio.Lock()
        try:
            settings = get_settings()
            self._scan_count = max(1, settings.redis_scan_count)
            self._ttl_jitter_percent = settings.redis_cache_ttl_jitter_percent
            self._swr_enabled = settings.redis_cache_swr_enabled
        except Exception:
            self._scan_count = 1000
            self._ttl_jitter_percent = 0.1
            self._swr_enabled = False

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

    def _jittered_ttl(self, ttl: int) -> int:
        """Apply random jitter to TTL to prevent thundering herd on mass expiry.

        Returns TTL ± jitter_percent, with a minimum of 1 second.
        """
        if self._ttl_jitter_percent <= 0 or ttl <= 0:
            return ttl
        jitter_range = int(ttl * self._ttl_jitter_percent)
        if jitter_range == 0:
            return ttl
        return max(1, ttl + secrets.randbelow(2 * jitter_range + 1) - jitter_range)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store a value with optional TTL (jitter applied automatically)."""
        if not self.available:
            return False
        try:
            await self._ensure_initialized()

            # Serialize value to JSON
            serialized_value = json.dumps(value)

            if ttl is not None:
                effective_ttl = self._jittered_ttl(ttl)
                result = await self.redis_client.call("setex", key, effective_ttl, serialized_value)
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
        """Clear all keys matching a pattern using SCAN + pipeline UNLINK.

        Accumulates all matching keys from SCAN, then deletes via Redis
        pipeline in batches of 1000 for reduced round-trip overhead.
        """
        if not self.available:
            return 0
        try:
            await self._ensure_initialized()

            # Accumulate all matching keys
            cursor: int | str = 0
            all_keys: list[str] = []
            while True:
                cursor, batch = await self.redis_client.call(
                    "scan",
                    cursor=cursor,
                    match=pattern,
                    count=self._scan_count,
                )
                if batch:
                    all_keys.extend(batch)
                if cursor in (0, "0"):
                    break

            if not all_keys:
                return 0

            # Pipeline UNLINK in batches of 1000
            deleted_total = 0
            pipeline_batch_size = 1000
            for i in range(0, len(all_keys), pipeline_batch_size):
                batch = all_keys[i : i + pipeline_batch_size]
                try:
                    deleted_total += await self.redis_client.call("unlink", *batch)
                except Exception:
                    # Fallback for Redis builds/ACLs where UNLINK is unavailable.
                    deleted_total += await self.redis_client.call("delete", *batch)

            return deleted_total

        except Exception as e:
            logger.error(f"Failed to clear keys with pattern {pattern}: {e!s}")
            self._initialized = False
            return 0

    async def increment(self, key: str, ttl: int | None = None) -> int | None:
        """Atomically increment a counter and optionally set TTL on first creation."""
        if not self.available:
            return None
        try:
            await self._ensure_initialized()

            new_value: int = await self.redis_client.call("incr", key)
            # Set TTL only when the key is first created (value == 1)
            if new_value == 1 and ttl is not None:
                await self.redis_client.call("expire", key, ttl)
            return new_value

        except Exception as e:
            logger.error(f"Failed to increment cache key {key}: {e!s}")
            self._initialized = False
            return None

    # --- Stale-While-Revalidate (SWR) Pattern ---

    async def set_with_swr(self, key: str, value: Any, soft_ttl: int, hard_ttl: int) -> bool:
        """Store a value with soft + hard TTL for stale-while-revalidate.

        The value is wrapped in a JSON envelope with a soft expiry timestamp.
        Redis TTL is set to hard_ttl (the actual eviction time).

        Args:
            key: Cache key.
            value: JSON-serializable value.
            soft_ttl: Seconds until the value is considered stale (triggers revalidation).
            hard_ttl: Seconds until Redis evicts the key entirely.

        Returns:
            True if stored successfully.
        """
        if not self.available or not self._swr_enabled:
            return await self.set(key, value, ttl=soft_ttl)
        try:
            await self._ensure_initialized()

            envelope = {
                "v": value,
                "soft_expires": time.time() + soft_ttl,
            }
            serialized = json.dumps(envelope)
            effective_hard_ttl = self._jittered_ttl(hard_ttl)
            result = await self.redis_client.call("setex", key, effective_hard_ttl, serialized)
            return result is not None

        except Exception as e:
            logger.error(f"Failed to set SWR cache key {key}: {e!s}")
            self._initialized = False
            return False

    async def get_with_swr(self, key: str) -> tuple[Any | None, bool]:
        """Retrieve a value with stale-while-revalidate awareness.

        Returns:
            Tuple of (value, is_stale).
            - (value, False) — fresh cache hit.
            - (value, True) — stale hit (caller should revalidate in background).
            - (None, False) — hard cache miss.
        """
        if not self.available:
            return None, False
        if not self._swr_enabled:
            value = await self.get(key)
            return value, False
        try:
            await self._ensure_initialized()

            raw = await self.redis_client.call("get", key)
            if raw is None:
                return None, False

            envelope = json.loads(raw)
            # Support both SWR envelopes and plain values
            if isinstance(envelope, dict) and "v" in envelope and "soft_expires" in envelope:
                is_stale = time.time() > envelope["soft_expires"]
                return envelope["v"], is_stale
            # Plain value (set without SWR)
            return envelope, False

        except json.JSONDecodeError:
            logger.error(f"Failed to deserialize SWR cache value for key {key}")
            await self.delete(key)
            return None, False
        except Exception as e:
            logger.error(f"Failed to get SWR cache key {key}: {e!s}")
            self._initialized = False
            return None, False
