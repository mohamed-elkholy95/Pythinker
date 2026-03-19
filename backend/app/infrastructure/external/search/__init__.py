"""Search Engine Infrastructure

Provides search engine implementations and factory for dynamic provider selection.

Supported providers:
- duckduckgo: DuckDuckGo search (default, privacy-focused, no API key required)
- bing: Bing web search (no API key required)
- google: Google Custom Search API (requires API key)
- brave: Brave Search API (requires API key)
- tavily: Tavily AI Search API (requires API key)
- serper: Serper.dev Google Search API (requires API key)
- exa: Exa semantic search API (requires API key)
- jina: Jina Search Foundation API (requires API key)
"""

import logging
import threading
from functools import lru_cache

from app.domain.external.search import SearchEngine
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType
from app.infrastructure.external.search.factory import (
    SearchProviderRegistry,
    get_search_engine_from_factory,
)
from app.infrastructure.external.search.utils import (
    clean_redirect_url,
    extract_domain,
    extract_text_from_tag,
    find_snippet_from_patterns,
    normalize_url,
    parse_result_count,
    sanitize_query,
)

logger = logging.getLogger(__name__)


_get_search_engine_init_lock = threading.Lock()


@lru_cache
def get_search_engine() -> SearchEngine | None:
    """Get search engine instance based on configuration.

    Uses the SearchProviderRegistry to dynamically select and instantiate
    the appropriate search engine based on SEARCH_PROVIDER setting.

    Returns:
        SearchEngine instance or None if configuration is invalid
    """
    with _get_search_engine_init_lock:
        return get_search_engine_from_factory()


async def shutdown_search_engine() -> None:
    """Close the cached search engine and clear the cache."""
    engine = get_search_engine()
    if engine is not None and hasattr(engine, "close"):
        try:
            await engine.close()
            logger.info("Search engine client closed")
        except Exception as e:
            logger.debug("Error closing search engine: %s", e)
    get_search_engine.cache_clear()


__all__ = [
    "SearchEngineBase",
    "SearchEngineType",
    "SearchProviderRegistry",
    "clean_redirect_url",
    "extract_domain",
    "extract_text_from_tag",
    "find_snippet_from_patterns",
    "get_search_engine",
    "normalize_url",
    "parse_result_count",
    "sanitize_query",
]
