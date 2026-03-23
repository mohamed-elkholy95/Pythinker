import asyncio
import contextlib
import logging
import threading
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _build_dense_vector_config() -> models.VectorParams:
    """Build dense vector config from settings.

    Uses tenant-aware HNSW: m=0 disables global links, payload_m builds
    per-user sub-graphs so filtered queries don't waste traversal steps.
    Requires collection recreation on existing deployments when changing m/payload_m.
    """
    settings = get_settings()
    return models.VectorParams(
        size=1536,
        distance=models.Distance.COSINE,
        hnsw_config=models.HnswConfigDiff(
            m=settings.qdrant_hnsw_m,  # 0 = no global links (tenant-aware)
            payload_m=settings.qdrant_hnsw_payload_m,  # Per-payload sub-graph links
            ef_construct=100,  # Build-time accuracy
            full_scan_threshold=10000,  # Use full scan for <10k points
        ),
    )


# Backward-compatible module-level reference (lazy — rebuilt each time COLLECTIONS is accessed).
# Tests that inspect DENSE_VECTOR_CONFIG directly still work.
DENSE_VECTOR_CONFIG = models.VectorParams(
    size=1536,
    distance=models.Distance.COSINE,
    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100, full_scan_threshold=10000),
)

# Collection names mapped to dense vector params.
# Keep this shape stable for wiring/tests that inspect size/distance directly.
COLLECTIONS: dict[str, models.VectorParams] = {
    "user_knowledge": DENSE_VECTOR_CONFIG,
    "task_artifacts": DENSE_VECTOR_CONFIG,
    "tool_logs": DENSE_VECTOR_CONFIG,
    "semantic_cache": DENSE_VECTOR_CONFIG,
    "conversation_context": DENSE_VECTOR_CONFIG,
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
    "conversation_context": [
        "session_id",
        "user_id",
        "role",
        "event_type",
        "turn_number",
        "created_at",
        "content_hash",
    ],
}

# Fields that require INTEGER index type instead of KEYWORD
INTEGER_INDEX_FIELDS: set[str] = {"turn_number", "created_at"}


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

        max_attempts = 3
        base_delay = 2.0
        remote_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
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
                break
            except Exception as exc:
                remote_error = exc
                await self._safe_close_client()
                self._client = None
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Qdrant connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Final attempt failed — fall through to fallback logic
                logger.warning(
                    "Qdrant connection attempt %d/%d failed: %s. No more retries.",
                    attempt,
                    max_attempts,
                    exc,
                )

        if remote_error is not None and self._client is None:
            can_fallback = getattr(self._settings, "environment", "development") != "production"
            if not can_fallback:
                logger.error(f"Failed to connect to Qdrant: {remote_error}")
                raise remote_error

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

        # Build tenant-aware dense vector config from settings
        dense_params = _build_dense_vector_config()

        # Create multi-collection architecture with named vectors
        for name in COLLECTIONS:
            if name not in existing_names:
                # Quantization config (Phase 5D: ~75% memory savings at >1M points)
                quantization_config = None
                if self._settings.qdrant_quantization_enabled and self._settings.qdrant_quantization_type == "scalar":
                    quantization_config = models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=models.ScalarType.INT8,
                            quantile=0.99,
                            always_ram=True,
                        ),
                    )

                await self._client.create_collection(
                    collection_name=name,
                    vectors_config={"dense": dense_params},  # HNSW config is in dense_params
                    sparse_vectors_config={"sparse": SPARSE_VECTOR_CONFIG},  # Uses inverted index
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=20000,  # Start HNSW indexing at 20k points
                        memmap_threshold=50000,  # Use disk for collections >50k
                        max_segment_size=200000,  # Balance query speed vs memory
                        deleted_threshold=0.2,  # Rebuild segment when 20% deleted
                        flush_interval_sec=300,  # Flush WAL every 5 minutes
                    ),
                    quantization_config=quantization_config,
                    on_disk_payload=True,  # Phase 6: Store payloads on disk for memory efficiency
                    # NOTE: No collection-level hnsw_config - it's specified per-vector in dense_params
                    # to avoid applying HNSW to sparse vectors (which use inverted indexes)
                )
                logger.info("Created Qdrant collection '%s' with named vectors: dense + sparse", name)
            else:
                logger.info(f"Qdrant collection '{name}' already exists")

        # Create payload indexes for filtered search (server Qdrant only)
        # In-memory/local Qdrant does not support payload indexes — skip silently.
        if self._using_local_fallback:
            logger.debug("Skipping payload index creation (in-memory Qdrant)")
            return

        for collection_name, fields in COLLECTION_INDEXES.items():
            if collection_name not in COLLECTIONS:
                continue

            for field in fields:
                with contextlib.suppress(Exception):
                    field_schema = (
                        models.PayloadSchemaType.INTEGER
                        if field in INTEGER_INDEX_FIELDS
                        else models.PayloadSchemaType.KEYWORD
                    )
                    await self._client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=field_schema,
                    )
                    logger.debug(f"Created payload index on {collection_name}.{field} ({field_schema})")

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


_qdrant_init_lock = threading.Lock()


@lru_cache
def get_qdrant() -> QdrantStorage:
    """Get the Qdrant storage instance (thread-safe singleton)."""
    with _qdrant_init_lock:
        return QdrantStorage()
