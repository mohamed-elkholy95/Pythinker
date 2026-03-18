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
from dataclasses import dataclass
from typing import Any

import httpx

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.http_pool import HTTPClientConfig, HTTPClientPool, ManagedHTTPClient
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

_SHOPPING_ENDPOINT = "https://google.serper.dev/shopping"


@dataclass
class ShoppingResult:
    """Structured product result from Google Shopping."""

    title: str
    source: str  # store name (e.g., "Best Buy", "Amazon")
    price: float
    link: str
    rating: float = 0.0
    rating_count: int = 0
    product_id: str = ""
    image_url: str = ""
    position: int = 0
    price_raw: str = ""  # original price string e.g. "$278.00"


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
        max_results: int = 8,
    ):
        """Initialize Serper search engine.

        Args:
            api_key: Primary Serper.dev API key
            fallback_api_keys: Optional list of fallback API keys
            redis_client: Redis client for distributed key coordination
            timeout: Optional custom timeout
            quota_cooldown_seconds: Cooldown after quota exhaustion (default 30min).
                Configurable via SERPER_QUOTA_COOLDOWN_SECONDS env var.
            max_results: Number of results to return per search (default 8)
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

        self._max_results = max_results

        self.base_url = "https://google.serper.dev/search"
        logger.info(f"Serper search initialized with {len(key_configs)} API key(s)")

    async def _get_client(self) -> ManagedHTTPClient:
        """Get a pooled HTTP client for Serper Search.

        Auth header (X-API-Key) is NOT baked in here — it is injected as a
        per-request header in search() so the connection pool is reused across
        all key rotations without needing to close and recreate the client.
        """
        config = HTTPClientConfig(
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=self.timeout,
            connect_timeout=10.0,
            read_timeout=self.timeout,
        )
        return await HTTPClientPool.get_client(
            name="search-serpersearchengine",
            config=config,
            follow_redirects=True,
        )

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
            "num": self._max_results,
        }

        if mapped := self._map_date_range(date_range):
            params["tbs"] = mapped

        return params

    async def _execute_request(self, client: ManagedHTTPClient, params: dict[str, Any]) -> httpx.Response:
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

    def _sanitize_query(self, query: str, context: str = "Serper") -> str:
        """Sanitize a search query for use in API requests.

        Collapses control characters and consecutive whitespace (which cause HTTP 400
        from Serper), strips leading/trailing whitespace, and caps length at 500 chars.

        Args:
            query: Raw query string from the caller.
            context: Label used in warning log when query is truncated (e.g. "Serper Shopping").

        Returns:
            Sanitized query string (may be empty — caller must check).
        """
        query = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", query).strip()
        query = re.sub(r" {2,}", " ", query)
        if len(query) > 500:
            logger.warning(f"{context} query truncated from {len(query)} to 500 chars")
            query = query[:500]
        return query

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

        query = self._sanitize_query(query)
        if not query:
            return self._create_error_result(query, date_range, "Serper bad request: empty search query")

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

    @staticmethod
    def _extract_price_number(price_raw: str) -> float:
        """Parse a price string like '$278.00' or '£1,299.99' into a float.

        Handles two separator conventions:
        - English: comma = thousands, dot = decimal  (e.g. "$1,299.99")
        - European: dot = thousands, comma = decimal (e.g. "€1.299,99")

        Detection rule: when both separators are present, the one appearing
        *last* in the string is the decimal separator.

        Args:
            price_raw: Raw price string from Serper Shopping API.

        Returns:
            Numeric price value, or 0.0 if parsing fails.
        """
        if not price_raw:
            return 0.0
        # Remove currency symbols and whitespace; keep digits, commas, and dots
        cleaned = re.sub(r"[^\d.,]", "", price_raw)
        if not cleaned:
            return 0.0

        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")

        if last_dot == -1 and last_comma == -1:
            # Digits only — nothing to do
            pass
        elif last_dot == -1:
            # Only commas present — decide by position of last comma:
            # if exactly 3 digits follow the last comma → thousands separator (e.g. "1,000")
            # otherwise → decimal separator (e.g. "1299,99")
            after_last_comma = cleaned[last_comma + 1 :]
            if len(after_last_comma) == 3 and after_last_comma.isdigit():
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(",", ".")
        elif last_comma == -1:
            # Only dots present — decide by position of last dot:
            # if exactly 3 digits follow the last dot → thousands separator (e.g. "1.000")
            # otherwise → decimal separator (e.g. "299.99")
            after_last_dot = cleaned[last_dot + 1 :]
            if len(after_last_dot) == 3 and after_last_dot.isdigit():
                cleaned = cleaned.replace(".", "")
            # else: keep as-is (valid decimal float string)
        elif last_comma > last_dot:
            # Comma comes after dot → European format (dot=thousands, comma=decimal)
            # e.g. "1.299,99" → remove dots → "1299,99" → replace comma with dot → "1299.99"
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Dot comes after comma → English format (comma=thousands, dot=decimal)
            # e.g. "1,299.99" → remove commas → "1299.99"
            cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _parse_shopping_item(self, item: dict[str, Any], position: int) -> ShoppingResult | None:
        """Parse a single Serper Shopping API result item into a ShoppingResult.

        Args:
            item: Raw dict from the ``shopping`` array in the API response.
            position: 1-based position within the results list.

        Returns:
            A populated :class:`ShoppingResult`, or ``None`` if required fields are absent.
        """
        title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        source = item.get("source", "").strip()
        price_raw = item.get("price", "")

        if not title or not link:
            return None

        price = self._extract_price_number(price_raw)

        return ShoppingResult(
            title=title,
            source=source,
            price=price,
            link=link,
            rating=float(item.get("rating", 0.0) or 0.0),
            rating_count=int(item.get("ratingCount", 0) or 0),
            product_id=str(item.get("productId", "") or ""),
            image_url=item.get("imageUrl", "") or "",
            position=int(item.get("position", position) or position),
            price_raw=price_raw,
        )

    async def search_shopping(
        self,
        query: str,
        num: int = 10,
        _attempt: int = 0,
    ) -> ToolResult[list[ShoppingResult]]:
        """Search Google Shopping via Serper and return structured product results.

        Posts to ``https://google.serper.dev/shopping`` and parses the
        ``shopping`` array from the JSON response into :class:`ShoppingResult`
        objects.

        Key rotation follows the same pattern as :meth:`search`: on HTTP
        401/402/403/429/400 the current key is marked exhausted via
        :attr:`_key_pool` and the next healthy key is tried.

        Args:
            query: Product search query (e.g. "Sony WH-1000XM5 headphones").
            num: Maximum number of results to request (default 10).
            _attempt: Internal retry counter — do not pass externally.

        Returns:
            :class:`ToolResult` whose ``data`` is a list of
            :class:`ShoppingResult` objects (may be empty). On failure,
            ``success`` is ``False`` and ``message`` describes the error.
        """
        if _attempt >= self._max_retries:
            return ToolResult.error(
                f"All {len(self._key_pool.keys)} Serper API keys exhausted after {_attempt} attempts"
            )

        query = self._sanitize_query(query, context="Serper Shopping")
        if not query:
            return ToolResult.error("Serper Shopping bad request: empty search query")

        key = await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)
        if not key:
            return ToolResult.error(f"All {len(self._key_pool.keys)} Serper API keys exhausted")

        try:
            client = await self._get_client()
            params: dict[str, Any] = {"q": query, "gl": "us", "hl": "en", "num": num}

            response = await client.post(
                _SHOPPING_ENDPOINT,
                json=params,
                headers={"X-API-Key": key},
            )

            if response.status_code in _ROTATE_STATUS_CODES:
                body = response.text[:200]
                logger.warning(
                    "Serper Shopping key error (HTTP %d%s), rotating",
                    response.status_code,
                    f": {body}" if body else "",
                )
                await self._key_pool.handle_error(key, status_code=response.status_code, body_text=body)
                return await self.search_shopping(query, num=num, _attempt=_attempt + 1)

            response.raise_for_status()

            # Dual quota detection in response body
            response_text = response.text[:500]
            if _text_has_quota_keywords(response_text):
                logger.warning("Serper Shopping quota keyword detected in response body, rotating key")
                await self._key_pool.handle_error(key, body_text=response_text)
                return await self.search_shopping(query, num=num, _attempt=_attempt + 1)

            data = response.json()
            raw_items: list[dict[str, Any]] = data.get("shopping", [])

            results: list[ShoppingResult] = []
            for pos, item in enumerate(raw_items, start=1):
                parsed = self._parse_shopping_item(item, position=pos)
                if parsed is not None:
                    results.append(parsed)

            self._key_pool.record_success(key)
            logger.debug("Serper Shopping returned %d results for query (len=%d)", len(results), len(query))
            return ToolResult.ok(
                message=f"Found {len(results)} shopping results for '{query}'",
                data=results,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in _ROTATE_STATUS_CODES:
                body = e.response.text[:200] if hasattr(e.response, "text") else ""
                await self._key_pool.handle_error(key, status_code=e.response.status_code, body_text=body)
                return await self.search_shopping(query, num=num, _attempt=_attempt + 1)
            return ToolResult.error(self._handle_http_error(e))

        except httpx.TimeoutException:
            await self._key_pool.handle_error(key, is_network_error=True)
            return ToolResult.error(f"Serper Shopping search timed out after {self.timeout}s")

        except Exception as e:
            logger.exception("Serper Shopping unexpected error: %s: %r", type(e).__name__, e)
            return ToolResult.error(f"Serper Shopping error: {type(e).__name__}: {e}")
