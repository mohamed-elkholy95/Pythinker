"""Brave Search Engine

Brave Search API implementation with privacy-focused search results.
Requires a Brave Search API key from https://brave.com/search/api/
"""

import logging

import httpx

from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)


@SearchProviderRegistry.register("brave")
class BraveSearchEngine(SearchEngine):
    """Brave Search API implementation.

    Uses Brave's official Search API which provides:
    - Privacy-focused search results
    - No tracking or profiling
    - Independent search index
    """

    def __init__(self, api_key: str):
        """Initialize Brave search engine.

        Args:
            api_key: Brave Search API key
        """
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Search web pages using Brave Search API.

        Args:
            query: Search query, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results
        """
        params = {
            "q": query,
            "count": 20,  # Number of results
            "text_decorations": False,  # No HTML formatting
            "search_lang": "en",
        }

        # Add freshness filter for date range
        if date_range and date_range != "all":
            # Brave API uses 'freshness' parameter
            date_mapping = {
                "past_hour": "ph",  # Past hour
                "past_day": "pd",  # Past day (24 hours)
                "past_week": "pw",  # Past week
                "past_month": "pm",  # Past month
                "past_year": "py",  # Past year
            }
            if date_range in date_mapping:
                params["freshness"] = date_mapping[date_range]

        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

                data = response.json()

                # Extract search results
                search_results = []
                web_results = data.get("web", {}).get("results", [])

                for item in web_results:
                    try:
                        title = item.get("title", "")
                        link = item.get("url", "")
                        snippet = item.get("description", "")

                        if title and link:
                            search_results.append(SearchResultItem(title=title, link=link, snippet=snippet))
                    except Exception as e:
                        logger.warning(f"Failed to parse Brave result: {e}")
                        continue

                # Get total results count if available
                total_results = data.get("web", {}).get("total_count", len(search_results))

                results = SearchResults(
                    query=query, date_range=date_range, total_results=total_results, results=search_results
                )

                return ToolResult(success=True, data=results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Brave Search API authentication failed: invalid API key")
                message = "Brave Search authentication failed: invalid API key"
            elif e.response.status_code == 429:
                logger.error("Brave Search API rate limit exceeded")
                message = "Brave Search rate limit exceeded"
            else:
                logger.error(f"Brave Search HTTP error: {e}")
                message = f"Brave Search HTTP error: {e.response.status_code}"

            error_results = SearchResults(query=query, date_range=date_range, total_results=0, results=[])
            return ToolResult(success=False, message=message, data=error_results)

        except Exception as e:
            logger.error(f"Brave Search failed: {e}")
            error_results = SearchResults(query=query, date_range=date_range, total_results=0, results=[])

            return ToolResult(success=False, message=f"Brave Search failed: {e}", data=error_results)


# Simple test
if __name__ == "__main__":
    import asyncio
    import os

    async def test():
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not api_key:
            print("Set BRAVE_SEARCH_API_KEY environment variable to test")
            return

        search_engine = BraveSearchEngine(api_key=api_key)
        result = await search_engine.search("Python programming")

        if result.success:
            print(f"Search successful! Found {len(result.data.results)} results")
            for i, item in enumerate(result.data.results[:3]):
                print(f"{i + 1}. {item.title}")
                print(f"   {item.link}")
                print(f"   {item.snippet}")
                print()
        else:
            print(f"Search failed: {result.message}")

    asyncio.run(test())
