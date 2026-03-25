"""Tests for MCP tool content handler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.models.event import McpToolContent, ToolEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tool_content_handlers.mcp import handle_mcp_content


def _make_event(**kwargs) -> ToolEvent:
    defaults = {
        "tool_call_id": "tc-mcp-1",
        "tool_name": "mcp_tool",
        "function_name": "mcp_invoke",
        "function_args": {},
        "status": "called",
    }
    defaults.update(kwargs)
    return ToolEvent(**defaults)


@pytest.mark.asyncio
async def test_extracts_data_from_result() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data={"key": "value"}),
    )
    await handle_mcp_content(event, MagicMock())
    assert isinstance(event.tool_content, McpToolContent)
    assert event.tool_content.result == {"key": "value"}


@pytest.mark.asyncio
async def test_success_no_data_uses_model_dump() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data=None),
    )
    await handle_mcp_content(event, MagicMock())
    assert isinstance(event.tool_content, McpToolContent)
    # Should fall through to model_dump since success=True but data is None
    result = event.tool_content.result
    assert result is not None


@pytest.mark.asyncio
async def test_no_function_result() -> None:
    event = _make_event(function_result=None)
    await handle_mcp_content(event, MagicMock())
    assert event.tool_content.result == "No result available"


@pytest.mark.asyncio
async def test_failed_result_uses_str() -> None:
    event = _make_event(
        function_result=ToolResult(success=False, data=None, message="failed"),
    )
    await handle_mcp_content(event, MagicMock())
    assert isinstance(event.tool_content, McpToolContent)
    result_str = str(event.tool_content.result)
    assert result_str  # Should have some string representation


@pytest.mark.asyncio
async def test_string_data() -> None:
    event = _make_event(
        function_result=ToolResult(success=True, data="plain text"),
    )
    await handle_mcp_content(event, MagicMock())
    assert event.tool_content.result == "plain text"
