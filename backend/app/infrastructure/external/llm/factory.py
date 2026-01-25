"""LLM Provider Factory

Registry pattern for dynamically selecting LLM providers based on configuration.
Supports: openai, anthropic, ollama
"""
from typing import Dict, Type, Optional
import logging

from app.domain.external.llm import LLM
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """Registry for LLM providers.

    Allows dynamic registration and retrieval of LLM implementations
    based on provider name configuration.
    """
    _providers: Dict[str, Type[LLM]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register an LLM provider.

        Args:
            name: Provider identifier (e.g., "openai", "anthropic")

        Returns:
            Decorator function

        Example:
            @LLMProviderRegistry.register("anthropic")
            class AnthropicLLM(LLM):
                ...
        """
        def decorator(provider_class: Type[LLM]) -> Type[LLM]:
            cls._providers[name.lower()] = provider_class
            logger.debug(f"Registered LLM provider: {name}")
            return provider_class
        return decorator

    @classmethod
    def get(cls, name: str, **kwargs) -> Optional[LLM]:
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


def get_llm_from_factory() -> Optional[LLM]:
    """Get LLM instance based on configuration.

    This is the main entry point for getting an LLM.
    It reads the provider from settings and returns an appropriate instance.

    Returns:
        LLM instance or None if configuration is invalid
    """
    # Import providers to register them
    from app.infrastructure.external.llm.openai_llm import OpenAILLM

    # Try to import optional providers
    try:
        from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM
    except ImportError:
        logger.debug("Anthropic LLM provider not available")

    try:
        from app.infrastructure.external.llm.ollama_llm import OllamaLLM
    except ImportError:
        logger.debug("Ollama LLM provider not available")

    settings = get_settings()
    provider = getattr(settings, 'llm_provider', 'openai')

    if not provider:
        provider = 'openai'  # Default to OpenAI-compatible

    # Build provider-specific kwargs
    kwargs = {}

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("Anthropic not configured: missing API key, falling back to OpenAI")
            provider = "openai"
        else:
            kwargs["api_key"] = settings.anthropic_api_key
            kwargs["model_name"] = getattr(settings, 'anthropic_model_name', 'claude-sonnet-4-20250514')

    elif provider == "ollama":
        kwargs["base_url"] = getattr(settings, 'ollama_base_url', 'http://localhost:11434')
        kwargs["model_name"] = getattr(settings, 'ollama_model', 'llama3.2')

    logger.info(f"Initializing LLM: {provider}")
    return LLMProviderRegistry.get(provider, **kwargs)


# Backwards-compatible function
def get_llm() -> Optional[LLM]:
    """Get LLM instance (backwards compatible alias)."""
    return get_llm_from_factory()
