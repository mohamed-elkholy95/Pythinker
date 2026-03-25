"""Tests for browser agent tool content handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.models.event import BrowserAgentToolContent, ToolEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tool_content_handlers.browser_agent import (
    handle_browser_agent_content,
)


def _make_event(**kwargs) -> ToolEvent:
    defaults = {
        "tool_call_id": "tc-ba-1",
        "tool_name": "browser_agent",
        "function_name": "run_browser_agent",
        "function_args": {},
        "status": "called",
    }
    defaults.update(kwargs)
    return ToolEvent(**defaults)


@pytest.mark.asyncio
async def test_extracts_result_and_steps() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data={"result": "found 3 items", "steps_taken": 5}),
    )
    await handle_browser_agent_content(event, MagicMock())
    assert isinstance(event.tool_content, BrowserAgentToolContent)
    assert event.tool_content.result == "found 3 items"
    assert event.tool_content.steps_taken == 5


@pytest.mark.asyncio
async def test_missing_steps_defaults_zero() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data={"result": "done"}),
    )
    await handle_browser_agent_content(event, MagicMock())
    assert event.tool_content.steps_taken == 0


@pytest.mark.asyncio
async def test_non_dict_data_stringified() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data="plain string"),
    )
    await handle_browser_agent_content(event, MagicMock())
    assert event.tool_content.result == "plain string"
    assert event.tool_content.steps_taken == 0


@pytest.mark.asyncio
async def test_no_function_result() -> None:
    event = _make_event(function_result=None)
    await handle_browser_agent_content(event, MagicMock())
    assert event.tool_content.result == "No result available"
    assert event.tool_content.steps_taken == 0


@pytest.mark.asyncio
async def test_none_data() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data=None),
    )
    await handle_browser_agent_content(event, MagicMock())
    assert event.tool_content.steps_taken == 0
