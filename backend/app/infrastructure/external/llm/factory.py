"""LLM Provider Factory

Registry pattern for dynamically selecting LLM providers based on configuration.

Supported providers:
- "auto" / "universal"  → UniversalLLM (auto-detects from keys/model/URL)
- "openai"              → OpenAI-compatible (OpenAI, OpenRouter, GLM-5, DeepSeek, etc.)
- "anthropic"           → Anthropic native API (Claude models)
- "ollama"              → Local Ollama server

Switching providers requires only one change:
    LLM_PROVIDER=anthropic   # or auto, openai, ollama
"""

import importlib
import logging
import threading
from typing import ClassVar

from app.core.config import get_settings
from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """Registry for LLM providers.

    Allows dynamic registration and retrieval of LLM implementations
    based on provider name configuration.
    """

    _providers: ClassVar[dict[str, type[LLM]]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register an LLM provider.

        Args:
            name: Provider identifier (e.g., "openai", "anthropic", "auto")

        Returns:
            Decorator function

        Example:
            @LLMProviderRegistry.register("anthropic")
            class AnthropicLLM(LLM):
                ...
        """

        def decorator(provider_class: type[LLM]) -> type[LLM]:
            cls._providers[name.lower()] = provider_class
            logger.debug(f"Registered LLM provider: {name}")
            return provider_class

        return decorator

    @classmethod
    def get(cls, name: str, **kwargs) -> LLM | None:
        """Get an LLM instance by provider name.

        Args:
            name: Provider identifier
            **kwargs: Provider-specific configuration

        Returns:
            LLM instance or None if provider not found
        """
        provider_class = cls._providers.get(name.lower())
        if provider_class is None:
            logger.warning(f"Unknown LLM provider: {name}")
            return None

        try:
            return provider_class(**kwargs)
        except Exception as e:
            logger.error(f"Failed to instantiate LLM provider {name}: {e}")
            return None

    @classmethod
    def available_providers(cls) -> list[str]:
        """Get list of registered provider names."""
        return list(cls._providers.keys())


def _get_redis_client():
    """Safely obtain the Redis client for key pool coordination."""
    try:
        from app.infrastructure.storage.redis import get_redis

        return get_redis()
    except Exception as e:
        logger.warning(f"Failed to get Redis client for LLM: {e}")
        return None


def get_llm_from_factory() -> LLM | None:
    """Get LLM instance based on configuration.

    Main entry point for creating an LLM. Reads LLM_PROVIDER from settings
    and returns the appropriate implementation.

    Provider resolution:
    - "auto" / "universal" → UniversalLLM (recommended — auto-detects everything)
    - "openai"             → OpenAILLM with multi-key failover
    - "anthropic"          → AnthropicLLM with multi-key failover
    - "ollama"             → OllamaLLM for local inference

    Returns:
        LLM instance or None if configuration is invalid
    """
    # Register all available providers
    _register_providers()

    settings = get_settings()
    provider = (getattr(settings, "llm_provider", "auto") or "auto").strip().lower()

    redis_client = _get_redis_client()

    # ── Auto / Universal: delegate to UniversalLLM which handles everything ──
    if provider in ("auto", "universal"):
        return LLMProviderRegistry.get(
            "auto",
            # Pass all credentials — UniversalLLM will pick what's needed
            api_key=settings.api_key,
            api_key_2=settings.api_key_2,
            api_key_3=settings.api_key_3,
            api_base=settings.api_base,
            anthropic_api_key=settings.anthropic_api_key,
            anthropic_api_key_2=settings.anthropic_api_key_2,
            anthropic_api_key_3=settings.anthropic_api_key_3,
            model_name=settings.model_name,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            ollama_base_url=settings.ollama_base_url,
            ollama_model=settings.ollama_model,
            redis_client=redis_client,
            # Pass explicit provider so UniversalLLM doesn't override with "auto" again
            provider="auto",
        )

    # ── Explicit providers (bypass UniversalLLM for direct instantiation) ──
    kwargs: dict = {}

    if provider == "openai":
        fallback_keys = [k for k in [settings.api_key_2, settings.api_key_3] if k and k.strip()]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        kwargs["redis_client"] = redis_client

    elif provider == "anthropic":
        fallback_keys = [k for k in [settings.anthropic_api_key_2, settings.anthropic_api_key_3] if k and k.strip()]
        if fallback_keys:
            kwargs["fallback_api_keys"] = fallback_keys
        kwargs["redis_client"] = redis_client

    elif provider == "ollama":
        kwargs["base_url"] = settings.ollama_base_url
        kwargs["model_name"] = settings.ollama_model

    logger.info(f"Initializing LLM: provider={provider}")
    return LLMProviderRegistry.get(provider, **kwargs)


def _register_providers() -> None:
    """Import provider modules to trigger their @LLMProviderRegistry.register() decorators."""
    provider_modules = [
        "app.infrastructure.external.llm.openai_llm",
        "app.infrastructure.external.llm.anthropic_llm",
        "app.infrastructure.external.llm.ollama_llm",
        # UniversalLLM must be last — it references the others
        "app.infrastructure.external.llm.universal_llm",
    ]
    for module_path in provider_modules:
        try:
            importlib.import_module(module_path)
        except ImportError:
            logger.debug(f"Optional LLM provider not available: {module_path}")


# ─────────────────────────── Cached getter ───────────────────────────

_cached_llm: LLM | None = None
_llm_init_attempted: bool = False
_llm_init_lock = threading.Lock()


def get_llm() -> LLM | None:
    """Get the cached LLM instance (creates on first call, thread-safe).

    Returns:
        LLM instance or None if configuration is invalid
    """
    global _cached_llm, _llm_init_attempted

    # Fast path: already initialized (no lock needed for reads of non-None value)
    if _cached_llm is not None:
        return _cached_llm

    # Slow path: acquire lock to prevent concurrent initialization
    with _llm_init_lock:
        # Double-checked locking: re-check after acquiring the lock
        if _cached_llm is not None:
            return _cached_llm

        _llm_init_attempted = True
        result = get_llm_from_factory()
        if result is not None:
            _cached_llm = result
        return result


def reset_llm_cache() -> None:
    """Reset the cached LLM instance (useful for testing or live config changes)."""
    global _cached_llm, _llm_init_attempted
    with _llm_init_lock:
        _cached_llm = None
        _llm_init_attempted = False
    logger.debug("LLM cache cleared")
