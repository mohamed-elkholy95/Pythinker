"""Qdrant-based vector search repository for memories.

This module provides high-performance vector similarity search using Qdrant,
replacing the 500-candidate limit of MongoDB's local cosine similarity
with sub-100ms retrieval at any scale.
"""

import logging

from qdrant_client import models

from app.core.config import get_settings
from app.domain.models.long_term_memory import MemoryImportance, MemoryType
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


class QdrantMemoryRepository:
    """Qdrant-based vector search for memories.

    This repository handles only vector operations in Qdrant.
    Full memory documents remain in MongoDB for rich querying.
    """

    def __init__(self):
        self._settings = get_settings()
        self._collection = self._settings.qdrant_collection

    async def upsert_memory(
        self,
        memory_id: str,
        user_id: str,
        embedding: list[float],
        memory_type: str,
        importance: str,
        tags: list[str] | None = None,
    ) -> None:
        """Store memory embedding in Qdrant.

        Args:
            memory_id: Unique identifier matching MongoDB document
            user_id: User who owns this memory
            embedding: Vector embedding (1536 dimensions for OpenAI)
            memory_type: Type of memory (fact, preference, etc.)
            importance: Importance level (critical, high, medium, low)
            tags: Optional tags for filtering
        """
        await get_qdrant().client.upsert(
            collection_name=self._collection,
            points=[
                models.PointStruct(
                    id=memory_id,
                    vector=embedding,
                    payload={
                        "user_id": user_id,
                        "memory_type": memory_type,
                        "importance": importance,
                        "tags": tags or [],
                    },
                )
            ],
        )
        logger.debug(f"Upserted memory {memory_id} to Qdrant")

    async def upsert_memories_batch(
        self,
        memories: list[dict],
    ) -> None:
        """Batch upsert multiple memories to Qdrant.

        Args:
            memories: List of dicts with keys: memory_id, user_id, embedding,
                     memory_type, importance, tags
        """
        if not memories:
            return

        points = [
            models.PointStruct(
                id=mem["memory_id"],
                vector=mem["embedding"],
                payload={
                    "user_id": mem["user_id"],
                    "memory_type": mem["memory_type"],
                    "importance": mem["importance"],
                    "tags": mem.get("tags", []),
                },
            )
            for mem in memories
        ]

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
    ) -> list[QdrantSearchResult]:
        """Search for similar memories using Qdrant.

        Args:
            user_id: Filter to this user's memories
            query_vector: Query embedding vector
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)
            memory_types: Optional filter by memory types
            min_importance: Optional minimum importance level
            tags: Optional filter by tags (any match)

        Returns:
            List of QdrantSearchResult with memory_id and relevance_score
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

        results = await get_qdrant().client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            score_threshold=min_score,
        )

        return [
            QdrantSearchResult(
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
