"""Repository protocol for direct memory document operations.

Defines the abstract contract for operations that need direct access
to memory documents in the primary data store (e.g., MongoDB).

Used by the reconciliation job to detect sync inconsistencies and
repair failed synchronization between primary and vector stores.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class MemoriesCollectionProtocol(ABC):
    """Abstract interface for direct memory document operations.

    This protocol abstracts the MongoDB-specific operations that the
    reconciliation job needs, allowing domain services to remain
    decoupled from infrastructure.

    Implementations should handle:
    - Querying memory documents by sync state
    - Updating sync state fields on memory documents
    - Aggregation queries for sync state statistics
    """

    @abstractmethod
    async def find_failed_memories(
        self,
        cutoff: datetime,
        max_sync_attempts: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Find failed memory documents eligible for sync retry.

        Args:
            cutoff: Only include memories with last_sync_attempt before this time
            max_sync_attempts: Maximum sync attempts to include
            limit: Maximum documents to return

        Returns:
            List of memory document dicts with _id, user_id, embedding, etc.
        """
        ...

    @abstractmethod
    async def find_synced_memories_needing_verification(
        self,
        since: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Find recently synced memories that should be verified in vector store.

        Args:
            since: Only include memories updated after this time
            limit: Maximum documents to return

        Returns:
            List of memory document dicts
        """
        ...

    @abstractmethod
    async def update_sync_state(
        self,
        memory_id: str,
        sync_state: str,
        sync_attempts_increment: int = 0,
        last_sync_attempt: datetime | None = None,
    ) -> bool:
        """Update sync state fields on a memory document.

        Args:
            memory_id: ID of the memory document
            sync_state: New sync state value
            sync_attempts_increment: Amount to increment sync_attempts by
            last_sync_attempt: Optional timestamp for last sync attempt

        Returns:
            True if document was updated
        """
        ...

    @abstractmethod
    async def aggregate_sync_states(self) -> dict[str, int]:
        """Aggregate memory documents by sync state.

        Returns:
            Dict mapping sync_state to count
        """
        ...
