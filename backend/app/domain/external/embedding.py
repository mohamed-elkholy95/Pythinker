"""Domain Protocol for embedding generation.

Defines the contract for embedding clients used by domain services.
Implementations handle API communication, key rotation, and caching.
"""

from typing import Protocol


class EmbeddingPort(Protocol):
    """Port for generating text embeddings.

    Implementations should handle:
    - Single and batch embedding generation
    - API key rotation and retry logic
    - Caching of deterministic embeddings
    """

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        ...
