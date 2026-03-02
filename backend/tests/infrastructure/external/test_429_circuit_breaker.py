"""Tests for 429-aware circuit breaker with separate 45s open window."""

import time

import pytest

from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    CircuitBreaker,
    CircuitState,
    ErrorType,
    RotationStrategy,
)

# ---------------------------------------------------------------------------
# CircuitBreaker unit tests
# ---------------------------------------------------------------------------


def test_circuit_opens_after_5_consecutive_429s():
    """Circuit trips on 5 consecutive 429 rate-limits."""
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure(ErrorType.RATE_LIMITED)
    assert cb.state == CircuitState.OPEN


def test_circuit_429_open_window_is_45s_not_300s():
    """429-triggered open window must be 45s, not 300s."""
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure(ErrorType.RATE_LIMITED)
    assert cb.state == CircuitState.OPEN
    assert cb.open_seconds <= 60  # 429 window <= 60s
    assert cb.open_seconds < cb.reset_timeout  # < 5xx window (300s)


def test_circuit_stays_closed_on_4_consecutive_429s():
    """Circuit remains CLOSED after only 4 consecutive 429s."""
    cb = CircuitBreaker()
    for _ in range(4):
        cb.record_failure(ErrorType.RATE_LIMITED)
    assert cb.state == CircuitState.CLOSED


def test_circuit_half_open_after_429_window_expires():
    """Circuit transitions to HALF_OPEN after 45s open window expires."""
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure(ErrorType.RATE_LIMITED)
    # Simulate window expired
    cb._opened_at = time.time() - 46
    assert cb.state == CircuitState.HALF_OPEN


def test_success_resets_both_429_and_5xx_counters():
    """record_success resets both 429 and 5xx failure counters."""
    cb = CircuitBreaker()
    # Trigger some 429s and 5xx
    for _ in range(4):
        cb.record_failure(ErrorType.RATE_LIMITED)
    for _ in range(3):
        cb.record_failure(ErrorType.UPSTREAM_5XX)
    cb.record_success()
    assert cb._429_count == 0
    assert cb._failure_count == 0
    assert cb.state == CircuitState.CLOSED


def test_5xx_circuit_still_uses_300s_window():
    """5xx-triggered circuit still uses the 300s reset timeout."""
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure(ErrorType.UPSTREAM_5XX)
    assert cb.state == CircuitState.OPEN
    assert cb.open_seconds == cb.reset_timeout  # 300s


def test_circuit_mixes_429_and_5xx_independently():
    """4 x 429 + 1 x 5xx does not trip the circuit (different counters)."""
    cb = CircuitBreaker()
    for _ in range(4):
        cb.record_failure(ErrorType.RATE_LIMITED)
    cb.record_failure(ErrorType.UPSTREAM_5XX)
    # 429 counter = 4 (< threshold 5) and 5xx counter = 1 (< threshold 5)
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# APIKeyPool integration
# ---------------------------------------------------------------------------


@pytest.fixture
def single_key_pool():
    return APIKeyPool(
        provider="test",
        keys=[APIKeyConfig(key="k1")],
        strategy=RotationStrategy.FAILOVER,
    )


def test_pool_circuit_opens_on_5_consecutive_429_handle_errors(single_key_pool):
    """APIKeyPool circuit breaker trips when handle_error is called 5x with 429."""
    pool = single_key_pool
    for _ in range(5):
        pool.circuit_breaker.record_failure(ErrorType.RATE_LIMITED)
    assert pool.circuit_breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_pool_get_healthy_key_returns_none_when_circuit_open(single_key_pool):
    """get_healthy_key returns None when circuit is OPEN."""
    pool = single_key_pool
    for _ in range(5):
        pool.circuit_breaker.record_failure(ErrorType.RATE_LIMITED)
    key = await pool.get_healthy_key()
    assert key is None
