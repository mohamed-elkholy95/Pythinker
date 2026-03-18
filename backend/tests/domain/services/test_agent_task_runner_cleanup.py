"""Tests for AgentTaskRunner background task cleanup and fire-and-forget safety."""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent, FlowSelectionEvent, MessageEvent, ToolEvent, ToolStatus
from app.domain.models.session import AgentMode, SessionStatus
from app.domain.services.agent_task_runner import AgentTaskRunner, _extract_mcp_server_name


def _make_minimal_runner(usage_recorder: AsyncMock | None = None) -> AgentTaskRunner:
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
        usage_recorder=usage_recorder,
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


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_run_cancelled_does_not_mark_completed(mock_settings: MagicMock) -> None:
    """Cancelled run should not emit synthetic completion status."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)

    runner = _make_minimal_runner()
    runner._llm.model = "test-model"
    runner._llm.model_name = "test-model"
    runner._sandbox.ensure_sandbox = AsyncMock(return_value=None)
    runner._mcp_repository.get_mcp_config = AsyncMock(return_value=SimpleNamespace(mcp_servers={}))
    runner._mcp_tool.initialized = AsyncMock(return_value=None)
    runner._session_repository.update_status = AsyncMock()
    runner._put_and_add_event = AsyncMock(side_effect=asyncio.CancelledError())

    task = SimpleNamespace(
        id="task-id",
        input_stream=SimpleNamespace(is_empty=AsyncMock(return_value=True)),
        paused=False,
    )

    await runner.run(task)

    runner._session_repository.update_status.assert_not_awaited()


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_run_does_not_emit_duplicate_done_when_flow_already_emits_done(mock_settings: MagicMock) -> None:
    """Runner should not emit synthetic DoneEvent if flow already emitted terminal done."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)

    runner = _make_minimal_runner()
    runner._llm.model = "test-model"
    runner._llm.model_name = "test-model"
    runner._sandbox.ensure_sandbox = AsyncMock(return_value=None)
    runner._mcp_repository.get_mcp_config = AsyncMock(return_value=SimpleNamespace(mcp_servers={}))
    runner._mcp_tool.initialized = AsyncMock(return_value=None)
    runner._sync_message_attachments_to_sandbox = AsyncMock(return_value=None)
    runner._session_repository.update_status = AsyncMock()
    runner._session_repository.update_title = AsyncMock()
    runner._session_repository.update_latest_message = AsyncMock()
    runner._session_repository.increment_unread_message_count = AsyncMock()

    async def _flow_with_done(_message_obj, _task):
        yield DoneEvent()

    runner._run_flow = _flow_with_done  # type: ignore[method-assign]
    runner._pop_event = AsyncMock(return_value=MessageEvent(message="do work", role="user"))
    runner._put_and_add_event = AsyncMock()

    task = SimpleNamespace(
        id="task-id",
        input_stream=SimpleNamespace(is_empty=AsyncMock(side_effect=[False, True, True])),
        paused=False,
    )

    await runner.run(task)

    emitted_events = [call.args[1] for call in runner._put_and_add_event.await_args_list]
    done_count = sum(isinstance(event, DoneEvent) for event in emitted_events)

    assert any(isinstance(event, FlowSelectionEvent) for event in emitted_events)
    assert done_count == 1
    runner._session_repository.update_status.assert_awaited_once()


@patch("app.core.config.get_settings")
def test_request_cancellation_ignored_after_terminal_status(mock_settings: MagicMock) -> None:
    """Cancellation requests should be ignored once the runner is terminal."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)

    runner = _make_minimal_runner()
    runner._terminal_status = SessionStatus.COMPLETED

    runner.request_cancellation()

    assert runner._cancel_event.is_set() is False


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_run_records_usage_lifecycle(mock_settings: MagicMock) -> None:
    """Runner should open and close an agent usage run around execution."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)
    usage_recorder = AsyncMock(side_effect=["run-123", None])
    runner = _make_minimal_runner(usage_recorder=usage_recorder)
    runner._llm.model = "test-model"
    runner._llm.model_name = "test-model"
    runner._sandbox.ensure_sandbox = AsyncMock(return_value=None)
    runner._mcp_repository.get_mcp_config = AsyncMock(return_value=SimpleNamespace(mcp_servers={}))
    runner._mcp_tool.initialized = AsyncMock(return_value=None)
    runner._sync_message_attachments_to_sandbox = AsyncMock(return_value=None)
    runner._session_repository.update_status = AsyncMock()
    runner._session_repository.update_title = AsyncMock()
    runner._session_repository.update_latest_message = AsyncMock()
    runner._session_repository.increment_unread_message_count = AsyncMock()

    async def _flow_with_done(_message_obj, _task):
        yield DoneEvent()

    runner._run_flow = _flow_with_done  # type: ignore[method-assign]
    runner._pop_event = AsyncMock(return_value=MessageEvent(message="do work", role="user"))
    runner._put_and_add_event = AsyncMock()

    task = SimpleNamespace(
        id="task-id",
        input_stream=SimpleNamespace(is_empty=AsyncMock(side_effect=[False, True, True])),
        paused=False,
    )

    await runner.run(task)

    assert usage_recorder.await_count >= 2
    start_call = usage_recorder.await_args_list[0]
    finish_call = usage_recorder.await_args_list[-1]
    assert start_call.kwargs["action"] == "start_run"
    assert start_call.kwargs["user_id"] == "user-1"
    assert finish_call.kwargs["action"] == "finish_run"
    assert finish_call.kwargs["run_id"] == "run-123"
    assert finish_call.kwargs["status"] == "completed"


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_record_tool_call_usage_passes_tool_and_mcp_metadata(mock_settings: MagicMock) -> None:
    """Tool usage callback should receive duration and parsed MCP server name."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)
    usage_recorder = AsyncMock()
    runner = _make_minimal_runner(usage_recorder=usage_recorder)
    runner._run_id = "run-123"

    event = ToolEvent(
        tool_call_id="call-1",
        tool_name="mcp__github__search_repos",
        function_name="mcp__github__search_repos",
        function_args={"query": "pythinker"},
        status=ToolStatus.CALLED,
        duration_ms=250,
    )

    await runner._record_tool_call_usage(event)

    usage_recorder.assert_awaited_once()
    kwargs = usage_recorder.await_args.kwargs
    assert kwargs["action"] == "record_tool_call"
    assert kwargs["run_id"] == "run-123"
    assert kwargs["tool_name"] == "mcp__github__search_repos"
    assert kwargs["mcp_server"] == "github"
    assert kwargs["duration_ms"] == 250


def test_extract_mcp_server_name_allows_missing_tool_name() -> None:
    """Missing tool names should not raise when deriving MCP metadata."""
    assert _extract_mcp_server_name(None) is None
