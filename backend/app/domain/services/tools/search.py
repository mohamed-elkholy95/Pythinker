import asyncio
import logging
import re
import time
from typing import Any

from app.domain.external.search import SearchEngine
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)

# Common stopwords to remove for query normalization
STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "about", "also",
    "and", "or", "but", "if", "what", "which", "who", "whom", "this",
    "that", "these", "those", "am", "i", "you", "he", "she", "it", "we",
    "they", "my", "your", "his", "her", "its", "our", "their", "me",
    "him", "us", "them", "best", "top", "good", "new", "latest"
}

# Domains that are typically authoritative sources
AUTHORITATIVE_DOMAINS = [
    # Manufacturer/official sites
    ".com/products", "/product/", "/specs", "/specifications",
    # Review sites
    "wirecutter.com", "rtings.com", "tomshardware.com", "techradar.com",
    "theverge.com", "arstechnica.com", "anandtech.com",
    # Documentation
    "docs.", "documentation", "manual",
]

# Keywords that suggest a research/comparison task
RESEARCH_KEYWORDS = ["best", "compare", "vs", "versus", "review", "recommend", "alternative"]


class SearchTool(BaseTool):
    """Search tool class, providing search engine interaction functions with caching"""

    name: str = "search"

    # Class-level cache shared across instances
    _cache: dict[str, tuple[float, Any]] = {}
    _cache_ttl: int = 3600  # 1 hour cache TTL
    _cache_max_size: int = 100  # Maximum cache entries

    def __init__(self, search_engine: SearchEngine, max_observe: int | None = None):
        """Initialize search tool class

        Args:
            search_engine: Search engine service
            max_observe: Optional custom observation limit (default: 8000)
        """
        super().__init__(max_observe=max_observe)
        self.search_engine = search_engine

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
        normalized = re.sub(r'[^\w\s-]', ' ', normalized)

        # Split into words
        words = normalized.split()

        # Remove stopwords and short words
        words = [w for w in words if w not in STOPWORDS and len(w) > 1]

        # Sort alphabetically for order-independent matching
        words.sort()

        # Join back
        return ' '.join(words)

    def _get_cache_key(self, query: str, date_range: str | None = None) -> str:
        """Generate cache key from normalized query parameters.

        Uses semantic normalization to catch equivalent queries.
        """
        normalized = self._normalize_query(query)
        return f"{normalized}:{date_range or 'all'}"

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
        max_concurrent: int = 5
    ) -> list[ToolResult]:
        """Execute multiple searches concurrently with caching

        Args:
            queries: List of search queries
            date_range: Optional time range filter
            max_concurrent: Maximum concurrent searches

        Returns:
            List of search results in order
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_with_limit(query: str) -> ToolResult:
            async with semaphore:
                return await self.info_search_web(query, date_range)

        return await asyncio.gather(*[search_with_limit(q) for q in queries])

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
        description="""Search web pages using search engine. Use for obtaining latest information or finding references.

IMPORTANT: Search snippets are NOT valid sources for factual claims.
For research/comparison tasks, you MUST visit the returned URLs to verify information.
Priority: Official product pages > Review sites (Wirecutter, RTINGS) > Forums

RECENCY BEST PRACTICES:
- For products/reviews/prices: Use date_range="past_month" or "past_year"
- Add current year (2025/2026) to queries for time-sensitive topics
- For technology/software: Always filter to recent results
- For evergreen topics (history, concepts): "all" is acceptable""",
        parameters={
            "query": {
                "type": "string",
                "description": "Search query in Google search style, using 3-5 keywords. Include current year for time-sensitive topics."
            },
            "date_range": {
                "type": "string",
                "enum": ["all", "past_hour", "past_day", "past_week", "past_month", "past_year"],
                "description": "Time range filter. RECOMMENDED: Use 'past_month' or 'past_year' for products, reviews, prices, or any time-sensitive information."
            }
        },
        required=["query"]
    )
    async def info_search_web(
        self,
        query: str,
        date_range: str | None = None
    ) -> ToolResult:
        """Search webpages using search engine with caching

        Args:
            query: Search query, Google search style, using 3-5 keywords
            date_range: (Optional) Time range filter for search results

        Returns:
            Search results with verification guidance for research queries
        """
        # Check cache first
        cache_key = self._get_cache_key(query, date_range)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # Execute search
        result = await self.search_engine.search(query, date_range)
        result = self._add_verification_guidance(result, query)

        # Cache successful results
        if result.success:
            self._save_to_cache(cache_key, result)

        return result
