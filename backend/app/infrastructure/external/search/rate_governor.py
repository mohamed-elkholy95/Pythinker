"""Redis global rate governor for search API providers.

Implements a token bucket shared across parallel tasks.
Key: search_rate_gov:{provider}:{egress_ip}
Falls back to in-memory token bucket when Redis is unavailable.
"""

import asyncio
import logging
import socket
import time
from typing import Any

logger = logging.getLogger(__name__)

LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local state = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(state[1]) or capacity
local last_refill = tonumber(state[2]) or now

local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1.0 then
    tokens = tokens - 1.0
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 0
end
"""

_egress_ip: str | None = None


def _get_egress_ip() -> str:
    """Detect this host's egress IP (cached after first call)."""
    global _egress_ip
    if _egress_ip is None:
        try:
            with socket.create_connection(("8.8.8.8", 80), timeout=2) as s:
                _egress_ip = s.getsockname()[0]
        except OSError:
            _egress_ip = "unknown"
    return _egress_ip


class SearchRateGovernor:
    """Token bucket rate governor shared across parallel tasks per {provider}:{egress_ip}.

    Usage:
        governor = SearchRateGovernor(redis=redis_client, provider="tavily", rps=3.0, burst=5.0)
        if not await governor.acquire():
            # Throttled — caller should sleep briefly before retrying
            await asyncio.sleep(1.0 / governor.rps + random.uniform(0, 0.3))

    Falls back to in-memory token bucket when Redis is unavailable or fails.
    """

    def __init__(
        self,
        redis: Any | None,
        provider: str,
        rps: float = 3.0,
        burst: float = 5.0,
    ) -> None:
        self._redis = redis
        self._provider = provider
        self._rps = rps
        self._burst = burst
        self._script: Any = None
        # In-memory fallback state
        self._in_memory_tokens: float = burst
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def rps(self) -> float:
        """Configured requests per second."""
        return self._rps

    def _bucket_key(self) -> str:
        """Redis key for this provider+IP combination."""
        return f"search_rate_gov:{self._provider}:{_get_egress_ip()}"

    async def acquire(self) -> bool:
        """Attempt to consume one token from the bucket.

        Returns:
            True if request is allowed, False if throttled.
            Never raises — falls back to in-memory on Redis failure.
        """
        if self._redis is None:
            return await self._acquire_in_memory()
        try:
            if self._script is None:
                self._script = self._redis.register_script(LUA_TOKEN_BUCKET)
            result = await self._script(
                keys=[self._bucket_key()],
                args=[self._burst, self._rps, time.time()],
            )
            return bool(result)
        except Exception as exc:
            logger.debug("SearchRateGovernor Redis error (%s), using in-memory fallback", exc)
            return await self._acquire_in_memory()

    async def _acquire_in_memory(self) -> bool:
        """Thread-safe in-memory token bucket fallback."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._in_memory_tokens = min(
                self._burst,
                self._in_memory_tokens + elapsed * self._rps,
            )
            self._last_refill = now
            if self._in_memory_tokens >= 1.0:
                self._in_memory_tokens -= 1.0
                return True
            return False
