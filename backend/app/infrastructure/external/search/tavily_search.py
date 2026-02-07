"""Tavily Search Engine

Tavily AI-powered Search API implementation.
Requires a Tavily API key from https://tavily.com/

Supports multiple API keys with automatic fallback: if the active key
hits quota/billing limits (HTTP 401, 402, 403, 429) or returns an error
in the JSON body, the engine rotates to the next configured key instantly.
Exhausted keys are remembered for the lifetime of the process so
subsequent searches skip them without making a network round-trip.
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

# Substrings in Tavily error responses that indicate billing/quota issues
_BILLING_ERROR_PATTERNS = (
    "quota",
    "limit",
    "exceeded",
    "billing",
    "payment",
    "credits",
    "subscription",
    "plan",
    "expired",
    "unauthorized",
    "invalid api key",
)


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
        timeout: float | None = None,
    ):
        """Initialize Tavily search engine.

        Args:
            api_key: Primary Tavily API key
            fallback_api_keys: Optional list of fallback API keys
            timeout: Optional custom timeout
        """
        super().__init__(timeout=timeout)
        # Collect all keys, filtering out obvious placeholders
        all_keys = [api_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)
        self._api_keys = [k for k in all_keys if not self._is_placeholder(k)]
        if not self._api_keys:
            # Keep at least the primary key even if it looks like a placeholder
            self._api_keys = [api_key]
        self._active_key_index = 0
        self._exhausted_keys: set[int] = set()  # Indices of keys that hit billing limits
        self.base_url = "https://api.tavily.com/search"
        logger.info(f"Tavily search initialized with {len(self._api_keys)} API key(s)")

    @staticmethod
    def _is_placeholder(key: str) -> bool:
        """Check if an API key is an obvious placeholder."""
        lower = key.lower()
        return "your-key" in lower or "your_key" in lower or key.strip() == ""

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
                detail = f" ({reason})" if reason else ""
                logger.warning(
                    f"Tavily API key rotated to key #{i + 1} of {len(self._api_keys)}{detail} "
                    f"— {len(self._exhausted_keys)}/{len(self._api_keys)} keys exhausted"
                )
                return True
        logger.error(f"All {len(self._api_keys)} Tavily API keys exhausted")
        return False

    def _get_headers(self) -> dict[str, str]:
        """Get Tavily API headers."""
        return {"Content-Type": "application/json"}

    def _get_date_range_mapping(self) -> dict[str, str]:
        """Tavily date hints (appended to query since API lacks direct filtering)."""
        return {
            "past_hour": "recent",
            "past_day": "today",
            "past_week": "this week",
            "past_month": "this month",
            "past_year": "this year",
        }

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, Any]:
        """Build Tavily API request payload."""
        actual_query = query
        if date_hint := self._map_date_range(date_range):
            actual_query = f"{query} {date_hint}"

        return {
            "api_key": self.api_key,
            "query": actual_query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
            "max_results": 20,
        }

    async def _execute_request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        """Execute POST request to Tavily API."""
        return await client.post(self.base_url, json=params)

    def _parse_response(self, response: httpx.Response) -> tuple[list[SearchResultItem], int]:
        """Parse Tavily API JSON response."""
        data = response.json()

        results: list[SearchResultItem] = []
        for item in data.get("results", []):
            title = item.get("title", "")
            link = item.get("url", "")
            snippet = item.get("content", "")

            if len(snippet) > 500:
                snippet = snippet[:497] + "..."

            if title and link:
                results.append(SearchResultItem(title=title, link=link, snippet=snippet))

        return results, len(results)

    def _is_billing_error_body(self, response: httpx.Response) -> str | None:
        """Check if a 200 response contains a billing/quota error in the JSON body.

        Tavily sometimes returns HTTP 200 with an error object instead of results.

        Returns:
            Error message string if billing error detected, None otherwise.
        """
        try:
            data = response.json()
        except Exception:
            return None

        # Check common error fields
        error_msg = data.get("error") or data.get("detail") or data.get("message") or ""
        if not error_msg:
            return None
        error_lower = str(error_msg).lower()
        if any(pattern in error_lower for pattern in _BILLING_ERROR_PATTERNS):
            return str(error_msg)
        return None

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        """Execute search with automatic API key rotation on billing/quota errors.

        Rotation triggers:
        - HTTP 401 (unauthorized / invalid key)
        - HTTP 402 (payment required)
        - HTTP 403 (forbidden / suspended)
        - HTTP 429 (rate limit)
        - HTTP 200 with billing-related error in JSON body

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
                query, date_range,
                f"All {len(self._api_keys)} Tavily API keys exhausted (quota/billing limit)",
            )

        while True:
            try:
                client = await self._get_client()
                params = self._build_request_params(query, date_range)
                response = await self._execute_request(client, params)

                # Check HTTP status for quota/billing/auth errors
                if response.status_code in _ROTATE_STATUS_CODES:
                    key_num = self._active_key_index + 1
                    logger.warning(
                        f"Tavily key #{key_num} failed (HTTP {response.status_code})"
                    )
                    if self._rotate_key(f"HTTP {response.status_code}"):
                        continue
                    return self._create_error_result(
                        query, date_range,
                        f"All {len(self._api_keys)} Tavily API keys exhausted (quota/billing limit)",
                    )

                response.raise_for_status()

                # Check for billing errors in JSON body (Tavily may return 200 with error)
                if billing_err := self._is_billing_error_body(response):
                    key_num = self._active_key_index + 1
                    logger.warning(f"Tavily key #{key_num} billing error in response: {billing_err}")
                    if self._rotate_key(billing_err):
                        continue
                    return self._create_error_result(
                        query, date_range,
                        f"All {len(self._api_keys)} Tavily API keys exhausted: {billing_err}",
                    )

                results, total_results = self._parse_response(response)
                return self._create_success_result(query, date_range, results, total_results)

            except httpx.HTTPStatusError as e:
                if e.response.status_code in _ROTATE_STATUS_CODES and self._rotate_key(f"HTTP {e.response.status_code}"):
                    continue
                return self._create_error_result(query, date_range, self._handle_http_error(e))

            except httpx.TimeoutException:
                # Timeout is not a billing error — don't rotate, just fail
                return self._create_error_result(
                    query, date_range,
                    f"Tavily search timed out after {self.timeout}s",
                )

            except Exception as e:
                return self._create_error_result(query, date_range, e)
