"""
Generic API Key Pool with multi-strategy rotation.

Supports:
- Round-robin rotation (even distribution)
- Failover rotation (priority-based)
- Weighted rotation (probability-based)
- Quota-aware rotation (future Phase 2)
- Redis-based health tracking with TTL recovery
- Exponential backoff with jitter

Industry patterns from AWS, Google Cloud, Apache APISIX.
"""

import hashlib
import logging
import random
from dataclasses import dataclass
from enum import Enum

from redis.asyncio import Redis

from app.infrastructure.observability.prometheus_metrics import (
    api_key_exhaustions_total,
    api_key_health_score,
    api_key_selections_total,
)

logger = logging.getLogger(__name__)


class RotationStrategy(str, Enum):
    """API key rotation strategies."""

    ROUND_ROBIN = "round_robin"
    FAILOVER = "failover"
    WEIGHTED = "weighted"
    QUOTA_AWARE = "quota_aware"


class KeyHealthStatus(str, Enum):
    """API key health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    EXHAUSTED = "exhausted"
    INVALID = "invalid"


@dataclass
class APIKeyConfig:
    """Configuration for a single API key."""

    key: str
    weight: float = 1.0
    priority: int = 0
    quota_per_hour: int | None = None


class APIKeyPool:
    """
    Generic API key pool with multi-strategy rotation.

    Example:
        ```python
        keys = [
            APIKeyConfig(key="key1", weight=2.0, priority=0),
            APIKeyConfig(key="key2", weight=1.0, priority=1),
        ]
        pool = APIKeyPool(provider="openai", keys=keys, strategy=RotationStrategy.WEIGHTED, redis_client=redis_client)
        key = await pool.get_healthy_key()
        ```
    """

    def __init__(
        self,
        provider: str,
        keys: list[APIKeyConfig],
        strategy: RotationStrategy,
        redis_client: Redis,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
    ):
        """
        Initialize API key pool.

        Args:
            provider: Provider name (e.g., "openai", "serper", "tavily")
            keys: List of API key configurations
            strategy: Rotation strategy to use
            redis_client: Redis client for health tracking
            base_backoff_seconds: Base delay for exponential backoff (default: 1s)
            max_backoff_seconds: Maximum backoff delay (default: 60s)

        Raises:
            ValueError: If keys list is empty
        """
        if not keys:
            raise ValueError("keys list cannot be empty")

        self.provider = provider
        self.keys = keys
        self.strategy = strategy
        self._redis = redis_client
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

        # Round-robin state
        self._round_robin_index = 0

    async def get_healthy_key(self) -> str | None:
        """
        Get next healthy API key using configured strategy.

        Returns:
            API key string, or None if no healthy keys are available
        """
        if self.strategy == RotationStrategy.ROUND_ROBIN:
            return await self._round_robin()
        if self.strategy == RotationStrategy.FAILOVER:
            return await self._failover()
        if self.strategy == RotationStrategy.WEIGHTED:
            return await self._weighted_selection()
        raise ValueError(f"Unsupported strategy: {self.strategy}")

    async def _round_robin(self) -> str | None:
        """
        Round-robin rotation with health checks.

        Cycles through keys evenly, skipping exhausted/invalid keys.

        Returns:
            API key string, or None if no healthy keys are available
        """
        attempts = 0
        max_attempts = len(self.keys) * 2  # Allow 2 full rotations

        while attempts < max_attempts:
            key_config = self.keys[self._round_robin_index]
            self._round_robin_index = (self._round_robin_index + 1) % len(self.keys)
            attempts += 1

            if await self._is_healthy(key_config.key):
                # Record successful selection
                key_hash = self._hash_key(key_config.key)
                api_key_selections_total.inc({"provider": self.provider, "key_id": key_hash, "status": "success"})

                # Update health score
                api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 1.0)

                return key_config.key

        # All keys unhealthy
        logger.warning(f"[{self.provider}] All {len(self.keys)} keys exhausted")

        # Record exhaustion
        api_key_selections_total.inc({"provider": self.provider, "key_id": "all", "status": "exhausted"})

        return None

    async def _failover(self) -> str | None:
        """
        Failover rotation (priority-based).

        Returns first healthy key by priority (lower priority = higher precedence).

        Returns:
            API key string, or None if no healthy keys are available
        """
        # Sort by priority (lower number = higher priority)
        sorted_keys = sorted(self.keys, key=lambda k: k.priority)

        for key_config in sorted_keys:
            if await self._is_healthy(key_config.key):
                # Record successful selection
                key_hash = self._hash_key(key_config.key)
                api_key_selections_total.inc({"provider": self.provider, "key_id": key_hash, "status": "success"})

                # Update health score
                api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 1.0)

                return key_config.key

        # All keys unhealthy
        logger.warning(f"[{self.provider}] All {len(self.keys)} keys exhausted")

        # Record exhaustion
        api_key_selections_total.inc({"provider": self.provider, "key_id": "all", "status": "exhausted"})

        return None

    async def _weighted_selection(self) -> str | None:
        """
        Weighted random selection.

        Selects keys based on weights, skipping exhausted/invalid keys.

        Returns:
            API key string, or None if no healthy keys are available
        """
        # Filter healthy keys
        healthy_keys = []
        weights = []

        for key_config in self.keys:
            if await self._is_healthy(key_config.key):
                healthy_keys.append(key_config)
                weights.append(key_config.weight)

        if not healthy_keys:
            # All keys unhealthy
            logger.warning(f"[{self.provider}] All {len(self.keys)} keys exhausted")

            # Record exhaustion
            api_key_selections_total.inc({"provider": self.provider, "key_id": "all", "status": "exhausted"})

            return None

        # Use random.choices for weighted selection
        selected = random.choices(healthy_keys, weights=weights, k=1)[0]  # noqa: S311

        # Record successful selection
        key_hash = self._hash_key(selected.key)
        api_key_selections_total.inc({"provider": self.provider, "key_id": key_hash, "status": "success"})

        # Update health score
        api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 1.0)

        return selected.key

    async def _is_healthy(self, key: str) -> bool:
        """
        Check if API key is healthy.

        Checks Redis for exhausted/invalid state. Keys marked exhausted
        will become healthy again after TTL expires.

        Args:
            key: API key to check

        Returns:
            True if key is healthy, False otherwise
        """
        key_hash = self._hash_key(key)

        # Check if key is invalid (permanent)
        invalid_key = f"api_key:invalid:{self.provider}:{key_hash}"
        if await self._redis.exists(invalid_key):
            return False

        # Check if key is exhausted (temporary with TTL)
        exhausted_key = f"api_key:exhausted:{self.provider}:{key_hash}"
        is_exhausted = await self._redis.exists(exhausted_key)
        return not is_exhausted

    async def mark_exhausted(self, key: str, ttl_seconds: int) -> None:
        """
        Mark API key as exhausted with TTL.

        After TTL expires, key becomes healthy again.

        Args:
            key: API key to mark as exhausted
            ttl_seconds: Time-to-live in seconds (e.g., 3600 for 1 hour)
        """
        key_hash = self._hash_key(key)
        redis_key = f"api_key:exhausted:{self.provider}:{key_hash}"
        await self._redis.setex(redis_key, ttl_seconds, KeyHealthStatus.EXHAUSTED.value)

        # Record exhaustion metric
        api_key_exhaustions_total.inc({"provider": self.provider, "reason": "quota"})

        # Update health score
        api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 0.0)

        logger.warning(f"[{self.provider}] Key {key_hash} marked EXHAUSTED, auto-recovery in {ttl_seconds}s")

    async def mark_invalid(self, key: str) -> None:
        """
        Mark API key as invalid permanently.

        Invalid keys are never retried (e.g., revoked keys, wrong keys).

        Args:
            key: API key to mark as invalid
        """
        key_hash = self._hash_key(key)
        redis_key = f"api_key:invalid:{self.provider}:{key_hash}"
        await self._redis.set(redis_key, KeyHealthStatus.INVALID.value)

        # Record invalidation metric
        api_key_exhaustions_total.inc({"provider": self.provider, "reason": "invalid"})

        # Update health score
        api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 0.0)

        logger.error(f"[{self.provider}] Key {key_hash} marked INVALID. Manual intervention required.")

    def get_backoff_delay(self, key: str, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Formula: min(base * 2^attempt, max) ± 25% jitter

        Args:
            key: API key (for potential future per-key backoff)
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Calculate exponential backoff
        delay = self.base_backoff_seconds * (2**attempt)

        # Cap at max
        delay = min(delay, self.max_backoff_seconds)

        # Add jitter (±25%)
        jitter = delay * 0.25
        delay = delay + random.uniform(-jitter, jitter)  # noqa: S311

        # Ensure non-negative
        return max(0, delay)

    def _hash_key(self, key: str) -> str:
        """
        Hash API key for Redis storage.

        Uses SHA256 to avoid storing raw keys in Redis.

        Args:
            key: API key to hash

        Returns:
            First 8 characters of SHA256 hash
        """
        return hashlib.sha256(key.encode()).hexdigest()[:8]
