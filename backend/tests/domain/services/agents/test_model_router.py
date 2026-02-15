"""
Unit tests for ModelRouter (Adaptive Model Selection).

Tests cover:
- ModelConfig validation
- ModelRouter initialization
- Complexity analysis
- Model routing logic
- Settings integration
- Prometheus metrics
- Singleton factory pattern
- Edge cases and error handling
"""

from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.domain.services.agents.model_router import (
    ModelConfig,
    ModelRouter,
    ModelTier,
    TaskComplexity,
    get_model_router,
)

# ============================================================================
# Test Class 1: ModelConfig Validation
# ============================================================================


class TestModelConfigValidation:
    """Test ModelConfig Pydantic validation."""

    def test_model_config_valid(self):
        """Valid ModelConfig should pass validation."""
        config = ModelConfig(
            provider="anthropic",
            model_name="claude-haiku-4-5",
            tier=ModelTier.FAST,
            max_tokens=2048,
            temperature=0.3,
        )
        assert config.provider == "anthropic"
        assert config.model_name == "claude-haiku-4-5"
        assert config.tier == ModelTier.FAST
        assert config.max_tokens == 2048
        assert config.temperature == 0.3

    def test_model_config_defaults(self):
        """ModelConfig should apply default values."""
        config = ModelConfig(
            provider="anthropic",
            model_name="claude-haiku-4-5",
            tier=ModelTier.FAST,
        )
        assert config.max_tokens == 4096  # Default
        assert config.temperature == 0.3  # Default


# ============================================================================
# Test Class 2: ModelRouter Initialization
# ============================================================================


class TestModelRouterInitialization:
    """Test ModelRouter initialization and settings integration."""

    @patch("app.core.config.get_settings")
    def test_init_loads_settings(self, mock_get_settings):
        """ModelRouter should load settings on initialization."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        router = ModelRouter()
        assert router.settings == mock_settings

    @patch("app.core.config.get_settings")
    def test_init_with_metrics(self, mock_get_settings):
        """ModelRouter should accept custom metrics."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        mock_metrics = MagicMock()

        router = ModelRouter(metrics=mock_metrics)
        assert router._metrics == mock_metrics

    @patch("app.core.config.get_settings")
    def test_init_with_force_tier(self, mock_get_settings):
        """ModelRouter should accept force_tier for testing."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        router = ModelRouter(force_tier=ModelTier.FAST)
        assert router.force_tier == ModelTier.FAST


# ============================================================================
# Test Class 3: Complexity Analysis
# ============================================================================


class TestComplexityAnalysis:
    """Test analyze_complexity method."""

    @patch("app.core.config.get_settings")
    def test_analyze_simple_task(self, mock_get_settings):
        """Short, simple tasks should be analyzed as SIMPLE."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        router = ModelRouter()

        assert router.analyze_complexity("list files") == TaskComplexity.SIMPLE
        assert router.analyze_complexity("what is 2+2") == TaskComplexity.SIMPLE
        assert router.analyze_complexity("run command ls") == TaskComplexity.SIMPLE

    @patch("app.core.config.get_settings")
    def test_analyze_complex_task(self, mock_get_settings):
        """Long or research tasks should be analyzed as COMPLEX."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        router = ModelRouter()

        complex_task = "Research the history of AI and compare different approaches to machine learning"
        assert router.analyze_complexity(complex_task) == TaskComplexity.COMPLEX

        design_task = "Design a comprehensive architecture for a distributed system"
        assert router.analyze_complexity(design_task) == TaskComplexity.COMPLEX

    @patch("app.core.config.get_settings")
    def test_analyze_medium_task(self, mock_get_settings):
        """Medium-length tasks should be analyzed as MEDIUM."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        router = ModelRouter()

        medium_task = "Create a function that processes user input and returns results"
        assert router.analyze_complexity(medium_task) == TaskComplexity.MEDIUM

    @patch("app.core.config.get_settings")
    def test_analyze_empty_string(self, mock_get_settings):
        """Empty string should default to MEDIUM."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        router = ModelRouter()

        assert router.analyze_complexity("") == TaskComplexity.MEDIUM


# ============================================================================
# Test Class 4: Model Routing
# ============================================================================


class TestModelRouting:
    """Test route method."""

    @patch("app.core.config.get_settings")
    def test_route_simple_to_fast(self, mock_get_settings):
        """Simple tasks should route to FAST tier when adaptive enabled."""
        mock_settings = MagicMock()
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)
        config = router.route("list files")

        assert config.tier == ModelTier.FAST
        assert config.model_name == "claude-haiku-4-5"

    @patch("app.core.config.get_settings")
    def test_route_complex_to_powerful(self, mock_get_settings):
        """Complex tasks should route to POWERFUL tier when adaptive enabled."""
        mock_settings = MagicMock()
        mock_settings.powerful_model = "claude-sonnet-4-5"
        mock_settings.max_tokens = 8192
        mock_settings.temperature = 0.7
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)
        config = router.route("Research the comprehensive history of AI and analyze trade-offs")

        assert config.tier == ModelTier.POWERFUL
        assert config.model_name == "claude-sonnet-4-5"

    @patch("app.core.config.get_settings")
    def test_route_disabled_uses_balanced(self, mock_get_settings):
        """When adaptive is disabled, should always use BALANCED."""
        mock_settings = MagicMock()
        mock_settings.effective_balanced_model = "gpt-4o"
        mock_settings.temperature = 0.7
        mock_settings.adaptive_model_selection_enabled = False
        mock_get_settings.return_value = mock_settings

        router = ModelRouter()

        # Both simple and complex should use BALANCED when disabled
        config_simple = router.route("list files")
        assert config_simple.tier == ModelTier.BALANCED

        config_complex = router.route("Research AI history")
        assert config_complex.tier == ModelTier.BALANCED


# ============================================================================
# Test Class 5: Force Tier Override
# ============================================================================


class TestForceTierOverride:
    """Test force_tier override for testing."""

    @patch("app.core.config.get_settings")
    def test_force_tier_overrides_analysis(self, mock_get_settings):
        """force_tier should override complexity analysis."""
        mock_settings = MagicMock()
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        router = ModelRouter(force_tier=ModelTier.FAST)

        # Even complex task should use FAST tier
        tier = router.get_tier_for_complexity(TaskComplexity.COMPLEX)
        assert tier == ModelTier.FAST


# ============================================================================
# Test Class 6: Prometheus Metrics
# ============================================================================


class TestPrometheusMetrics:
    """Test Prometheus metrics integration."""

    @patch("app.core.config.get_settings")
    def test_metrics_recorded_on_routing(self, mock_get_settings):
        """Routing should record Prometheus metrics."""
        mock_settings = MagicMock()
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)

        router.route("list files")

        # Should increment counter
        mock_metrics.increment.assert_called_once()
        call_args = mock_metrics.increment.call_args
        assert call_args[0][0] == "pythinker_model_tier_selections_total"
        assert "tier" in call_args[1]["labels"]
        assert "complexity" in call_args[1]["labels"]


# ============================================================================
# Test Class 7: Routing Statistics
# ============================================================================


class TestRoutingStatistics:
    """Test routing statistics tracking."""

    @patch("app.core.config.get_settings")
    def test_stats_tracking(self, mock_get_settings):
        """Router should track routing statistics."""
        mock_settings = MagicMock()
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)

        # Route some tasks
        router.route("list files")  # SIMPLE
        router.route("list files again")  # SIMPLE

        stats = router.get_stats()
        assert stats["total_routed"] == 2
        assert stats["simple_tasks"] == 2

    @patch("app.core.config.get_settings")
    def test_stats_reset(self, mock_get_settings):
        """Router should allow resetting statistics."""
        mock_settings = MagicMock()
        mock_settings.fast_model = "claude-haiku-4-5"
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        mock_metrics = MagicMock()
        router = ModelRouter(metrics=mock_metrics)
        router.route("list files")

        stats_before = router.get_stats()
        assert stats_before["total_routed"] > 0

        router.reset_stats()

        stats_after = router.get_stats()
        assert stats_after["total_routed"] == 0


# ============================================================================
# Test Class 8: Singleton Factory
# ============================================================================


class TestSingletonFactory:
    """Test get_model_router singleton factory."""

    @patch("app.core.config.get_settings")
    def test_singleton_returns_same_instance(self, mock_get_settings):
        """get_model_router should return same instance on multiple calls."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        # Clear singleton
        import app.domain.services.agents.model_router as router_module

        router_module._model_router = None

        router1 = get_model_router()
        router2 = get_model_router()

        assert router1 is router2  # Same object reference


# ============================================================================
# Test Class 9: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("app.core.config.get_settings")
    def test_very_long_task(self, mock_get_settings):
        """Very long tasks should be handled correctly."""
        mock_settings = MagicMock()
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        router = ModelRouter()
        long_task = "x" * 1000

        # Should not crash
        complexity = router.analyze_complexity(long_task)
        assert complexity in [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM, TaskComplexity.COMPLEX]

    @patch("app.core.config.get_settings")
    def test_special_characters(self, mock_get_settings):
        """Tasks with special characters should be handled correctly."""
        mock_settings = MagicMock()
        mock_settings.adaptive_model_selection_enabled = True
        mock_get_settings.return_value = mock_settings

        router = ModelRouter()
        special_task = "List files with chars: <>!@#$%^&*()"

        # Should not crash
        complexity = router.analyze_complexity(special_task)
        assert complexity in [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM, TaskComplexity.COMPLEX]
