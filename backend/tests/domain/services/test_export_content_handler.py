"""Tests for export tool content handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import ToolEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tool_content_handlers.export import handle_export_content


def _make_event(**kwargs) -> ToolEvent:
    defaults = {
        "tool_call_id": "tc-exp-1",
        "tool_name": "export",
        "function_name": "export_file",
        "function_args": {},
        "status": "called",
    }
    defaults.update(kwargs)
    return ToolEvent(**defaults)


def _make_ctx(sync_mock: AsyncMock | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx._sync_file_to_storage = sync_mock or AsyncMock()
    ctx._agent_id = "agent-1"
    return ctx


@pytest.mark.asyncio
async def test_syncs_file_from_path_key() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(success=True, data={"path": "/tmp/report.pdf"}),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_awaited_once_with("/tmp/report.pdf")


@pytest.mark.asyncio
async def test_syncs_file_from_file_path_key() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(success=True, data={"file_path": "/tmp/out.zip"}),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_awaited_once_with("/tmp/out.zip")


@pytest.mark.asyncio
async def test_syncs_file_from_output_path_key() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(
            success=True, data={"output_path": "/tmp/archive.tar.gz"}
        ),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_awaited_once_with("/tmp/archive.tar.gz")


@pytest.mark.asyncio
async def test_no_sync_when_no_path_keys() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(success=True, data={"other": "value"}),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_sync_when_no_function_result() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(function_result=None)
    await handle_export_content(event, ctx)
    sync_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_sync_when_data_is_not_dict() -> None:
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(success=True, data="just a string"),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_priority_path_over_file_path() -> None:
    """'path' key takes priority over 'file_path'."""
    sync_mock = AsyncMock()
    ctx = _make_ctx(sync_mock)
    event = _make_event(
        function_result=ToolResult(
            success=True, data={"path": "/a.pdf", "file_path": "/b.pdf"}
        ),
    )
    await handle_export_content(event, ctx)
    sync_mock.assert_awaited_once_with("/a.pdf")
