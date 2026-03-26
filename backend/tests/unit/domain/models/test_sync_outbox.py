"""Tests for sync outbox models (app.domain.models.sync_outbox).

Covers OutboxOperation, OutboxStatus, OutboxEntry lifecycle
(can_retry, mark_processing, mark_completed, mark_failed),
exponential backoff calculation, DeadLetterEntry, and schemas.
"""

from datetime import UTC, datetime, timedelta

from app.domain.models.sync_outbox import (
    DeadLetterEntry,
    OutboxCreate,
    OutboxEntry,
    OutboxOperation,
    OutboxStatus,
    OutboxUpdate,
)


class TestOutboxEnums:
    def test_operation_values(self) -> None:
        assert OutboxOperation.UPSERT == "upsert"
        assert OutboxOperation.DELETE == "delete"
        assert OutboxOperation.BATCH_UPSERT == "batch_upsert"
        assert OutboxOperation.BATCH_DELETE == "batch_delete"

    def test_status_values(self) -> None:
        assert OutboxStatus.PENDING == "pending"
        assert OutboxStatus.PROCESSING == "processing"
        assert OutboxStatus.COMPLETED == "completed"
        assert OutboxStatus.FAILED == "failed"


class TestOutboxEntry:
    def _make_entry(self) -> OutboxEntry:
        return OutboxEntry(
            operation=OutboxOperation.UPSERT,
            collection_name="memories",
            payload={"memory_id": "m-1", "vector": [0.1, 0.2]},
        )

    def test_defaults(self) -> None:
        entry = self._make_entry()
        assert entry.status == "pending"
        assert entry.retry_count == 0
        assert entry.max_retries == 6
        assert entry.error_message is None
        assert entry.completed_at is None

    def test_can_retry_pending(self) -> None:
        entry = self._make_entry()
        assert entry.can_retry() is True

    def test_can_retry_failed(self) -> None:
        entry = self._make_entry()
        entry.status = OutboxStatus.FAILED
        assert entry.can_retry() is False

    def test_can_retry_max_retries_exceeded(self) -> None:
        entry = self._make_entry()
        entry.retry_count = 6
        assert entry.can_retry() is False

    def test_can_retry_future_retry_time(self) -> None:
        entry = self._make_entry()
        entry.next_retry_at = datetime.now(UTC) + timedelta(hours=1)
        assert entry.can_retry() is False

    def test_can_retry_past_retry_time(self) -> None:
        entry = self._make_entry()
        entry.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        assert entry.can_retry() is True

    def test_mark_processing(self) -> None:
        entry = self._make_entry()
        entry.mark_processing()
        assert entry.status == "processing"

    def test_mark_completed(self) -> None:
        entry = self._make_entry()
        entry.error_message = "previous error"
        entry.mark_completed()
        assert entry.status == "completed"
        assert entry.completed_at is not None
        assert entry.error_message is None

    def test_mark_failed_increments_retry(self) -> None:
        entry = self._make_entry()
        entry.mark_failed("Connection refused")
        assert entry.retry_count == 1
        assert entry.error_message == "Connection refused"
        assert entry.status == "pending"
        assert entry.next_retry_at is not None

    def test_mark_failed_moves_to_dlq_after_max(self) -> None:
        entry = self._make_entry()
        entry.retry_count = 5  # One more will hit max_retries=6
        entry.mark_failed("Final failure")
        assert entry.retry_count == 6
        assert entry.status == "failed"
        assert entry.next_retry_at is None

    def test_backoff_increases_exponentially(self) -> None:
        entry = self._make_entry()
        delays = []
        for i in range(6):
            entry.retry_count = i
            retry_time = entry.calculate_next_retry()
            delay = (retry_time - datetime.now(UTC)).total_seconds()
            delays.append(delay)
        # Each delay should be roughly double the previous (with jitter)
        for i in range(1, len(delays)):
            # Allow generous margin for jitter
            assert delays[i] > delays[i - 1] * 0.5

    def test_backoff_max_cap(self) -> None:
        entry = self._make_entry()
        entry.retry_count = 10  # Way past max
        retry_time = entry.calculate_next_retry()
        delay = (retry_time - datetime.now(UTC)).total_seconds()
        # Should be capped at ~32s (± jitter)
        assert delay < 45.0


class TestDeadLetterEntry:
    def test_creation(self) -> None:
        entry = DeadLetterEntry(
            original_outbox_id="outbox-1",
            operation=OutboxOperation.UPSERT,
            collection_name="memories",
            payload={"memory_id": "m-1"},
            retry_count=6,
            final_error="Connection refused after 6 retries",
            original_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert entry.original_outbox_id == "outbox-1"
        assert entry.retry_count == 6
        assert entry.error_history == []


class TestOutboxSchemas:
    def test_outbox_create(self) -> None:
        create = OutboxCreate(
            operation=OutboxOperation.DELETE,
            collection_name="sessions",
            payload={"session_id": "s-1"},
        )
        assert create.max_retries == 6

    def test_outbox_update(self) -> None:
        update = OutboxUpdate(status=OutboxStatus.COMPLETED)
        assert update.status == "completed"
        assert update.retry_count is None
