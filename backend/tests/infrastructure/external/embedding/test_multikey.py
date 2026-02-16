"""Tests for Embedding Client multi-key support."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.embedding.client import EmbeddingClient
from app.infrastructure.external.key_pool import RotationStrategy
from app.infrastructure.storage.redis import get_redis


@pytest.fixture
async def redis_client():
    """Get Redis client for testing. Skips if Redis is unavailable."""
    import redis.exceptions

    client = get_redis()
    try:
        await client.initialize()
    except (redis.exceptions.ConnectionError, ConnectionError, OSError):
        pytest.skip("Redis unavailable")
    yield client
    # Cleanup
    await client.shutdown()


class TestEmbeddingMultiKey:
    """Test embedding client with APIKeyPool."""

    @pytest.mark.asyncio
    async def test_embedding_uses_round_robin(self, redis_client):
        """Embedding client should use ROUND_ROBIN strategy."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        assert client._key_pool is not None
        assert len(client._key_pool.keys) == 3
        assert client._key_pool.strategy == RotationStrategy.ROUND_ROBIN  # Round-robin!

    @pytest.mark.asyncio
    async def test_embedding_distributes_load(self, redis_client):
        """Round-robin should distribute requests across all keys."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        # Get 9 keys (3 rounds)
        keys_used = []
        for _ in range(9):
            key = await client.get_api_key()
            keys_used.append(key)

        # Each key should appear 3 times (even distribution)
        assert keys_used.count("key1") == 3
        assert keys_used.count("key2") == 3
        assert keys_used.count("key3") == 3

    @pytest.mark.asyncio
    async def test_embedding_respects_retry_limit(self, redis_client, mocker):
        """Test retry limit prevents infinite recursion."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2", "key3"],
            redis_client=redis_client,
        )

        # Mock httpx AsyncClient to always return 429
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        mock_post = AsyncMock(return_value=mock_response)
        mocker.patch("httpx.AsyncClient.post", mock_post)

        with pytest.raises(RuntimeError) as exc:
            await client.embed_batch(["test text"])

        assert "exhausted after 3 attempts" in str(exc.value)

    @pytest.mark.asyncio
    async def test_embedding_works_without_redis(self):
        """Test in-memory mode without Redis."""
        client = EmbeddingClient(
            api_key="test-key-1",
            fallback_api_keys=["test-key-2"],
            redis_client=None,
        )

        key = await client.get_api_key()
        assert key in ["test-key-1", "test-key-2"]  # Round-robin can return either
        assert client._key_pool._redis is None

    @pytest.mark.asyncio
    async def test_embedding_single_key_mode(self, redis_client):
        """Test with single key (no fallbacks)."""
        client = EmbeddingClient(
            api_key="only-key",
            fallback_api_keys=None,
            redis_client=redis_client,
        )

        assert len(client._key_pool.keys) == 1
        key = await client.get_api_key()
        assert key == "only-key"

    @pytest.mark.asyncio
    async def test_embedding_filters_empty_keys(self, redis_client):
        """Test that empty/whitespace keys are filtered out."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2", "", "  ", None],
            redis_client=redis_client,
        )

        # Should only have 2 keys (key1 and key2)
        assert len(client._key_pool.keys) == 2

    @pytest.mark.asyncio
    async def test_embed_batch_success(self, redis_client, mocker):
        """Test successful batch embedding with multi-key."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=redis_client,
        )

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * 1536},
                {"index": 1, "embedding": [0.2] * 1536},
            ]
        }

        mock_post = AsyncMock(return_value=mock_response)
        mocker.patch("httpx.AsyncClient.post", mock_post)

        result = await client.embed_batch(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1] * 1536
        assert result[1] == [0.2] * 1536

    @pytest.mark.asyncio
    async def test_embed_batch_auto_rotation_on_429(self, redis_client, mocker):
        """Test automatic key rotation on 429 rate limit."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=redis_client,
        )

        # First call returns 429, second succeeds
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"x-ratelimit-reset": "1234567890"}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"index": 0, "embedding": [0.5] * 1536}]}

        mock_post = AsyncMock(side_effect=[mock_response_429, mock_response_200])
        mocker.patch("httpx.AsyncClient.post", mock_post)

        result = await client.embed_batch(["test"])

        assert len(result) == 1
        assert mock_post.call_count == 2  # Rotated to second key

    @pytest.mark.asyncio
    async def test_embed_batch_auto_rotation_on_401(self, redis_client, mocker):
        """Test automatic key rotation on 401 unauthorized."""
        client = EmbeddingClient(
            api_key="key1",
            fallback_api_keys=["key2"],
            redis_client=redis_client,
        )

        # First call returns 401, second succeeds
        mock_response_401 = MagicMock()
        mock_response_401.status_code = 401
        mock_response_401.headers = {}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"index": 0, "embedding": [0.5] * 1536}]}

        mock_post = AsyncMock(side_effect=[mock_response_401, mock_response_200])
        mocker.patch("httpx.AsyncClient.post", mock_post)

        result = await client.embed_batch(["test"])

        assert len(result) == 1
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_parse_rate_limit_ttl_with_header(self, redis_client):
        """Test TTL parsing from X-RateLimit-Reset header."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        import time

        future_timestamp = time.time() + 3600  # 1 hour from now
        headers = {"x-ratelimit-reset": str(future_timestamp)}

        ttl = client._parse_rate_limit_ttl(headers)

        # Should be close to 3600 seconds (allow 5 second tolerance)
        assert 3595 <= ttl <= 3605

    @pytest.mark.asyncio
    async def test_parse_rate_limit_ttl_without_header(self, redis_client):
        """Test default TTL when header is missing."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        headers = {}
        ttl = client._parse_rate_limit_ttl(headers)

        assert ttl == 60  # Default 1 minute

    @pytest.mark.asyncio
    async def test_parse_rate_limit_ttl_with_invalid_header(self, redis_client):
        """Test default TTL when header is invalid."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        headers = {"x-ratelimit-reset": "invalid-timestamp"}
        ttl = client._parse_rate_limit_ttl(headers)

        assert ttl == 60  # Default 1 minute

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self, redis_client):
        """Test embed_batch with empty list."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        result = await client.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_truncates_long_texts(self, redis_client, mocker):
        """Test that long texts are truncated to 8000 chars."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"index": 0, "embedding": [0.1] * 1536}]}

        mock_post = AsyncMock(return_value=mock_response)
        mocker.patch("httpx.AsyncClient.post", mock_post)

        long_text = "a" * 10000
        await client.embed_batch([long_text])

        # Check that the request payload has truncated text
        call_kwargs = mock_post.call_args.kwargs
        input_texts = call_kwargs["json"]["input"]
        assert len(input_texts[0]) == 8000

    @pytest.mark.asyncio
    async def test_embed_batch_maintains_order(self, redis_client, mocker):
        """Test that batch results maintain input order."""
        client = EmbeddingClient(
            api_key="key1",
            redis_client=redis_client,
        )

        # Return shuffled order from API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"index": 2, "embedding": [0.3] * 1536},
                {"index": 0, "embedding": [0.1] * 1536},
                {"index": 1, "embedding": [0.2] * 1536},
            ]
        }

        mock_post = AsyncMock(return_value=mock_response)
        mocker.patch("httpx.AsyncClient.post", mock_post)

        result = await client.embed_batch(["text0", "text1", "text2"])

        # Should be sorted by index
        assert result[0] == [0.1] * 1536
        assert result[1] == [0.2] * 1536
        assert result[2] == [0.3] * 1536
