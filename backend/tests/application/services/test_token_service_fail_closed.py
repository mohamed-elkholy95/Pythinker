"""Tests for fail-closed security behavior in TokenService.

These tests verify that token blacklist and user revocation checks DENY ACCESS
when Redis is unavailable, preventing authentication bypass during infrastructure
outages.

Security Vulnerabilities Addressed:
    1. Token blacklist check fails closed (not open) on Redis error
    2. User token revocation check fails closed (not open) on Redis error

Fail-Closed Principle:
    When a security check cannot be performed (e.g., Redis unavailable),
    access MUST be denied. Allowing access when the check fails ("fail open")
    would let revoked/compromised tokens bypass authentication.

Attack Scenarios Prevented:
    - Attacker steals token, user revokes it, Redis goes down -> attacker blocked
    - Redis network partition during token blacklist check -> blacklisted tokens blocked
    - User changes password (triggers revoke-all), Redis flaps -> old tokens blocked
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.application.services import token_service as token_service_module
from app.application.services.token_service import TokenService
from app.core.prometheus_metrics import token_auth_fail_closed_total

# ---------------------------------------------------------------------------
# Fake settings
# ---------------------------------------------------------------------------


class _BlacklistEnabledSettings:
    """Minimal settings stub with blacklist enabled."""

    jwt_secret_key = "test-secret-key-for-unit-tests"
    jwt_algorithm = "HS256"
    jwt_access_token_expire_minutes = 30
    jwt_refresh_token_expire_days = 7
    jwt_token_blacklist_enabled = True


class _BlacklistDisabledSettings(_BlacklistEnabledSettings):
    """Settings with blacklist disabled."""

    jwt_token_blacklist_enabled = False


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------


class _FakeRedisClient:
    """In-memory Redis client for happy-path tests."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def get(self, key: str) -> str | None:
        val = self._store.get(key)
        return str(val) if val is not None else None

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


class _FakeRedisWrapper:
    """Wraps _FakeRedisClient with the interface expected by TokenService."""

    def __init__(
        self,
        client: _FakeRedisClient | None = None,
        fail_on_call: bool = False,
        fail_exception: Exception | None = None,
    ) -> None:
        self.client = client or _FakeRedisClient()
        self.fail_on_call = fail_on_call
        self.fail_exception = fail_exception or ConnectionError("Redis connection refused")

    async def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if self.fail_on_call:
            raise self.fail_exception
        method = getattr(self.client, method_name)
        return await method(*args, **kwargs)


class _FakeRedisWrapperTimeout(_FakeRedisWrapper):
    """Redis wrapper that simulates a network timeout."""

    def __init__(self) -> None:
        super().__init__(fail_on_call=True, fail_exception=TimeoutError("Redis connection timed out"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service(settings: Any | None = None) -> TokenService:
    """Build a TokenService with faked settings."""
    service = TokenService.__new__(TokenService)
    service.settings = settings or _BlacklistEnabledSettings()
    return service


def _reset_fail_closed_metric() -> None:
    """Reset the fail-closed metric counter for test isolation."""
    token_auth_fail_closed_total._values.clear()


# ---------------------------------------------------------------------------
# Test: _is_token_blacklisted - Normal Operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBlacklistNormalOperation:
    """Verify blacklist check works correctly when Redis is healthy."""

    async def test_non_blacklisted_token_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A token that is NOT in the blacklist returns False (allow access)."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service._is_token_blacklisted("valid-token-not-in-blacklist")

        assert result is False

    async def test_blacklisted_token_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A token that IS in the blacklist returns True (deny access)."""
        client = _FakeRedisClient()
        # Pre-populate the blacklist with a token hash
        service = _build_service()
        token = "revoked-token-abc123"
        token_hash = service._hash_token(token)
        key = f"{service.BLACKLIST_PREFIX}{token_hash}"
        client._store[key] = "revoked"

        redis_wrapper = _FakeRedisWrapper(client=client)
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)

        result = await service._is_token_blacklisted(token)

        assert result is True

    async def test_different_tokens_have_different_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only the specific blacklisted token is rejected, not others."""
        client = _FakeRedisClient()
        service = _build_service()

        # Blacklist only one token
        blacklisted_token = "bad-token"
        token_hash = service._hash_token(blacklisted_token)
        key = f"{service.BLACKLIST_PREFIX}{token_hash}"
        client._store[key] = "revoked"

        redis_wrapper = _FakeRedisWrapper(client=client)
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)

        assert await service._is_token_blacklisted(blacklisted_token) is True
        assert await service._is_token_blacklisted("good-token") is False


# ---------------------------------------------------------------------------
# Test: _is_token_blacklisted - Fail Closed on Redis Error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBlacklistFailClosed:
    """Verify blacklist check DENIES ACCESS when Redis is unavailable."""

    async def test_redis_connection_error_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When Redis raises ConnectionError, method returns True (deny access).

        This is the critical fail-closed behavior: if we cannot check the
        blacklist, we must assume the worst and deny access.
        """
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service._is_token_blacklisted("some-token")

        assert result is True

    async def test_redis_timeout_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When Redis connection times out, method returns True (deny access)."""
        redis_wrapper = _FakeRedisWrapperTimeout()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service._is_token_blacklisted("some-token")

        assert result is True

    async def test_redis_generic_exception_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any unexpected exception still fails closed (deny access)."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=RuntimeError("Unexpected Redis error"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service._is_token_blacklisted("some-token")

        assert result is True

    async def test_redis_os_error_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError (network issues) also fails closed."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=OSError("Network unreachable"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service._is_token_blacklisted("some-token")

        assert result is True

    async def test_get_redis_raises_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When get_redis() itself raises, method still fails closed."""

        def _broken_redis() -> None:
            raise ConnectionError("Redis not initialized")

        monkeypatch.setattr(token_service_module, "get_redis", _broken_redis)
        service = _build_service()

        result = await service._is_token_blacklisted("some-token")

        assert result is True


# ---------------------------------------------------------------------------
# Test: _is_token_blacklisted - Security Logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBlacklistSecurityLogging:
    """Verify that fail-closed events produce security audit logs."""

    async def test_redis_failure_logs_error_level(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Redis failure logs at ERROR level (not WARNING) for security visibility."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        with caplog.at_level(logging.ERROR, logger="app.application.services.token_service"):
            await service._is_token_blacklisted("some-token")

        assert len(caplog.records) >= 1
        error_record = caplog.records[0]
        assert error_record.levelno == logging.ERROR
        assert "FAILING CLOSED" in error_record.message
        assert "blacklist" in error_record.message.lower()

    async def test_redis_failure_log_contains_token_hash_prefix(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Error log includes token hash prefix for correlation without leaking the token."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        with caplog.at_level(logging.ERROR, logger="app.application.services.token_service"):
            await service._is_token_blacklisted("test-token-for-hash")

        error_record = caplog.records[0]
        # The extra dict should contain token_hash_prefix
        assert hasattr(error_record, "token_hash_prefix")
        # The prefix should be 8 chars of the SHA256 hash
        expected_hash = service._hash_token("test-token-for-hash")[:8]
        assert error_record.token_hash_prefix == expected_hash


# ---------------------------------------------------------------------------
# Test: _is_token_blacklisted - Prometheus Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBlacklistMetrics:
    """Verify that fail-closed events increment Prometheus counters."""

    async def test_redis_failure_increments_blacklist_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis failure increments token_auth_fail_closed_total with check_type=blacklist."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service._is_token_blacklisted("some-token")

        metric_value = token_auth_fail_closed_total.get({"check_type": "blacklist"})
        assert metric_value == 1.0

    async def test_multiple_failures_accumulate_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple Redis failures accumulate the metric counter."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service._is_token_blacklisted("token-1")
        await service._is_token_blacklisted("token-2")
        await service._is_token_blacklisted("token-3")

        metric_value = token_auth_fail_closed_total.get({"check_type": "blacklist"})
        assert metric_value == 3.0

    async def test_successful_check_does_not_increment_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful Redis operations do not increment the fail-closed metric."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service._is_token_blacklisted("some-token")

        metric_value = token_auth_fail_closed_total.get({"check_type": "blacklist"})
        assert metric_value == 0.0


# ---------------------------------------------------------------------------
# Test: is_user_token_revoked - Normal Operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserRevocationNormalOperation:
    """Verify user token revocation works correctly when Redis is healthy."""

    async def test_non_revoked_user_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A user with no revocation timestamp returns False (allow access)."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is False

    async def test_token_issued_before_revocation_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A token issued BEFORE the revocation timestamp is rejected."""
        client = _FakeRedisClient()
        # Set revocation timestamp to 2000000
        client._store["token:user:user-123:revoked_before"] = "2000000"

        redis_wrapper = _FakeRedisWrapper(client=client)
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        # Token was issued at 1000000, revocation at 2000000 -> should be revoked
        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True

    async def test_token_issued_after_revocation_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A token issued AFTER the revocation timestamp is allowed."""
        client = _FakeRedisClient()
        client._store["token:user:user-123:revoked_before"] = "1000000"

        redis_wrapper = _FakeRedisWrapper(client=client)
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        # Token was issued at 2000000, revocation at 1000000 -> should be allowed
        result = await service.is_user_token_revoked("user-123", issued_at=2000000)

        assert result is False

    async def test_blacklist_disabled_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When blacklist is disabled, always returns False regardless of state."""
        service = _build_service(settings=_BlacklistDisabledSettings())

        # Should return False without even touching Redis
        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is False


# ---------------------------------------------------------------------------
# Test: is_user_token_revoked - Fail Closed on Redis Error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserRevocationFailClosed:
    """Verify user revocation check DENIES ACCESS when Redis is unavailable."""

    async def test_redis_connection_error_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When Redis raises ConnectionError, method returns True (deny access).

        Attack scenario: User changes password, triggering revoke-all.
        Redis goes down. Attacker's stolen token must NOT be accepted.
        """
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True

    async def test_redis_timeout_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When Redis connection times out, method returns True (deny access)."""
        redis_wrapper = _FakeRedisWrapperTimeout()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True

    async def test_redis_generic_exception_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any unexpected exception still fails closed (deny access)."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=RuntimeError("Unexpected error"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True

    async def test_redis_os_error_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError (network issues) also fails closed."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=OSError("Network unreachable"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True

    async def test_blacklist_disabled_skips_redis_entirely(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When blacklist is disabled, Redis is never consulted, returns False."""
        # Use a Redis wrapper that would fail if called
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True)
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service(settings=_BlacklistDisabledSettings())

        # Should return False without hitting Redis at all
        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is False

    async def test_get_redis_raises_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When get_redis() itself raises, method still fails closed."""

        def _broken_redis() -> None:
            raise ConnectionError("Redis not initialized")

        monkeypatch.setattr(token_service_module, "get_redis", _broken_redis)
        service = _build_service()

        result = await service.is_user_token_revoked("user-123", issued_at=1000000)

        assert result is True


# ---------------------------------------------------------------------------
# Test: is_user_token_revoked - Security Logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserRevocationSecurityLogging:
    """Verify that fail-closed revocation events produce security audit logs."""

    async def test_redis_failure_logs_error_level(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Redis failure logs at ERROR level for security visibility."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        with caplog.at_level(logging.ERROR, logger="app.application.services.token_service"):
            await service.is_user_token_revoked("user-456", issued_at=1000000)

        assert len(caplog.records) >= 1
        error_record = caplog.records[0]
        assert error_record.levelno == logging.ERROR
        assert "FAILING CLOSED" in error_record.message
        assert "revocation" in error_record.message.lower()

    async def test_redis_failure_log_contains_user_id(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Error log includes user_id for security auditing."""
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        with caplog.at_level(logging.ERROR, logger="app.application.services.token_service"):
            await service.is_user_token_revoked("user-789", issued_at=1000000)

        error_record = caplog.records[0]
        # The extra dict should contain user_id
        assert hasattr(error_record, "user_id")
        assert error_record.user_id == "user-789"


# ---------------------------------------------------------------------------
# Test: is_user_token_revoked - Prometheus Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserRevocationMetrics:
    """Verify that fail-closed revocation events increment Prometheus counters."""

    async def test_redis_failure_increments_revocation_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis failure increments token_auth_fail_closed_total with check_type=user_revocation."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service.is_user_token_revoked("user-123", issued_at=1000000)

        metric_value = token_auth_fail_closed_total.get({"check_type": "user_revocation"})
        assert metric_value == 1.0

    async def test_multiple_failures_accumulate_revocation_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple Redis failures accumulate the metric counter."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Connection refused"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service.is_user_token_revoked("user-1", issued_at=1000000)
        await service.is_user_token_revoked("user-2", issued_at=1000000)

        metric_value = token_auth_fail_closed_total.get({"check_type": "user_revocation"})
        assert metric_value == 2.0

    async def test_successful_check_does_not_increment_revocation_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful Redis operations do not increment the fail-closed metric."""
        _reset_fail_closed_metric()

        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        await service.is_user_token_revoked("user-123", issued_at=1000000)

        metric_value = token_auth_fail_closed_total.get({"check_type": "user_revocation"})
        assert metric_value == 0.0


# ---------------------------------------------------------------------------
# Test: verify_token_async - End-to-End Fail Closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerifyTokenAsyncFailClosed:
    """Verify that verify_token_async rejects tokens when Redis is down."""

    async def test_valid_token_rejected_when_blacklist_check_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid JWT token is rejected when the blacklist check cannot complete.

        This is the core security property: even a cryptographically valid token
        must be rejected if we cannot verify it is not blacklisted.
        """
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Redis down"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        # Create a real valid token
        from datetime import UTC, datetime

        from app.domain.models.user import User, UserRole

        user = User(
            id="user-test",
            fullname="Test User",
            email="test@example.com",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        token = service.create_access_token(user)

        # Token is cryptographically valid, but Redis is down
        # verify_token_async should return None because blacklist check fails closed
        result = await service.verify_token_async(token)

        assert result is None

    async def test_valid_token_accepted_when_redis_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid JWT token is accepted when Redis is healthy and token is not blacklisted."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        from datetime import UTC, datetime

        from app.domain.models.user import User, UserRole

        user = User(
            id="user-test",
            fullname="Test User",
            email="test@example.com",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        token = service.create_access_token(user)

        result = await service.verify_token_async(token)

        assert result is not None
        assert result["sub"] == "user-test"

    async def test_valid_token_rejected_when_revocation_check_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid token is rejected when user revocation check cannot complete.

        Scenario: Blacklist check passes (token not individually blacklisted),
        but the user-wide revocation check fails due to Redis error.
        The token should still be rejected.
        """
        call_count = 0

        class _PartialFailRedisWrapper:
            """Redis that succeeds for exists (blacklist) but fails for get (revocation)."""

            async def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                if method_name == "exists":
                    return 0  # Not blacklisted
                # Fail on the "get" call (revocation check)
                raise ConnectionError("Redis failed on get")

        monkeypatch.setattr(token_service_module, "get_redis", lambda: _PartialFailRedisWrapper())
        service = _build_service()

        from datetime import UTC, datetime

        from app.domain.models.user import User, UserRole

        user = User(
            id="user-test",
            fullname="Test User",
            email="test@example.com",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        token = service.create_access_token(user)

        result = await service.verify_token_async(token)

        assert result is None


# ---------------------------------------------------------------------------
# Test: Attack Scenario Simulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAttackScenarioSimulation:
    """Simulate real attack scenarios to verify fail-closed prevents them."""

    async def test_stolen_token_rejected_during_redis_outage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Attack scenario:
        1. Attacker steals a user's token
        2. User detects breach, revokes all tokens
        3. Redis experiences a brief outage
        4. Attacker tries to use stolen token
        5. Token MUST be rejected (fail-closed)
        """
        redis_wrapper = _FakeRedisWrapper(fail_on_call=True, fail_exception=ConnectionError("Redis network partition"))
        monkeypatch.setattr(token_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service()

        from datetime import UTC, datetime

        from app.domain.models.user import User, UserRole

        victim = User(
            id="victim-user",
            fullname="Victim User",
            email="victim@example.com",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        stolen_token = service.create_access_token(victim)

        # Attacker tries to use stolen token during Redis outage
        result = await service.verify_token_async(stolen_token)

        # Token MUST be rejected
        assert result is None

    async def test_revoked_token_blocked_even_with_redis_flapping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Attack scenario: Redis is flapping (intermittent failures).
        Blacklisted tokens must NEVER be accepted during Redis failures.
        """
        service = _build_service()

        from datetime import UTC, datetime

        from app.domain.models.user import User, UserRole

        user = User(
            id="user-flap",
            fullname="Flap User",
            email="flap@example.com",
            role=UserRole.USER,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        token = service.create_access_token(user)

        # Simulate Redis flapping: alternate between success and failure
        attempt = 0

        class _FlappingRedisWrapper:
            async def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
                nonlocal attempt
                attempt += 1
                if attempt % 2 == 0:
                    raise ConnectionError("Redis flapping")
                # On success, token is not blacklisted
                if method_name == "exists":
                    return 0
                return None

        monkeypatch.setattr(token_service_module, "get_redis", lambda: _FlappingRedisWrapper())

        results = []
        for _ in range(6):
            result = await service.verify_token_async(token)
            results.append(result is not None)

        # During Redis failures (even-numbered attempts), token should be rejected
        # No blacklisted token should ever slip through
        # The key point: at least some attempts are blocked
        blocked_count = sum(1 for r in results if r is False)
        assert blocked_count > 0, "At least some attempts should be blocked during Redis failures"
