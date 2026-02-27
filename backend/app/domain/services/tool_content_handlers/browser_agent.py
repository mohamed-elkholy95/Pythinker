"""Browser agent tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.event import BrowserAgentToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_browser_agent_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Extract browser agent steps and result."""
    logger.debug(
        "Processing %s tool event: function_result=%s",
        event.tool_name,
        event.function_result,
    )
    if event.function_result:
        result_data = event.function_result.data if hasattr(event.function_result, "data") else {}
        steps_taken = result_data.get("steps_taken", 0) if isinstance(result_data, dict) else 0
        result = result_data.get("result", str(result_data)) if isinstance(result_data, dict) else str(result_data)
        event.tool_content = BrowserAgentToolContent(result=result, steps_taken=steps_taken)
    else:
        event.tool_content = BrowserAgentToolContent(result="No result available", steps_taken=0)
