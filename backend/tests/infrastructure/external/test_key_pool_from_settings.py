"""Tests for key pool settings integration."""

from app.infrastructure.external.key_pool import CIRCUIT_BREAKER_THRESHOLD, CircuitBreaker


class TestCircuitBreakerFromSettings:
    def test_custom_threshold(self):
        cb = CircuitBreaker(threshold=3, reset_timeout=60.0)
        assert cb.threshold == 3

    def test_default_threshold(self):
        cb = CircuitBreaker()
        assert cb.threshold == CIRCUIT_BREAKER_THRESHOLD

    def test_from_settings_fallback(self):
        # from_settings() should not crash even if settings not available
        cb = CircuitBreaker.from_settings()
        assert cb.threshold >= 1
