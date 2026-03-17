"""Tests for app.domain.utils.llm_compat — centralised LLM provider detection."""

import pytest

from app.domain.utils.llm_compat import is_native_openai


class TestIsNativeOpenAI:
    """is_native_openai() should return True only for genuine OpenAI endpoints."""

    # ── Native OpenAI (True) ──────────────────────────────────────────────
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://API.OPENAI.COM/v1",  # case-insensitive
            "https://openai.azure.com/openai/deployments/gpt-4o",
            "https://my-resource.openai.azure.com/openai/v1",
        ],
    )
    def test_native_openai_returns_true(self, url: str) -> None:
        assert is_native_openai(url) is True

    # ── Non-native / compatible (False) ───────────────────────────────────
    @pytest.mark.parametrize(
        "url",
        [
            "https://open.bigmodel.cn/api/paas/v4",  # GLM
            "https://api.kimi.com/coding/v1",  # Kimi
            "https://api.deepseek.com/v1",  # DeepSeek
            "https://openrouter.ai/api/v1",  # OpenRouter
            "http://localhost:11434/v1",  # Ollama
            "http://host.docker.internal:11434/v1",  # Ollama in Docker
            "https://api.together.xyz/v1",  # Together AI
            "https://api.groq.com/openai/v1",  # Groq
            "https://generativelanguage.googleapis.com/v1",  # Google
        ],
    )
    def test_compatible_providers_return_false(self, url: str) -> None:
        assert is_native_openai(url) is False

    # ── Edge cases ────────────────────────────────────────────────────────
    def test_none_returns_false(self) -> None:
        assert is_native_openai(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert is_native_openai("") is False

    def test_whitespace_returns_false(self) -> None:
        assert is_native_openai("   ") is False
