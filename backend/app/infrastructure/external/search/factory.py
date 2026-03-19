"""Search Provider Factory

Registry pattern for dynamically selecting search providers based on configuration.
Supports: bing, google, duckduckgo, brave, tavily, serper, exa, jina
"""

import importlib
import logging
from typing import Any, ClassVar

from app.core.config import get_settings
from app.core.search_provider_policy import (
    ALLOWED_SEARCH_PROVIDERS,
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    parse_search_provider_chain,
)
from app.domain.external.search import SearchEngine
from app.domain.models.search import SearchResults
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.search.provider_health_ranker import get_provider_health_ranker

logger = logging.getLogger(__name__)
_missing_config_warned: set[str] = set()

DEFAULT_PROVIDER_CHAIN = list(DEFAULT_SEARCH_PROVIDER_CHAIN)


def _warn_missing_provider_config_once(provider: str, detail: str) -> None:
    """Emit missing-provider-config notice only once per process.

    Uses info level because unconfigured providers are expected when
    the fallback chain covers them (e.g. brave missing but tavily active).
    """
    key = f"{provider}:{detail}"
    if key in _missing_config_warned:
        return
    _missing_config_warned.add(key)
    logger.info("%s Search not configured: %s", provider.capitalize(), detail)


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
        self._health_ranker = get_provider_health_ranker()
        chain = " -> ".join(name for name, _ in providers)
        logger.info(f"Search fallback chain enabled: {chain}")

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        errors: list[str] = []
        ordered_providers = self._rank_providers_by_health()

        for index, (provider_name, engine) in enumerate(ordered_providers):
            try:
                result = await engine.search(query, date_range)
            except Exception as e:
                errors.append(f"{provider_name}: {e}")
                self._health_ranker.record_error(provider_name)
                logger.warning(f"Search provider {provider_name} raised exception, trying next: {e}")
                continue

            if result.success:
                self._health_ranker.record_success(provider_name)
                if index > 0 and errors:
                    logger.warning(
                        "Search fallback recovered with provider %s after failures: %s",
                        provider_name,
                        "; ".join(errors),
                    )
                return result

            error_message = result.message or "unknown error"
            errors.append(f"{provider_name}: {error_message}")
            if self._looks_like_rate_limit_or_exhaustion(error_message):
                self._health_ranker.record_429(provider_name)
            else:
                self._health_ranker.record_error(provider_name)
            logger.warning(f"Search provider {provider_name} failed, trying next: {error_message}")

        chain = " -> ".join(name for name, _ in ordered_providers)
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

    def _rank_providers_by_health(self) -> list[tuple[str, SearchEngine]]:
        """Reorder providers using sliding-window health scoring."""
        provider_map = dict(self._providers)
        ranked_names = self._health_ranker.rank([name for name, _ in self._providers])
        return [(name, provider_map[name]) for name in ranked_names if name in provider_map]

    @staticmethod
    def _looks_like_rate_limit_or_exhaustion(error_message: str) -> bool:
        lowered = error_message.lower()
        return any(
            marker in lowered
            for marker in (
                "429",
                "rate limit",
                "quota",
                "credits",
                "exhausted",
            )
        )

    async def close(self) -> None:
        """Close all wrapped search engine clients."""
        for name, engine in self._providers:
            try:
                if hasattr(engine, "close"):
                    await engine.close()
            except Exception as e:
                logger.debug("Error closing search engine %s: %s", name, e)

    async def get_health_summary(self) -> dict[str, Any]:
        """Return health status of all providers in the chain."""
        summary: dict[str, Any] = {"providers": [], "healthy_count": 0, "total_count": 0}
        engines = getattr(self, "_engines", None) or getattr(self, "_provider_engines", None) or self._providers
        if isinstance(engines, list):
            # If engines is a list of (name, engine) tuples (self._providers format)
            for item in engines:
                if isinstance(item, tuple) and len(item) == 2:
                    name, engine = item
                else:
                    name = type(item).__name__
                    engine = item
                summary["total_count"] += 1
                pool = getattr(engine, "_key_pool", None)
                if pool:
                    healthy = getattr(pool, "healthy_key_count", 0)
                    total = getattr(pool, "total_key_count", 1)
                    summary["providers"].append(
                        {
                            "name": name,
                            "healthy_keys": healthy,
                            "total_keys": total,
                            "status": "healthy" if healthy > 0 else "exhausted",
                        }
                    )
                    if healthy > 0:
                        summary["healthy_count"] += 1
                else:
                    summary["providers"].append({"name": name, "status": "unknown"})
                    summary["healthy_count"] += 1
        elif isinstance(engines, dict):
            for name, engine in engines.items():
                summary["total_count"] += 1
                pool = getattr(engine, "_key_pool", None)
                if pool:
                    healthy = getattr(pool, "healthy_key_count", 0)
                    total = getattr(pool, "total_key_count", 1)
                    summary["providers"].append(
                        {
                            "name": name,
                            "healthy_keys": healthy,
                            "total_keys": total,
                            "status": "healthy" if healthy > 0 else "exhausted",
                        }
                    )
                    if healthy > 0:
                        summary["healthy_count"] += 1
                else:
                    summary["providers"].append({"name": name, "status": "unknown"})
                    summary["healthy_count"] += 1
        return summary


class RerankingSearchEngine:
    """Search engine wrapper that applies optional post-search reranking."""

    def __init__(self, base_engine: SearchEngine, reranker: Any, top_n: int):
        self._base_engine = base_engine
        self._reranker = reranker
        self._top_n = top_n

    async def search(self, query: str, date_range: str | None = None) -> ToolResult[SearchResults]:
        result = await self._base_engine.search(query, date_range)
        if not result.success or not result.data or len(result.data.results) < 2:
            return result

        try:
            reranked = await self._reranker.rerank(query=query, results=result.data.results, top_n=self._top_n)
            if reranked:
                result.data.results = reranked
                result.data.total_results = len(reranked)
                note = "[RERANKED: Jina]"
                if result.message:
                    result.message = f"{result.message}\n\n{note}"
                else:
                    result.message = note
        except Exception as e:
            logger.warning("Jina rerank wrapper failed; preserving original ordering: %s", e)

        return result

    async def close(self) -> None:
        """Close the wrapped search engine client."""
        if hasattr(self._base_engine, "close"):
            await self._base_engine.close()


def _maybe_wrap_with_jina_rerank(engine: SearchEngine, redis_client=None) -> SearchEngine:
    """Wrap an engine with Jina reranker when feature/config is enabled."""
    settings = get_settings()
    use_jina_rerank = bool(getattr(settings, "search_use_jina_rerank", False))
    jina_api_key = getattr(settings, "jina_api_key", None)
    if not use_jina_rerank or not jina_api_key:
        return engine

    try:
        from app.infrastructure.external.search.jina_reranker import JinaReranker

        fallback_keys = [
            key
            for key in [
                getattr(settings, "jina_api_key_2", None),
                getattr(settings, "jina_api_key_3", None),
                getattr(settings, "jina_api_key_4", None),
                getattr(settings, "jina_api_key_5", None),
            ]
            if key
        ]
        model = getattr(settings, "search_jina_rerank_model", "jina-reranker-v2-base-multilingual")
        configured_top_n = getattr(settings, "search_jina_rerank_top_n", 8)
        top_n = max(2, configured_top_n if isinstance(configured_top_n, int) else 8)

        reranker = JinaReranker(
            api_key=jina_api_key,
            fallback_api_keys=fallback_keys,
            redis_client=redis_client,
            model=model,
        )
        logger.info("Jina rerank wrapper enabled (top_n=%d)", top_n)
        return RerankingSearchEngine(base_engine=engine, reranker=reranker, top_n=top_n)
    except Exception as e:
        logger.warning("Failed to initialize Jina rerank wrapper; continuing without rerank: %s", e)
        return engine


def _provider_kwargs(provider: str, redis_client=None) -> dict | None:
    """Build provider-specific kwargs from settings.

    Returns None when a provider is not sufficiently configured.
    """
    settings = get_settings()

    max_results = getattr(settings, "search_max_results", 8)
    if not isinstance(max_results, int) or max_results < 1:
        max_results = 8

    if provider == "google":
        if not settings.google_search_api_key or not settings.google_search_engine_id:
            _warn_missing_provider_config_once("google", "missing API key or engine ID")
            return None
        return {"api_key": settings.google_search_api_key, "cx": settings.google_search_engine_id}

    if provider == "brave":
        if not settings.brave_search_api_key:
            _warn_missing_provider_config_once("brave", "missing API key")
            return None
        kwargs = {"api_key": settings.brave_search_api_key, "max_results": max_results}
        fallback_keys = [key for key in [settings.brave_search_api_key_2, settings.brave_search_api_key_3] if key]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        if redis_client:
            kwargs["redis_client"] = redis_client
        return kwargs

    if provider == "tavily":
        if not settings.tavily_api_key:
            _warn_missing_provider_config_once("tavily", "missing API key")
            return None
        search_depth = getattr(settings, "tavily_search_depth", "basic")
        if search_depth not in {"basic", "advanced"}:
            search_depth = "basic"

        kwargs: dict = {
            "api_key": settings.tavily_api_key,
            "max_results": max_results,
            "search_depth": search_depth,
        }
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
            _warn_missing_provider_config_once("serper", "missing API key")
            return None
        kwargs = {"api_key": settings.serper_api_key, "max_results": max_results}
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
            _warn_missing_provider_config_once("exa", "missing API key")
            return None
        search_type = getattr(settings, "exa_search_type", "auto")
        if search_type not in {"auto", "keyword", "neural"}:
            search_type = "auto"

        kwargs = {"api_key": settings.exa_api_key, "max_results": max_results, "search_type": search_type}
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

    if provider == "jina":
        if not settings.jina_api_key:
            _warn_missing_provider_config_once("jina", "missing API key")
            return None
        kwargs = {"api_key": settings.jina_api_key}
        fallback_keys = [
            key
            for key in [
                settings.jina_api_key_2,
                settings.jina_api_key_3,
                settings.jina_api_key_4,
                settings.jina_api_key_5,
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
        importlib.import_module("app.infrastructure.external.search.jina_search")
    except ImportError:
        logger.debug("Jina search provider not available")

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
        return _maybe_wrap_with_jina_rerank(engines[0][1], redis_client=redis_client)

    logger.info(
        "Initializing search engines with fallback chain: %s",
        " -> ".join(name for name, _ in engines),
    )
    fallback_engine = FallbackSearchEngine(engines)
    return _maybe_wrap_with_jina_rerank(fallback_engine, redis_client=redis_client)


# Register built-in providers
# Note: The actual classes register themselves via decorator when imported
