"""Tests for file tool content handler (tool panel preview)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.models.tool_result import ToolResult
from app.domain.services.tool_content_handlers.file import handle_file_content


@pytest.mark.asyncio
async def test_handle_file_content_surfaces_sandbox_error_when_read_fails() -> None:
    """Failed file_read has data=None but message explains denial — show message in panel."""
    event = ToolEvent(
        tool_call_id="tc1",
        tool_name="file",
        function_name="file_read",
        function_args={"file": "/app/report.md"},
        status=ToolStatus.CALLED,
    )
    ctx = MagicMock()
    ctx._file_before_cache.pop = MagicMock(return_value="")
    ctx._sandbox.file_read = AsyncMock(
        return_value=ToolResult(
            success=False,
            message=(
                "Sandbox API error (HTTP 400): Path traversal denied: "
                "path must be within one of: /home/ubuntu, /workspace, /tmp"
            ),
        )
    )
    ctx._sync_file_to_storage = AsyncMock(return_value=None)

    await handle_file_content(event, ctx)

    assert event.tool_content is not None
    assert "Path traversal denied" in event.tool_content.content
    assert "HTTP 400" in event.tool_content.content
    assert "file not found or empty response" not in event.tool_content.content
