"""Tests for MongoDB session projection discipline and bounded event array.

Validates that:
- add_event uses $push/$each/$slice to bound the events array
- find_by_id, find_by_id_and_user_id exclude events/files
- add_file, get_file_by_path use files-only projection
- get_event_by_sequence uses $slice projection
- get_event_by_id and get_events_in_range use aggregation $filter
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.exceptions.base import SessionNotFoundException
from app.domain.models.event import BaseEvent
from app.domain.models.file import FileInfo
from app.infrastructure.models.documents import SessionDocument
from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository


@pytest.fixture
def repo():
    return MongoSessionRepository()


@pytest.fixture
def mock_collection():
    """Mock pymongo collection returned by SessionDocument.get_pymongo_collection()."""
    return AsyncMock()


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.mongodb_session_event_limit = 5000
    return settings


class TestBoundedEventArray:
    """Test that add_event uses $push + $each + $slice."""

    @pytest.mark.asyncio
    async def test_add_event_uses_slice(self, repo, mock_settings):
        """add_event should use $push/$each/$slice to bound the array."""
        event = MagicMock(spec=BaseEvent)
        event.model_dump.return_value = {"type": "message", "id": "e1"}

        mock_update_result = MagicMock()
        mock_find_one = MagicMock()
        mock_find_one.update = AsyncMock(return_value=mock_update_result)

        with (
            patch.object(SessionDocument, "session_id", create=True, new="session_id"),
            patch.object(SessionDocument, "find_one", return_value=mock_find_one),
            patch("app.core.config.get_settings", return_value=mock_settings),
        ):
            await repo.add_event("session-1", event)

            # Verify the update call used $push/$each/$slice
            call_args = mock_find_one.update.call_args[0][0]
            assert "$push" in call_args
            push_spec = call_args["$push"]
            assert "events" in push_spec
            assert "$each" in push_spec["events"]
            assert "$slice" in push_spec["events"]
            assert push_spec["events"]["$slice"] == -5000
            # Verify $inc for event_count
            assert "$inc" in call_args
            assert call_args["$inc"]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_add_event_not_found_raises(self, repo, mock_settings):
        """add_event should raise SessionNotFoundException when session doesn't exist."""
        event = MagicMock(spec=BaseEvent)
        event.model_dump.return_value = {"type": "message", "id": "e1"}

        mock_find_one = MagicMock()
        mock_find_one.update = AsyncMock(return_value=None)

        with (
            patch.object(SessionDocument, "session_id", create=True, new="session_id"),
            patch.object(SessionDocument, "find_one", return_value=mock_find_one),
            patch("app.core.config.get_settings", return_value=mock_settings),
            pytest.raises(SessionNotFoundException),
        ):
            await repo.add_event("missing-session", event)


class TestProjectionDiscipline:
    """Test that non-event queries exclude events/files."""

    @pytest.mark.asyncio
    async def test_find_by_id_uses_projection(self, repo, mock_collection):
        """find_by_id should exclude events and files from the query."""
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "obj_id",
                "session_id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                "status": "running",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.find_by_id("s1")

            # Verify projection was passed
            call_args = mock_collection.find_one.call_args
            projection = call_args[1].get("projection") or call_args[0][1]
            assert projection.get("events") == 0
            assert projection.get("files") == 0

    @pytest.mark.asyncio
    async def test_find_by_id_and_user_id_uses_projection(self, repo, mock_collection):
        """find_by_id_and_user_id should exclude events and files."""
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "obj_id",
                "session_id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                "status": "running",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.find_by_id_and_user_id("s1", "u1")

            call_args = mock_collection.find_one.call_args
            projection = call_args[1].get("projection") or call_args[0][1]
            assert projection.get("events") == 0
            assert projection.get("files") == 0

    @pytest.mark.asyncio
    async def test_add_file_loads_only_files(self, repo, mock_collection):
        """add_file should load only the files array for duplicate check."""
        mock_collection.find_one = AsyncMock(return_value={"_id": "obj_id", "files": []})

        file_info = MagicMock(spec=FileInfo)
        file_info.file_id = "f1"
        file_info.file_path = "/test.py"
        file_info.model_dump.return_value = {"file_id": "f1", "file_path": "/test.py"}

        mock_update_result = MagicMock()
        mock_find_one_query = MagicMock()
        mock_find_one_query.update = AsyncMock(return_value=mock_update_result)

        with (
            patch.object(SessionDocument, "session_id", create=True, new="session_id"),
            patch.object(SessionDocument, "get_pymongo_collection", return_value=mock_collection),
            patch.object(SessionDocument, "find_one", return_value=mock_find_one_query),
        ):
            await repo.add_file("s1", file_info)

            # Verify pymongo find_one used files-only projection
            call_args = mock_collection.find_one.call_args
            projection = call_args[1].get("projection") or call_args[0][1]
            assert projection == {"files": 1}

    @pytest.mark.asyncio
    async def test_get_file_by_path_loads_only_files(self, repo, mock_collection):
        """get_file_by_path should load only the files array."""
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "obj_id",
                "files": [{"file_id": "f1", "file_path": "/test.py", "file_name": "test.py"}],
            }
        )

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.get_file_by_path("s1", "/test.py")

            call_args = mock_collection.find_one.call_args
            projection = call_args[1].get("projection") or call_args[0][1]
            assert projection == {"files": 1}


class TestEventQueryOptimizations:
    """Test that event queries use $slice/aggregation instead of full document loads."""

    @pytest.mark.asyncio
    async def test_get_event_by_sequence_uses_slice(self, repo, mock_collection):
        """get_event_by_sequence should use $slice projection."""
        mock_collection.find_one = AsyncMock(return_value={"events": [{"type": "message", "id": "e5"}]})

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.get_event_by_sequence("s1", 5)

            call_args = mock_collection.find_one.call_args
            projection = call_args[0][1]
            assert "events" in projection
            assert projection["events"] == {"$slice": [5, 1]}

    @pytest.mark.asyncio
    async def test_get_event_by_id_uses_aggregation(self, repo, mock_collection):
        """get_event_by_id should use aggregation $filter."""
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = lambda self: self
        results = [{"events": [{"type": "message", "id": "e1"}]}]
        mock_cursor.__anext__ = AsyncMock(side_effect=[*results, StopAsyncIteration()])
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.get_event_by_id("s1", "e1")

            # Verify aggregation pipeline was used
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0] == {"$match": {"session_id": "s1"}}
            assert "$project" in pipeline[1]
            assert "$filter" in pipeline[1]["$project"]["events"]

    @pytest.mark.asyncio
    async def test_get_events_in_range_uses_aggregation(self, repo, mock_collection):
        """get_events_in_range should use aggregation $filter."""
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 12, 31, tzinfo=UTC)

        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = lambda self: self
        results = [{"events": [{"type": "message", "id": "e1", "timestamp": "2026-06-01T00:00:00Z"}]}]
        mock_cursor.__anext__ = AsyncMock(side_effect=[*results, StopAsyncIteration()])
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        with patch(
            "app.infrastructure.repositories.mongo_session_repository.SessionDocument.get_pymongo_collection",
            return_value=mock_collection,
        ):
            await repo.get_events_in_range("s1", start, end)

            pipeline = mock_collection.aggregate.call_args[0][0]
            assert pipeline[0] == {"$match": {"session_id": "s1"}}
            filter_spec = pipeline[1]["$project"]["events"]["$filter"]
            assert filter_spec["as"] == "ev"
