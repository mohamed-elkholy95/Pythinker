"""Tests for Redis cache pipeline bulk deletion (Phase 2C)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.cache.redis_cache import RedisCache


@pytest.fixture
def cache():
    """Create a RedisCache with a mock redis client."""
    c = RedisCache.__new__(RedisCache)
    c.redis_client = MagicMock()
    c._initialized = True
    c._init_lock = MagicMock()
    c._scan_count = 100
    c._ttl_jitter_percent = 0.0
    c._swr_enabled = False
    c.redis_client.call = AsyncMock()
    return c


class TestClearPatternPipeline:
    """Tests for pipeline-based bulk key deletion."""

    @pytest.mark.asyncio
    async def test_clear_pattern_uses_unlink(self, cache):
        """Keys are deleted via UNLINK for non-blocking operation."""
        # SCAN returns keys then cursor=0 (done)
        cache.redis_client.call.side_effect = [
            (0, ["key:1", "key:2", "key:3"]),  # scan
            3,  # unlink
        ]

        deleted = await cache.clear_pattern("key:*")

        assert deleted == 3
        # Verify UNLINK was called with all keys
        calls = cache.redis_client.call.call_args_list
        assert calls[1][0] == ("unlink", "key:1", "key:2", "key:3")

    @pytest.mark.asyncio
    async def test_clear_pattern_accumulates_across_scan_batches(self, cache):
        """Keys from multiple SCAN batches are accumulated before deletion."""
        cache.redis_client.call.side_effect = [
            (42, ["key:1", "key:2"]),  # scan batch 1 (cursor=42, not done)
            (0, ["key:3"]),  # scan batch 2 (cursor=0, done)
            3,  # unlink all accumulated keys
        ]

        deleted = await cache.clear_pattern("key:*")

        assert deleted == 3
        calls = cache.redis_client.call.call_args_list
        # Third call should unlink all 3 keys
        assert calls[2][0] == ("unlink", "key:1", "key:2", "key:3")

    @pytest.mark.asyncio
    async def test_clear_pattern_empty_returns_zero(self, cache):
        """No matching keys returns 0 without calling UNLINK."""
        cache.redis_client.call.side_effect = [
            (0, []),  # scan returns empty
        ]

        deleted = await cache.clear_pattern("nonexistent:*")

        assert deleted == 0
        assert cache.redis_client.call.call_count == 1  # Only SCAN, no UNLINK

    @pytest.mark.asyncio
    async def test_clear_pattern_falls_back_to_delete_on_unlink_failure(self, cache):
        """Falls back to DELETE when UNLINK is unavailable."""
        cache.redis_client.call.side_effect = [
            (0, ["key:1", "key:2"]),  # scan
            Exception("UNLINK not available"),  # unlink fails
            2,  # delete fallback
        ]

        deleted = await cache.clear_pattern("key:*")

        assert deleted == 2
