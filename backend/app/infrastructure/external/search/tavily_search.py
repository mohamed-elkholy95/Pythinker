"""Tavily Search Engine

Tavily AI-powered Search API implementation.
Requires a Tavily API key from https://tavily.com/
"""

from typing import Any

import httpx

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry


@SearchProviderRegistry.register("tavily")
class TavilySearchEngine(SearchEngineBase):
    """Tavily AI-powered Search API implementation.

    Uses Tavily's Search API which provides:
    - AI-optimized search results
    - Relevance ranking powered by AI
    - Real-time web search
    - Clean, structured results
    """

    provider_name = "Tavily"
    engine_type = SearchEngineType.API

    def __init__(self, api_key: str, timeout: float | None = None):
        """Initialize Tavily search engine.

        Args:
            api_key: Tavily API key
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"

    def _get_headers(self) -> dict[str, str]:
        """Get Tavily API headers."""
        return {"Content-Type": "application/json"}

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Tavily date hints (appended to query since API lacks direct filtering)."""
        return {
            "past_hour": "recent",
            "past_day": "today",
            "past_week": "this week",
            "past_month": "this month",
            "past_year": "this year",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Tavily API request payload."""
        # Append date hint to query if specified
        actual_query = query
        if date_hint := self._map_date_range(date_range):
            actual_query = f"{query} {date_hint}"

        return {
            "api_key": self.api_key,
            "query": actual_query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
            "max_results": 20,
        }

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to Tavily API."""
        return await client.post(self.base_url, json=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Tavily API JSON response."""
        data = response.json()

        results: list[SearchResultItem] = []
        for item in data.get("results", []):
            title = item.get("title", "")
            link = item.get("url", "")
            snippet = item.get("content", "")

            # Truncate long snippets
            if len(snippet) > 500:
                snippet = snippet[:497] + "..."

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results, len(results)
