"""Tests for adaptive model selection (DeepCode Phase 1).

Context7 validated:
- pytest fixture patterns
- ModelRouter integration
- Settings mock patterns
"""

from unittest.mock import MagicMock, patch

from app.domain.services.agents.model_router import (
    ModelConfig,
    ModelRouter,
    ModelTier,
    TaskComplexity,
)

SETTINGS_PATH = "app.core.config.get_settings"


def _mock_settings(*, enabled=True):
    """Create a mock settings object."""
    settings = MagicMock()
    settings.adaptive_model_selection_enabled = enabled
    settings.fast_model = "claude-haiku-4-5"
    settings.powerful_model = "claude-sonnet-4-5"
    settings.effective_balanced_model = "default-model"
    return settings


class TestModelRouterComplexity:
    """Test model tier recommendation based on step descriptions."""

    @patch(SETTINGS_PATH)
    def setup_method(self, method=None, mock_get_settings=None):
        """Set up test fixtures."""
        if mock_get_settings:
            mock_get_settings.return_value = _mock_settings()
        with patch(SETTINGS_PATH, return_value=_mock_settings()):
            self.router = ModelRouter()

    def test_simple_complexity_for_short_tasks(self):
        """Simple complexity for very short tasks."""
        complexity = self.router.analyze_complexity("Check status")
        assert complexity == TaskComplexity.SIMPLE

    def test_complex_complexity_for_architecture(self):
        """Complex complexity for architecture tasks."""
        complexity = self.router.analyze_complexity(
            "Design the architecture for the new microservice with authentication"
        )
        assert complexity == TaskComplexity.COMPLEX

    def test_medium_complexity_default(self):
        """Medium complexity as default for standard tasks."""
        complexity = self.router.analyze_complexity(
            "Write a Python function that processes the uploaded CSV file and extracts key metrics"
        )
        assert complexity == TaskComplexity.MEDIUM

    def test_fast_tier_for_simple(self):
        """Fast tier maps from simple complexity."""
        tier = self.router.get_tier_for_complexity(TaskComplexity.SIMPLE)
        assert tier == ModelTier.FAST

    def test_balanced_tier_for_medium(self):
        """Balanced tier maps from medium complexity."""
        tier = self.router.get_tier_for_complexity(TaskComplexity.MEDIUM)
        assert tier == ModelTier.BALANCED

    def test_powerful_tier_for_complex(self):
        """Powerful tier maps from complex complexity."""
        tier = self.router.get_tier_for_complexity(TaskComplexity.COMPLEX)
        assert tier == ModelTier.POWERFUL


class TestModelRouterRouting:
    """Test ModelRouter.route() with feature flag behavior."""

    @patch(SETTINGS_PATH)
    def test_feature_flag_disabled_returns_balanced(self, mock_get_settings):
        """When feature flag disabled, always returns balanced config."""
        mock_get_settings.return_value = _mock_settings(enabled=False)

        router = ModelRouter()
        config = router.route("Design a complex architecture")

        assert isinstance(config, ModelConfig)
        assert config.tier == ModelTier.BALANCED
        assert config.model_name == "default-model"

    @patch(SETTINGS_PATH)
    def test_feature_flag_enabled_routes_by_complexity(self, mock_get_settings):
        """When feature flag enabled, routes based on complexity."""
        mock_get_settings.return_value = _mock_settings()

        router = ModelRouter()

        # Short task -> fast model
        config = router.route("Check status")
        assert config.tier == ModelTier.FAST
        assert config.model_name == "claude-haiku-4-5"

    @patch(SETTINGS_PATH)
    def test_prometheus_metrics_incremented(self, mock_get_settings):
        """Prometheus counter incremented on each selection."""
        mock_get_settings.return_value = _mock_settings()

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)

        router.route("Check status")

        mock_metrics.increment.assert_called_once()
        call_args = mock_metrics.increment.call_args
        assert call_args[0][0] == "pythinker_model_tier_selections_total"


class TestExecutionAgentModelSelection:
    """Test ExecutionAgent._select_model_for_step integration."""

    @patch(SETTINGS_PATH)
    @patch("app.domain.services.agents.execution._metrics")
    def test_select_model_returns_model_name(self, mock_metrics, mock_get_settings):
        """_select_model_for_step returns a model name string."""
        from app.domain.services.agents.execution import ExecutionAgent
        from app.domain.services.agents.step_executor import StepExecutor

        mock_get_settings.return_value = _mock_settings()

        agent = MagicMock(spec=ExecutionAgent)
        agent._step_executor = StepExecutor(
            context_manager=MagicMock(),
            source_tracker=MagicMock(),
            metrics=mock_metrics,
        )
        agent._select_model_for_step = ExecutionAgent._select_model_for_step.__get__(agent)
        agent._user_thinking_mode = None
        agent.name = "execution"

        result = agent._select_model_for_step("Check status")
        assert isinstance(result, str)
        assert result == "claude-haiku-4-5"
