"""Comprehensive tests for CircuitBreakerRegistry and related classes.

Covers CircuitState enum, CircuitBreakerConfig, CircuitBreakerStats,
CircuitBreaker state transitions, and CircuitBreakerRegistry class methods.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

import app.core.circuit_breaker_registry as cbr_module
from app.core.circuit_breaker_registry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitBreakerStats,
    CircuitOpenError,
    CircuitState,
    get_circuit_breaker,
)

# ---------------------------------------------------------------------------
# Helpers / shared patches
# ---------------------------------------------------------------------------

FEATURE_FLAGS_PATCH = "app.core.circuit_breaker_registry.get_feature_flags"


@pytest.fixture(autouse=True)
def reset_registry():
    """Clear the class-level registry dict between every test."""
    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.fixture(autouse=True)
def mock_feature_flags():
    """Ensure get_feature_flags returns an empty dict (no adaptive breaker)."""
    with patch(FEATURE_FLAGS_PATCH, return_value={}):
        yield


@pytest.fixture(autouse=True)
def reset_metrics_globals():
    """Reset the module-level metrics globals so lazy import is retried fresh."""
    original_imported = cbr_module._metrics_imported
    original_state = cbr_module._record_circuit_breaker_state
    original_call = cbr_module._record_circuit_breaker_call
    original_change = cbr_module._record_circuit_breaker_state_change
    cbr_module._metrics_imported = False
    cbr_module._record_circuit_breaker_state = None
    cbr_module._record_circuit_breaker_call = None
    cbr_module._record_circuit_breaker_state_change = None
    yield
    cbr_module._metrics_imported = original_imported
    cbr_module._record_circuit_breaker_state = original_state
    cbr_module._record_circuit_breaker_call = original_call
    cbr_module._record_circuit_breaker_state_change = original_change


def make_breaker(**kwargs) -> CircuitBreaker:
    """Return a fresh CircuitBreaker with convenient defaults."""
    config = CircuitBreakerConfig(**kwargs)
    return CircuitBreaker("test-breaker", config)


# ===========================================================================
# 1. CircuitState enum values (3 tests)
# ===========================================================================


class TestCircuitStateEnum:
    def test_closed_value(self):
        assert CircuitState.CLOSED.value == "closed"

    def test_open_value(self):
        assert CircuitState.OPEN.value == "open"

    def test_half_open_value(self):
        assert CircuitState.HALF_OPEN.value == "half_open"


# ===========================================================================
# 2. CircuitBreakerConfig defaults and custom (4 tests)
# ===========================================================================


class TestCircuitBreakerConfig:
    def test_default_failure_threshold(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5

    def test_default_recovery_timeout(self):
        cfg = CircuitBreakerConfig()
        assert cfg.recovery_timeout == 60

    def test_default_excluded_empty(self):
        cfg = CircuitBreakerConfig()
        assert cfg.excluded_exceptions == ()
        assert cfg.excluded_error_patterns == ()

    def test_custom_values_stored(self):
        cfg = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=5,
            recovery_timeout=120,
            half_open_max_calls=2,
            failure_rate_threshold=0.3,
            sliding_window_size=20,
            excluded_exceptions=(ValueError,),
            excluded_error_patterns=("rate limit",),
        )
        assert cfg.failure_threshold == 10
        assert cfg.success_threshold == 5
        assert cfg.recovery_timeout == 120
        assert cfg.half_open_max_calls == 2
        assert cfg.failure_rate_threshold == 0.3
        assert cfg.sliding_window_size == 20
        assert ValueError in cfg.excluded_exceptions
        assert "rate limit" in cfg.excluded_error_patterns


# ===========================================================================
# 3. CircuitBreakerStats failure_rate and sliding window (5 tests)
# ===========================================================================


class TestCircuitBreakerStats:
    def test_failure_rate_empty_window(self):
        stats = CircuitBreakerStats()
        assert stats.failure_rate == 0.0

    def test_failure_rate_all_failures(self):
        stats = CircuitBreakerStats()
        stats.recent_results = [False, False, False]
        assert stats.failure_rate == 1.0

    def test_failure_rate_mixed(self):
        stats = CircuitBreakerStats()
        stats.recent_results = [True, False, True, False]
        assert stats.failure_rate == 0.5

    def test_record_result_appends(self):
        stats = CircuitBreakerStats()
        stats.record_result(True, window_size=5)
        assert stats.recent_results == [True]

    def test_record_result_trims_to_window(self):
        stats = CircuitBreakerStats()
        for _ in range(12):
            stats.record_result(True, window_size=10)
        assert len(stats.recent_results) == 10


# ===========================================================================
# 4. CircuitBreaker state transitions (6 tests)
# ===========================================================================


class TestCircuitBreakerStateTransitions:
    def test_initial_state_is_closed(self):
        cb = make_breaker()
        assert cb.state == CircuitState.CLOSED

    def test_closed_to_open_on_failure_threshold(self):
        cb = make_breaker(failure_threshold=3, failure_rate_threshold=1.0, sliding_window_size=10)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open_after_recovery_timeout(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # recovery_timeout=0 means immediately eligible
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_enough_successes(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0, success_threshold=2)
        cb.record_failure()
        cb.can_execute()  # triggers OPEN -> HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb._half_open_calls = 1
        cb.record_success()
        cb._half_open_calls = 1
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.can_execute()  # OPEN -> HALF_OPEN
        cb._half_open_calls = 1
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_state_changes_counter_increments(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0, success_threshold=1)
        cb.record_failure()  # CLOSED -> OPEN (+1)
        cb.can_execute()  # OPEN -> HALF_OPEN (+1)
        cb._half_open_calls = 1
        cb.record_success()  # HALF_OPEN -> CLOSED (+1)
        assert cb.stats.state_changes == 3


# ===========================================================================
# 5. can_execute in all states (4 tests)
# ===========================================================================


class TestCanExecute:
    def test_can_execute_in_closed_state(self):
        cb = make_breaker()
        assert cb.can_execute() is True

    def test_cannot_execute_in_open_state_within_timeout(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_can_execute_in_half_open_within_limit(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0, half_open_max_calls=2)
        cb.record_failure()
        cb.can_execute()  # OPEN -> HALF_OPEN; half_open_calls=0 < 2
        # Still within limit
        cb._half_open_calls = 1
        assert cb.can_execute() is True

    def test_cannot_execute_in_half_open_at_limit(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0, half_open_max_calls=2)
        cb.record_failure()
        cb.can_execute()  # OPEN -> HALF_OPEN
        cb._half_open_calls = 2  # saturate the limit
        assert cb.can_execute() is False


# ===========================================================================
# 6. record_success in closed/half_open (4 tests)
# ===========================================================================


class TestRecordSuccess:
    def test_success_increments_counters(self):
        cb = make_breaker()
        cb.record_success()
        assert cb.stats.total_calls == 1
        assert cb.stats.successful_calls == 1

    def test_success_resets_failure_count_in_closed(self):
        cb = make_breaker(failure_threshold=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0

    def test_success_in_half_open_increments_success_count(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=0, success_threshold=5)
        cb.record_failure()
        cb.can_execute()  # OPEN -> HALF_OPEN
        cb._half_open_calls = 1
        cb.record_success()
        assert cb._success_count == 1

    def test_success_updates_last_success_time(self):
        cb = make_breaker()
        before = datetime.now(UTC)
        cb.record_success()
        assert cb.stats.last_success_time is not None
        assert cb.stats.last_success_time >= before


# ===========================================================================
# 7. record_failure count-based and rate-based opening (4 tests)
# ===========================================================================


class TestRecordFailure:
    def test_failure_increments_counters(self):
        cb = make_breaker(failure_threshold=10)
        cb.record_failure()
        assert cb.stats.total_calls == 1
        assert cb.stats.failed_calls == 1

    def test_failure_opens_on_count_threshold(self):
        cb = make_breaker(failure_threshold=3, failure_rate_threshold=1.0, sliding_window_size=20)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_failure_opens_on_rate_threshold(self):
        # failure_rate_threshold=0.5, sliding_window=4: 3 failures in 4 calls
        cb = make_breaker(failure_threshold=100, failure_rate_threshold=0.5, sliding_window_size=4)
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        # 3/4 = 0.75 >= 0.5 -> should open
        assert cb.state == CircuitState.OPEN

    def test_failure_updates_last_failure_time(self):
        cb = make_breaker(failure_threshold=100)
        before = datetime.now(UTC)
        cb.record_failure()
        assert cb.stats.last_failure_time is not None
        assert cb.stats.last_failure_time >= before


# ===========================================================================
# 8. reject_call stats (2 tests)
# ===========================================================================


class TestRejectCall:
    def test_reject_call_increments_rejected_count(self):
        cb = make_breaker()
        cb.reject_call()
        assert cb.stats.rejected_calls == 1

    def test_reject_call_does_not_change_state(self):
        cb = make_breaker()
        cb.reject_call()
        assert cb.state == CircuitState.CLOSED


# ===========================================================================
# 9. execute() async context manager (6 tests)
# ===========================================================================


class TestExecuteContextManager:
    def test_execute_success_records_success(self):
        cb = make_breaker()

        async def run():
            async with cb.execute():
                pass

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.successful_calls == 1

    def test_execute_exception_records_failure(self):
        cb = make_breaker(failure_threshold=100)

        async def run():
            with pytest.raises(RuntimeError):
                async with cb.execute():
                    raise RuntimeError("boom")

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.failed_calls == 1

    def test_execute_raises_circuit_open_error_when_open(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()

        async def run():
            with pytest.raises(CircuitOpenError):
                async with cb.execute():
                    pass  # should never reach here

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.rejected_calls == 1

    def test_execute_excluded_exception_does_not_trip_breaker(self):
        cb = make_breaker(
            failure_threshold=1,
            excluded_exceptions=(KeyboardInterrupt,),
        )

        async def run():
            with pytest.raises(KeyboardInterrupt):
                async with cb.execute():
                    raise KeyboardInterrupt()

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.failed_calls == 0
        assert cb.state == CircuitState.CLOSED

    def test_execute_excluded_pattern_does_not_trip_breaker(self):
        cb = make_breaker(
            failure_threshold=1,
            excluded_error_patterns=("rate limit",),
        )

        async def run():
            with pytest.raises(RuntimeError):
                async with cb.execute():
                    raise RuntimeError("Server returned rate limit exceeded")

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.failed_calls == 0
        assert cb.state == CircuitState.CLOSED

    def test_execute_non_excluded_exception_trips_breaker(self):
        cb = make_breaker(
            failure_threshold=1,
            excluded_exceptions=(ValueError,),
        )

        async def run():
            with pytest.raises(RuntimeError):
                async with cb.execute():
                    raise RuntimeError("generic error")

        asyncio.get_event_loop().run_until_complete(run())
        assert cb.stats.failed_calls == 1
        assert cb.state == CircuitState.OPEN


# ===========================================================================
# 10. reset() method (2 tests)
# ===========================================================================


class TestReset:
    def test_reset_returns_to_closed(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_counters(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()
        cb.reset()
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._half_open_calls == 0
        assert cb._last_failure_time is None


# ===========================================================================
# 11. get_status() structure (2 tests)
# ===========================================================================


class TestGetStatus:
    def test_get_status_has_expected_keys(self):
        cb = make_breaker()
        status = cb.get_status()
        assert "name" in status
        assert "state" in status
        assert "failure_count" in status
        assert "failure_rate" in status
        assert "stats" in status
        assert "config" in status

    def test_get_status_state_reflects_current(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=9999)
        cb.record_failure()
        status = cb.get_status()
        assert status["state"] == "open"
        assert status["stats"]["failed_calls"] == 1


# ===========================================================================
# 12. CircuitBreakerRegistry (10 tests)
# ===========================================================================


class TestCircuitBreakerRegistry:
    def test_get_or_create_new_breaker(self):
        cb = CircuitBreakerRegistry.get_or_create("svc-a")
        assert cb is not None
        assert cb.name == "svc-a"

    def test_get_or_create_returns_same_instance(self):
        cb1 = CircuitBreakerRegistry.get_or_create("svc-b")
        cb2 = CircuitBreakerRegistry.get_or_create("svc-b")
        assert cb1 is cb2

    def test_get_returns_existing(self):
        CircuitBreakerRegistry.get_or_create("svc-c")
        cb = CircuitBreakerRegistry.get("svc-c")
        assert cb is not None
        assert cb.name == "svc-c"

    def test_get_returns_none_for_missing(self):
        assert CircuitBreakerRegistry.get("nonexistent") is None

    def test_get_all_states_empty(self):
        assert CircuitBreakerRegistry.get_all_states() == {}

    def test_get_all_states_with_entries(self):
        CircuitBreakerRegistry.get_or_create("svc-d")
        states = CircuitBreakerRegistry.get_all_states()
        assert "svc-d" in states
        assert states["svc-d"] == "closed"

    def test_get_all_status_returns_full_dict(self):
        CircuitBreakerRegistry.get_or_create("svc-e")
        all_status = CircuitBreakerRegistry.get_all_status()
        assert "svc-e" in all_status
        assert "state" in all_status["svc-e"]

    def test_reset_all_closes_open_breakers(self):
        cb = CircuitBreakerRegistry.get_or_create("svc-f", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        CircuitBreakerRegistry.reset_all()
        assert cb.state == CircuitState.CLOSED

    def test_reset_specific_breaker(self):
        cb = CircuitBreakerRegistry.get_or_create("svc-g", failure_threshold=1)
        cb.record_failure()
        assert CircuitBreakerRegistry.reset("svc-g") is True
        assert cb.state == CircuitState.CLOSED

    def test_reset_returns_false_for_missing(self):
        assert CircuitBreakerRegistry.reset("not-there") is False

    def test_remove_existing_breaker(self):
        CircuitBreakerRegistry.get_or_create("svc-h")
        result = CircuitBreakerRegistry.remove("svc-h")
        assert result is True
        assert CircuitBreakerRegistry.get("svc-h") is None

    def test_remove_missing_returns_false(self):
        assert CircuitBreakerRegistry.remove("ghost") is False

    def test_clear_empties_registry(self):
        CircuitBreakerRegistry.get_or_create("svc-i")
        CircuitBreakerRegistry.get_or_create("svc-j")
        CircuitBreakerRegistry.clear()
        assert CircuitBreakerRegistry.get_all_states() == {}

    def test_get_or_create_with_custom_config(self):
        config = CircuitBreakerConfig(failure_threshold=99)
        cb = CircuitBreakerRegistry.get_or_create("svc-k", config=config)
        assert cb.config.failure_threshold == 99


# ===========================================================================
# 13. get_circuit_breaker convenience (2 tests)
# ===========================================================================


class TestGetCircuitBreakerConvenience:
    def test_returns_circuit_breaker_instance(self):
        cb = get_circuit_breaker("convenience-svc")
        assert isinstance(cb, CircuitBreaker)
        assert cb.name == "convenience-svc"

    def test_idempotent_across_calls(self):
        cb1 = get_circuit_breaker("idempotent-svc")
        cb2 = get_circuit_breaker("idempotent-svc")
        assert cb1 is cb2


# ===========================================================================
# 14. Recovery timeout (_should_attempt_recovery) (3 tests)
# ===========================================================================


class TestShouldAttemptRecovery:
    def test_no_failure_time_allows_recovery(self):
        cb = make_breaker(recovery_timeout=9999)
        cb._last_failure_time = None
        assert cb._should_attempt_recovery() is True

    def test_within_timeout_blocks_recovery(self):
        cb = make_breaker(recovery_timeout=9999)
        cb._last_failure_time = datetime.now(UTC)
        assert cb._should_attempt_recovery() is False

    def test_past_timeout_allows_recovery(self):
        cb = make_breaker(recovery_timeout=1)
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=5)
        assert cb._should_attempt_recovery() is True
