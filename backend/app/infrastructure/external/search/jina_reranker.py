"""Jina Reranker integration.

Calls Jina's /v1/rerank endpoint to reorder search results by relevance.
Designed as an optional post-search stage with fail-open behavior.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    RotationStrategy,
    _text_has_quota_keywords,
)

logger = logging.getLogger(__name__)

_ROTATE_STATUS_CODES = {400, 401, 402, 403, 429}


class JinaReranker:
    """Rerank search results with Jina API key rotation support."""

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        timeout: float = 20.0,
        model: str = "jina-reranker-v2-base-multilingual",
    ):
        self.timeout = timeout
        self.model = model
        self.base_url = "https://api.jina.ai/v1/rerank"
        self._client: httpx.AsyncClient | None = None

        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]
        self._key_pool = APIKeyPool(
            provider="jina-reranker",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )
        self._max_retries = len(key_configs)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    @staticmethod
    def _build_documents(items: list[SearchResultItem]) -> list[str]:
        documents: list[str] = []
        for item in items:
            combined = f"{item.title}\n{item.snippet}".strip()
            documents.append(combined or item.title)
        return documents

    @staticmethod
    def _apply_ranked_order(
        original_window: list[SearchResultItem],
        ranking_rows: list[dict],
    ) -> list[SearchResultItem]:
        ranked_indices: list[int] = []
        seen: set[int] = set()
        for row in ranking_rows:
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            if isinstance(index, int) and 0 <= index < len(original_window) and index not in seen:
                ranked_indices.append(index)
                seen.add(index)

        if not ranked_indices:
            return list(original_window)

        ordered = [original_window[idx] for idx in ranked_indices]
        ordered.extend(item for idx, item in enumerate(original_window) if idx not in seen)
        return ordered

    async def rerank(
        self,
        query: str,
        results: list[SearchResultItem],
        top_n: int = 8,
        _attempt: int = 0,
    ) -> list[SearchResultItem]:
        """Return a reranked list, or original order if reranking fails."""
        if len(results) < 2:
            return results
        if _attempt >= self._max_retries:
            return results

        rerank_window_size = max(2, min(top_n, len(results)))
        head = results[:rerank_window_size]
        tail = results[rerank_window_size:]

        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if not query:
            return results

        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=60.0)
        if not key:
            return results

        payload = {
            "model": self.model,
            "query": query,
            "documents": self._build_documents(head),
            "top_n": rerank_window_size,
            "return_documents": False,
        }

        try:
            client = await self._get_client()
            response = await client.post(
                self.base_url,
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            )

            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.rerank(query, results, top_n=top_n, _attempt=_attempt + 1)

            response.raise_for_status()
            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                await self._key_pool.handle_error(key, body_text=response_text)
                return await self.rerank(query, results, top_n=top_n, _attempt=_attempt + 1)

            data = response.json()
            ranking_rows = data.get("results", []) if isinstance(data, dict) else []
            if not isinstance(ranking_rows, list):
                ranking_rows = []

            self._key_pool.record_success(key)
            reordered_head = self._apply_ranked_order(head, ranking_rows)
            return reordered_head + tail

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.rerank(query, results, top_n=top_n, _attempt=_attempt + 1)
            logger.warning("Jina rerank HTTP error, preserving original order: %s", e)
            return results

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            logger.warning("Jina rerank timed out, preserving original order")
            return results

        except Exception as e:
            logger.warning("Jina rerank failed, preserving original order: %s", e)
            return results
