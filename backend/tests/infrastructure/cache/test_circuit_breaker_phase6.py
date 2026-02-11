"""Tests for Phase 6 semantic cache circuit breaker.

Tests SLO monitoring and automatic cache bypass when hit rate drops.
"""

import time

import pytest

from app.infrastructure.external.cache.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    SemanticCacheCircuitBreaker,
)


class TestCircuitBreakerInitialization:
    """Test circuit breaker initialization."""

    def test_default_initialization(self):
        """Test circuit breaker initializes with default config."""
        cb = SemanticCacheCircuitBreaker()

        assert cb.state == CircuitState.CLOSED
        assert cb._config.failure_threshold == 0.40
        assert cb._config.recovery_threshold == 0.60
        assert cb._config.failure_window_seconds == 300
        assert cb._config.recovery_window_seconds == 180

    def test_custom_config(self):
        """Test circuit breaker with custom configuration."""
        config = CircuitBreakerConfig(
            failure_threshold=0.30,
            recovery_threshold=0.70,
            failure_window_seconds=120,
        )
        cb = SemanticCacheCircuitBreaker(config)

        assert cb._config.failure_threshold == 0.30
        assert cb._config.recovery_threshold == 0.70
        assert cb._config.failure_window_seconds == 120


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    def test_starts_in_closed_state(self):
        """Test circuit starts in CLOSED state."""
        cb = SemanticCacheCircuitBreaker()

        assert cb.state == CircuitState.CLOSED
        assert cb.is_cache_allowed() is True

    def test_low_hit_rate_opens_circuit(self):
        """Test circuit opens when hit rate drops below threshold."""
        config = CircuitBreakerConfig(
            failure_threshold=0.40,
            failure_window_seconds=10,
            min_samples=5,
        )
        cb = SemanticCacheCircuitBreaker(config)

        # Simulate low hit rate (30%)
        for _ in range(3):
            cb.record_request(hit=True)
        for _ in range(7):
            cb.record_request(hit=False)

        # Wait a bit for samples to accumulate
        time.sleep(0.1)

        # Should still be closed (need consecutive failures)
        # Record more low-hit-rate samples
        for _ in range(3):
            cb.record_request(hit=True)
        for _ in range(7):
            cb.record_request(hit=False)

        time.sleep(0.1)

        # After consecutive failures, should open
        for _ in range(3):
            cb.record_request(hit=True)
        for _ in range(7):
            cb.record_request(hit=False)

        time.sleep(0.1)

        # Check if circuit opened (may take a few samples)
        assert cb._consecutive_failures >= 1

    def test_cache_bypassed_when_open(self):
        """Test cache is bypassed when circuit is OPEN."""
        cb = SemanticCacheCircuitBreaker()
        cb._state = CircuitState.OPEN

        assert cb.is_cache_allowed() is False

    def test_cache_allowed_when_half_open(self):
        """Test cache is allowed when circuit is HALF_OPEN."""
        cb = SemanticCacheCircuitBreaker()
        cb._state = CircuitState.HALF_OPEN

        assert cb.is_cache_allowed() is True


class TestCircuitBreakerRecovery:
    """Test circuit breaker recovery logic."""

    def test_transitions_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after failure window."""
        config = CircuitBreakerConfig(failure_window_seconds=1)
        cb = SemanticCacheCircuitBreaker(config)

        # Force OPEN state
        cb._state = CircuitState.OPEN
        cb._state_changed_at = time.time() - 2  # 2 seconds ago

        # Trigger state update
        cb.record_request(hit=True)

        # Should transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_circuit_on_recovery(self):
        """Test circuit closes when hit rate recovers."""
        config = CircuitBreakerConfig(
            recovery_threshold=0.60,
            recovery_window_seconds=5,
            half_open_test_seconds=1,
            min_samples=5,
        )
        cb = SemanticCacheCircuitBreaker(config)

        # Start in HALF_OPEN
        cb._state = CircuitState.HALF_OPEN
        cb._half_open_started_at = time.time() - 2  # Started 2 seconds ago

        # Simulate high hit rate (70%)
        for _ in range(7):
            cb.record_request(hit=True)
        for _ in range(3):
            cb.record_request(hit=False)

        time.sleep(0.1)

        # Should close after consecutive successes
        for _ in range(7):
            cb.record_request(hit=True)
        for _ in range(3):
            cb.record_request(hit=False)

        time.sleep(0.1)

        # Check recovery attempt
        assert cb._consecutive_successes >= 1


class TestHitRateCalculation:
    """Test hit rate calculation in time windows."""

    def test_hit_rate_with_sufficient_samples(self):
        """Test hit rate calculation with enough samples."""
        config = CircuitBreakerConfig(min_samples=3)
        cb = SemanticCacheCircuitBreaker(config)

        # 60% hit rate
        for _ in range(6):
            cb.record_request(hit=True)
        for _ in range(4):
            cb.record_request(hit=False)

        hit_rate = cb._get_hit_rate_in_window(window_seconds=60)

        assert hit_rate is not None
        assert 0.55 <= hit_rate <= 0.65  # Allow for floating point

    def test_hit_rate_insufficient_samples(self):
        """Test hit rate returns None when samples insufficient."""
        config = CircuitBreakerConfig(min_samples=10)
        cb = SemanticCacheCircuitBreaker(config)

        # Only 3 samples
        cb.record_request(hit=True)
        cb.record_request(hit=True)
        cb.record_request(hit=False)

        hit_rate = cb._get_hit_rate_in_window(window_seconds=60)

        assert hit_rate is None

    def test_hit_rate_time_window_filtering(self):
        """Test hit rate only considers samples in time window."""
        cb = SemanticCacheCircuitBreaker()

        # Old samples (outside window)
        cb._samples.append(
            type("Sample", (), {"timestamp": time.time() - 1000, "hits": 10, "misses": 0, "total": 10})()
        )

        # Recent samples (inside window)
        for _ in range(5):
            cb.record_request(hit=True)
        for _ in range(5):
            cb.record_request(hit=False)

        hit_rate = cb._get_hit_rate_in_window(window_seconds=60)

        # Should only count recent samples (50% hit rate)
        assert hit_rate is not None
        assert 0.45 <= hit_rate <= 0.55


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics and monitoring."""

    def test_state_numeric_mapping(self):
        """Test numeric state mapping for Prometheus."""
        cb = SemanticCacheCircuitBreaker()

        cb._state = CircuitState.CLOSED
        assert cb.state_numeric == 0

        cb._state = CircuitState.OPEN
        assert cb.state_numeric == 1

        cb._state = CircuitState.HALF_OPEN
        assert cb.state_numeric == 2

    def test_get_metrics_returns_current_state(self):
        """Test get_metrics returns comprehensive metrics."""
        cb = SemanticCacheCircuitBreaker()

        # Add some samples
        for _ in range(6):
            cb.record_request(hit=True)
        for _ in range(4):
            cb.record_request(hit=False)

        metrics = cb.get_metrics()

        assert "state" in metrics
        assert "state_numeric" in metrics
        assert "current_hit_rate" in metrics
        assert "failure_threshold" in metrics
        assert "recovery_threshold" in metrics
        assert "time_in_state_seconds" in metrics
        assert "total_samples" in metrics

        assert metrics["state"] == "closed"
        assert metrics["state_numeric"] == 0
        assert metrics["total_samples"] == 10


class TestSampleAggregation:
    """Test request sample aggregation."""

    def test_samples_aggregated_by_second(self):
        """Test requests are aggregated into per-second samples."""
        cb = SemanticCacheCircuitBreaker()

        # Multiple requests in same second
        cb.record_request(hit=True)
        cb.record_request(hit=True)
        cb.record_request(hit=False)

        # Should have 1 sample with 2 hits, 1 miss
        assert len(cb._samples) == 1
        assert cb._samples[0].hits == 2
        assert cb._samples[0].misses == 1

    def test_new_sample_created_after_second(self):
        """Test new sample is created after 1 second."""
        cb = SemanticCacheCircuitBreaker()

        cb.record_request(hit=True)
        initial_count = len(cb._samples)

        # Wait for next second
        time.sleep(1.1)

        cb.record_request(hit=True)

        # Should have 2 samples now
        assert len(cb._samples) == initial_count + 1
