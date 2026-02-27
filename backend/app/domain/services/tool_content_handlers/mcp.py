"""MCP tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.event import McpToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_mcp_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Extract MCP function result into tool content."""
    logger.debug("Processing MCP tool event: function_result=%s", event.function_result)
    if event.function_result:
        if hasattr(event.function_result, "data") and event.function_result.data:
            logger.debug("MCP tool result data: %s", event.function_result.data)
            event.tool_content = McpToolContent(result=event.function_result.data)
        elif hasattr(event.function_result, "success") and event.function_result.success:
            logger.debug("MCP tool result (success, no data): %s", event.function_result)
            result_data = (
                event.function_result.model_dump()
                if hasattr(event.function_result, "model_dump")
                else str(event.function_result)
            )
            event.tool_content = McpToolContent(result=result_data)
        else:
            logger.debug("MCP tool result (fallback): %s", event.function_result)
            event.tool_content = McpToolContent(result=str(event.function_result))
    else:
        logger.warning("MCP tool: No function_result found")
        event.tool_content = McpToolContent(result="No result available")

    logger.debug("MCP tool_content set to: %s", event.tool_content)
    if event.tool_content:
        logger.debug("MCP tool_content.result: %s", event.tool_content.result)
        logger.debug("MCP tool_content dict: %s", event.tool_content.model_dump())
