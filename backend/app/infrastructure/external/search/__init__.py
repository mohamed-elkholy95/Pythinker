"""Search Engine Infrastructure

Provides search engine implementations and factory for dynamic provider selection.

Supported providers:
- bing: Bing web search (default, no API key required)
- google: Google Custom Search API (requires API key)
- baidu: Baidu web search
- searxng: SearXNG metasearch engine
- duckduckgo: DuckDuckGo search (privacy-focused)
- brave: Brave Search API (requires API key)
"""
from functools import lru_cache
from typing import Optional
import logging

from app.domain.external.search import SearchEngine
from app.infrastructure.external.search.factory import (
    SearchProviderRegistry,
    get_search_engine_from_factory,
)

logger = logging.getLogger(__name__)


@lru_cache()
def get_search_engine() -> Optional[SearchEngine]:
    """Get search engine instance based on configuration.

    Uses the SearchProviderRegistry to dynamically select and instantiate
    the appropriate search engine based on SEARCH_PROVIDER setting.

    Returns:
        SearchEngine instance or None if configuration is invalid
    """
    return get_search_engine_from_factory()


__all__ = [
    "get_search_engine",
    "SearchProviderRegistry",
]