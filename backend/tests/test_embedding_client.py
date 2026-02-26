"""Tests for the shared embedding client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.embedding.client import EmbeddingClient, get_embedding_client


class TestEmbeddingClient:
    """Test EmbeddingClient functionality."""

    def test_init_defaults(self):
        """Should initialize with API key and default model/dimension."""
        client = EmbeddingClient(
            api_key="test-key",
        )
        assert client.model == "text-embedding-3-small"
        assert client.dimension == 1536

    def test_init_custom_model(self):
        """Should accept custom model and base_url."""
        client = EmbeddingClient(
            api_key="test-key",
            base_url="https://custom-api.example.com/v1",
            model="text-embedding-ada-002",
        )
        assert client.model == "text-embedding-ada-002"
        assert client.dimension == 1536

    @pytest.mark.asyncio
    async def test_embed_delegates_to_embed_batch(self):
        """embed() should delegate to embed_batch() for unified key rotation."""
        client = EmbeddingClient(api_key="test-key")

        expected_embedding = [0.1] * 1536
        client.embed_batch = AsyncMock(return_value=[expected_embedding])

        result = await client.embed("Hello world")

        assert result == expected_embedding
        client.embed_batch.assert_awaited_once_with(["Hello world"])

    @pytest.mark.asyncio
    async def test_embed_returns_first_element(self):
        """embed() should return the first (and only) embedding from batch."""
        client = EmbeddingClient(api_key="test-key")

        embedding = [0.5] * 1536
        client.embed_batch = AsyncMock(return_value=[embedding])

        result = await client.embed("test text")

        assert result == embedding
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        """Should return empty list for empty input."""
        client = EmbeddingClient(api_key="test-key")
        result = await client.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_single_text(self):
        """Should handle single-item batch via HTTPClientPool."""
        client = EmbeddingClient(api_key="test-key")

        api_response = {
            "data": [{"index": 0, "embedding": [0.5] * 1536}],
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = api_response
        mock_http_response.raise_for_status = MagicMock()

        mock_managed_client = AsyncMock()
        mock_managed_client.post = AsyncMock(return_value=mock_http_response)

        with patch(
            "app.infrastructure.external.embedding.client.HTTPClientPool.get_client",
            new_callable=AsyncMock,
            return_value=mock_managed_client,
        ):
            result = await client.embed_batch(["single text"])

        assert len(result) == 1
        assert result[0] == [0.5] * 1536

    @pytest.mark.asyncio
    async def test_embed_batch_maintains_order(self):
        """Batch results should maintain input order even when API returns shuffled."""
        client = EmbeddingClient(api_key="test-key")

        api_response = {
            "data": [
                {"index": 1, "embedding": [0.2] * 1536},
                {"index": 0, "embedding": [0.1] * 1536},
            ],
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = api_response
        mock_http_response.raise_for_status = MagicMock()

        mock_managed_client = AsyncMock()
        mock_managed_client.post = AsyncMock(return_value=mock_http_response)

        with patch(
            "app.infrastructure.external.embedding.client.HTTPClientPool.get_client",
            new_callable=AsyncMock,
            return_value=mock_managed_client,
        ):
            result = await client.embed_batch(["text0", "text1"])

        # Should be sorted by index (0 first, then 1)
        assert result[0] == [0.1] * 1536
        assert result[1] == [0.2] * 1536

    @pytest.mark.asyncio
    async def test_embed_batch_truncates_all_texts(self):
        """Batch should truncate all texts to 8000 chars."""
        client = EmbeddingClient(api_key="test-key")

        api_response = {
            "data": [
                {"index": 0, "embedding": [0.1] * 1536},
                {"index": 1, "embedding": [0.2] * 1536},
            ],
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = api_response
        mock_http_response.raise_for_status = MagicMock()

        mock_managed_client = AsyncMock()
        mock_managed_client.post = AsyncMock(return_value=mock_http_response)

        with patch(
            "app.infrastructure.external.embedding.client.HTTPClientPool.get_client",
            new_callable=AsyncMock,
            return_value=mock_managed_client,
        ):
            long_texts = ["x" * 10000, "y" * 9000]
            await client.embed_batch(long_texts)

        # Verify truncation in the HTTP request body
        call_kwargs = mock_managed_client.post.call_args
        request_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        input_texts = request_body["input"]
        assert len(input_texts[0]) == 8000
        assert len(input_texts[1]) == 8000

    @pytest.mark.asyncio
    async def test_embed_batch_uses_pool_with_base_url(self):
        """Should pass base_url and timeout to HTTPClientPool.get_client."""
        client = EmbeddingClient(
            api_key="test-key",
            base_url="https://custom-api.example.com/v1",
            timeout=60.0,
        )

        api_response = {
            "data": [{"index": 0, "embedding": [0.1] * 1536}],
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = api_response
        mock_http_response.raise_for_status = MagicMock()

        mock_managed_client = AsyncMock()
        mock_managed_client.post = AsyncMock(return_value=mock_http_response)

        with patch(
            "app.infrastructure.external.embedding.client.HTTPClientPool.get_client",
            new_callable=AsyncMock,
            return_value=mock_managed_client,
        ) as mock_get_client:
            await client.embed_batch(["test"])

        mock_get_client.assert_awaited_once_with(
            "openai-embedding",
            base_url="https://custom-api.example.com/v1",
            timeout=60.0,
        )

    @pytest.mark.asyncio
    async def test_embed_batch_sends_relative_url(self):
        """Should POST to /embeddings (relative), not full URL — base_url is on pool."""
        client = EmbeddingClient(api_key="test-key")

        api_response = {
            "data": [{"index": 0, "embedding": [0.1] * 1536}],
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = api_response
        mock_http_response.raise_for_status = MagicMock()

        mock_managed_client = AsyncMock()
        mock_managed_client.post = AsyncMock(return_value=mock_http_response)

        with patch(
            "app.infrastructure.external.embedding.client.HTTPClientPool.get_client",
            new_callable=AsyncMock,
            return_value=mock_managed_client,
        ):
            await client.embed_batch(["test"])

        # First positional arg to post() should be relative path
        post_args = mock_managed_client.post.call_args
        assert post_args[0][0] == "/embeddings"

    def test_model_property(self):
        """model property should return the configured model."""
        client = EmbeddingClient(api_key="key", model="custom-model")
        assert client.model == "custom-model"

    def test_dimension_property(self):
        """dimension property should return 1536."""
        client = EmbeddingClient(api_key="key")
        assert client.dimension == 1536


class TestGetEmbeddingClient:
    """Test the singleton factory function."""

    @patch("app.infrastructure.external.embedding.client.get_settings")
    def test_creates_client_with_settings(self, mock_settings):
        """Should use settings for configuration."""
        mock_settings.return_value = MagicMock(
            embedding_api_key="test-key",
            api_key="fallback-key",
            embedding_api_base="https://api.openai.com/v1",
            embedding_model="text-embedding-3-small",
        )

        # Clear cache to force fresh creation
        get_embedding_client.cache_clear()

        client = get_embedding_client()
        assert isinstance(client, EmbeddingClient)
        assert client.model == "text-embedding-3-small"

        # Cleanup
        get_embedding_client.cache_clear()

    @patch("app.infrastructure.external.embedding.client.get_settings")
    def test_uses_embedding_api_key_over_fallback(self, mock_settings):
        """Should prefer embedding_api_key over api_key."""
        mock_settings.return_value = MagicMock(
            embedding_api_key="specific-embedding-key",
            api_key="general-api-key",
            embedding_api_base="https://api.openai.com/v1",
            embedding_model="text-embedding-3-small",
        )

        get_embedding_client.cache_clear()
        client = get_embedding_client()
        assert isinstance(client, EmbeddingClient)
        get_embedding_client.cache_clear()

    @patch("app.infrastructure.external.embedding.client.get_settings")
    def test_falls_back_to_api_key(self, mock_settings):
        """Should fall back to api_key when embedding_api_key is None."""
        mock_settings.return_value = MagicMock(
            embedding_api_key=None,
            api_key="fallback-key",
            embedding_api_base="https://api.openai.com/v1",
            embedding_model="text-embedding-3-small",
        )

        get_embedding_client.cache_clear()
        client = get_embedding_client()
        assert isinstance(client, EmbeddingClient)
        get_embedding_client.cache_clear()

    @patch("app.infrastructure.external.embedding.client.get_settings")
    def test_raises_without_api_key(self, mock_settings):
        """Should raise RuntimeError if no API key configured."""
        mock_settings.return_value = MagicMock(
            embedding_api_key=None,
            api_key=None,
        )

        get_embedding_client.cache_clear()

        with pytest.raises(RuntimeError, match="No embedding API key"):
            get_embedding_client()

        get_embedding_client.cache_clear()

    @patch("app.infrastructure.external.embedding.client.get_settings")
    def test_singleton_caches_instance(self, mock_settings):
        """Subsequent calls should return the same cached instance."""
        mock_settings.return_value = MagicMock(
            embedding_api_key="test-key",
            api_key=None,
            embedding_api_base="https://api.openai.com/v1",
            embedding_model="text-embedding-3-small",
        )

        get_embedding_client.cache_clear()

        client1 = get_embedding_client()
        client2 = get_embedding_client()
        assert client1 is client2

        get_embedding_client.cache_clear()
