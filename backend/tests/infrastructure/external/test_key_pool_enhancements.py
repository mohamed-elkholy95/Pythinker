"""Tests for APIKeyPool enhancements: error classification, circuit breaker,
consecutive rate limit tracking, dual quota detection, adaptive TTL, and
per-provider cooldown overrides.
"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.key_pool import (
    _ERROR_COOLDOWNS,
    QUOTA_KEYWORDS,
    APIKeyConfig,
    APIKeyPool,
    CircuitBreaker,
    CircuitState,
    ErrorType,
    RotationStrategy,
    _text_has_quota_keywords,
    classify_error,
)

# ─────────────────────────────────────────────────────────────────
# 1. ErrorType + classify_error()
# ─────────────────────────────────────────────────────────────────


class TestClassifyError:
    """Test the 7-category error classification function."""

    def test_client_error_400(self):
        error_type, cooldown = classify_error(status_code=400)
        assert error_type == ErrorType.CLIENT_ERROR
        assert cooldown == 0  # No cooldown for client errors

    def test_auth_error_401(self):
        error_type, cooldown = classify_error(status_code=401)
        assert error_type == ErrorType.AUTH_ERROR
        assert cooldown == 3600

    def test_auth_error_403(self):
        error_type, cooldown = classify_error(status_code=403)
        assert error_type == ErrorType.AUTH_ERROR
        assert cooldown == 3600

    def test_payment_required_402(self):
        error_type, cooldown = classify_error(status_code=402)
        assert error_type == ErrorType.QUOTA_EXHAUSTED
        assert cooldown == 86400

    def test_rate_limited_429(self):
        error_type, cooldown = classify_error(status_code=429)
        assert error_type == ErrorType.RATE_LIMITED
        assert cooldown == 60  # Base cooldown

    def test_upstream_5xx(self):
        for code in (500, 502, 503, 504):
            error_type, cooldown = classify_error(status_code=code)
            assert error_type == ErrorType.UPSTREAM_5XX
            assert cooldown == 30

    def test_network_error(self):
        error_type, cooldown = classify_error(is_network_error=True)
        assert error_type == ErrorType.NETWORK_ERROR
        assert cooldown == 15

    def test_quota_keyword_in_body_overrides_status_code(self):
        """Body keyword scan takes precedence over generic status codes."""
        error_type, cooldown = classify_error(
            status_code=200,
            body_text='{"error": "monthly limit exceeded"}',
        )
        assert error_type == ErrorType.QUOTA_EXHAUSTED
        assert cooldown == 86400

    def test_not_enough_credits_in_body(self):
        error_type, _ = classify_error(
            status_code=400,
            body_text='{"message": "Not enough credits"}',
        )
        assert error_type == ErrorType.QUOTA_EXHAUSTED

    def test_billing_keyword_in_body(self):
        error_type, _ = classify_error(body_text="billing error: subscription expired")
        assert error_type == ErrorType.QUOTA_EXHAUSTED

    def test_unknown_status_code(self):
        error_type, cooldown = classify_error(status_code=418)
        assert error_type == ErrorType.OTHER
        assert cooldown == 60

    def test_no_info_returns_other(self):
        error_type, cooldown = classify_error()
        assert error_type == ErrorType.OTHER
        assert cooldown == 60

    def test_network_error_overrides_body(self):
        """Network errors are checked first — even if body has quota keywords."""
        error_type, _ = classify_error(is_network_error=True, body_text="quota exceeded")
        assert error_type == ErrorType.NETWORK_ERROR


class TestQuotaKeywords:
    """Test dual quota detection keyword scanning."""

    def test_quota_keywords_constant(self):
        assert "quota" in QUOTA_KEYWORDS
        assert "not enough credits" in QUOTA_KEYWORDS
        assert "billing" in QUOTA_KEYWORDS

    def test_text_has_quota_keywords_positive(self):
        assert _text_has_quota_keywords("Your monthly limit has been exceeded")
        assert _text_has_quota_keywords('{"error": "Not enough credits"}')
        assert _text_has_quota_keywords("usage limit reached for this key")
        assert _text_has_quota_keywords("Payment Required: billing issue")

    def test_text_has_quota_keywords_negative(self):
        assert not _text_has_quota_keywords("Search completed successfully")
        assert not _text_has_quota_keywords('{"results": [{"title": "test"}]}')

    def test_case_insensitive(self):
        assert _text_has_quota_keywords("QUOTA EXCEEDED")
        assert _text_has_quota_keywords("Not Enough Credits")


# ─────────────────────────────────────────────────────────────────
# 2. Circuit Breaker
# ─────────────────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Test the CLOSED → OPEN → HALF_OPEN state machine."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_success_keeps_closed(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_non_5xx_does_not_trip(self):
        cb = CircuitBreaker(threshold=2)
        for _ in range(10):
            cb.record_failure(ErrorType.RATE_LIMITED)
            cb.record_failure(ErrorType.AUTH_ERROR)
        assert cb.state == CircuitState.CLOSED

    def test_5xx_trips_after_threshold(self):
        cb = CircuitBreaker(threshold=5)
        for i in range(4):
            cb.record_failure(ErrorType.UPSTREAM_5XX)
            assert cb.state == CircuitState.CLOSED, f"Should still be closed after {i + 1} failures"

        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(threshold=1)
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_open_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(threshold=1, reset_timeout=0.1)
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request()  # One probe allowed

    def test_half_open_allows_one_probe(self):
        cb = CircuitBreaker(threshold=1, reset_timeout=0.0)
        cb.record_failure(ErrorType.UPSTREAM_5XX)

        # Force transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        # First request: allowed (probe)
        assert cb.allow_request()
        # Second request: blocked (probe in flight)
        assert not cb.allow_request()

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(threshold=1, reset_timeout=0.0)
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(threshold=1, reset_timeout=60)  # Non-zero to prevent auto-transition
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.OPEN

        # Manually force HALF_OPEN by backdating opened_at
        cb._opened_at = time.time() - 61
        assert cb.state == CircuitState.HALF_OPEN

        cb.allow_request()  # Start probe
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(threshold=5)
        # Accumulate 4 failures
        for _ in range(4):
            cb.record_failure(ErrorType.UPSTREAM_5XX)
        # Reset with success
        cb.record_success()
        # 4 more failures should not trip (counter reset)
        for _ in range(4):
            cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.state == CircuitState.CLOSED

    def test_status_report(self):
        cb = CircuitBreaker()
        assert "CLOSED" in cb.status_report()

        cb = CircuitBreaker(threshold=1)
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        report = cb.status_report()
        assert "OPEN" in report
        assert "remaining" in report

    def test_is_open_property(self):
        cb = CircuitBreaker(threshold=1)
        assert not cb.is_open
        cb.record_failure(ErrorType.UPSTREAM_5XX)
        assert cb.is_open


# ─────────────────────────────────────────────────────────────────
# 3. Consecutive Rate Limit Tracking
# ─────────────────────────────────────────────────────────────────


class TestRateLimitTracking:
    """Test exponential backoff progression for rate-limited keys."""

    def _make_pool(self, n_keys: int = 2) -> APIKeyPool:
        keys = [APIKeyConfig(key=f"key-{i}") for i in range(n_keys)]
        return APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )

    def test_first_rate_limit_uses_base_cooldown(self):
        pool = self._make_pool()
        cooldown = pool._get_rate_limit_cooldown("key-0")
        # Base = 60s * 2^0 = 60s + jitter(0-15)
        assert 60 <= cooldown <= 75

    def test_exponential_progression(self):
        pool = self._make_pool()
        cooldowns = [pool._get_rate_limit_cooldown("key-0") for _ in range(5)]

        # Each should roughly double (with jitter making exact values unpredictable)
        # 1st: ~60s, 2nd: ~120s, 3rd: ~240s, 4th: ~480s, 5th: capped at ~600s
        assert cooldowns[0] < cooldowns[1]
        assert cooldowns[1] < cooldowns[2]
        assert cooldowns[2] < cooldowns[3]
        # 5th should be capped at 600s + jitter (max 60s) = 660s
        assert cooldowns[4] <= 660

    def test_cap_at_600_seconds(self):
        pool = self._make_pool()
        # Simulate many rate limits
        for _ in range(20):
            pool._get_rate_limit_cooldown("key-0")
        final = pool._get_rate_limit_cooldown("key-0")
        # Should be capped: 600 + jitter(max 60) = 660
        assert final <= 660

    def test_success_resets_counter(self):
        pool = self._make_pool()
        # Accumulate rate limits
        pool._get_rate_limit_cooldown("key-0")
        pool._get_rate_limit_cooldown("key-0")
        pool._get_rate_limit_cooldown("key-0")

        # Reset
        pool.record_success("key-0")

        # Next rate limit should be back to base
        cooldown = pool._get_rate_limit_cooldown("key-0")
        assert 60 <= cooldown <= 75

    def test_per_key_isolation(self):
        pool = self._make_pool()
        # Rate limit key-0 multiple times
        for _ in range(3):
            pool._get_rate_limit_cooldown("key-0")

        # key-1 should be at base level
        cooldown = pool._get_rate_limit_cooldown("key-1")
        assert 60 <= cooldown <= 75


# ─────────────────────────────────────────────────────────────────
# 4. handle_error() integration
# ─────────────────────────────────────────────────────────────────


class TestHandleError:
    """Test the unified error handling entry point."""

    def _make_pool(self) -> APIKeyPool:
        keys = [APIKeyConfig(key=f"key-{i}") for i in range(3)]
        return APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.FAILOVER,
            redis_client=None,
        )

    @pytest.mark.asyncio
    async def test_client_error_no_cooldown(self):
        pool = self._make_pool()
        error_type = await pool.handle_error("key-0", status_code=400)
        assert error_type == ErrorType.CLIENT_ERROR
        # Key should still be healthy
        assert await pool._is_healthy("key-0")

    @pytest.mark.asyncio
    async def test_auth_error_marks_invalid(self):
        pool = self._make_pool()
        error_type = await pool.handle_error("key-0", status_code=401)
        assert error_type == ErrorType.AUTH_ERROR
        # Key should be permanently invalid
        assert not await pool._is_healthy("key-0")

    @pytest.mark.asyncio
    async def test_rate_limited_marks_exhausted_with_backoff(self):
        pool = self._make_pool()
        error_type = await pool.handle_error("key-0", status_code=429)
        assert error_type == ErrorType.RATE_LIMITED
        # Key should be in cooldown
        assert not await pool._is_healthy("key-0")

    @pytest.mark.asyncio
    async def test_quota_exhausted_from_body(self):
        pool = self._make_pool()
        error_type = await pool.handle_error(
            "key-0",
            status_code=200,
            body_text='{"error": "monthly limit exceeded"}',
        )
        assert error_type == ErrorType.QUOTA_EXHAUSTED
        assert not await pool._is_healthy("key-0")

    @pytest.mark.asyncio
    async def test_upstream_5xx_triggers_circuit_breaker(self):
        pool = self._make_pool()
        pool.circuit_breaker = CircuitBreaker(threshold=2)

        await pool.handle_error("key-0", status_code=500)
        assert pool.circuit_breaker.state == CircuitState.CLOSED

        await pool.handle_error("key-1", status_code=502)
        assert pool.circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_network_error_short_cooldown(self):
        pool = self._make_pool()
        error_type = await pool.handle_error("key-0", is_network_error=True)
        assert error_type == ErrorType.NETWORK_ERROR
        assert not await pool._is_healthy("key-0")

    @pytest.mark.asyncio
    async def test_record_success_resets_state(self):
        pool = self._make_pool()
        pool._get_rate_limit_cooldown("key-0")
        pool._get_rate_limit_cooldown("key-0")

        pool.record_success("key-0")

        key_hash = pool._hash_key("key-0")
        assert key_hash not in pool._consecutive_rate_limits


# ─────────────────────────────────────────────────────────────────
# 5. Circuit breaker integration with get_healthy_key()
# ─────────────────────────────────────────────────────────────────


class TestCircuitBreakerIntegration:
    """Test circuit breaker blocks get_healthy_key() when OPEN."""

    @pytest.mark.asyncio
    async def test_open_circuit_returns_none(self):
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )

        # Trip circuit
        pool.circuit_breaker = CircuitBreaker(threshold=1)
        pool.circuit_breaker.record_failure(ErrorType.UPSTREAM_5XX)
        assert pool.circuit_breaker.is_open

        # get_healthy_key should return None
        result = await pool.get_healthy_key()
        assert result is None

    @pytest.mark.asyncio
    async def test_closed_circuit_returns_key(self):
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )

        result = await pool.get_healthy_key()
        assert result == "key-0"


# ─────────────────────────────────────────────────────────────────
# 6. Status report
# ─────────────────────────────────────────────────────────────────


class TestStatusReport:
    """Test human-readable status output."""

    def test_status_report_shows_all_keys(self):
        keys = [APIKeyConfig(key=f"key-{i}") for i in range(3)]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        report = pool.status_report()
        assert "test API Key Pool Status" in report
        assert "Total keys: 3" in report
        assert "Available: 3" in report
        assert "Circuit Breaker: CLOSED" in report

    @pytest.mark.asyncio
    async def test_status_report_shows_cooldown(self):
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        await pool.mark_exhausted("key-0", ttl_seconds=3600)
        report = pool.status_report()
        assert "COOLDOWN" in report

    @pytest.mark.asyncio
    async def test_status_report_shows_invalid(self):
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        await pool.mark_invalid("key-0")
        report = pool.status_report()
        assert "INVALID" in report


# ─────────────────────────────────────────────────────────────────
# 7. Per-provider cooldown overrides
# ─────────────────────────────────────────────────────────────────


class TestCooldownOverrides:
    """Test per-provider cooldown override mechanism."""

    @pytest.mark.asyncio
    async def test_cooldown_override_respected(self):
        """Per-provider override replaces default cooldown for that error type."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="serper",
            keys=keys,
            strategy=RotationStrategy.FAILOVER,
            redis_client=None,
            cooldown_overrides={ErrorType.QUOTA_EXHAUSTED: 14400},  # 4h
        )
        assert pool._cooldowns[ErrorType.QUOTA_EXHAUSTED] == 14400

        # Trigger quota exhaustion — should use 14400s, not 86400s
        await pool.handle_error("key-0", status_code=402)
        key_hash = pool._hash_key("key-0")
        expiry = pool._memory_exhausted[key_hash]
        # The TTL should be ~14400s from now (with adaptive multiplier=1.0)
        remaining = expiry - time.time()
        assert 14300 < remaining < 14500

    def test_default_cooldown_unchanged(self):
        """Without overrides, defaults match module-level _ERROR_COOLDOWNS."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        for error_type, default in _ERROR_COOLDOWNS.items():
            assert pool._cooldowns[error_type] == default

    def test_partial_override_preserves_others(self):
        """Only specified types are overridden; others keep defaults."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
            cooldown_overrides={ErrorType.QUOTA_EXHAUSTED: 7200},
        )
        assert pool._cooldowns[ErrorType.QUOTA_EXHAUSTED] == 7200
        assert pool._cooldowns[ErrorType.AUTH_ERROR] == _ERROR_COOLDOWNS[ErrorType.AUTH_ERROR]
        assert pool._cooldowns[ErrorType.RATE_LIMITED] == _ERROR_COOLDOWNS[ErrorType.RATE_LIMITED]


# ─────────────────────────────────────────────────────────────────
# 8. Expanded QUOTA_KEYWORDS
# ─────────────────────────────────────────────────────────────────


class TestExpandedQuotaKeywords:
    """Test newly added quota keywords."""

    def test_credits_keyword(self):
        assert "credits" in QUOTA_KEYWORDS
        assert _text_has_quota_keywords("You have 0 credits remaining")

    def test_insufficient_keyword(self):
        assert "insufficient" in QUOTA_KEYWORDS
        assert _text_has_quota_keywords("Insufficient balance for this request")
        assert _text_has_quota_keywords("insufficient credits")

    def test_credits_triggers_quota_exhausted(self):
        error_type, _ = classify_error(status_code=200, body_text="0 credits remaining")
        assert error_type == ErrorType.QUOTA_EXHAUSTED

    def test_insufficient_triggers_quota_exhausted(self):
        error_type, _ = classify_error(status_code=200, body_text="insufficient quota")
        assert error_type == ErrorType.QUOTA_EXHAUSTED


# ─────────────────────────────────────────────────────────────────
# 9. Redis TTL sync
# ─────────────────────────────────────────────────────────────────


class TestRedisTTLSync:
    """Test that _is_healthy uses actual Redis TTL for in-memory sync."""

    @pytest.mark.asyncio
    async def test_redis_ttl_sync(self):
        """_is_healthy uses actual Redis TTL, not hardcoded 60s."""
        mock_redis = AsyncMock()
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )
        key_hash = pool._hash_key("key-0")

        # Simulate Redis: key not invalid, but exhausted with 7200s TTL
        mock_redis.call = AsyncMock(
            side_effect=lambda cmd, *args: (
                0
                if cmd == "exists"
                # not invalid
                else 7200
                if cmd == "ttl"
                else 0
            )
        )

        healthy = await pool._is_healthy("key-0")
        assert not healthy

        # Verify in-memory expiry is ~7200s from now (not 60s)
        remaining = pool._memory_exhausted[key_hash] - time.time()
        assert 7100 < remaining < 7300

    @pytest.mark.asyncio
    async def test_redis_ttl_negative_means_healthy(self):
        """TTL -2 (key doesn't exist) means the key is healthy."""
        mock_redis = AsyncMock()
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Simulate Redis: not invalid, TTL=-2 (key doesn't exist = healthy)
        mock_redis.call = AsyncMock(side_effect=lambda cmd, *args: 0 if cmd == "exists" else -2 if cmd == "ttl" else 0)

        healthy = await pool._is_healthy("key-0")
        assert healthy


# ─────────────────────────────────────────────────────────────────
# 10. Adaptive TTL learning
# ─────────────────────────────────────────────────────────────────


class TestAdaptiveTTL:
    """Test adaptive TTL multiplier shrinks on early recovery."""

    @pytest.mark.asyncio
    async def test_adaptive_ttl_shrinks_on_early_recovery(self):
        """Multiplier decreases when key recovers before 75% of configured TTL."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
            cooldown_overrides={ErrorType.QUOTA_EXHAUSTED: 10000},
        )
        assert pool._adaptive_ttl_multiplier == 1.0

        key_hash = pool._hash_key("key-0")
        # Simulate: key was marked exhausted 1000s ago (well under 75% of 10000s)
        pool._exhaustion_timestamps[key_hash] = time.time() - 1000

        pool.record_success("key-0")

        # Multiplier should shrink by 0.7
        assert abs(pool._adaptive_ttl_multiplier - 0.7) < 0.01

    @pytest.mark.asyncio
    async def test_adaptive_ttl_floor(self):
        """Multiplier never drops below 0.25."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        key_hash = pool._hash_key("key-0")

        # Simulate many early recoveries to push multiplier toward floor
        for _ in range(20):
            pool._exhaustion_timestamps[key_hash] = time.time() - 10
            pool.record_success("key-0")

        assert pool._adaptive_ttl_multiplier >= 0.25

    @pytest.mark.asyncio
    async def test_adaptive_multiplier_applied_to_mark_exhausted(self):
        """mark_exhausted applies the adaptive multiplier to TTL."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        # Force a low multiplier
        pool._adaptive_ttl_multiplier = 0.5

        await pool.mark_exhausted("key-0", ttl_seconds=10000)
        key_hash = pool._hash_key("key-0")
        remaining = pool._memory_exhausted[key_hash] - time.time()
        # Should be ~5000s (10000 * 0.5), not 10000s
        assert 4900 < remaining < 5100

    @pytest.mark.asyncio
    async def test_adaptive_not_applied_to_rate_limit(self):
        """Rate limit cooldowns bypass adaptive multiplier."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        pool._adaptive_ttl_multiplier = 0.25  # Would drastically reduce if applied

        await pool.handle_error("key-0", status_code=429)
        key_hash = pool._hash_key("key-0")
        remaining = pool._memory_exhausted[key_hash] - time.time()
        # Rate limit base = 60s; if adaptive were applied it'd be 15s
        # It should be 60+ (not reduced)
        assert remaining >= 55


# ─────────────────────────────────────────────────────────────────
# 11. Background health probe
# ─────────────────────────────────────────────────────────────────


class TestHealthProbe:
    """Test background health probe lifecycle."""

    @pytest.mark.asyncio
    async def test_health_probe_clears_expired(self):
        """Probe removes expired in-memory entries."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )
        key_hash = pool._hash_key("key-0")

        # Set an already-expired entry
        pool._memory_exhausted[key_hash] = time.time() - 10
        pool._exhaustion_timestamps[key_hash] = time.time() - 100

        # Start probe with very short interval
        pool.start_health_probe(interval_seconds=0.05)
        try:
            await asyncio.sleep(0.15)  # Wait for at least one probe cycle
            assert key_hash not in pool._memory_exhausted
            assert key_hash not in pool._exhaustion_timestamps
        finally:
            pool.stop_health_probe()

    @pytest.mark.asyncio
    async def test_health_probe_cancellation(self):
        """Probe stops cleanly on stop_health_probe()."""
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=None,
        )

        pool.start_health_probe(interval_seconds=0.05)
        assert pool._health_probe_task is not None
        assert not pool._health_probe_task.done()

        pool.stop_health_probe()
        assert pool._health_probe_task is None

    @pytest.mark.asyncio
    async def test_health_probe_redis_sync(self):
        """Probe clears in-memory entries when Redis TTL shows key expired."""
        mock_redis = AsyncMock()
        keys = [APIKeyConfig(key="key-0")]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )
        key_hash = pool._hash_key("key-0")

        # Entry still in memory (not yet expired locally) but Redis says TTL=-2
        pool._memory_exhausted[key_hash] = time.time() + 9999

        mock_redis.call = AsyncMock(return_value=-2)

        pool.start_health_probe(interval_seconds=0.05)
        try:
            await asyncio.sleep(0.15)
            assert key_hash not in pool._memory_exhausted
        finally:
            pool.stop_health_probe()
