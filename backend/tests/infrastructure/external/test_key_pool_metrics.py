"""Tests for APIKeyPool Prometheus metrics integration."""

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    RotationStrategy,
)


@pytest.fixture
def redis_mock():
    """Mock Redis client with state tracking."""
    redis = AsyncMock()

    # Track state in memory
    redis._state = {}

    async def mock_exists(key):
        return key in redis._state

    async def mock_setex(key, ttl, value):
        redis._state[key] = value

    async def mock_set(key, value):
        redis._state[key] = value

    redis.exists.side_effect = mock_exists
    redis.setex.side_effect = mock_setex
    redis.set.side_effect = mock_set

    return redis


@pytest.fixture
def clear_metrics():
    """Clear Prometheus metrics before each test."""
    from app.infrastructure.observability.prometheus_metrics import reset_all_metrics

    reset_all_metrics()
    yield
    reset_all_metrics()


@pytest.mark.asyncio
class TestAPIKeyPoolMetrics:
    """Test Prometheus metrics integration."""

    async def test_key_selection_increments_counter(self, redis_mock, clear_metrics):
        """Selecting a key should increment api_key_selections_total counter."""
        from app.infrastructure.observability.prometheus_metrics import api_key_selections_total

        pool = APIKeyPool(
            provider="test",
            keys=[APIKeyConfig(key="key1")],
            redis_client=redis_mock,
            strategy=RotationStrategy.ROUND_ROBIN,
        )

        # Get key 3 times
        for _ in range(3):
            await pool.get_healthy_key()

        # Check counter (key1 hash is 81740996)
        metric_value = api_key_selections_total.get({"provider": "test", "key_id": "81740996", "status": "success"})

        assert metric_value == 3

    async def test_exhaustion_increments_counter(self, redis_mock, clear_metrics):
        """Marking key exhausted should increment api_key_exhaustions_total."""
        from app.infrastructure.observability.prometheus_metrics import api_key_exhaustions_total

        pool = APIKeyPool(
            provider="serper",
            keys=[APIKeyConfig(key="test-key")],
            redis_client=redis_mock,
            strategy=RotationStrategy.ROUND_ROBIN,
        )

        await pool.mark_exhausted("test-key", ttl_seconds=3600)

        # Check counter
        metric_value = api_key_exhaustions_total.get({"provider": "serper", "reason": "quota"})

        assert metric_value == 1

    async def test_invalid_increments_counter(self, redis_mock, clear_metrics):
        """Marking key invalid should increment api_key_exhaustions_total."""
        from app.infrastructure.observability.prometheus_metrics import api_key_exhaustions_total

        pool = APIKeyPool(
            provider="anthropic",
            keys=[APIKeyConfig(key="test-key")],
            redis_client=redis_mock,
            strategy=RotationStrategy.FAILOVER,
        )

        await pool.mark_invalid("test-key")

        # Check counter
        metric_value = api_key_exhaustions_total.get({"provider": "anthropic", "reason": "invalid"})

        assert metric_value == 1
