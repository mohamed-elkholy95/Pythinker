"""LLM Infrastructure

Provides LLM implementations and factory for dynamic provider selection.

Supported providers:
- openai: OpenAI-compatible API (default, includes DeepSeek, etc.)
- anthropic: Anthropic Claude models (requires anthropic package)
- ollama: Local Ollama models
"""

import logging
from app.domain.external.llm import LLM
from app.infrastructure.external.llm.factory import (
    LLMProviderRegistry,
    get_llm_from_factory,
)

logger = logging.getLogger(__name__)


_cached_llm: LLM | None = None
_llm_init_attempted: bool = False


def get_llm() -> LLM | None:
    """Get LLM instance based on configuration.

    Uses the LLMProviderRegistry to dynamically select and instantiate
    the appropriate LLM based on LLM_PROVIDER setting.

    Caches successful results but retries on None to avoid permanently
    caching a failed initialization.

    Returns:
        LLM instance or None if configuration is invalid
    """
    global _cached_llm, _llm_init_attempted
    if _cached_llm is not None:
        return _cached_llm
    result = get_llm_from_factory()
    if result is not None:
        _cached_llm = result
    elif not _llm_init_attempted:
        _llm_init_attempted = True
        logger.warning("LLM initialization returned None — will retry on next call")
    return result


__all__ = [
    "LLMProviderRegistry",
    "get_llm",
]
