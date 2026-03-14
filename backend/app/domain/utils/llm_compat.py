"""LLM provider compatibility utilities.

Centralised helpers that determine whether an LLM endpoint is *native* OpenAI
(i.e. supports all OpenAI-specific parameters like ``response_format``,
``max_completion_tokens``, ``service_tier``, etc.) or an OpenAI-*compatible*
provider that may reject those parameters.

These helpers are consumed by the browser-agent tool and the browser-use
infrastructure adapter so that provider detection logic lives in one place.
"""

from __future__ import annotations

# Domains whose APIs are fully OpenAI-native (support response_format, etc.)
_NATIVE_OPENAI_DOMAINS: tuple[str, ...] = (
    "api.openai.com",
    "openai.azure.com",
)


def is_native_openai(api_base: str | None) -> bool:
    """Return ``True`` when *api_base* points to a genuinely OpenAI-native API.

    Only ``api.openai.com`` and ``openai.azure.com`` qualify.  Every other
    OpenAI-*compatible* endpoint (GLM, Kimi, DeepSeek, OpenRouter, Ollama, …)
    returns ``False`` because those providers may reject OpenAI-specific
    parameters such as ``response_format``, ``max_completion_tokens``,
    ``frequency_penalty``, or ``service_tier``.

    Args:
        api_base: The LLM API base URL (e.g. ``https://api.openai.com/v1``).

    Returns:
        ``True`` if the endpoint is native OpenAI, ``False`` otherwise
        (including ``None`` or empty string).
    """
    if not api_base:
        return False
    base_lower = api_base.lower()
    return any(domain in base_lower for domain in _NATIVE_OPENAI_DOMAINS)
