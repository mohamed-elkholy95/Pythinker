"""Serper.dev Google Search Engine

Google Search API via Serper.dev — fast, structured JSON results
from Google's index. Requires an API key from https://serper.dev/
Free tier: 2,500 queries/month.

Supports multiple API keys with automatic fallback: if the active key
hits quota/billing limits (HTTP 401, 402, 403, 429), the engine rotates
to the next configured key instantly. Exhausted keys are remembered for
the lifetime of the process so subsequent searches skip them without
making a network round-trip.
"""

import logging
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import SearchProviderRegistry

logger = logging.getLogger(__name__)

# HTTP status codes that indicate the API key should be rotated
_ROTATE_STATUS_CODES = {401, 402, 403, 429}


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
        timeout: float | None = None,
    ):
        """Initialize Serper search engine.

        Args:
            api_key: Primary Serper.dev API key
            fallback_api_keys: Optional list of fallback API keys
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)
        self._api_keys = [k for k in all_keys if k and k.strip()]
        if not self._api_keys:
            self._api_keys = [api_key]
        self._active_key_index = 0
        self._exhausted_keys: set[int] = set()  # Indices of keys that hit billing limits
        self.base_url = "https://google.serper.dev/search"
        logger.info(f"Serper search initialized with {len(self._api_keys)} API key(s)")

    @property
    def api_key(self) -> str:
        """Get the currently active API key."""
        return self._api_keys[self._active_key_index]

    def _rotate_key(self, reason: str = "") -> bool:
        """Rotate to the next available non-exhausted API key.

        Marks the current key as exhausted and finds the next usable key.

        Args:
            reason: Human-readable reason for rotation (for logging)

        Returns:
            True if rotated successfully, False if all keys exhausted.
        """
        self._exhausted_keys.add(self._active_key_index)
        # Find next non-exhausted key
        for i in range(len(self._api_keys)):
            if i not in self._exhausted_keys:
                self._active_key_index = i
                # Reset the HTTP client so new headers take effect
                self._client = None
                detail = f" ({reason})" if reason else ""
                logger.warning(
                    f"Serper API key rotated to key #{i + 1} of {len(self._api_keys)}{detail} "
                    f"— {len(self._exhausted_keys)}/{len(self._api_keys)} keys exhausted"
                )
                return True
        logger.error(f"All {len(self._api_keys)} Serper API keys exhausted")
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
        """Execute search with automatic API key rotation on billing/quota errors.

        Rotation triggers:
        - HTTP 401 (unauthorized / invalid key)
        - HTTP 402 (payment required)
        - HTTP 403 (forbidden / suspended)
        - HTTP 429 (rate limit)

        Exhausted keys are tracked and skipped on subsequent calls.

        Args:
            query: Search query string
            date_range: Optional date range filter

        Returns:
            ToolResult containing SearchResults
        """
        # Fast path: if current key is already exhausted, rotate before even trying
        if self._active_key_index in self._exhausted_keys and not self._rotate_key("current key already exhausted"):
            return self._create_error_result(
                query,
                date_range,
                f"All {len(self._api_keys)} Serper API keys exhausted (quota/billing limit)",
            )

        while True:
            try:
                client = await self._get_client()
                params = self._build_request_params(query, date_range)
                response = await self._execute_request(client, params)

                # Check HTTP status for quota/billing/auth errors
                if response.status_code in _ROTATE_STATUS_CODES:
                    key_num = self._active_key_index + 1
                    logger.warning(f"Serper key #{key_num} failed (HTTP {response.status_code})")
                    if self._rotate_key(f"HTTP {response.status_code}"):
                        continue
                    return self._create_error_result(
                        query,
                        date_range,
                        f"All {len(self._api_keys)} Serper API keys exhausted (quota/billing limit)",
                    )

                response.raise_for_status()
                results, total_results = self._parse_response(response)
                return self._create_success_result(query, date_range, results, total_results)

            except httpx.HTTPStatusError as e:
                if e.response.status_code in _ROTATE_STATUS_CODES and self._rotate_key(
                    f"HTTP {e.response.status_code}"
                ):
                    continue
                return self._create_error_result(query, date_range, self._handle_http_error(e))

            except httpx.TimeoutException:
                # Timeout is not a billing error — don't rotate, just fail
                return self._create_error_result(
                    query,
                    date_range,
                    f"Serper search timed out after {self.timeout}s",
                )

            except Exception as e:
                return self._create_error_result(query, date_range, e)
