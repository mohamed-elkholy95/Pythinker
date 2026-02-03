"""Adaptive circuit breaker with failure tracking and recovery monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.failure_tracker import FailureTracker
from app.core.recovery_monitor import RecoveryMonitor
from app.infrastructure.observability.prometheus_metrics import (
    record_circuit_breaker_failure_rate,
    record_circuit_breaker_mttr,
    record_circuit_breaker_recovery,
    record_circuit_breaker_threshold,
)

from .circuit_breaker_registry import CircuitBreaker, CircuitBreakerConfig, CircuitState

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveConfig:
    """Adaptive threshold settings."""

    min_failure_threshold: int = 2
    max_failure_threshold: int = 10
    adjust_step: int = 1
    high_failure_rate: float = 0.7
    low_failure_rate: float = 0.1


class AdaptiveCircuitBreaker(CircuitBreaker):
    """Circuit breaker that adapts thresholds based on recent failures."""

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
        adaptive_config: AdaptiveConfig | None = None,
        failure_tracker: FailureTracker | None = None,
        recovery_monitor: RecoveryMonitor | None = None,
    ) -> None:
        super().__init__(name, config)
        self._adaptive_config = adaptive_config or AdaptiveConfig()
        self._failure_tracker = failure_tracker or FailureTracker()
        self._recovery_monitor = recovery_monitor or RecoveryMonitor()

    def record_success(self) -> None:
        super().record_success()
        self._failure_tracker.record_success(self.name)

        stats = self._failure_tracker.get_stats(self.name)
        record_circuit_breaker_failure_rate(self.name, stats.failure_rate)

        # Adapt threshold upward on sustained stability
        if stats.failure_rate <= self._adaptive_config.low_failure_rate:
            self._adjust_threshold(increase=True)

    def record_failure(self) -> None:
        super().record_failure()
        self._failure_tracker.record_failure(self.name, "failure")

        stats = self._failure_tracker.get_stats(self.name)
        record_circuit_breaker_failure_rate(self.name, stats.failure_rate)

        # Adapt threshold downward on high failure rate
        if stats.failure_rate >= self._adaptive_config.high_failure_rate:
            self._adjust_threshold(increase=False)

    def _transition_to(self, new_state: CircuitState) -> None:
        super()._transition_to(new_state)

        if new_state == CircuitState.OPEN:
            self._recovery_monitor.record_open(self.name)
            record_circuit_breaker_recovery(self.name, "attempt")
        if new_state == CircuitState.CLOSED:
            stats = self._recovery_monitor.record_recovery(self.name, success=True)
            record_circuit_breaker_recovery(self.name, "success")
            if stats.last_recovery_seconds is not None:
                record_circuit_breaker_mttr(self.name, stats.last_recovery_seconds)

    def _adjust_threshold(self, increase: bool) -> None:
        current = self.config.failure_threshold
        if increase:
            updated = min(current + self._adaptive_config.adjust_step, self._adaptive_config.max_failure_threshold)
        else:
            updated = max(current - self._adaptive_config.adjust_step, self._adaptive_config.min_failure_threshold)

        if updated != current:
            self.config.failure_threshold = updated
            record_circuit_breaker_threshold(self.name, updated)
            logger.info(
                "Adaptive circuit breaker threshold updated",
                extra={"circuit_breaker": self.name, "failure_threshold": updated},
            )
