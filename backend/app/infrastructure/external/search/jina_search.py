"""Jina Search Engine

Jina Search Foundation web search via https://s.jina.ai/.
Requires a Jina API key from https://jina.ai/.

Uses APIKeyPool for production-grade multi-key management:
- FAILOVER strategy: primary key preferred, fallbacks only when exhausted
- TTL-based recovery: keys auto-recover after cooldown
- Redis coordination: distributed key health tracking across instances
- Per-request auth: Authorization header injected per-request
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

_ROTATE_STATUS_CODES = {401, 402, 403, 429}


@SearchProviderRegistry.register("jina")
class JinaSearchEngine(SearchEngineBase):
    """Jina Search API provider with multi-key fallback support."""

    provider_name = "Jina"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float | None = None,
    ):
        super().__init__(timeout=timeout)

        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]
        self._key_pool = APIKeyPool(
            provider="jina",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )
        self._max_retries = len(key_configs)
        self.base_url = "https://s.jina.ai/"
        logger.info("Jina search initialized with %d API key(s)", len(key_configs))

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client.

        Auth header is not baked into the shared client. It is injected
        per-request so key rotation can reuse the same connection pool.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Jina does not expose native date filters; use query hints."""
        return {
            "past_hour": "last hour",
            "past_day": "today",
            "past_week": "this week",
            "past_month": "this month",
            "past_year": "this year",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        actual_query = query
        if date_hint := self._map_date_range(date_range):
            actual_query = f"{query} {date_hint}"
        return {"q": actual_query}

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        return await client.post(self.base_url, json=params)

    @staticmethod
    def _parse_response_data(data: dict[str, Any]) -> tuple[list[SearchResultItem], int]:
        raw_items = data.get("data", [])
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("results", [])
        if not isinstance(raw_items, list):
            raw_items = []

        results: list[SearchResultItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            link = str(item.get("url", "")).strip()
            snippet = str(item.get("content") or item.get("description") or "").strip()
            if len(snippet) > 500:
                snippet = snippet[:497] + "..."
            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results, len(results)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        data = response.json()
        if not isinstance(data, dict):
            return [], 0
        return self._parse_response_data(data)

    async def search(
        self,
        query: str,
        date_range: str | None = None,
        _attempt: int = 0,
    ) -> ToolResult[SearchResults]:
        """Execute Jina search with API key rotation."""
        if _attempt >= self._max_retries:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Jina API keys exhausted after {_attempt} attempts"
            )

        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return self._create_error_result(query, date_range, "Jina bad request: empty search query")
        if len(query) > 500:
            logger.warning("Jina query truncated from %d to 500 chars", len(query))
            query = query[:500]

        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return self._create_error_result(
                query, date_range, f"All {len(self._key_pool.keys)} Jina API keys exhausted"
            )

        try:
            client = await self._get_client()
            params = self._build_request_params(query, date_range)
            response = await client.post(
                self.base_url,
                json=params,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                logger.warning(
                    "Jina key error (HTTP %d%s), rotating", response.status_code, f": {body}" if body else ""
                )
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            response.raise_for_status()

            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                logger.warning("Jina quota keyword detected in response body, rotating key")
                await self._key_pool.handle_error(key, body_text=response_text)
                return await self.search(query, date_range, _attempt=_attempt + 1)

            data = response.json()
            if isinstance(data, dict):
                error_msg = str(data.get("error") or data.get("message") or "").strip()
                if error_msg and _text_has_quota_keywords(error_msg):
                    await self._key_pool.handle_error(key, body_text=error_msg)
                    return await self.search(query, date_range, _attempt=_attempt + 1)
                if error_msg and "unauthorized" in error_msg.lower():
                    await self._key_pool.handle_error(key, status_code=401, body_text=error_msg)
                    return await self.search(query, date_range, _attempt=_attempt + 1)

            self._key_pool.record_success(key)
            results, total_results = self._parse_response_data(data if isinstance(data, dict) else {})
            return self._create_success_result(query, date_range, results, total_results)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.search(query, date_range, _attempt=_attempt + 1)
            return self._create_error_result(query, date_range, self._handle_http_error(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return self._create_error_result(query, date_range, f"Jina search timed out after {self.timeout}s")

        except Exception as e:
            return self._create_error_result(query, date_range, e)
