"""Tests for JWT secret startup validation (SEC-015).

Verifies that Settings raises ValueError at construction time when
auth_provider != 'none' and jwt_secret_key is missing/empty.
"""

import pytest


class TestJWTSecretValidation:
    def test_password_auth_requires_jwt_secret(self, monkeypatch):
        """Settings must reject construction when auth requires JWT but secret is absent."""
        monkeypatch.setenv("AUTH_PROVIDER", "password")
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        from app.core.config import Settings

        with pytest.raises(ValueError, match=r"jwt_secret_key.*required"):
            Settings(auth_provider="password", jwt_secret_key=None)

    def test_local_auth_requires_jwt_secret(self, monkeypatch):
        """Local auth provider also requires jwt_secret_key."""
        monkeypatch.setenv("AUTH_PROVIDER", "local")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        from app.core.config import Settings

        with pytest.raises(ValueError, match=r"jwt_secret_key.*required"):
            Settings(auth_provider="local", jwt_secret_key=None)

    def test_none_auth_allows_missing_jwt_secret(self, monkeypatch):
        """When auth_provider='none', a missing jwt_secret_key is acceptable."""
        monkeypatch.setenv("AUTH_PROVIDER", "none")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        from app.core.config import Settings

        config = Settings(auth_provider="none", jwt_secret_key=None)
        assert config.jwt_secret_key is None

    def test_jwt_secret_set_passes_validation(self, monkeypatch):
        """A non-empty jwt_secret_key satisfies the validator for password auth."""
        monkeypatch.setenv("AUTH_PROVIDER", "password")
        monkeypatch.setenv("JWT_SECRET_KEY", "super-secret-key-1234")

        from app.core.config import Settings

        config = Settings(auth_provider="password", jwt_secret_key="super-secret-key-1234")
        assert config.jwt_secret_key == "super-secret-key-1234"

    def test_empty_string_jwt_secret_rejected(self, monkeypatch):
        """An empty string jwt_secret_key is treated the same as None."""
        monkeypatch.setenv("AUTH_PROVIDER", "password")
        monkeypatch.setenv("JWT_SECRET_KEY", "")

        from app.core.config import Settings

        with pytest.raises(ValueError, match=r"jwt_secret_key.*required"):
            Settings(auth_provider="password", jwt_secret_key="")
