"""Tests for User domain model."""

import pytest

from app.domain.models.user import User, UserRole


class TestUserRole:
    def test_values(self) -> None:
        assert UserRole.ADMIN == "admin"
        assert UserRole.USER == "user"


class TestUser:
    def _make(self) -> User:
        return User(id="u-1", fullname="Alice Smith", email="alice@example.com")

    def test_defaults(self) -> None:
        u = self._make()
        assert u.role == UserRole.USER
        assert u.is_active is True
        assert u.email_verified is False
        assert u.totp_enabled is False

    def test_email_normalized(self) -> None:
        u = User(id="u-1", fullname="Bob", email="  BOB@Example.COM  ")
        assert u.email == "bob@example.com"

    def test_invalid_email_no_at(self) -> None:
        with pytest.raises(ValueError, match="@"):
            User(id="u-1", fullname="Bob", email="notanemail")

    def test_invalid_email_no_domain(self) -> None:
        with pytest.raises(ValueError, match="format"):
            User(id="u-1", fullname="Bob", email="bob@")

    def test_short_fullname(self) -> None:
        with pytest.raises(ValueError, match="2 characters"):
            User(id="u-1", fullname="A", email="a@b.com")

    def test_update_last_login(self) -> None:
        u = self._make()
        assert u.last_login_at is None
        u.update_last_login()
        assert u.last_login_at is not None

    def test_verify_email(self) -> None:
        u = self._make()
        assert u.email_verified is False
        u.verify_email()
        assert u.email_verified is True

    def test_deactivate_activate(self) -> None:
        u = self._make()
        u.deactivate()
        assert u.is_active is False
        u.activate()
        assert u.is_active is True
