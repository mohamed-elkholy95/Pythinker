"""Repository interface for long-term memory persistence.

Defines the contract for memory storage implementations,
supporting both traditional queries and vector similarity search.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.long_term_memory import (
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
    MemoryType,
    MemoryUpdate,
)


class MemoryRepository(ABC):
    """Abstract repository for long-term memory storage.

    Implementations should handle:
    - CRUD operations for memories
    - Vector similarity search (if embeddings provided)
    - Keyword and filter-based search
    - Deduplication
    - Expiration handling
    """

    @abstractmethod
    async def create(self, memory: MemoryEntry) -> MemoryEntry:
        """Create a new memory entry.

        Args:
            memory: The memory entry to create

        Returns:
            Created memory with generated ID
        """
        ...

    @abstractmethod
    async def create_many(self, memories: list[MemoryEntry]) -> list[MemoryEntry]:
        """Create multiple memory entries in batch.

        Args:
            memories: List of memories to create

        Returns:
            List of created memories with IDs
        """
        ...

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> MemoryEntry | None:
        """Get a memory by its ID.

        Args:
            memory_id: Unique memory identifier

        Returns:
            Memory entry or None if not found
        """
        ...

    @abstractmethod
    async def update(self, memory_id: str, update: MemoryUpdate) -> MemoryEntry | None:
        """Update an existing memory.

        Args:
            memory_id: ID of memory to update
            update: Fields to update

        Returns:
            Updated memory or None if not found
        """
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def delete_by_user(self, user_id: str) -> int:
        """Delete all memories for a user.

        Args:
            user_id: User whose memories to delete

        Returns:
            Number of memories deleted
        """
        ...

    @abstractmethod
    async def search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """Search memories using various criteria.

        Supports:
        - Semantic search (if query_text and embeddings available)
        - Keyword matching
        - Type/importance/tag filtering
        - Time-based filtering

        Args:
            query: Search parameters

        Returns:
            List of matching memories with relevance scores
        """
        ...

    @abstractmethod
    async def vector_search(
        self,
        user_id: str,
        embedding: list[float],
        limit: int = 10,
        min_score: float = 0.0,
        memory_types: list[MemoryType] | None = None
    ) -> list[MemorySearchResult]:
        """Search memories by vector similarity.

        Args:
            user_id: User to search for
            embedding: Query embedding vector
            limit: Maximum results
            min_score: Minimum similarity score
            memory_types: Optional type filter

        Returns:
            List of similar memories with scores
        """
        ...

    @abstractmethod
    async def find_duplicates(
        self,
        user_id: str,
        content_hash: str
    ) -> list[MemoryEntry]:
        """Find memories with matching content hash.

        Used for deduplication.

        Args:
            user_id: User to check
            content_hash: Hash of content to find

        Returns:
            List of memories with matching hash
        """
        ...

    @abstractmethod
    async def get_by_entities(
        self,
        user_id: str,
        entities: list[str],
        limit: int = 20
    ) -> list[MemoryEntry]:
        """Get memories mentioning specific entities.

        Args:
            user_id: User to search for
            entities: Entity names to match
            limit: Maximum results

        Returns:
            List of matching memories
        """
        ...

    @abstractmethod
    async def get_recent(
        self,
        user_id: str,
        limit: int = 10,
        memory_types: list[MemoryType] | None = None
    ) -> list[MemoryEntry]:
        """Get most recently created memories.

        Args:
            user_id: User to get memories for
            limit: Maximum results
            memory_types: Optional type filter

        Returns:
            List of recent memories
        """
        ...

    @abstractmethod
    async def get_most_accessed(
        self,
        user_id: str,
        limit: int = 10,
        since: datetime | None = None
    ) -> list[MemoryEntry]:
        """Get most frequently accessed memories.

        Args:
            user_id: User to get memories for
            limit: Maximum results
            since: Only consider accesses after this time

        Returns:
            List of frequently accessed memories
        """
        ...

    @abstractmethod
    async def get_stats(self, user_id: str) -> MemoryStats:
        """Get memory statistics for a user.

        Args:
            user_id: User to get stats for

        Returns:
            Memory statistics
        """
        ...

    @abstractmethod
    async def cleanup_expired(self, user_id: str | None = None) -> int:
        """Remove expired memories.

        Args:
            user_id: Optional user filter (None = all users)

        Returns:
            Number of memories removed
        """
        ...

    @abstractmethod
    async def record_access(self, memory_id: str) -> None:
        """Record that a memory was accessed.

        Updates last_accessed and access_count.

        Args:
            memory_id: ID of accessed memory
        """
        ...

    @abstractmethod
    async def merge_memories(
        self,
        memory_ids: list[str],
        merged_content: str,
        keep_original: bool = False
    ) -> MemoryEntry:
        """Merge multiple memories into one.

        Args:
            memory_ids: IDs of memories to merge
            merged_content: Combined content
            keep_original: Whether to keep originals (mark inactive)

        Returns:
            New merged memory
        """
        ...
