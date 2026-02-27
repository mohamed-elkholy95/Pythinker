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
    search_results: ToolResult[SearchResults] = event.function_result
    logger.debug("Search tool results: %s", search_results)

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

    logger.info(
        "Search tool results count=%s tool_call_id=%s",
        len(normalized_results),
        event.tool_call_id,
    )
    event.tool_content = SearchToolContent(results=normalized_results)
