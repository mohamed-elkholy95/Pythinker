"""Browser tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.event import BrowserToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_browser_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Extract page content from browser tool result."""
    page_content = None
    if event.function_result and hasattr(event.function_result, "data"):
        result_data = event.function_result.data
        if isinstance(result_data, dict):
            page_content = result_data.get("content") or result_data.get("text") or result_data.get("data")
        elif isinstance(result_data, str):
            page_content = result_data
    event.tool_content = BrowserToolContent(content=page_content)
