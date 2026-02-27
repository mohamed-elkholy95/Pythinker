"""Exa AI Neural Search Engine

Semantic/neural search via Exa AI — finds content by meaning, not just keywords.
Supports neural, keyword, auto, and deep search types.
API docs: https://exa.ai/docs/reference/search

Uses APIKeyPool for production-grade multi-key management:
- FAILOVER strategy: primary key preferred, fallbacks only when exhausted
- TTL-based recovery: keys auto-recover after cooldown
- Redis coordination: distributed key health tracking across instances
- Dual quota detection: HTTP status codes + response body keyword scan
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
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
_ROTATE_STATUS_CODES = {400, 401, 403, 429}


def _date_range_to_iso(date_range: str | None) -> str | None:
    """Convert standard date range to ISO 8601 date string for Exa's startPublishedDate."""
    if not date_range or date_range == "all":
        return None

    now = datetime.now(tz=UTC)
    offsets: dict[str, timedelta] = {
        "past_hour": timedelta(hours=1),
        "past_day": timedelta(days=1),
        "past_week": timedelta(weeks=1),
        "past_month": timedelta(days=30),
        "past_year": timedelta(days=365),
    }

    delta = offsets.get(date_range)
    if delta is None:
        return None

    return (now - delta).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@SearchProviderRegistry.register("exa")
class ExaSearchEngine(SearchEngineBase):
    """Exa AI Neural Search with multi-key fallback.

    Uses Exa's POST /search API which returns semantically relevant results:
    - Neural search finds content by meaning (embeddings-based)
    - Auto mode intelligently combines neural and keyword search
    - Inline content extraction via text=true in request body

    When multiple API keys are configured, automatically rotates to the
    next key on 401/403/429 errors. Exhausted keys are tracked and
    skipped on future requests.
    """

    provider_name = "Exa"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float | None = None,
    ):
        super().__init__(timeout=timeout)

        # Build key configs (primary + fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with FAILOVER strategy
        self._key_pool = APIKeyPool(
            provider="exa",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )

        # Set max retries to number of keys to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self.base_url = "https://api.exa.ai/search"
        logger.info(f"Exa search initialized with {len(key_configs)} API key(s)")

    @property
    async def api_key(self) -> str | None:
        """Get the currently active API key from pool."""
        return await self._key_pool.get_healthy_key()

    async def _get_headers(self) -> dict[str, str]:
        """Get Exa API headers with active key authentication."""
        key = await self.api_key
        if not key:
            raise RuntimeError("All Exa API keys exhausted")

        return {
            "x-api-key": key,
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
        """Exa uses ISO date strings — mapping handled in _build_request_params."""
        return {}

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Exa API request body (sent as JSON POST)."""
        params: dict[str, Any] = {
            "query": query,
            "type": "auto",
            "numResults": 20,
            "text": True,
        }

        start_date = _date_range_to_iso(date_range)
        if start_date:
            params["startPublishedDate"] = start_date

        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to Exa API."""
        return await client.post(self.base_url, json=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Exa API JSON response.

        Exa returns:
        - results: list of {title, url, text, publishedDate, author, id, ...}
        """
        data = response.json()
        raw_results = data.get("results", [])

        results = [
            result
            for item in raw_results
            if (result := self._parse_exa_result(item))
        ]

        return results, len(results)

    @staticmethod
    def _parse_exa_result(item: dict[str, Any]) -> SearchResultItem | None:
        """Parse a single Exa result into SearchResultItem."""
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()

        if not title or not url:
            return None

        # Use text content as snippet, truncated to 300 chars
        text = item.get("text", "")
        snippet = text[:300].strip() if text else ""

        return SearchResultItem(title=title, link=url, snippet=snippet)

    async def search(
        self,
        query: str,
        date_range: str | None = None,
        _attempt: int = 0,
    ) -> ToolResult[SearchResults]:
        """Execute search with automatic API key rotation via pool.

        Rotation triggers:
        - HTTP 400 (bad request / quota errors)
        - HTTP 401 (unauthorized / invalid key)
        - HTTP 403 (forbidden / rate limit)
        - HTTP 429 (rate limit)

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
                query, date_range, f"All {len(self._key_pool.keys)} Exa API keys exhausted after {_attempt} attempts"
            )

        # Sanitize query: collapse newlines/control chars, strip, cap length
        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return self._create_error_result(query, date_range, "Exa bad request: empty search query")
        if len(query) > 500:
            logger.warning(f"Exa query truncated from {len(query)} to 500 chars")
            query = query[:500]

        # Get healthy key from pool
        key = await self.api_key
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Exa API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)
            response = await self._execute_request(client, params)

            # Check for quota/auth errors
            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                logger.warning("Exa key error (HTTP %d%s), rotating", response.status_code, f": {body}" if body else "")
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                await self.close()
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()

            # Dual quota detection: scan successful response body
            results, total_results = self._parse_response(response)
            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                logger.warning("Exa quota keyword detected in response body, rotating key")
                await self._key_pool.handle_error(key, body_text=response_text)
                await self.close()
                return await self.search(query, date_range, _attempt=_attempt + 1)

            self._key_pool.record_success(key)
            return self._create_success_result(query, date_range, results, total_results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                await self.close()
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return self._create_error_result(query, date_range, f"Exa search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
