from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.schemas.resource import AccessTokenRequest, SignedUrlResponse


class TestAccessTokenRequest:
    def test_default_expire_minutes(self) -> None:
        req = AccessTokenRequest()
        assert req.expire_minutes == 15

    def test_explicit_expire_minutes(self) -> None:
        req = AccessTokenRequest(expire_minutes=5)
        assert req.expire_minutes == 5

    def test_minimum_valid_value(self) -> None:
        req = AccessTokenRequest(expire_minutes=1)
        assert req.expire_minutes == 1

    def test_maximum_valid_value(self) -> None:
        req = AccessTokenRequest(expire_minutes=15)
        assert req.expire_minutes == 15

    def test_mid_range_valid_value(self) -> None:
        req = AccessTokenRequest(expire_minutes=8)
        assert req.expire_minutes == 8

    def test_zero_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AccessTokenRequest(expire_minutes=0)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("expire_minutes",) for e in errors)

    def test_negative_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AccessTokenRequest(expire_minutes=-1)

    def test_above_maximum_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AccessTokenRequest(expire_minutes=16)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("expire_minutes",) for e in errors)

    def test_far_above_maximum_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AccessTokenRequest(expire_minutes=100)

    def test_serialization(self) -> None:
        req = AccessTokenRequest(expire_minutes=10)
        data = req.model_dump()
        assert data == {"expire_minutes": 10}


class TestSignedUrlResponse:
    def test_construction(self) -> None:
        resp = SignedUrlResponse(signed_url="https://example.com/file?sig=abc", expires_in=3600)
        assert resp.signed_url == "https://example.com/file?sig=abc"
        assert resp.expires_in == 3600

    def test_requires_signed_url(self) -> None:
        with pytest.raises(ValidationError):
            SignedUrlResponse(expires_in=3600)  # type: ignore[call-arg]

    def test_requires_expires_in(self) -> None:
        with pytest.raises(ValidationError):
            SignedUrlResponse(signed_url="https://example.com")  # type: ignore[call-arg]

    def test_expires_in_zero(self) -> None:
        resp = SignedUrlResponse(signed_url="https://example.com", expires_in=0)
        assert resp.expires_in == 0

    def test_expires_in_large_value(self) -> None:
        resp = SignedUrlResponse(signed_url="https://s3.example.com/key", expires_in=86400)
        assert resp.expires_in == 86400

    def test_serialization(self) -> None:
        resp = SignedUrlResponse(signed_url="https://cdn.example.com/obj", expires_in=300)
        data = resp.model_dump()
        assert data == {"signed_url": "https://cdn.example.com/obj", "expires_in": 300}
