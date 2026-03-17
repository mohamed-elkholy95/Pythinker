from app.core.circuit_breaker_adaptive import AdaptiveCircuitBreaker
from app.core.circuit_breaker_registry import CircuitBreakerConfig


def test_adaptive_threshold_decreases_on_failures():
    config = CircuitBreakerConfig(failure_threshold=5, failure_rate_threshold=1.0, sliding_window_size=5)
    breaker = AdaptiveCircuitBreaker("test", config)

    breaker.record_failure()

    # After a failure with 100% failure rate (>= high_failure_rate 0.7),
    # the threshold should decrease by adjust_step (1), from 5 to 4
    assert breaker.config.failure_threshold == 4, (
        f"Expected threshold to decrease from 5 to 4 after failure, got {breaker.config.failure_threshold}"
    )


def test_adaptive_recovery_records_success():
    config = CircuitBreakerConfig(
        failure_threshold=1,
        success_threshold=1,
        recovery_timeout=0,
        failure_rate_threshold=1.0,
        sliding_window_size=2,
    )
    breaker = AdaptiveCircuitBreaker("test_recovery", config)

    breaker.record_failure()  # opens
    assert breaker.state.value == "open"

    # Transition to half-open and close on success
    assert breaker.can_execute() is True
    breaker.record_success()

    stats = breaker._recovery_monitor.get_stats("test_recovery")
    assert stats.successes >= 1
