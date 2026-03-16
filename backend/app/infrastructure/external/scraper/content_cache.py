"""Multi-tier content cache for scraped data.

L1 uses an in-process LRU cache with TTL.
L2 reuses the application's cache abstraction when available.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from app.domain.external.stealth_types import FetchResult, StealthMode

if TYPE_CHECKING:
    from app.domain.external.cache import Cache

logger = logging.getLogger(__name__)


class ContentCache:
    """Mode-aware multi-tier cache for scraped content."""

    _L2_PREFIX = "scrape:cache:"

    def __init__(
        self,
        l1_max_size: int = 100,
        l2_ttl: int = 300,
        include_mode_in_key: bool = True,
        redis_client: Cache | None = None,
    ) -> None:
        self._redis = redis_client
        self._include_mode = include_mode_in_key
        self._l1_max_size = max(1, l1_max_size)
        self._l1_ttl = 60.0
        self._l2_ttl = max(1, l2_ttl)
        self._l1_cache: OrderedDict[str, tuple[FetchResult, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _make_key(self, url: str, mode: StealthMode) -> str:
        raw = f"{url}:{mode.value}" if self._include_mode else url
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _make_l2_key(self, key: str) -> str:
        return f"{self._L2_PREFIX}{key}"

    @staticmethod
    def _normalize_result(result: FetchResult | dict[str, object]) -> FetchResult:
        mode = result.get("mode_used", StealthMode.HTTP)
        if not isinstance(mode, StealthMode):
            mode = StealthMode(str(mode))

        return FetchResult(
            content=str(result.get("content", "")),
            url=str(result.get("url", "")),
            final_url=str(result.get("final_url", result.get("url", ""))),
            mode_used=mode,
            proxy_used=result.get("proxy_used"),
            response_time_ms=float(result.get("response_time_ms", 0.0)),
            from_cache=bool(result.get("from_cache", False)),
            cloudflare_solved=bool(result.get("cloudflare_solved", False)),
            error=result.get("error"),
        )

    @staticmethod
    def _serialize_result(result: FetchResult) -> dict[str, object]:
        serialized = dict(result)
        mode = serialized.get("mode_used")
        if isinstance(mode, StealthMode):
            serialized["mode_used"] = mode.value
        return serialized

    async def get(self, url: str, mode: StealthMode) -> FetchResult | None:
        """Return a cached result if present and not expired."""
        key = self._make_key(url, mode)
        cached = await self._get_l1(key)
        if cached is not None:
            return cached

        if self._redis is None:
            return None

        try:
            cached_l2 = await self._redis.get(self._make_l2_key(key))
        except Exception:
            logger.warning("content_cache_l2_get_failed", exc_info=True)
            return None

        if not isinstance(cached_l2, dict):
            return None

        result = self._normalize_result(cached_l2)
        await self._set_l1(key, result)
        return result

    async def set(self, url: str, mode: StealthMode, result: FetchResult) -> None:
        """Store a result in L1 and, when available, L2."""
        key = self._make_key(url, mode)
        normalized = self._normalize_result(result)
        await self._set_l1(key, normalized)

        if self._redis is None:
            return

        try:
            await self._redis.set(self._make_l2_key(key), self._serialize_result(normalized), ttl=self._l2_ttl)
        except Exception:
            logger.warning("content_cache_l2_set_failed", exc_info=True)

    async def invalidate(self, url: str | None = None) -> int:
        """Invalidate one URL or the full cache."""
        if url is None:
            return await self._invalidate_all()
        return await self._invalidate_url(url)

    async def get_stats(self) -> dict[str, int | bool]:
        """Return cache stats for observability and API reporting."""
        async with self._lock:
            l1_size = len(self._l1_cache)
        return {
            "l1_size": l1_size,
            "l1_max_size": self._l1_max_size,
            "l2_enabled": self._redis is not None,
            "l2_ttl": self._l2_ttl,
        }

    async def _get_l1(self, key: str) -> FetchResult | None:
        async with self._lock:
            cached = self._l1_cache.get(key)
            if cached is None:
                return None

            result, expiry = cached
            if expiry <= time.monotonic():
                del self._l1_cache[key]
                return None

            self._l1_cache.move_to_end(key)
            return result

    async def _set_l1(self, key: str, result: FetchResult) -> None:
        expiry = time.monotonic() + self._l1_ttl
        async with self._lock:
            if key in self._l1_cache:
                del self._l1_cache[key]
            self._l1_cache[key] = (result, expiry)
            self._l1_cache.move_to_end(key)
            while len(self._l1_cache) > self._l1_max_size:
                self._l1_cache.popitem(last=False)

    async def _invalidate_all(self) -> int:
        async with self._lock:
            l1_count = len(self._l1_cache)
            self._l1_cache.clear()

        l2_count = 0
        if self._redis is not None:
            try:
                l2_count = await self._redis.clear_pattern(f"{self._L2_PREFIX}*")
            except Exception:
                logger.warning("content_cache_l2_clear_failed", exc_info=True)

        return l1_count + l2_count

    async def _invalidate_url(self, url: str) -> int:
        count = 0
        keys = {self._make_key(url, mode) for mode in StealthMode}

        async with self._lock:
            for key in keys:
                if key in self._l1_cache:
                    del self._l1_cache[key]
                    count += 1

        if self._redis is not None:
            for key in keys:
                try:
                    deleted = await self._redis.delete(self._make_l2_key(key))
                except Exception:
                    logger.warning("content_cache_l2_delete_failed", exc_info=True)
                    continue
                count += int(bool(deleted))

        return count
