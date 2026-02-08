import contextlib
import logging
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Collection definitions for multi-collection architecture
COLLECTIONS: dict[str, models.VectorParams] = {
    "user_knowledge": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    "task_artifacts": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    "tool_logs": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    "semantic_cache": models.VectorParams(size=1536, distance=models.Distance.COSINE),
}

# Payload indexes for each collection (for fast filtered search)
COLLECTION_INDEXES: dict[str, list[str]] = {
    "user_knowledge": ["user_id", "memory_type", "importance"],
    "task_artifacts": ["user_id", "session_id", "artifact_type", "agent_role"],
    "tool_logs": ["user_id", "session_id", "tool_name", "outcome"],
    "semantic_cache": ["context_hash", "model"],
}


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

            # Ensure all collections exist
            await self._ensure_collections()
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    async def _ensure_collections(self) -> None:
        """Create all collections if they don't exist, including payload indexes."""
        existing = await self._client.get_collections()
        existing_names = {c.name for c in existing.collections}

        # Legacy collection for backward compatibility
        legacy_name = self._settings.qdrant_collection
        if legacy_name not in existing_names and legacy_name not in COLLECTIONS:
            await self._client.create_collection(
                collection_name=legacy_name,
                vectors_config=models.VectorParams(
                    size=1536,  # OpenAI text-embedding-3-small dimension
                    distance=models.Distance.COSINE,
                ),
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=20000,  # Start HNSW indexing at 20k points
                ),
            )
            logger.info(f"Created legacy Qdrant collection: {legacy_name}")

        # Multi-collection architecture collections
        for name, params in COLLECTIONS.items():
            if name not in existing_names:
                await self._client.create_collection(
                    collection_name=name,
                    vectors_config=params,
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=20000,
                    ),
                )
                logger.info(f"Created Qdrant collection: {name}")

        # Create payload indexes for filtered search
        for collection_name, fields in COLLECTION_INDEXES.items():
            for field in fields:
                with contextlib.suppress(Exception):
                    # Index may already exist — suppress duplicates
                    await self._client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )

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
