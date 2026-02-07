"""Serper.dev Google Search Engine

Google Search API via Serper.dev — fast, structured JSON results
from Google's index. Requires an API key from https://serper.dev/
Free tier: 2,500 queries/month.

Supports multiple API keys with automatic fallback: if the active key
hits quota/billing limits (HTTP 429 or 402), the engine rotates to
the next configured key transparently.
"""

import logging
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# HTTP status codes that indicate quota/billing exhaustion
_QUOTA_STATUS_CODES = {402, 429}


@SearchProviderRegistry.register("serper")
class SerperSearchEngine(SearchEngineBase):
    """Serper.dev Google Search API with multi-key fallback.

    Uses Serper's POST API which returns structured Google SERP data:
    - Organic results with title, link, snippet
    - Knowledge graph entries
    - Answer boxes
    - People also ask

    When multiple API keys are configured, automatically rotates to the
    next key on 429 (rate limit) or 402 (payment required) errors.
    """

    provider_name = "Serper"
    engine_type = SearchEngineType.API

    def __init__(
        self,
        api_key: str,
        fallback_api_keys: list[str] | None = None,
        timeout: float | None = None,
    ):
        """Initialize Serper search engine.

        Args:
            api_key: Primary Serper.dev API key
            fallback_api_keys: Optional list of fallback API keys
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        self._api_keys = [api_key]
        if fallback_api_keys:
            self._api_keys.extend(fallback_api_keys)
        self._active_key_index = 0
        self.base_url = "https://google.serper.dev/search"

    @property
    def api_key(self) -> str:
        """Get the currently active API key."""
        return self._api_keys[self._active_key_index]

    def _rotate_key(self) -> bool:
        """Rotate to the next available API key.

        Returns:
            True if rotated successfully, False if all keys exhausted.
        """
        next_index = self._active_key_index + 1
        if next_index < len(self._api_keys):
            self._active_key_index = next_index
            logger.warning(f"Serper API key rotated to key #{next_index + 1} of {len(self._api_keys)}")
            # Reset the HTTP client so new headers take effect
            self._client = None
            return True
        return False

    def _get_headers(self) -> dict[str, str]:
        """Get Serper API headers with active key authentication."""
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

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
            "autocorrect": True,
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

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Execute search with automatic API key rotation on quota errors.

        Overrides the base search() to add multi-key fallback logic.
        On 429/402 responses, rotates to the next configured API key
        and retries the request transparently.

        Args:
            query: Search query string
            date_range: Optional date range filter

        Returns:
            ToolResult containing SearchResults
        """
        while True:
            try:
                client = await self._get_client()
                params = self._build_request_params(query, date_range)
                response = await self._execute_request(client, params)

                # Check for quota/billing errors — rotate key and retry
                if response.status_code in _QUOTA_STATUS_CODES:
                    key_num = self._active_key_index + 1
                    logger.warning(
                        f"Serper key #{key_num} quota exceeded (HTTP {response.status_code})"
                    )
                    if self._rotate_key():
                        continue
                    # All keys exhausted
                    return self._create_error_result(
                        query,
                        date_range,
                        f"All {len(self._api_keys)} Serper API keys exhausted (quota/billing limit)",
                    )

                response.raise_for_status()
                results, total_results = self._parse_response(response)
                return self._create_success_result(query, date_range, results, total_results)

            except httpx.HTTPStatusError as e:
                # Catch quota errors raised by raise_for_status (shouldn't happen
                # since we check above, but be defensive)
                if e.response.status_code in _QUOTA_STATUS_CODES and self._rotate_key():
                    continue
                return self._create_error_result(query, date_range, self._handle_http_error(e))

            except Exception as e:
                return self._create_error_result(query, date_range, e)
