"""Tavily Search Engine

Tavily AI-powered Search API implementation.
Requires a Tavily API key from https://tavily.com/

Uses APIKeyPool for production-grade multi-key management:
- FAILOVER strategy: primary key preferred, fallbacks only when exhausted
- TTL-based recovery: keys auto-recover after 24 hours (Tavily quota reset)
- Redis coordination: distributed key health tracking across instances
- Prometheus metrics: observability for key exhaustion and rotation
- Wait-for-recovery: waits up to 120s for soonest-recovering key (MCP Rotator pattern)
- Per-request auth: API key injected per-request, connection pool survives rotation
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
    _text_has_quota_keywords,
)
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the API key should be rotated
_ROTATE_STATUS_CODES = {401, 402, 403, 429, 432}


@SearchProviderRegistry.register("tavily")
class TavilySearchEngine(SearchEngineBase):
    """Tavily AI-powered Search API with multi-key fallback.

    Uses Tavily's Search API which provides:
    - AI-optimized search results
    - Relevance ranking powered by AI
    - Real-time web search
    - Clean, structured results

    When multiple API keys are configured, automatically rotates to the
    next key on 401/402/403/429 errors or billing-related JSON errors.
    Exhausted keys are tracked and skipped on future requests.
    """

    provider_name = "Tavily"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float | None = None,
        max_results: int = 8,
        search_depth: str = "basic",
    ):
        """Initialize Tavily search engine.

        Args:
            api_key: Primary Tavily API key
            fallback_api_keys: Optional list of fallback API keys (up to 8 fallbacks = 9 total)
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
            max_results: Number of results to return per search (default 8)
            search_depth: Tavily search depth — "basic" (1 credit) or "advanced" (2 credits)
        """
        super().__init__(timeout=timeout)

        # Build key configs (primary + up to 8 fallbacks)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Initialize key pool with FAILOVER strategy
        self._key_pool = APIKeyPool(
            provider="tavily",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )

        # Set max retries to prevent unbounded recursion
        self._max_retries = len(key_configs)

        self._max_results = max_results
        self._search_depth = search_depth

        self.base_url = "https://api.tavily.com/search"
        logger.info(f"Tavily search initialized with {len(key_configs)} API key(s)")

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Tavily-native time_range mapping."""
        return {
            "past_day": "day",
            "past_week": "week",
            "past_month": "month",
            "past_year": "year",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Tavily API request payload (without API key).

        The API key is injected per-request in search() so the connection pool
        survives key rotation without needing to close and recreate the client.
        """
        params = {
            "query": query,
            "search_depth": self._search_depth,
            "include_answer": True,
            "include_images": False,
            "include_raw_content": False,
            "max_results": self._max_results,
        }
        if time_range := self._map_date_range(date_range):
            params["time_range"] = time_range
        elif date_range == "past_hour":
            # Tavily does not expose hour-level filtering, so preserve the older
            # "recent" hint instead of silently dropping the user's time intent.
            params["query"] = f"{query} recent"
        return params

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to Tavily API."""
        return await client.post(self.base_url, json=params)

    def _parse_response_data(self, data: dict[str, Any]) -> tuple[list[SearchResultItem], int, str]:
        """Parse Tavily API JSON response data.

        Returns a 3-tuple: (results, total_results, answer).
        `answer` is Tavily's AI-synthesized summary (empty string if not present).
        Snippet size increased to 1500 chars — since we pay per query, not per byte,
        larger snippets give the LLM richer context at no additional credit cost.
        """
        answer: str = data.get("answer") or ""

        results: list[SearchResultItem] = []
        for item in data.get("results", []):
            title = item.get("title", "")
            link = item.get("url", "")
            snippet = item.get("content", "")

            if len(snippet) > 1500:
                snippet = snippet[:1497] + "..."

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results, len(results), answer

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Tavily API HTTP response to satisfy SearchEngineBase contract."""
        data = response.json()
        results, total_results, _answer = self._parse_response_data(data)
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
        - HTTP 432 (Tavily-specific billing error)
        - HTTP 200 with billing-related error in JSON body

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
                query,
                date_range,
                f"All {len(self._key_pool.keys)} Tavily API keys exhausted after {_attempt} attempts",
            )

        # Sanitize query: collapse newlines/control chars, strip, cap length
        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return self._create_error_result(query, date_range, "Tavily bad request: empty search query")
        if len(query) > 500:
            logger.warning(f"Tavily query truncated from {len(query)} to 500 chars")
            query = query[:500]

        # Wait up to 120s for a key to become available (MCP Rotator pattern).
        # Falls through to fallback provider when cooldowns exceed the budget.
        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Tavily API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)

            # Per-request auth injection: API key in JSON body so the connection
            # pool is reused across all key rotations without recreating the client.
            params["api_key"] = key
            response = await self._execute_request(client, params)

            # Check for quota/auth errors (HTTP status codes)
            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200] if hasattr(response, "text") else ""
                logger.warning(
                    "Tavily key error (HTTP %d%s), rotating", response.status_code, f": {body}" if body else ""
                )
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()

            # Parse response
            data = response.json()

            # Dual quota detection: check JSON body for quota/billing/auth errors
            if "error" in data:
                error_msg = str(data["error"])

                if _text_has_quota_keywords(error_msg):
                    logger.warning("Tavily quota keyword detected in response body, rotating key")
                    await self._key_pool.handle_error(key, body_text=error_msg)
                    return await self.search(query, date_range, _attempt=_attempt + 1)

                # Check for auth errors (permanent invalidity)
                error_lower = error_msg.lower()
                if "invalid" in error_lower or "auth" in error_lower:
                    logger.warning("Tavily auth error in response body, rotating key")
                    await self._key_pool.handle_error(key, status_code=401, body_text=error_msg)
                    return await self.search(query, date_range, _attempt=_attempt + 1)

            self._key_pool.record_success(key)
            results, total_results, answer = self._parse_response_data(data)
            result = self._create_success_result(query, date_range, results, total_results)
            if answer:
                result.message = f"[TAVILY ANSWER] {answer}\n\n" + (result.message or "")
            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return self._create_error_result(query, date_range, f"Tavily search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
