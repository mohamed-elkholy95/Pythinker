"""Tests for Redis cache stale-while-revalidate pattern (Phase 2B)."""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.cache.redis_cache import RedisCache


@pytest.fixture
def swr_cache():
    """Create a RedisCache with SWR enabled and a mock redis client."""
    cache = RedisCache.__new__(RedisCache)
    cache.redis_client = MagicMock()
    cache._initialized = True
    cache._init_lock = MagicMock()
    cache._scan_count = 1000
    cache._ttl_jitter_percent = 0.0  # Disable jitter for deterministic tests
    cache._swr_enabled = True
    cache.redis_client.call = AsyncMock()
    return cache


class TestSWRSet:
    """Tests for RedisCache.set_with_swr()."""

    @pytest.mark.asyncio
    async def test_set_with_swr_stores_envelope(self, swr_cache):
        """SWR set wraps value in envelope with soft_expires timestamp."""
        swr_cache.redis_client.call.return_value = "OK"

        result = await swr_cache.set_with_swr("key1", {"data": "hello"}, soft_ttl=60, hard_ttl=300)

        assert result is True
        call_args = swr_cache.redis_client.call.call_args
        assert call_args[0][0] == "setex"
        assert call_args[0][1] == "key1"
        assert call_args[0][2] == 300  # hard_ttl

        envelope = json.loads(call_args[0][3])
        assert envelope["v"] == {"data": "hello"}
        assert "soft_expires" in envelope

    @pytest.mark.asyncio
    async def test_set_with_swr_disabled_falls_back_to_plain_set(self):
        """When SWR is disabled, falls back to regular set with soft_ttl."""
        cache = RedisCache.__new__(RedisCache)
        cache.redis_client = MagicMock()
        cache._initialized = True
        cache._init_lock = MagicMock()
        cache._scan_count = 1000
        cache._ttl_jitter_percent = 0.0
        cache._swr_enabled = False
        cache.redis_client.call = AsyncMock(return_value="OK")

        result = await cache.set_with_swr("key1", "value", soft_ttl=60, hard_ttl=300)
        assert result is True

        # Should use soft_ttl as plain TTL
        call_args = cache.redis_client.call.call_args
        assert call_args[0][0] == "setex"
        assert call_args[0][2] == 60  # soft_ttl used as plain TTL


class TestSWRGet:
    """Tests for RedisCache.get_with_swr()."""

    @pytest.mark.asyncio
    async def test_fresh_hit(self, swr_cache):
        """Value within soft TTL returns (value, False)."""
        envelope = {
            "v": {"data": "fresh"},
            "soft_expires": time.time() + 300,  # Expires in 5 min
        }
        swr_cache.redis_client.call.return_value = json.dumps(envelope)

        value, is_stale = await swr_cache.get_with_swr("key1")

        assert value == {"data": "fresh"}
        assert is_stale is False

    @pytest.mark.asyncio
    async def test_stale_hit(self, swr_cache):
        """Value past soft TTL but before hard TTL returns (value, True)."""
        envelope = {
            "v": {"data": "stale"},
            "soft_expires": time.time() - 60,  # Expired 1 min ago
        }
        swr_cache.redis_client.call.return_value = json.dumps(envelope)

        value, is_stale = await swr_cache.get_with_swr("key1")

        assert value == {"data": "stale"}
        assert is_stale is True

    @pytest.mark.asyncio
    async def test_hard_miss(self, swr_cache):
        """Key evicted by Redis returns (None, False)."""
        swr_cache.redis_client.call.return_value = None

        value, is_stale = await swr_cache.get_with_swr("key1")

        assert value is None
        assert is_stale is False

    @pytest.mark.asyncio
    async def test_plain_value_returned_as_fresh(self, swr_cache):
        """Non-SWR values (set without SWR) are returned as fresh."""
        swr_cache.redis_client.call.return_value = json.dumps("plain_value")

        value, is_stale = await swr_cache.get_with_swr("key1")

        assert value == "plain_value"
        assert is_stale is False
