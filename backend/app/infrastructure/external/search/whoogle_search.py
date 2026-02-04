"""Whoogle Search Engine

Privacy-focused Google search proxy with JSON and HTML fallback parsing.
"""

from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry
from app.infrastructure.external.search.utils import clean_redirect_url, extract_text_from_tag


@SearchProviderRegistry.register("whoogle")
class WhoogleSearchEngine(SearchEngineBase):
    """Whoogle search engine implementation.

    Hybrid engine that tries JSON response first, then falls back to HTML parsing.
    """

    provider_name = "Whoogle"
    engine_type = SearchEngineType.HYBRID

    def __init__(self, base_url: str = "http://whoogle:5000", timeout: float | None = None):
        """Initialize Whoogle search engine.

        Args:
            base_url: Whoogle instance URL
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout or 20.0)
        self.base_url = base_url.rstrip("/")
        self.search_url = f"{self.base_url}/search"

    def _get_headers(self) -> dict[str, str]:
        """Get Whoogle-specific headers."""
        return {
            "User-Agent": "Pythinker-Agent/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Google tbs parameter mapping via Whoogle."""
        return {
            "past_day": "qdr:d",
            "past_week": "qdr:w",
            "past_month": "qdr:m",
            "past_year": "qdr:y",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Whoogle search parameters."""
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
        }

        if mapped := self._map_date_range(date_range):
            params["tbs"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Whoogle."""
        return await client.get(self.search_url, params=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Whoogle response (JSON or HTML fallback)."""
        results: list[SearchResultItem] = []
        content_type = response.headers.get("content-type", "").lower()

        # Try JSON parsing first
        if "application/json" in content_type:
            results = self._parse_json_results(response.json())
        else:
            # Try JSON anyway, fall back to HTML
            try:
                results = self._parse_json_results(response.json())
            except Exception:
                results = self._parse_html_results(response.text)

        # Final fallback to HTML if no results
        if not results and response.text:
            results = self._parse_html_results(response.text)

        return results, len(results)

    def _parse_json_results(self, payload: dict[str, Any]) -> list[SearchResultItem]:
        """Parse JSON response from Whoogle."""
        results: list[SearchResultItem] = []

        for item in payload.get("results", []):
            title = item.get("title") or item.get("name") or ""
            link = item.get("link") or item.get("url") or ""
            snippet = item.get("snippet") or item.get("text") or ""

            link = clean_redirect_url(link, self.base_url)

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results

    def _parse_html_results(self, html: str) -> list[SearchResultItem]:
        """Parse HTML response from Whoogle."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResultItem] = []

        # Try various result selectors
        nodes = soup.select("div.result, div.g, div.web-result")
        if not nodes:
            nodes = soup.find_all("div", class_=lambda cls: cls and "result" in str(cls))

        for node in nodes:
            link_tag = node.select_one("a[href]")
            if not link_tag:
                continue

            title = extract_text_from_tag(link_tag)
            link = clean_redirect_url(link_tag.get("href", ""), self.base_url)

            # Try various snippet selectors
            snippet_tag = node.select_one(
                ".result__snippet, .result-snippet, .result-content, .result__body, .st"
            )
            snippet = extract_text_from_tag(snippet_tag)

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Override search to use custom response handling for hybrid parsing."""
        # Use base class implementation which calls our _parse_response
        return await super().search(query, date_range)
