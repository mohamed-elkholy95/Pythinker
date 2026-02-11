"""Domain models for sync outbox pattern.

The outbox pattern ensures reliable MongoDB → Qdrant synchronization by:
1. Storing sync operations in MongoDB first (transactional)
2. Processing them asynchronously with retry logic
3. Moving failed entries to dead-letter queue after max retries
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OutboxOperation(str, Enum):
    """Types of sync operations."""

    UPSERT = "upsert"
    DELETE = "delete"
    BATCH_UPSERT = "batch_upsert"
    BATCH_DELETE = "batch_delete"


class OutboxStatus(str, Enum):
    """Outbox entry processing status."""

    PENDING = "pending"  # Waiting to be processed
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully synced to Qdrant
    FAILED = "failed"  # Failed after max retries (moved to DLQ)


class OutboxEntry(BaseModel):
    """Outbox entry for reliable sync operations.

    Stores operations to be synced from MongoDB to Qdrant with retry logic.
    """

    id: str | None = None  # MongoDB ObjectId
    operation: OutboxOperation
    collection_name: str  # Target Qdrant collection
    payload: dict[str, Any]  # Operation-specific data (memory_id, vectors, etc.)

    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    max_retries: int = 6  # Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s
    next_retry_at: datetime | None = None

    error_message: str | None = None
    last_error_at: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    class Config:
        use_enum_values = True

    def can_retry(self) -> bool:
        """Check if this entry can be retried."""
        if self.status == OutboxStatus.FAILED:
            return False
        if self.retry_count >= self.max_retries:
            return False
        if self.next_retry_at and self.next_retry_at > datetime.utcnow():
            return False
        return True

    def calculate_next_retry(self) -> datetime:
        """Calculate next retry time with exponential backoff.

        Backoff schedule: 1s, 2s, 4s, 8s, 16s, 32s (max)
        """
        delay_seconds = min(2**self.retry_count, 32)
        return datetime.utcnow() + timedelta(seconds=delay_seconds)

    def mark_processing(self) -> None:
        """Mark entry as currently being processed."""
        self.status = OutboxStatus.PROCESSING
        self.updated_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark entry as successfully completed."""
        self.status = OutboxStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.error_message = None

    def mark_failed(self, error: str) -> None:
        """Mark entry as failed and calculate next retry or move to DLQ."""
        self.retry_count += 1
        self.error_message = error
        self.last_error_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        if self.retry_count >= self.max_retries:
            self.status = OutboxStatus.FAILED
            self.next_retry_at = None
        else:
            self.status = OutboxStatus.PENDING
            self.next_retry_at = self.calculate_next_retry()


class DeadLetterEntry(BaseModel):
    """Dead-letter queue entry for permanently failed sync operations.

    Stores operations that exceeded max retries for manual intervention.
    """

    id: str | None = None  # MongoDB ObjectId
    original_outbox_id: str  # Reference to original outbox entry
    operation: OutboxOperation
    collection_name: str
    payload: dict[str, Any]

    retry_count: int  # How many times it was retried
    final_error: str  # Last error message
    error_history: list[dict[str, Any]] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    original_created_at: datetime  # When original outbox entry was created

    class Config:
        use_enum_values = True


class OutboxCreate(BaseModel):
    """Schema for creating new outbox entries."""

    operation: OutboxOperation
    collection_name: str
    payload: dict[str, Any]
    max_retries: int = 6


class OutboxUpdate(BaseModel):
    """Schema for updating outbox entries."""

    status: OutboxStatus | None = None
    retry_count: int | None = None
    next_retry_at: datetime | None = None
    error_message: str | None = None
    last_error_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        use_enum_values = True
