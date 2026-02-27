import asyncio
import logging
import re
import time
from collections import OrderedDict
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from app.domain.external.search import SearchEngine
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.external.browser import Browser
    from app.domain.external.scraper import Scraper

logger = logging.getLogger(__name__)


class SearchType(str, Enum):
    """Search intent types inspired by Pythinker AI.

    Different search types route to optimized backends and apply
    appropriate filtering and formatting for each use case.
    """

    INFO = "info"  # General web content (default)
    NEWS = "news"  # Current events with time filtering
    IMAGE = "image"  # Visual assets and images
    ACADEMIC = "academic"  # Research papers and scholarly articles
    API = "api"  # API documentation and developer resources
    DATA = "data"  # Structured datasets and statistics
    TOOL = "tool"  # External tools and SaaS platforms


# Search type configurations
SEARCH_TYPE_CONFIG = {
    SearchType.INFO: {
        "date_default": None,
        "query_suffix": "",
        "result_format": "standard",
    },
    SearchType.NEWS: {
        "date_default": "past_week",
        "query_suffix": "",
        "result_format": "news",
    },
    SearchType.IMAGE: {
        "date_default": None,
        "query_suffix": "",
        "result_format": "image",
    },
    SearchType.ACADEMIC: {
        "date_default": None,
        "query_suffix": "site:arxiv.org OR site:scholar.google.com OR site:pubmed.gov OR site:researchgate.net",
        "result_format": "academic",
    },
    SearchType.API: {
        "date_default": None,
        "query_suffix": "API documentation OR SDK OR developer guide",
        "result_format": "technical",
    },
    SearchType.DATA: {
        "date_default": None,
        "query_suffix": "dataset OR statistics OR data.gov OR kaggle",
        "result_format": "data",
    },
    SearchType.TOOL: {
        "date_default": None,
        "query_suffix": "tool OR app OR software OR platform",
        "result_format": "standard",
    },
}

# Common stopwords to remove for query normalization
STOPWORDS: set[str] = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "about",
    "also",
    "and",
    "or",
    "but",
    "if",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
    "am",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "me",
    "him",
    "us",
    "them",
}

# Domains that are typically authoritative sources
AUTHORITATIVE_DOMAINS = [
    # Manufacturer/official sites
    ".com/products",
    "/product/",
    "/specs",
    "/specifications",
    # Review sites
    "wirecutter.com",
    "rtings.com",
    "tomshardware.com",
    "techradar.com",
    "theverge.com",
    "arstechnica.com",
    "anandtech.com",
    # Documentation
    "docs.",
    "documentation",
    "manual",
]

# Keywords that suggest a research/comparison task
RESEARCH_KEYWORDS = ["best", "compare", "vs", "versus", "review", "recommend", "alternative"]


class QueryExpander:
    """Expands queries into multiple variants for comprehensive search.

    Inspired by Pythinker's query expansion which processes up to 3 variants
    to improve result relevance.
    """

    @staticmethod
    def expand(query: str, search_type: SearchType = SearchType.INFO, max_variants: int = 3) -> list[str]:
        """Generate query variants for broader coverage.

        Args:
            query: Original search query
            search_type: Type of search to optimize for
            max_variants: Maximum number of query variants (1-3)

        Returns:
            List of query variants including original
        """
        variants = [query]  # Always include original

        if max_variants <= 1:
            return variants

        # Add search type suffix if configured
        config = SEARCH_TYPE_CONFIG.get(search_type, {})
        suffix = config.get("query_suffix", "")
        if suffix and len(variants) < max_variants:
            variants.append(f"{query} {suffix}")

        # Synonym-based expansion for common terms
        synonyms = {
            "best": ["top", "leading", "recommended"],
            "how to": ["tutorial", "guide", "steps"],
            "what is": ["definition", "meaning", "explain"],
            "review": ["comparison", "analysis", "evaluation"],
            "alternative": ["similar to", "like", "instead of"],
            "cheap": ["affordable", "budget", "low-cost"],
            "fast": ["quick", "rapid", "speedy"],
        }

        for term, replacements in synonyms.items():
            if term in query.lower() and len(variants) < max_variants:
                for replacement in replacements[:1]:  # Take first synonym only
                    variant = query.lower().replace(term, replacement)
                    if variant not in [v.lower() for v in variants]:
                        variants.append(variant.title() if query[0].isupper() else variant)
                        break

        return variants[:max_variants]


class SearchTool(BaseTool):
    """Search tool class, providing search engine interaction functions with caching.

    When `search_prefer_browser` is enabled in settings and a browser instance is provided,
    searches will be performed visually in the browser (visible in live preview/sandbox viewer)
    instead of using the API-based search engine.
    """

    name: str = "search"

    _cache_ttl: ClassVar[int] = 3600  # 1 hour cache TTL
    _cache_max_size: ClassVar[int] = 100  # Maximum cache entries
    # prevent GC of fire-and-forget browse tasks
    _background_tasks: ClassVar[set[asyncio.Task[None]]] = set()

    class _BudgetTracker:
        """Per-task search API call budget enforcement.

        Tracks actual API calls (not tool invocations) and wide_research usage
        to prevent runaway key consumption within a single agent task.
        """

        def __init__(self, max_api_calls: int, max_wide_research: int) -> None:
            self._api_calls = 0
            self._wide_calls = 0
            self._max_api = max_api_calls
            self._max_wide = max_wide_research

        def can_search(self) -> tuple[bool, str]:
            if self._api_calls >= self._max_api:
                return False, f"Search budget exhausted ({self._api_calls}/{self._max_api} API calls used)"
            return True, ""

        def can_wide_research(self) -> tuple[bool, str]:
            if self._wide_calls >= self._max_wide:
                return False, f"Wide research limit reached ({self._wide_calls}/{self._max_wide})"
            return self.can_search()

        def record_api_call(self, count: int = 1) -> None:
            self._api_calls += count

        def record_wide_research(self) -> None:
            self._wide_calls += 1

        def remaining(self) -> int:
            return max(0, self._max_api - self._api_calls)

    def __init__(
        self,
        search_engine: SearchEngine,
        browser: "Browser | None" = None,
        max_observe: int | None = None,
        search_prefer_browser: bool | None = None,
        scraper: "Scraper | None" = None,
    ):
        """Initialize search tool class

        Args:
            search_engine: Search engine service for API-based search
            browser: Optional browser instance for visual search (visible in live preview)
            max_observe: Optional custom observation limit (default: 8000)
            scraper: Optional scraper for spider-based URL enrichment in wide_research
        """
        super().__init__(max_observe=max_observe)
        self.search_engine = search_engine
        self._browser = browser
        self._search_prefer_browser = search_prefer_browser
        self._scraper = scraper
        # Instance-level cache with O(1) LRU eviction
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

        # Budget enforcement (per-task, since SearchTool is instantiated per task)
        from app.core.config import get_settings

        settings = get_settings()
        self._budget = self._BudgetTracker(
            max_api_calls=settings.max_search_api_calls_per_task,
            max_wide_research=settings.max_wide_research_calls_per_task,
        )
        self._max_wide_queries = settings.max_wide_research_queries
        self._dedup_skip = settings.search_dedup_skip_existing

        # Cache for pre-planning search results.  When the planner ran
        # pre-planning web searches, the execution agent propagates the
        # context here so that dedup-blocked queries can return cached
        # results instead of failing with 0 results.
        self._pre_planning_context: str | None = None

    def _should_use_browser_search(self) -> bool:
        """Check if browser-based search should be used.

        Returns True when:
        1. search_prefer_browser is enabled
        2. A browser instance is available
        """
        prefer_browser = self._search_prefer_browser
        if prefer_browser is None:
            from app.core.config import get_settings

            prefer_browser = get_settings().search_prefer_browser
        return prefer_browser and self._browser is not None

    async def _search_via_browser(self, query: str, date_range: str | None = None) -> ToolResult:
        """Perform search using browser navigation (visible in live preview/sandbox viewer).

        This navigates the browser to DuckDuckGo and extracts results,
        making the search visible to users in the sandbox viewer.

        Args:
            query: Search query
            date_range: Optional time range filter

        Returns:
            Search results from browser-based search
        """
        if not self._browser:
            return ToolResult(
                success=False,
                message="Browser not available for search",
            )

        try:
            # Build DuckDuckGo URL
            search_url = f"https://duckduckgo.com/?q={quote(query)}"
            if date_range and date_range != "all":
                time_map = {
                    "past_day": "d",
                    "past_week": "w",
                    "past_month": "m",
                    "past_year": "y",
                }
                if date_range in time_map:
                    search_url += f"&df={time_map[date_range]}"

            logger.info(f"Browser search via DuckDuckGo (visible in sandbox): {query}")

            # Navigate to search page
            nav_result = await self._browser.navigate(search_url)

            if not nav_result.success:
                logger.error(f"Browser navigation failed: {nav_result.message}")
                return ToolResult(
                    success=False,
                    message=f"Browser search failed: {nav_result.message}. Ensure sandbox is running.",
                )

            # Wait briefly for page load
            await asyncio.sleep(1.0)

            # Get page content
            view_result = await self._browser.view_page(wait_for_load=True)
            if not view_result.success:
                logger.error(f"Browser view failed: {view_result.message}")
                return ToolResult(
                    success=False,
                    message=f"Browser search failed to view results: {view_result.message}",
                )

            # Extract content from browser view
            content = view_result.message or ""

            # Build result message
            message = "[BROWSER SEARCH - visible in sandbox]\n"
            message += f"Query: {query}\n"
            if date_range:
                message += f"Time filter: {date_range}\n"
            message += f"\n{content[:6000]}"  # Limit content size

            # Add verification guidance for research queries
            if self._is_research_query(query):
                message += (
                    "\n\nVERIFICATION REQUIRED: These are search results displayed in browser. "
                    "Click on links to visit pages and verify information before making claims."
                )

            return ToolResult(
                success=True,
                message=message,
                data={"query": query, "date_range": date_range, "source": "browser"},
            )

        except Exception as e:
            logger.error(f"Browser search error: {e}")
            return ToolResult(
                success=False,
                message=f"Browser search failed: {e!s}. Ensure sandbox browser is running.",
            )

    def _normalize_query(self, query: str) -> str:
        """Normalize query for semantic deduplication.

        Transforms queries like "Python 3.12 features" and "new features in python 3.12"
        into the same normalized form for cache lookup.

        Args:
            query: Raw search query

        Returns:
            Normalized query string
        """
        # Lowercase
        normalized = query.lower()

        # Remove punctuation except hyphens in compound words
        normalized = re.sub(r"[^\w\s-]", " ", normalized)

        # Split into words
        words = normalized.split()

        # Remove stopwords and short words
        words = [w for w in words if w not in STOPWORDS and len(w) > 1]

        # Sort alphabetically for order-independent matching
        words.sort()

        # Join back
        return " ".join(words)

    def _get_cache_key(
        self, query: str, date_range: str | None = None, search_type: SearchType = SearchType.INFO
    ) -> str:
        """Generate cache key from normalized query parameters.

        Uses semantic normalization to catch equivalent queries.
        """
        normalized = self._normalize_query(query)
        return f"{search_type.value}:{normalized}:{date_range or 'all'}"

    def _get_from_cache(self, cache_key: str) -> ToolResult | None:
        """Get cached result if valid, with LRU promotion."""
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                self._cache.move_to_end(cache_key)  # LRU: promote on hit
                logger.debug(f"Search cache hit for: {cache_key[:50]}")
                return data
            # Cache expired, remove it
            del self._cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: ToolResult) -> None:
        """Save result to cache with O(1) LRU eviction."""
        # Evict oldest entry if cache is full (O(1) with OrderedDict)
        if len(self._cache) >= self._cache_max_size:
            self._cache.popitem(last=False)

        self._cache[cache_key] = (time.time(), result)
        logger.debug(f"Search cached: {cache_key[:50]}")

    async def _execute_typed_search(
        self, query: str, date_range: str | None = None, search_type: SearchType = SearchType.INFO
    ) -> ToolResult:
        """Execute a search with the specified type.

        Args:
            query: Search query
            date_range: Optional time range filter
            search_type: Type of search to perform

        Returns:
            Search results
        """
        # Apply search type configuration
        config = SEARCH_TYPE_CONFIG.get(search_type, {})

        # Use default date range for search type if not specified
        if date_range is None:
            date_range = config.get("date_default")

        # For news searches, force recent results
        if search_type == SearchType.NEWS and date_range is None:
            date_range = "past_week"

        # Use browser-based search if enabled (visible in live preview/sandbox viewer)
        if self._should_use_browser_search():
            logger.info(f"Using browser search for {search_type.value} query: {query}")
            result = await self._search_via_browser(query, date_range)
            # Add search type context to browser result
            if result.success and result.message:
                result.message = f"[{search_type.value.upper()} SEARCH via BROWSER]\n{result.message}"
            return result

        # Check cache (API search only)
        cache_key = self._get_cache_key(query, date_range, search_type)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # Budget check before making the API call
        ok, reason = self._budget.can_search()
        if not ok:
            from app.core.prometheus_metrics import search_budget_exhausted_total

            search_budget_exhausted_total.inc({"tool": "api_search"})
            logger.warning(f"Search budget exhausted: {reason}")
            from app.domain.models.search import SearchResults

            return ToolResult(
                success=False,
                message=reason,
                data=SearchResults(query=query, date_range=date_range),
            )

        # Execute API search
        result = await self.search_engine.search(query, date_range)

        # Record the API call in budget and Prometheus
        self._budget.record_api_call()
        try:
            from app.core.prometheus_metrics import search_api_calls_total

            provider = getattr(self.search_engine, "provider_name", "unknown").lower()
            search_api_calls_total.inc({"provider": provider, "tool": "api_search"})
        except Exception:
            logger.debug("Failed to record search API call metric", exc_info=True)

        result = self._add_verification_guidance(result, query)

        # Add search type context to result
        if result.success and result.message:
            result.message = f"[{search_type.value.upper()} SEARCH]\n{result.message}"
        elif result.success:
            result.message = f"[{search_type.value.upper()} SEARCH]"

        # Cache successful results
        if result.success:
            self._save_to_cache(cache_key, result)

        return result

    async def expanded_search(
        self,
        query: str,
        search_type: SearchType = SearchType.INFO,
        date_range: str | None = None,
        max_variants: int = 3,
    ) -> ToolResult:
        """Execute search with query expansion for comprehensive coverage.

        Inspired by Pythinker's query expansion which processes up to 3 variants
        to improve result relevance.

        Args:
            query: Original search query
            search_type: Type of search to perform
            date_range: Optional time range filter
            max_variants: Number of query variants to search (1-3)

        Returns:
            Aggregated search results from all variants
        """
        # Generate query variants
        variants = QueryExpander.expand(query, search_type, max_variants)
        logger.info(f"Expanded query into {len(variants)} variants: {variants}")

        # Execute variants concurrently with early deduplication
        # Use a lock to protect shared state from concurrent mutation
        all_items = []
        seen_urls: set[str] = set()
        variant_errors: list[str] = []
        semaphore = asyncio.Semaphore(3)
        dedup_lock = asyncio.Lock()

        async def search_and_dedup(query: str) -> None:
            async with semaphore:
                try:
                    result = await self._execute_typed_search(query, date_range, search_type)
                except Exception as exc:
                    async with dedup_lock:
                        variant_errors.append(f"{query}: {exc!s}")
                    return

                if not result.success:
                    async with dedup_lock:
                        variant_errors.append(f"{query}: {result.message or 'search failed'}")
                    return

                if result.data:
                    async with dedup_lock:
                        for item in result.data.results:
                            if item.link not in seen_urls:
                                seen_urls.add(item.link)
                                all_items.append(item)

        results = await asyncio.gather(
            *[search_and_dedup(v) for v in variants],
            return_exceptions=True,
        )
        # Log any exceptions from variant searches
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning(f"Search variant {i} failed: {r}")
                variant_errors.append(f"{variants[i]}: {r!s}")

        # Create aggregated result
        from app.domain.models.search import SearchResults

        aggregated_data = SearchResults(
            query=query,
            date_range=date_range,
            total_results=len(all_items),
            results=all_items[:20],  # Limit to top 20
        )

        message = f"[{search_type.value.upper()} SEARCH - {len(variants)} variants]\n"
        message += f"Found {len(all_items)} unique results across {len(variants)} query variants."
        if variant_errors:
            error_preview = "; ".join(variant_errors[:3])
            if len(variant_errors) > 3:
                error_preview += f"; ... (+{len(variant_errors) - 3} more)"
            message += f"\n\nVARIANT ERRORS ({len(variant_errors)}): {error_preview}"

        if not all_items and variant_errors:
            return ToolResult(
                success=False,
                data=aggregated_data,
                message=(
                    f"[{search_type.value.upper()} SEARCH - {len(variants)} variants]\n"
                    f"All variants failed for query '{query}'.\n"
                    f"Errors: {error_preview}"
                ),
            )

        if self._is_research_query(query):
            message += (
                "\n\nVERIFICATION REQUIRED: These are search snippets only. "
                "For research/comparison tasks, you MUST visit official product pages "
                "to verify specifications before making claims."
            )

        return ToolResult(success=True, data=aggregated_data, message=message)

    async def _browse_top_results(self, search_data: Any, count: int = 3) -> None:
        """Open top search result URLs in the browser for live preview visibility.

        After API search returns results, navigates to the top URLs so the user
        can see browsing activity in the sandbox live preview. This runs as a
        fire-and-forget background task and does not block the search response.

        Args:
            search_data: SearchResults model or dict with results list
            count: Number of top results to open (default 3)
        """
        try:
            browser_type = type(self._browser)
            supports_lazy_connect = hasattr(browser_type, "initialize") and hasattr(browser_type, "_ensure_page")
            if (
                hasattr(self._browser, "is_connected")
                and not self._browser.is_connected()
                and not supports_lazy_connect
            ):
                logger.debug("_browse_top_results: browser disconnected and lazy connect is unavailable, skipping")
                return

            # Extract result items from SearchResults model or dict
            if hasattr(search_data, "results"):
                items = search_data.results
            elif isinstance(search_data, dict):
                items = search_data.get("results", [])
            else:
                return

            urls: list[str] = []
            for item in items[:count]:
                url = getattr(item, "link", None) or (item.get("link") if isinstance(item, dict) else None)
                if url:
                    urls.append(url)

            if not urls:
                return

            logger.info(f"Browsing top {len(urls)} search results for live preview visibility")
            consecutive_failures = 0
            max_failures = 2
            navigation_timeout_seconds = 20.0
            for url in urls:
                # Check if a foreground browser operation cancelled us
                if getattr(self._browser, "_background_browse_cancelled", False):
                    logger.info("_browse_top_results: cancelled by foreground browser operation")
                    break
                try:
                    if hasattr(self._browser, "navigate_for_display"):
                        success = await asyncio.wait_for(
                            self._browser.navigate_for_display(url),
                            timeout=navigation_timeout_seconds,
                        )
                        if not success:
                            consecutive_failures += 1
                        else:
                            consecutive_failures = 0
                    else:
                        await asyncio.wait_for(
                            self._browser.navigate(url),
                            timeout=navigation_timeout_seconds,
                        )
                        consecutive_failures = 0
                    # Brief pause for live preview render (kept short to avoid blocking)
                    await asyncio.sleep(1.0)
                except Exception as e:
                    consecutive_failures += 1
                    logger.debug(f"Failed to browse {url}: {e}")

                if consecutive_failures >= max_failures:
                    logger.info(
                        f"_browse_top_results: stopping early after {consecutive_failures} consecutive failures"
                    )
                    break
        except Exception as e:
            logger.debug(f"_browse_top_results error (non-critical): {e}")

    def _is_research_query(self, query: str) -> bool:
        """Check if query indicates a research task"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in RESEARCH_KEYWORDS)

    def _add_verification_guidance(self, result: ToolResult, query: str) -> ToolResult:
        """Add verification guidance to search results for research queries"""
        if not result.success or not self._is_research_query(query):
            return result

        # Add verification reminder to the result message
        verification_note = (
            "\n\nVERIFICATION REQUIRED: These are search snippets only. "
            "For research/comparison tasks, you MUST visit official product pages "
            "to verify specifications before making claims. "
            "Prioritize: manufacturer sites > review sites (Wirecutter, RTINGS) > forums."
            "\n\nRECENCY CHECK: Verify publish dates on sources - prefer content from last 6 months. "
            "Do NOT rely on your model knowledge for prices, specs, or availability - it may be outdated."
        )

        if result.message:
            result.message += verification_note
        else:
            result.message = verification_note.strip()

        return result

    @tool(
        name="info_search_web",
        description="Search web pages using search engine. Use for obtaining latest information or finding references.",
        parameters={
            "query": {
                "type": "string",
                "description": "Search query in Google search style, using 3-5 keywords.",
            },
            "date_range": {
                "type": "string",
                "enum": ["all", "past_hour", "past_day", "past_week", "past_month", "past_year"],
                "description": "(Optional) Time range filter for search results.",
            },
        },
        required=["query"],
    )
    async def info_search_web(self, query: str, date_range: str | None = None) -> ToolResult:
        """Search webpages using search engine.

        Tries browser-based search first (visible in live preview), falls back to API search.

        Args:
            query: Search query, Google search style, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results
        """
        logger.info(f"Info search web: {query}")

        # Budget check
        ok, reason = self._budget.can_search()
        if not ok:
            from app.core.prometheus_metrics import search_budget_exhausted_total

            search_budget_exhausted_total.inc({"tool": "info_search_web"})
            logger.warning(f"Search budget exhausted for info_search_web: {reason}")
            from app.domain.models.search import SearchResults

            return ToolResult(
                success=False,
                message=reason,
                data=SearchResults(query=query, date_range=date_range),
            )

        # Record query in task state to survive token trimming
        is_new = True
        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            tsm = get_task_state_manager()
            is_new = tsm.record_query(query)
            if not is_new:
                logger.info(f"Search query already executed: {query}")
        except Exception:
            logger.debug("Failed to record search query in task state", exc_info=True)

        # Skip duplicate if already searched and dedup enabled
        if self._dedup_skip and not is_new:
            # If pre-planning search context is available, return it instead
            # of failing — the results are already in the agent's context.
            if self._pre_planning_context:
                logger.info(f"Dedup hit for '{query}' — returning cached pre-planning results")
                from app.domain.models.search import SearchResults

                return ToolResult(
                    success=True,
                    message=(
                        f"Results for '{query}' (from pre-planning search):\n\n"
                        f"{self._pre_planning_context}"
                    ),
                    data=SearchResults(query=query, date_range=date_range),
                )

            logger.info(f"Skipping duplicate search (dedup_skip=True): {query}")
            from app.domain.models.search import SearchResults

            return ToolResult(
                success=False,
                message=f"Already searched: '{query}'. Use different keywords for new results.",
                data=SearchResults(query=query, date_range=date_range),
            )

        # Try browser-based search first only when explicitly enabled via settings
        if self._should_use_browser_search():
            result = await self._search_via_browser(query, date_range)
            if result.success and result.message:
                content_parts = result.message.split("\n\n", 1)
                actual_content = content_parts[1] if len(content_parts) > 1 else ""
                if actual_content.strip():
                    return result
                logger.warning("Browser search returned empty content, falling back to API")
            else:
                logger.warning(f"Browser search failed, falling back to API: {result.message}")

        # API-based search (default path)
        logger.info(f"Using API search for: {query}")
        result = await self.search_engine.search(query, date_range)

        # Record the API call in budget and Prometheus (not in _execute_typed_search path)
        self._budget.record_api_call()
        try:
            from app.core.prometheus_metrics import search_api_calls_total

            provider = getattr(self.search_engine, "provider_name", "unknown").lower()
            search_api_calls_total.inc({"provider": provider, "tool": "info_search_web"})
        except Exception:
            logger.debug("Failed to record search API call metric", exc_info=True)

        result = self._add_verification_guidance(result, query)
        if result.success and result.message:
            result.message = f"[INFO SEARCH]\n{result.message}"
        elif result.success:
            result.message = "[INFO SEARCH]"

        # Fire-and-forget: open top 3 results in browser for live preview visibility
        if result.success and self._browser and result.data:
            if hasattr(self._browser, "allow_background_browsing"):
                self._browser.allow_background_browsing()
            task = asyncio.create_task(self._browse_top_results(result.data, count=3))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            # Append system note to prevent LLM from re-navigating these same URLs
            result.message = (
                (result.message or "")
                + "\n\n[SYSTEM NOTE: Top search result URLs are being opened automatically in the browser. "
                "Do NOT call browser_navigate to these same URLs. Proceed to analyze the search snippets "
                "or use browser_get_content to read pages already opened.]"
            )

        return result

    # Legacy alias for backward compatibility
    async def web_search(self, query: str, date_range: str | None = None) -> ToolResult:
        """Legacy alias for info_search_web. Use info_search_web instead."""
        return await self.info_search_web(query, date_range)

    @tool(
        name="wide_research",
        description="""Execute deep, comprehensive research with parallel searches across multiple queries and source types.

USE THIS instead of info_search_web when:
- You need thorough, in-depth research (not just a quick lookup)
- The topic requires searching from multiple angles
- You want to compare information across sources
- You need to validate claims with multiple sources

This searches MORE queries, uses query expansion, and runs searches in PARALLEL
for comprehensive coverage. Takes longer but produces much better results.

EXAMPLE:
wide_research(
    topic="best practices for Python async programming",
    queries=["python async best practices", "asyncio patterns", "python concurrent programming"],
    date_range="past_year"
)""",
        parameters={
            "topic": {"type": "string", "description": "Research topic or main question"},
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 2-5 specific search queries related to the topic",
            },
            "search_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["info", "news", "academic", "api", "data", "tool"]},
                "description": "Types of sources to search. Default: ['info']",
            },
            "date_range": {
                "type": "string",
                "enum": ["all", "past_week", "past_month", "past_year"],
                "description": "Time range filter for results",
            },
        },
        required=["topic", "queries"],
    )
    async def wide_research(
        self,
        topic: str,
        queries: list[str],
        search_types: list[str] | None = None,
        date_range: str | None = None,
    ) -> ToolResult:
        """Execute comprehensive parallel research — deep search with more queries and sources.

        Uses the same search mechanism as info_search_web but runs multiple queries
        in parallel with query expansion for thorough coverage.

        Args:
            topic: Research topic or main question
            queries: List of search queries (2-5)
            search_types: Types of sources to search
            date_range: Time range filter

        Returns:
            Comprehensive research results with SearchResults data for display
        """
        from app.domain.models.search import SearchResultItem, SearchResults

        # Budget check for wide_research invocation
        ok, reason = self._budget.can_wide_research()
        if not ok:
            from app.core.prometheus_metrics import search_budget_exhausted_total

            search_budget_exhausted_total.inc({"tool": "wide_research"})
            logger.warning(f"Wide research budget exhausted: {reason}")
            return ToolResult(
                success=False,
                message=reason,
                data=SearchResults(query=topic, date_range=date_range),
            )

        # Clamp queries list to configured maximum
        if len(queries) > self._max_wide_queries:
            logger.warning(
                f"Wide research queries clamped: {len(queries)} → {self._max_wide_queries}"
            )
            queries = queries[: self._max_wide_queries]

        # Parse search types
        if search_types is None:
            search_types = ["info"]

        stypes = []
        for st in search_types:
            try:
                stypes.append(SearchType(st.lower()))
            except ValueError:
                logger.warning(f"Unknown search type '{st}', skipping")

        if not stypes:
            stypes = [SearchType.INFO]

        # Generate all query-type combinations with expansion
        all_queries = []
        for query in queries:
            for stype in stypes:
                variants = QueryExpander.expand(query, stype, max_variants=2)
                all_queries.extend((variant, stype) for variant in variants)

        # Trim to remaining budget
        remaining = self._budget.remaining()
        if len(all_queries) > remaining:
            logger.warning(
                f"Wide research queries trimmed to budget: {len(all_queries)} → {remaining}"
            )
            all_queries = all_queries[:remaining]

        logger.info(f"Wide research on '{topic}': {len(all_queries)} total queries across {len(stypes)} search types")

        # Record all queries in task state to survive token trimming
        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            tsm = get_task_state_manager()
            tsm.record_query(topic)
            for q in queries:
                tsm.record_query(q)
        except Exception:
            logger.debug("Failed to record batch search queries in task state", exc_info=True)

        # Execute all searches in parallel with lock-protected dedup
        all_items: list[SearchResultItem] = []
        seen_urls: set[str] = set()
        errors: list[str] = []
        dedup_lock = asyncio.Lock()

        async def search_one(query_str: str, stype: SearchType) -> None:
            try:
                result = await self._execute_typed_search(query_str, date_range, stype)
                if result.success and result.data and hasattr(result.data, "results"):
                    async with dedup_lock:
                        for item in result.data.results:
                            if item.link not in seen_urls:
                                seen_urls.add(item.link)
                                all_items.append(item)
            except Exception as e:
                async with dedup_lock:
                    errors.append(f"{query_str}: {e}")

        # Run with concurrency limit
        semaphore = asyncio.Semaphore(5)

        async def search_with_limit(query_str: str, stype: SearchType) -> None:
            async with semaphore:
                await search_one(query_str, stype)

        await asyncio.gather(
            *[search_with_limit(q, st) for q, st in all_queries],
            return_exceptions=True,
        )

        # Record wide_research invocation (individual API calls already tracked in _execute_typed_search)
        self._budget.record_wide_research()

        # Optional spider enrichment: fetch full page content for top-K URLs
        if self._scraper and all_items:
            from app.core.config import get_settings as _get_settings

            _s = _get_settings()
            if _s.scraping_spider_enabled:
                top_k = _s.scraping_spider_top_k
                top_urls = [item.link for item in all_items[:top_k] if item.link]
                if top_urls:
                    logger.info(
                        "Spider-enriching %d URLs for wide_research on '%s'",
                        len(top_urls),
                        topic,
                    )
                    try:
                        fetched = await self._scraper.fetch_batch(top_urls)
                        url_to_content = {
                            r.url: r for r in fetched if r.success and len(r.text) > 200
                        }
                        for item in all_items:
                            if item.link in url_to_content:
                                r = url_to_content[item.link]
                                item.snippet = r.text[:2000]
                                if r.title and not item.title:
                                    item.title = r.title
                        logger.info(
                            "Spider enriched %d/%d URLs", len(url_to_content), len(top_urls)
                        )
                    except Exception as exc:
                        logger.warning("Spider enrichment failed for '%s': %s", topic, exc)

        # Build SearchResults (same format as info_search_web) for SearchContentView display
        search_data = SearchResults(
            query=topic,
            date_range=date_range,
            total_results=len(all_items),
            results=all_items[:20],  # Top 20 results
        )

        # Return failure if no results found — distinguish error types
        if not all_items:
            if len(errors) == len(all_queries):
                # All queries failed (API errors, network issues)
                return ToolResult(
                    success=False,
                    message=(
                        f"[WIDE RESEARCH] All {len(all_queries)} queries failed for '{topic}'. "
                        f"Search API errors: {', '.join(errors[:3])}"
                    ),
                    data=search_data,
                )
            # Queries succeeded but returned no results
            error_detail = f" ({len(errors)} query errors)" if errors else ""
            return ToolResult(
                success=False,
                message=(
                    f"[WIDE RESEARCH] No results found for '{topic}' "
                    f"after {len(all_queries)} queries across {len(stypes)} search types.{error_detail} "
                    "Try broadening the search terms or using different keywords."
                ),
                data=search_data,
            )

        message = (
            f"[WIDE RESEARCH] Completed research on '{topic}'\n"
            f"Found {len(all_items)} unique results from {len(all_queries)} queries "
            f"across {len(stypes)} search types.\n\n"
        )

        # Add result summaries to message for the LLM context
        for i, item in enumerate(all_items[:15], 1):
            message += f"{i}. [{item.title}]({item.link})\n   {item.snippet[:200]}\n\n"

        if errors:
            message += f"\n{len(errors)} queries had errors."

        if self._is_research_query(topic):
            message += (
                "\n\nVERIFICATION REQUIRED: These are search snippets only. "
                "Visit official pages to verify before making claims."
            )

        # Fire-and-forget: open top 3 results in browser for live preview visibility
        if self._browser and search_data:
            task = asyncio.create_task(self._browse_top_results(search_data, count=3))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            # Append system note to prevent LLM from re-navigating these same URLs
            message += (
                "\n\n[SYSTEM NOTE: Top search result URLs are being opened automatically in the browser. "
                "Do NOT call browser_navigate to these same URLs. Proceed to analyze the search snippets "
                "or use browser_get_content to read pages already opened.]"
            )

        return ToolResult(
            success=True,
            message=message,
            data=search_data,
        )
