# Qdrant Sparse Vectors - Complete Implementation Guide

**Date**: 2026-02-11
**Status**: Research Complete - Ready for Implementation

## Problem Identified

The original code was **incorrectly mixing** dense and sparse vectors in the same `vectors_config`:

```python
# ❌ WRONG - This causes the 'size' attribute error
COLLECTIONS = {
    "user_knowledge": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
        "sparse": models.SparseVectorParams(),  # Don't mix in same config!
    },
}

client.create_collection(
    collection_name="user_knowledge",
    vectors_config=COLLECTIONS["user_knowledge"],  # ❌ ERROR
)
```

**Why it failed**: Qdrant expects `vectors_config` (dense) and `sparse_vectors_config` (sparse) as **separate parameters**.

## Correct Implementation

### Option 1: Basic Sparse Vectors (Recommended)

```python
# File: backend/app/infrastructure/storage/qdrant.py

from qdrant_client import AsyncQdrantClient, models

# Separate dense and sparse configurations
DENSE_VECTORS_CONFIG = {
    "user_knowledge": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    },
    "task_artifacts": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    },
    "tool_logs": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    },
    "semantic_cache": {
        "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
    },
}

SPARSE_VECTORS_CONFIG = {
    "user_knowledge": {
        "sparse": models.SparseVectorParams(),
    },
    "task_artifacts": {
        "sparse": models.SparseVectorParams(),
    },
    "tool_logs": {
        "sparse": models.SparseVectorParams(),
    },
    "semantic_cache": {
        "sparse": models.SparseVectorParams(),
    },
}

# Create collection with both
await client.create_collection(
    collection_name="user_knowledge",
    vectors_config=DENSE_VECTORS_CONFIG["user_knowledge"],      # ✅ Dense only
    sparse_vectors_config=SPARSE_VECTORS_CONFIG["user_knowledge"],  # ✅ Sparse only
)
```

### Option 2: BM25 with IDF Modifier

For better text search with BM25 + IDF scoring:

```python
SPARSE_VECTORS_CONFIG = {
    "user_knowledge": {
        "sparse": models.SparseVectorParams(
            modifier=models.Modifier.IDF  # IDF-based rescoring
        ),
    },
}
```

### Option 3: Advanced Configuration

With index parameters for performance tuning:

```python
SPARSE_VECTORS_CONFIG = {
    "user_knowledge": {
        "sparse": models.SparseVectorParams(
            index=models.SparseIndexParams(
                on_disk=False,  # Keep in memory for speed
            ),
            modifier=models.Modifier.IDF,
        ),
    },
}
```

## Full Working Example

Based on [official Qdrant documentation](https://qdrant.tech/documentation/beginner-tutorials/hybrid-search-fastembed):

```python
from qdrant_client import AsyncQdrantClient, models

async def create_hybrid_collection():
    client = AsyncQdrantClient(url="http://localhost:6333")

    collection_name = "user_knowledge"

    # Check if collection exists
    if not await client.collection_exists(collection_name):
        await client.create_collection(
            collection_name=collection_name,
            # Dense vectors configuration
            vectors_config={
                "dense": models.VectorParams(
                    size=1536,
                    distance=models.Distance.COSINE
                )
            },
            # Sparse vectors configuration (separate parameter!)
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF
                )
            },
        )
        print(f"✅ Created collection '{collection_name}' with hybrid search")
```

## Implementation Steps

### Step 1: Update Collection Definitions

**File**: `backend/app/infrastructure/storage/qdrant.py`

```python
import contextlib
import logging
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Collection names
COLLECTIONS = [
    "user_knowledge",
    "task_artifacts",
    "tool_logs",
    "semantic_cache",
]

# Dense vector configuration (1536 = OpenAI text-embedding-3-small)
DENSE_VECTOR_CONFIG = models.VectorParams(size=1536, distance=models.Distance.COSINE)

# Sparse vector configuration (BM25 + IDF)
SPARSE_VECTOR_CONFIG = models.SparseVectorParams(
    modifier=models.Modifier.IDF,
    index=models.SparseIndexParams(on_disk=False),
)

# Payload indexes for fast filtered search
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
        """Create all collections with hybrid dense+sparse vector support."""
        existing = await self._client.get_collections()
        existing_names = {c.name for c in existing.collections}

        # Log active collection configuration
        active_collection = self._settings.qdrant_user_knowledge_collection
        logger.info(f"Qdrant active memory collection: {active_collection}")

        # Create collections with hybrid search support
        for collection_name in COLLECTIONS:
            if collection_name not in existing_names:
                await self._client.create_collection(
                    collection_name=collection_name,
                    # Dense vectors (semantic search)
                    vectors_config={
                        "dense": DENSE_VECTOR_CONFIG,
                    },
                    # Sparse vectors (keyword search / BM25)
                    sparse_vectors_config={
                        "sparse": SPARSE_VECTOR_CONFIG,
                    },
                    # Performance optimizations
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=20000,
                        memmap_threshold=50000,
                        max_segment_size=200000,
                    ),
                )
                logger.info(
                    f"Created Qdrant collection '{collection_name}' "
                    f"with hybrid search (dense + sparse)"
                )
            else:
                logger.debug(f"Qdrant collection '{collection_name}' already exists")

        # Create payload indexes for filtered search
        for collection_name, fields in COLLECTION_INDEXES.items():
            if collection_name not in existing_names:
                continue

            for field in fields:
                with contextlib.suppress(Exception):
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
            logger.info("Disconnected from Qdrant")
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
```

### Step 2: Update Repository to Use Sparse Vectors

**File**: `backend/app/infrastructure/repositories/qdrant_memory_repository.py`

The repository code already handles sparse vectors correctly:

```python
# Inserting with sparse vectors
vectors = {
    "dense": dense_embedding,  # List[float]
}

if sparse_vector:
    # BM25 sparse vector {index: score}
    vectors["sparse"] = models.SparseVector(
        indices=list(sparse_vector.keys()),
        values=list(sparse_vector.values()),
    )

await client.upsert(
    collection_name="user_knowledge",
    points=[
        models.PointStruct(
            id=memory_id,
            vector=vectors,  # Both dense and sparse
            payload=payload,
        )
    ],
)
```

### Step 3: Hybrid Search Query

```python
# Hybrid search combining dense + sparse
search_result = await client.query_points(
    collection_name="user_knowledge",
    prefetch=[
        # Prefetch from dense vectors
        models.Prefetch(
            query=dense_embedding,
            using="dense",
            limit=20,
        ),
        # Prefetch from sparse vectors
        models.Prefetch(
            query=models.SparseVector(
                indices=list(sparse_vector.keys()),
                values=list(sparse_vector.values()),
            ),
            using="sparse",
            limit=20,
        ),
    ],
    # Fusion strategy (RRF = Reciprocal Rank Fusion)
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=10,
)
```

## Testing & Verification

### 1. Reset Collections with New Schema

```bash
# Run reset script to recreate collections with hybrid support
docker exec pythinker-backend-1 python scripts/reset_qdrant_collections.py
```

### 2. Verify Collection Schema

```bash
# Check collection configuration
curl http://localhost:6333/collections/user_knowledge | jq '.result.config.params'

# Expected output:
# {
#   "vectors": {
#     "dense": {
#       "size": 1536,
#       "distance": "Cosine"
#     }
#   },
#   "sparse_vectors": {
#     "sparse": {
#       "modifier": "idf"
#     }
#   }
# }
```

### 3. Test Insertion

```python
# Test inserting a point with both dense and sparse vectors
import asyncio
from qdrant_client import AsyncQdrantClient, models

async def test_hybrid_insert():
    client = AsyncQdrantClient(url="http://localhost:6333")

    # Sample vectors
    dense_vec = [0.1] * 1536
    sparse_vec = {10: 0.5, 25: 0.3, 100: 0.8}  # BM25 term indices

    await client.upsert(
        collection_name="user_knowledge",
        points=[
            models.PointStruct(
                id="test-1",
                vector={
                    "dense": dense_vec,
                    "sparse": models.SparseVector(
                        indices=list(sparse_vec.keys()),
                        values=list(sparse_vec.values()),
                    ),
                },
                payload={"text": "Test memory"},
            )
        ],
    )
    print("✅ Hybrid vector inserted successfully")

asyncio.run(test_hybrid_insert())
```

## Key Takeaways

1. **Separate Configs**: Use `vectors_config` for dense, `sparse_vectors_config` for sparse
2. **Named Vectors**: Both dense and sparse are named ("dense", "sparse")
3. **Modifier**: Use `models.Modifier.IDF` for BM25 + IDF scoring
4. **Index Params**: Configure `on_disk` for memory vs disk tradeoff
5. **Hybrid Search**: Use `Prefetch` + `FusionQuery` with RRF for best results

## References

**Official Documentation:**
- [Qdrant Hybrid Search Tutorial](https://qdrant.tech/documentation/beginner-tutorials/hybrid-search-fastembed)
- [Qdrant Collections Documentation](https://qdrant.tech/documentation/concepts/collections/)
- [Qdrant Python Client](https://python-client.qdrant.tech/)
- [Advanced Hybrid Search with Reranking](https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search)

**Code Examples:**
- [Create Collection with Dense and Sparse Vectors](https://qdrant.tech/documentation/beginner-tutorials/hybrid-search-fastembed)
- [Qdrant Client GitHub](https://github.com/qdrant/qdrant-client)

## Migration Checklist

When ready to implement:

- [ ] Backup existing collections (if any data exists)
- [ ] Update `backend/app/infrastructure/storage/qdrant.py` with new schema
- [ ] Test connection and collection creation
- [ ] Run reset script to recreate collections
- [ ] Verify schema via API
- [ ] Test hybrid insertion
- [ ] Test hybrid search queries
- [ ] Update memory service to generate BM25 sparse vectors
- [ ] Monitor performance and adjust index parameters
- [ ] Update documentation

## Performance Considerations

**Dense Vectors:**
- Size: 1536 (OpenAI embeddings)
- Index: HNSW (fast approximate search)
- Memory: ~6 KB per point

**Sparse Vectors:**
- Size: Variable (typically 50-200 non-zero elements)
- Index: Inverted index (exact keyword matching)
- Memory: ~200 bytes per point

**Total**: ~6.2 KB per point with hybrid vectors

**Recommendation**: Start with `on_disk=False` for speed, switch to `on_disk=True` if memory exceeds available RAM.
