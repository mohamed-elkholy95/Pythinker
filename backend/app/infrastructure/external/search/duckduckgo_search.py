"""DuckDuckGo Search Engine

Privacy-focused search engine using DuckDuckGo's instant answer API
and web scraping fallback.
"""
from typing import Optional
import logging
import httpx
import re
from bs4 import BeautifulSoup

from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults, SearchResultItem
from app.domain.external.search import SearchEngine
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)


@SearchProviderRegistry.register("duckduckgo")
class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo web search engine implementation.

    Uses DuckDuckGo's HTML search page for results since they don't
    provide an official API for web search.
    """

    def __init__(self):
        """Initialize DuckDuckGo search engine."""
        self.base_url = "https://html.duckduckgo.com/html/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

    async def search(
        self,
        query: str,
        date_range: Optional[str] = None
    ) -> ToolResult[SearchResults]:
        """Search web pages using DuckDuckGo.

        Args:
            query: Search query, using 3-5 keywords
            date_range: (Optional) Time range filter (limited support)

        Returns:
            Search results
        """
        # DuckDuckGo HTML API uses POST with form data
        data = {
            "q": query,
            "b": "",  # Start position
        }

        # DuckDuckGo has limited date range support via query modifiers
        if date_range and date_range != "all":
            date_modifiers = {
                "past_day": "d",
                "past_week": "w",
                "past_month": "m",
                "past_year": "y",
            }
            if date_range in date_modifiers:
                # Append date filter to query
                data["df"] = date_modifiers[date_range]

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
                follow_redirects=True
            ) as client:
                response = await client.post(self.base_url, data=data)
                response.raise_for_status()

                # Parse HTML content
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract search results
                search_results = []

                # DuckDuckGo HTML results are in divs with class 'result'
                result_items = soup.find_all('div', class_='result')

                for item in result_items:
                    try:
                        # Extract title and link
                        title = ""
                        link = ""

                        # Title is in a.result__a
                        title_tag = item.find('a', class_='result__a')
                        if title_tag:
                            title = title_tag.get_text(strip=True)
                            link = title_tag.get('href', '')

                        if not title:
                            continue

                        # Extract snippet from result__snippet
                        snippet = ""
                        snippet_tag = item.find('a', class_='result__snippet')
                        if snippet_tag:
                            snippet = snippet_tag.get_text(strip=True)

                        # Clean up link - DuckDuckGo uses redirect URLs
                        if link and '//duckduckgo.com/l/' in link:
                            # Try to extract actual URL from redirect
                            import urllib.parse
                            parsed = urllib.parse.urlparse(link)
                            params = urllib.parse.parse_qs(parsed.query)
                            if 'uddg' in params:
                                link = urllib.parse.unquote(params['uddg'][0])

                        if title and link:
                            search_results.append(SearchResultItem(
                                title=title,
                                link=link,
                                snippet=snippet
                            ))
                    except Exception as e:
                        logger.warning(f"Failed to parse DuckDuckGo result: {e}")
                        continue

                # DuckDuckGo doesn't provide total result count
                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=len(search_results),
                    results=search_results
                )

                return ToolResult(success=True, data=results)

        except Exception as e:
            logger.error(f"DuckDuckGo Search failed: {e}")
            error_results = SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[]
            )

            return ToolResult(
                success=False,
                message=f"DuckDuckGo Search failed: {e}",
                data=error_results
            )


# Simple test
if __name__ == "__main__":
    import asyncio

    async def test():
        search_engine = DuckDuckGoSearchEngine()
        result = await search_engine.search("Python programming")

        if result.success:
            print(f"Search successful! Found {len(result.data.results)} results")
            for i, item in enumerate(result.data.results[:3]):
                print(f"{i+1}. {item.title}")
                print(f"   {item.link}")
                print(f"   {item.snippet}")
                print()
        else:
            print(f"Search failed: {result.message}")

    asyncio.run(test())
