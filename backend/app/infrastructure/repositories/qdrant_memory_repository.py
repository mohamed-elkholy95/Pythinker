"""Qdrant-based vector search repository for memories.

This module provides high-performance vector similarity search using Qdrant,
replacing the 500-candidate limit of MongoDB's local cosine similarity
with sub-100ms retrieval at any scale.

Phase 1: Named-vector schema with hybrid dense+sparse retrieval support.
"""

import logging
from datetime import datetime

from qdrant_client import models

from app.core.config import get_settings
from app.domain.models.long_term_memory import MemoryImportance, MemoryType
from app.domain.repositories.vector_memory_repository import VectorMemoryRepository, VectorSearchResult
from app.infrastructure.storage.qdrant import get_qdrant

logger = logging.getLogger(__name__)


class QdrantSearchResult:
    """Result from Qdrant vector search."""

    def __init__(
        self,
        memory_id: str,
        relevance_score: float,
        memory_type: str | None = None,
        importance: str | None = None,
    ):
        self.memory_id = memory_id
        self.relevance_score = relevance_score
        self.memory_type = memory_type
        self.importance = importance


class QdrantMemoryRepository(VectorMemoryRepository):
    """Qdrant-based vector search for memories.

    This repository handles only vector operations in Qdrant.
    Full memory documents remain in MongoDB for rich querying.

    Phase 1: Supports named-vector schema with dense + sparse hybrid search.
    """

    def __init__(self):
        self._settings = get_settings()
        # Use user_knowledge collection as primary (Phase 1 migration)
        self._collection = self._settings.qdrant_user_knowledge_collection

    async def upsert_memory(
        self,
        memory_id: str,
        user_id: str,
        embedding: list[float],
        memory_type: str,
        importance: str,
        tags: list[str] | None = None,
        sparse_vector: dict[int, float] | None = None,
        session_id: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        """Store memory embedding in Qdrant with named vectors.

        Args:
            memory_id: Unique identifier matching MongoDB document
            user_id: User who owns this memory
            embedding: Dense vector embedding (1536 dimensions for OpenAI)
            memory_type: Type of memory (fact, preference, etc.)
            importance: Importance level (critical, high, medium, low)
            tags: Optional tags for filtering
            sparse_vector: Optional BM25 sparse vector {index: score}
            session_id: Optional session ID for filtering
            created_at: Optional creation timestamp for temporal filtering
        """
        # Phase 1: Named-vector format
        vectors = {"dense": embedding}

        if sparse_vector:
            # Convert dict to Qdrant SparseVector format
            vectors["sparse"] = models.SparseVector(
                indices=list(sparse_vector.keys()),
                values=list(sparse_vector.values()),
            )

        # Enhanced payload with Phase 1 fields
        payload = {
            "user_id": user_id,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
        }

        if session_id:
            payload["session_id"] = session_id

        if created_at:
            # Store as Unix timestamp for integer indexing
            payload["created_at"] = int(created_at.timestamp())

        await get_qdrant().client.upsert(
            collection_name=self._collection,
            points=[
                models.PointStruct(
                    id=memory_id,
                    vector=vectors,
                    payload=payload,
                )
            ],
        )
        logger.debug(f"Upserted memory {memory_id} to Qdrant with named vectors")

    async def upsert_memories_batch(
        self,
        memories: list[dict],
    ) -> None:
        """Batch upsert multiple memories to Qdrant with named vectors.

        Args:
            memories: List of dicts with keys: memory_id, user_id, embedding,
                     memory_type, importance, tags, sparse_vector (optional),
                     session_id (optional), created_at (optional)
        """
        if not memories:
            return

        points = []
        for mem in memories:
            # Named-vector format
            vectors = {"dense": mem["embedding"]}

            if "sparse_vector" in mem and mem["sparse_vector"]:
                sparse = mem["sparse_vector"]
                vectors["sparse"] = models.SparseVector(
                    indices=list(sparse.keys()),
                    values=list(sparse.values()),
                )

            # Enhanced payload
            payload = {
                "user_id": mem["user_id"],
                "memory_type": mem["memory_type"],
                "importance": mem["importance"],
                "tags": mem.get("tags", []),
            }

            if "session_id" in mem and mem["session_id"]:
                payload["session_id"] = mem["session_id"]

            if "created_at" in mem and mem["created_at"]:
                payload["created_at"] = int(mem["created_at"].timestamp())

            points.append(
                models.PointStruct(
                    id=mem["memory_id"],
                    vector=vectors,
                    payload=payload,
                )
            )

        await get_qdrant().client.upsert(
            collection_name=self._collection,
            points=points,
        )
        logger.info(f"Batch upserted {len(memories)} memories to Qdrant")

    async def search_similar(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int = 10,
        min_score: float = 0.3,
        memory_types: list[MemoryType] | None = None,
        min_importance: MemoryImportance | None = None,
        tags: list[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Search for similar memories using dense vector only.

        Phase 1: Uses named 'dense' vector. For hybrid search, use search_hybrid().

        Args:
            user_id: Filter to this user's memories
            query_vector: Query embedding vector (dense)
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)
            memory_types: Optional filter by memory types
            min_importance: Optional minimum importance level
            tags: Optional filter by tags (any match)

        Returns:
            List of VectorSearchResult with memory_id and relevance_score
        """
        # Build filter conditions
        must_conditions = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]

        if memory_types:
            must_conditions.append(
                models.FieldCondition(
                    key="memory_type",
                    match=models.MatchAny(any=[t.value for t in memory_types]),
                )
            )

        if min_importance:
            # Map importance to numeric for filtering
            importance_order = ["low", "medium", "high", "critical"]
            min_idx = importance_order.index(min_importance.value)
            allowed = importance_order[min_idx:]
            must_conditions.append(
                models.FieldCondition(
                    key="importance",
                    match=models.MatchAny(any=allowed),
                )
            )

        if tags:
            must_conditions.append(
                models.FieldCondition(
                    key="tags",
                    match=models.MatchAny(any=tags),
                )
            )

        # Phase 1: Use named 'dense' vector
        results = await get_qdrant().client.query_points(
            collection_name=self._collection,
            query=query_vector,
            using="dense",  # Named vector
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            score_threshold=min_score,
        )

        return [
            VectorSearchResult(
                memory_id=str(point.id),
                relevance_score=point.score,
                memory_type=point.payload.get("memory_type") if point.payload else None,
                importance=point.payload.get("importance") if point.payload else None,
            )
            for point in results.points
        ]

    async def search_hybrid(
        self,
        user_id: str,
        query_text: str,
        dense_vector: list[float],
        sparse_vector: dict[int, float],
        limit: int = 10,
        min_score: float = 0.3,
        memory_types: list[MemoryType] | None = None,
        min_importance: MemoryImportance | None = None,
        tags: list[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Hybrid search combining dense semantic + sparse keyword retrieval.

        Phase 1: Uses RRF (Reciprocal Rank Fusion) to merge dense and sparse results.

        Args:
            user_id: Filter to this user's memories
            query_text: Original query text (for logging)
            dense_vector: Dense semantic embedding
            sparse_vector: BM25 sparse vector {index: score}
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)
            memory_types: Optional filter by memory types
            min_importance: Optional minimum importance level
            tags: Optional filter by tags (any match)

        Returns:
            List of VectorSearchResult with memory_id and relevance_score
        """
        # Build filter conditions
        must_conditions = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]

        if memory_types:
            must_conditions.append(
                models.FieldCondition(
                    key="memory_type",
                    match=models.MatchAny(any=[t.value for t in memory_types]),
                )
            )

        if min_importance:
            importance_order = ["low", "medium", "high", "critical"]
            min_idx = importance_order.index(min_importance.value)
            allowed = importance_order[min_idx:]
            must_conditions.append(
                models.FieldCondition(
                    key="importance",
                    match=models.MatchAny(any=allowed),
                )
            )

        if tags:
            must_conditions.append(
                models.FieldCondition(
                    key="tags",
                    match=models.MatchAny(any=tags),
                )
            )

        # Convert sparse dict to SparseVector
        sparse_vec = models.SparseVector(
            indices=list(sparse_vector.keys()),
            values=list(sparse_vector.values()),
        )

        # Hybrid query with RRF fusion
        results = await get_qdrant().client.query_points(
            collection_name=self._collection,
            prefetch=[
                # Sparse prefetch (BM25 keyword search)
                models.Prefetch(
                    query=sparse_vec,
                    using="sparse",
                    limit=limit * 2,  # Fetch 2x for fusion
                ),
                # Dense prefetch (semantic search)
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=limit * 2,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),  # Reciprocal Rank Fusion
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            score_threshold=min_score,
        )

        logger.debug(f"Hybrid search for '{query_text[:50]}...' returned {len(results.points)} results")

        return [
            VectorSearchResult(
                memory_id=str(point.id),
                relevance_score=point.score,
                memory_type=point.payload.get("memory_type") if point.payload else None,
                importance=point.payload.get("importance") if point.payload else None,
            )
            for point in results.points
        ]

    async def delete_memory(self, memory_id: str) -> None:
        """Delete a single memory from Qdrant.

        Args:
            memory_id: ID of memory to delete
        """
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.PointIdsList(points=[memory_id]),
        )
        logger.debug(f"Deleted memory {memory_id} from Qdrant")

    async def delete_memories_batch(self, memory_ids: list[str]) -> None:
        """Delete multiple memories from Qdrant.

        Args:
            memory_ids: List of memory IDs to delete
        """
        if not memory_ids:
            return

        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.PointIdsList(points=memory_ids),
        )
        logger.info(f"Batch deleted {len(memory_ids)} memories from Qdrant")

    async def delete_user_memories(self, user_id: str) -> None:
        """Delete all memories for a user.

        Args:
            user_id: User whose memories to delete
        """
        await get_qdrant().client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
                )
            ),
        )
        logger.info(f"Deleted all memories for user {user_id} from Qdrant")

    async def get_memory_count(self, user_id: str | None = None) -> int:
        """Get count of memories in Qdrant.

        Args:
            user_id: Optional filter by user

        Returns:
            Number of memories
        """
        if user_id:
            result = await get_qdrant().client.count(
                collection_name=self._collection,
                count_filter=models.Filter(
                    must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
                ),
            )
        else:
            result = await get_qdrant().client.count(
                collection_name=self._collection,
            )
        return result.count

    async def memory_exists(self, memory_id: str) -> bool:
        """Check if a memory exists in Qdrant.

        Args:
            memory_id: ID to check

        Returns:
            True if memory exists
        """
        result = await get_qdrant().client.retrieve(
            collection_name=self._collection,
            ids=[memory_id],
        )
        return len(result) > 0
