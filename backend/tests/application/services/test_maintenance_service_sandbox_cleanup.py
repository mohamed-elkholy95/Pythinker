from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.application.services.maintenance_service import MaintenanceService


class _AsyncCursor:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._iter = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_cleanup_stale_running_sessions_destroys_only_owned_sandboxes() -> None:
    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    sessions = [
        {
            "_id": "session-owned",
            "status": "running",
            "updated_at": stale_time,
            "title": "owned",
            "sandbox_id": "sandbox-owned",
            "sandbox_owned": True,
            "sandbox_lifecycle_mode": "ephemeral",
        },
        {
            "_id": "session-unowned",
            "status": "running",
            "updated_at": stale_time,
            "title": "shared",
            "sandbox_id": "sandbox-shared",
            "sandbox_owned": False,
            "sandbox_lifecycle_mode": "static",
        },
    ]

    sessions_collection = SimpleNamespace(update_one=AsyncMock())
    # find() is sync in motor API, so return async-iterable cursor directly.
    sessions_collection.find = lambda *_args, **_kwargs: _AsyncCursor(sessions)

    db = SimpleNamespace(sessions=sessions_collection)
    service = MaintenanceService(db)

    owned_sandbox = AsyncMock()
    with (
        patch(
            "app.application.services.maintenance_service.get_settings",
            return_value=SimpleNamespace(sandbox_lifecycle_mode="static"),
        ),
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.DockerSandbox.get",
            new=AsyncMock(return_value=owned_sandbox),
        ),
    ):
        result = await service.cleanup_stale_running_sessions(stale_threshold_minutes=5, dry_run=False)

    assert result["sessions_cleaned"] == 2
    assert result["sandboxes_destroyed"] == 1
    owned_sandbox.destroy.assert_awaited_once()
    assert sessions_collection.update_one.await_count == 2


@pytest.mark.asyncio
async def test_cleanup_stale_running_sessions_resets_pending_runtime_and_skips_static_pending() -> None:
    stale_time = datetime.now(UTC) - timedelta(minutes=45)
    sessions = [
        {
            "_id": "pending-owned",
            "status": "pending",
            "updated_at": stale_time,
            "title": "pending owned sandbox",
            "sandbox_id": "sandbox-owned",
            "sandbox_owned": True,
            "sandbox_lifecycle_mode": "ephemeral",
            "task_id": None,
        },
        {
            "_id": "pending-static",
            "status": "pending",
            "updated_at": stale_time,
            "title": "pending static sandbox",
            "sandbox_id": "sandbox-static",
            "sandbox_owned": False,
            "sandbox_lifecycle_mode": "static",
            "task_id": None,
        },
        {
            "_id": "pending-task",
            "status": "pending",
            "updated_at": stale_time,
            "title": "pending leaked task",
            "sandbox_id": None,
            "sandbox_owned": False,
            "sandbox_lifecycle_mode": "static",
            "task_id": "task-123",
        },
    ]

    find_mock = Mock(return_value=_AsyncCursor(sessions))
    sessions_collection = SimpleNamespace(update_one=AsyncMock(), find=find_mock)

    db = SimpleNamespace(sessions=sessions_collection)
    service = MaintenanceService(db)

    owned_sandbox = AsyncMock()
    with (
        patch(
            "app.application.services.maintenance_service.get_settings",
            return_value=SimpleNamespace(sandbox_lifecycle_mode="static"),
        ),
        patch(
            "app.infrastructure.external.sandbox.docker_sandbox.DockerSandbox.get",
            new=AsyncMock(return_value=owned_sandbox),
        ),
    ):
        result = await service.cleanup_stale_running_sessions(stale_threshold_minutes=5, dry_run=False)

    query = find_mock.call_args.args[0]
    assert "updated_at" in query
    assert "$or" in query
    assert any(clause.get("status") == "pending" for clause in query["$or"] if isinstance(clause, dict))
    assert result["sessions_cleaned"] == 2
    assert len(result["sessions_reset_pending"]) == 2
    assert len(result["sessions_marked_failed"]) == 0
    assert len(result["sessions_skipped"]) == 1
    assert result["sessions_skipped"][0]["session_id"] == "pending-static"
    assert result["sandboxes_destroyed"] == 1
    owned_sandbox.destroy.assert_awaited_once()
    assert sessions_collection.update_one.await_count == 2

    updated_statuses = [
        call.args[1]["$set"]["status"]
        for call in sessions_collection.update_one.await_args_list
    ]
    assert updated_statuses == ["pending", "pending"]
