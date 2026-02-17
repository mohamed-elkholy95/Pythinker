"""Repository interface for vector-based memory search.

Defines the contract for vector similarity search implementations,
supporting fast retrieval of semantically similar memories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.long_term_memory import MemoryImportance, MemoryType


@dataclass
class VectorSearchResult:
    """Result from vector similarity search."""

    memory_id: str
    relevance_score: float
    memory_type: str | None = None
    importance: str | None = None


class VectorMemoryRepository(ABC):
    """Abstract repository for vector-based memory search.

    Implementations should handle:
    - Vector storage and retrieval
    - Similarity search with filters
    - Batch operations for efficiency
    """

    @abstractmethod
    async def upsert_memory(
        self,
        memory_id: str,
        user_id: str,
        embedding: list[float],
        memory_type: str,
        importance: str,
        tags: list[str] | None = None,
        sparse_vector: dict[int, float] | dict[str, float] | None = None,
        session_id: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        """Store memory embedding in vector store.

        Args:
            memory_id: Unique identifier matching MongoDB document
            user_id: User who owns this memory
            embedding: Vector embedding
            memory_type: Type of memory (fact, preference, etc.)
            importance: Importance level (critical, high, medium, low)
            tags: Optional tags for filtering
            sparse_vector: Optional BM25 sparse vector {index: score}
            session_id: Optional session ID for filtering
            created_at: Optional creation timestamp for temporal filtering
        """
        ...

    @abstractmethod
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
        """Search for similar memories using vector similarity.

        Args:
            user_id: Filter to this user's memories
            query_vector: Query embedding vector
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)
            memory_types: Optional filter by memory types
            min_importance: Optional minimum importance level
            tags: Optional filter by tags (any match)

        Returns:
            List of VectorSearchResult with memory_id and relevance_score
        """
        ...

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> None:
        """Delete a memory from the vector store.

        Args:
            memory_id: ID of memory to delete
        """
        ...

    @abstractmethod
    async def delete_user_memories(self, user_id: str) -> None:
        """Delete all memories for a user from the vector store.

        Args:
            user_id: User whose memories to delete
        """
        ...

    @abstractmethod
    async def upsert_memories_batch(self, memories: list[dict]) -> None:
        """Batch upsert multiple memories to the vector store.

        Args:
            memories: List of dicts with keys: memory_id, user_id, embedding,
                     memory_type, importance, tags, sparse_vector (optional),
                     session_id (optional), created_at (optional)
        """
        ...

    @abstractmethod
    async def delete_memories_batch(self, memory_ids: list[str]) -> None:
        """Delete multiple memories from the vector store.

        Args:
            memory_ids: List of memory IDs to delete
        """
        ...

    @abstractmethod
    async def memory_exists(self, memory_id: str) -> bool:
        """Check if a memory exists in the vector store.

        Args:
            memory_id: ID to check

        Returns:
            True if memory exists
        """
        ...


# ===== Module-level Repository Singleton =====

_vector_memory_repo: VectorMemoryRepository | None = None


def set_vector_memory_repository(repo: VectorMemoryRepository) -> None:
    """Set the global vector memory repository instance.

    This should be called during application startup to inject the
    infrastructure implementation.

    Args:
        repo: VectorMemoryRepository implementation to use globally
    """
    global _vector_memory_repo
    _vector_memory_repo = repo


def get_vector_memory_repository() -> VectorMemoryRepository | None:
    """Get the global vector memory repository instance.

    Returns the configured repository or None if none is configured.
    Domain services should check for None and fall back appropriately.

    Returns:
        VectorMemoryRepository implementation or None
    """
    return _vector_memory_repo
