"""Tavily Search Engine

Tavily AI-powered Search API implementation.
Requires a Tavily API key from https://tavily.com/
"""
import logging

import httpx

from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)


@SearchProviderRegistry.register("tavily")
class TavilySearchEngine(SearchEngine):
    """Tavily AI-powered Search API implementation.

    Uses Tavily's Search API which provides:
    - AI-optimized search results
    - Relevance ranking powered by AI
    - Real-time web search
    - Clean, structured results
    """

    def __init__(self, api_key: str):
        """Initialize Tavily search engine.

        Args:
            api_key: Tavily API key
        """
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"

    async def search(
        self,
        query: str,
        date_range: str | None = None
    ) -> ToolResult[SearchResults]:
        """Search web pages using Tavily Search API.

        Args:
            query: Search query, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results
        """
        # Tavily API uses POST requests with JSON body
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",  # Use advanced for better results
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
            "max_results": 20,
        }

        # Add topic filter for date range (Tavily uses different approach)
        # Tavily doesn't have direct date filtering, but we can hint with the query
        if date_range and date_range != "all":
            date_hints = {
                "past_hour": "recent",
                "past_day": "today",
                "past_week": "this week",
                "past_month": "this month",
                "past_year": "this year",
            }
            if date_range in date_hints:
                # Append time hint to query
                payload["query"] = f"{query} {date_hints[date_range]}"

        headers = {
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()

                data = response.json()

                # Extract search results
                search_results = []
                results_list = data.get("results", [])

                for item in results_list:
                    try:
                        title = item.get("title", "")
                        link = item.get("url", "")
                        snippet = item.get("content", "")

                        # Truncate snippet if too long
                        if len(snippet) > 500:
                            snippet = snippet[:497] + "..."

                        if title and link:
                            search_results.append(SearchResultItem(
                                title=title,
                                link=link,
                                snippet=snippet
                            ))
                    except Exception as e:
                        logger.warning(f"Failed to parse Tavily result: {e}")
                        continue

                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=len(search_results),
                    results=search_results
                )

                return ToolResult(success=True, data=results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Tavily Search API authentication failed: invalid API key")
                message = "Tavily Search authentication failed: invalid API key"
            elif e.response.status_code == 429:
                logger.error("Tavily Search API rate limit exceeded")
                message = "Tavily Search rate limit exceeded"
            elif e.response.status_code == 400:
                logger.error("Tavily Search API bad request")
                message = "Tavily Search bad request: check query format"
            else:
                logger.error(f"Tavily Search HTTP error: {e}")
                message = f"Tavily Search HTTP error: {e.response.status_code}"

            error_results = SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[]
            )
            return ToolResult(success=False, message=message, data=error_results)

        except Exception as e:
            logger.error(f"Tavily Search failed: {e}")
            error_results = SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[]
            )

            return ToolResult(
                success=False,
                message=f"Tavily Search failed: {e}",
                data=error_results
            )


# Simple test
if __name__ == "__main__":
    import asyncio
    import os

    async def test():
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            print("Set TAVILY_API_KEY environment variable to test")
            return

        search_engine = TavilySearchEngine(api_key=api_key)
        result = await search_engine.search("Python programming best practices")

        if result.success:
            print(f"Search successful! Found {len(result.data.results)} results")
            for i, item in enumerate(result.data.results[:3]):
                print(f"{i+1}. {item.title}")
                print(f"   {item.link}")
                print(f"   {item.snippet[:100]}...")
                print()
        else:
            print(f"Search failed: {result.message}")

    asyncio.run(test())
