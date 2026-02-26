"""Serper.dev Google Search Engine

Google Search API via Serper.dev — fast, structured JSON results
from Google's index. Requires an API key from https://serper.dev/
Free tier: 2,500 queries/month.

Uses APIKeyPool for production-grade multi-key management:
- FAILOVER strategy: primary key preferred, fallbacks only when exhausted
- TTL-based recovery: keys auto-recover after 1 hour (Serper quota reset)
- Redis coordination: distributed key health tracking across instances
- Prometheus metrics: observability for key exhaustion and rotation
"""

import logging
import re
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

# HTTP status codes that indicate the API key should be rotated
_ROTATE_STATUS_CODES = {400, 401, 402, 403, 429}  # 400: Serper returns this for "Not enough credits"


@SearchProviderRegistry.register("serper")
class SerperSearchEngine(SearchEngineBase):
    """Serper.dev Google Search API with multi-key fallback.

    Uses Serper's POST API which returns structured Google SERP data:
    - Organic results with title, link, snippet
    - Knowledge graph entries
    - Answer boxes
    - People also ask

    When multiple API keys are configured, automatically rotates to the
    next key on 401/402/403/429 errors. Exhausted keys are tracked and
    skipped on future requests.
    """

    provider_name = "Serper"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float | None = None,
    ):
        """Initialize Serper search engine.

        Args:
            api_key: Primary Serper.dev API key
            fallback_api_keys: Optional list of fallback API keys
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)

        # Build key configs (primary + fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with FAILOVER strategy
        self._key_pool = APIKeyPool(
            provider="serper",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )

        # Set max retries to number of keys to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self.base_url = "https://google.serper.dev/search"
        logger.info(f"Serper search initialized with {len(key_configs)} API key(s)")

    @property
    async def api_key(self) -> str | None:
        """Get the currently active API key from pool."""
        return await self._key_pool.get_healthy_key()

    async def _get_headers(self) -> dict[str, str]:
        """Get Serper API headers with active key authentication."""
        key = await self.api_key
        if not key:
            raise RuntimeError("All Serper API keys exhausted")

        return {
            "X-API-Key": key,
            "Content-Type": "application/json",
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
        """Google tbs parameter mapping via Serper."""
        return {
            "past_hour": "qdr:h",
            "past_day": "qdr:d",
            "past_week": "qdr:w",
            "past_month": "qdr:m",
            "past_year": "qdr:y",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Serper API request body (sent as JSON POST)."""
        params: dict[str, Any] = {
            "q": query,
            "gl": "us",
            "hl": "en",
            "num": 20,
        }

        if mapped := self._map_date_range(date_range):
            params["tbs"] = mapped

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to Serper API."""
        return await client.post(self.base_url, json=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Serper API JSON response.

        Serper returns:
        - organic: list of {title, link, snippet, position, ...}
        - knowledgeGraph: optional dict
        - answerBox: optional dict
        """
        data = response.json()
        organic = data.get("organic", [])

        results = [
            result
            for item in organic
            if (result := self._parse_json_result_item(item, link_keys=("link",), snippet_keys=("snippet",)))
        ]

        total_results = len(results)
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
                query, date_range, f"All {len(self._key_pool.keys)} Serper API keys exhausted after {_attempt} attempts"
            )

        # Sanitize query: collapse newlines/control chars (HTTP 400 from Serper), strip, cap length
        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return self._create_error_result(query, date_range, "Serper bad request: empty search query")
        if len(query) > 500:
            logger.warning(f"Serper query truncated from {len(query)} to 500 chars")
            query = query[:500]

        # Get healthy key from pool
        key = await self.api_key
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Serper API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)
            response = await self._execute_request(client, params)

            # Check for quota/auth errors (400 = "Not enough credits" from Serper)
            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200] if response.status_code == 400 else ""
                logger.warning("Serper key exhausted (HTTP %d%s), rotating", response.status_code, f": {body}" if body else "")
                # Mark key exhausted with 1-hour TTL (Serper resets hourly)
                await self._key_pool.mark_exhausted(key, ttl_seconds=3600)

                # Close cached client so next retry creates one with the new key
                await self.close()

                # Retry with next key
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()
            results, total_results = self._parse_response(response)
            return self._create_success_result(query, date_range, results, total_results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                await self._key_pool.mark_exhausted(key, ttl_seconds=3600)
                await self.close()
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            return self._create_error_result(query, date_range, f"Serper search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
