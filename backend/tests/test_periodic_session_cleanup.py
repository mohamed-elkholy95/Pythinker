"""Tests for periodic session cleanup background task."""

import asyncio
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_periodic_cleanup_task_calls_maintenance_service() -> None:
    """Verify the periodic cleanup task calls the maintenance service."""
    mock_maintenance = AsyncMock()
    mock_maintenance.cleanup_stale_running_sessions = AsyncMock(
        return_value={"sessions_cleaned": 2, "sandboxes_destroyed": 1}
    )

    from app.core.lifespan import _run_periodic_session_cleanup

    task = asyncio.create_task(_run_periodic_session_cleanup(mock_maintenance, interval_seconds=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert mock_maintenance.cleanup_stale_running_sessions.called
