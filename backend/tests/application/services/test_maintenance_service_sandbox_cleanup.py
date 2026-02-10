from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
