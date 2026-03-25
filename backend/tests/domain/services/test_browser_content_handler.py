"""Tests for browser tool content handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import BrowserToolContent, ToolEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tool_content_handlers.browser import handle_browser_content


def _make_tool_event(**kwargs) -> ToolEvent:
    defaults = {
        "tool_call_id": "tc-1",
        "tool_name": "browser_navigate",
        "function_name": "navigate",
        "function_args": {},
        "status": "called",
    }
    defaults.update(kwargs)
    return ToolEvent(**defaults)


@pytest.mark.asyncio
async def test_extracts_content_from_dict_content_key() -> None:
    event = _make_tool_event(
        function_result=ToolResult(success=True, data={"content": "page text"}),
    )
    await handle_browser_content(event, MagicMock())
    assert isinstance(event.tool_content, BrowserToolContent)
    assert event.tool_content.content == "page text"


@pytest.mark.asyncio
async def test_extracts_content_from_dict_text_key() -> None:
    event = _make_tool_event(
        function_result=ToolResult(success=True, data={"text": "alt text"}),
    )
    await handle_browser_content(event, MagicMock())
    assert event.tool_content.content == "alt text"


@pytest.mark.asyncio
async def test_extracts_content_from_dict_data_key() -> None:
    event = _make_tool_event(
        function_result=ToolResult(success=True, data={"data": "nested data"}),
    )
    await handle_browser_content(event, MagicMock())
    assert event.tool_content.content == "nested data"


@pytest.mark.asyncio
async def test_extracts_content_from_string_data() -> None:
    event = _make_tool_event(
        function_result=ToolResult(success=True, data="raw string"),
    )
    await handle_browser_content(event, MagicMock())
    assert event.tool_content.content == "raw string"


@pytest.mark.asyncio
async def test_no_function_result() -> None:
    event = _make_tool_event(function_result=None)
    await handle_browser_content(event, MagicMock())
    assert isinstance(event.tool_content, BrowserToolContent)
    assert event.tool_content.content is None


@pytest.mark.asyncio
async def test_empty_dict_data() -> None:
    event = _make_tool_event(
        function_result=ToolResult(success=True, data={}),
    )
    await handle_browser_content(event, MagicMock())
    assert event.tool_content.content is None


@pytest.mark.asyncio
async def test_priority_content_over_text() -> None:
    """content key takes priority over text key."""
    event = _make_tool_event(
        function_result=ToolResult(
            success=True, data={"content": "primary", "text": "secondary"}
        ),
    )
    await handle_browser_content(event, MagicMock())
    assert event.tool_content.content == "primary"
