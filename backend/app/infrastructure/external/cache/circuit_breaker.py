"""Circuit Breaker for Semantic Cache SLO Monitoring.

Implements circuit breaker pattern to automatically bypass semantic cache
when hit rate drops below acceptable thresholds, preventing cascading failures
and ensuring system reliability.

States:
- CLOSED: Normal operation, cache enabled (hit rate >= 40%)
- OPEN: Cache bypassed due to low hit rate (hit rate < 40% for 5 minutes)
- HALF_OPEN: Testing recovery, allowing limited traffic (after 3 minutes)

SLO Thresholds:
- Failure threshold: Hit rate < 40% for 5 consecutive minutes
- Recovery threshold: Hit rate > 60% for 3 consecutive minutes
- Half-open test period: 30 seconds
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Cache bypassed
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: float = 0.40
    """Hit rate threshold for opening circuit (40%)."""

    recovery_threshold: float = 0.60
    """Hit rate threshold for closing circuit (60%)."""

    failure_window_seconds: int = 300
    """Time window for detecting failures (5 minutes)."""

    recovery_window_seconds: int = 180
    """Time window for detecting recovery (3 minutes)."""

    half_open_test_seconds: int = 30
    """Duration of half-open state testing (30 seconds)."""

    min_samples: int = 10
    """Minimum samples required for hit rate calculation."""


@dataclass
class HitRateSample:
    """A sample of cache hit rate at a specific time."""

    timestamp: float
    hits: int
    misses: int

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total > 0 else 0.0


class SemanticCacheCircuitBreaker:
    """Circuit breaker for semantic cache SLO enforcement.

    Monitors cache hit rate and automatically bypasses cache when
    performance degrades below acceptable thresholds.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        """Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._samples: deque[HitRateSample] = deque(maxlen=1000)
        self._state_changed_at = time.time()
        self._half_open_started_at: float | None = None
        self._consecutive_failures = 0
        self._consecutive_successes = 0

        logger.info(
            f"Circuit breaker initialized: "
            f"failure_threshold={self._config.failure_threshold}, "
            f"recovery_threshold={self._config.recovery_threshold}"
        )

    def record_request(self, hit: bool) -> None:
        """Record a cache request result.

        Args:
            hit: True if cache hit, False if cache miss
        """
        now = time.time()

        # Add or update current sample (aggregate by second)
        if self._samples and (now - self._samples[-1].timestamp) < 1.0:
            # Update current sample
            sample = self._samples[-1]
            if hit:
                self._samples[-1] = HitRateSample(
                    timestamp=sample.timestamp,
                    hits=sample.hits + 1,
                    misses=sample.misses,
                )
            else:
                self._samples[-1] = HitRateSample(
                    timestamp=sample.timestamp,
                    hits=sample.hits,
                    misses=sample.misses + 1,
                )
        else:
            # Create new sample
            self._samples.append(
                HitRateSample(
                    timestamp=now,
                    hits=1 if hit else 0,
                    misses=0 if hit else 1,
                )
            )

        # Check state transitions
        self._update_state()

    def _update_state(self) -> None:
        """Update circuit breaker state based on recent hit rates."""
        now = time.time()

        if self._state == CircuitState.CLOSED:
            # Check for failure condition
            hit_rate = self._get_hit_rate_in_window(self._config.failure_window_seconds)
            if hit_rate is not None and hit_rate < self._config.failure_threshold:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:  # 3 consecutive low samples
                    self._open_circuit()
            else:
                self._consecutive_failures = 0

        elif self._state == CircuitState.OPEN:
            # Check if enough time has passed to try half-open
            time_since_open = now - self._state_changed_at
            if time_since_open >= self._config.failure_window_seconds:
                self._half_open_circuit()

        elif self._state == CircuitState.HALF_OPEN:
            # Check for recovery or re-failure
            if self._half_open_started_at is None:
                self._half_open_started_at = now

            test_duration = now - self._half_open_started_at

            if test_duration >= self._config.half_open_test_seconds:
                # Test period complete, evaluate recovery
                hit_rate = self._get_hit_rate_in_window(self._config.recovery_window_seconds)

                if hit_rate is not None and hit_rate >= self._config.recovery_threshold:
                    self._consecutive_successes += 1
                    if self._consecutive_successes >= 2:  # 2 consecutive good samples
                        self._close_circuit()
                else:
                    # Still not recovered, go back to OPEN
                    self._open_circuit()

    def _get_hit_rate_in_window(self, window_seconds: int) -> float | None:
        """Calculate hit rate in a time window.

        Args:
            window_seconds: Time window in seconds

        Returns:
            Hit rate (0-1) or None if insufficient samples
        """
        now = time.time()
        cutoff = now - window_seconds

        # Filter samples within window
        recent_samples = [s for s in self._samples if s.timestamp >= cutoff]

        if len(recent_samples) < self._config.min_samples:
            return None

        total_hits = sum(s.hits for s in recent_samples)
        total_requests = sum(s.total for s in recent_samples)

        if total_requests == 0:
            return None

        return total_hits / total_requests

    def _open_circuit(self) -> None:
        """Open the circuit (bypass cache)."""
        if self._state != CircuitState.OPEN:
            logger.warning(
                f"Circuit breaker OPEN: Cache hit rate below {self._config.failure_threshold:.0%}. "
                "Bypassing semantic cache."
            )
            self._state = CircuitState.OPEN
            self._state_changed_at = time.time()
            self._consecutive_failures = 0
            self._half_open_started_at = None

    def _half_open_circuit(self) -> None:
        """Transition to half-open state (testing recovery)."""
        if self._state != CircuitState.HALF_OPEN:
            logger.info("Circuit breaker HALF_OPEN: Testing cache recovery")
            self._state = CircuitState.HALF_OPEN
            self._state_changed_at = time.time()
            self._half_open_started_at = time.time()
            self._consecutive_successes = 0

    def _close_circuit(self) -> None:
        """Close the circuit (normal operation)."""
        if self._state != CircuitState.CLOSED:
            logger.info(
                f"Circuit breaker CLOSED: Cache hit rate recovered above {self._config.recovery_threshold:.0%}"
            )
            self._state = CircuitState.CLOSED
            self._state_changed_at = time.time()
            self._consecutive_successes = 0
            self._half_open_started_at = None

    def is_cache_allowed(self) -> bool:
        """Check if cache operations are allowed.

        Returns:
            True if cache should be used, False if bypassed
        """
        return self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def state_numeric(self) -> int:
        """Get numeric state for Prometheus (0=CLOSED, 1=OPEN, 2=HALF_OPEN)."""
        return {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }[self._state]

    def get_metrics(self) -> dict:
        """Get circuit breaker metrics for monitoring."""
        current_hit_rate = self._get_hit_rate_in_window(60)  # Last minute

        return {
            "state": self._state.value,
            "state_numeric": self.state_numeric,
            "current_hit_rate": current_hit_rate,
            "failure_threshold": self._config.failure_threshold,
            "recovery_threshold": self._config.recovery_threshold,
            "time_in_state_seconds": time.time() - self._state_changed_at,
            "total_samples": len(self._samples),
        }


# Global circuit breaker instance
_circuit_breaker: SemanticCacheCircuitBreaker | None = None


def get_circuit_breaker() -> SemanticCacheCircuitBreaker:
    """Get or create the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = SemanticCacheCircuitBreaker()
    return _circuit_breaker
