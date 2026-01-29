"""SearXNG Metasearch Engine Implementation

Production-grade search engine adapter with:
- Robust error handling and retry logic with exponential backoff
- Engine rotation and circuit breaker for resilience
- Rate limit and CAPTCHA detection
- Connection pooling and timeout management
- Comprehensive logging for debugging
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_random_exponential,
)

from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# Reliable engines in order of preference
# These engines are known to have stable APIs and good result quality
RELIABLE_ENGINES = ["duckduckgo", "brave", "qwant", "mojeek", "wikipedia"]

# Engine groups for different query types - ordered by reliability
GENERAL_ENGINES = "duckduckgo,brave,qwant,mojeek"
FALLBACK_ENGINES = "google,bing,yahoo,yandex"
ACADEMIC_ENGINES = "arxiv,wikipedia,wikidata"
CODE_ENGINES = "github,stackexchange"

# CAPTCHA indicators in response content
CAPTCHA_INDICATORS = [
    "captcha", "CAPTCHA", "robot", "bot detection",
    "unusual traffic", "verify you are human", "access denied",
    "rate limit", "too many requests", "blocked"
]


@dataclass
class EngineHealth:
    """Track health status of individual search engines."""
    failures: int = 0
    last_failure: datetime | None = None
    is_suspended: bool = False
    suspend_until: datetime | None = None
    failure_reasons: list[str] = field(default_factory=list)

    def record_failure(self, reason: str, suspend_minutes: int = 5):
        """Record a failure and potentially suspend the engine."""
        self.failures += 1
        self.last_failure = datetime.now()
        self.failure_reasons.append(reason)

        # Keep only last 10 reasons
        if len(self.failure_reasons) > 10:
            self.failure_reasons = self.failure_reasons[-10:]

        # Suspend after 3 consecutive failures
        if self.failures >= 3:
            self.is_suspended = True
            # Exponential suspension: 5min, 10min, 20min, max 60min
            suspend_time = min(suspend_minutes * (2 ** (self.failures - 3)), 60)
            self.suspend_until = datetime.now() + timedelta(minutes=suspend_time)
            logger.warning(f"Engine suspended for {suspend_time} minutes due to repeated failures")

    def record_success(self):
        """Record a successful request, reset failure count."""
        self.failures = 0
        self.is_suspended = False
        self.suspend_until = None

    def is_available(self) -> bool:
        """Check if engine is available for use."""
        if not self.is_suspended:
            return True
        if self.suspend_until and datetime.now() > self.suspend_until:
            # Suspension expired, give it another chance
            self.is_suspended = False
            self.suspend_until = None
            self.failures = max(0, self.failures - 1)  # Reduce failure count
            return True
        return False


class EngineCircuitBreaker:
    """Circuit breaker for managing engine availability."""

    def __init__(self):
        self._engine_health: dict[str, EngineHealth] = {}
        self._lock = asyncio.Lock()

    def _get_health(self, engine: str) -> EngineHealth:
        """Get or create health record for an engine."""
        if engine not in self._engine_health:
            self._engine_health[engine] = EngineHealth()
        return self._engine_health[engine]

    async def record_failure(self, engine: str, reason: str):
        """Record a failure for an engine."""
        async with self._lock:
            health = self._get_health(engine)
            health.record_failure(reason)
            logger.info(f"Engine '{engine}' failure recorded: {reason} (total: {health.failures})")

    async def record_success(self, engine: str):
        """Record a success for an engine."""
        async with self._lock:
            health = self._get_health(engine)
            health.record_success()

    async def get_available_engines(self, requested_engines: list[str]) -> list[str]:
        """Filter engines to only those currently available."""
        async with self._lock:
            available = []
            for engine in requested_engines:
                health = self._get_health(engine)
                if health.is_available():
                    available.append(engine)
                else:
                    logger.debug(f"Engine '{engine}' is suspended until {health.suspend_until}")
            return available

    async def get_status(self) -> dict[str, dict]:
        """Get current status of all engines."""
        async with self._lock:
            return {
                engine: {
                    "failures": health.failures,
                    "is_suspended": health.is_suspended,
                    "suspend_until": health.suspend_until.isoformat() if health.suspend_until else None,
                    "last_failure": health.last_failure.isoformat() if health.last_failure else None,
                }
                for engine, health in self._engine_health.items()
            }


# Global circuit breaker instance
_circuit_breaker = EngineCircuitBreaker()


@SearchProviderRegistry.register("searxng")
class SearXNGSearchEngine(SearchEngine):
    """SearXNG metasearch engine implementation with production-grade reliability.

    Features:
    - Automatic retry with exponential backoff and jitter
    - Engine rotation with circuit breaker pattern
    - Rate limit and CAPTCHA detection
    - Connection pooling for performance
    - Comprehensive error handling
    """

    def __init__(
        self,
        base_url: str = "http://searxng:8080",
        timeout: float = 30.0,
        max_retries: int = 3,
        max_retry_delay: float = 30.0,
        enable_fallback: bool = True
    ):
        """Initialize SearXNG search engine.

        Args:
            base_url: Base URL of the SearXNG instance
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            max_retry_delay: Maximum delay between retries in seconds
            enable_fallback: Enable fallback to alternative engines
        """
        self.base_url = base_url.rstrip('/')
        self.search_url = f"{self.base_url}/search"
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_retry_delay = max_retry_delay
        self.enable_fallback = enable_fallback
        self.headers = {
            'Accept': 'application/json',
            'User-Agent': 'Pythinker-Agent/1.0',
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1',
        }
        # Reusable HTTP client for connection pooling
        self._client: httpx.AsyncClient | None = None
        # Circuit breaker for engine management
        self._circuit_breaker = _circuit_breaker

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

    def _get_engines_for_query(self, query: str) -> list[str]:
        """Select appropriate engines based on query content.

        Args:
            query: Search query string

        Returns:
            List of engine names in order of preference
        """
        query_lower = query.lower()
        engines = GENERAL_ENGINES.split(",")

        # Academic/research queries
        if any(kw in query_lower for kw in ['paper', 'research', 'study', 'journal', 'arxiv']):
            engines.extend(ACADEMIC_ENGINES.split(","))

        # Code/programming queries
        if any(kw in query_lower for kw in ['code', 'programming', 'github', 'stackoverflow', 'api', 'library']):
            engines.extend(CODE_ENGINES.split(","))

        # Add fallback engines at the end
        if self.enable_fallback:
            engines.extend(FALLBACK_ENGINES.split(","))

        return engines

    async def _get_active_engines(self, query: str) -> str:
        """Get comma-separated list of currently available engines."""
        all_engines = self._get_engines_for_query(query)
        available = await self._circuit_breaker.get_available_engines(all_engines)

        if not available:
            # All engines suspended, reset and try all
            logger.warning("All engines suspended, resetting circuit breaker")
            available = all_engines[:4]  # Try first 4 general engines

        return ",".join(available)

    def _detect_captcha_or_block(self, response_text: str) -> str | None:
        """Detect CAPTCHA or blocking in response content.

        Args:
            response_text: Raw response text

        Returns:
            Blocking reason if detected, None otherwise
        """
        text_lower = response_text.lower()
        for indicator in CAPTCHA_INDICATORS:
            if indicator.lower() in text_lower:
                return indicator
        return None

    async def _process_unresponsive_engines(self, unresponsive: list) -> None:
        """Process and record unresponsive engines from SearXNG response."""
        for engine_info in unresponsive:
            if isinstance(engine_info, list) and len(engine_info) >= 2:
                engine_name, reason = engine_info[0], engine_info[1]
                # Detect specific issues
                reason_lower = str(reason).lower()
                if any(x in reason_lower for x in ['captcha', 'rate', 'too many', 'blocked', 'denied']):
                    await self._circuit_breaker.record_failure(engine_name, reason)
                elif 'timeout' in reason_lower:
                    await self._circuit_breaker.record_failure(engine_name, "timeout")
            elif isinstance(engine_info, str):
                await self._circuit_breaker.record_failure(engine_info, "unresponsive")

    async def search(
        self,
        query: str,
        date_range: str | None = None
    ) -> ToolResult[SearchResults]:
        """Search web pages using SearXNG metasearch with robust error handling.

        Args:
            query: Search query (3-5 keywords recommended)
            date_range: Optional time range filter

        Returns:
            ToolResult containing SearchResults
        """
        # Get available engines (filtered by circuit breaker)
        engines = await self._get_active_engines(query)

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

        # Attempt search with exponential backoff retry
        try:
            result = await self._search_with_retry(query, params, date_range)
            return result
        except RetryError as e:
            # All retries exhausted
            last_error = e.last_attempt.exception() if e.last_attempt else None
            error_message = f"Search failed after {self.max_retries} retries"
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
        except Exception as e:
            logger.error(f"Unexpected search error: {type(e).__name__}: {e}")
            return ToolResult(
                success=False,
                message=f"Search error: {type(e).__name__}",
                data=SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=0,
                    results=[]
                )
            )

    async def _search_with_retry(
        self,
        query: str,
        params: dict,
        date_range: str | None
    ) -> ToolResult[SearchResults]:
        """Execute search with tenacity-based exponential backoff retry.

        Uses exponential backoff with jitter to avoid thundering herd problem.
        """
        attempt_count = 0

        @retry(
            stop=(stop_after_attempt(self.max_retries) | stop_after_delay(60)),
            wait=wait_random_exponential(multiplier=1, min=1, max=self.max_retry_delay),
            retry=retry_if_exception_type((
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ConnectError,
            )),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def _do_search():
            nonlocal attempt_count
            attempt_count += 1

            client = await self._get_client()
            response = await client.get(self.search_url, params=params)

            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "30")
                wait_time = min(int(retry_after) if retry_after.isdigit() else 30, 60)
                logger.warning(f"Rate limited (429), waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time + random.uniform(1, 5))  # Add jitter
                raise httpx.NetworkError(f"Rate limited, retrying after {wait_time}s")

            # Handle server errors with retry
            if response.status_code >= 500:
                logger.warning(f"Server error {response.status_code}, will retry")
                raise httpx.NetworkError(f"Server error {response.status_code}")

            response.raise_for_status()

            # Check for CAPTCHA/blocking in response
            response_text = response.text
            block_reason = self._detect_captcha_or_block(response_text)
            if block_reason:
                logger.warning(f"Detected blocking: {block_reason}")
                # Don't retry CAPTCHA, just note it

            data = response.json()

            # Process unresponsive engines and update circuit breaker
            if "unresponsive_engines" in data:
                unresponsive = data.get("unresponsive_engines", [])
                if unresponsive:
                    logger.warning(f"Unresponsive engines: {unresponsive}")
                    await self._process_unresponsive_engines(unresponsive)

            # Parse results
            search_results = self._parse_results(data)
            total_results = data.get("number_of_results", len(search_results))

            # Record success for engines that responded
            responding_engines = set(params.get("engines", "").split(","))
            unresponsive_names = {e[0] if isinstance(e, list) else e for e in data.get("unresponsive_engines", [])}
            for engine in responding_engines - unresponsive_names:
                await self._circuit_breaker.record_success(engine)

            results = SearchResults(
                query=query,
                date_range=date_range,
                total_results=total_results,
                results=search_results
            )

            if search_results:
                logger.info(f"Search successful: '{query[:50]}' returned {len(search_results)} results (attempt {attempt_count})")
            else:
                logger.warning(f"Search returned no results: '{query[:50]}'")

            return ToolResult(success=True, data=results)

        return await _do_search()

    def _parse_results(self, data: dict) -> list[SearchResultItem]:
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

    async def get_engine_status(self) -> dict[str, dict]:
        """Get current health status of all tracked engines.

        Returns:
            Dictionary mapping engine names to their health status
        """
        return await self._circuit_breaker.get_status()

    async def reset_engine(self, engine_name: str) -> None:
        """Manually reset an engine's circuit breaker status.

        Args:
            engine_name: Name of the engine to reset
        """
        async with self._circuit_breaker._lock:
            if engine_name in self._circuit_breaker._engine_health:
                self._circuit_breaker._engine_health[engine_name] = EngineHealth()
                logger.info(f"Reset circuit breaker for engine: {engine_name}")

    async def reset_all_engines(self) -> None:
        """Reset circuit breaker status for all engines."""
        async with self._circuit_breaker._lock:
            self._circuit_breaker._engine_health.clear()
            logger.info("Reset circuit breaker for all engines")


# Utility function to get global circuit breaker status
def get_search_circuit_breaker() -> EngineCircuitBreaker:
    """Get the global search engine circuit breaker."""
    return _circuit_breaker


# Test function for development
if __name__ == "__main__":

    async def test():
        search_engine = SearXNGSearchEngine(base_url="http://localhost:8888")

        # Health check
        healthy = await search_engine.health_check()
        print(f"SearXNG healthy: {healthy}")

        if healthy:
            # Test multiple searches to see circuit breaker in action
            queries = [
                "Python programming best practices 2026",
                "LangGraph AI agent framework",
                "machine learning tutorials"
            ]

            for query in queries:
                result = await search_engine.search(query)

                if result.success:
                    print(f"\nSearch successful! Found {len(result.data.results)} results for: {query[:40]}...")
                    for i, item in enumerate(result.data.results[:3]):
                        print(f"  {i+1}. {item.title}")
                else:
                    print(f"\nSearch failed: {result.message}")

            # Print engine status
            print("\n--- Engine Health Status ---")
            status = await search_engine.get_engine_status()
            for engine, health in status.items():
                print(f"  {engine}: failures={health['failures']}, suspended={health['is_suspended']}")

        await search_engine.close()

    asyncio.run(test())
