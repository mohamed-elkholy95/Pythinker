import asyncio
import logging
import re
import time
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from app.core.config import get_settings
from app.domain.external.search import SearchEngine
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.external.browser import Browser

logger = logging.getLogger(__name__)


class SearchType(str, Enum):
    """Search intent types inspired by Manus AI.

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
    "best",
    "top",
    "good",
    "new",
    "latest",
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

    Inspired by Manus's query expansion which processes up to 3 variants
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
    searches will be performed visually in the browser (visible in VNC/sandbox viewer)
    instead of using the API-based search engine.
    """

    name: str = "search"

    # Class-level cache shared across instances
    _cache: ClassVar[dict[str, tuple[float, Any]]] = {}
    _cache_ttl: ClassVar[int] = 3600  # 1 hour cache TTL
    _cache_max_size: ClassVar[int] = 100  # Maximum cache entries

    def __init__(
        self,
        search_engine: SearchEngine,
        browser: "Browser | None" = None,
        max_observe: int | None = None,
    ):
        """Initialize search tool class

        Args:
            search_engine: Search engine service for API-based search
            browser: Optional browser instance for visual search (visible in VNC)
            max_observe: Optional custom observation limit (default: 8000)
        """
        super().__init__(max_observe=max_observe)
        self.search_engine = search_engine
        self._browser = browser

    def _should_use_browser_search(self) -> bool:
        """Check if browser-based search should be used.

        Returns True when:
        1. search_prefer_browser is enabled in settings
        2. A browser instance is available
        """
        settings = get_settings()
        return settings.search_prefer_browser and self._browser is not None

    async def _search_via_browser(self, query: str, date_range: str | None = None) -> ToolResult:
        """Perform search using browser navigation (visible in VNC/sandbox viewer).

        This navigates the browser to a search engine and extracts results,
        making the search visible to users in the sandbox viewer.

        Uses SearXNG if configured, otherwise falls back to DuckDuckGo (more reliable than Google).

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
            settings = get_settings()

            # Use SearXNG if configured (Docker internal URL), otherwise use DuckDuckGo
            # Google blocks automated access, so we avoid it
            if settings.searxng_url:
                # SearXNG search URL
                search_url = f"{settings.searxng_url}/search?q={quote(query)}&format=html"
                if date_range and date_range != "all":
                    # SearXNG time range
                    time_map = {
                        "past_day": "day",
                        "past_week": "week",
                        "past_month": "month",
                        "past_year": "year",
                    }
                    if date_range in time_map:
                        search_url += f"&time_range={time_map[date_range]}"
                logger.info(f"Browser search via SearXNG: {query}")
            else:
                # Fall back to DuckDuckGo (doesn't block automation as aggressively)
                search_url = f"https://duckduckgo.com/?q={quote(query)}"
                if date_range and date_range != "all":
                    # DuckDuckGo time range
                    time_map = {
                        "past_day": "d",
                        "past_week": "w",
                        "past_month": "m",
                        "past_year": "y",
                    }
                    if date_range in time_map:
                        search_url += f"&df={time_map[date_range]}"
                logger.info(f"Browser search via DuckDuckGo: {query}")

            logger.info(f"Browser search (visible in sandbox): {query}")

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
            content = view_result.message if view_result.message else ""

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
        """Get cached result if valid"""
        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Search cache hit for: {cache_key[:50]}")
                return data
            # Cache expired, remove it
            del self._cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: ToolResult) -> None:
        """Save result to cache with size limit enforcement"""
        # Evict oldest entries if cache is full
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

        self._cache[cache_key] = (time.time(), result)
        logger.debug(f"Search cached: {cache_key[:50]}")

    async def batch_search(
        self,
        queries: list[str],
        date_range: str | None = None,
        search_type: SearchType = SearchType.INFO,
        max_concurrent: int = 5,
    ) -> list[ToolResult]:
        """Execute multiple searches concurrently with caching

        Args:
            queries: List of search queries
            date_range: Optional time range filter
            search_type: Type of search to perform
            max_concurrent: Maximum concurrent searches

        Returns:
            List of search results in order
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_with_limit(query: str) -> ToolResult:
            async with semaphore:
                return await self._execute_typed_search(query, date_range, search_type)

        return await asyncio.gather(*[search_with_limit(q) for q in queries])

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

        # Use browser-based search if enabled (visible in VNC/sandbox viewer)
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

        # Execute API search
        result = await self.search_engine.search(query, date_range)
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

        Inspired by Manus's query expansion which processes up to 3 variants
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

        # Execute all variants concurrently
        results = await self.batch_search(variants, date_range, search_type)

        # Aggregate results
        all_items = []
        seen_urls = set()

        for result in results:
            if result.success and result.data:
                for item in result.data.results:
                    if item.link not in seen_urls:
                        seen_urls.add(item.link)
                        all_items.append(item)

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

        if self._is_research_query(query):
            message += (
                "\n\nVERIFICATION REQUIRED: These are search snippets only. "
                "For research/comparison tasks, you MUST visit official product pages "
                "to verify specifications before making claims."
            )

        return ToolResult(success=True, data=aggregated_data, message=message)

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

        Tries browser-based search first (visible in VNC), falls back to API search.

        Args:
            query: Search query, Google search style, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results
        """
        logger.info(f"Info search web: {query}")

        # Try browser-based search first (visible in VNC) if browser is available
        if self._browser:
            result = await self._search_via_browser(query, date_range)
            # Check if browser search succeeded AND has actual content
            if result.success and result.message:
                # Extract content after the header metadata
                content_parts = result.message.split("\n\n", 1)
                actual_content = content_parts[1] if len(content_parts) > 1 else ""
                if actual_content.strip():
                    return result
                # Browser search returned empty content, fall back to API
                logger.warning("Browser search returned empty content, falling back to API")
            else:
                # Browser search failed, fall back to API
                logger.warning(f"Browser search failed, falling back to API: {result.message}")

        # Fall back to API-based search directly (bypass browser search check)
        logger.info(f"Using API search for: {query}")
        result = await self.search_engine.search(query, date_range)
        result = self._add_verification_guidance(result, query)
        if result.success and result.message:
            result.message = f"[INFO SEARCH]\n{result.message}"
        elif result.success:
            result.message = "[INFO SEARCH]"
        return result

    # Legacy alias for backward compatibility
    async def web_search(self, query: str, date_range: str | None = None) -> ToolResult:
        """Legacy alias for info_search_web. Use info_search_web instead."""
        return await self.info_search_web(query, date_range)

    @tool(
        name="wide_research",
        description="""Execute comprehensive parallel research across multiple source types.

INSPIRED BY MANUS AI'S "MAP" CAPABILITY:
Divides research into homogeneous subtasks executed concurrently,
then aggregates and synthesizes results.

WHEN TO USE:
- Researching a topic from multiple angles
- Comparing information across different source types (web, news, academic)
- Validating claims with multiple sources
- Generating comprehensive research reports

FEATURES:
- Parallel search across multiple search types
- Query expansion for comprehensive coverage
- Result deduplication and relevance scoring
- Automatic synthesis with source citations

EXAMPLE:
wide_research(
    topic="AI agents comparison 2024",
    queries=["best AI agents", "AI agent comparison", "autonomous AI tools"],
    search_types=["info", "news", "academic"],
    aggregation="synthesize"
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
            "aggregation": {
                "type": "string",
                "enum": ["merge", "synthesize", "compare", "validate"],
                "description": "How to aggregate results: merge (combine), synthesize (summarize), compare (side-by-side), validate (cross-check)",
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
        aggregation: str = "synthesize",
        date_range: str | None = None,
    ) -> ToolResult:
        """Execute comprehensive parallel research.

        Inspired by Manus AI's "Map" capability for parallel research.

        Args:
            topic: Research topic or main question
            queries: List of search queries
            search_types: Types of sources to search
            aggregation: Aggregation strategy
            date_range: Time range filter

        Returns:
            Comprehensive research results with synthesis
        """
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

        # Generate all query-type combinations
        all_queries = []
        for query in queries:
            for stype in stypes:
                # Use query expansion for each
                variants = QueryExpander.expand(query, stype, max_variants=2)
                for variant in variants:
                    all_queries.append((variant, stype))

        logger.info(f"Wide research on '{topic}': {len(all_queries)} total queries across {len(stypes)} search types")

        # Execute all searches in parallel
        all_sources: list[dict] = []
        seen_urls: set[str] = set()
        errors: list[str] = []

        async def search_one(query_str: str, stype: SearchType) -> None:
            try:
                result = await self._execute_typed_search(query_str, date_range, stype)
                if result.success and result.data:
                    for item in result.data.results:
                        if item.link not in seen_urls:
                            seen_urls.add(item.link)
                            all_sources.append(
                                {
                                    "title": item.title,
                                    "url": item.link,
                                    "snippet": item.snippet,
                                    "query": query_str,
                                    "search_type": stype.value,
                                }
                            )
            except Exception as e:
                errors.append(f"{query_str}: {e}")

        # Run with concurrency limit
        semaphore = asyncio.Semaphore(5)

        async def search_with_limit(query_str: str, stype: SearchType) -> None:
            async with semaphore:
                await search_one(query_str, stype)

        await asyncio.gather(*[search_with_limit(q, st) for q, st in all_queries])

        # Aggregate results based on strategy
        aggregated = self._aggregate_wide_research(topic, all_sources, stypes, aggregation)

        # Build citations
        citations = [{"index": str(i), "title": s["title"], "url": s["url"]} for i, s in enumerate(all_sources[:30], 1)]

        message = (
            f"[WIDE RESEARCH] Completed research on '{topic}'\n"
            f"Found {len(all_sources)} unique sources from {len(all_queries)} queries."
        )

        if errors:
            message += f"\n{len(errors)} queries had errors."

        return ToolResult(
            success=True,
            message=message,
            data={
                "topic": topic,
                "total_sources": len(all_sources),
                "total_queries": len(all_queries),
                "search_types": [st.value for st in stypes],
                "aggregation": aggregation,
                "content": aggregated,
                "citations": citations,
                "sources": all_sources[:20],  # Limit for context
            },
        )

    def _aggregate_wide_research(
        self, topic: str, all_sources: list[dict], stypes: list[SearchType], aggregation: str
    ) -> str:
        """Aggregate wide research results based on strategy.

        Args:
            topic: Research topic
            all_sources: All collected sources
            stypes: Search types used
            aggregation: Aggregation strategy

        Returns:
            Aggregated content string
        """
        if aggregation == "merge":
            content_lines = [f"# Research: {topic}\n"]
            content_lines.append(f"Found {len(all_sources)} unique sources.\n\n")
            for i, src in enumerate(all_sources[:20], 1):
                content_lines.append(f"{i}. [{src['title']}]({src['url']})")
                content_lines.append(f"   {src['snippet'][:200]}...\n")
            return "\n".join(content_lines)

        if aggregation == "compare":
            by_type: dict[str, list[dict]] = {}
            for src in all_sources:
                st = src["search_type"]
                if st not in by_type:
                    by_type[st] = []
                by_type[st].append(src)

            content_lines = [f"# Research Comparison: {topic}\n"]
            for stype_key, sources in by_type.items():
                content_lines.append(f"\n## {stype_key.upper()} Sources ({len(sources)})\n")
                for src in sources[:5]:
                    content_lines.append(f"- [{src['title']}]({src['url']})")
            return "\n".join(content_lines)

        if aggregation == "validate":
            content_lines = [f"# Cross-Validation: {topic}\n"]
            content_lines.append(f"Analyzed {len(all_sources)} sources for fact verification.\n")

            word_count: dict[str, int] = {}
            for src in all_sources:
                words = set(src["snippet"].lower().split())
                for word in words:
                    if len(word) > 6:
                        word_count[word] = word_count.get(word, 0) + 1

            common_terms = sorted([(w, c) for w, c in word_count.items() if c >= 3], key=lambda x: x[1], reverse=True)[
                :10
            ]

            content_lines.append("\n## Common Themes\n")
            for term, count in common_terms:
                content_lines.append(f"- '{term}' mentioned in {count} sources")

            content_lines.append("\n## Top Sources\n")
            for src in all_sources[:10]:
                content_lines.append(f"- [{src['title']}]({src['url']})")
            return "\n".join(content_lines)

        # synthesize (default)
        content_lines = [f"# Research Synthesis: {topic}\n"]
        content_lines.append(f"Synthesized from {len(all_sources)} sources across {len(stypes)} search types.\n")

        content_lines.append("\n## Key Findings\n")
        for i, src in enumerate(all_sources[:10], 1):
            content_lines.append(f"### {i}. {src['title']}")
            content_lines.append(f"Source: [{src['search_type']}]({src['url']})")
            first_sentence = src["snippet"].split(".")[0] + "."
            content_lines.append(f"> {first_sentence}\n")

        content_lines.append("\n## Sources\n")
        for i, src in enumerate(all_sources[:15], 1):
            content_lines.append(f"{i}. [{src['title']}]({src['url']})")

        return "\n".join(content_lines)
