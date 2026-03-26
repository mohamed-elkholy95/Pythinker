"""Tests for TokenService — JWT creation, verification, signing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.application.services.token_service import TokenService


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.jwt_secret_key = "test-secret-key-12345"
    settings.jwt_refresh_secret_key = "test-refresh-secret-67890"
    settings.jwt_algorithm = "HS256"
    settings.jwt_access_token_expire_minutes = 30
    settings.jwt_refresh_token_expire_days = 7
    settings.jwt_token_blacklist_enabled = True
    return settings


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = "user-123"
    user.fullname = "Test User"
    user.email = "test@example.com"
    user.role.value = "user"
    user.is_active = True
    return user


@pytest.fixture
def token_service(mock_settings: MagicMock) -> TokenService:
    with patch("app.application.services.token_service.get_settings", return_value=mock_settings):
        return TokenService()


class TestCreateAccessToken:
    """Tests for create_access_token."""

    def test_creates_valid_jwt(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_info(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["fullname"] == "Test User"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_token_has_expiration(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"])
        assert "exp" in payload
        assert "iat" in payload
        # Expiry should be ~30 min from now
        exp_delta = payload["exp"] - payload["iat"]
        assert 1790 <= exp_delta <= 1810  # ~30 min in seconds


class TestCreateRefreshToken:
    """Tests for create_refresh_token."""

    def test_creates_refresh_jwt(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_refresh_token(mock_user)
        assert isinstance(token, str)

    def test_uses_refresh_secret(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_refresh_token(mock_user)
        payload = jwt.decode(token, "test-refresh-secret-67890", algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_refresh_token_not_decodable_with_access_secret(
        self, token_service: TokenService, mock_user: MagicMock
    ) -> None:
        token = token_service.create_refresh_token(mock_user)
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"])


class TestVerifyToken:
    """Tests for verify_token and verify_token_with_reason."""

    def test_valid_token_returns_payload(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        payload = token_service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"

    def test_expired_token_returns_none(self, token_service: TokenService) -> None:
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "type": "access",
        }
        token = jwt.encode(payload, "test-secret-key-12345", algorithm="HS256")
        result = token_service.verify_token(token)
        assert result is None

    def test_expired_token_reason(self, token_service: TokenService) -> None:
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "type": "access",
        }
        token = jwt.encode(payload, "test-secret-key-12345", algorithm="HS256")
        result, reason = token_service.verify_token_with_reason(token)
        assert result is None
        assert reason == "token_expired"

    def test_invalid_signature_returns_none(self, token_service: TokenService) -> None:
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "type": "access",
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        result, reason = token_service.verify_token_with_reason(token)
        assert result is None
        assert reason == "invalid_token"

    def test_type_mismatch_returns_none(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        result, reason = token_service.verify_token_with_reason(token, expected_type="refresh")
        assert result is None
        assert reason == "invalid_token"

    def test_garbage_token(self, token_service: TokenService) -> None:
        result, _reason = token_service.verify_token_with_reason("not.a.jwt")
        assert result is None


class TestVerifyTokenAsync:
    """Tests for async token verification with blacklist."""

    @pytest.mark.asyncio
    async def test_blacklisted_token_denied(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(return_value=1)  # exists returns 1

        with patch("app.application.services.token_service.get_redis", return_value=mock_redis):
            result, reason = await token_service.verify_token_async_with_reason(token)

        assert result is None
        assert reason == "token_revoked"

    @pytest.mark.asyncio
    async def test_valid_non_blacklisted_token(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(return_value=0)  # not blacklisted, not revoked

        with patch("app.application.services.token_service.get_redis", return_value=mock_redis):
            result, reason = await token_service.verify_token_async_with_reason(token)

        assert result is not None
        assert reason is None

    @pytest.mark.asyncio
    async def test_redis_failure_fails_closed(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch("app.application.services.token_service.get_redis", return_value=mock_redis),
            patch("app.application.services.token_service.token_auth_fail_closed_total"),
        ):
            result, reason = await token_service.verify_token_async_with_reason(token)

        assert result is None
        assert reason == "token_revoked"


class TestHashToken:
    """Tests for _hash_token."""

    def test_deterministic(self, token_service: TokenService) -> None:
        h1 = token_service._hash_token("test-token")
        h2 = token_service._hash_token("test-token")
        assert h1 == h2

    def test_truncated_to_32(self, token_service: TokenService) -> None:
        h = token_service._hash_token("any-token")
        assert len(h) == 32

    def test_different_tokens_different_hashes(self, token_service: TokenService) -> None:
        h1 = token_service._hash_token("token-a")
        h2 = token_service._hash_token("token-b")
        assert h1 != h2


class TestGetUserFromToken:
    """Tests for get_user_from_token."""

    def test_extracts_user_info(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        user_info = token_service.get_user_from_token(token)
        assert user_info is not None
        assert user_info["id"] == "user-123"
        assert user_info["fullname"] == "Test User"
        assert user_info["email"] == "test@example.com"
        assert user_info["token_type"] == "access"

    def test_invalid_token_returns_none(self, token_service: TokenService) -> None:
        result = token_service.get_user_from_token("invalid")
        assert result is None


class TestIsTokenValid:
    """Tests for is_token_valid."""

    def test_valid_token(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        assert token_service.is_token_valid(token) is True

    def test_invalid_token(self, token_service: TokenService) -> None:
        assert token_service.is_token_valid("garbage") is False


class TestGetTokenExpiration:
    """Tests for get_token_expiration."""

    def test_returns_expiration(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        exp = token_service.get_token_expiration(token)
        assert exp is not None
        assert exp > datetime.now(UTC)

    def test_invalid_token_returns_none(self, token_service: TokenService) -> None:
        assert token_service.get_token_expiration("bad") is None


class TestCreateResourceAccessToken:
    """Tests for create_resource_access_token."""

    def test_creates_resource_token(self, token_service: TokenService) -> None:
        token = token_service.create_resource_access_token("file", "file-123", "user-456")
        assert isinstance(token, str)

        payload = jwt.decode(token, "test-secret-key-12345", algorithms=["HS256"])
        assert payload["resource_type"] == "file"
        assert payload["resource_id"] == "file-123"
        assert payload["user_id"] == "user-456"
        assert payload["type"] == "resource_access"


class TestSignedUrl:
    """Tests for create_signed_url and verify_signed_url."""

    def test_create_and_verify(self, token_service: TokenService) -> None:
        signed_url = token_service.create_signed_url("/api/v1/files/123")
        assert token_service.verify_signed_url(signed_url) is True

    def test_create_with_user_id(self, token_service: TokenService) -> None:
        signed_url = token_service.create_signed_url("/api/v1/files/123", user_id="user-456")
        assert "uid=user-456" in signed_url
        assert token_service.verify_signed_url(signed_url) is True

    def test_tampered_signature_fails(self, token_service: TokenService) -> None:
        signed_url = token_service.create_signed_url("/api/v1/files/123")
        tampered = signed_url.replace("signature=", "signature=tampered")
        assert token_service.verify_signed_url(tampered) is False

    def test_expired_url_fails(self, token_service: TokenService) -> None:
        signed_url = token_service.create_signed_url("/api/v1/files/123", expire_minutes=-1)
        assert token_service.verify_signed_url(signed_url) is False

    def test_missing_signature_fails(self, token_service: TokenService) -> None:
        assert token_service.verify_signed_url("/api/v1/files/123") is False


class TestRevokeTokenAsync:
    """Tests for revoke_token_async."""

    @pytest.mark.asyncio
    async def test_revokes_token(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token = token_service.create_access_token(mock_user)
        mock_redis = AsyncMock()
        mock_redis.call = AsyncMock(return_value="OK")

        with patch("app.application.services.token_service.get_redis", return_value=mock_redis):
            result = await token_service.revoke_token_async(token)

        assert result is True
        mock_redis.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_token_skips_blacklist(self, token_service: TokenService) -> None:
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "type": "access",
        }
        token = jwt.encode(payload, "test-secret-key-12345", algorithm="HS256")
        mock_redis = AsyncMock()

        with patch("app.application.services.token_service.get_redis", return_value=mock_redis):
            result = await token_service.revoke_token_async(token)

        assert result is True
        mock_redis.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_blacklist_disabled_returns_true(self, token_service: TokenService, mock_user: MagicMock) -> None:
        token_service.settings.jwt_token_blacklist_enabled = False
        token = token_service.create_access_token(mock_user)
        result = await token_service.revoke_token_async(token)
        assert result is True
