"""Tests for SearchRateGovernor token bucket."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.search.rate_governor import SearchRateGovernor, _get_egress_ip

# ---------------------------------------------------------------------------
# In-memory fallback tests (Redis=None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governor_allows_under_burst():
    """First acquire from a fresh bucket is always allowed (burst capacity)."""
    gov = SearchRateGovernor(redis=None, provider="tavily", rps=5.0, burst=5.0)
    allowed = await gov.acquire()
    assert allowed is True


@pytest.mark.asyncio
async def test_governor_throttles_over_burst():
    """Governor denies when bucket is empty (no refill time elapsed)."""
    gov = SearchRateGovernor(redis=None, provider="tavily", rps=1.0, burst=1.0)
    first = await gov.acquire()  # consumes the 1 burst token
    second = await gov.acquire()  # immediately after — no refill
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_governor_fails_open_on_redis_none():
    """With redis=None, in-memory fallback always starts allowing (burst > 0)."""
    gov = SearchRateGovernor(redis=None, provider="serper", rps=10.0, burst=3.0)
    # First 3 (burst) should all pass
    results = [await gov.acquire() for _ in range(3)]
    assert all(results)


@pytest.mark.asyncio
async def test_governor_in_memory_refills_after_interval():
    """In-memory bucket refills proportional to time elapsed."""
    gov = SearchRateGovernor(redis=None, provider="tavily", rps=10.0, burst=1.0)
    first = await gov.acquire()  # consume the burst token
    assert first is True

    # Simulate 150ms elapsed (should refill 1.5 tokens at 10 rps)
    gov._last_refill -= 0.15
    second = await gov.acquire()  # should succeed after refill
    assert second is True


def test_governor_bucket_key_contains_provider():
    """Bucket key must include the provider name."""
    gov = SearchRateGovernor(redis=None, provider="serper", rps=3.0, burst=5.0)
    assert "serper" in gov._bucket_key()


def test_governor_bucket_key_contains_ip():
    """Bucket key must include an IP address (not empty)."""
    gov = SearchRateGovernor(redis=None, provider="serper", rps=3.0, burst=5.0)
    key = gov._bucket_key()
    # Key format: search_rate_gov:{provider}:{ip}
    parts = key.split(":")
    assert len(parts) >= 3
    ip_part = ":".join(parts[2:])  # handle IPv6
    assert ip_part  # not empty


# ---------------------------------------------------------------------------
# Redis path tests (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_governor_uses_redis_when_available():
    """When Redis is provided, acquire() uses the Lua script path."""
    mock_redis = MagicMock()
    mock_script = AsyncMock(return_value=1)  # allowed
    mock_redis.register_script.return_value = mock_script

    gov = SearchRateGovernor(redis=mock_redis, provider="brave", rps=1.0, burst=5.0)
    result = await gov.acquire()

    mock_redis.register_script.assert_called_once()
    mock_script.assert_called_once()
    assert result is True


@pytest.mark.asyncio
async def test_governor_falls_back_to_memory_on_redis_error():
    """On Redis exception, falls back gracefully to in-memory token bucket."""
    mock_redis = MagicMock()
    mock_script = AsyncMock(side_effect=RuntimeError("Redis unavailable"))
    mock_redis.register_script.return_value = mock_script

    gov = SearchRateGovernor(redis=mock_redis, provider="exa", rps=5.0, burst=5.0)
    result = await gov.acquire()
    # Falls back to in-memory (burst=5 so first call passes)
    assert result is True


# ---------------------------------------------------------------------------
# Egress IP helper
# ---------------------------------------------------------------------------


def test_get_egress_ip_returns_string():
    """_get_egress_ip returns a non-empty string (or 'unknown')."""
    ip = _get_egress_ip()
    assert isinstance(ip, str)
    assert ip  # not empty
