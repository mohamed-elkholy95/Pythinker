"""Tests for MongoDB $slice projection in event pagination (Phase 5A)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.models.documents import SessionDocument
from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository


@pytest.fixture
def repo():
    """Create a MongoSessionRepository instance."""
    # The repository uses SessionDocument class methods, so no constructor args needed
    return MongoSessionRepository()


class TestEventPaginationProjection:
    """Tests that pagination uses MongoDB $slice instead of Python slicing."""

    @pytest.mark.asyncio
    async def test_get_events_paginated_uses_slice_projection(self, repo):
        """Verify the query uses $slice projection."""
        events = [{"type": "message", "content": f"msg_{i}"} for i in range(5)]
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value={"events": events})

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            result = await repo.get_events_paginated("session-1", offset=0, limit=5)

        assert result == events
        # Verify $slice projection was used
        call_args = mock_collection.find_one.call_args
        assert call_args[0][0] == {"session_id": "session-1"}
        projection = call_args[0][1]
        assert "events" in projection
        assert projection["events"] == {"$slice": [0, 5]}

    @pytest.mark.asyncio
    async def test_get_events_paginated_with_offset(self, repo):
        """$slice correctly handles offset for pagination."""
        events = [{"type": "tool", "name": f"tool_{i}"} for i in range(3)]
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value={"events": events})

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            await repo.get_events_paginated("session-1", offset=10, limit=3)

        call_args = mock_collection.find_one.call_args
        projection = call_args[0][1]
        assert projection["events"] == {"$slice": [10, 3]}

    @pytest.mark.asyncio
    async def test_get_events_paginated_returns_empty_for_missing_session(self, repo):
        """Missing session returns empty list."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            result = await repo.get_events_paginated("nonexistent", offset=0, limit=100)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_event_count_uses_size_aggregation(self, repo):
        """Event count uses $size aggregation instead of loading full document."""
        mock_collection = AsyncMock()

        async def mock_aggregate(pipeline):
            yield {"count": 42}

        mock_collection.aggregate = mock_aggregate

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            count = await repo.get_event_count("session-1")

        assert count == 42

    @pytest.mark.asyncio
    async def test_get_event_count_returns_zero_for_missing_session(self, repo):
        """Missing session returns 0 event count."""
        mock_collection = AsyncMock()

        async def mock_aggregate(pipeline):
            return
            yield  # Make it an async generator that yields nothing

        mock_collection.aggregate = mock_aggregate

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            count = await repo.get_event_count("nonexistent")

        assert count == 0
