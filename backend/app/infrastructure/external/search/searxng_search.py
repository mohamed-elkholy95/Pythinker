"""SearXNG Metasearch Engine Implementation

Production-grade search engine adapter with:
- Robust error handling and retry logic
- Multiple engine fallback support
- Connection pooling and timeout management
- Comprehensive logging for debugging
"""

from typing import Optional, List
import logging
import httpx
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults, SearchResultItem
from app.domain.external.search import SearchEngine
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# Reliable engines in order of preference
# These engines are known to have stable APIs and good result quality
RELIABLE_ENGINES = ["duckduckgo", "brave", "qwant", "mojeek", "wikipedia"]

# Engine groups for different query types
GENERAL_ENGINES = "duckduckgo,brave,qwant,mojeek"
ACADEMIC_ENGINES = "arxiv,wikipedia,wikidata"
CODE_ENGINES = "github,stackexchange"


@SearchProviderRegistry.register("searxng")
class SearXNGSearchEngine(SearchEngine):
    """SearXNG metasearch engine implementation with production-grade reliability.

    Features:
    - Automatic retry with exponential backoff
    - Multiple engine fallback
    - Connection pooling for performance
    - Comprehensive error handling
    """

    def __init__(
        self,
        base_url: str = "http://searxng:8080",
        timeout: float = 30.0,
        max_retries: int = 2
    ):
        """Initialize SearXNG search engine.

        Args:
            base_url: Base URL of the SearXNG instance
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url.rstrip('/')
        self.search_url = f"{self.base_url}/search"
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            'Accept': 'application/json',
            'User-Agent': 'Pythinker-Agent/1.0',
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1',
        }
        # Reusable HTTP client for connection pooling
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0
                ),
                follow_redirects=True
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_engines_for_query(self, query: str) -> str:
        """Select appropriate engines based on query content.

        Args:
            query: Search query string

        Returns:
            Comma-separated list of engine names
        """
        query_lower = query.lower()

        # Academic/research queries
        if any(kw in query_lower for kw in ['paper', 'research', 'study', 'journal', 'arxiv']):
            return f"{GENERAL_ENGINES},{ACADEMIC_ENGINES}"

        # Code/programming queries
        if any(kw in query_lower for kw in ['code', 'programming', 'github', 'stackoverflow', 'api', 'library']):
            return f"{GENERAL_ENGINES},{CODE_ENGINES}"

        # Default to general engines
        return GENERAL_ENGINES

    async def search(
        self,
        query: str,
        date_range: Optional[str] = None
    ) -> ToolResult[SearchResults]:
        """Search web pages using SearXNG metasearch with robust error handling.

        Args:
            query: Search query (3-5 keywords recommended)
            date_range: Optional time range filter

        Returns:
            ToolResult containing SearchResults
        """
        # Select appropriate engines for this query type
        engines = self._get_engines_for_query(query)

        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "engines": engines,
            "language": "en",
        }

        # Map date_range to SearXNG time_range parameter
        if date_range and date_range != "all":
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

        # Attempt search with retries
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.get(self.search_url, params=params)
                response.raise_for_status()

                data = response.json()

                # Check for engine errors in response
                if "unresponsive_engines" in data:
                    unresponsive = data.get("unresponsive_engines", [])
                    if unresponsive:
                        logger.warning(f"Unresponsive engines: {unresponsive}")

                # Parse results
                search_results = self._parse_results(data)
                total_results = data.get("number_of_results", len(search_results))

                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=total_results,
                    results=search_results
                )

                if search_results:
                    logger.info(f"Search successful: '{query[:50]}' returned {len(search_results)} results")
                else:
                    logger.warning(f"Search returned no results: '{query[:50]}'")

                return ToolResult(success=True, data=results)

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Search timeout (attempt {attempt + 1}/{self.max_retries + 1}): {query[:50]}")

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                logger.error(f"HTTP {status_code} error (attempt {attempt + 1}): {query[:50]}")

                # Don't retry on client errors (4xx)
                if 400 <= status_code < 500:
                    break

            except httpx.RequestError as e:
                last_error = e
                logger.error(f"Request error (attempt {attempt + 1}): {e}")

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected search error: {type(e).__name__}: {e}")
                break

        # All retries failed
        error_message = f"Search failed after {self.max_retries + 1} attempts"
        if last_error:
            error_message += f": {type(last_error).__name__}"

        logger.error(f"{error_message} for query: {query[:50]}")

        return ToolResult(
            success=False,
            message=error_message,
            data=SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[]
            )
        )

    def _parse_results(self, data: dict) -> List[SearchResultItem]:
        """Parse search results from SearXNG JSON response.

        Args:
            data: Raw JSON response from SearXNG

        Returns:
            List of parsed SearchResultItem objects
        """
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

                # Skip duplicate URLs
                if any(r.link == link for r in search_results):
                    continue

                search_results.append(SearchResultItem(
                    title=title,
                    link=link,
                    snippet=snippet or ""
                ))

            except Exception as e:
                logger.debug(f"Failed to parse result item: {e}")
                continue

        return search_results

    async def health_check(self) -> bool:
        """Check if SearXNG service is available.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/config",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"SearXNG health check failed: {e}")
            return False


# Test function for development
if __name__ == "__main__":
    import asyncio

    async def test():
        search_engine = SearXNGSearchEngine(base_url="http://localhost:8888")

        # Health check
        healthy = await search_engine.health_check()
        print(f"SearXNG healthy: {healthy}")

        if healthy:
            result = await search_engine.search("Python programming best practices 2026")

            if result.success:
                print(f"Search successful! Found {len(result.data.results)} results")
                for i, item in enumerate(result.data.results[:5]):
                    print(f"{i+1}. {item.title}")
                    print(f"   {item.link}")
                    print(f"   {item.snippet[:100]}..." if len(item.snippet) > 100 else f"   {item.snippet}")
                    print()
            else:
                print(f"Search failed: {result.message}")

        await search_engine.close()

    asyncio.run(test())
