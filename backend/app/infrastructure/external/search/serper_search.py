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
    ErrorType,
    RotationStrategy,
    _text_has_quota_keywords,
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
        quota_cooldown_seconds: int = 1800,
    ):
        """Initialize Serper search engine.

        Args:
            api_key: Primary Serper.dev API key
            fallback_api_keys: Optional list of fallback API keys
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
            quota_cooldown_seconds: Cooldown after quota exhaustion (default 30min).
                Configurable via SERPER_QUOTA_COOLDOWN_SECONDS env var.
        """
        super().__init__(timeout=timeout)

        # Build key configs (primary + fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with FAILOVER strategy
        # Cooldown configurable via env; default 30min (was 4h, too aggressive)
        self._key_pool = APIKeyPool(
            provider="serper",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
            cooldown_overrides={ErrorType.QUOTA_EXHAUSTED: quota_cooldown_seconds},
        )

        # Set max retries to number of keys to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self.base_url = "https://google.serper.dev/search"
        logger.info(f"Serper search initialized with {len(key_configs)} API key(s)")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client.

        Auth header (X-API-Key) is NOT baked in here — it is injected as a
        per-request header in search() so the connection pool is reused across
        all key rotations without needing to close and recreate the client.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Content-Type": "application/json", "Accept": "application/json"},
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
        """Satisfy abstract base contract. Not called — search() drives the full flow."""
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

        # Wait up to 120s for a key to become available (MCP Rotator pattern).
        # Falls through to fallback provider when cooldowns exceed the budget.
        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Serper API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)

            # Per-request auth injection: key header overrides the pool-level client
            # so the connection pool is reused across all key rotations.
            response = await client.post(
                self.base_url,
                json=params,
                headers={"X-API-Key": key},
            )

            # Check for quota/auth errors (400 = "Not enough credits" from Serper)
            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                logger.warning(
                    "Serper key error (HTTP %d%s), rotating", response.status_code, f": {body}" if body else ""
                )
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()

            # Dual quota detection: scan successful response body
            results, total_results = self._parse_response(response)
            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                logger.warning("Serper quota keyword detected in response body, rotating key")
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
            return self._create_error_result(query, date_range, f"Serper search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
