"""Domain models for sync outbox pattern.

The outbox pattern ensures reliable MongoDB → Qdrant synchronization by:
1. Storing sync operations in MongoDB first (transactional)
2. Processing them asynchronously with retry logic
3. Moving failed entries to dead-letter queue after max retries
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.retry import RetryConfig, calculate_delay


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

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)

    def can_retry(self) -> bool:
        """Check if this entry can be retried."""
        if self.status == OutboxStatus.FAILED:
            return False
        if self.retry_count >= self.max_retries:
            return False
        return not (self.next_retry_at and self.next_retry_at > datetime.now(UTC))

    def calculate_next_retry(self) -> datetime:
        """Calculate next retry time with exponential backoff using centralized retry logic.

        Backoff schedule: 1s, 2s, 4s, 8s, 16s, 32s (max)
        """
        # Use centralized exponential backoff (base=1.0, max=32s)
        retry_config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=32.0,
            jitter=True,
        )
        delay_seconds = calculate_delay(self.retry_count + 1, retry_config)
        return datetime.now(UTC) + timedelta(seconds=delay_seconds)

    def mark_processing(self) -> None:
        """Mark entry as currently being processed."""
        self.status = OutboxStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def mark_completed(self) -> None:
        """Mark entry as successfully completed."""
        self.status = OutboxStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.error_message = None

    def mark_failed(self, error: str) -> None:
        """Mark entry as failed and calculate next retry or move to DLQ."""
        self.retry_count += 1
        self.error_message = error
        self.last_error_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

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

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_created_at: datetime  # When original outbox entry was created

    model_config = ConfigDict(use_enum_values=True)


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

    model_config = ConfigDict(use_enum_values=True)
