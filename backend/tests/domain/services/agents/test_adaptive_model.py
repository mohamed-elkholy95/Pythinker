"""Tests for adaptive model selection (DeepCode Phase 1).

Context7 validated:
- pytest fixture patterns
- ComplexityAssessor integration
- Settings mock patterns
"""

from unittest.mock import MagicMock, patch

from app.domain.services.agents.complexity_assessor import (
    ComplexityAssessor,
    ModelTier,
)


class TestModelTierRecommendation:
    """Test model tier recommendation based on step descriptions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.assessor = ComplexityAssessor()

    def test_fast_tier_for_summaries(self):
        """Fast tier selected for summaries and simple transforms."""
        step_description = "Summarize the results from the search"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.FAST

    def test_fast_tier_for_status_checks(self):
        """Fast tier selected for status checks and listings."""
        step_description = "Show the current status of the task"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.FAST

    def test_powerful_tier_for_architecture(self):
        """Powerful tier selected for architecture and design."""
        step_description = "Design the architecture for the new microservice"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.POWERFUL

    def test_powerful_tier_for_refactoring(self):
        """Powerful tier selected for refactoring tasks."""
        step_description = "Refactor the authentication module for better performance"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.POWERFUL

    def test_balanced_tier_for_standard_execution(self):
        """Balanced tier selected for standard execution steps."""
        step_description = "Execute the search query and collect results"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.BALANCED

    def test_balanced_tier_default_fallback(self):
        """Balanced tier as default for ambiguous steps."""
        step_description = "Do something with the data"
        tier = self.assessor.recommend_model_tier(step_description)
        assert tier == ModelTier.BALANCED


class TestExecutionAgentModelSelection:
    """Test ExecutionAgent model selection integration."""

    @patch("app.domain.services.agents.execution.get_settings")
    def test_feature_flag_disabled_returns_none(self, mock_get_settings):
        """When feature flag disabled, no model override is returned."""
        from app.domain.services.agents.execution import ExecutionAgent

        # Mock settings with feature disabled
        settings = MagicMock()
        settings.adaptive_model_selection_enabled = False
        mock_get_settings.return_value = settings

        # Create minimal ExecutionAgent instance (without full initialization)
        agent = MagicMock(spec=ExecutionAgent)
        agent._select_model_for_step = ExecutionAgent._select_model_for_step.__get__(agent)
        agent.name = "execution"

        # Call model selection
        result = agent._select_model_for_step("Design a new feature")

        # Should return None when disabled
        assert result is None

    @patch("app.domain.services.agents.execution.get_settings")
    @patch("app.domain.services.agents.execution._metrics")
    def test_feature_flag_enabled_returns_model(self, mock_metrics, mock_get_settings):
        """When feature flag enabled, returns appropriate model based on tier."""
        from app.domain.services.agents.execution import ExecutionAgent

        # Mock settings with feature enabled
        settings = MagicMock()
        settings.adaptive_model_selection_enabled = True
        settings.fast_model = "claude-haiku-4-5"
        settings.powerful_model = "claude-sonnet-4-5"
        settings.effective_balanced_model = "nvidia/nemotron-3-nano-30b-a3b"
        mock_get_settings.return_value = settings

        # Create minimal ExecutionAgent instance
        agent = MagicMock(spec=ExecutionAgent)
        agent._select_model_for_step = ExecutionAgent._select_model_for_step.__get__(agent)
        agent.name = "execution"

        # Test fast tier selection
        result = agent._select_model_for_step("Summarize the results")
        assert result == "claude-haiku-4-5"

        # Test powerful tier selection
        result = agent._select_model_for_step("Design the architecture")
        assert result == "claude-sonnet-4-5"

        # Test balanced tier selection
        result = agent._select_model_for_step("Execute the search query")
        assert result == "nvidia/nemotron-3-nano-30b-a3b"

    @patch("app.domain.services.agents.execution.get_settings")
    @patch("app.domain.services.agents.execution._metrics")
    def test_prometheus_metrics_incremented(self, mock_metrics, mock_get_settings):
        """Prometheus counter incremented on each selection."""
        from app.domain.services.agents.execution import ExecutionAgent

        # Mock settings with feature enabled
        settings = MagicMock()
        settings.adaptive_model_selection_enabled = True
        settings.fast_model = "claude-haiku-4-5"
        settings.powerful_model = "claude-sonnet-4-5"
        settings.effective_balanced_model = "nvidia/nemotron-3-nano-30b-a3b"
        mock_get_settings.return_value = settings

        # Create minimal ExecutionAgent instance
        agent = MagicMock(spec=ExecutionAgent)
        agent._select_model_for_step = ExecutionAgent._select_model_for_step.__get__(agent)
        agent.name = "execution"

        # Call model selection
        agent._select_model_for_step("Summarize the results")

        # Verify metrics increment was called
        mock_metrics.increment.assert_called_once()
        call_args = mock_metrics.increment.call_args
        assert call_args[0][0] == "pythinker_model_tier_selections_total"
        assert call_args[1]["labels"]["tier"] == "fast"
        assert call_args[1]["labels"]["agent"] == "execution"
