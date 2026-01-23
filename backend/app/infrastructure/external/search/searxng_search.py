from typing import Optional
import logging
import httpx
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults, SearchResultItem
from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)


class SearXNGSearchEngine(SearchEngine):
    """SearXNG metasearch engine implementation using JSON API"""

    def __init__(self, base_url: str = "http://searxng:8080"):
        """Initialize SearXNG search engine

        Args:
            base_url: Base URL of the SearXNG instance (e.g., http://searxng:8080)
        """
        self.base_url = base_url.rstrip('/')
        self.search_url = f"{self.base_url}/search"
        self.headers = {
            'Accept': 'application/json',
            'User-Agent': 'Pythinker-Agent/1.0',
        }

    async def search(
        self,
        query: str,
        date_range: Optional[str] = None
    ) -> ToolResult[SearchResults]:
        """Search web pages using SearXNG metasearch

        Args:
            query: Search query, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results
        """
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }

        # Add time range filter
        if date_range and date_range != "all":
            # Convert date_range to SearXNG time_range parameter
            date_mapping = {
                "past_hour": None,  # SearXNG doesn't support hourly filtering
                "past_day": "day",
                "past_week": "week",
                "past_month": "month",
                "past_year": "year"
            }
            mapped_range = date_mapping.get(date_range)
            if mapped_range:
                params["time_range"] = mapped_range

        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as client:
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()

                data = response.json()

                # Extract search results from JSON response
                search_results = []
                results_data = data.get("results", [])

                for item in results_data:
                    try:
                        title = item.get("title", "").strip()
                        link = item.get("url", "").strip()
                        snippet = item.get("content", "").strip()

                        # Skip results without essential fields
                        if not title or not link:
                            continue

                        search_results.append(SearchResultItem(
                            title=title,
                            link=link,
                            snippet=snippet or ""
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to parse SearXNG result: {e}")
                        continue

                # Get total results count
                total_results = data.get("number_of_results", len(search_results))

                # Build return result
                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=total_results,
                    results=search_results
                )

                return ToolResult(success=True, data=results)

        except httpx.TimeoutException:
            logger.error("SearXNG search timed out")
            return ToolResult(
                success=False,
                message="SearXNG search timed out",
                data=SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=0,
                    results=[]
                )
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"SearXNG HTTP error: {e.response.status_code}")
            return ToolResult(
                success=False,
                message=f"SearXNG HTTP error: {e.response.status_code}",
                data=SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=0,
                    results=[]
                )
            )
        except Exception as e:
            logger.error(f"SearXNG Search failed: {e}")
            return ToolResult(
                success=False,
                message=f"SearXNG Search failed: {e}",
                data=SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=0,
                    results=[]
                )
            )


# Simple test
if __name__ == "__main__":
    import asyncio

    async def test():
        search_engine = SearXNGSearchEngine(base_url="http://localhost:8080")
        result = await search_engine.search("Python programming")

        if result.success:
            print(f"Search successful! Found {len(result.data.results)} results")
            for i, item in enumerate(result.data.results[:5]):
                print(f"{i+1}. {item.title}")
                print(f"   {item.link}")
                print(f"   {item.snippet[:100]}..." if len(item.snippet) > 100 else f"   {item.snippet}")
                print()
        else:
            print(f"Search failed: {result.message}")

    asyncio.run(test())
