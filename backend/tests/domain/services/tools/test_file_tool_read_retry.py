import time
from unittest.mock import AsyncMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.file import _SAME_FILE_WRITE_WINDOW_SECONDS, FileTool


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


@pytest.mark.asyncio
async def test_file_write_strips_placeholder_and_meta_artifacts_for_markdown() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    raw = (
        "I see the issue and will now write the report.\n"
        "# Findings\n"
        "Useful content.\n"
        "[...]\n"
        "> **Note:** The model's output was cut off before completion.\n"
    )
    await tool.file_write(file="/workspace/report.md", content=raw)

    written = sandbox.file_write.await_args.kwargs["content"]
    assert "I see the issue" not in written
    assert "[...]" not in written
    assert "The model's output was cut off before completion" not in written
    assert "# Findings" in written


@pytest.mark.asyncio
async def test_file_write_warns_on_content_regression_for_overwrite() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    file_path = "/workspace/output/report.md"
    # Simulate previous larger write (v4) before a smaller overwrite (v5)
    tool._recent_write_sizes[file_path] = 18031

    result = await tool.file_write(file=file_path, content="x" * 10056, append=False)

    assert result.success is True
    assert "shrinks content from 18,031 to 10,056 bytes" in (result.message or "")
    assert "file_str_replace" in (result.message or "")
    assert tool._recent_write_sizes[file_path] == 10056


@pytest.mark.asyncio
async def test_file_write_skips_regression_warning_in_append_mode() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    file_path = "/workspace/output/report.md"
    tool._recent_write_sizes[file_path] = 18031

    result = await tool.file_write(file=file_path, content="x" * 10056, append=True)

    assert result.success is True
    assert "shrinks content from" not in (result.message or "")


@pytest.mark.asyncio
async def test_file_write_warns_on_repetitive_overwrite_loop() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(side_effect=lambda **_: ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    file_path = "/workspace/output/report.md"

    first = await tool.file_write(file=file_path, content="version-1", append=False)
    second = await tool.file_write(file=file_path, content="version-2", append=False)
    third = await tool.file_write(file=file_path, content="version-3", append=False)

    assert first.success and second.success
    # 3rd overwrite is BLOCKED — returns error per design 2B enforcement
    assert third.success is False
    assert "overwrite loop detected" not in (first.message or "")
    assert "overwrite loop detected" not in (second.message or "")
    assert "overwrite loop detected" in (third.message or "")
    assert "file_str_replace" in (third.message or "")


@pytest.mark.asyncio
async def test_file_write_overwrite_loop_window_expires() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=ToolResult(success=True, message="ok"))

    tool = FileTool(sandbox=sandbox, session_id="session-1")
    file_path = "/workspace/output/report.md"

    old_ts = time.monotonic() - (_SAME_FILE_WRITE_WINDOW_SECONDS + 1)
    tool._write_history[file_path] = [old_ts, old_ts, old_ts]

    result = await tool.file_write(file=file_path, content="fresh-write", append=False)

    assert result.success is True
    assert "overwrite loop detected" not in (result.message or "")
