"""Baidu Search Engine

Baidu web search engine implementation using web scraping.
No API key required.
"""

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry
from app.infrastructure.external.search.utils import clean_redirect_url, extract_text_from_tag


@SearchProviderRegistry.register("baidu")
class BaiduSearchEngine(SearchEngineBase):
    """Baidu web search engine implementation using web scraping."""

    provider_name = "Baidu"
    engine_type = SearchEngineType.SCRAPER

    def __init__(self, timeout: float | None = None):
        """Initialize Baidu search engine."""
        super().__init__(timeout=timeout)
        self.base_url = "https://www.baidu.com/s"
        self.cookies = httpx.Cookies()

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Baidu gpc parameter mapping."""
        return {
            "past_day": "1",
            "past_week": "2",
            "past_month": "3",
            "past_year": "4",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Baidu search parameters."""
        params: dict[str, Any] = {"wd": query}

        if mapped := self._map_date_range(date_range):
            params["gpc"] = f"stf={mapped}"

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Baidu with cookie handling."""
        response = await client.get(self.base_url, params=params, cookies=self.cookies)
        self.cookies.update(response.cookies)
        return response

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Baidu HTML response."""
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[SearchResultItem] = []

        # Try different selectors for Baidu search results
        result_divs = (
            soup.find_all("div", class_="result")
            or soup.find_all("div", class_="result-op")
            or soup.find_all("div", class_="c-container")
            or soup.find_all("div", attrs={"mu": True})
            or soup.find_all("div", attrs={"data-log": True})
        )

        for div in result_divs:
            result = self._parse_result_item(div)
            if result:
                results.append(result)

        # Extract total results count
        total_results = self._extract_result_count(soup)

        return results, total_results

    def _parse_result_item(self, item: BeautifulSoup) -> SearchResultItem | None:
        """Parse a single Baidu result item."""
        title = ""
        link = ""

        # Method 1: Standard h3 > a structure
        title_tag = item.find("h3")
        if title_tag:
            title_a = title_tag.find("a")
            if title_a:
                title = extract_text_from_tag(title_a)
                link = title_a.get("href", "")

        # Method 2: Try a tag with title-like classes
        if not title:
            for a_tag in item.find_all("a", class_=re.compile(r"title|link")):
                text = extract_text_from_tag(a_tag)
                if text:
                    title = text
                    link = a_tag.get("href", "")
                    break

        # Method 3: Try any a tag with substantial text
        if not title:
            for a_tag in item.find_all("a"):
                text = extract_text_from_tag(a_tag)
                if len(text) > 10 and not text.startswith("http"):
                    title = text
                    link = a_tag.get("href", "")
                    break

        if not title:
            return None

        # Extract snippet
        snippet = self._extract_snippet(item)

        # Clean up link
        link = clean_redirect_url(link, "https://www.baidu.com")

        if title and link:
            return SearchResultItem(title=title, link=link, snippet=snippet)
        return None

    def _extract_snippet(self, item: BeautifulSoup) -> str:
        """Extract snippet from Baidu result item."""
        # Method 1: Look for abstract/content classes
        snippet_divs = item.find_all(["div", "span"], class_=re.compile(r"abstract|content|desc"))
        if snippet_divs:
            return extract_text_from_tag(snippet_divs[0])

        # Method 2: Look for common text containers
        for container in item.find_all(["div", "span", "p"], class_=re.compile(r"c-span|c-abstract")):
            text = extract_text_from_tag(container)
            if len(text) > 20:
                return text

        # Method 3: Get any substantial text
        all_text = item.get_text(strip=True)
        # Split by Chinese sentence terminators
        sentences = re.split(r"[\u3002\uFF01\uFF1F\n]", all_text)
        for sentence in sentences:
            if len(sentence.strip()) > 20:
                return sentence.strip()

        return ""

    def _extract_result_count(self, soup: BeautifulSoup) -> int:
        """Extract total result count from page."""
        results_nums = soup.find_all(string=re.compile(r"百度为您找到相关结果约"))
        if results_nums:
            match = re.search(r"约([\d,]+)个结果", results_nums[0])
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
                except ValueError:
                    pass
        return 0
