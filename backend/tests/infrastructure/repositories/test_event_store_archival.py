"""Tests for event store archival (Phase 1A)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.repositories.event_store_repository import EventStoreRepository


@pytest.fixture
def repo():
    return EventStoreRepository()


class TestArchiveEventsBefore:
    """Tests for EventStoreRepository.archive_events_before()."""

    @pytest.mark.asyncio
    async def test_archive_moves_old_events_to_archive_collection(self, repo):
        """Events older than cutoff are copied to archive and deleted from source."""
        cutoff = datetime.now(UTC) - timedelta(days=90)
        old_events = [
            {"_id": f"id_{i}", "event_id": f"evt_{i}", "timestamp": cutoff - timedelta(days=i + 1)} for i in range(3)
        ]

        # Use MagicMock for the collection since find() returns a sync cursor
        mock_source = MagicMock()
        mock_archive = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_archive)
        mock_source.database = mock_db

        # find().sort().limit() returns a cursor; to_list() is async
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(side_effect=[old_events, []])
        mock_source.find.return_value.sort.return_value.limit.return_value = mock_cursor

        mock_delete_result = MagicMock()
        mock_delete_result.deleted_count = 3
        mock_source.delete_many = AsyncMock(return_value=mock_delete_result)
        mock_archive.insert_many = AsyncMock()

        with patch(
            "app.infrastructure.repositories.event_store_repository.AgentEventDocument.get_pymongo_collection",
            return_value=mock_source,
        ):
            archived = await repo.archive_events_before(cutoff)

        assert archived == 3
        mock_archive.insert_many.assert_called_once()
        mock_source.delete_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_returns_zero_when_no_old_events(self, repo):
        """No events older than cutoff → 0 archived."""
        cutoff = datetime.now(UTC)

        mock_source = MagicMock()
        mock_db = MagicMock()
        mock_source.database = mock_db
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_source.find.return_value.sort.return_value.limit.return_value = mock_cursor

        with patch(
            "app.infrastructure.repositories.event_store_repository.AgentEventDocument.get_pymongo_collection",
            return_value=mock_source,
        ):
            archived = await repo.archive_events_before(cutoff)

        assert archived == 0

    @pytest.mark.asyncio
    async def test_archive_processes_multiple_batches(self, repo):
        """Large event sets are processed in batch_size chunks."""
        cutoff = datetime.now(UTC)

        batch1 = [{"_id": f"id_{i}", "timestamp": cutoff - timedelta(days=1)} for i in range(5)]
        batch2 = [{"_id": f"id_{i + 5}", "timestamp": cutoff - timedelta(days=1)} for i in range(3)]

        mock_source = MagicMock()
        mock_archive = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_archive)
        mock_source.database = mock_db

        # After first batch, switch to second
        call_count = 0

        def get_cursor(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = AsyncMock()
            if call_count == 1:
                mock.to_list = AsyncMock(return_value=batch1)
            else:
                mock.to_list = AsyncMock(return_value=batch2)
            return mock

        mock_source.find.return_value.sort.return_value.limit = get_cursor

        mock_delete_result = MagicMock()
        mock_delete_result.deleted_count = 5
        mock_delete_result2 = MagicMock()
        mock_delete_result2.deleted_count = 3
        mock_source.delete_many = AsyncMock(side_effect=[mock_delete_result, mock_delete_result2])
        mock_archive.insert_many = AsyncMock()

        with patch(
            "app.infrastructure.repositories.event_store_repository.AgentEventDocument.get_pymongo_collection",
            return_value=mock_source,
        ):
            archived = await repo.archive_events_before(cutoff, batch_size=5)

        assert archived == 8
        assert mock_archive.insert_many.call_count == 2
