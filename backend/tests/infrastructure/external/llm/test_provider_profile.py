"""Tests for ProviderProfile registry."""

import pytest

from app.infrastructure.external.llm.provider_profile import (
    ProviderProfile,
    get_provider_profile,
)


class TestProviderProfile:
    """Test ProviderProfile frozen dataclass and registry lookup."""

    def test_default_profile_is_conservative(self):
        profile = get_provider_profile("https://unknown-api.example.com/v1", "some-model")
        assert profile.name == "default"
        assert profile.connect_timeout == 10.0
        assert profile.read_timeout == 300.0
        assert profile.supports_json_mode is True
        assert profile.tool_arg_truncation_prone is False

    def test_glm_profile_detected_by_url(self):
        profile = get_provider_profile("https://api.z.ai/api/paas/v4", "glm-5")
        assert profile.name == "glm"
        assert profile.needs_message_merging is True
        assert profile.needs_thinking_suppression is True
        assert profile.tool_arg_truncation_prone is True
        assert profile.requires_orphan_cleanup is True

    def test_glm_profile_detected_by_model_name(self):
        profile = get_provider_profile("https://openrouter.ai/api/v1", "glm-5")
        # URL match takes priority — openrouter URL matches openrouter profile
        # But model name "glm-5" should still be detected
        # Since URL patterns are checked first, openrouter wins here
        # Test with a neutral URL instead
        profile = get_provider_profile("https://some-proxy.example.com/v1", "glm-5")
        assert profile.name == "glm"

    def test_deepseek_profile(self):
        profile = get_provider_profile("https://api.deepseek.com", "deepseek-chat")
        assert profile.name == "deepseek"
        assert profile.read_timeout == 180.0
        assert profile.tool_arg_truncation_prone is False

    def test_openrouter_profile(self):
        profile = get_provider_profile("https://openrouter.ai/api/v1", "qwen/qwen3-coder")
        assert profile.name == "openrouter"
        assert profile.supports_json_mode is True
        assert profile.supports_tool_choice is True

    def test_anthropic_profile(self):
        profile = get_provider_profile("https://api.anthropic.com/v1", "claude-sonnet-4-6")
        assert profile.name == "anthropic"
        assert profile.read_timeout == 180.0

    def test_ollama_profile(self):
        profile = get_provider_profile("http://localhost:11434", "llama3.2")
        assert profile.name == "ollama"
        assert profile.read_timeout == 600.0

    def test_kimi_profile(self):
        profile = get_provider_profile("https://api.kimi.ai/v1", "kimi-k2.5")
        assert profile.name == "kimi"
        assert profile.needs_thinking_suppression is True

    def test_profile_is_frozen(self):
        profile = get_provider_profile("https://api.z.ai/api/paas/v4", "glm-5")
        with pytest.raises(AttributeError):
            profile.name = "hacked"  # type: ignore[misc]

    def test_bigmodel_cn_matches_glm(self):
        profile = get_provider_profile("https://open.bigmodel.cn/api/paas/v4", "glm-4")
        assert profile.name == "glm"
