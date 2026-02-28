"""Search Provider Factory

Registry pattern for dynamically selecting search providers based on configuration.
Supports: bing, google, duckduckgo, brave, tavily, serper
"""

import importlib
import logging
from typing import ClassVar

from app.core.config import get_settings
from app.core.search_provider_policy import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    parse_search_provider_chain,
)
from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResults
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_CHAIN = list(DEFAULT_SEARCH_PROVIDER_CHAIN)


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


class FallbackSearchEngine:
    """Search engine wrapper with provider-level fallback.

    Tries providers in order until one returns success=True.
    """

    def __init__(self, providers: list[tuple[str, SearchEngine]]):
        self._providers = providers
        chain = " -> ".join(name for name, _ in providers)
        logger.info(f"Search fallback chain enabled: {chain}")

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        errors: list[str] = []

        for index, (provider_name, engine) in enumerate(self._providers):
            try:
                result = await engine.search(query, date_range)
            except Exception as e:
                errors.append(f"{provider_name}: {e}")
                logger.warning(f"Search provider {provider_name} raised exception, trying next: {e}")
                continue

            if result.success:
                if index > 0 and errors:
                    logger.warning(
                        "Search fallback recovered with provider %s after failures: %s",
                        provider_name,
                        "; ".join(errors),
                    )
                return result

            error_message = result.message or "unknown error"
            errors.append(f"{provider_name}: {error_message}")
            logger.warning(f"Search provider {provider_name} failed, trying next: {error_message}")

        chain = " -> ".join(name for name, _ in self._providers)
        final_error = f"All search providers failed ({chain}): {'; '.join(errors) if errors else 'unknown error'}"
        return ToolResult.error(
            message=final_error,
            data=SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[],
            ),
        )


def _provider_kwargs(provider: str, redis_client=None) -> dict | None:
    """Build provider-specific kwargs from settings.

    Returns None when a provider is not sufficiently configured.
    """
    settings = get_settings()

    if provider == "google":
        if not settings.google_search_api_key or not settings.google_search_engine_id:
            logger.warning("Google Search not configured: missing API key or engine ID")
            return None
        return {"api_key": settings.google_search_api_key, "cx": settings.google_search_engine_id}

    if provider == "brave":
        if not settings.brave_search_api_key:
            logger.warning("Brave Search not configured: missing API key")
            return None
        kwargs = {"api_key": settings.brave_search_api_key}
        fallback_keys = [key for key in [settings.brave_search_api_key_2, settings.brave_search_api_key_3] if key]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        if redis_client:
            kwargs["redis_client"] = redis_client
        return kwargs

    if provider == "tavily":
        if not settings.tavily_api_key:
            logger.warning("Tavily Search not configured: missing API key")
            return None
        kwargs: dict = {"api_key": settings.tavily_api_key}
        fallback_keys = [
            key
            for key in [
                settings.tavily_api_key_2,
                settings.tavily_api_key_3,
                settings.tavily_api_key_4,
                settings.tavily_api_key_5,
                settings.tavily_api_key_6,
                settings.tavily_api_key_7,
                settings.tavily_api_key_8,
                settings.tavily_api_key_9,
            ]
            if key
        ]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        if redis_client:
            kwargs["redis_client"] = redis_client
        return kwargs

    if provider == "serper":
        if not settings.serper_api_key:
            logger.warning("Serper Search not configured: missing API key")
            return None
        kwargs = {"api_key": settings.serper_api_key}
        fallback_keys = [
            key
            for key in [
                settings.serper_api_key_2,
                settings.serper_api_key_3,
                settings.serper_api_key_4,
                settings.serper_api_key_5,
                settings.serper_api_key_6,
                settings.serper_api_key_7,
                settings.serper_api_key_8,
                settings.serper_api_key_9,
            ]
            if key
        ]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        if redis_client:
            kwargs["redis_client"] = redis_client
        quota_cooldown = getattr(settings, "serper_quota_cooldown_seconds", 1800)
        kwargs["quota_cooldown_seconds"] = quota_cooldown
        return kwargs

    if provider == "exa":
        if not settings.exa_api_key:
            logger.warning("Exa Search not configured: missing API key")
            return None
        kwargs = {"api_key": settings.exa_api_key}
        fallback_keys = [
            key
            for key in [
                settings.exa_api_key_2,
                settings.exa_api_key_3,
                settings.exa_api_key_4,
                settings.exa_api_key_5,
            ]
            if key
        ]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        if redis_client:
            kwargs["redis_client"] = redis_client
        return kwargs

    # Providers without required API key config (duckduckgo, bing, etc.)
    return {}


def _create_provider_engine(provider: str, redis_client=None) -> SearchEngine | None:
    """Instantiate a provider if configured."""
    kwargs = _provider_kwargs(provider, redis_client=redis_client)
    if kwargs is None:
        return None
    return SearchProviderRegistry.get(provider, **kwargs)


def _resolve_provider_chain(provider: str | None, configured_chain: str | list[str] | None) -> list[str]:
    """Resolve final chain with defaults, configured-provider append, and dedupe."""
    chain = parse_search_provider_chain(configured_chain)
    if not chain:
        chain = list(DEFAULT_SEARCH_PROVIDER_CHAIN)

    if provider and provider in ALLOWED_SEARCH_PROVIDERS and provider not in chain:
        chain.append(provider)
    elif provider and provider not in ALLOWED_SEARCH_PROVIDERS:
        logger.warning("Ignoring unsupported search provider in chain resolution: %s", provider)

    unique_chain: list[str] = []
    for candidate in chain:
        if candidate not in unique_chain:
            unique_chain.append(candidate)

    if unique_chain:
        return unique_chain
    return list(DEFAULT_SEARCH_PROVIDER_CHAIN)


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
        importlib.import_module("app.infrastructure.external.search.exa_search")
    except ImportError:
        logger.debug("Exa search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.bing_search")
    except ImportError:
        logger.debug("Bing search provider not available")

    try:
        importlib.import_module("app.infrastructure.external.search.google_search")
    except ImportError:
        logger.debug("Google search provider not available")

    settings = get_settings()
    configured_provider = getattr(settings, "search_provider", None)
    provider = configured_provider.strip().lower() if isinstance(configured_provider, str) else ""

    if not provider:
        logger.warning("No search provider configured; resolving from provider chain/defaults")

    if provider == "baidu":
        logger.warning("Baidu provider has been removed; falling back to duckduckgo")
        provider = "duckduckgo"

    # Get Redis client for API key pool coordination
    redis_client = None
    try:
        from app.infrastructure.storage.redis import get_redis

        redis_client = get_redis()
    except Exception as e:
        logger.warning(f"Failed to get Redis client for search key pool: {e}")

    chain_setting = getattr(settings, "search_provider_chain", None)
    unique_chain = _resolve_provider_chain(provider=provider, configured_chain=chain_setting)

    engines: list[tuple[str, SearchEngine]] = []
    for candidate in unique_chain:
        engine = _create_provider_engine(candidate, redis_client=redis_client)
        if engine is not None:
            engines.append((candidate, engine))

    if not engines:
        logger.warning("No search engines available after evaluating provider chain: %s", " -> ".join(unique_chain))
        return None

    if len(engines) == 1:
        logger.info("Initializing search engine: %s", engines[0][0])
        return engines[0][1]

    logger.info(
        "Initializing search engines with fallback chain: %s",
        " -> ".join(name for name, _ in engines),
    )
    return FallbackSearchEngine(engines)


# Register built-in providers
# Note: The actual classes register themselves via decorator when imported
