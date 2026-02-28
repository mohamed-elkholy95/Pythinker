"""Provider Capability Registry (domain layer).

Centralises what each LLM model/provider supports: JSON schema, vision,
tool use, max context window, etc.  Eliminates scattered ``_is_glm_api``,
``_is_openrouter``, ``_is_deepseek`` checks spread across OpenAILLM.

Usage::

    caps = get_capabilities("glm-4-air", api_base="https://open.bigmodel.cn")
    if not caps.json_schema:
        # fall back to text extraction
    ...

Registry rules:
- Keys are glob patterns matched against the *full model name* in order.
- First match wins (most-specific patterns should come first).
- ``api_base`` overrides are checked before model-name patterns.
- Falls back to ``DEFAULT_CAPABILITIES`` when nothing matches.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Immutable description of an LLM provider's feature support.

    Attributes:
        json_schema: Supports ``response_format={type: json_schema, ...}``.
        tool_use: Supports tool / function calling.
        vision: Accepts image content in messages.
        thinking: Supports extended thinking / chain-of-thought mode.
        streaming: Supports token streaming.
        parallel_tool_calls: Can emit multiple tool calls in one turn.
        max_context_window: Maximum total tokens (prompt + completion).
        max_output_tokens: Maximum completion tokens per call.
        system_message_position: Where the system message must appear.
            ``"any"`` — no constraint.
            ``"first_only"`` — must be the very first message (GLM).
        content_format: How message content must be encoded.
            ``"flexible"`` — accepts string or content-block list.
            ``"string_only"`` — only plain strings (GLM, some older models).
    """

    json_schema: bool = True
    tool_use: bool = True
    vision: bool = False
    thinking: bool = False
    streaming: bool = True
    parallel_tool_calls: bool = True
    max_context_window: int = 128_000
    max_output_tokens: int = 16_384
    system_message_position: str = "any"  # "any" | "first_only"
    content_format: str = "flexible"  # "flexible" | "string_only"


# ─────────────────────────── Default ─────────────────────────────────────────

DEFAULT_CAPABILITIES = ProviderCapabilities()

# ─────────────────────────── Registry ────────────────────────────────────────
# Ordered list of (glob_pattern, ProviderCapabilities).
# Matched against lowercased model name.  First match wins.

_REGISTRY: list[tuple[str, ProviderCapabilities]] = [
    # ── Anthropic Claude ──────────────────────────────────────────────────
    (
        "claude-*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            vision=True,
            thinking=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=200_000,
            max_output_tokens=8_192,
            system_message_position="any",
            content_format="flexible",
        ),
    ),
    # ── OpenAI GPT-4o family ─────────────────────────────────────────────
    (
        "gpt-4o*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            vision=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=128_000,
            max_output_tokens=16_384,
        ),
    ),
    # ── OpenAI GPT OSS (120B) ────────────────────────────────────────────
    (
        "openai/gpt-oss*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            max_context_window=128_000,
            max_output_tokens=16_384,
        ),
    ),
    # ── GLM family (BigModel / ZhipuAI) ──────────────────────────────────
    # No JSON schema mode, system must be first, content must be string.
    (
        "glm-*",
        ProviderCapabilities(
            json_schema=False,
            tool_use=True,
            vision=False,
            thinking=False,
            streaming=True,
            parallel_tool_calls=False,
            max_context_window=128_000,
            max_output_tokens=4_096,
            system_message_position="first_only",
            content_format="string_only",
        ),
    ),
    # ── DeepSeek ──────────────────────────────────────────────────────────
    (
        "deepseek*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=128_000,
            max_output_tokens=8_192,
        ),
    ),
    # ── Qwen3-Coder (large context) ───────────────────────────────────────
    (
        "qwen*coder*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=262_144,
            max_output_tokens=65_536,
        ),
    ),
    # ── Qwen family (general) ─────────────────────────────────────────────
    (
        "qwen*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=131_072,
            max_output_tokens=16_384,
        ),
    ),
    # ── Gemini 2.5 (huge context) ─────────────────────────────────────────
    (
        "gemini-2.5*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            vision=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=1_000_000,
            max_output_tokens=65_536,
        ),
    ),
    # ── Gemini (general) ──────────────────────────────────────────────────
    (
        "gemini-*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            vision=True,
            streaming=True,
            max_context_window=1_000_000,
            max_output_tokens=8_192,
        ),
    ),
    # ── Kimi / Moonshot ───────────────────────────────────────────────────
    (
        "moonshotai/*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            parallel_tool_calls=True,
            max_context_window=128_000,
            max_output_tokens=16_384,
        ),
    ),
    # ── MiMo (Xiaomi) ─────────────────────────────────────────────────────
    (
        "xiaomi/mimo*",
        ProviderCapabilities(
            json_schema=True,
            tool_use=True,
            streaming=True,
            max_context_window=32_768,
            max_output_tokens=4_096,
        ),
    ),
    # ── Llama (Ollama / Meta) ─────────────────────────────────────────────
    (
        "llama*",
        ProviderCapabilities(
            json_schema=False,
            tool_use=True,
            streaming=True,
            parallel_tool_calls=False,
            max_context_window=128_000,
            max_output_tokens=8_192,
            content_format="string_only",
        ),
    ),
]

# API-base → ProviderCapabilities overrides (checked first, before model patterns)
_API_BASE_OVERRIDES: dict[str, ProviderCapabilities] = {
    "open.bigmodel.cn": ProviderCapabilities(
        json_schema=False,
        tool_use=True,
        streaming=True,
        parallel_tool_calls=False,
        max_context_window=128_000,
        max_output_tokens=4_096,
        system_message_position="first_only",
        content_format="string_only",
    ),
    "z.ai": ProviderCapabilities(
        json_schema=False,
        tool_use=True,
        streaming=True,
        parallel_tool_calls=False,
        max_context_window=128_000,
        max_output_tokens=4_096,
        system_message_position="first_only",
        content_format="string_only",
    ),
}


def get_capabilities(
    model_name: str,
    api_base: str | None = None,
) -> ProviderCapabilities:
    """Return the best-matching ``ProviderCapabilities`` for a model.

    Args:
        model_name: Full model identifier (e.g. ``"glm-4-air"``,
            ``"claude-sonnet-4-20250514"``, ``"qwen/qwen3-coder-next"``).
        api_base: Optional base URL; some providers share model names but
            differ in capabilities (e.g. GLM via z.ai vs openrouter).

    Returns:
        ``ProviderCapabilities`` — always non-None (falls back to defaults).
    """
    # 1. API-base override takes highest precedence
    if api_base:
        for domain, caps in _API_BASE_OVERRIDES.items():
            if domain in api_base:
                logger.debug("Capabilities from api_base=%s → %s", api_base, domain)
                return caps

    # 2. Glob match against lowercased model name
    name_lower = (model_name or "").lower()
    for pattern, caps in _REGISTRY:
        if fnmatch.fnmatch(name_lower, pattern.lower()):
            logger.debug("Capabilities for model=%s matched pattern=%s", model_name, pattern)
            return caps

    logger.debug("No capability match for model=%s; using defaults", model_name)
    return DEFAULT_CAPABILITIES
