"""Brave Search Engine

Brave Search API implementation with privacy-focused search results.
Requires a Brave Search API key from https://brave.com/search/api/
"""

import logging
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    RotationStrategy,
)
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)


@SearchProviderRegistry.register("brave")
class BraveSearchEngine(SearchEngineBase):
    """Brave Search API implementation.

    Uses Brave's official Search API which provides:
    - Privacy-focused search results
    - No tracking or profiling
    - Independent search index
    """

    provider_name = "Brave"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float | None = None,
    ):
        """Initialize Brave search engine.

        Args:
            api_key: Primary Brave API key
            fallback_api_keys: Optional list of fallback API keys (up to 2 fallbacks = 3 total)
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)

        # Build key configs (primary + up to 2 fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with FAILOVER strategy
        self._key_pool = APIKeyPool(
            provider="brave",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )

        # Set max retries to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        logger.info(f"Brave search initialized with {len(key_configs)} API key(s)")

    @property
    async def api_key(self) -> str | None:
        """Get the currently active API key from pool."""
        return await self._key_pool.get_healthy_key()

    async def _get_headers(self) -> dict[str, str]:
        """Get Brave API headers with authentication."""
        key = await self.api_key
        if not key:
            raise RuntimeError("All Brave API keys exhausted")

        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling.

        Overrides base class to support async header generation.
        """
        if self._client is None or self._client.is_closed:
            headers = await self._get_headers()
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Brave API freshness parameter mapping."""
        return {
            "past_hour": "ph",
            "past_day": "pd",
            "past_week": "pw",
            "past_month": "pm",
            "past_year": "py",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Brave API request parameters."""
        params: dict[str, Any] = {
            "q": query,
            "count": 20,
            "text_decorations": False,
            "search_lang": "en",
        }

        if mapped := self._map_date_range(date_range):
            params["freshness"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request to Brave API."""
        return await client.get(self.base_url, params=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Brave API JSON response."""
        data = response.json()
        web_data = data.get("web", {})
        web_results = web_data.get("results", [])

        results = [
            result
            for item in web_results
            if (result := self._parse_json_result_item(item, link_keys=("url",), snippet_keys=("description",)))
        ]

        total_results = web_data.get("total_count", len(results))
        return results, total_results

    async def search(
        self,
        query: str,
        date_range: str | None = None,
        _attempt: int = 0,
    ) -> ToolResult[SearchResults]:
        """Execute search with automatic API key rotation via pool.

        Rotation triggers:
        - HTTP 401 (unauthorized / invalid key)
        - HTTP 402 (payment required)
        - HTTP 403 (forbidden / suspended)
        - HTTP 429 (rate limit)

        APIKeyPool handles exhausted key tracking with TTL-based recovery.

        Args:
            query: Search query string
            date_range: Optional date range filter
            _attempt: Internal retry counter to prevent unbounded recursion

        Returns:
            ToolResult containing SearchResults
        """
        # Status codes that trigger key rotation
        rotate_status_codes = {401, 402, 403, 429}

        # Check retry limit to prevent stack overflow
        if _attempt >= self._max_retries:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Brave API keys exhausted after {_attempt} attempts"
            )

        # Get healthy key from pool
        key = await self.api_key
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Brave API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)
            response = await self._execute_request(client, params)

            # Check for quota/auth errors
            if response.status_code in rotate_status_codes:
                # Mark key exhausted with 24-hour TTL (Brave has generous monthly quotas but daily TTL is safe)
                await self._key_pool.mark_exhausted(key, ttl_seconds=86400)

                # Close client so it gets recreated with new key on retry
                await self.close()

                # Retry with next key
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()
            results, total_results = self._parse_response(response)
            return self._create_success_result(query, date_range, results, total_results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in rotate_status_codes:
                await self._key_pool.mark_exhausted(key, ttl_seconds=86400)
                # Close client so it gets recreated with new key on retry
                await self.close()
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            return self._create_error_result(query, date_range, f"Brave search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
