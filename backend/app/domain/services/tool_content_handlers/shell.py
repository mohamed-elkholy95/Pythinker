"""Shell tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.event import ShellToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_shell_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Extract shell output and console session data."""
    if not event.command and "command" in event.function_args:
        event.command = event.function_args["command"]
    if event.function_result and hasattr(event.function_result, "data"):
        data = event.function_result.data or {}
        if isinstance(data, dict):
            event.stdout = data.get("output")
            event.exit_code = data.get("returncode")
    if "id" in event.function_args:
        shell_result = await ctx._sandbox.view_shell(event.function_args["id"], console=True)
        event.tool_content = ShellToolContent(console=(shell_result.data or {}).get("console", []))
    else:
        event.tool_content = ShellToolContent(console="(No Console)")
