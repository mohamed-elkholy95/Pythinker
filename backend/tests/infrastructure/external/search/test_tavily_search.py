"""Integration tests for TavilySearchEngine with APIKeyPool."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.infrastructure.external.search.tavily_search import TavilySearchEngine
from app.infrastructure.storage.redis import get_redis


@pytest.fixture
async def redis_client():
    """Get Redis client for testing."""
    client = get_redis()
    await client.initialize()
    yield client
    # Cleanup
    await client.shutdown()


async def test_tavily_uses_key_pool_rotation(redis_client):
    """Tavily should use APIKeyPool for multi-key rotation."""
    engine = TavilySearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3", "key4", "key5", "key6", "key7", "key8", "key9"],
        redis_client=redis_client,
    )

    # Verify pool is initialized
    assert engine._key_pool is not None
    assert len(engine._key_pool.keys) == 9  # 9 total keys (different from Serper's 3)

    # Verify strategy is FAILOVER
    from app.infrastructure.external.key_pool import RotationStrategy

    assert engine._key_pool.strategy == RotationStrategy.FAILOVER


@pytest.mark.asyncio
async def test_tavily_respects_retry_limit(redis_client, mocker):
    """Test that search() doesn't recurse infinitely when all keys are exhausted."""
    engine = TavilySearchEngine(
        api_key="key1",
        fallback_api_keys=["key2", "key3"],  # 3 keys total
        redis_client=redis_client,
    )

    # Mock HTTP client to always return 429 (rate limit)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    # Mock _get_client to return our mock client
    mocker.patch.object(engine, "_get_client", return_value=mock_client)

    # Execute search - should fail after 3 attempts (3 keys), not stack overflow
    result = await engine.search("test query")

    # Verify result is an error
    assert result.success is False
    assert "exhausted after" in result.message

    # Verify we made exactly 3 attempts (one per key)
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_tavily_works_without_redis():
    """Test that TavilySearchEngine works in-memory mode without Redis."""
    # Initialize without Redis (None)
    engine = TavilySearchEngine(
        api_key="test-key-1",
        fallback_api_keys=["test-key-2"],
        redis_client=None,  # Should not crash
    )

    # Should be able to get a key
    key = await engine.api_key
    assert key == "test-key-1"  # First key in FAILOVER strategy

    # Verify pool is in in-memory mode
    assert engine._key_pool._redis is None
