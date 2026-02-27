"""Code executor tool content handler."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.domain.models.event import FileToolContent, ShellToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_code_executor_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Handle code execution output, artifact save/read, and console display."""
    if not (event.function_result and hasattr(event.function_result, "data")):
        event.tool_content = ShellToolContent(console="(No output)")
        return

    data = event.function_result.data
    if not isinstance(data, dict):
        event.tool_content = ShellToolContent(console=str(data) if data else "(No output)")
        return

    if event.function_name == "code_save_artifact":
        content = event.function_args.get("content")
        event.tool_content = FileToolContent(content=content if isinstance(content, str) else "")
        artifact_path = data.get("path")
        if isinstance(artifact_path, str):
            event.file_path = artifact_path
            if getattr(event.function_result, "success", False):
                await ctx._sync_file_to_storage(artifact_path)

    elif event.function_name == "code_read_artifact":
        content = data.get("content")
        event.tool_content = FileToolContent(content=content if isinstance(content, str) else "")
        artifact_path = data.get("path")
        if isinstance(artifact_path, str):
            event.file_path = artifact_path
        else:
            artifact_name = data.get("filename")
            if isinstance(artifact_name, str):
                event.file_path = artifact_name
    else:
        # Extract stdout/stderr for console display
        console_output = []
        if data.get("stdout"):
            console_output.append(data["stdout"])
        if data.get("stderr"):
            console_output.append(f"[stderr] {data['stderr']}")
        if data.get("exit_code") is not None:
            console_output.append(f"[exit code: {data['exit_code']}]")
        event.stdout = data.get("stdout")
        event.stderr = data.get("stderr")
        event.exit_code = data.get("exit_code")
        event.tool_content = ShellToolContent(console="\n".join(console_output) if console_output else "(No output)")

        # Sync artifacts to session files
        artifacts = data.get("artifacts", [])
        if artifacts:
            sync_tasks = []
            for artifact in artifacts:
                artifact_path = artifact.get("path") if isinstance(artifact, dict) else None
                if artifact_path:
                    sync_tasks.append(ctx._sync_file_to_storage(artifact_path))
            if sync_tasks:
                await asyncio.gather(*sync_tasks, return_exceptions=True)
                logger.debug(
                    "Agent %s: Synced %s artifacts from code_executor",
                    ctx._agent_id,
                    len(sync_tasks),
                )
