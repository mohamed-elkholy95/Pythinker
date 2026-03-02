"""
Generic API Key Pool with multi-strategy rotation.

Supports:
- Round-robin rotation (even distribution)
- Failover rotation (priority-based)
- Weighted rotation (probability-based)
- Quota-aware rotation (future Phase 2)
- Redis-based health tracking with TTL recovery
- Exponential backoff with jitter
- 7-category error classification with granular cooldowns
- Circuit breaker (CLOSED → OPEN → HALF_OPEN) for upstream outage protection
- Consecutive rate-limit tracking with exponential backoff progression
- Dual quota detection (HTTP status + response body keyword scan)

Industry patterns from AWS, Google Cloud, Apache APISIX, MCP API Rotators.
"""

import asyncio
import contextlib
import email.utils
import hashlib
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum

from redis.asyncio import Redis

from app.core.prometheus_metrics import (
    api_key_early_recoveries_total,
    api_key_exhaustions_total,
    api_key_health_score,
    api_key_selections_total,
)
from app.core.retry import RetryConfig, calculate_delay
from app.domain.exceptions.base import LLMKeysExhaustedError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dual quota detection keywords — scanned in both HTTP error text and
# successful response bodies to catch APIs that return 200 OK with errors.
# ---------------------------------------------------------------------------
QUOTA_KEYWORDS = frozenset(
    {
        "quota",
        "limit exceeded",
        "usage limit",
        "monthly limit",
        "not enough credits",
        "billing",
        "payment required",
        "credits",
        "insufficient",
    }
)


def _text_has_quota_keywords(text: str) -> bool:
    """Check if text contains any quota-related keywords (case-insensitive)."""
    lower = text.lower()
    return any(kw in lower for kw in QUOTA_KEYWORDS)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class ErrorType(str, Enum):
    """7-category error taxonomy for API key rotation decisions."""

    CLIENT_ERROR = "client_error"  # 400 — bad request, not the key's fault
    AUTH_ERROR = "auth_error"  # 401/403 — invalid or revoked key
    RATE_LIMITED = "rate_limited"  # 429 — rate limit hit
    QUOTA_EXHAUSTED = "quota_exhausted"  # Quota/billing keywords in body
    UPSTREAM_5XX = "upstream_5xx"  # 500+ — upstream server error
    NETWORK_ERROR = "network_error"  # Connection timeout/reset
    OTHER = "other"  # Unclassified


# Default cooldown per error type (seconds)
_ERROR_COOLDOWNS: dict[ErrorType, int] = {
    ErrorType.CLIENT_ERROR: 0,  # No cooldown — bad request from caller
    ErrorType.AUTH_ERROR: 3600,  # 1 hour
    ErrorType.RATE_LIMITED: 60,  # Base for exponential backoff
    ErrorType.QUOTA_EXHAUSTED: 86400,  # 24 hours
    ErrorType.UPSTREAM_5XX: 30,  # 30 seconds
    ErrorType.NETWORK_ERROR: 15,  # 15 seconds
    ErrorType.OTHER: 60,  # 1 minute
}


def classify_error(
    status_code: int | None = None,
    body_text: str = "",
    is_network_error: bool = False,
) -> tuple[ErrorType, int]:
    """Classify an API error into one of 7 categories with a default cooldown.

    Checks in order: network → quota keywords → status code → fallback.

    Args:
        status_code: HTTP status code (None for connection-level errors)
        body_text: Response body or error message text
        is_network_error: True if the error is a connection/timeout failure

    Returns:
        Tuple of (ErrorType, default_cooldown_seconds)
    """
    # Network errors (connection refused, timeout, DNS failure)
    if is_network_error:
        return ErrorType.NETWORK_ERROR, _ERROR_COOLDOWNS[ErrorType.NETWORK_ERROR]

    # Check body text for quota keywords (catches 200 OK with embedded errors)
    if body_text and _text_has_quota_keywords(body_text):
        return ErrorType.QUOTA_EXHAUSTED, _ERROR_COOLDOWNS[ErrorType.QUOTA_EXHAUSTED]

    # Status code classification
    if status_code is not None:
        if status_code == 400:
            return ErrorType.CLIENT_ERROR, _ERROR_COOLDOWNS[ErrorType.CLIENT_ERROR]
        if status_code in (401, 403):
            return ErrorType.AUTH_ERROR, _ERROR_COOLDOWNS[ErrorType.AUTH_ERROR]
        if status_code == 402:
            return ErrorType.QUOTA_EXHAUSTED, _ERROR_COOLDOWNS[ErrorType.QUOTA_EXHAUSTED]
        if status_code == 429:
            return ErrorType.RATE_LIMITED, _ERROR_COOLDOWNS[ErrorType.RATE_LIMITED]
        if status_code >= 500:
            return ErrorType.UPSTREAM_5XX, _ERROR_COOLDOWNS[ErrorType.UPSTREAM_5XX]

    return ErrorType.OTHER, _ERROR_COOLDOWNS[ErrorType.OTHER]


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # All requests rejected
    HALF_OPEN = "half_open"  # One probe request allowed


# Circuit breaker defaults
CIRCUIT_BREAKER_THRESHOLD = 5  # Consecutive 5xx failures to trip
CIRCUIT_BREAKER_RESET_TIMEOUT = 300  # Seconds before OPEN → HALF_OPEN


class CircuitBreaker:
    """Circuit breaker to protect against cascading upstream failures.

    Tracks two independent failure counters:
    - 5xx errors: 5 consecutive failures → OPEN for 300 s (slow infrastructure recovery)
    - 429 errors: 5 consecutive rate-limits → OPEN for 45 s (short transient burst)

    Client errors (4xx) do NOT trip the circuit — the API is working fine.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        reset_timeout: float = CIRCUIT_BREAKER_RESET_TIMEOUT,
    ):
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._half_open_in_flight = False

        # 429-specific thresholds (short window — transient rate-limit, not infra failure)
        self._429_threshold: int = 5
        self._429_open_seconds: float = 45.0
        self._429_count: int = 0

        # Store which type triggered the open (for open_seconds property)
        self._open_reason: str = "none"  # "429_storm" | "5xx_storm"

    @property
    def open_seconds(self) -> float:
        """Returns the open window duration depending on what triggered the open.

        - 429 storm: 45 s (transient rate-limit burst, recovers quickly)
        - 5xx storm: 300 s (infrastructure failure, needs longer recovery)
        """
        if self._open_reason == "429_storm":
            return self._429_open_seconds
        return self.reset_timeout  # 300 s for 5xx

    @property
    def state(self) -> CircuitState:
        """Current state, auto-transitioning OPEN → HALF_OPEN on timeout."""
        if self._state == CircuitState.OPEN and time.time() - self._opened_at >= self.open_seconds:
            self._state = CircuitState.HALF_OPEN
            self._half_open_in_flight = False
        return self._state

    @property
    def is_open(self) -> bool:
        """True if circuit is OPEN (all requests rejected)."""
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit breaker."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            if not self._half_open_in_flight:
                self._half_open_in_flight = True
                return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful request — resets circuit to CLOSED."""
        self._failure_count = 0
        self._429_count = 0
        self._open_reason = "none"
        self._state = CircuitState.CLOSED
        self._half_open_in_flight = False

    def record_failure(self, error_type: ErrorType) -> None:
        """Record a failed request.

        - RATE_LIMITED (429): independent counter, trips at 5 with 45 s open window.
        - UPSTREAM_5XX: original counter, trips at 5 with 300 s open window.
        - All other error types are ignored by the circuit breaker.
        """
        if error_type == ErrorType.RATE_LIMITED:
            self._429_count += 1
            if self._429_count >= self._429_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._open_reason = "429_storm"
                self._half_open_in_flight = False
            return

        if error_type != ErrorType.UPSTREAM_5XX:
            return

        # In HALF_OPEN, any 5xx failure immediately reopens the circuit
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            self._open_reason = "5xx_storm"
            self._half_open_in_flight = False
            return

        self._failure_count += 1
        if self._failure_count >= self.threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            self._open_reason = "5xx_storm"
            self._half_open_in_flight = False

    def status_report(self) -> str:
        """Human-readable circuit breaker status."""
        current = self.state
        if current == CircuitState.OPEN:
            remaining = max(0, self.open_seconds - (time.time() - self._opened_at))
            reason = f", reason={self._open_reason}" if self._open_reason != "none" else ""
            return f"OPEN ({remaining:.0f}s remaining{reason})"
        if current == CircuitState.HALF_OPEN:
            return "HALF_OPEN (probing)"
        return "CLOSED"


class APIKeysExhaustedError(LLMKeysExhaustedError, RuntimeError):
    """Raised when all API keys in a pool are exhausted or invalid.

    Inherits from ``LLMKeysExhaustedError`` (domain) so domain services can
    catch it without importing from infrastructure. Also inherits from
    ``RuntimeError`` for backward compatibility with existing ``except
    RuntimeError`` handlers.
    """


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
        redis_client: Redis | None = None,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        cooldown_overrides: dict[ErrorType, int] | None = None,
    ):
        """
        Initialize API key pool.

        Args:
            provider: Provider name (e.g., "openai", "serper", "tavily")
            keys: List of API key configurations
            strategy: Rotation strategy to use
            redis_client: Redis client for health tracking (None = in-memory mode)
            base_backoff_seconds: Base delay for exponential backoff (default: 1s)
            max_backoff_seconds: Maximum backoff delay (default: 60s)
            cooldown_overrides: Per-provider cooldown overrides by error type.
                Merges with defaults — only specified types are overridden.
                Example: ``{ErrorType.QUOTA_EXHAUSTED: 14400}`` for 4h instead of 24h.

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

        # Per-provider cooldown overrides (merge with defaults)
        self._cooldowns = dict(_ERROR_COOLDOWNS)
        if cooldown_overrides:
            self._cooldowns.update(cooldown_overrides)

        # Round-robin state (lock protects index read+increment atomicity)
        self._round_robin_index = 0
        self._round_robin_lock = asyncio.Lock()

        # In-memory fallback state (used when Redis unavailable or fails)
        self._memory_exhausted: dict[str, float] = {}  # key_hash -> expiry_timestamp
        self._memory_invalid: set[str] = set()  # set of invalid key_hashes

        # Per-key consecutive rate limit counters for exponential backoff
        self._consecutive_rate_limits: dict[str, int] = {}  # key_hash -> count

        # Adaptive TTL learning: tracks when keys were marked exhausted
        # and adjusts future TTLs based on actual recovery times
        self._exhaustion_timestamps: dict[str, float] = {}  # key_hash -> when marked exhausted
        self._adaptive_ttl_multiplier: float = 1.0  # shrinks on early recovery (floor: 0.25)

        # Circuit breaker for upstream outage protection
        self.circuit_breaker = CircuitBreaker()

        # Cooldown: suppress repeated "all keys exhausted" warnings
        self._last_exhaustion_warning: float = 0.0
        self._exhaustion_warning_cooldown: float = 60.0  # seconds

        # Background health probe task (opt-in via start_health_probe)
        self._health_probe_task: asyncio.Task | None = None

        # Warn if running without Redis
        if redis_client is None:
            logger.warning(
                f"[{provider}] APIKeyPool running in-memory mode (no Redis). Multi-instance coordination disabled."
            )

    def _log_all_keys_exhausted(self) -> None:
        """Log key exhaustion with cooldown to prevent log spam.

        Logs at WARNING level once per cooldown period, then DEBUG for
        subsequent calls within the cooldown window. Includes the soonest
        recovery time for actionable debugging.
        """
        now = time.time()
        if now - self._last_exhaustion_warning >= self._exhaustion_warning_cooldown:
            _, remaining = self._get_soonest_recovery()
            recovery_hint = (
                f", soonest recovery in {remaining:.0f}s (~{remaining / 60:.1f}min)" if remaining > 0 else ""
            )
            logger.warning(f"[{self.provider}] All {len(self.keys)} keys exhausted{recovery_hint}")
            self._last_exhaustion_warning = now
        else:
            logger.debug(f"[{self.provider}] All {len(self.keys)} keys exhausted (suppressed)")

        api_key_selections_total.inc({"provider": self.provider, "key_id": "all", "status": "exhausted"})

    async def get_healthy_key(self) -> str | None:
        """
        Get next healthy API key using configured strategy.

        Checks circuit breaker first — if OPEN, rejects immediately.

        Returns:
            API key string, or None if no healthy keys are available
        """
        if not self.circuit_breaker.allow_request():
            logger.warning(
                f"[{self.provider}] Circuit breaker {self.circuit_breaker.status_report()}, rejecting request"
            )
            return None

        if self.strategy == RotationStrategy.ROUND_ROBIN:
            return await self._round_robin()
        if self.strategy == RotationStrategy.FAILOVER:
            return await self._failover()
        if self.strategy == RotationStrategy.WEIGHTED:
            return await self._weighted_selection()
        raise ValueError(f"Unsupported strategy: {self.strategy}")

    def _get_soonest_recovery(self) -> tuple[str | None, float]:
        """Find the non-invalid key with the shortest remaining cooldown.

        Scans in-memory exhaustion state only (Redis sync happens lazily via
        _is_healthy). Sufficient for the wait decision since _is_healthy keeps
        _memory_exhausted in sync with Redis TTLs on each get_healthy_key() call.

        Returns:
            Tuple of (key_string, remaining_seconds). Returns (key, 0) if a key
            is immediately available. Returns (None, 0) if all keys are permanently
            invalid and cannot recover.
        """
        now = time.time()
        best_key: str | None = None
        best_remaining = float("inf")

        for key_config in self.keys:
            key_hash = self._hash_key(key_config.key)

            # Skip permanently invalid keys (cannot recover)
            if key_hash in self._memory_invalid:
                continue

            if key_hash in self._memory_exhausted:
                remaining = self._memory_exhausted[key_hash] - now
                if remaining <= 0:
                    # TTL already expired in memory — key is healthy again
                    return key_config.key, 0.0
                if remaining < best_remaining:
                    best_remaining = remaining
                    best_key = key_config.key
            else:
                # Key is not exhausted — immediately available
                return key_config.key, 0.0

        return best_key, best_remaining if best_key is not None else 0.0

    async def get_healthy_key_or_wait(self, max_wait_seconds: float = 120.0) -> str | None:
        """Get a healthy key, waiting for the soonest-recovering key if all are exhausted.

        Implements the MCP API Rotators wait pattern: instead of returning None
        immediately when all keys are in cooldown, waits up to max_wait_seconds
        for the soonest-recovering key.

        Useful for rate-limited (60-120s) and short cooldown (15-30s) scenarios.
        For long quota cooldowns (4h+), the wait budget is exceeded and the caller
        falls back to the next search provider via FallbackSearchEngine.

        Args:
            max_wait_seconds: Maximum seconds to wait for key recovery (default 120s).

        Returns:
            API key string, or None if soonest recovery exceeds max_wait_seconds
            or all keys are permanently invalid.
        """
        # Fast path: return immediately if a key is already healthy
        key = await self.get_healthy_key()
        if key is not None:
            return key

        # All keys in cooldown — find the soonest-recovering non-invalid key
        soonest_key, remaining = self._get_soonest_recovery()

        if soonest_key is None:
            logger.error(f"[{self.provider}] All {len(self.keys)} keys are permanently invalid — cannot recover")
            return None

        if remaining <= 0:
            # A key recovered since get_healthy_key() ran (race cleared by _is_healthy)
            return await self.get_healthy_key()

        if remaining > max_wait_seconds:
            logger.warning(
                f"[{self.provider}] All keys exhausted; soonest recovery in {remaining:.0f}s "
                f"(> max_wait={max_wait_seconds:.0f}s) — not waiting, using fallback"
            )
            return None

        logger.info(
            f"[{self.provider}] All keys exhausted; waiting {remaining:.1f}s for soonest key to recover "
            f"(budget: {max_wait_seconds:.0f}s)"
        )
        # +1s buffer ensures the TTL has fully elapsed before re-check
        await asyncio.sleep(remaining + 1.0)

        # Final selection after wait
        return await self.get_healthy_key()

    async def _round_robin(self) -> str | None:
        """
        Round-robin rotation with health checks.

        Cycles through keys evenly, skipping exhausted/invalid keys.
        Uses asyncio.Lock to ensure atomic index read+increment under
        concurrent access (prevents key skipping and duplicate selection).

        Returns:
            API key string, or None if no healthy keys are available
        """
        attempts = 0
        max_attempts = len(self.keys) * 2  # Allow 2 full rotations

        while attempts < max_attempts:
            # Atomic read+increment: lock ensures no two coroutines
            # read the same index before either increments it
            async with self._round_robin_lock:
                key_config = self.keys[self._round_robin_index]
                self._round_robin_index = (self._round_robin_index + 1) % len(self.keys)
            attempts += 1

            # Health check is outside the lock: it involves async I/O
            # (Redis calls) and should not hold the lock during network ops
            if await self._is_healthy(key_config.key):
                # Record successful selection
                key_hash = self._hash_key(key_config.key)
                api_key_selections_total.inc({"provider": self.provider, "key_id": key_hash, "status": "success"})

                # Update health score
                api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 1.0)

                return key_config.key

        # All keys unhealthy
        self._log_all_keys_exhausted()
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
        self._log_all_keys_exhausted()
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

        Uses in-memory fallback when Redis unavailable or fails.

        Args:
            key: API key to check

        Returns:
            True if key is healthy, False otherwise
        """
        key_hash = self._hash_key(key)

        # Check in-memory state first (always available)
        # Remove expired exhausted keys
        now = time.time()
        if key_hash in self._memory_exhausted:
            if self._memory_exhausted[key_hash] <= now:
                # TTL expired, key is healthy again
                del self._memory_exhausted[key_hash]
            else:
                # Still exhausted
                return False

        # Check invalid keys (permanent)
        if key_hash in self._memory_invalid:
            return False

        # If Redis available, also check Redis state
        if self._redis is not None:
            try:
                # Check if key is invalid (permanent)
                invalid_key = f"api_key:invalid:{self.provider}:{key_hash}"
                invalid_result = await self._redis.call("exists", invalid_key)
                # Only trust result if it's actually a boolean or int (0/1)
                if isinstance(invalid_result, (bool, int)) and invalid_result:
                    # Sync to in-memory state
                    self._memory_invalid.add(key_hash)
                    return False

                # Check if key is exhausted (temporary with TTL)
                # Use TTL instead of EXISTS to get actual remaining seconds
                # TTL returns: >0 = seconds remaining, -2 = key doesn't exist, -1 = no expiry
                exhausted_key = f"api_key:exhausted:{self.provider}:{key_hash}"
                ttl_result = await self._redis.call("ttl", exhausted_key)
                if isinstance(ttl_result, int) and ttl_result > 0:
                    # Sync actual Redis TTL to in-memory state
                    self._memory_exhausted[key_hash] = now + ttl_result
                    return False
            except Exception as e:
                logger.warning(f"[{self.provider}] Redis check failed, using in-memory state: {e}")

        return True

    async def mark_exhausted(self, key: str, ttl_seconds: int, *, apply_adaptive: bool = True) -> None:
        """
        Mark API key as exhausted with TTL.

        After TTL expires, key becomes healthy again.

        Uses in-memory state as fallback when Redis unavailable.
        Deduplicates: if the key is already marked exhausted, skips the
        update to prevent log spam from concurrent callers hitting 429.

        Args:
            key: API key to mark as exhausted
            ttl_seconds: Time-to-live in seconds (e.g., 3600 for 1 hour)
            apply_adaptive: Whether to apply the adaptive TTL multiplier (default True).
                Set to False for rate-limit backoff where the cooldown is already calculated.
        """
        key_hash = self._hash_key(key)

        # Skip if already marked exhausted (prevents log spam from concurrent callers)
        if key_hash in self._memory_exhausted and self._memory_exhausted[key_hash] > time.time():
            return

        # Apply adaptive TTL multiplier for quota exhaustion cooldowns
        if apply_adaptive and self._adaptive_ttl_multiplier < 1.0:
            original = ttl_seconds
            ttl_seconds = max(60, int(ttl_seconds * self._adaptive_ttl_multiplier))
            logger.info(
                f"[{self.provider}] Adaptive TTL: {original}s → {ttl_seconds}s "
                f"(multiplier={self._adaptive_ttl_multiplier:.2f})"
            )

        # Record exhaustion timestamp for adaptive learning
        self._exhaustion_timestamps[key_hash] = time.time()

        expiry_time = time.time() + ttl_seconds

        # Always update in-memory state
        self._memory_exhausted[key_hash] = expiry_time

        # Try to update Redis if available
        if self._redis is not None:
            try:
                redis_key = f"api_key:exhausted:{self.provider}:{key_hash}"
                await self._redis.call("setex", redis_key, ttl_seconds, KeyHealthStatus.EXHAUSTED.value)
            except Exception as e:
                logger.warning(f"[{self.provider}] Failed to mark key exhausted in Redis, using in-memory only: {e}")

        # Record exhaustion metric
        api_key_exhaustions_total.inc({"provider": self.provider, "reason": "quota"})

        # Update health score
        api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 0.0)

        logger.warning(f"[{self.provider}] Key {key_hash} marked EXHAUSTED, auto-recovery in {ttl_seconds}s")

    async def mark_invalid(self, key: str) -> None:
        """
        Mark API key as invalid permanently.

        Invalid keys are never retried (e.g., revoked keys, wrong keys).

        Uses in-memory state as fallback when Redis unavailable.

        Args:
            key: API key to mark as invalid
        """
        key_hash = self._hash_key(key)

        # Always update in-memory state
        self._memory_invalid.add(key_hash)
        # Remove from exhausted if present (invalid takes precedence)
        self._memory_exhausted.pop(key_hash, None)

        # Try to update Redis if available
        if self._redis is not None:
            try:
                redis_key = f"api_key:invalid:{self.provider}:{key_hash}"
                await self._redis.call("set", redis_key, KeyHealthStatus.INVALID.value)
            except Exception as e:
                logger.warning(f"[{self.provider}] Failed to mark key invalid in Redis, using in-memory only: {e}")

        # Record invalidation metric
        api_key_exhaustions_total.inc({"provider": self.provider, "reason": "invalid"})

        # Update health score
        api_key_health_score.set({"provider": self.provider, "key_id": key_hash}, 0.0)

        logger.error(f"[{self.provider}] Key {key_hash} marked INVALID. Manual intervention required.")

    async def handle_error(
        self,
        key: str,
        status_code: int | None = None,
        body_text: str = "",
        is_network_error: bool = False,
        response_headers: dict[str, str] | None = None,
    ) -> ErrorType:
        """Classify an error, apply the appropriate cooldown, and update circuit breaker.

        This is the primary entry point for consumers to report errors.
        Replaces manual ``mark_exhausted`` / ``mark_invalid`` calls with
        automatic error-type-aware handling.

        Args:
            key: The API key that experienced the error
            status_code: HTTP status code (None for connection-level errors)
            body_text: Response body or error message text
            is_network_error: True if the error is a connection/timeout failure
            response_headers: Optional HTTP response headers to check for Retry-After

        Returns:
            The classified ErrorType
        """
        error_type, _default_cooldown = classify_error(status_code, body_text, is_network_error)
        # Use per-provider cooldown override (falls back to module default)
        cooldown = self._cooldowns[error_type]

        # Update circuit breaker (only 5xx errors count)
        self.circuit_breaker.record_failure(error_type)

        key_hash = self._hash_key(key)

        if error_type == ErrorType.CLIENT_ERROR:
            # No cooldown — bad request from caller, not the key's fault
            logger.debug(f"[{self.provider}] Key {key_hash} client error (HTTP {status_code}), no cooldown")
            return error_type

        if error_type == ErrorType.AUTH_ERROR:
            # Permanent invalidation for auth errors
            await self.mark_invalid(key)
            return error_type

        if error_type == ErrorType.RATE_LIMITED:
            # Header-aware backoff: honor Retry-After before exponential fallback
            rate_cooldown = self._get_rate_limit_cooldown(key, response_headers=response_headers)
            await self.mark_exhausted(key, ttl_seconds=rate_cooldown, apply_adaptive=False)
            return error_type

        if error_type == ErrorType.QUOTA_EXHAUSTED:
            # Long cooldown for quota exhaustion (adaptive TTL applies)
            await self.mark_exhausted(key, ttl_seconds=cooldown)
            return error_type

        # UPSTREAM_5XX, NETWORK_ERROR, OTHER — short cooldowns
        await self.mark_exhausted(key, ttl_seconds=cooldown)
        return error_type

    def record_success(self, key: str) -> None:
        """Record a successful request for a key.

        Resets the consecutive rate limit counter, updates circuit breaker,
        and checks for early recovery to adapt future TTLs.

        Args:
            key: The API key that succeeded
        """
        key_hash = self._hash_key(key)
        # Reset consecutive rate limit counter on success
        self._consecutive_rate_limits.pop(key_hash, None)
        # Update circuit breaker
        self.circuit_breaker.record_success()

        # Adaptive TTL learning: detect early recovery
        if key_hash in self._exhaustion_timestamps:
            exhausted_at = self._exhaustion_timestamps.pop(key_hash)
            actual_recovery = time.time() - exhausted_at

            # Check if key was in exhausted state (now cleared by _is_healthy TTL expiry)
            # If recovery happened in <75% of the configured TTL, shrink the multiplier
            configured_ttl = self._cooldowns.get(ErrorType.QUOTA_EXHAUSTED, 86400)
            threshold = configured_ttl * 0.75 * self._adaptive_ttl_multiplier

            if actual_recovery < threshold:
                old_multiplier = self._adaptive_ttl_multiplier
                self._adaptive_ttl_multiplier = max(0.25, self._adaptive_ttl_multiplier * 0.7)
                logger.info(
                    f"[{self.provider}] Key {key_hash} recovered early "
                    f"({actual_recovery:.0f}s < {threshold:.0f}s threshold). "
                    f"Adaptive multiplier: {old_multiplier:.2f} → {self._adaptive_ttl_multiplier:.2f}"
                )
                api_key_early_recoveries_total.inc({"provider": self.provider})

            # Clear from memory exhausted if still present
            self._memory_exhausted.pop(key_hash, None)

    def _parse_retry_after_header(self, headers: dict[str, str]) -> int | None:
        """Parse Retry-After, X-RateLimit-Reset, or RateLimit-Reset headers into seconds.

        Priority order (RFC 6585 + common provider conventions):
        1. Retry-After: <seconds>        (integer — Tavily, Serper)
        2. Retry-After: <HTTP-date>      (RFC 7231 date string)
        3. X-RateLimit-Reset: <unix>     (Brave, Exa)
        4. RateLimit-Reset: <unix>       (IETF draft)

        Returns None if no recognized header is present or parsing fails.
        """
        h = {k.lower(): v for k, v in headers.items()}

        if "retry-after" in h:
            val = h["retry-after"].strip()
            if val.isdigit():
                return max(0, int(val))
            try:
                reset_ts = email.utils.parsedate_to_datetime(val).timestamp()
                return max(0, int(reset_ts - time.time()))
            except Exception:  # noqa: S110  # invalid date string — silently fall through
                pass

        for hdr in ("x-ratelimit-reset", "ratelimit-reset"):
            if hdr in h:
                try:
                    return max(0, int(float(h[hdr])) - int(time.time()))
                except ValueError:
                    pass
        return None

    def _get_rate_limit_cooldown(self, key: str, response_headers: dict[str, str] | None = None) -> int:
        """Calculate cooldown for rate-limited keys.

        Checks response headers first (Retry-After, X-RateLimit-Reset) before
        falling back to exponential backoff. Honoring provider-declared cooldown
        is required by RFC 6585 and prevents escalating blocks.

        Formula (fallback): min(base * 2^consecutive_hits, 600) + jitter

        Args:
            key: The rate-limited API key
            response_headers: Optional HTTP response headers to check for Retry-After

        Returns:
            Cooldown in seconds
        """
        key_hash = self._hash_key(key)

        # Honor provider-declared cooldown first (RFC 6585)
        if response_headers:
            header_cooldown = self._parse_retry_after_header(response_headers)
            if header_cooldown is not None:
                logger.debug(f"[{self.provider}] Key {key_hash} using header-declared cooldown {header_cooldown}s")
                return header_cooldown

        # Increment consecutive counter for exponential backoff
        count = self._consecutive_rate_limits.get(key_hash, 0)
        self._consecutive_rate_limits[key_hash] = count + 1

        # Exponential backoff: 60s * 2^count, capped at 600s (10 min)
        base_cooldown = _ERROR_COOLDOWNS[ErrorType.RATE_LIMITED]
        cooldown = base_cooldown * (2.0**count)
        cooldown = min(cooldown, 600)

        # Add jitter to prevent thundering herd
        jitter = random.uniform(0, min(15 * (count + 1), 60))  # noqa: S311
        total = int(cooldown + jitter)

        logger.info(
            f"[{self.provider}] Key {key_hash} rate-limited (hit #{count + 1}), "
            f"cooldown={total}s (base={cooldown:.0f}s + jitter={jitter:.0f}s)"
        )
        return total

    def get_backoff_delay(self, key: str, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter using centralized retry logic.

        Formula: min(base * 2^attempt, max) ± 25% jitter

        Args:
            key: API key (for potential future per-key backoff)
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Use centralized exponential backoff calculation
        retry_config = RetryConfig(
            base_delay=self.base_backoff_seconds,
            exponential_base=2.0,
            max_delay=self.max_backoff_seconds,
            jitter=True,
            jitter_factor=0.25,  # ±25% jitter
        )
        return calculate_delay(attempt + 1, retry_config)  # Convert 0-indexed to 1-indexed

    def status_report(self) -> str:
        """Human-readable status report of all keys and circuit breaker.

        Returns:
            Multi-line status string
        """
        lines = [f"{self.provider} API Key Pool Status:", ""]
        now = time.time()

        available_count = 0
        cooldown_count = 0
        exhausted_count = 0
        invalid_count = 0

        for i, key_config in enumerate(self.keys):
            key_hash = self._hash_key(key_config.key)
            rate_hits = self._consecutive_rate_limits.get(key_hash, 0)

            if key_hash in self._memory_invalid:
                status = "INVALID"
                invalid_count += 1
            elif key_hash in self._memory_exhausted:
                remaining = self._memory_exhausted[key_hash] - now
                if remaining > 0:
                    status = f"COOLDOWN ({remaining:.0f}s remaining)"
                    cooldown_count += 1
                else:
                    status = "AVAILABLE"
                    available_count += 1
            else:
                status = "AVAILABLE"
                available_count += 1

            lines.append(f"  key-{i} ({key_hash}): {status}")
            if rate_hits > 0:
                lines.append(f"    Consecutive rate limits: {rate_hits}")

        lines.append("")
        lines.append(f"  Total keys: {len(self.keys)}")
        lines.append(f"  Available: {available_count}")
        lines.append(f"  In cooldown: {cooldown_count}")
        lines.append(f"  Quota exhausted: {exhausted_count}")
        lines.append(f"  Invalid: {invalid_count}")
        lines.append(f"  Circuit Breaker: {self.circuit_breaker.status_report()}")
        return "\n".join(lines)

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

    # ------------------------------------------------------------------
    # Background health probe (opt-in)
    # ------------------------------------------------------------------

    def start_health_probe(self, interval_seconds: float = 300.0) -> None:
        """Start a background task that periodically cleans stale in-memory state.

        The probe:
        - Removes expired entries from ``_memory_exhausted``
        - Checks Redis TTL for entries that Redis has already expired

        Opt-in: call this after construction. No consumer changes required
        for MVP — keys are naturally re-tested when ``get_healthy_key()`` runs.
        The probe ensures stale in-memory entries don't block keys after
        Redis TTL expires between ``get_healthy_key()`` calls.
        """
        if self._health_probe_task is not None:
            logger.warning(f"[{self.provider}] Health probe already running")
            return
        self._health_probe_task = asyncio.create_task(
            self._health_probe_loop(interval_seconds),
            name=f"key-pool-health-probe-{self.provider}",
        )
        logger.info(f"[{self.provider}] Health probe started (interval={interval_seconds}s)")

    def stop_health_probe(self) -> None:
        """Cancel the background health probe gracefully."""
        if self._health_probe_task is not None:
            self._health_probe_task.cancel()
            self._health_probe_task = None
            logger.info(f"[{self.provider}] Health probe stopped")

    async def _health_probe_loop(self, interval: float) -> None:
        """Background loop: clean expired in-memory entries and sync with Redis."""
        try:
            while True:
                await asyncio.sleep(interval)
                now = time.time()

                # 1. Remove expired in-memory entries
                expired = [kh for kh, exp in self._memory_exhausted.items() if exp <= now]
                for kh in expired:
                    del self._memory_exhausted[kh]
                    self._exhaustion_timestamps.pop(kh, None)

                # 2. If Redis available, check TTL for remaining entries
                if self._redis is not None:
                    for kh in list(self._memory_exhausted):
                        with contextlib.suppress(Exception):
                            redis_key = f"api_key:exhausted:{self.provider}:{kh}"
                            ttl = await self._redis.call("ttl", redis_key)
                            if isinstance(ttl, int) and ttl == -2:
                                # Key doesn't exist in Redis — clear in-memory
                                del self._memory_exhausted[kh]
                                self._exhaustion_timestamps.pop(kh, None)

                if expired:
                    logger.debug(f"[{self.provider}] Health probe cleared {len(expired)} expired entries")
        except asyncio.CancelledError:
            pass
