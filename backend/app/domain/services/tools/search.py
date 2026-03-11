import asyncio
import ipaddress
import logging
import re
import socket
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlsplit, urlunsplit

from app.domain.external.search import SearchEngine
from app.domain.models.event import ToolProgressEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.external.browser import Browser
    from app.domain.external.scraper import Scraper

logger = logging.getLogger(__name__)

# Domains that block anonymous scraping or require OAuth/API access.
# Search snippets are preserved for these URLs — no spider enrichment.
_SPIDER_DENYLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "reddit.com",  # Responsible Builder Policy — requires OAuth
        "x.com",  # Aggressive bot blocking
        "twitter.com",  # Legacy domain for x.com
        "instagram.com",  # Login wall, returns UI boilerplate only
        "facebook.com",  # Login wall, no useful anonymous content
        "tiktok.com",  # Video platform, no text content for research
        "linkedin.com",  # Login wall, aggressive bot blocking
        "pinterest.com",  # Login wall, image-only platform
    }
)


def _should_skip_spider(url: str) -> bool:
    """Check if URL should be skipped by the spider (domain denylist)."""
    try:
        hostname = urlparse(url).hostname or ""
        hostname = hostname.removeprefix("www.")
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _SPIDER_DENYLIST_DOMAINS)
    except Exception:
        return False


_BLOCKED_IP_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private (ULA)
]


def _is_pdf_url(url: str) -> bool:
    """Check if URL points to a PDF file (by extension)."""
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _validate_fetch_url(url: str) -> bool:
    """Return False if URL resolves to a blocked/private IP range (SSRF protection).

    Only allows http and https schemes. Resolves the hostname and checks
    all returned IP addresses against blocked network ranges.

    Args:
        url: URL to validate before fetching

    Returns:
        True if safe to fetch, False if blocked
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        resolved = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if any(ip in net for net in _BLOCKED_IP_NETWORKS):
                logger.warning("SSRF blocked: %s resolved to %s", url, ip)
                return False
    except Exception:
        return False
    return True


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


def canonicalize_query(query: str) -> str:
    """Normalize search query for stable, collision-resistant cache keys.

    Normalizations applied:
    - Strip leading/trailing whitespace
    - Lowercase
    - Collapse internal whitespace runs to single space

    Examples:
        "  Hello   World  " -> "hello world"
        "Python FastAPI" -> "python fastapi"
    """
    return re.sub(r"\s+", " ", query.strip().lower())


# ---------------------------------------------------------------------------
# In-process hot cache — burst absorber (30s TTL, max 50 entries)
# Absorbs duplicate/near-duplicate queries within a single task burst.
# ---------------------------------------------------------------------------
_HOT_CACHE_TTL: float = 30.0
_HOT_CACHE_MAXSIZE: int = 50
_PROGRESS_QUEUE_MAX_SIZE = 256
# Dict keyed by canonical_query -> (result, expiry_monotonic_time)
_hot_cache: dict[str, tuple[object, float]] = {}


def _hot_cache_get(key: str) -> object | None:
    """Return cached result if not expired, else None."""
    entry = _hot_cache.get(key)
    if entry is None:
        return None
    result, expiry = entry
    if time.monotonic() < expiry:
        return result
    del _hot_cache[key]
    return None


def _hot_cache_set(key: str, value: object, ttl: float = _HOT_CACHE_TTL) -> None:
    """Store result with TTL. Evicts oldest entry if at capacity."""
    if len(_hot_cache) >= _HOT_CACHE_MAXSIZE:
        # Evict the oldest entry (dict preserves insertion order in Python 3.7+)
        oldest = next(iter(_hot_cache))
        del _hot_cache[oldest]
    _hot_cache[key] = (value, time.monotonic() + ttl)


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
    supports_progress: bool = True

    _cache_ttl: ClassVar[int] = 3600  # 1 hour cache TTL
    _cache_max_size: ClassVar[int] = 100  # Maximum cache entries
    _preview_url_cache_max_size: ClassVar[int] = 200
    # Keep reserve for follow-up verification after wide research bursts.
    _WIDE_RESEARCH_FOLLOWUP_RESERVE_CALLS: ClassVar[int] = 2
    _QUOTA_ERROR_MARKERS: ClassVar[tuple[str, ...]] = (
        "not enough credits",
        "quota",
        "rate limit",
        "exhausted",
    )
    _tracking_query_params: ClassVar[set[str]] = {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "ref",
        "ref_src",
        "source",
        "sourceid",
    }
    # prevent GC of fire-and-forget browse tasks
    _background_tasks: ClassVar[set[asyncio.Task[None]]] = set()

    @classmethod
    def _handle_background_task_done(cls, task: asyncio.Task[None]) -> None:
        """Remove finished task from the GC-prevention set and retrieve any exception.

        Without calling ``task.exception()``, asyncio logs a noisy
        "Task exception was never retrieved" warning for every Playwright
        navigation that gets cancelled or hits ``net::ERR_ABORTED``.
        """
        cls._background_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc:
                logger.debug("Background browse task raised (non-critical): %s", exc)

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
        complexity_score: float | None = None,
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
        # Track the current browse task so we can cancel it before spawning a new one
        self._current_browse_task: asyncio.Task[None] | None = None
        # Serialize background browse task replacement to avoid races when
        # multiple search calls complete at nearly the same time.
        self._browse_task_lock = asyncio.Lock()
        # Instance-level cache with O(1) LRU eviction
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        # Session-scoped LRU set of URLs already shown in live preview.
        self._previewed_result_urls: OrderedDict[str, float] = OrderedDict()
        # URLs currently being previewed by background tasks. Prevents duplicate
        # navigation when multiple search calls race.
        self._previewing_result_urls: set[str] = set()
        self._progress_queue: asyncio.Queue[ToolProgressEvent] = asyncio.Queue(
            maxsize=_PROGRESS_QUEUE_MAX_SIZE,
        )
        self._active_tool_call_id: str = ""
        self._active_function_name: str = ""
        self._start_time: float = 0.0

        # Budget enforcement (per-task, since SearchTool is instantiated per task)
        from app.core.config import get_settings

        settings = get_settings()
        self._budget = self._BudgetTracker(
            max_api_calls=settings.max_search_api_calls_per_task,
            max_wide_research=settings.max_wide_research_calls_per_task,
        )
        self._max_wide_queries = settings.max_wide_research_queries
        self._complexity_score = complexity_score
        self._effective_max_wide_queries = (
            settings.max_wide_research_queries_complex
            if complexity_score is not None and complexity_score >= 0.8
            else settings.max_wide_research_queries
        )
        self._dedup_skip = settings.search_dedup_skip_existing

        # Quota manager integration (feature-flagged, zero behavior change when disabled)
        self._quota_manager = None
        if getattr(settings, "search_quota_manager_enabled", False):
            try:
                from app.domain.services.search.quota_manager import get_search_quota_manager

                self._quota_manager = get_search_quota_manager()
                logger.info("SearchQuotaManager enabled — credit-optimized routing active")
            except Exception as e:
                logger.warning("Failed to initialize SearchQuotaManager: %s", e)

        # Consecutive dedup rejection counter: escalates the rejection message
        # so the LLM stops retrying with slight query variations
        self._consecutive_dedup_rejections = 0

        # Cache for pre-planning search results.  When the planner ran
        # pre-planning web searches, the execution agent propagates the
        # context here so that dedup-blocked queries can return cached
        # results instead of failing with 0 results.
        self._pre_planning_context: str | None = None

    def _reset_progress_queue(self) -> None:
        """Clear stale progress events from previous tool invocations."""
        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _begin_progress_run(self) -> None:
        """Initialize progress state for a top-level search tool call."""
        self._reset_progress_queue()
        self._start_time = time.monotonic()

    def _enqueue_progress(
        self,
        *,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a ToolProgressEvent for durable timeline/replay history."""
        percent = min(99, int(steps_completed / steps_total * 100)) if steps_total and steps_total > 0 else 0
        elapsed_ms = (time.monotonic() - self._start_time) * 1000 if self._start_time else 0
        event = ToolProgressEvent(
            tool_call_id=self._active_tool_call_id,
            tool_name=self.name,
            function_name=self._active_function_name,
            progress_percent=percent,
            current_step=current_step,
            steps_completed=steps_completed,
            steps_total=steps_total,
            elapsed_ms=elapsed_ms,
            checkpoint_data=checkpoint_data,
        )
        try:
            self._progress_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("Search progress queue full, dropping event: %s", current_step)

    async def drain_progress_events(self) -> AsyncGenerator[ToolProgressEvent, None]:
        """Drain queued progress events for SSE delivery."""
        while not self._progress_queue.empty():
            try:
                yield self._progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def set_complexity_score(self, score: float | None) -> None:
        """Update complexity score after construction."""
        self._complexity_score = score
        from app.core.config import get_settings

        settings = get_settings()
        self._effective_max_wide_queries = (
            settings.max_wide_research_queries_complex
            if score is not None and score >= 0.8
            else settings.max_wide_research_queries
        )

    async def _schedule_background_preview(self, search_data: Any, count: int = 3) -> None:
        """Schedule at most one fire-and-forget preview task for top search URLs.

        This method centralizes task lifecycle management so concurrent calls to
        info_search_web/wide_research don't race and leave orphan browse tasks.
        """
        if not self._browser or not search_data:
            return

        if hasattr(self._browser, "allow_background_browsing"):
            self._browser.allow_background_browsing()

        async with self._browse_task_lock:
            if self._current_browse_task and not self._current_browse_task.done():
                self._current_browse_task.cancel()
            task = asyncio.create_task(self._browse_top_results(search_data, count=count))
            self._current_browse_task = task
            self._background_tasks.add(task)
            task.add_done_callback(self._handle_background_task_done)

    async def _auto_enrich_results(self, search_data: Any) -> int:
        """Enrich top-K search result snippets with full page content via scraper.

        Mirrors the spider enrichment pattern from wide_research but applies
        to info_search_web results.  Replaces ~200-char search snippets with
        ~2000-char page excerpts so the LLM has grounded content without
        needing to call browser_navigate manually.

        Returns the number of successfully enriched results.
        """
        if not self._scraper or not search_data:
            return 0

        from app.core.config import get_settings as _get_settings

        settings = _get_settings()
        if not settings.search_auto_enrich_enabled:
            return 0

        top_k = settings.search_auto_enrich_top_k
        max_snippet = settings.search_auto_enrich_snippet_chars

        # Extract items from SearchResults or raw list
        items = search_data.results if hasattr(search_data, "results") else search_data
        if not items:
            return 0

        candidates = [
            item.link
            for item in items[:top_k]
            if item.link and not _is_pdf_url(item.link) and not _should_skip_spider(item.link)
        ]
        if not candidates:
            return 0

        logger.info(
            "Auto-enriching %d/%d search result URLs",
            len(candidates),
            min(top_k, len(items)),
        )

        try:
            fetched = await self._scraper.fetch_batch(candidates)
            url_to_content = {r.url: r for r in fetched if r.success and len(r.text) > 200}
            for item in items:
                if item.link in url_to_content:
                    r = url_to_content[item.link]
                    item.snippet = r.text[:max_snippet]
                    if r.title and not item.title:
                        item.title = r.title
            enriched_count = len(url_to_content)
            logger.info("Auto-enriched %d/%d URLs for info_search_web", enriched_count, len(candidates))
            return enriched_count
        except Exception as exc:
            logger.warning("Auto-enrichment failed: %s", exc)
            return 0

    @classmethod
    def _is_tracking_query_param(cls, key: str) -> bool:
        key_lower = key.lower()
        return key_lower.startswith("utm_") or key_lower in cls._tracking_query_params

    @classmethod
    def _normalize_preview_url(cls, url: str) -> str:
        """Normalize URL for live-preview deduplication."""
        stripped = url.strip()
        if not stripped:
            return stripped

        parsed = urlsplit(stripped)
        if not parsed.netloc:
            return stripped.split("#", 1)[0].rstrip("/").lower()

        scheme = (parsed.scheme or "https").lower()
        # Treat http/https as the same target page to suppress scheme-only duplicates.
        if scheme in {"http", "https"}:
            scheme = "https"

        host = (parsed.hostname or "").lower()
        port = parsed.port
        netloc = (f"{host}:{port}" if port and port not in {80, 443} else host) if host else parsed.netloc.lower()

        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")

        filtered_query = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if not cls._is_tracking_query_param(k)
        ]
        filtered_query.sort(key=lambda item: (item[0].lower(), item[1]))
        query = urlencode(filtered_query, doseq=True)
        return urlunsplit((scheme, netloc, path, query, ""))

    def _mark_previewed_url(self, normalized_url: str) -> None:
        self._previewed_result_urls[normalized_url] = time.time()
        self._previewed_result_urls.move_to_end(normalized_url)
        while len(self._previewed_result_urls) > self._preview_url_cache_max_size:
            self._previewed_result_urls.popitem(last=False)

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

        # Quota-aware degradation: fallback to browser search when API credits are exhausted.
        if not result.success and self._browser is not None and self._is_quota_exhaustion_error(result.message):
            logger.warning(
                "Search API quota exhaustion detected for query '%s'; attempting browser fallback",
                query[:120],
            )
            fallback = await self._search_via_browser(query, date_range)
            if fallback.success:
                prefix = f"[{search_type.value.upper()} SEARCH via BROWSER FALLBACK]"
                fallback.message = f"{prefix}\n{fallback.message}" if fallback.message else prefix
                result = fallback
            else:
                result = ToolResult(
                    success=False,
                    message=(
                        f"{result.message or 'Search provider quota exhausted'}; "
                        f"browser fallback failed: {fallback.message or 'unknown browser error'}"
                    ),
                    data=result.data or fallback.data,
                )

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

        # Feed result URLs to URL failure guard for alternative suggestions
        if all_items:
            try:
                guard = getattr(self, "_url_failure_guard", None)
                if guard:
                    result_urls = [item.link for item in all_items if item.link]
                    guard.record_search_results(result_urls)
                    logger.debug("Fed %d search result URLs to URL failure guard", len(result_urls))
            except Exception as _guard_err:
                logger.debug("Failed to feed search URLs to guard: %s", _guard_err)

        return ToolResult(success=True, data=aggregated_data, message=message)

    async def _browse_top_results(
        self,
        search_data: Any,
        count: int = 3,
        *,
        emit_progress: bool = False,
        progress_query: str | None = None,
        progress_step_offset: int = 0,
        progress_total_steps: int | None = None,
        dwell_seconds: float = 5.0,
    ) -> None:
        """Open top search result URLs in the browser for live preview visibility.

        After API search returns results, navigates to the top URLs so the user
        can see browsing activity in the sandbox live preview. This runs as a
        fire-and-forget background task by default, or synchronously when the
        caller wants those pages captured in session replay history.

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

            candidate_urls: list[tuple[str, str]] = []
            seen_this_batch: set[str] = set()
            skipped_already_previewed = 0
            reserved_urls: set[str] = set()
            for item in items:
                url = getattr(item, "link", None) or (item.get("link") if isinstance(item, dict) else None)
                if not url:
                    continue
                normalized_url = self._normalize_preview_url(url)
                if normalized_url in seen_this_batch:
                    continue
                seen_this_batch.add(normalized_url)
                if normalized_url in self._previewed_result_urls or normalized_url in self._previewing_result_urls:
                    skipped_already_previewed += 1
                    continue
                candidate_urls.append((url, normalized_url))
                self._previewing_result_urls.add(normalized_url)
                reserved_urls.add(normalized_url)
                if len(candidate_urls) >= count:
                    break

            if not candidate_urls:
                if skipped_already_previewed:
                    logger.info(
                        "_browse_top_results: skipped %d URLs already shown in live preview",
                        skipped_already_previewed,
                    )
                return

            logger.info(
                "Browsing top %d search results for live preview visibility (%d already shown skipped)",
                len(candidate_urls),
                skipped_already_previewed,
            )
            consecutive_failures = 0
            total_failures = 0
            max_consecutive_failures = max(3, min(5, len(candidate_urls)))
            max_total_failures = max(4, min(8, len(candidate_urls) + 1))
            navigation_timeout_seconds = 20.0
            preview_total_steps = progress_total_steps or (progress_step_offset + len(candidate_urls))
            for preview_index, (url, normalized_url) in enumerate(candidate_urls, start=1):
                # Check if a foreground browser operation cancelled us
                if getattr(self._browser, "_background_browse_cancelled", False):
                    logger.debug("_browse_top_results: cancelled by foreground browser operation")
                    break
                if emit_progress:
                    progress_step = progress_step_offset + preview_index
                    self._enqueue_progress(
                        current_step=f"Previewing result {preview_index} of {len(candidate_urls)}: {url}",
                        steps_completed=progress_step,
                        steps_total=preview_total_steps,
                        checkpoint_data={
                            "action": "navigate",
                            "action_function": "browser_navigate",
                            "url": url,
                            "index": preview_index,
                            "query": progress_query,
                            "step": progress_step,
                            "command_category": "browse",
                        },
                    )
                navigation_succeeded = False
                try:
                    if hasattr(self._browser, "navigate_for_display"):
                        success = await asyncio.wait_for(
                            self._browser.navigate_for_display(url),
                            timeout=navigation_timeout_seconds,
                        )
                        if not success:
                            consecutive_failures += 1
                            total_failures += 1
                        else:
                            consecutive_failures = 0
                            navigation_succeeded = True
                    else:
                        nav_result = await asyncio.wait_for(
                            self._browser.navigate(url),
                            timeout=navigation_timeout_seconds,
                        )
                        if nav_result.success:
                            consecutive_failures = 0
                            navigation_succeeded = True
                        else:
                            consecutive_failures += 1
                            total_failures += 1
                    # Dwell only on successful navigation so failures do not stall
                    # preview progression.
                    if navigation_succeeded:
                        await asyncio.sleep(dwell_seconds)
                    elif consecutive_failures:
                        await asyncio.sleep(min(1.5, 0.5 * consecutive_failures))
                except Exception as e:
                    consecutive_failures += 1
                    total_failures += 1
                    logger.debug(f"Failed to browse {url}: {e}")
                    await asyncio.sleep(min(1.5, 0.5 * consecutive_failures))
                finally:
                    self._previewing_result_urls.discard(normalized_url)
                    if navigation_succeeded:
                        self._mark_previewed_url(normalized_url)

                if consecutive_failures >= max_consecutive_failures or total_failures >= max_total_failures:
                    logger.info(
                        "_browse_top_results: stopping early after failures (consecutive=%d/%d, total=%d/%d)",
                        consecutive_failures,
                        max_consecutive_failures,
                        total_failures,
                        max_total_failures,
                    )
                    break
            # Cleanup any URLs reserved but never reached because of cancellation
            # or early stop.
            for normalized_url in reserved_urls:
                self._previewing_result_urls.discard(normalized_url)
        except asyncio.CancelledError:
            logger.debug("_browse_top_results: cancelled by newer browse task")
        except Exception as e:
            logger.debug(f"_browse_top_results error (non-critical): {e}")

    def _is_research_query(self, query: str) -> bool:
        """Check if query indicates a research task"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in RESEARCH_KEYWORDS)

    @classmethod
    def _is_quota_exhaustion_error(cls, message: str | None) -> bool:
        if not message:
            return False
        lowered = message.lower()
        return any(marker in lowered for marker in cls._QUOTA_ERROR_MARKERS)

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
        self._begin_progress_run()
        self._enqueue_progress(
            current_step=f"Searching web for '{query}'",
            steps_completed=1,
            steps_total=4,
            checkpoint_data={
                "action": "search",
                "action_function": "info_search_web",
                "query": query,
                "step": 1,
                "command_category": "search",
            },
        )

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

        # Quota manager routing (feature-flagged, falls back to default on any error)
        if self._quota_manager is not None:
            try:
                result = await self._quota_manager.route(query, self.search_engine)
                if not result.success:
                    return result
                # Count against per-task budget
                self._budget.record_api_call()
                return result
            except Exception as e:
                logger.warning("QuotaManager route failed, falling back to default: %s", e)

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
                from app.domain.models.search import SearchResultItem, SearchResults

                # Parse pre-planning context into structured results for the
                # frontend live view.  Format: "- [Title](url): Snippet"
                cached_items: list[SearchResultItem] = []
                for line in self._pre_planning_context.splitlines():
                    line = line.strip()
                    if not line.startswith("- "):
                        continue
                    m = re.match(r"^- \[(.+?)\]\((.+?)\)(?::\s*(.*))?$", line)
                    if m:
                        cached_items.append(
                            SearchResultItem(
                                title=m.group(1),
                                link=m.group(2),
                                snippet=m.group(3) or "",
                            )
                        )

                return ToolResult(
                    success=True,
                    message=(f"Results for '{query}' (from pre-planning search):\n\n{self._pre_planning_context}"),
                    data=SearchResults(
                        query=query,
                        date_range=date_range,
                        total_results=len(cached_items),
                        results=cached_items,
                    ),
                )

            self._consecutive_dedup_rejections += 1
            logger.info(
                f"Skipping duplicate search (dedup_skip=True, "
                f"consecutive={self._consecutive_dedup_rejections}): {query}"
            )
            from app.domain.models.search import SearchResults

            # Escalating rejection message: gentle → firm → hard-stop
            if self._consecutive_dedup_rejections >= 3:
                msg = (
                    f"STOP SEARCHING. You have attempted {self._consecutive_dedup_rejections} "
                    f"duplicate searches in a row. All variations of this query have already "
                    f"been executed. You MUST proceed with the information you already have. "
                    f"Do NOT call any search tool again — synthesize your answer from "
                    f"existing results and move to the next step."
                )
            elif self._consecutive_dedup_rejections >= 2:
                msg = (
                    f"Already searched: '{query}'. This is the {self._consecutive_dedup_rejections}th "
                    f"consecutive duplicate. You have sufficient search results — proceed with "
                    f"writing your answer using the information already gathered. Do not search again."
                )
            else:
                msg = f"Already searched: '{query}'. Use different keywords for new results."

            return ToolResult(
                success=False,
                message=msg,
                data=SearchResults(query=query, date_range=date_range),
            )

        # Query is new (passed dedup check) — reset consecutive rejection counter
        self._consecutive_dedup_rejections = 0

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

        # Auto-enrich search results with full page content (model-agnostic)
        enriched_count = 0
        if result.success and result.data and self._scraper:
            enriched_count = await self._auto_enrich_results(result.data)

        # Preview top results in-band so the visited pages are preserved in
        # live view, replay, and the persisted session timeline.
        if result.success and self._browser and result.data:
            await self._browse_top_results(
                result.data,
                count=3,
                emit_progress=True,
                progress_query=query,
                progress_step_offset=1,
                progress_total_steps=4,
                dwell_seconds=1.5,
            )

        # Append contextual guidance based on enrichment status
        if result.success and result.data:
            if enriched_count > 0:
                result.message = (
                    (result.message or "")
                    + f"\n\n[SYSTEM NOTE: {enriched_count} search results above have been enriched "
                    "with full page content (~2000 chars each). These enriched snippets provide initial "
                    "content. For comprehensive research, use browser_navigate to visit the most promising "
                    "URLs for full page content, detailed data, and information beyond snippets.]"
                )
            elif self._browser:
                result.message = (
                    (result.message or "") + "\n\n[SYSTEM NOTE: Search results contain brief snippets only. "
                    "Top result pages were previewed in the sandbox browser and recorded in the session timeline. "
                    "IMPORTANT: Use browser_navigate to visit the top 3-5 most relevant URLs from "
                    "these results to gather detailed information for your research.]"
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

        self._begin_progress_run()
        self._enqueue_progress(
            current_step=f"Running wide research for '{topic}'",
            steps_completed=1,
            steps_total=4,
            checkpoint_data={
                "action": "search",
                "action_function": "wide_research",
                "query": topic,
                "step": 1,
                "command_category": "search",
            },
        )

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

        # Clamp queries list to configured maximum (complexity-aware)
        if len(queries) > self._effective_max_wide_queries:
            logger.warning(
                "Wide research queries clamped: %d → %d (complexity=%s)",
                len(queries),
                self._effective_max_wide_queries,
                self._complexity_score,
            )
            queries = queries[: self._effective_max_wide_queries]

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
        remaining = max(0, self._budget.remaining() - self._WIDE_RESEARCH_FOLLOWUP_RESERVE_CALLS)
        if len(all_queries) > remaining:
            logger.warning(f"Wide research queries trimmed to budget: {len(all_queries)} → {remaining}")
            all_queries = all_queries[:remaining]

        if not all_queries:
            return ToolResult(
                success=False,
                message=(
                    f"[WIDE RESEARCH] Insufficient search budget for '{topic}'. "
                    f"Reserved {self._WIDE_RESEARCH_FOLLOWUP_RESERVE_CALLS} API calls for follow-up verification."
                ),
                data=SearchResults(query=topic, date_range=date_range),
            )

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
                spider_candidates = [
                    item.link for item in all_items[:top_k] if item.link and not _is_pdf_url(item.link)
                ]
                denied_count = sum(1 for u in spider_candidates if _should_skip_spider(u))
                top_urls = [u for u in spider_candidates if not _should_skip_spider(u)]
                if denied_count:
                    logger.info("Skipped %d denied-domain URL(s) from spider enrichment", denied_count)
                if top_urls:
                    logger.info(
                        "Spider-enriching %d URLs for wide_research on '%s'",
                        len(top_urls),
                        topic,
                    )
                    try:
                        fetched = await self._scraper.fetch_batch(top_urls)
                        url_to_content = {r.url: r for r in fetched if r.success and len(r.text) > 200}
                        for item in all_items:
                            if item.link in url_to_content:
                                r = url_to_content[item.link]
                                item.snippet = r.text[:2000]
                                if r.title and not item.title:
                                    item.title = r.title
                        logger.info("Spider enriched %d/%d URLs", len(url_to_content), len(top_urls))
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

        # Preview top results in-band so those browser pages are replayable.
        if self._browser and search_data:
            await self._browse_top_results(
                search_data,
                count=3,
                emit_progress=True,
                progress_query=topic,
                progress_step_offset=1,
                progress_total_steps=4,
                dwell_seconds=1.5,
            )

            # Append system note to guide LLM on browser navigation after preview
            message += (
                "\n\n[SYSTEM NOTE: Top search result URLs were previewed in the sandbox browser "
                "and recorded in the session timeline. You may still use browser_navigate for "
                "interactive exploration or to visit pages that need deeper inspection beyond "
                "what snippets provide.]"
            )

        return ToolResult(
            success=True,
            message=message,
            data=search_data,
        )
