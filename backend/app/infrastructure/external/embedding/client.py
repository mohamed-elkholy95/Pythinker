"""Shared embedding client for vector generation.

Provides a singleton embedding client used by both MemoryService
and SemanticCache. Wraps OpenAI's embedding API with fallback support.
"""

import logging
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Client for generating text embeddings via OpenAI-compatible API.

    Used by both MemoryService and SemanticCache to generate vector
    embeddings for text content.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dimension = 1536  # text-embedding-3-small dimension

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed (truncated to 8000 chars)

        Returns:
            Embedding vector (1536 dimensions)

        Raises:
            Exception: If embedding API call fails
        """
        truncated = text[:8000]
        response = await self._client.embeddings.create(
            model=self._model,
            input=truncated,
            encoding_format="float",
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            Exception: If embedding API call fails
        """
        if not texts:
            return []

        # OpenAI supports batch embedding natively
        truncated = [t[:8000] for t in texts]
        response = await self._client.embeddings.create(
            model=self._model,
            input=truncated,
            encoding_format="float",
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [d.embedding for d in sorted_data]

    @property
    def model(self) -> str:
        """Get the embedding model name."""
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        return self._dimension


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    """Get the singleton embedding client.

    Uses settings for API key, base URL, and model configuration.

    Returns:
        Configured EmbeddingClient instance

    Raises:
        RuntimeError: If no embedding API key is configured
    """
    settings = get_settings()
    api_key = settings.embedding_api_key or settings.api_key

    if not api_key:
        raise RuntimeError("No embedding API key configured. Set EMBEDDING_API_KEY or API_KEY.")

    return EmbeddingClient(
        api_key=api_key,
        base_url=settings.embedding_api_base,
        model=settings.embedding_model,
    )
