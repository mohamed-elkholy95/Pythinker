"""Google Search Engine

Google Custom Search API implementation.
Requires a Google API key and Custom Search Engine ID.
"""

from typing import Any

import httpx

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry


@SearchProviderRegistry.register("google")
class GoogleSearchEngine(SearchEngineBase):
    """Google Custom Search API implementation."""

    provider_name = "Google"
    engine_type = SearchEngineType.API

    def __init__(self, api_key: str, cx: str, timeout: float | None = None):
        """Initialize Google search engine.

        Args:
            api_key: Google Custom Search API key
            cx: Google Search Engine ID
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        self.api_key = api_key
        self.cx = cx
        self.base_url = "https://www.googleapis.com/customsearch/v1"

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Google dateRestrict parameter mapping."""
        return {
            "past_hour": "d1",
            "past_day": "d1",
            "past_week": "w1",
            "past_month": "m1",
            "past_year": "y1",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Google API request parameters."""
        params: dict[str, Any] = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
        }

        if mapped := self._map_date_range(date_range):
            params["dateRestrict"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Google API."""
        return await client.get(self.base_url, params=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Google API JSON response."""
        data = response.json()

        results = [
            SearchResultItem(
                title=item.get("title", ""),
                link=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in data.get("items", [])
            if item.get("title") and item.get("link")
        ]

        # Get total results
        search_info = data.get("searchInformation", {})
        try:
            total_results = int(search_info.get("totalResults", "0"))
        except (ValueError, TypeError):
            total_results = len(results)

        return results, total_results
