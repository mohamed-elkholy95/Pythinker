"""Repository protocol for sync outbox operations.

Defines the abstract contract for sync outbox persistence,
supporting the outbox pattern for reliable MongoDB -> Qdrant synchronization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.domain.models.sync_outbox import (
    DeadLetterEntry,
    OutboxCreate,
    OutboxEntry,
    OutboxUpdate,
)


class SyncOutboxRepository(ABC):
    """Abstract repository for sync outbox operations.

    Implementations should handle:
    - Creating outbox entries for async sync
    - Retrieving pending entries for processing
    - Marking entries as processing/completed/failed
    - Moving permanently failed entries to dead-letter queue
    - Providing statistics on outbox state
    """

    @abstractmethod
    async def create(self, entry: OutboxCreate) -> OutboxEntry:
        """Create a new outbox entry.

        Args:
            entry: Outbox creation parameters

        Returns:
            Created outbox entry with generated ID
        """
        ...

    @abstractmethod
    async def get_pending_entries(self, limit: int = 100) -> list[OutboxEntry]:
        """Get pending outbox entries ready for processing.

        Returns entries that are:
        - Status PENDING
        - Either no next_retry_at or next_retry_at <= now
        - Ordered by created_at (FIFO)

        Args:
            limit: Maximum entries to return

        Returns:
            List of pending outbox entries
        """
        ...

    @abstractmethod
    async def update(self, entry_id: str, update: OutboxUpdate) -> bool:
        """Update an outbox entry.

        Args:
            entry_id: ID of entry to update
            update: Fields to update

        Returns:
            True if entry was updated
        """
        ...

    @abstractmethod
    async def mark_processing(self, entry_id: str) -> bool:
        """Mark entry as currently being processed.

        Args:
            entry_id: ID of entry to mark

        Returns:
            True if entry was updated
        """
        ...

    @abstractmethod
    async def mark_completed(self, entry_id: str) -> bool:
        """Mark entry as successfully completed.

        Args:
            entry_id: ID of entry to mark

        Returns:
            True if entry was updated
        """
        ...

    @abstractmethod
    async def mark_failed(
        self,
        entry_id: str,
        error: str,
        retry_count: int,
        next_retry_at: datetime | None,
    ) -> bool:
        """Mark entry as failed with retry information.

        Args:
            entry_id: ID of entry to mark
            error: Error message
            retry_count: Current retry count
            next_retry_at: When to retry next (None = no more retries)

        Returns:
            True if entry was updated
        """
        ...

    @abstractmethod
    async def move_to_dead_letter_queue(self, entry: OutboxEntry) -> DeadLetterEntry:
        """Move failed entry to dead-letter queue.

        Args:
            entry: Failed outbox entry to move

        Returns:
            Created dead-letter queue entry
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Get outbox statistics.

        Returns:
            Dict with counts per status and DLQ count
        """
        ...
