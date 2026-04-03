"""Lightweight read-only tool for retrieving stored tool results by reference ID.

When tool results exceed their size threshold, they are offloaded to ToolResultStore
and replaced with a preview + [ref:trs-xxx] marker. This tool lets the agent fetch
the full content when it needs to dig deeper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

if TYPE_CHECKING:
    from app.domain.services.agents.tool_result_store import ToolResultStore


class ResultRetrievalTool(BaseTool):
    """Tool for retrieving full content of previously offloaded tool results."""

    name: str = "result_retrieval"

    def __init__(self, result_store: ToolResultStore) -> None:
        super().__init__(
            defaults=ToolDefaults(
                is_read_only=True,
                is_concurrency_safe=True,
                category="utility",
            ),
        )
        self._store = result_store

    @tool(
        name="retrieve_result",
        description=(
            "Retrieve the full content of a previously stored tool result by its reference ID. "
            "Use this when a tool result was truncated and you see a [ref:trs-xxx] marker."
        ),
        parameters={
            "result_id": {
                "type": "string",
                "description": "The reference ID (e.g. 'trs-abc123def456') from the [ref:...] marker",
            },
        },
        required=["result_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def retrieve_result(self, result_id: str) -> ToolResult:
        """Retrieve full content of a stored tool result.

        Args:
            result_id: Reference ID from the [ref:...] marker.

        Returns:
            ToolResult with the full content, or error if not found.
        """
        content = self._store.retrieve(result_id)
        if content is None:
            return ToolResult.error(
                message=f"Result {result_id} not found (may have been evicted from both memory and disk)."
            )
        return ToolResult(
            success=True,
            message=content,
        )
