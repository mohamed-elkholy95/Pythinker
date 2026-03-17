"""Adapter to bridge SearchEngine protocol to WideResearchOrchestrator's SearchToolProtocol.

The WideResearchOrchestrator expects `SearchToolProtocol.execute(query) -> dict`,
while Pythinker's search infrastructure uses `SearchEngine.search(query) -> ToolResult[SearchResults]`.
This adapter bridges the two without modifying either interface.
"""

from typing import Any

from app.domain.external.search import SearchEngine


class SearchToolAdapter:
    """Adapts SearchEngine to SearchToolProtocol for WideResearchOrchestrator."""

    MAX_RESULTS = 10

    def __init__(self, search_engine: SearchEngine) -> None:
        self._search_engine = search_engine

    async def execute(self, query: str) -> dict[str, Any]:
        """Execute a search query and return results in orchestrator format.

        Args:
            query: Search query string

        Returns:
            Dict with 'results' key containing list of result dicts
        """
        tool_result = await self._search_engine.search(query)

        if not tool_result.success or not tool_result.data:
            return {"results": []}

        return {
            "results": [
                {
                    "url": item.link,
                    "title": item.title,
                    "content": item.snippet,
                    "snippet": item.snippet,
                }
                for item in tool_result.data.results[: self.MAX_RESULTS]
            ]
        }
