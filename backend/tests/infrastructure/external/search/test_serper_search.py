"""Integration tests for SerperSearchEngine with APIKeyPool."""

import pytest

from app.infrastructure.external.search.serper_search import SerperSearchEngine
from app.infrastructure.storage.redis import get_redis


@pytest.fixture
async def redis_client():
    """Get Redis client for testing."""
    client = get_redis()
    await client.initialize()
    yield client
    # Cleanup
    await client.shutdown()


async def test_serper_uses_key_pool_rotation(redis_client):
    """Serper should use APIKeyPool for multi-key rotation."""
    engine = SerperSearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],
        redis_client=redis_client,
    )

    # Verify pool is initialized
    assert engine._key_pool is not None
    assert len(engine._key_pool._keys) == 3

    # Verify strategy is FAILOVER
    from app.infrastructure.external.key_pool import RotationStrategy

    assert engine._key_pool._strategy == RotationStrategy.FAILOVER
