"""Brave Search Engine

Brave Search API implementation with privacy-focused search results.
Requires a Brave Search API key from https://brave.com/search/api/

Uses APIKeyPool for production-grade multi-key management:
- FAILOVER strategy: primary key preferred, fallbacks only when exhausted
- TTL-based recovery: keys auto-recover after cooldown
- Redis coordination: distributed key health tracking across instances
- Wait-for-recovery: waits up to 120s for soonest-recovering key (MCP Rotator pattern)
- Per-request auth: X-Subscription-Token injected per-request, connection pool survives rotation
"""

import logging
import re
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.http_pool import HTTPClientConfig, HTTPClientPool, ManagedHTTPClient
from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    RotationStrategy,
    _text_has_quota_keywords,
)
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the API key should be rotated
_ROTATE_STATUS_CODES = {401, 402, 403, 429}


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
        max_results: int = 8,
    ):
        """Initialize Brave search engine.

        Args:
            api_key: Primary Brave API key
            fallback_api_keys: Optional list of fallback API keys (up to 2 fallbacks = 3 total)
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
            max_results: Number of results to return per search (default 8)
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

        self._max_results = max_results

        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        logger.info(f"Brave search initialized with {len(key_configs)} API key(s)")

    async def _get_client(self) -> ManagedHTTPClient:
        """Get a pooled HTTP client for Brave Search.

        Auth header (X-Subscription-Token) is NOT baked in here — it is injected
        as a per-request header in search() so the connection pool is reused
        across all key rotations without needing to close and recreate the client.
        """
        config = HTTPClientConfig(
            headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
            timeout=self.timeout,
            connect_timeout=10.0,
            read_timeout=self.timeout,
        )
        return await HTTPClientPool.get_client(
            name="search-bravesearchengine",
            config=config,
            follow_redirects=True,
        )

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
            "count": self._max_results,
            "text_decorations": False,
            "search_lang": "en",
        }

        if mapped := self._map_date_range(date_range):
            params["freshness"] = mapped

        return params

    async def _execute_request(self, client: ManagedHTTPClient, params: dict[str, Any]) -> httpx.Response:
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
        # Check retry limit to prevent stack overflow
        if _attempt >= self._max_retries:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Brave API keys exhausted after {_attempt} attempts"
            )

        # Sanitize query: collapse newlines/control chars, strip, cap length
        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return self._create_error_result(query, date_range, "Brave bad request: empty search query")
        if len(query) > 500:
            logger.warning(f"Brave query truncated from {len(query)} to 500 chars")
            query = query[:500]

        # Wait up to 120s for a key to become available (MCP Rotator pattern).
        # Falls through to fallback provider when cooldowns exceed the budget.
        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Brave API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)

            # Per-request auth injection: key header overrides the pool-level client
            # so the connection pool is reused across all key rotations.
            response = await client.get(
                self.base_url,
                params=params,
                headers={"X-Subscription-Token": key},
            )

            # Check for quota/auth errors
            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200] if hasattr(response, "text") else ""
                logger.warning(
                    "Brave key error (HTTP %d%s), rotating", response.status_code, f": {body}" if body else ""
                )
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()

            # Dual quota detection: scan successful response body
            results, total_results = self._parse_response(response)
            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                logger.warning("Brave quota keyword detected in response body, rotating key")
                await self._key_pool.handle_error(key, body_text=response_text)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            self._key_pool.record_success(key)
            return self._create_success_result(query, date_range, results, total_results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return self._create_error_result(query, date_range, f"Brave search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
