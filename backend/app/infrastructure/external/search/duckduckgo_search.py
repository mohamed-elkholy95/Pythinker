"""DuckDuckGo Search Engine

Privacy-focused search engine using DuckDuckGo's HTML search page.
No API key required.
"""

from typing import Any

import httpx
from scrapling.parser import Adaptor

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry
from app.infrastructure.external.search.utils import clean_redirect_url, extract_text_from_tag


@SearchProviderRegistry.register("duckduckgo")
class DuckDuckGoSearchEngine(SearchEngineBase):
    """DuckDuckGo web search engine implementation.

    Uses DuckDuckGo's HTML search page for results since they don't
    provide an official API for web search.
    """

    provider_name = "DuckDuckGo"
    engine_type = SearchEngineType.SCRAPER

    def __init__(self, timeout: float | None = None):
        """Initialize DuckDuckGo search engine."""
        super().__init__(timeout=timeout)
        self.base_url = "https://html.duckduckgo.com/html/"

    def _get_date_range_mapping(self) -> dict[str, str]:
        """DuckDuckGo date filter mapping."""
        return {
            "past_day": "d",
            "past_week": "w",
            "past_month": "m",
            "past_year": "y",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build DuckDuckGo form data parameters."""
        params: dict[str, Any] = {
            "q": query,
            "b": "",  # Start position
        }

        if mapped := self._map_date_range(date_range):
            params["df"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to DuckDuckGo HTML API."""
        return await client.post(self.base_url, data=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse DuckDuckGo HTML response."""
        page = Adaptor(response.text)
        results: list[SearchResultItem] = []

        # DuckDuckGo HTML results are in divs with class 'result'
        for item in page.find_all("div", class_="result"):
            # Extract title and link from a.result__a
            title_tag = item.find("a", class_="result__a")
            if not title_tag:
                continue

            title = extract_text_from_tag(title_tag)
            if not title:
                continue

            link = title_tag.attrib.get("href", "")
            link = clean_redirect_url(link)

            # Extract snippet from result__snippet
            snippet_tag = item.find("a", class_="result__snippet")
            snippet = extract_text_from_tag(snippet_tag)

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        # DuckDuckGo doesn't provide total result count
        return results, len(results)
