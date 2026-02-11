import contextlib
import logging
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Dense vector configuration (1536 = OpenAI text-embedding-3-small)
# HNSW config is specified per-vector, not at collection level, to avoid applying to sparse vectors
DENSE_VECTOR_CONFIG = models.VectorParams(
    size=1536,
    distance=models.Distance.COSINE,
    hnsw_config=models.HnswConfigDiff(
        m=16,  # Connections per node in HNSW graph
        ef_construct=100,  # Build-time accuracy
        full_scan_threshold=10000,  # Use full scan for <10k points
    ),
)

# Collection names mapped to dense vector params.
# Keep this shape stable for wiring/tests that inspect size/distance directly.
COLLECTIONS: dict[str, models.VectorParams] = {
    "user_knowledge": DENSE_VECTOR_CONFIG,
    "task_artifacts": DENSE_VECTOR_CONFIG,
    "tool_logs": DENSE_VECTOR_CONFIG,
    "semantic_cache": DENSE_VECTOR_CONFIG,
}

# Sparse vector configuration (BM25 + IDF)
# Sparse vectors use inverted indexes, not HNSW, so no hnsw_config needed
SPARSE_VECTOR_CONFIG = models.SparseVectorParams(modifier=models.Modifier.IDF)

# Payload indexes for each collection (for fast filtered search)
# Phase 1: Enhanced indexes including tags, session_id, created_at
COLLECTION_INDEXES: dict[str, list[str]] = {
    "user_knowledge": ["user_id", "memory_type", "importance", "tags", "session_id", "created_at"],
    "task_artifacts": ["user_id", "session_id", "artifact_type", "agent_role"],
    "tool_logs": ["user_id", "session_id", "tool_name", "outcome"],
    "semantic_cache": ["context_hash", "model"],
}


class QdrantStorage:
    """Qdrant vector database client singleton."""

    def __init__(self):
        self._client: AsyncQdrantClient | None = None
        self._settings = get_settings()
        self._using_local_fallback = False

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
            await self._client.get_collections()
            self._using_local_fallback = False
            logger.info("Successfully connected to Qdrant")
        except Exception as remote_error:
            can_fallback = getattr(self._settings, "environment", "development") != "production"
            if not can_fallback:
                await self._safe_close_client()
                self._client = None
                logger.error(f"Failed to connect to Qdrant: {remote_error}")
                raise

            logger.warning(
                "Failed to connect to remote Qdrant (%s). Falling back to in-memory Qdrant for development.",
                remote_error,
            )
            await self._safe_close_client()
            self._client = AsyncQdrantClient(location=":memory:")
            await self._client.get_collections()
            self._using_local_fallback = True

        try:
            # Ensure all collections exist
            await self._ensure_collections()
        except Exception:
            await self._safe_close_client()
            self._client = None
            self._using_local_fallback = False
            raise

    async def _safe_close_client(self) -> None:
        """Best-effort close for partially initialized clients."""
        if self._client is None:
            return
        with contextlib.suppress(Exception):
            await self._client.close()

    async def _ensure_collections(self) -> None:
        """Create all collections with named-vector schema and payload indexes.

        Phase 1: Creates collections with hybrid dense+sparse vector support.
        In dev mode, existing collections with incompatible schema should be
        dropped manually via: docker exec pythinker-qdrant-1 rm -rf /qdrant/storage
        """
        existing = await self._client.get_collections()
        existing_names = {c.name for c in existing.collections}

        # Log active collection configuration
        active_collection = self._settings.qdrant_user_knowledge_collection
        logger.info(f"Qdrant active memory collection: {active_collection}")

        # Create multi-collection architecture with named vectors
        for name, dense_params in COLLECTIONS.items():
            if name not in existing_names:
                await self._client.create_collection(
                    collection_name=name,
                    vectors_config={"dense": dense_params},  # HNSW config is in dense_params
                    sparse_vectors_config={"sparse": SPARSE_VECTOR_CONFIG},  # Uses inverted index
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=20000,  # Start HNSW indexing at 20k points
                        memmap_threshold=50000,  # Use disk for collections >50k
                        max_segment_size=200000,  # Balance query speed vs memory
                    ),
                    # NOTE: No collection-level hnsw_config - it's specified per-vector in dense_params
                    # to avoid applying HNSW to sparse vectors (which use inverted indexes)
                )
                logger.info("Created Qdrant collection '%s' with named vectors: dense + sparse", name)
            else:
                logger.debug(f"Qdrant collection '{name}' already exists")

        # Create payload indexes for filtered search
        for collection_name, fields in COLLECTION_INDEXES.items():
            if collection_name not in existing_names:
                # Skip indexing for collections that don't exist yet (will be created on next startup)
                continue

            for field in fields:
                with contextlib.suppress(Exception):
                    # Index may already exist — suppress duplicates
                    await self._client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                    logger.debug(f"Created payload index on {collection_name}.{field}")

    async def shutdown(self) -> None:
        """Shutdown Qdrant connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._using_local_fallback = False
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
