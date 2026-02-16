"""
Unit tests for APIKeyPool multi-strategy rotation.

Tests cover:
- Round-robin rotation (even distribution, skip exhausted keys)
- Failover rotation (priority order, fallback on exhaustion)
- Weighted rotation (respect weights)
- Health tracking (mark exhausted with TTL, mark invalid permanent)
- TTL recovery (key becomes healthy after TTL expires)
- Exponential backoff (with jitter, capped at max)
"""

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    KeyHealthStatus,
    RotationStrategy,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing with state tracking."""
    redis = AsyncMock()

    # Track state in memory
    redis._state = {}

    async def mock_exists(key):
        return key in redis._state

    async def mock_setex(key, ttl, value):
        redis._state[key] = value

    async def mock_set(key, value):
        redis._state[key] = value

    async def mock_call(method, *args):
        method = method.lower()
        if method == "exists":
            return await mock_exists(args[0])
        if method == "setex":
            await mock_setex(args[0], args[1], args[2])
            return True
        if method == "set":
            await mock_set(args[0], args[1])
            return True
        raise AssertionError(f"Unexpected Redis method in test mock: {method}")

    redis.exists.side_effect = mock_exists
    redis.setex.side_effect = mock_setex
    redis.set.side_effect = mock_set
    redis.call.side_effect = mock_call

    return redis


@pytest.fixture
def basic_keys():
    """Basic key pool for testing."""
    return [
        APIKeyConfig(key="key1", weight=1.0, priority=0),
        APIKeyConfig(key="key2", weight=1.0, priority=1),
        APIKeyConfig(key="key3", weight=1.0, priority=2),
    ]


@pytest.mark.asyncio
class TestRoundRobinRotation:
    """Test round-robin rotation strategy."""

    async def test_round_robin_even_distribution(self, mock_redis, basic_keys):
        """Round-robin should distribute evenly across keys."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Get 9 keys (3 full rotations)
        results = []
        for _ in range(9):
            key = await pool.get_healthy_key()
            results.append(key)

        # Should cycle through keys in order
        assert results == ["key1", "key2", "key3"] * 3

    async def test_round_robin_skip_exhausted_keys(self, mock_redis, basic_keys):
        """Round-robin should skip exhausted keys."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Mark key2 as exhausted
        await pool.mark_exhausted("key2", ttl_seconds=60)

        # Get 6 keys
        results = []
        for _ in range(6):
            key = await pool.get_healthy_key()
            results.append(key)

        # Should only cycle between key1 and key3
        assert results == ["key1", "key3"] * 3


@pytest.mark.asyncio
class TestFailoverRotation:
    """Test failover rotation strategy."""

    async def test_failover_priority_order(self, mock_redis, basic_keys):
        """Failover should use priority order (lower = higher priority)."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.FAILOVER,
            redis_client=mock_redis,
        )

        # Should always return key1 (priority=1)
        for _ in range(5):
            key = await pool.get_healthy_key()
            assert key == "key1"

    async def test_failover_fallback_on_exhaustion(self, mock_redis, basic_keys):
        """Failover should fall back when primary is exhausted."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.FAILOVER,
            redis_client=mock_redis,
        )

        # Mark key1 as exhausted
        await pool.mark_exhausted("key1", ttl_seconds=60)

        # Should fallback to key2 (priority=2)
        key = await pool.get_healthy_key()
        assert key == "key2"

        # Mark key2 as exhausted
        await pool.mark_exhausted("key2", ttl_seconds=60)

        # Should fallback to key3 (priority=3)
        key = await pool.get_healthy_key()
        assert key == "key3"


@pytest.mark.asyncio
class TestWeightedRotation:
    """Test weighted rotation strategy."""

    async def test_weighted_distribution(self, mock_redis):
        """Weighted rotation should respect weights."""
        keys = [
            APIKeyConfig(key="heavy", weight=9.0, priority=0),
            APIKeyConfig(key="light", weight=1.0, priority=1),
        ]
        pool = APIKeyPool(
            provider="test",
            keys=keys,
            strategy=RotationStrategy.WEIGHTED,
            redis_client=mock_redis,
        )

        # Get 1000 keys and check distribution
        results = []
        for _ in range(1000):
            key = await pool.get_healthy_key()
            results.append(key)

        heavy_count = results.count("heavy")
        light_count = results.count("light")

        # Heavy should be ~90% (900/1000)
        # Allow 10% variance
        assert 800 <= heavy_count <= 950
        assert 50 <= light_count <= 200


@pytest.mark.asyncio
class TestHealthTracking:
    """Test key health tracking."""

    async def test_mark_exhausted_with_ttl(self, mock_redis, basic_keys):
        """mark_exhausted should set Redis key with TTL."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        await pool.mark_exhausted("key1", ttl_seconds=300)

        # Verify Redis call("setex", ...) was issued with correct params
        setex_calls = [call for call in mock_redis.call.call_args_list if call.args and call.args[0] == "setex"]
        assert len(setex_calls) == 1
        call_args = setex_calls[0].args
        assert call_args[1].startswith("api_key:exhausted:test:")
        assert call_args[2] == 300
        assert call_args[3] == KeyHealthStatus.EXHAUSTED.value

    async def test_mark_invalid_permanent(self, mock_redis, basic_keys):
        """mark_invalid should set Redis key with no TTL."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        await pool.mark_invalid("key1")

        # Verify Redis call("set", ...) was issued (no TTL)
        set_calls = [call for call in mock_redis.call.call_args_list if call.args and call.args[0] == "set"]
        assert len(set_calls) == 1
        call_args = set_calls[0].args
        assert call_args[1].startswith("api_key:invalid:test:")
        assert call_args[2] == KeyHealthStatus.INVALID.value

    async def test_ttl_recovery(self, mock_redis, basic_keys):
        """Exhausted keys should become healthy after TTL expires."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Mark key2 as exhausted
        await pool.mark_exhausted("key2", ttl_seconds=60)

        # Should skip key2
        key = await pool.get_healthy_key()
        assert key != "key2"

        # Simulate TTL expiry (clear Redis state)
        mock_redis._state.clear()
        exhausted_hash = pool._hash_key("key2")
        pool._memory_exhausted[exhausted_hash] = 0.0

        # Should be able to use key2 again
        results = []
        for _ in range(10):
            key = await pool.get_healthy_key()
            results.append(key)

        # key2 should appear in results
        assert "key2" in results


@pytest.mark.asyncio
class TestBackoffStrategy:
    """Test exponential backoff with jitter."""

    async def test_exponential_backoff_with_jitter(self, mock_redis, basic_keys):
        """Backoff should follow exponential pattern with jitter."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Test backoff progression
        delays = []
        for attempt in range(5):
            delay = pool.get_backoff_delay("key1", attempt)
            delays.append(delay)

        # Verify exponential growth (with jitter variance)
        # Attempt 0: ~1s (0.75-1.25s)
        # Attempt 1: ~2s (1.5-2.5s)
        # Attempt 2: ~4s (3-5s)
        # Attempt 3: ~8s (6-10s)
        # Attempt 4: ~16s (12-20s)
        assert 0.5 <= delays[0] <= 1.5
        assert 1.0 <= delays[1] <= 3.0
        assert 2.5 <= delays[2] <= 5.5
        assert 5.0 <= delays[3] <= 11.0
        assert 10.0 <= delays[4] <= 22.0

    async def test_backoff_capped_at_max(self, mock_redis, basic_keys):
        """Backoff should be capped at max_backoff_seconds."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
            base_backoff_seconds=1.0,
            max_backoff_seconds=10.0,
        )

        # High attempt should be capped at max (10s ± 25%)
        delay = pool.get_backoff_delay("key1", attempt=10)
        assert 7.5 <= delay <= 12.5


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_no_healthy_keys_returns_none(self, mock_redis, basic_keys):
        """Should return None when all keys are exhausted."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Mark all keys as exhausted
        for key_config in basic_keys:
            await pool.mark_exhausted(key_config.key, ttl_seconds=60)

        # Should return None
        key = await pool.get_healthy_key()
        assert key is None

    async def test_empty_keys_list_raises_exception(self, mock_redis):
        """Should raise exception when initialized with empty keys list."""
        with pytest.raises(ValueError, match="keys list cannot be empty"):
            APIKeyPool(
                provider="test",
                keys=[],
                strategy=RotationStrategy.ROUND_ROBIN,
                redis_client=mock_redis,
            )

    async def test_invalid_keys_skipped(self, mock_redis, basic_keys):
        """Invalid keys should be permanently skipped."""
        pool = APIKeyPool(
            provider="test",
            keys=basic_keys,
            strategy=RotationStrategy.ROUND_ROBIN,
            redis_client=mock_redis,
        )

        # Mark key2 as invalid
        await pool.mark_invalid("key2")

        # Get 6 keys - should skip key2
        results = []
        for _ in range(6):
            key = await pool.get_healthy_key()
            results.append(key)

        # Should only cycle between key1 and key3
        assert results == ["key1", "key3"] * 3
        assert "key2" not in results
