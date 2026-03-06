"""Tests for proactive schema sanitization on strict providers."""

from __future__ import annotations

from app.infrastructure.external.llm.provider_profile import ProviderProfile, get_provider_profile


class TestProviderProfileStrictSchema:
    """strict_schema field on provider profiles."""

    def test_kimi_has_strict_schema(self):
        profile = get_provider_profile("https://api.kimi.com/coding/v1", "kimi-for-coding")
        assert profile.strict_schema is True

    def test_glm_has_strict_schema(self):
        profile = get_provider_profile("https://open.bigmodel.cn/api/v4", "glm-5")
        assert profile.strict_schema is True

    def test_openai_not_strict(self):
        profile = get_provider_profile("https://api.openai.com/v1", "gpt-4o")
        assert profile.strict_schema is False

    def test_default_not_strict(self):
        profile = get_provider_profile("https://unknown.example.com", "unknown-model")
        assert profile.strict_schema is False

    def test_deepseek_not_strict(self):
        profile = get_provider_profile("https://api.deepseek.com/v1", "deepseek-chat")
        assert profile.strict_schema is False

    def test_anthropic_not_strict(self):
        profile = get_provider_profile("https://api.anthropic.com/v1", "claude-3-5-sonnet-20241022")
        assert profile.strict_schema is False

    def test_ollama_not_strict(self):
        profile = get_provider_profile("http://localhost:11434/v1", "llama3")
        assert profile.strict_schema is False


class TestNeedsProactiveSanitize:
    """_needs_proactive_sanitize should match strict_schema."""

    def test_strict_provider_needs_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = ProviderProfile(name="test", strict_schema=True)
        assert OpenAILLM._needs_proactive_sanitize(profile) is True

    def test_non_strict_provider_no_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = ProviderProfile(name="test", strict_schema=False)
        assert OpenAILLM._needs_proactive_sanitize(profile) is False

    def test_missing_attribute_no_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = type("P", (), {"name": "fake"})()
        assert OpenAILLM._needs_proactive_sanitize(profile) is False

    def test_kimi_profile_needs_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = get_provider_profile("https://api.kimi.com/coding/v1", "kimi-for-coding")
        assert OpenAILLM._needs_proactive_sanitize(profile) is True

    def test_glm_profile_needs_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = get_provider_profile("https://open.bigmodel.cn/api/v4", "glm-4-flash")
        assert OpenAILLM._needs_proactive_sanitize(profile) is True

    def test_openai_profile_no_sanitize(self):
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        profile = get_provider_profile("https://api.openai.com/v1", "gpt-4o")
        assert OpenAILLM._needs_proactive_sanitize(profile) is False
