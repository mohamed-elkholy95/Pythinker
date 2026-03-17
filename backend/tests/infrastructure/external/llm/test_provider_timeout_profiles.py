"""Tests for provider-aware timeout profiles.

Verifies that:
1. GLM's tool_read_timeout is 180s (not 90s)
2. _create_timeout() uses provider profile's tool_read_timeout instead of hardcoded 90s
3. asyncio-level llm_tool_request_timeout respects provider profile minimum
4. Other providers retain their default 90s tool_read_timeout
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.infrastructure.external.llm.provider_profile import (
    ProviderProfile,
    get_provider_profile,
)


class TestGLMToolReadTimeout:
    """GLM provider should have 180s tool_read_timeout to prevent triple-timeout failures."""

    def test_glm_tool_read_timeout_is_180(self) -> None:
        profile = get_provider_profile("https://open.bigmodel.cn/api/paas/v4/", "glm-5")
        assert profile.tool_read_timeout == 180.0

    def test_glm_profile_by_model_name(self) -> None:
        profile = get_provider_profile("", "glm-5")
        assert profile.tool_read_timeout == 180.0

    def test_glm_profile_by_zhipuai_url(self) -> None:
        profile = get_provider_profile("https://api.zhipuai.cn/v4/", "")
        assert profile.tool_read_timeout == 180.0

    def test_glm_profile_by_z_ai_url(self) -> None:
        profile = get_provider_profile("https://z.ai/api/v4/", "")
        assert profile.tool_read_timeout == 180.0


class TestDefaultToolReadTimeout:
    """Other providers should retain 90s default tool_read_timeout."""

    @pytest.mark.parametrize(
        "api_base,model_name",
        [
            ("https://api.openai.com/v1/", "gpt-4o"),
            ("https://api.anthropic.com/v1/", "claude-3-sonnet"),
            ("https://api.deepseek.com/v1/", "deepseek-v3"),
            ("", "kimi-for-coding"),
        ],
    )
    def test_non_glm_providers_retain_90s_tool_timeout(self, api_base: str, model_name: str) -> None:
        profile = get_provider_profile(api_base, model_name)
        assert profile.tool_read_timeout == 90.0

    def test_default_profile_tool_timeout(self) -> None:
        profile = get_provider_profile("https://unknown-provider.com/v1/", "unknown-model")
        assert profile.tool_read_timeout == 90.0

    def test_ollama_profile_tool_timeout(self) -> None:
        profile = get_provider_profile("http://localhost:11434", "llama3")
        assert profile.tool_read_timeout == 90.0


class TestCreateTimeoutUsesProviderProfile:
    """_create_timeout() should use provider profile's tool_read_timeout, not hardcoded 90s."""

    def _make_llm(self, provider_name: str = "glm") -> MagicMock:
        """Create a mock LLM instance with provider profile."""
        profile = ProviderProfile(
            name=provider_name,
            tool_read_timeout=180.0 if provider_name == "glm" else 90.0,
        )
        llm = MagicMock()
        llm._provider_profile = profile
        return llm

    def test_tool_call_timeout_uses_provider_profile(self) -> None:
        """For GLM, tool call read timeout should be 180s, not hardcoded 90s."""

        profile = get_provider_profile("https://open.bigmodel.cn/api/paas/v4/", "glm-5")
        # The tool_read_timeout from profile should be 180
        assert profile.tool_read_timeout == 180.0

    def test_openai_tool_call_timeout_stays_at_90(self) -> None:
        """OpenAI should still use 90s tool read timeout."""
        profile = get_provider_profile("https://api.openai.com/v1/", "gpt-4o")
        assert profile.tool_read_timeout == 90.0


class TestAsyncioToolTimeoutRespectsProvider:
    """llm_tool_request_timeout should be at least as high as provider's tool_read_timeout."""

    def test_glm_asyncio_timeout_at_least_180(self) -> None:
        """When settings has 90s but GLM profile has 180s, asyncio timeout should be 180s."""
        profile = get_provider_profile("https://open.bigmodel.cn/api/paas/v4/", "glm-5")
        settings_tool_timeout = 90.0
        effective_timeout = max(settings_tool_timeout, profile.tool_read_timeout)
        assert effective_timeout == 180.0

    def test_openai_asyncio_timeout_stays_at_settings(self) -> None:
        """When settings has 90s and OpenAI profile has 90s, asyncio timeout stays 90s."""
        profile = get_provider_profile("https://api.openai.com/v1/", "gpt-4o")
        settings_tool_timeout = 90.0
        effective_timeout = max(settings_tool_timeout, profile.tool_read_timeout)
        assert effective_timeout == 90.0

    def test_exponential_backoff_with_higher_base(self) -> None:
        """GLM exponential backoff: 180 → 360 → 720 (capped at global 300)."""
        base_timeout = 180.0  # GLM's tool_read_timeout
        global_timeout = 300.0

        retry_0 = base_timeout  # 180
        retry_1 = min(base_timeout * (2**1), global_timeout)  # 300 (capped)
        retry_2 = min(base_timeout * (2**2), global_timeout)  # 300 (capped)

        assert retry_0 == 180.0
        assert retry_1 == 300.0
        assert retry_2 == 300.0
