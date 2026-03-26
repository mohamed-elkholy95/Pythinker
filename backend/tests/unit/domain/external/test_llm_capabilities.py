"""Tests for LLM capability registry (app.domain.external.llm_capabilities).

Covers ProviderCapabilities defaults, model-name matching via glob
patterns, API base overrides, specific provider configurations, and
fallback behavior.
"""

from app.domain.external.llm_capabilities import (
    DEFAULT_CAPABILITIES,
    ProviderCapabilities,
    get_capabilities,
)


# ── ProviderCapabilities defaults ────────────────────────────────────


class TestProviderCapabilities:
    """Tests for ProviderCapabilities dataclass."""

    def test_default_values(self) -> None:
        caps = DEFAULT_CAPABILITIES
        assert caps.json_schema is False
        assert caps.json_object is False
        assert caps.tool_use is True
        assert caps.vision is False
        assert caps.thinking is False
        assert caps.streaming is True
        assert caps.parallel_tool_calls is True
        assert caps.max_context_window == 128_000
        assert caps.max_output_tokens == 16_384
        assert caps.system_message_position == "any"
        assert caps.content_format == "flexible"

    def test_immutability(self) -> None:
        caps = ProviderCapabilities()
        try:
            caps.json_schema = True  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass  # frozen=True


# ── Anthropic Claude ─────────────────────────────────────────────────


class TestClaudeCapabilities:
    """Tests for Claude model capabilities."""

    def test_claude_sonnet(self) -> None:
        caps = get_capabilities("claude-sonnet-4-20250514")
        assert caps.json_schema is True
        assert caps.vision is True
        assert caps.thinking is True
        assert caps.tool_use is True
        assert caps.max_context_window == 200_000

    def test_claude_opus(self) -> None:
        caps = get_capabilities("claude-opus-4-20250514")
        assert caps.json_schema is True
        assert caps.vision is True

    def test_claude_haiku(self) -> None:
        caps = get_capabilities("claude-3.5-haiku")
        assert caps.json_schema is True


# ── OpenAI GPT ───────────────────────────────────────────────────────


class TestOpenAICapabilities:
    """Tests for OpenAI model capabilities."""

    def test_gpt4o(self) -> None:
        caps = get_capabilities("gpt-4o")
        assert caps.json_schema is True
        assert caps.json_object is True
        assert caps.vision is True
        assert caps.max_context_window == 128_000

    def test_gpt4o_mini(self) -> None:
        caps = get_capabilities("gpt-4o-mini")
        assert caps.json_schema is True

    def test_gpt5(self) -> None:
        caps = get_capabilities("gpt-5-turbo")
        assert caps.json_schema is True
        assert caps.thinking is True
        assert caps.max_context_window == 400_000
        assert caps.max_output_tokens == 128_000


# ── GLM ──────────────────────────────────────────────────────────────


class TestGLMCapabilities:
    """Tests for GLM/ZhipuAI model capabilities."""

    def test_glm_4_air(self) -> None:
        caps = get_capabilities("glm-4-air")
        assert caps.json_schema is False
        assert caps.json_object is False
        assert caps.system_message_position == "first_only"
        assert caps.content_format == "string_only"
        assert caps.parallel_tool_calls is False

    def test_glm_5(self) -> None:
        caps = get_capabilities("glm-5-plus")
        assert caps.json_schema is False
        assert caps.content_format == "string_only"


# ── DeepSeek ─────────────────────────────────────────────────────────


class TestDeepSeekCapabilities:
    """Tests for DeepSeek model capabilities."""

    def test_deepseek_v3(self) -> None:
        caps = get_capabilities("deepseek-v3")
        assert caps.json_schema is True
        assert caps.json_object is True
        assert caps.parallel_tool_calls is True

    def test_deepseek_coder(self) -> None:
        caps = get_capabilities("deepseek-coder-33b")
        assert caps.tool_use is True


# ── Qwen ─────────────────────────────────────────────────────────────


class TestQwenCapabilities:
    """Tests for Qwen model capabilities."""

    def test_qwen_coder(self) -> None:
        caps = get_capabilities("qwen3-coder-next")
        assert caps.json_schema is True
        assert caps.max_context_window == 262_144
        assert caps.max_output_tokens == 65_536

    def test_qwen_general(self) -> None:
        caps = get_capabilities("qwen2.5-72b")
        assert caps.json_schema is True
        assert caps.max_context_window == 131_072


# ── Gemini ───────────────────────────────────────────────────────────


class TestGeminiCapabilities:
    """Tests for Gemini model capabilities."""

    def test_gemini_25(self) -> None:
        caps = get_capabilities("gemini-2.5-pro")
        assert caps.json_schema is True
        assert caps.vision is True
        assert caps.max_context_window == 1_000_000
        assert caps.max_output_tokens == 65_536

    def test_gemini_20(self) -> None:
        caps = get_capabilities("gemini-2.0-flash")
        assert caps.json_schema is True
        assert caps.max_context_window == 1_000_000


# ── Llama ────────────────────────────────────────────────────────────


class TestLlamaCapabilities:
    """Tests for Llama model capabilities."""

    def test_llama(self) -> None:
        caps = get_capabilities("llama-3.1-70b")
        assert caps.json_schema is False
        assert caps.content_format == "string_only"
        assert caps.parallel_tool_calls is False


# ── API base overrides ───────────────────────────────────────────────


class TestAPIBaseOverrides:
    """Tests for API base URL overrides."""

    def test_bigmodel_cn_override(self) -> None:
        caps = get_capabilities("some-model", api_base="https://open.bigmodel.cn/v4")
        assert caps.json_schema is False
        assert caps.system_message_position == "first_only"
        assert caps.content_format == "string_only"

    def test_z_ai_override(self) -> None:
        caps = get_capabilities("some-model", api_base="https://api.z.ai/v1")
        assert caps.json_schema is False
        assert caps.content_format == "string_only"

    def test_api_base_takes_precedence(self) -> None:
        # Even for a Claude model, bigmodel.cn api_base should override
        caps = get_capabilities("claude-3.5-sonnet", api_base="https://open.bigmodel.cn/v4")
        assert caps.json_schema is False
        assert caps.content_format == "string_only"


# ── Fallback ─────────────────────────────────────────────────────────


class TestFallback:
    """Tests for fallback to default capabilities."""

    def test_unknown_model(self) -> None:
        caps = get_capabilities("totally-unknown-model-xyz")
        assert caps == DEFAULT_CAPABILITIES

    def test_empty_model(self) -> None:
        caps = get_capabilities("")
        assert caps == DEFAULT_CAPABILITIES

    def test_none_like_model(self) -> None:
        caps = get_capabilities("None")
        assert caps == DEFAULT_CAPABILITIES

    def test_case_insensitive_matching(self) -> None:
        caps = get_capabilities("CLAUDE-SONNET-4")
        assert caps.json_schema is True  # matched claude-* pattern
        assert caps.vision is True
