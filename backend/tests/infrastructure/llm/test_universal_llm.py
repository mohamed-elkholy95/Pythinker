from __future__ import annotations

import pytest

from app.infrastructure.external.llm.universal_llm import detect_provider


class TestDetectProvider:
    """Tests for the detect_provider function."""

    # ── Explicit provider override ────────────────────────────────────

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama", "deepseek"])
    def test_explicit_provider_wins(self, provider: str) -> None:
        result = detect_provider(explicit_provider=provider)
        assert result == provider

    def test_explicit_provider_case_insensitive(self) -> None:
        assert detect_provider(explicit_provider="ANTHROPIC") == "anthropic"
        assert detect_provider(explicit_provider="Ollama") == "ollama"

    def test_explicit_auto_falls_through(self) -> None:
        result = detect_provider(explicit_provider="auto", api_key="sk-123")
        assert result == "openai"

    def test_explicit_empty_string_falls_through(self) -> None:
        result = detect_provider(explicit_provider="", api_key="sk-123")
        assert result == "openai"

    # ── Anthropic API key detection ──��────────────────────────────────

    def test_anthropic_api_key_detected(self) -> None:
        result = detect_provider(anthropic_api_key="sk-ant-12345")
        assert result == "anthropic"

    def test_anthropic_key_whitespace_only_ignored(self) -> None:
        result = detect_provider(anthropic_api_key="   ")
        assert result == "openai"  # falls through to default

    def test_anthropic_key_none_ignored(self) -> None:
        result = detect_provider(anthropic_api_key=None, api_key="sk-123")
        assert result == "openai"

    # ── Model name prefix detection ───────────────────────────────────

    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-3-opus-20240229",
            "Claude-Sonnet-4-5",  # case variations
        ],
    )
    def test_claude_model_detected_as_anthropic(self, model: str) -> None:
        result = detect_provider(model_name=model)
        assert result == "anthropic"

    @pytest.mark.parametrize(
        "model",
        [
            "glm-5",
            "glm-5-turbo",
            "GLM-5",
        ],
    )
    def test_glm_model_detected_as_openai(self, model: str) -> None:
        result = detect_provider(model_name=model)
        assert result == "openai"

    def test_glm_z_model_detected(self) -> None:
        result = detect_provider(model_name="some-glm-z-variant")
        assert result == "openai"

    @pytest.mark.parametrize(
        "model",
        [
            "gpt-4",
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
        ],
    )
    def test_gpt_models_fall_through(self, model: str) -> None:
        result = detect_provider(model_name=model, api_key="sk-123")
        assert result == "openai"

    # ── API base URL detection ────────────────────────────────────────

    @pytest.mark.parametrize(
        "base",
        [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://host.docker.internal:11434",
            "http://localhost:8081",
        ],
    )
    def test_local_base_url_detected_as_ollama(self, base: str) -> None:
        result = detect_provider(api_base=base)
        assert result == "ollama"

    @pytest.mark.parametrize(
        "base",
        [
            "https://open.z.ai/v1",
            "https://open.bigmodel.cn/api/v1",
            "https://api.zhipuai.cn",
        ],
    )
    def test_zhipu_base_url_detected_as_openai(self, base: str) -> None:
        result = detect_provider(api_base=base)
        assert result == "openai"

    def test_openai_base_url_with_key(self) -> None:
        result = detect_provider(api_base="https://api.openai.com/v1", api_key="sk-123")
        assert result == "openai"

    # ── API key fallback ──────────────────────────────────────────────

    def test_api_key_present_returns_openai(self) -> None:
        result = detect_provider(api_key="sk-123456")
        assert result == "openai"

    def test_api_key_whitespace_only_ignored(self) -> None:
        result = detect_provider(api_key="   ")
        assert result == "openai"  # default fallback

    # ── Default fallback ──────────────────────────────────────────────

    def test_no_args_returns_openai(self) -> None:
        result = detect_provider()
        assert result == "openai"

    def test_all_none_returns_openai(self) -> None:
        result = detect_provider(
            api_key=None,
            anthropic_api_key=None,
            model_name=None,
            api_base=None,
            explicit_provider=None,
        )
        assert result == "openai"

    # ── Priority ordering ─────────────────────────────────────────────

    def test_explicit_beats_anthropic_key(self) -> None:
        result = detect_provider(
            explicit_provider="ollama",
            anthropic_api_key="sk-ant-123",
        )
        assert result == "ollama"

    def test_anthropic_key_beats_model_name(self) -> None:
        result = detect_provider(
            anthropic_api_key="sk-ant-123",
            model_name="gpt-4",
        )
        assert result == "anthropic"

    def test_claude_model_beats_api_key(self) -> None:
        result = detect_provider(
            model_name="claude-sonnet-4-5",
            api_key="sk-openai-123",
        )
        assert result == "anthropic"

    def test_localhost_base_beats_api_key(self) -> None:
        result = detect_provider(
            api_base="http://localhost:11434",
            api_key="sk-123",
        )
        assert result == "ollama"

    def test_api_key_beats_default(self) -> None:
        result = detect_provider(api_key="sk-123")
        assert result == "openai"
