"""Whoogle Search Engine

Privacy-focused Google search proxy with JSON and HTML fallback parsing.
"""
import logging
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

DATE_RANGE_MAP = {
    "past_day": "qdr:d",
    "past_week": "qdr:w",
    "past_month": "qdr:m",
    "past_year": "qdr:y",
}


@SearchProviderRegistry.register("whoogle")
class WhoogleSearchEngine(SearchEngine):
    """Whoogle search engine implementation."""

    def __init__(self, base_url: str = "http://whoogle:5000", timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.search_url = f"{self.base_url}/search"
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Pythinker-Agent/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }

    def _build_params(self, query: str, date_range: str | None) -> dict:
        params = {
            "q": query,
            "format": "json",
        }
        if date_range and date_range in DATE_RANGE_MAP:
            params["tbs"] = DATE_RANGE_MAP[date_range]
        return params

    def _clean_link(self, link: str) -> str:
        if not link:
            return ""
        if link.startswith("/url?"):
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            if query.get("q"):
                return query["q"][0]
        if link.startswith("http://") or link.startswith("https://"):
            return link
        return urljoin(self.base_url, link)

    def _parse_json_results(self, payload: dict) -> list[SearchResultItem]:
        results: list[SearchResultItem] = []
        for item in payload.get("results", []):
            title = item.get("title") or item.get("name") or ""
            link = item.get("link") or item.get("url") or ""
            snippet = item.get("snippet") or item.get("text") or ""
            link = self._clean_link(link)
            if title and link:
                results.append(SearchResultItem(
                    title=title,
                    link=link,
                    snippet=snippet,
                ))
        return results

    def _parse_html_results(self, html: str) -> list[SearchResultItem]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResultItem] = []
        nodes = soup.select("div.result, div.g, div.web-result")
        if not nodes:
            nodes = soup.find_all("div", class_=lambda cls: cls and "result" in cls)

        for node in nodes:
            link_tag = node.select_one("a[href]")
            if not link_tag:
                continue
            title = link_tag.get_text(" ", strip=True)
            link = self._clean_link(link_tag.get("href", ""))
            snippet_tag = node.select_one(".result__snippet, .result-snippet, .result-content, .result__body, .st")
            snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
            if title and link:
                results.append(SearchResultItem(
                    title=title,
                    link=link,
                    snippet=snippet,
                ))
        return results

    async def search(
        self,
        query: str,
        date_range: str | None = None
    ) -> ToolResult[SearchResults]:
        params = self._build_params(query, date_range)

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            ) as client:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()

                results: list[SearchResultItem] = []
                content_type = response.headers.get("content-type", "").lower()

                if "application/json" in content_type:
                    results = self._parse_json_results(response.json())
                else:
                    try:
                        results = self._parse_json_results(response.json())
                    except Exception:
                        results = self._parse_html_results(response.text)

                if not results and response.text:
                    results = self._parse_html_results(response.text)

                return ToolResult(
                    success=True,
                    data=SearchResults(
                        query=query,
                        date_range=date_range,
                        total_results=len(results),
                        results=results,
                    )
                )
        except Exception as e:
            logger.error(f"Whoogle Search failed: {e}")
            return ToolResult(
                success=False,
                message=f"Whoogle Search failed: {e}",
                data=SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=0,
                    results=[],
                ),
            )
