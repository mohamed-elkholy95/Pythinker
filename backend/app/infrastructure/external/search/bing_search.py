"""Bing Search Engine

Bing web search engine implementation using web scraping.
No API key required.
"""

from typing import Any

import httpx
from scrapling.parser import Adaptor

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry
from app.infrastructure.external.search.utils import extract_text_from_tag, parse_result_count


@SearchProviderRegistry.register("bing")
class BingSearchEngine(SearchEngineBase):
    """Bing web search engine implementation using web scraping."""

    provider_name = "Bing"
    engine_type = SearchEngineType.SCRAPER

    def __init__(self, timeout: float | None = None):
        """Initialize Bing search engine."""
        super().__init__(timeout=timeout)
        self.base_url = "https://www.bing.com/search"
        self.cookies = httpx.Cookies()

    def _get_headers(self) -> dict[str, str]:
        """Get Bing-specific browser headers."""
        headers = self.BROWSER_HEADERS.copy()
        headers["Upgrade-Insecure-Requests"] = "1"
        return headers

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Bing filter parameter mapping."""
        return {
            "past_hour": "interval%3d%22Hour%22",
            "past_day": "interval%3d%22Day%22",
            "past_week": "interval%3d%22Week%22",
            "past_month": "interval%3d%22Month%22",
            "past_year": "interval%3d%22Year%22",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Bing search parameters."""
        params: dict[str, Any] = {
            "q": query,
            "count": "20",
            "first": "1",
        }

        if mapped := self._map_date_range(date_range):
            params["filters"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Bing with cookie handling."""
        response = await client.get(self.base_url, params=params, cookies=self.cookies)
        self.cookies.update(response.cookies)
        return response

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Bing HTML response."""
        page = Adaptor(response.text)
        results: list[SearchResultItem] = []

        # Bing search results are in li elements with class 'b_algo'
        for item in page.find_all("li", class_="b_algo"):
            result = self._parse_result_item(item)
            if result:
                results.append(result)

        # Extract total results count
        total_results = self._extract_result_count(page)

        return results, total_results

    def _parse_result_item(self, item: Adaptor) -> SearchResultItem | None:
        """Parse a single Bing result item."""
        title = ""
        link = ""

        # Title is usually in h2 > a
        title_tag = item.find("h2")
        if title_tag:
            title_a = title_tag.find("a")
            if title_a:
                title = extract_text_from_tag(title_a)
                link = title_a.attrib.get("href", "")

        # Fallback: try other link structures
        if not title:
            for a_tag in item.find_all("a"):
                text = extract_text_from_tag(a_tag)
                if len(text) > 10 and not text.startswith("http"):
                    title = text
                    link = a_tag.attrib.get("href", "")
                    break

        if not title:
            return None

        # Extract snippet
        snippet = self._extract_snippet(item)

        # Clean up relative links
        if link and not link.startswith("http"):
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = "https://www.bing.com" + link

        if title and link:
            return SearchResultItem(title=title, link=link, snippet=snippet)
        return None

    def _extract_snippet(self, item: Adaptor) -> str:
        """Extract snippet from Bing result item."""
        # Look for description in known Bing CSS classes
        snippet_tags = item.css(
            "p.b_lineclamp, p.b_descript, p.b_caption, div.b_lineclamp, div.b_descript, div.b_caption"
        )
        if snippet_tags:
            return extract_text_from_tag(snippet_tags.first)

        # Fallback: any p tag with substantial text
        for p_tag in item.find_all("p"):
            text = extract_text_from_tag(p_tag)
            if len(text) > 20:
                return text

        return ""

    def _extract_result_count(self, page: Adaptor) -> int:
        """Extract total result count from page."""
        # Try text containing result count via regex element search
        for stat in page.find_by_regex(r"\d+[,\d]*\s*results?", first_match=False):
            count = parse_result_count(stat.text)
            if count:
                return count

        # Try specific count elements
        for elem in page.css("span.sb_count, span.b_focusTextMedium, div.sb_count, div.b_focusTextMedium"):
            count = parse_result_count(elem.text)
            if count:
                return count

        return 0
