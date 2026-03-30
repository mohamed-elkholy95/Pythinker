"""File tool content handler."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.domain.models.event import FileToolContent, ToolEvent
from app.domain.utils.diff import build_unified_diff

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_file_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Read file content, sync to storage, and generate diffs."""
    if "file" in event.function_args:
        file_path = event.function_args["file"]
        file_read_task = ctx._sandbox.file_read(file_path)
        sync_task = ctx._sync_file_to_storage(file_path)
        file_read_result, _ = await asyncio.gather(file_read_task, sync_task, return_exceptions=True)
        if isinstance(file_read_result, Exception):
            file_content = f"(Error: {file_read_result})"
        elif file_read_result is None:
            file_content = "(Error: file not found or empty response)"
        elif not file_read_result.success:
            # Failed reads often have data=None but a detailed message (HTTP 400 path denial, 404, etc.).
            detail = file_read_result.message or "Could not read file"
            file_content = f"(Error: {detail})"
        elif file_read_result.data is None:
            file_content = "(Error: file not found or empty response)"
        else:
            file_content = file_read_result.data.get("content", "")
        event.tool_content = FileToolContent(content=file_content)

        before_content = ctx._file_before_cache.pop(event.tool_call_id, "")
        diff_text = build_unified_diff(before_content, file_content, file_path)
        if diff_text:
            event.diff = diff_text
    else:
        event.tool_content = FileToolContent(content="(No Content)")
