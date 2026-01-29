import logging
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class QdrantStorage:
    """Qdrant vector database client singleton."""

    def __init__(self):
        self._client: AsyncQdrantClient | None = None
        self._settings = get_settings()

    async def initialize(self) -> None:
        """Initialize Qdrant connection."""
        if self._client is not None:
            return

        try:
            self._client = AsyncQdrantClient(
                url=self._settings.qdrant_url,
                port=self._settings.qdrant_grpc_port if self._settings.qdrant_prefer_grpc else None,
                prefer_grpc=self._settings.qdrant_prefer_grpc,
                api_key=self._settings.qdrant_api_key,
            )
            # Verify connection
            await self._client.get_collections()
            logger.info("Successfully connected to Qdrant")

            # Ensure collection exists
            await self._ensure_collection()
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    async def _ensure_collection(self) -> None:
        """Create collection if it doesn't exist."""
        collection_name = self._settings.qdrant_collection
        collections = await self._client.get_collections()

        if collection_name not in [c.name for c in collections.collections]:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=1536,  # OpenAI text-embedding-3-small dimension
                    distance=models.Distance.COSINE,
                ),
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=20000,  # Start HNSW indexing at 20k points
                ),
            )
            logger.info(f"Created Qdrant collection: {collection_name}")

    async def shutdown(self) -> None:
        """Shutdown Qdrant connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Qdrant")
        # Clear cache for this module
        get_qdrant.cache_clear()

    @property
    def client(self) -> AsyncQdrantClient:
        """Return initialized Qdrant client."""
        if self._client is None:
            raise RuntimeError("Qdrant client not initialized. Call initialize() first.")
        return self._client


@lru_cache
def get_qdrant() -> QdrantStorage:
    """Get the Qdrant storage instance."""
    return QdrantStorage()
