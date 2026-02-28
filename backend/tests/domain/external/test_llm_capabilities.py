"""Tests for the Provider Capability Registry (Phase 3).

Covers: model name glob matching, api_base override, fallback to defaults,
and key capability values for known providers.
"""

from __future__ import annotations

import pytest

from app.domain.external.llm_capabilities import (
    DEFAULT_CAPABILITIES,
    ProviderCapabilities,
    get_capabilities,
)


# ─────────────────────────── Known providers ─────────────────────────────────


def test_claude_model_gets_anthropic_caps():
    caps = get_capabilities("claude-sonnet-4-20250514")
    assert caps.vision is True
    assert caps.max_context_window == 200_000
    assert caps.tool_use is True
    assert caps.json_schema is True


def test_glm_model_gets_restricted_caps():
    caps = get_capabilities("glm-4-air")
    assert caps.json_schema is False
    assert caps.system_message_position == "first_only"
    assert caps.content_format == "string_only"
    assert caps.parallel_tool_calls is False


def test_qwen_coder_gets_large_context():
    caps = get_capabilities("qwen/qwen3-coder-next")
    assert caps.max_context_window == 262_144
    assert caps.max_output_tokens == 65_536


def test_gpt4o_gets_vision_and_json_schema():
    caps = get_capabilities("gpt-4o-2024-11-20")
    assert caps.vision is True
    assert caps.json_schema is True
    assert caps.max_context_window == 128_000


def test_deepseek_model():
    caps = get_capabilities("deepseek/deepseek-chat")
    assert caps.json_schema is True
    assert caps.parallel_tool_calls is True


def test_gemini_25_gets_million_context():
    caps = get_capabilities("gemini-2.5-pro")
    assert caps.max_context_window == 1_000_000


def test_llama_model_string_only_content():
    caps = get_capabilities("llama3.2")
    assert caps.content_format == "string_only"
    assert caps.json_schema is False


# ─────────────────────────── API-base override ───────────────────────────────


def test_api_base_bigmodel_overrides_model_match():
    # Even a "gpt-4o" model name should get GLM caps via bigmodel.cn
    caps = get_capabilities("gpt-4o", api_base="https://open.bigmodel.cn/api/paas/v4/")
    assert caps.json_schema is False
    assert caps.system_message_position == "first_only"


def test_api_base_z_ai_overrides():
    caps = get_capabilities("gpt-4o", api_base="https://api.z.ai/v1")
    assert caps.content_format == "string_only"


# ─────────────────────────── Fallback ────────────────────────────────────────


def test_unknown_model_returns_default_caps():
    caps = get_capabilities("some-unknown-model-xyz")
    assert caps == DEFAULT_CAPABILITIES


def test_empty_model_name_returns_defaults():
    caps = get_capabilities("")
    assert caps == DEFAULT_CAPABILITIES


def test_none_api_base_no_error():
    caps = get_capabilities("claude-opus-4-6", api_base=None)
    assert caps.max_context_window == 200_000


# ─────────────────────────── Case insensitivity ──────────────────────────────


def test_matching_is_case_insensitive():
    caps_upper = get_capabilities("GLM-4-Air")
    caps_lower = get_capabilities("glm-4-air")
    assert caps_upper == caps_lower


# ─────────────────────────── ProviderCapabilities ────────────────────────────


def test_provider_capabilities_frozen():
    caps = ProviderCapabilities()
    with pytest.raises((AttributeError, TypeError)):
        caps.json_schema = False  # type: ignore[misc]


def test_default_capabilities_values():
    caps = ProviderCapabilities()
    assert caps.json_schema is True
    assert caps.tool_use is True
    assert caps.vision is False
    assert caps.max_context_window == 128_000
    assert caps.system_message_position == "any"
    assert caps.content_format == "flexible"
