"""Tests for LLM middleware feature flag defaults and GLM retry config.

Validates that the 5 middleware feature flags have the correct default values
and that the GLM provider retry config matches other providers on max_attempts.
"""

from app.core.config_features import FeatureFlagsSettingsMixin
from app.core.retry import PROVIDER_RETRY_CONFIGS


class TestMiddlewareFeatureFlagDefaults:
    """Verify middleware feature flag defaults.

    The middleware pipeline is enabled by default for production reliability.
    Other middleware flags default to False until fully validated.
    """

    def test_middleware_pipeline_enabled_by_default(self) -> None:
        mixin = FeatureFlagsSettingsMixin()
        assert mixin.feature_llm_middleware_pipeline is True

    def test_retry_budget_disabled_by_default(self) -> None:
        mixin = FeatureFlagsSettingsMixin()
        assert mixin.feature_llm_retry_budget is False

    def test_health_scoring_disabled_by_default(self) -> None:
        mixin = FeatureFlagsSettingsMixin()
        assert mixin.feature_llm_health_scoring is False

    def test_provider_fallback_disabled_by_default(self) -> None:
        mixin = FeatureFlagsSettingsMixin()
        assert mixin.feature_llm_provider_fallback is False

    def test_dynamic_context_disabled_by_default(self) -> None:
        mixin = FeatureFlagsSettingsMixin()
        assert mixin.feature_llm_dynamic_context is False


class TestGLMRetryConfig:
    """Verify GLM provider retry config after timeout cascade fix."""

    def test_glm_max_attempts_matches_peers(self) -> None:
        """GLM should have max_attempts=3, same as openai/anthropic/deepseek."""
        glm = PROVIDER_RETRY_CONFIGS["glm"]
        assert glm.max_attempts == 3

    def test_glm_max_delay_accommodates_slow_recovery(self) -> None:
        """GLM max_delay should be 60s to handle slow inference recovery."""
        glm = PROVIDER_RETRY_CONFIGS["glm"]
        assert glm.max_delay == 60.0

    def test_glm_base_delay_unchanged(self) -> None:
        """GLM base_delay should remain at 3s (higher than OpenAI's 1s)."""
        glm = PROVIDER_RETRY_CONFIGS["glm"]
        assert glm.base_delay == 3.0

    def test_all_providers_have_configs(self) -> None:
        """Every expected provider must have a retry config."""
        expected = {"default", "glm", "anthropic", "openai", "deepseek", "ollama"}
        assert expected == set(PROVIDER_RETRY_CONFIGS.keys())
