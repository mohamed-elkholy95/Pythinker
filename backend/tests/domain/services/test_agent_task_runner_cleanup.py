"""Tests for AgentTaskRunner background task cleanup and fire-and-forget safety."""

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner


def _make_minimal_runner() -> AgentTaskRunner:
    """Build AgentTaskRunner (Discuss mode) with minimal mocks for cleanup tests."""
    return AgentTaskRunner(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        llm=MagicMock(),
        sandbox=MagicMock(),
        browser=MagicMock(),
        agent_repository=AsyncMock(),
        session_repository=AsyncMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
        mode=AgentMode.DISCUSS,
    )


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_fire_and_forget_consumes_exceptions(mock_settings: MagicMock) -> None:
    """Fire-and-forget tasks must consume exceptions to avoid unretrieved-exception noise."""
    mock_settings.return_value = MagicMock(default_language="English")

    async def failing_coro() -> None:
        raise ValueError("intentional failure")

    runner = _make_minimal_runner()
    runner._fire_and_forget(failing_coro())
    await asyncio.sleep(0.15)

    assert len(runner._background_tasks) == 0
    # No exception should propagate; task.exception() consumed in callback


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_fire_and_forget_cancelled_does_not_leak(mock_settings: MagicMock) -> None:
    """Cancelled fire-and-forget tasks must be discarded from registry."""
    mock_settings.return_value = MagicMock(default_language="English")
    started = asyncio.Event()

    async def slow_coro() -> None:
        started.set()
        await asyncio.sleep(10)

    runner = _make_minimal_runner()
    runner._fire_and_forget(slow_coro())
    await started.wait()
    tasks = list(runner._background_tasks)
    assert len(tasks) == 1
    tasks[0].cancel()
    with suppress(asyncio.CancelledError):
        await tasks[0]
    await asyncio.sleep(0.05)
    assert len(runner._background_tasks) == 0
