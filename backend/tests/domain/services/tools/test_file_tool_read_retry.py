import time
from unittest.mock import AsyncMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.file import FileTool


@pytest.mark.asyncio
async def test_file_read_retries_once_for_transient_not_found() -> None:
    """Retry fires when the path was recently written (write-read race)."""
    sandbox = AsyncMock()
    sandbox.file_read = AsyncMock(
        side_effect=[
            ToolResult(success=False, message="Sandbox API error (HTTP 404): File not found"),
            ToolResult(success=True, data={"content": "ok"}, message=None),
        ]
    )

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    # Simulate a prior write to this path
    tool._recently_written["/workspace/session-1/output/report.md"] = time.monotonic()

    result = await tool.file_read(file="/workspace/session-1/output/report.md")

    assert result.success is True
    assert sandbox.file_read.await_count == 2


@pytest.mark.asyncio
async def test_file_read_does_not_retry_non_not_found_errors() -> None:
    sandbox = AsyncMock()
    sandbox.file_read = AsyncMock(return_value=ToolResult(success=False, message="Sandbox API error (HTTP 500): boom"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    result = await tool.file_read(file="/workspace/session-1/output/report.md")

    assert result.success is False
    assert sandbox.file_read.await_count == 1


@pytest.mark.asyncio
async def test_file_read_skips_retry_for_unwritten_path() -> None:
    """No retry when the path was never written — avoids wasted latency on 'does it exist?' probes."""
    sandbox = AsyncMock()
    sandbox.file_read = AsyncMock(
        return_value=ToolResult(success=False, message="Sandbox API error (HTTP 404): File not found"),
    )

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    # _recently_written is empty — no prior write to this path
    result = await tool.file_read(file="/workspace/session-1/output/report.md")

    assert result.success is False
    assert result.message == "File not found: /workspace/session-1/output/report.md"
    assert sandbox.file_read.await_count == 1


@pytest.mark.asyncio
async def test_file_write_tracks_path() -> None:
    """file_write records the path in _recently_written for read-after-write retry gating."""
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    assert "/workspace/test.md" not in tool._recently_written

    await tool.file_write(file="/workspace/test.md", content="hello")

    assert "/workspace/test.md" in tool._recently_written
