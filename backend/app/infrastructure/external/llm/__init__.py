"""LLM Infrastructure

Provides LLM implementations and factory for dynamic provider selection.

Supported providers:
- openai: OpenAI-compatible API (default, includes DeepSeek, etc.)
- anthropic: Anthropic Claude models (requires anthropic package)
- ollama: Local Ollama models
"""
from functools import lru_cache
from typing import Optional
import logging

from app.domain.external.llm import LLM
from app.infrastructure.external.llm.factory import (
    LLMProviderRegistry,
    get_llm_from_factory,
)

logger = logging.getLogger(__name__)


@lru_cache()
def get_llm() -> Optional[LLM]:
    """Get LLM instance based on configuration.

    Uses the LLMProviderRegistry to dynamically select and instantiate
    the appropriate LLM based on LLM_PROVIDER setting.

    Returns:
        LLM instance or None if configuration is invalid
    """
    return get_llm_from_factory()


__all__ = [
    "get_llm",
    "LLMProviderRegistry",
]
