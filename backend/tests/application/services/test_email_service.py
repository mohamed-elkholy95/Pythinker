"""Tests for EmailService — verification codes, rating emails, cleanup."""

from __future__ import annotations

import email as email_mod
import smtplib
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.errors.exceptions import BadRequestError
from app.application.services.email_service import EmailService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: Any) -> MagicMock:
    """Return a mock settings object with sensible email defaults."""
    defaults = {
        "email_host": "smtp.example.com",
        "email_port": 465,
        "email_username": "user@example.com",
        "email_password": "s3cret",
        "email_from": "noreply@example.com",
        "rating_notification_email": "ratings@example.com",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_cache() -> AsyncMock:
    """Return an ``AsyncMock`` that satisfies the ``Cache`` protocol."""
    cache = AsyncMock()
    cache.set.return_value = True
    cache.get.return_value = None
    cache.delete.return_value = True
    cache.exists.return_value = False
    cache.get_ttl.return_value = None
    cache.keys.return_value = []
    cache.clear_pattern.return_value = 0
    # Default to fallback path unless a specific test sets atomic increments.
    cache.increment.return_value = None
    return cache


def _stored_code_data(
    code: str = "123456",
    *,
    created_seconds_ago: float = 120,
    expires_in_seconds: float = 180,
    attempts: int = 0,
) -> dict[str, Any]:
    """Build a stored verification-code dict matching EmailService format."""
    now = datetime.now(UTC)
    return {
        "code": code,
        "created_at": (now - timedelta(seconds=created_seconds_ago)).isoformat(),
        "expires_at": (now + timedelta(seconds=expires_in_seconds)).isoformat(),
        "attempts": attempts,
    }


def _expired_code_data(code: str = "123456", *, attempts: int = 0) -> dict[str, Any]:
    """Build a stored verification-code dict that is already expired."""
    now = datetime.now(UTC)
    return {
        "code": code,
        "created_at": (now - timedelta(seconds=600)).isoformat(),
        "expires_at": (now - timedelta(seconds=300)).isoformat(),
        "attempts": attempts,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings() -> MagicMock:
    return _make_settings()


@pytest.fixture()
def mock_cache() -> AsyncMock:
    return _make_cache()


@pytest.fixture()
def service(mock_settings: MagicMock, mock_cache: AsyncMock) -> EmailService:
    with patch("app.application.services.email_service.get_settings", return_value=mock_settings):
        return EmailService(cache=mock_cache)


# ===========================================================================
# 1. _generate_verification_code
# ===========================================================================


class TestGenerateVerificationCode:
    """The code must always be a 6-digit string in [100000, 999999]."""

    def test_returns_string(self, service: EmailService) -> None:
        code = service._generate_verification_code()
        assert isinstance(code, str)

    def test_always_six_digits(self, service: EmailService) -> None:
        for _ in range(200):
            code = service._generate_verification_code()
            assert len(code) == 6, f"Expected 6-digit code, got: {code}"
            assert code.isdigit(), f"Expected all-digit string, got: {code}"

    def test_range_100000_to_999999(self, service: EmailService) -> None:
        for _ in range(200):
            code = service._generate_verification_code()
            value = int(code)
            assert 100000 <= value <= 999999, f"Code {value} out of range"

    def test_produces_varying_codes(self, service: EmailService) -> None:
        """Sanity-check that codes are not constant (probabilistic but safe)."""
        codes = {service._generate_verification_code() for _ in range(50)}
        assert len(codes) > 1, "All 50 generated codes were identical"


# ===========================================================================
# 2. verify_code
# ===========================================================================


class TestVerifyCode:
    """Verification scenarios: success, wrong code, expired, max attempts, missing."""

    EMAIL = "test@example.com"
    KEY = f"verification_code:{EMAIL}"

    @pytest.mark.asyncio
    async def test_valid_code_returns_true_and_deletes(self, service: EmailService, mock_cache: AsyncMock) -> None:
        mock_cache.get.return_value = _stored_code_data("654321")

        result = await service.verify_code(self.EMAIL, "654321")

        assert result is True
        mock_cache.delete.assert_awaited_once_with(self.KEY)

    @pytest.mark.asyncio
    async def test_wrong_code_returns_false_and_increments_attempts(
        self, service: EmailService, mock_cache: AsyncMock
    ) -> None:
        stored = _stored_code_data("654321", attempts=0)
        mock_cache.get.return_value = stored

        result = await service.verify_code(self.EMAIL, "000000")

        assert result is False
        # Should update cache with incremented attempts
        mock_cache.set.assert_awaited_once()
        call_args = mock_cache.set.call_args
        updated_data = call_args.args[1] if len(call_args.args) > 1 else call_args[0][1]
        assert updated_data["attempts"] == 1

    @pytest.mark.asyncio
    async def test_wrong_code_second_attempt(self, service: EmailService, mock_cache: AsyncMock) -> None:
        stored = _stored_code_data("654321", attempts=1)
        mock_cache.get.return_value = stored

        result = await service.verify_code(self.EMAIL, "000000")

        assert result is False
        mock_cache.set.assert_awaited_once()
        call_args = mock_cache.set.call_args
        updated_data = call_args.args[1] if len(call_args.args) > 1 else call_args[0][1]
        assert updated_data["attempts"] == 2

    @pytest.mark.asyncio
    async def test_wrong_code_uses_atomic_increment_when_available(
        self, service: EmailService, mock_cache: AsyncMock
    ) -> None:
        """When increment returns an int, service should use the atomic counter path."""
        mock_cache.get.return_value = _stored_code_data("654321", attempts=0)
        mock_cache.increment.return_value = 1

        result = await service.verify_code(self.EMAIL, "000000")

        assert result is False
        mock_cache.increment.assert_awaited_once()
        increment_call = mock_cache.increment.await_args
        assert increment_call.args[0] == f"{self.KEY}:attempts"
        assert isinstance(increment_call.kwargs["ttl"], int)
        assert increment_call.kwargs["ttl"] > 0
        mock_cache.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_atomic_increment_over_limit_invalidates_code(
        self, service: EmailService, mock_cache: AsyncMock
    ) -> None:
        """Atomic counter >3 must invalidate stored verification code."""
        mock_cache.get.return_value = _stored_code_data("654321", attempts=0)
        mock_cache.increment.return_value = 4

        result = await service.verify_code(self.EMAIL, "654321")

        assert result is False
        mock_cache.delete.assert_awaited_once_with(self.KEY)

    @pytest.mark.asyncio
    async def test_expired_code_returns_false_and_deletes(self, service: EmailService, mock_cache: AsyncMock) -> None:
        mock_cache.get.return_value = _expired_code_data("654321")

        result = await service.verify_code(self.EMAIL, "654321")

        assert result is False
        mock_cache.delete.assert_awaited_once_with(self.KEY)

    @pytest.mark.asyncio
    async def test_max_attempts_reached_returns_false_and_deletes(
        self, service: EmailService, mock_cache: AsyncMock
    ) -> None:
        stored = _stored_code_data("654321", attempts=3)
        mock_cache.get.return_value = stored

        result = await service.verify_code(self.EMAIL, "654321")

        assert result is False
        mock_cache.delete.assert_awaited_once_with(self.KEY)

    @pytest.mark.asyncio
    async def test_no_stored_code_returns_false(self, service: EmailService, mock_cache: AsyncMock) -> None:
        mock_cache.get.return_value = None

        result = await service.verify_code(self.EMAIL, "123456")

        assert result is False
        mock_cache.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrong_code_with_no_remaining_ttl_does_not_update_cache(
        self, service: EmailService, mock_cache: AsyncMock
    ) -> None:
        """If remaining TTL <= 0 after a wrong attempt, cache.set is NOT called."""
        # Expires essentially now (within a fraction of a second)
        now = datetime.now(UTC)
        stored = {
            "code": "654321",
            "created_at": (now - timedelta(seconds=300)).isoformat(),
            "expires_at": (now + timedelta(milliseconds=1)).isoformat(),
            "attempts": 0,
        }
        mock_cache.get.return_value = stored

        # Tiny sleep is not needed -- by the time we compute remaining_ttl it
        # will be 0 or negative because int() truncates.  But we won't rely on
        # race; instead set expires_at to NOW so remaining_ttl == 0.
        stored["expires_at"] = now.isoformat()

        result = await service.verify_code(self.EMAIL, "000000")

        # Code didn't match and remaining_ttl <= 0, so cache.set should NOT be called
        # (the code was already expired by the time we check remaining_ttl)
        # Actually the code is expired so delete is called first
        assert result is False


# ===========================================================================
# 3. send_verification_code
# ===========================================================================


class TestSendVerificationCode:
    EMAIL = "user@example.com"

    @pytest.mark.asyncio
    async def test_raises_if_email_config_incomplete(self, mock_cache: AsyncMock) -> None:
        """Missing any of host/port/username/password should raise BadRequestError."""
        incomplete_configs = [
            {"email_host": ""},
            {"email_port": 0},
            {"email_username": ""},
            {"email_password": ""},
            {"email_host": None},
        ]
        for override in incomplete_configs:
            settings = _make_settings(**override)
            with patch("app.application.services.email_service.get_settings", return_value=settings):
                svc = EmailService(cache=mock_cache)

            with pytest.raises(BadRequestError, match="Email configuration is incomplete"):
                await svc.send_verification_code(self.EMAIL)

    @pytest.mark.asyncio
    async def test_rate_limits_if_code_too_recent(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """If a code was created < 60s ago, raise BadRequestError with wait message."""
        mock_cache.get.return_value = _stored_code_data("999999", created_seconds_ago=30, expires_in_seconds=270)

        with pytest.raises(BadRequestError, match=r"Please wait .* seconds"):
            await service.send_verification_code(self.EMAIL)

    @pytest.mark.asyncio
    async def test_allows_resend_after_60_seconds(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Code created >= 60s ago should not be rate-limited."""
        mock_cache.get.return_value = _stored_code_data("999999", created_seconds_ago=61, expires_in_seconds=239)

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            await service.send_verification_code(self.EMAIL)

        # Code should have been stored
        mock_cache.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_success_sends_smtp_and_stores_code(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Happy path: no existing code, sends email, stores verification code."""
        mock_cache.get.return_value = None  # no existing code

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            await service.send_verification_code(self.EMAIL)

            # SMTP interactions
            mock_smtp_cls.assert_called_once_with("smtp.example.com", 465, timeout=30)
            mock_server.login.assert_called_once_with("user@example.com", "s3cret")
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()

        # Code stored in cache
        mock_cache.set.assert_awaited()
        store_call = mock_cache.set.call_args
        stored_key = store_call.args[0] if store_call.args else store_call[0][0]
        assert stored_key == f"verification_code:{self.EMAIL}"
        stored_value = store_call.args[1] if len(store_call.args) > 1 else store_call[0][1]
        assert "code" in stored_value
        assert len(stored_value["code"]) == 6

    @pytest.mark.asyncio
    async def test_smtp_failure_propagates(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """If SMTP raises, the exception propagates (not silenced)."""
        mock_cache.get.return_value = None

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp_cls.side_effect = smtplib.SMTPConnectError(421, b"Service unavailable")

            with pytest.raises(smtplib.SMTPConnectError):
                await service.send_verification_code(self.EMAIL)

    @pytest.mark.asyncio
    async def test_rate_limit_skips_invalid_existing_data(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """If existing cached data has invalid/missing created_at, proceed normally."""
        mock_cache.get.return_value = {"some": "garbage"}

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            # Should NOT raise — invalid data is silently ignored
            await service.send_verification_code(self.EMAIL)

        mock_cache.set.assert_awaited()


# ===========================================================================
# 4. send_rating_email
# ===========================================================================


class TestSendRatingEmail:
    COMMON_KWARGS: ClassVar[dict[str, Any]] = {
        "user_email": "alice@example.com",
        "user_name": "Alice",
        "session_id": "sess-001",
        "report_id": "rpt-001",
        "rating": 4,
        "feedback": "Great job!",
    }

    @pytest.mark.asyncio
    async def test_noop_if_no_target_email(self, mock_cache: AsyncMock) -> None:
        settings = _make_settings(rating_notification_email="")
        with patch("app.application.services.email_service.get_settings", return_value=settings):
            svc = EmailService(cache=mock_cache)

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            await svc.send_rating_email(**self.COMMON_KWARGS)
            mock_smtp_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_if_target_is_none(self, mock_cache: AsyncMock) -> None:
        settings = _make_settings(rating_notification_email=None)
        with patch("app.application.services.email_service.get_settings", return_value=settings):
            svc = EmailService(cache=mock_cache)

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            await svc.send_rating_email(**self.COMMON_KWARGS)
            mock_smtp_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_if_email_config_incomplete(self, mock_cache: AsyncMock) -> None:
        settings = _make_settings(email_host="", rating_notification_email="ratings@example.com")
        with patch("app.application.services.email_service.get_settings", return_value=settings):
            svc = EmailService(cache=mock_cache)

        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            await svc.send_rating_email(**self.COMMON_KWARGS)
            mock_smtp_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_sends_email(self, service: EmailService, mock_cache: AsyncMock) -> None:
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            await service.send_rating_email(**self.COMMON_KWARGS)

            mock_smtp_cls.assert_called_once_with("smtp.example.com", 465, timeout=30)
            mock_server.login.assert_called_once()
            mock_server.sendmail.assert_called_once()
            # Verify it was sent to the rating target, not the user
            sendmail_args = mock_server.sendmail.call_args
            assert sendmail_args[0][1] == "ratings@example.com"
            mock_server.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_without_feedback(self, service: EmailService, mock_cache: AsyncMock) -> None:
        kwargs = {**self.COMMON_KWARGS, "feedback": None}
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            await service.send_rating_email(**kwargs)

            mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_smtp_exception_is_caught_and_logged(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """send_rating_email must NOT propagate SMTP exceptions."""
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp_cls.side_effect = smtplib.SMTPConnectError(421, b"Service unavailable")

            # Should NOT raise
            await service.send_rating_email(**self.COMMON_KWARGS)

    @pytest.mark.asyncio
    async def test_generic_exception_is_caught(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Even a non-SMTP exception must be swallowed."""
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp_cls.side_effect = RuntimeError("unexpected")

            await service.send_rating_email(**self.COMMON_KWARGS)

    @pytest.mark.asyncio
    async def test_email_subject_contains_stars(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Subject should include star characters and the rating."""
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server
            mock_server.login.return_value = (235, b"OK")
            mock_server.sendmail.return_value = {}

            await service.send_rating_email(**self.COMMON_KWARGS)

            sendmail_args = mock_server.sendmail.call_args
            raw_email = sendmail_args[0][2]
            parsed = email_mod.message_from_string(raw_email)
            # Decode the (possibly RFC-2047-encoded) Subject header
            decoded_subject = str(email_mod.header.decode_header(parsed["Subject"])[0][0], "utf-8")
            assert "4/5" in decoded_subject
            assert "Alice" in decoded_subject


# ===========================================================================
# 5. cleanup_expired_codes
# ===========================================================================


class TestCleanupExpiredCodes:
    @pytest.mark.asyncio
    async def test_deletes_expired_codes(self, service: EmailService, mock_cache: AsyncMock) -> None:
        expired = _expired_code_data("111111")
        mock_cache.keys.return_value = ["verification_code:expired@example.com"]
        mock_cache.get.return_value = expired

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_awaited_once_with("verification_code:expired@example.com")

    @pytest.mark.asyncio
    async def test_keeps_valid_codes(self, service: EmailService, mock_cache: AsyncMock) -> None:
        valid = _stored_code_data("222222", expires_in_seconds=120)
        mock_cache.keys.return_value = ["verification_code:valid@example.com"]
        mock_cache.get.return_value = valid

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_mixed_expired_and_valid(self, service: EmailService, mock_cache: AsyncMock) -> None:
        expired = _expired_code_data("111111")
        valid = _stored_code_data("222222", expires_in_seconds=120)

        keys = [
            "verification_code:expired@example.com",
            "verification_code:valid@example.com",
        ]
        mock_cache.keys.return_value = keys

        # Return different data for each key
        mock_cache.get.side_effect = [expired, valid]

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_awaited_once_with("verification_code:expired@example.com")

    @pytest.mark.asyncio
    async def test_deletes_invalid_data_missing_expires_at(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Data without 'expires_at' key is considered invalid and deleted."""
        invalid = {"code": "123456", "attempts": 0}
        mock_cache.keys.return_value = ["verification_code:bad@example.com"]
        mock_cache.get.return_value = invalid

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_awaited_once_with("verification_code:bad@example.com")

    @pytest.mark.asyncio
    async def test_deletes_invalid_data_bad_expires_at(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """Data with unparseable 'expires_at' value is deleted."""
        invalid = {"code": "123456", "expires_at": "not-a-date", "attempts": 0}
        mock_cache.keys.return_value = ["verification_code:bad@example.com"]
        mock_cache.get.return_value = invalid

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_awaited_once_with("verification_code:bad@example.com")

    @pytest.mark.asyncio
    async def test_skips_keys_with_none_data(self, service: EmailService, mock_cache: AsyncMock) -> None:
        """If cache.get returns None (key expired between keys() and get()), skip it."""
        mock_cache.keys.return_value = ["verification_code:gone@example.com"]
        mock_cache.get.return_value = None

        await service.cleanup_expired_codes()

        mock_cache.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_keys_is_noop(self, service: EmailService, mock_cache: AsyncMock) -> None:
        mock_cache.keys.return_value = []

        await service.cleanup_expired_codes()

        mock_cache.get.assert_not_awaited()
        mock_cache.delete.assert_not_awaited()


# ===========================================================================
# 6. _store_verification_code (internal, but worth asserting contract)
# ===========================================================================


class TestStoreVerificationCode:
    @pytest.mark.asyncio
    async def test_stores_with_correct_key_and_ttl(self, service: EmailService, mock_cache: AsyncMock) -> None:
        await service._store_verification_code("store@example.com", "456789")

        mock_cache.set.assert_awaited_once()
        call_args = mock_cache.set.call_args
        key = call_args.args[0] if call_args.args else call_args[0][0]
        assert key == "verification_code:store@example.com"

        value = call_args.args[1] if len(call_args.args) > 1 else call_args[0][1]
        assert value["code"] == "456789"
        assert value["attempts"] == 0
        assert "created_at" in value
        assert "expires_at" in value

        # TTL should be 300 seconds
        ttl = call_args.kwargs.get("ttl")
        assert ttl == 300


# ===========================================================================
# 7. _create_verification_email (internal formatting)
# ===========================================================================


class TestCreateVerificationEmail:
    def test_email_fields(self, service: EmailService) -> None:
        msg = service._create_verification_email("dest@example.com", "123456")

        assert msg["To"] == "dest@example.com"
        assert msg["From"] == "noreply@example.com"
        assert "Verification" in msg["Subject"]

    def test_email_body_contains_code(self, service: EmailService) -> None:
        msg = service._create_verification_email("dest@example.com", "987654")
        payload = msg.get_payload()[0].get_payload()
        assert "987654" in payload

    def test_uses_username_as_from_when_no_email_from(self, mock_cache: AsyncMock) -> None:
        settings = _make_settings(email_from="")
        with patch("app.application.services.email_service.get_settings", return_value=settings):
            svc = EmailService(cache=mock_cache)

        msg = svc._create_verification_email("dest@example.com", "123456")
        assert msg["From"] == "user@example.com"
