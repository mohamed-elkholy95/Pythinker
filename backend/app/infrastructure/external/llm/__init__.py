"""LLM Infrastructure

Provides LLM implementations and factory for dynamic provider selection.

Supported providers (set LLM_PROVIDER in .env):
- "auto"      → auto-detect from keys/model/URL (default, recommended)
- "openai"    → OpenAI-compatible (OpenAI, OpenRouter, GLM-5, DeepSeek, etc.)
- "anthropic" → Anthropic native API (Claude models)
- "ollama"    → Local Ollama server

Quick provider switching examples (.env):

    # Use Anthropic Claude
    LLM_PROVIDER=auto
    ANTHROPIC_API_KEY=sk-ant-...
    # MODEL_NAME=claude-opus-4-5  (optional, defaults to anthropic_model_name)

    # Use OpenAI / OpenRouter
    LLM_PROVIDER=auto
    API_KEY=sk-...
    MODEL_NAME=gpt-4o

    # Use GLM-5 (ZhipuAI)
    LLM_PROVIDER=auto
    API_KEY=your-zhipu-key
    API_BASE=https://api.z.ai/api/paas/v4
    MODEL_NAME=glm-5

    # Use local Ollama
    LLM_PROVIDER=auto
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_MODEL=llama3.2
"""

from app.domain.external.llm import LLM
from app.infrastructure.external.llm.factory import (
    LLMProviderRegistry,
    get_llm,
    get_llm_from_factory,
    reset_llm_cache,
)

__all__ = [
    "LLM",
    "LLMProviderRegistry",
    "get_llm",
    "get_llm_from_factory",
    "reset_llm_cache",
]
