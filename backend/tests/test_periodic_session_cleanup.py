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


def test_beanie_models_include_agent_event_document() -> None:
    """Event archival relies on AgentEventDocument being initialized in Beanie."""
    from app.core import lifespan as lifespan_module
    from app.infrastructure.repositories.event_store_repository import AgentEventDocument

    assert AgentEventDocument in lifespan_module.BEANIE_DOCUMENT_MODELS


@pytest.mark.asyncio
async def test_periodic_event_archival_logs_exception_type_for_empty_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty-string exceptions should still log useful diagnostics."""
    from app.core import lifespan as lifespan_module

    class EmptyMessageError(Exception):
        def __str__(self) -> str:
            return ""

    class _DummyMetrics:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def inc(self, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
            del value
            self.calls.append(labels or {})

    class _FakeRepo:
        def __init__(self, db_client) -> None:
            del db_client

        async def archive_events_before(self, cutoff):
            del cutoff
            raise EmptyMessageError()

    class _FakeMongo:
        def __init__(self) -> None:
            self.client = {"test_db": object()}

    sleep_calls = {"count": 0}

    async def _fake_sleep(seconds: float) -> None:
        del seconds
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 2:
            raise asyncio.CancelledError()

    metrics = _DummyMetrics()
    monkeypatch.setattr("app.core.prometheus_metrics.event_store_archival_runs", metrics)
    monkeypatch.setattr("app.infrastructure.repositories.event_store_repository.EventStoreRepository", _FakeRepo)
    monkeypatch.setattr(lifespan_module, "get_mongodb", lambda: _FakeMongo())
    monkeypatch.setattr(lifespan_module.settings, "mongodb_database", "test_db")
    monkeypatch.setattr(lifespan_module.settings, "mongodb_event_retention_days", 90)
    monkeypatch.setattr(lifespan_module.asyncio, "sleep", _fake_sleep)

    warning_calls: list[tuple[tuple, dict]] = []

    def _capture_warning(*args, **kwargs):
        warning_calls.append((args, kwargs))

    monkeypatch.setattr(lifespan_module.logger, "warning", _capture_warning)

    with pytest.raises(asyncio.CancelledError):
        await lifespan_module._run_periodic_event_archival(interval_seconds=0.01)

    assert {"status": "error"} in metrics.calls
    rendered_messages: list[str] = []
    for args, _ in warning_calls:
        if not args:
            continue
        fmt = args[0]
        if isinstance(fmt, str) and len(args) > 1:
            try:
                rendered_messages.append(fmt % args[1:])
            except Exception:
                rendered_messages.append(str(args))
        else:
            rendered_messages.append(str(args))
    assert any("EmptyMessageError" in msg for msg in rendered_messages)
