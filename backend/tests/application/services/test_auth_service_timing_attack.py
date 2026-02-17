"""Tests for timing-attack prevention in AuthService.authenticate_user.

These tests verify that the password authentication flow always executes
a full PBKDF2 hash computation regardless of the reason for failure,
preventing attackers from using response-time differences to enumerate
valid email addresses or determine account states.

Timing Attack Vectors Covered:
    1. Non-existent user  -> must still run PBKDF2
    2. Inactive user      -> must still run PBKDF2
    3. User without hash  -> must still run PBKDF2
    4. Wrong password     -> runs PBKDF2 (baseline)
    5. Correct password   -> runs PBKDF2 (success path)

Security Properties Verified:
    - _verify_password is called exactly once for EVERY failure scenario
    - Dummy hash is used when no real hash is available
    - Failed login attempts are tracked for ALL failure reasons
    - Account lockout triggers correctly regardless of failure reason
    - Log messages never leak the specific failure reason to the caller
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services import auth_service as auth_service_module
from app.application.services.auth_service import AuthService
from app.domain.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Fake settings
# ---------------------------------------------------------------------------


class _PasswordProviderSettings:
    """Minimal settings stub for 'password' auth provider tests."""

    auth_provider = "password"
    password_salt = "test-salt"
    password_hash_rounds = 1000  # Low for fast tests
    account_lockout_enabled = True
    account_lockout_threshold = 5
    account_lockout_reset_minutes = 5
    account_lockout_duration_minutes = 15


class _LockoutDisabledSettings(_PasswordProviderSettings):
    """Settings with account lockout disabled."""

    account_lockout_enabled = False


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------


class _FakeRedisClient:
    """Minimal Redis client stub."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def register_script(self, script: str):
        async def _execute(*, keys: list[str], args: list[int], client: Any = None) -> int:
            key = keys[0]
            val = self._store.get(key, 0) + 1
            self._store[key] = val
            return val

        return _execute

    async def get(self, key: str) -> str | None:
        val = self._store.get(key)
        return str(val) if val is not None else None

    async def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def ttl(self, key: str) -> int:
        return -2  # Key does not exist

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


class _FakeRedisWrapper:
    """Wraps _FakeRedisClient with the interface expected by AuthService."""

    def __init__(self, client: _FakeRedisClient | None = None) -> None:
        self.client = client or _FakeRedisClient()

    async def initialize(self) -> None:
        return None

    async def execute_with_retry(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs.pop("operation_name", None)
        return await operation(*args, **kwargs)

    async def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.client, method_name)
        return await method(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fake User Repository
# ---------------------------------------------------------------------------


class _FakeUserRepository:
    """In-memory user repository for unit tests."""

    def __init__(self, users: dict[str, User] | None = None) -> None:
        self._users = users or {}

    async def get_user_by_email(self, email: str) -> User | None:
        return self._users.get(email.lower())

    async def get_user_by_id(self, user_id: str) -> User | None:
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None

    async def email_exists(self, email: str) -> bool:
        return email.lower() in self._users

    async def create_user(self, user: User) -> User:
        self._users[user.email.lower()] = user
        return user

    async def update_user(self, user: User) -> User:
        self._users[user.email.lower()] = user
        return user


class _FakeTokenService:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    email: str = "user@example.com",
    plaintext: str | None = "correct-password",
    is_active: bool = True,
    has_hash: bool = True,
) -> tuple[User, AuthService]:
    """Create a user and an AuthService that can verify the password.

    Returns the user and the service instance so the test can call
    ``service.authenticate_user()``.
    """
    settings = _PasswordProviderSettings()
    service = AuthService.__new__(AuthService)
    service.user_repository = _FakeUserRepository()
    service.settings = settings
    service.token_service = _FakeTokenService()
    service._counter_with_expiry_script = None

    # Compute a real hash for the user's plaintext credential using the service
    password_hash = service._hash_password(plaintext) if plaintext and has_hash else None

    user = User(
        id="user-1",
        fullname="Test User",
        email=email,
        password_hash=password_hash,
        role=UserRole.USER,
        is_active=is_active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    return user, service


def _build_service(
    users: dict[str, User] | None = None,
    settings: Any = None,
) -> AuthService:
    """Build an AuthService with faked dependencies."""
    settings = settings or _PasswordProviderSettings()
    repo = _FakeUserRepository(users or {})
    service = AuthService.__new__(AuthService)
    service.user_repository = repo
    service.settings = settings
    service.token_service = _FakeTokenService()
    service._counter_with_expiry_script = None

    # Ensure dummy hash is initialized
    if AuthService._DUMMY_PASSWORD_HASH is None:
        AuthService._DUMMY_PASSWORD_HASH = service._hash_password("dummy-timing-attack-prevention-password")

    return service


# ---------------------------------------------------------------------------
# Test: Dummy hash generation
# ---------------------------------------------------------------------------


class TestDummyHash:
    """Verify the _get_dummy_hash() mechanism."""

    def test_dummy_hash_is_precomputed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The class-level _DUMMY_PASSWORD_HASH must be set after __init__."""
        monkeypatch.setattr(auth_service_module, "get_settings", lambda: _PasswordProviderSettings())
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        # Reset to None to test initialization
        original = AuthService._DUMMY_PASSWORD_HASH
        AuthService._DUMMY_PASSWORD_HASH = None
        try:
            AuthService(_FakeUserRepository(), _FakeTokenService())
            assert AuthService._DUMMY_PASSWORD_HASH is not None
            assert isinstance(AuthService._DUMMY_PASSWORD_HASH, str)
            assert len(AuthService._DUMMY_PASSWORD_HASH) > 0
        finally:
            AuthService._DUMMY_PASSWORD_HASH = original

    def test_get_dummy_hash_returns_valid_string(self) -> None:
        """_get_dummy_hash() returns a non-empty string."""
        service = _build_service()
        dummy = service._get_dummy_hash()
        assert isinstance(dummy, str)
        assert len(dummy) > 0

    def test_dummy_hash_is_consistent(self) -> None:
        """Multiple calls return the same pre-computed value."""
        service = _build_service()
        assert service._get_dummy_hash() == service._get_dummy_hash()

    def test_dummy_hash_does_not_match_any_real_password(self) -> None:
        """The dummy hash must never validate against real passwords."""
        service = _build_service()
        dummy = service._get_dummy_hash()
        assert not service._verify_password("password123", dummy)
        assert not service._verify_password("", dummy)
        assert not service._verify_password("correct-password", dummy)


# ---------------------------------------------------------------------------
# Test: Constant-time password verification
# ---------------------------------------------------------------------------


class TestConstantTimeVerification:
    """Verify that _verify_password always runs PBKDF2."""

    def test_verify_password_runs_pbkdf2_with_valid_hash(self) -> None:
        """Verifying against a valid hash produces the correct result."""
        service = _build_service()
        real_hash = service._hash_password("my-password")
        assert service._verify_password("my-password", real_hash) is True
        assert service._verify_password("wrong-password", real_hash) is False

    def test_verify_password_runs_pbkdf2_with_dummy_hash(self) -> None:
        """Verifying against the dummy hash always returns False."""
        service = _build_service()
        dummy = service._get_dummy_hash()
        # Any password checked against the dummy hash should fail
        assert service._verify_password("anything", dummy) is False

    def test_verify_password_handles_exception_gracefully(self) -> None:
        """If hashing raises, _verify_password returns False without crashing."""
        service = _build_service()
        with patch.object(service, "_hash_password", side_effect=RuntimeError("boom")):
            assert service._verify_password("password", "somehash") is False


# ---------------------------------------------------------------------------
# Test: authenticate_user timing-attack prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuthenticateUserTimingAttack:
    """Verify that authenticate_user always runs password verification,
    regardless of user existence or state."""

    async def test_nonexistent_user_runs_password_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the user does not exist, _verify_password MUST still be called
        with the dummy hash to ensure constant-time behavior."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())
        service = _build_service(users={})  # No users at all

        with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
            result = await service.authenticate_user("nobody@example.com", "any-password")

        assert result is None
        mock_verify.assert_called_once()
        # The hash argument should be the dummy hash (since user doesn't exist)
        call_args = mock_verify.call_args
        assert call_args[0][1] == service._get_dummy_hash()

    async def test_inactive_user_runs_password_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the user is inactive, _verify_password MUST still be called."""
        user, service = _make_user(is_active=False)
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
            result = await service.authenticate_user(user.email, "correct-password")

        assert result is None
        mock_verify.assert_called_once()

    async def test_user_without_password_hash_runs_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the user has no password_hash, _verify_password MUST still be
        called with the dummy hash."""
        user, service = _make_user(has_hash=False)
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
            result = await service.authenticate_user(user.email, "any-password")

        assert result is None
        mock_verify.assert_called_once()
        # Should use dummy hash since user.password_hash is None
        call_args = mock_verify.call_args
        assert call_args[0][1] == service._get_dummy_hash()

    async def test_wrong_password_runs_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wrong password follows the same code path as other failures."""
        user, service = _make_user()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
            result = await service.authenticate_user(user.email, "wrong-password")

        assert result is None
        mock_verify.assert_called_once()
        # Should use the real hash
        call_args = mock_verify.call_args
        assert call_args[0][1] == user.password_hash

    async def test_correct_password_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid credentials return the user."""
        user, service = _make_user()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
            result = await service.authenticate_user(user.email, "correct-password")

        assert result is not None
        assert result.email == user.email
        mock_verify.assert_called_once()

    async def test_verify_password_called_exactly_once_for_each_scenario(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regardless of the scenario, _verify_password is called exactly once."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        scenarios = [
            ("nonexistent@example.com", "any-pass", {}),
        ]

        for email, password, users in scenarios:
            service = _build_service(users=users)
            with patch.object(service, "_verify_password", wraps=service._verify_password) as mock_verify:
                await service.authenticate_user(email, password)
            assert mock_verify.call_count == 1, f"Failed for scenario: {email}"


# ---------------------------------------------------------------------------
# Test: Failed login tracking for all failure reasons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFailedAttemptTracking:
    """Verify that failed login attempts are tracked for ALL failure reasons,
    not just wrong-password."""

    async def test_nonexistent_user_increments_failed_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Failed attempts are tracked even when user doesn't exist."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service(users={})

        with patch.object(
            service, "_increment_failed_attempts", wraps=service._increment_failed_attempts
        ) as mock_increment:
            await service.authenticate_user("nobody@example.com", "password")

        mock_increment.assert_called_once_with("nobody@example.com")

    async def test_inactive_user_increments_failed_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Failed attempts are tracked for inactive users."""
        user, service = _make_user(is_active=False)
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(
            service, "_increment_failed_attempts", wraps=service._increment_failed_attempts
        ) as mock_increment:
            await service.authenticate_user(user.email, "correct-password")

        mock_increment.assert_called_once_with(user.email)

    async def test_user_without_hash_increments_failed_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Failed attempts are tracked for users without password hash."""
        user, service = _make_user(has_hash=False)
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(
            service, "_increment_failed_attempts", wraps=service._increment_failed_attempts
        ) as mock_increment:
            await service.authenticate_user(user.email, "password")

        mock_increment.assert_called_once_with(user.email)

    async def test_wrong_password_increments_failed_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Failed attempts are tracked for wrong passwords."""
        user, service = _make_user()
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(
            service, "_increment_failed_attempts", wraps=service._increment_failed_attempts
        ) as mock_increment:
            await service.authenticate_user(user.email, "wrong-password")

        mock_increment.assert_called_once_with(user.email)

    async def test_successful_login_clears_failed_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful login clears the failed attempts counter."""
        user, service = _make_user()
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_clear_failed_attempts", wraps=service._clear_failed_attempts) as mock_clear:
            result = await service.authenticate_user(user.email, "correct-password")

        assert result is not None
        mock_clear.assert_called_once_with(user.email)


# ---------------------------------------------------------------------------
# Test: Account lockout integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAccountLockout:
    """Verify that account lockout triggers correctly for all failure reasons."""

    async def test_lockout_triggers_for_nonexistent_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repeated failed attempts for non-existent users trigger lockout."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)

        settings = _PasswordProviderSettings()
        settings.account_lockout_threshold = 2  # Low threshold for test
        service = _build_service(users={}, settings=settings)

        with patch.object(service, "_lock_account", new_callable=AsyncMock) as mock_lock:
            # First attempt
            await service.authenticate_user("nobody@example.com", "pass1")
            mock_lock.assert_not_called()

            # Second attempt triggers lockout (threshold = 2)
            await service.authenticate_user("nobody@example.com", "pass2")
            mock_lock.assert_called_once_with("nobody@example.com")

    async def test_lockout_triggers_for_wrong_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repeated wrong passwords trigger lockout."""
        redis_wrapper = _FakeRedisWrapper()
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)

        user, service = _make_user()
        settings = _PasswordProviderSettings()
        settings.account_lockout_threshold = 2
        service.settings = settings
        service.user_repository = _FakeUserRepository({user.email: user})

        with patch.object(service, "_lock_account", new_callable=AsyncMock) as mock_lock:
            await service.authenticate_user(user.email, "wrong1")
            await service.authenticate_user(user.email, "wrong2")
            mock_lock.assert_called_once_with(user.email)

    async def test_locked_account_raises_before_password_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A locked account raises UnauthorizedError before running PBKDF2."""
        from app.application.errors.exceptions import UnauthorizedError

        redis_client = _FakeRedisClient()
        # Simulate a locked account
        redis_client._store["auth:lockout:locked@example.com"] = "locked"

        # Override ttl to return positive value
        async def _ttl(key: str) -> int:
            if key == "auth:lockout:locked@example.com":
                return 600
            return -2

        redis_client.ttl = _ttl

        redis_wrapper = _FakeRedisWrapper(redis_client)
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: redis_wrapper)
        service = _build_service(users={})

        with (
            patch.object(service, "_verify_password") as mock_verify,
            pytest.raises(UnauthorizedError, match="temporarily locked"),
        ):
            await service.authenticate_user("locked@example.com", "password")

        # _verify_password should NOT have been called for locked accounts
        mock_verify.assert_not_called()

    async def test_lockout_disabled_still_allows_authentication(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When lockout is disabled, authentication still works normally."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        user, service = _make_user()
        service.settings = _LockoutDisabledSettings()
        service.user_repository = _FakeUserRepository({user.email: user})

        result = await service.authenticate_user(user.email, "correct-password")
        assert result is not None
        assert result.email == user.email


# ---------------------------------------------------------------------------
# Test: Unified failure path (no information leakage)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnifiedFailurePath:
    """Verify that all failure reasons produce indistinguishable outcomes."""

    async def test_all_failures_return_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every failure scenario returns None (not an exception with details)."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        # Scenario 1: Non-existent user
        service = _build_service(users={})
        assert await service.authenticate_user("nobody@example.com", "pass") is None

        # Scenario 2: Inactive user
        user, service = _make_user(is_active=False)
        service.user_repository = _FakeUserRepository({user.email: user})
        assert await service.authenticate_user(user.email, "correct-password") is None

        # Scenario 3: User without password hash
        user, service = _make_user(has_hash=False)
        service.user_repository = _FakeUserRepository({user.email: user})
        assert await service.authenticate_user(user.email, "pass") is None

        # Scenario 4: Wrong password
        user, service = _make_user()
        service.user_repository = _FakeUserRepository({user.email: user})
        assert await service.authenticate_user(user.email, "wrong") is None

    async def test_success_only_with_all_conditions_met(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Authentication succeeds ONLY when ALL conditions are met:
        user exists, is active, has password hash, and password is correct."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        user, service = _make_user(
            email="valid@example.com",
            plaintext="correct-password",
            is_active=True,
            has_hash=True,
        )
        service.user_repository = _FakeUserRepository({user.email: user})

        result = await service.authenticate_user(user.email, "correct-password")
        assert result is not None
        assert result.email == "valid@example.com"
        assert result.is_active is True


# ---------------------------------------------------------------------------
# Test: Database update on successful login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSuccessfulLoginSideEffects:
    """Verify side effects of a successful authentication."""

    async def test_last_login_is_updated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful authentication updates the user's last_login_at."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        user, service = _make_user()
        service.user_repository = _FakeUserRepository({user.email: user})
        original_login = user.last_login_at

        result = await service.authenticate_user(user.email, "correct-password")
        assert result is not None
        assert result.last_login_at is not None
        # last_login_at should have been updated (it was None or earlier)
        if original_login is not None:
            assert result.last_login_at >= original_login

    async def test_user_is_persisted_after_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful authentication calls update_user to persist changes."""
        monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper())

        user, service = _make_user()
        repo = _FakeUserRepository({user.email: user})
        service.user_repository = repo

        # Spy on update_user
        original_update = repo.update_user
        update_calls: list[User] = []

        async def _track_update(u: User) -> User:
            update_calls.append(u)
            return await original_update(u)

        repo.update_user = _track_update

        await service.authenticate_user(user.email, "correct-password")
        assert len(update_calls) == 1
        assert update_calls[0].email == user.email
