"""Search tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.models.event import SearchToolContent, ToolEvent
from app.domain.models.search import SearchResults
from app.domain.models.tool_result import ToolResult

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_search_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Normalize search results for SearchContentView."""
    # Skip if tool_content already has results (set by base.py _create_tool_event)
    if (
        event.tool_content is not None
        and isinstance(event.tool_content, SearchToolContent)
        and event.tool_content.results
    ):
        logger.info(
            "Search tool content already populated with %d results, skipping handler",
            len(event.tool_content.results),
        )
        return

    search_results: ToolResult[SearchResults] = event.function_result
    if search_results is None:
        return

    normalized_results: list[Any] = []
    if hasattr(search_results, "data") and search_results.data:
        data = search_results.data
        if isinstance(data, SearchResults):
            normalized_results = data.results
        elif isinstance(data, dict):
            if isinstance(data.get("results"), list):
                normalized_results = data["results"]
            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("results"), list):
                normalized_results = data["data"]["results"]

    if normalized_results:
        logger.info(
            "Search tool results count=%s tool_call_id=%s",
            len(normalized_results),
            event.tool_call_id,
        )
        event.tool_content = SearchToolContent(results=normalized_results)
    else:
        logger.debug("Search handler found no results for tool_call_id=%s", event.tool_call_id)
