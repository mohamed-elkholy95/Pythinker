"""LLM Provider Factory

Registry pattern for dynamically selecting LLM providers based on configuration.
Supports: openai (including OpenRouter and other OpenAI-compatible APIs), ollama
"""

import importlib
import logging
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
            name: Provider identifier (e.g., "openai", "anthropic")

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


def get_llm_from_factory() -> LLM | None:
    """Get LLM instance based on configuration.

    This is the main entry point for getting an LLM.
    It reads the provider from settings and returns an appropriate instance.

    Returns:
        LLM instance or None if configuration is invalid
    """
    # Import providers to register them

    # Import OpenAI-compatible provider (works with OpenRouter, OpenAI, DeepSeek, etc.)
    try:
        importlib.import_module("app.infrastructure.external.llm.openai_llm")
    except ImportError:
        logger.debug("OpenAI LLM provider not available")

    # Try to import optional providers
    try:
        importlib.import_module("app.infrastructure.external.llm.anthropic_llm")
    except ImportError:
        logger.debug("Anthropic LLM provider not available")

    try:
        importlib.import_module("app.infrastructure.external.llm.ollama_llm")
    except ImportError:
        logger.debug("Ollama LLM provider not available")

    settings = get_settings()
    provider = getattr(settings, "llm_provider", "openai")

    if not provider:
        provider = "openai"  # Default to OpenAI-compatible

    # Build provider-specific kwargs
    kwargs = {}

    if provider == "ollama":
        kwargs["base_url"] = getattr(settings, "ollama_base_url", "http://localhost:11434")
        kwargs["model_name"] = getattr(settings, "ollama_model", "llama3.2")

    logger.info(f"Initializing LLM: {provider}")
    return LLMProviderRegistry.get(provider, **kwargs)
