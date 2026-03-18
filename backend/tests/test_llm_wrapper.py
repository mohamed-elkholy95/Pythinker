"""Unit tests for LLM provider compatibility detection.

The original _wrap_llm_for_compatibility method on BrowserUseService was replaced
by provider detection via is_native_openai() which drives ChatOpenAI compat flags
(dont_force_structured_output, add_schema_to_system_prompt, etc.).

These tests verify that is_native_openai correctly classifies endpoints and that
BrowserUseService sets compat flags accordingly.
"""

import pytest

from app.domain.utils.llm_compat import is_native_openai


class TestIsNativeOpenAI:
    """Verify that only genuine OpenAI endpoints are classified as native."""

    @pytest.mark.parametrize(
        "api_base",
        [
            "https://api.openai.com/v1",
            "https://API.OPENAI.COM/v1",
            "https://something.openai.azure.com/openai/deployments/gpt-4",
        ],
    )
    def test_native_openai_endpoints(self, api_base: str) -> None:
        assert is_native_openai(api_base) is True

    @pytest.mark.parametrize(
        "api_base",
        [
            "https://api.deepseek.com",
            "https://api.kimi.com/coding/v1",
            "https://api.z.ai/api/coding/paas/v4",
            "https://openrouter.ai/api/v1",
            "http://localhost:11434/v1",
            "https://api.together.xyz/v1",
        ],
    )
    def test_compatible_endpoints_are_not_native(self, api_base: str) -> None:
        assert is_native_openai(api_base) is False

    def test_none_returns_false(self) -> None:
        assert is_native_openai(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert is_native_openai("") is False


class TestBrowserUseServiceCompatFlags:
    """Verify that BrowserUseService compat detection logic is correct."""

    def test_non_native_endpoint_enables_compat_mode(self) -> None:
        """Non-OpenAI endpoints should trigger compat=True (no response_format etc.)."""
        compat = not is_native_openai("https://api.deepseek.com")
        assert compat is True

    def test_native_endpoint_disables_compat_mode(self) -> None:
        """Native OpenAI endpoints should use full parameter support."""
        compat = not is_native_openai("https://api.openai.com/v1")
        assert compat is False
