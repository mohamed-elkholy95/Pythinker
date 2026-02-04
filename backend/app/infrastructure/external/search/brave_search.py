"""Brave Search Engine

Brave Search API implementation with privacy-focused search results.
Requires a Brave Search API key from https://brave.com/search/api/
"""

from typing import Any

import httpx

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry


@SearchProviderRegistry.register("brave")
class BraveSearchEngine(SearchEngineBase):
    """Brave Search API implementation.

    Uses Brave's official Search API which provides:
    - Privacy-focused search results
    - No tracking or profiling
    - Independent search index
    """

    provider_name = "Brave"
    engine_type = SearchEngineType.API

    def __init__(self, api_key: str, timeout: float | None = None):
        """Initialize Brave search engine.

        Args:
            api_key: Brave Search API key
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    def _get_headers(self) -> dict[str, str]:
        """Get Brave API headers with authentication."""
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Brave API freshness parameter mapping."""
        return {
            "past_hour": "ph",
            "past_day": "pd",
            "past_week": "pw",
            "past_month": "pm",
            "past_year": "py",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Brave API request parameters."""
        params: dict[str, Any] = {
            "q": query,
            "count": 20,
            "text_decorations": False,
            "search_lang": "en",
        }

        if mapped := self._map_date_range(date_range):
            params["freshness"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Brave API."""
        return await client.get(self.base_url, params=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Brave API JSON response."""
        data = response.json()
        web_data = data.get("web", {})
        web_results = web_data.get("results", [])

        results = [
            result
            for item in web_results
            if (result := self._parse_json_result_item(item, link_keys=("url",), snippet_keys=("description",)))
        ]

        total_results = web_data.get("total_count", len(results))
        return results, total_results
