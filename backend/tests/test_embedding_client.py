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
    async def test_embed_returns_vector(self):
        """Should return embedding vector from API response."""
        client = EmbeddingClient(api_key="test-key")

        expected_embedding = [0.1] * 1536
        mock_data_item = MagicMock()
        mock_data_item.embedding = expected_embedding

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        result = await client.embed("Hello world")

        assert result == expected_embedding
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_truncates_long_text(self):
        """Should truncate text to 8000 chars."""
        client = EmbeddingClient(api_key="test-key")

        mock_data_item = MagicMock()
        mock_data_item.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        long_text = "a" * 10000
        result = await client.embed(long_text)

        # Verify text was truncated in the API call
        call_kwargs = mock_embeddings.create.call_args.kwargs
        assert len(call_kwargs["input"]) == 8000
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_passes_model_and_encoding(self):
        """Should pass model name and encoding_format to API."""
        client = EmbeddingClient(api_key="test-key", model="text-embedding-3-large")

        mock_data_item = MagicMock()
        mock_data_item.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        await client.embed("test text")

        call_kwargs = mock_embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-large"
        assert call_kwargs["encoding_format"] == "float"

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        """Should return empty list for empty input."""
        client = EmbeddingClient(api_key="test-key")
        result = await client.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_single_text(self):
        """Should handle single-item batch."""
        client = EmbeddingClient(api_key="test-key")

        mock_data_item = MagicMock()
        mock_data_item.index = 0
        mock_data_item.embedding = [0.5] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_data_item]

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        result = await client.embed_batch(["single text"])

        assert len(result) == 1
        assert result[0] == [0.5] * 1536

    @pytest.mark.asyncio
    async def test_embed_batch_maintains_order(self):
        """Batch results should maintain input order even when API returns shuffled."""
        client = EmbeddingClient(api_key="test-key")

        # Create mock response with shuffled indices
        mock_item_1 = MagicMock()
        mock_item_1.index = 1
        mock_item_1.embedding = [0.2] * 1536

        mock_item_0 = MagicMock()
        mock_item_0.index = 0
        mock_item_0.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_item_1, mock_item_0]  # Shuffled order

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        result = await client.embed_batch(["text0", "text1"])

        # Should be sorted by index (0 first, then 1)
        assert result[0] == [0.1] * 1536
        assert result[1] == [0.2] * 1536

    @pytest.mark.asyncio
    async def test_embed_batch_truncates_all_texts(self):
        """Batch should truncate all texts to 8000 chars."""
        client = EmbeddingClient(api_key="test-key")

        mock_item_0 = MagicMock()
        mock_item_0.index = 0
        mock_item_0.embedding = [0.1] * 1536

        mock_item_1 = MagicMock()
        mock_item_1.index = 1
        mock_item_1.embedding = [0.2] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_item_0, mock_item_1]

        mock_embeddings = MagicMock()
        mock_embeddings.create = AsyncMock(return_value=mock_response)
        client._client = MagicMock()
        client._client.embeddings = mock_embeddings

        long_texts = ["x" * 10000, "y" * 9000]
        await client.embed_batch(long_texts)

        call_kwargs = mock_embeddings.create.call_args.kwargs
        input_texts = call_kwargs["input"]
        assert len(input_texts[0]) == 8000
        assert len(input_texts[1]) == 8000

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
