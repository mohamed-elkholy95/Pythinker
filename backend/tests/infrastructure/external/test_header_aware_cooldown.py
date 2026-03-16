"""Tests for header-aware cooldown parsing in APIKeyPool — Fix 4.

Verifies Retry-After, X-RateLimit-Reset, and RateLimit-Reset headers
are honored before falling back to exponential backoff.
"""

from __future__ import annotations

import time
from email.utils import formatdate

from app.infrastructure.external.key_pool import APIKeyPool, RotationStrategy


def _make_pool() -> APIKeyPool:
    return APIKeyPool(keys=["test-key-1"], provider="test", strategy=RotationStrategy.FAILOVER)


class TestParseRetryAfterHeader:
    def test_integer_retry_after(self):
        pool = _make_pool()
        headers = {"Retry-After": "120"}
        result = pool._parse_retry_after_header(headers)
        assert result == 120

    def test_zero_retry_after(self):
        pool = _make_pool()
        headers = {"Retry-After": "0"}
        result = pool._parse_retry_after_header(headers)
        assert result == 0

    def test_http_date_retry_after(self):
        pool = _make_pool()
        future_ts = time.time() + 90
        headers = {"Retry-After": formatdate(future_ts, usegmt=True)}
        result = pool._parse_retry_after_header(headers)
        assert result is not None
        assert 80 <= result <= 100  # 90s ± 10s tolerance

    def test_x_ratelimit_reset_unix(self):
        pool = _make_pool()
        reset_ts = int(time.time()) + 60
        headers = {"X-RateLimit-Reset": str(reset_ts)}
        result = pool._parse_retry_after_header(headers)
        assert result is not None
        assert 50 <= result <= 70

    def test_ratelimit_reset_unix(self):
        pool = _make_pool()
        reset_ts = int(time.time()) + 45
        headers = {"RateLimit-Reset": str(reset_ts)}
        result = pool._parse_retry_after_header(headers)
        assert result is not None
        assert 35 <= result <= 55

    def test_case_insensitive_headers(self):
        pool = _make_pool()
        headers = {"retry-after": "30"}
        result = pool._parse_retry_after_header(headers)
        assert result == 30

    def test_no_header_returns_none(self):
        pool = _make_pool()
        result = pool._parse_retry_after_header({})
        assert result is None

    def test_invalid_value_falls_through(self):
        pool = _make_pool()
        headers = {"Retry-After": "not-a-number"}
        result = pool._parse_retry_after_header(headers)
        # Invalid date string — should return None and fall through
        assert result is None


class TestGetRateLimitCooldownWithHeaders:
    def test_header_overrides_exponential_backoff(self):
        pool = _make_pool()
        headers = {"Retry-After": "120"}
        cooldown = pool._get_rate_limit_cooldown("test-key-1", response_headers=headers)
        assert cooldown == 120

    def test_no_header_uses_exponential_backoff(self):
        pool = _make_pool()
        cooldown = pool._get_rate_limit_cooldown("test-key-1", response_headers=None)
        # Base is 60s, first hit should be 60s + some jitter
        assert cooldown >= 60

    def test_none_headers_uses_exponential_backoff(self):
        pool = _make_pool()
        cooldown = pool._get_rate_limit_cooldown("test-key-1")
        assert cooldown >= 60
