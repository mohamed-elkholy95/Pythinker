"""Search Engine Base Class

Provides common functionality for all search engine implementations:
- HTTP client management with connection pooling
- Standardized error/success response creation
- Date range mapping template
- Result parsing utilities
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar

import httpx

from app.core.retry import RetryConfig, calculate_delay
from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.http_pool import HTTPClientConfig, HTTPClientPool, ManagedHTTPClient

logger = logging.getLogger(__name__)

CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_EXPECTED_TRANSIENT_ERROR_PATTERNS = (
    "api key",
    "keys exhausted",
    "quota",
    "rate limit",
    "timed out",
    "timeout",
    "temporarily unavailable",
)


class SearchEngineType(str, Enum):
    """Search engine types for determining base behavior."""

    API = "api"  # JSON API-based (Google, Brave, Tavily)
    SCRAPER = "scraper"  # HTML scraping-based (Bing, Baidu, DuckDuckGo)
    HYBRID = "hybrid"  # Both JSON and HTML


class SearchEngineBase(ABC, SearchEngine):
    """Abstract base class for all search engine implementations.

    Provides common functionality:
    - HTTP client management with connection pooling
    - Standardized error handling and response creation
    - Date range mapping template
    - Result parsing utilities

    Subclasses must implement:
    - _get_date_range_mapping(): Provider-specific date range values
    - _build_request_params(): Build request parameters
    - _execute_request(): Execute the HTTP request
    - _parse_response(): Parse provider-specific response

    Example:
        class BraveSearchEngine(SearchEngineBase):
            provider_name = "Brave"
            engine_type = SearchEngineType.API

            def _get_date_range_mapping(self) -> dict[str, str]:
                return {"past_hour": "ph", "past_day": "pd", ...}

            def _build_request_params(self, query: str, date_range: str | None) -> dict:
                return {"q": query, "count": 20}

            async def _execute_request(self, client: httpx.AsyncClient, params: dict):
                return await client.get(self.base_url, params=params)

            def _parse_response(self, response: httpx.Response):
                data = response.json()
                results = [self._parse_json_result_item(item) for item in data["results"]]
                return [r for r in results if r], len(results)
    """

    engine_type: SearchEngineType = SearchEngineType.API
    provider_name: str = "unknown"
    default_timeout: float = 30.0

    # Common browser headers for scraping engines
    BROWSER_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    # HTTP status codes that are worth retrying
    RETRYABLE_STATUS_CODES: ClassVar[set[int]] = {429, 502, 503, 504}
    # Rotate key but do NOT retry the same request — these are auth/policy errors
    ROTATE_NO_RETRY_CODES: ClassVar[set[int]] = {401, 403}
    # Permanent client errors — do not retry, do not rotate key, fail immediately
    PERMANENT_FAIL_CODES: ClassVar[set[int]] = {400}

    # Per-class semaphores keyed by class name + max_concurrent value
    _semaphores: ClassVar[dict[str, asyncio.Semaphore]] = {}

    def __init__(self, timeout: float | None = None, max_concurrent: int = 3):
        """Initialize search engine base.

        Args:
            timeout: Optional custom timeout in seconds
            max_concurrent: Maximum concurrent in-flight requests for this provider
        """
        self.timeout = timeout or self.default_timeout
        self._max_concurrent = max_concurrent

    @property
    def _semaphore(self) -> asyncio.Semaphore:
        """Per-provider async semaphore (class-level, keyed by class name + limit)."""
        key = f"{self.__class__.__name__}:{self._max_concurrent}"
        if key not in self.__class__._semaphores:
            self.__class__._semaphores[key] = asyncio.Semaphore(self._max_concurrent)
        return self.__class__._semaphores[key]

    # ===== Abstract Methods (provider-specific) =====

    @abstractmethod
    def _get_date_range_mapping(self) -> dict[str, str]:
        """Return provider-specific date range parameter mapping.

        Keys are standard date range values (past_hour, past_day, etc.),
        values are provider-specific parameters.

        Returns:
            Dict mapping standard date ranges to provider values
        """
        ...

    @abstractmethod
    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build provider-specific request parameters.

        Args:
            query: Search query string
            date_range: Optional date range filter

        Returns:
            Dict of request parameters
        """
        ...

    @abstractmethod
    async def _execute_request(self, client: ManagedHTTPClient, params: dict[str, Any]) -> httpx.Response:
        """Execute the actual HTTP request.

        Args:
            client: Managed HTTP client from the pool
            params: Request parameters from _build_request_params

        Returns:
            HTTP response
        """
        ...

    @abstractmethod
    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse provider-specific response format.

        Args:
            response: HTTP response to parse

        Returns:
            Tuple of (search_results list, total_results count)
        """
        ...

    # ===== Common Implementation =====

    def _get_headers(self) -> dict[str, str]:
        """Get headers for requests. Override for custom headers.

        Returns:
            Dict of HTTP headers
        """
        if self.engine_type == SearchEngineType.SCRAPER:
            return self.BROWSER_HEADERS.copy()
        return {"Accept": "application/json", "Accept-Encoding": "gzip"}

    async def _get_client(self) -> ManagedHTTPClient:
        """Get a pooled HTTP client for this search engine.

        Uses HTTPClientPool so connections are reused across requests and
        Prometheus metrics are recorded automatically.

        Returns:
            ManagedHTTPClient from the shared pool
        """
        client_name = f"search-{self.__class__.__name__.lower()}"
        config = HTTPClientConfig(
            headers=self._get_headers(),
            timeout=self.timeout,
            connect_timeout=10.0,
            read_timeout=self.timeout,
        )
        return await HTTPClientPool.get_client(
            name=client_name,
            config=config,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Release this engine's pooled HTTP client."""
        client_name = f"search-{self.__class__.__name__.lower()}"
        await HTTPClientPool.close_client(client_name)

    def _map_date_range(self, date_range: str | None) -> str | None:
        """Map standard date range to provider-specific value.

        Args:
            date_range: Standard date range (past_hour, past_day, etc.)

        Returns:
            Provider-specific date range value or None
        """
        if not date_range or date_range == "all":
            return None
        mapping = self._get_date_range_mapping()
        return mapping.get(date_range)

    def _create_success_result(
        self,
        query: str,
        date_range: str | None,
        results: list[SearchResultItem],
        total_results: int,
    ) -> ToolResult[SearchResults]:
        """Create standardized success response.

        Args:
            query: Original search query
            date_range: Date range used
            results: List of search results
            total_results: Total count of results

        Returns:
            ToolResult with success=True
        """
        return ToolResult.ok(
            data=SearchResults(
                query=query,
                date_range=date_range,
                total_results=total_results,
                results=results,
            )
        )

    def _create_error_result(
        self,
        query: str,
        date_range: str | None,
        error: Exception | str,
    ) -> ToolResult[SearchResults]:
        """Create standardized error response.

        Args:
            query: Original search query
            date_range: Date range used
            error: Exception or error message

        Returns:
            ToolResult with success=False
        """
        message = str(error) if isinstance(error, str) else f"{self.provider_name} Search failed: {error}"
        lowered_message = message.lower()
        is_expected_transient = any(pattern in lowered_message for pattern in _EXPECTED_TRANSIENT_ERROR_PATTERNS)
        if is_expected_transient:
            logger.warning(message)
        else:
            logger.error(message)
        return ToolResult.error(
            message=message,
            data=SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[],
            ),
        )

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> str:
        """Handle HTTP status errors with common patterns.

        Args:
            error: HTTP status error

        Returns:
            Human-readable error message
        """
        status = error.response.status_code
        if status == 401:
            return f"{self.provider_name} authentication failed: invalid API key"
        if status == 429:
            return f"{self.provider_name} rate limit exceeded"
        if status == 400:
            return f"{self.provider_name} bad request: check query format"
        if status >= 500:
            return f"{self.provider_name} server error: {status}"
        return f"{self.provider_name} HTTP error: {status}"

    def _parse_json_result_item(
        self,
        item: dict[str, Any],
        title_keys: tuple[str, ...] = ("title",),
        link_keys: tuple[str, ...] = ("url", "link"),
        snippet_keys: tuple[str, ...] = ("content", "description", "snippet"),
    ) -> SearchResultItem | None:
        """Parse a single result item from JSON with configurable key names.

        Args:
            item: JSON dict containing result data
            title_keys: Possible keys for title field
            link_keys: Possible keys for link/URL field
            snippet_keys: Possible keys for snippet/description field

        Returns:
            SearchResultItem or None if required fields missing
        """
        title = self._get_first_value(item, title_keys)
        link = self._get_first_value(item, link_keys)
        snippet = self._get_first_value(item, snippet_keys)

        if title and link:
            return SearchResultItem(title=title, link=link, snippet=snippet or "")
        return None

    @staticmethod
    def _get_first_value(data: dict[str, Any], keys: tuple[str, ...]) -> str:
        """Get first non-empty value from dict using multiple possible keys.

        Args:
            data: Dict to search in
            keys: Keys to try in order

        Returns:
            First non-empty string value found, or empty string
        """
        for key in keys:
            value = data.get(key, "")
            if value:
                return str(value).strip()
        return ""

    def _contains_chinese_text(self, result: SearchResultItem) -> bool:
        """Return True when a result includes Chinese characters in user-visible text."""
        searchable_text = f"{result.title} {result.snippet}"
        return bool(CHINESE_CHAR_RE.search(searchable_text))

    def _filter_english_results(self, results: list[SearchResultItem]) -> list[SearchResultItem]:
        """Remove results containing Chinese text to keep search output English-only."""
        filtered_results = [result for result in results if not self._contains_chinese_text(result)]
        removed_count = len(results) - len(filtered_results)
        if removed_count > 0:
            logger.info(f"{self.provider_name} removed {removed_count} Chinese-language result(s)")
        return filtered_results

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Execute search with semaphore-based concurrency control."""
        async with self._semaphore:
            return await self._do_search(query, date_range)

    async def _do_search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Internal search implementation with standardized error handling and retry.

        Retry discipline:
        - 429/502/503/504: Retry with exponential backoff (transient)
        - Connection/read timeouts: Retry once (transient network)
        - 401/403: Do NOT retry — rotate key at higher level, fail this attempt
        - 400: Do NOT retry, do NOT rotate — permanent client error
        - Other: Return error immediately

        Args:
            query: Search query string
            date_range: Optional date range filter

        Returns:
            ToolResult containing SearchResults
        """
        last_error: Exception | None = None
        for attempt in range(2):  # max 2 attempts (1 retry)
            try:
                client = await self._get_client()
                params = self._build_request_params(query, date_range)
                response = await self._execute_request(client, params)
                response.raise_for_status()

                results, total_results = self._parse_response(response)
                results = self._filter_english_results(results)
                total_results = len(results)
                return self._create_success_result(query, date_range, results, total_results)

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code

                # Permanent failure — do not retry or rotate
                if status in self.PERMANENT_FAIL_CODES:
                    logger.warning(f"{self.provider_name} permanent client error {status} — not retrying")
                    return self._create_error_result(query, date_range, self._handle_http_error(e))

                # Auth/policy failure — fail this attempt, key rotation handled by key pool above
                if status in self.ROTATE_NO_RETRY_CODES:
                    logger.warning(f"{self.provider_name} auth/policy error {status} — failing (key pool will rotate)")
                    return self._create_error_result(query, date_range, self._handle_http_error(e))

                # Transient — retry with backoff
                if attempt == 0 and status in self.RETRYABLE_STATUS_CODES:
                    retry_config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=5.0, jitter=True)
                    delay = calculate_delay(attempt + 1, retry_config)
                    logger.warning(f"{self.provider_name} search got {status}, retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    continue

                return self._create_error_result(query, date_range, self._handle_http_error(e))

            except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                last_error = e
                if attempt == 0:
                    retry_config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=5.0, jitter=True)
                    delay = calculate_delay(attempt + 1, retry_config)
                    logger.warning(f"{self.provider_name} search timeout, retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    continue
                return self._create_error_result(query, date_range, e)

            except Exception as e:
                return self._create_error_result(query, date_range, e)

        return self._create_error_result(query, date_range, last_error or Exception("Search failed after retry"))

    async def __aenter__(self) -> "SearchEngineBase":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - close client."""
        await self.close()
