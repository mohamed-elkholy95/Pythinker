"""Search Provider Factory

Registry pattern for dynamically selecting search providers based on configuration.
Supports: bing, google, duckduckgo, brave, tavily, serper
"""

import importlib
import logging
from typing import ClassVar

from app.core.config import get_settings
from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)


class SearchProviderRegistry:
    """Registry for search engine providers.

    Allows dynamic registration and retrieval of search engines
    based on provider name configuration.
    """

    _providers: ClassVar[dict[str, type[SearchEngine]]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a search provider.

        Args:
            name: Provider identifier (e.g., "bing", "duckduckgo")

        Returns:
            Decorator function

        Example:
            @SearchProviderRegistry.register("duckduckgo")
            class DuckDuckGoSearchEngine(SearchEngine):
                ...
        """

        def decorator(provider_class: type[SearchEngine]) -> type[SearchEngine]:
            cls._providers[name.lower()] = provider_class
            logger.debug(f"Registered search provider: {name}")
            return provider_class

        return decorator

    @classmethod
    def get(cls, name: str, **kwargs) -> SearchEngine | None:
        """Get a search engine instance by provider name.

        Args:
            name: Provider identifier
            **kwargs: Provider-specific configuration

        Returns:
            SearchEngine instance or None if provider not found
        """
        provider_class = cls._providers.get(name.lower())
        if provider_class is None:
            logger.warning(f"Unknown search provider: {name}")
            return None

        try:
            return provider_class(**kwargs)
        except Exception as e:
            logger.error(f"Failed to instantiate search provider {name}: {e}")
            return None

    @classmethod
    def available_providers(cls) -> list[str]:
        """Get list of registered provider names."""
        return list(cls._providers.keys())


def get_search_engine_from_factory() -> SearchEngine | None:
    """Get search engine instance based on configuration.

    This is the main entry point for getting a search engine.
    It reads the provider from settings and returns an appropriate instance.

    Returns:
        SearchEngine instance or None if configuration is invalid
    """
    # Import providers to register them

    # Try to import optional providers
    try:
        importlib.import_module("app.infrastructure.external.search.duckduckgo_search")
    except ImportError:
        logger.debug("DuckDuckGo search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.brave_search")
    except ImportError:
        logger.debug("Brave search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.tavily_search")
    except ImportError:
        logger.debug("Tavily search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.serper_search")
    except ImportError:
        logger.debug("Serper search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.bing_search")
    except ImportError:
        logger.debug("Bing search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.google_search")
    except ImportError:
        logger.debug("Google search provider not available")

    settings = get_settings()
    provider = settings.search_provider

    if not provider:
        logger.warning("No search provider configured")
        return None

    if provider == "baidu":
        logger.warning("Baidu provider has been removed; falling back to duckduckgo")
        provider = "duckduckgo"

    # Build provider-specific kwargs
    kwargs = {}

    if provider == "google":
        if not settings.google_search_api_key or not settings.google_search_engine_id:
            logger.warning("Google Search not configured: missing API key or engine ID")
            return None
        kwargs["api_key"] = settings.google_search_api_key
        kwargs["cx"] = settings.google_search_engine_id

    elif provider == "brave":
        if not settings.brave_search_api_key:
            logger.warning("Brave Search not configured: missing API key")
            return None
        kwargs["api_key"] = settings.brave_search_api_key

    elif provider == "tavily":
        if not settings.tavily_api_key:
            logger.warning("Tavily Search not configured: missing API key")
            return None
        kwargs["api_key"] = settings.tavily_api_key
        # Collect fallback keys for auto-rotation on quota/billing errors
        fallback_keys = [
            k
            for k in [
                settings.tavily_api_key_2,
                settings.tavily_api_key_3,
                settings.tavily_api_key_4,
                settings.tavily_api_key_5,
                settings.tavily_api_key_6,
                settings.tavily_api_key_7,
                settings.tavily_api_key_8,
                settings.tavily_api_key_9,
            ]
            if k
        ]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys

    elif provider == "serper":
        if not settings.serper_api_key:
            logger.warning("Serper Search not configured: missing API key")
            return None
        kwargs["api_key"] = settings.serper_api_key
        # Collect fallback keys for auto-rotation on quota/billing errors
        fallback_keys = [k for k in [settings.serper_api_key_2, settings.serper_api_key_3] if k]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys

    logger.info(f"Initializing search engine: {provider}")
    return SearchProviderRegistry.get(provider, **kwargs)


# Register built-in providers
# Note: The actual classes register themselves via decorator when imported
