"""Tests for AuthToken domain model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.auth import AuthToken
from app.domain.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(**overrides) -> User:
    """Return a minimal valid User instance."""
    defaults = {
        "id": "user-001",
        "fullname": "Alice Smith",
        "email": "alice@example.com",
    }
    defaults.update(overrides)
    return User(**defaults)


# ---------------------------------------------------------------------------
# Construction — required fields
# ---------------------------------------------------------------------------

def test_auth_token_minimal_construction():
    """AuthToken can be constructed with only access_token."""
    token = AuthToken(access_token="abc123")
    assert token.access_token == "abc123"


def test_auth_token_access_token_is_required():
    """Omitting access_token raises a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        AuthToken()  # type: ignore[call-arg]
    errors = exc_info.value.errors()
    field_names = [e["loc"][0] for e in errors]
    assert "access_token" in field_names


def test_auth_token_access_token_stored_as_given():
    """access_token is stored verbatim — no normalisation."""
    token = AuthToken(access_token="Bearer eyJhbGciOiJIUzI1NiJ9")
    assert token.access_token == "Bearer eyJhbGciOiJIUzI1NiJ9"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_auth_token_default_token_type():
    """token_type defaults to 'bearer'."""
    token = AuthToken(access_token="tok")
    assert token.token_type == "bearer"


def test_auth_token_default_refresh_token_is_none():
    """refresh_token defaults to None."""
    token = AuthToken(access_token="tok")
    assert token.refresh_token is None


def test_auth_token_default_user_is_none():
    """user defaults to None."""
    token = AuthToken(access_token="tok")
    assert token.user is None


def test_auth_token_default_requires_totp_is_false():
    """requires_totp defaults to False."""
    token = AuthToken(access_token="tok")
    assert token.requires_totp is False


# ---------------------------------------------------------------------------
# Optional fields — explicit values
# ---------------------------------------------------------------------------

def test_auth_token_custom_token_type():
    """token_type can be set to any string value."""
    token = AuthToken(access_token="tok", token_type="mac")
    assert token.token_type == "mac"


def test_auth_token_with_refresh_token():
    """refresh_token is stored when provided."""
    token = AuthToken(access_token="access", refresh_token="refresh-xyz")
    assert token.refresh_token == "refresh-xyz"


def test_auth_token_requires_totp_true():
    """requires_totp can be set to True (e.g. after first-factor auth)."""
    token = AuthToken(access_token="partial", requires_totp=True)
    assert token.requires_totp is True


# ---------------------------------------------------------------------------
# Nested User field
# ---------------------------------------------------------------------------

def test_auth_token_with_user_instance():
    """user field accepts a full User object."""
    user = make_user()
    token = AuthToken(access_token="tok", user=user)
    assert token.user is not None
    assert token.user.email == "alice@example.com"
    assert token.user.fullname == "Alice Smith"


def test_auth_token_with_user_admin_role():
    """User with ADMIN role is accepted inside AuthToken."""
    user = make_user(id="admin-1", fullname="Bob Admin", email="bob@example.com", role=UserRole.ADMIN)
    token = AuthToken(access_token="tok", user=user)
    assert token.user is not None
    assert token.user.role == UserRole.ADMIN


def test_auth_token_user_can_be_set_to_none_explicitly():
    """user=None is accepted (same as default)."""
    token = AuthToken(access_token="tok", user=None)
    assert token.user is None


# ---------------------------------------------------------------------------
# Full construction
# ---------------------------------------------------------------------------

def test_auth_token_full_construction():
    """All fields can be set together without error."""
    user = make_user()
    token = AuthToken(
        access_token="access-abc",
        token_type="bearer",
        refresh_token="refresh-abc",
        user=user,
        requires_totp=False,
    )
    assert token.access_token == "access-abc"
    assert token.token_type == "bearer"
    assert token.refresh_token == "refresh-abc"
    assert token.user is not None
    assert token.requires_totp is False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_auth_token_model_dump_minimal():
    """model_dump() includes all expected keys for a minimal token."""
    token = AuthToken(access_token="tok")
    data = token.model_dump()
    assert data["access_token"] == "tok"
    assert data["token_type"] == "bearer"
    assert data["refresh_token"] is None
    assert data["user"] is None
    assert data["requires_totp"] is False


def test_auth_token_model_dump_with_user():
    """model_dump() serializes the nested user as a dict."""
    user = make_user()
    token = AuthToken(access_token="tok", user=user)
    data = token.model_dump()
    assert isinstance(data["user"], dict)
    assert data["user"]["email"] == "alice@example.com"


def test_auth_token_model_dump_with_refresh():
    """refresh_token appears correctly in serialized output."""
    token = AuthToken(access_token="a", refresh_token="r")
    data = token.model_dump()
    assert data["refresh_token"] == "r"


def test_auth_token_round_trip_from_dict():
    """AuthToken can be reconstructed from its own model_dump() output."""
    user = make_user()
    original = AuthToken(
        access_token="access",
        token_type="bearer",
        refresh_token="refresh",
        user=user,
        requires_totp=False,
    )
    data = original.model_dump()
    reconstructed = AuthToken.model_validate(data)
    assert reconstructed.access_token == original.access_token
    assert reconstructed.token_type == original.token_type
    assert reconstructed.refresh_token == original.refresh_token
    assert reconstructed.user is not None
    assert reconstructed.user.email == original.user.email  # type: ignore[union-attr]
    assert reconstructed.requires_totp == original.requires_totp


def test_auth_token_model_dump_json_returns_string():
    """model_dump_json() returns a JSON string."""
    token = AuthToken(access_token="tok")
    json_str = token.model_dump_json()
    assert isinstance(json_str, str)
    assert "tok" in json_str


def test_auth_token_round_trip_via_json():
    """AuthToken survives a JSON serialization round-trip."""
    token = AuthToken(access_token="tok", refresh_token="ref", requires_totp=True)
    json_str = token.model_dump_json()
    reconstructed = AuthToken.model_validate_json(json_str)
    assert reconstructed.access_token == "tok"
    assert reconstructed.refresh_token == "ref"
    assert reconstructed.requires_totp is True


def test_auth_token_requires_totp_totp_flow():
    """Simulates a TOTP challenge: token returned without user, requires_totp=True."""
    token = AuthToken(access_token="partial-token", requires_totp=True, user=None)
    assert token.requires_totp is True
    assert token.user is None
    # After TOTP verification a second token is issued with the full user
    user = make_user()
    full_token = AuthToken(access_token="full-token", user=user, requires_totp=False)
    assert full_token.requires_totp is False
    assert full_token.user is not None
