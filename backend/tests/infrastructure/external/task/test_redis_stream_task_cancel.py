"""Tests for RedisStreamTask cancellation semantics around terminal tasks."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.external.task.redis_task import RedisStreamTask


class _DummyQueue:
    def __init__(self, stream_name: str):
        self._stream_name = stream_name

    async def delete_stream(self) -> None:
        return None


class _ExecutionTaskStub:
    def __init__(self) -> None:
        self.cancel_called = False

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancel_called = True


@pytest.mark.asyncio
async def test_cancel_does_not_request_cancellation_when_task_already_done(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid noisy cancellation signaling once task is already terminal."""

    monkeypatch.setattr("app.infrastructure.external.task.redis_task.RedisStreamQueue", _DummyQueue)

    runner = MagicMock()
    runner.request_cancellation = MagicMock()

    task = RedisStreamTask(runner=runner)
    task._cleanup_redis_streams = AsyncMock(return_value=None)

    cancelled = task.cancel()

    assert cancelled is False
    runner.request_cancellation.assert_not_called()

    # Allow background cleanup task to run and prevent task-leak warnings in test process.
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_cancel_requests_cancellation_when_task_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Active tasks should still receive cooperative cancellation signal."""

    monkeypatch.setattr("app.infrastructure.external.task.redis_task.RedisStreamQueue", _DummyQueue)

    runner = MagicMock()
    runner.request_cancellation = MagicMock()

    task = RedisStreamTask(runner=runner)
    task._cleanup_redis_streams = AsyncMock(return_value=None)
    task._execution_task = _ExecutionTaskStub()

    cancelled = task.cancel()

    assert cancelled is True
    assert task._execution_task.cancel_called is True
    runner.request_cancellation.assert_called_once()
