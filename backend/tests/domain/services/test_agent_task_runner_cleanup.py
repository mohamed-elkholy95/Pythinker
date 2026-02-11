"""Tests for AgentTaskRunner cleanup behavior."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.models.screenshot import ScreenshotTrigger
from app.domain.models.session import AgentMode
from app.domain.services.agent_task_runner import AgentTaskRunner


@pytest.fixture
def mock_sandbox() -> AsyncMock:
    sandbox = AsyncMock()
    sandbox.destroy = AsyncMock()
    sandbox.release_pooled_browser = AsyncMock()
    return sandbox


@pytest.fixture
def mock_browser() -> MagicMock:
    return MagicMock()


@pytest.fixture
def runner(mock_sandbox, mock_browser) -> AgentTaskRunner:
    with patch("app.domain.services.agent_task_runner.PlanActFlow"):
        return AgentTaskRunner(
            session_id="test-session",
            agent_id="test-agent",
            user_id="test-user",
            llm=MagicMock(),
            sandbox=mock_sandbox,
            browser=mock_browser,
            agent_repository=AsyncMock(),
            session_repository=AsyncMock(),
            json_parser=MagicMock(),
            file_storage=AsyncMock(),
            mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
            search_engine=AsyncMock(),
            mode=AgentMode.AGENT,
        )


@pytest.mark.asyncio
async def test_destroy_releases_pooled_browser(runner, mock_sandbox, mock_browser):
    await runner.destroy()

    mock_sandbox.release_pooled_browser.assert_awaited_once_with(mock_browser, had_error=False)


@pytest.mark.asyncio
async def test_fire_and_forget_consumes_task_exception(runner, caplog: pytest.LogCaptureFixture):
    async def _failing_background_task() -> None:
        raise RuntimeError("background boom")

    with caplog.at_level(logging.WARNING):
        runner._fire_and_forget(_failing_background_task())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert runner._background_tasks == set()
    warning_messages = [record.message for record in caplog.records if "Background task failed" in record.message]
    assert warning_messages == ["Background task failed for Agent test-agent: background boom"]


@pytest.mark.asyncio
async def test_destroy_attempts_session_end_screenshot(runner):
    screenshot_service = MagicMock()
    screenshot_service.stop_periodic = AsyncMock()
    screenshot_service.capture = AsyncMock(return_value=MagicMock())
    runner._screenshot_service = screenshot_service

    await runner.destroy()

    screenshot_service.stop_periodic.assert_awaited_once()
    screenshot_service.capture.assert_awaited_once_with(ScreenshotTrigger.SESSION_END)


@pytest.mark.asyncio
async def test_destroy_logs_warning_when_session_end_capture_returns_none(
    runner,
    caplog: pytest.LogCaptureFixture,
):
    screenshot_service = MagicMock()
    screenshot_service.stop_periodic = AsyncMock()
    screenshot_service.capture = AsyncMock(return_value=None)
    runner._screenshot_service = screenshot_service

    with caplog.at_level(logging.WARNING):
        await runner.destroy()

    warning_messages = [record.message for record in caplog.records]
    assert "SESSION_END screenshot capture returned no image for session test-session" in warning_messages


@pytest.mark.asyncio
async def test_destroy_captures_session_end_even_if_stop_periodic_fails(
    runner,
    caplog: pytest.LogCaptureFixture,
):
    screenshot_service = MagicMock()
    screenshot_service.stop_periodic = AsyncMock(side_effect=RuntimeError("stop failed"))
    screenshot_service.capture = AsyncMock(return_value=MagicMock())
    runner._screenshot_service = screenshot_service

    with caplog.at_level(logging.WARNING):
        await runner.destroy()

    screenshot_service.capture.assert_awaited_once_with(ScreenshotTrigger.SESSION_END)
    warning_messages = [record.message for record in caplog.records]
    assert "Failed to stop periodic screenshot capture for session test-session: stop failed" in warning_messages


@pytest.mark.asyncio
async def test_handle_tool_event_updates_screenshot_tool_context(runner):
    screenshot_service = MagicMock()
    screenshot_service.set_tool_context = MagicMock()
    screenshot_service.clear_tool_context = MagicMock()
    screenshot_service.capture = AsyncMock(return_value=MagicMock())
    runner._screenshot_service = screenshot_service

    calling_event = ToolEvent(
        tool_call_id="tool-call-1",
        tool_name="browser",
        function_name="browser_navigate",
        function_args={},
        status=ToolStatus.CALLING,
    )
    called_event = ToolEvent(
        tool_call_id="tool-call-1",
        tool_name="browser",
        function_name="browser_navigate",
        function_args={},
        status=ToolStatus.CALLED,
    )

    await runner._handle_tool_event(calling_event)
    await runner._handle_tool_event(called_event)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    screenshot_service.set_tool_context.assert_called_once_with(
        tool_call_id="tool-call-1",
        tool_name="browser",
        function_name="browser_navigate",
        action_type=calling_event.action_type,
    )
    screenshot_service.clear_tool_context.assert_called_once_with(tool_call_id="tool-call-1")
