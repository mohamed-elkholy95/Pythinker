"""Circuit Breaker Registry for Service Protection.

Provides centralized circuit breaker management across services to prevent
cascade failures and enable graceful degradation.

The registry maintains named circuit breakers that track failure rates and
temporarily disable calls to failing services.

Usage:
    # Get or create a circuit breaker
    cb = CircuitBreakerRegistry.get_or_create("external-api", failure_threshold=5)

    # Check if we can execute
    if cb.can_execute():
        try:
            result = await external_api_call()
            cb.record_success()
        except Exception as e:
            cb.record_failure()
            raise

    # Get status of all breakers
    states = CircuitBreakerRegistry.get_all_states()

    # Use as async context manager
    async with CircuitBreakerRegistry.get_or_create("service").execute():
        await call_service()
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, ClassVar, TypeVar

from app.core.config import get_feature_flags

logger = logging.getLogger(__name__)

# Lazy import for metrics to avoid circular dependency
_metrics_imported = False
_record_circuit_breaker_state = None
_record_circuit_breaker_call = None
_record_circuit_breaker_state_change = None


def _import_metrics() -> None:
    """Lazy import metrics to avoid circular imports."""
    global _metrics_imported, _record_circuit_breaker_state
    global _record_circuit_breaker_call, _record_circuit_breaker_state_change
    if not _metrics_imported:
        try:
            from app.core.prometheus_metrics import (
                record_circuit_breaker_call,
                record_circuit_breaker_state,
                record_circuit_breaker_state_change,
            )

            _record_circuit_breaker_state = record_circuit_breaker_state
            _record_circuit_breaker_call = record_circuit_breaker_call
            _record_circuit_breaker_state_change = record_circuit_breaker_state_change
        except ImportError:
            pass
        _metrics_imported = True


T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, allowing calls
    OPEN = "open"  # Blocking calls due to failures
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5
    """Number of failures before opening the circuit."""

    success_threshold: int = 3
    """Number of successes in half-open to close the circuit."""

    recovery_timeout: int = 60
    """Seconds to wait before testing recovery (half-open)."""

    half_open_max_calls: int = 3
    """Maximum concurrent calls allowed in half-open state."""

    failure_rate_threshold: float = 0.5
    """Failure rate (0-1) above which circuit opens (alternative to count)."""

    sliding_window_size: int = 10
    """Size of sliding window for failure rate calculation."""

    excluded_exceptions: tuple[type[Exception], ...] = ()
    """Exception types that should not count as provider failures."""

    excluded_error_patterns: tuple[str, ...] = ()
    """Case-insensitive substrings that should not count as provider failures."""


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None
    last_state_change: datetime | None = None

    # Sliding window for recent calls
    recent_results: list = field(default_factory=list)

    @property
    def failure_rate(self) -> float:
        """Calculate current failure rate."""
        if not self.recent_results:
            return 0.0
        failures = sum(1 for r in self.recent_results if not r)
        return failures / len(self.recent_results)

    def record_result(self, success: bool, window_size: int) -> None:
        """Record a call result in the sliding window."""
        self.recent_results.append(success)
        if len(self.recent_results) > window_size:
            self.recent_results.pop(0)


class CircuitBreaker:
    """Circuit breaker for protecting external service calls.

    Implements the circuit breaker pattern with three states:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Calls are rejected immediately
    - HALF_OPEN: Limited calls allowed to test recovery
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        """Initialize circuit breaker.

        Args:
            name: Unique name for this circuit breaker
            config: Configuration options (uses defaults if not provided)
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        self._stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return self._stats

    def can_execute(self) -> bool:
        """Check if a call can be executed.

        Returns:
            True if the call should proceed, False if it should be rejected.
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if self._should_attempt_recovery():
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open
            return self._half_open_calls < self.config.half_open_max_calls

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        self._stats.total_calls += 1
        self._stats.successful_calls += 1
        self._stats.last_success_time = datetime.now(UTC)
        self._stats.record_result(True, self.config.sliding_window_size)

        # Phase 6: Record metric
        _import_metrics()
        if _record_circuit_breaker_call:
            _record_circuit_breaker_call(self.name, "success")

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            self._half_open_calls -= 1

            # Check if we've had enough successes to close
            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        else:
            # In closed state, reset failure count on success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.last_failure_time = datetime.now(UTC)
        self._last_failure_time = datetime.now(UTC)
        self._stats.record_result(False, self.config.sliding_window_size)

        # Phase 6: Record metric
        _import_metrics()
        if _record_circuit_breaker_call:
            _record_circuit_breaker_call(self.name, "failure")

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self._half_open_calls -= 1
            self._transition_to(CircuitState.OPEN)
        else:
            self._failure_count += 1

            # Check if we should open the circuit
            should_open = (
                self._failure_count >= self.config.failure_threshold
                or self._stats.failure_rate >= self.config.failure_rate_threshold
            )

            if should_open:
                self._transition_to(CircuitState.OPEN)

    def reject_call(self) -> None:
        """Record a rejected call (circuit open)."""
        self._stats.rejected_calls += 1

        # Phase 6: Record metric
        _import_metrics()
        if _record_circuit_breaker_call:
            _record_circuit_breaker_call(self.name, "rejected")

    def _should_attempt_recovery(self) -> bool:
        """Check if we should attempt recovery from open state."""
        if self._last_failure_time is None:
            return True

        elapsed = datetime.now(UTC) - self._last_failure_time
        return elapsed >= timedelta(seconds=self.config.recovery_timeout)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1
        self._stats.last_state_change = datetime.now(UTC)

        # Phase 6: Record metrics
        _import_metrics()
        if _record_circuit_breaker_state:
            _record_circuit_breaker_state(self.name, new_state.value)
        if _record_circuit_breaker_state_change:
            _record_circuit_breaker_state_change(self.name, old_state.value, new_state.value)

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            pass  # Keep failure count for logging

        logger.warning(
            f"Circuit breaker '{self.name}' state change: {old_state.value} -> {new_state.value}",
            extra={
                "circuit_breaker": self.name,
                "old_state": old_state.value,
                "new_state": new_state.value,
                "failure_count": self._failure_count,
            },
        )

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None
        logger.info(f"Circuit breaker '{self.name}' reset to closed")

    @asynccontextmanager
    async def execute(self):
        """Async context manager for executing with circuit breaker protection.

        Usage:
            async with circuit_breaker.execute():
                await some_operation()

        Raises:
            CircuitOpenError: If the circuit is open
        """
        if not self.can_execute():
            self.reject_call()
            raise CircuitOpenError(f"Circuit breaker '{self.name}' is {self._state.value}")

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1

        try:
            yield
            self.record_success()
        except Exception as exc:
            if self._is_excluded_exception(exc):
                raise
            self.record_failure()
            raise

    def _is_excluded_exception(self, exc: Exception) -> bool:
        """Return True when an exception should not trip the breaker."""
        config = self.config
        if config.excluded_exceptions and isinstance(exc, config.excluded_exceptions):
            return True
        if config.excluded_error_patterns:
            text = str(exc).lower()
            for pattern in config.excluded_error_patterns:
                if pattern.lower() in text:
                    return True
        return False

    def get_status(self) -> dict[str, Any]:
        """Get current status as a dictionary."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_rate": round(self._stats.failure_rate, 3),
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "state_changes": self._stats.state_changes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
            },
        }


class CircuitOpenError(Exception):
    """Raised when trying to execute through an open circuit."""

    pass


class CircuitBreakerRegistry:
    """Centralized registry for managing circuit breakers.

    Provides a single point of access for all circuit breakers in the system,
    enabling monitoring and coordinated management.
    """

    _breakers: ClassVar[dict[str, CircuitBreaker]] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    def get_or_create(
        cls,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 3,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one.

        Args:
            name: Unique name for the circuit breaker
            failure_threshold: Failures before opening (if creating new)
            recovery_timeout: Seconds before attempting recovery (if creating new)
            success_threshold: Successes to close from half-open (if creating new)
            config: Full configuration (overrides individual params)

        Returns:
            CircuitBreaker instance
        """
        if name in cls._breakers:
            return cls._breakers[name]

        # Create config from params or use provided
        if config is None:
            config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                success_threshold=success_threshold,
            )

        flags = get_feature_flags()
        if flags.get("circuit_breaker_adaptive"):
            try:
                from app.core.circuit_breaker_adaptive import AdaptiveCircuitBreaker

                breaker = AdaptiveCircuitBreaker(name, config)
            except Exception as e:
                logger.warning(f"Adaptive circuit breaker unavailable, falling back: {e}")
                breaker = CircuitBreaker(name, config)
        else:
            breaker = CircuitBreaker(name, config)
        cls._breakers[name] = breaker

        logger.info(
            f"Created circuit breaker: {name}",
            extra={
                "circuit_breaker": name,
                "failure_threshold": config.failure_threshold,
                "recovery_timeout": config.recovery_timeout,
            },
        )

        return breaker

    @classmethod
    def get(cls, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name.

        Args:
            name: Circuit breaker name

        Returns:
            CircuitBreaker or None if not found
        """
        return cls._breakers.get(name)

    @classmethod
    def get_all_states(cls) -> dict[str, str]:
        """Get the state of all circuit breakers.

        Returns:
            Dict mapping breaker names to their states
        """
        return {name: breaker.state.value for name, breaker in cls._breakers.items()}

    @classmethod
    def get_all_status(cls) -> dict[str, dict[str, Any]]:
        """Get detailed status of all circuit breakers.

        Returns:
            Dict mapping breaker names to their full status
        """
        return {name: breaker.get_status() for name, breaker in cls._breakers.items()}

    @classmethod
    def reset_all(cls) -> None:
        """Reset all circuit breakers to closed state."""
        for breaker in cls._breakers.values():
            breaker.reset()
        logger.info(f"Reset all {len(cls._breakers)} circuit breakers")

    @classmethod
    def reset(cls, name: str) -> bool:
        """Reset a specific circuit breaker.

        Args:
            name: Circuit breaker name

        Returns:
            True if breaker was found and reset, False otherwise
        """
        breaker = cls._breakers.get(name)
        if breaker:
            breaker.reset()
            return True
        return False

    @classmethod
    def remove(cls, name: str) -> bool:
        """Remove a circuit breaker from the registry.

        Args:
            name: Circuit breaker name

        Returns:
            True if breaker was found and removed
        """
        if name in cls._breakers:
            del cls._breakers[name]
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """Clear all circuit breakers from the registry."""
        cls._breakers.clear()


# Convenience function for use without explicit registry access
def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a circuit breaker by name.

    Convenience wrapper for CircuitBreakerRegistry.get_or_create.
    """
    return CircuitBreakerRegistry.get_or_create(name, **kwargs)
