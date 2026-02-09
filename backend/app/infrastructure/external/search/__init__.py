"""Search Engine Infrastructure

Provides search engine implementations and factory for dynamic provider selection.

Supported providers:
- duckduckgo: DuckDuckGo search (default, privacy-focused, no API key required)
- bing: Bing web search (no API key required)
- google: Google Custom Search API (requires API key)
- brave: Brave Search API (requires API key)
- tavily: Tavily AI Search API (requires API key)
- serper: Serper.dev Google Search API (requires API key)
"""

import logging
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


@lru_cache
def get_search_engine() -> SearchEngine | None:
    """Get search engine instance based on configuration.

    Uses the SearchProviderRegistry to dynamically select and instantiate
    the appropriate search engine based on SEARCH_PROVIDER setting.

    Returns:
        SearchEngine instance or None if configuration is invalid
    """
    return get_search_engine_from_factory()


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
