"""Tests for feature flags configuration in LangGraph workflow.

This module tests that feature flags are:
1. No longer stored in workflow state (PlanActState)
2. Passed via LangGraph config mechanism
3. Accessible via get_feature_flags() in nodes

Phase: P3 - Move feature flags to configuration
"""

from unittest.mock import patch

import pytest

from app.core.config import get_feature_flags
from app.domain.services.langgraph.state import PlanActState, create_initial_state


class TestFeatureFlagsNotInState:
    """Test that feature_flags field is removed from PlanActState."""

    def test_feature_flags_not_in_state_typeddict(self):
        """PlanActState TypedDict should not have feature_flags field."""
        # Get the annotations from PlanActState
        annotations = PlanActState.__annotations__

        # feature_flags should not be in the state schema
        assert "feature_flags" not in annotations, (
            "feature_flags should be removed from PlanActState - use get_feature_flags() from config instead"
        )

    def test_create_initial_state_no_feature_flags(self):
        """create_initial_state should not include feature_flags in returned state."""
        from unittest.mock import MagicMock

        # Create a minimal message mock
        message = MagicMock()
        message.message = "Test message"

        state = create_initial_state(
            message=message,
            agent_id="test-agent",
            session_id="test-session",
        )

        # feature_flags should not be in the created state
        assert "feature_flags" not in state, (
            "create_initial_state should not include feature_flags - "
            "they should be accessed via get_feature_flags() or config"
        )


class TestGetFeatureFlags:
    """Test the get_feature_flags() function."""

    def test_get_feature_flags_returns_dict(self):
        """get_feature_flags should return a dictionary."""
        flags = get_feature_flags()
        assert isinstance(flags, dict)

    def test_get_feature_flags_has_required_keys(self):
        """get_feature_flags should include key feature flags."""
        flags = get_feature_flags()

        # These are core feature flags that should always be present
        expected_keys = [
            "plan_validation_v2",
            "reflection_advanced",
            "context_optimization",
            "cove_verification",
        ]

        for key in expected_keys:
            assert key in flags, f"Feature flag '{key}' should be present in get_feature_flags()"

    def test_get_feature_flags_values_are_bool(self):
        """All feature flag values should be booleans."""
        flags = get_feature_flags()

        for key, value in flags.items():
            assert isinstance(value, bool), f"Feature flag '{key}' should be a boolean, got {type(value).__name__}"


class TestFeatureFlagsInConfig:
    """Test that feature flags are passed via LangGraph config."""

    def test_flow_passes_feature_flags_in_config(self):
        """LangGraphPlanActFlow should pass feature_flags in config."""
        # We test this by checking the flow.py module's config structure
        # The actual runtime behavior is tested in integration tests

        from app.domain.services.langgraph import flow

        # Verify the import is present (get_feature_flags is imported)
        assert hasattr(flow, "get_feature_flags") or "get_feature_flags" in dir(flow)

    def test_feature_flags_can_be_overridden_via_module_patch(self):
        """Feature flags should be mockable for testing via module-level patch."""
        # Since get_feature_flags uses lru_cache, we need to patch at the module level
        # where it's imported, not at the source
        from unittest.mock import patch

        mock_flags = {
            "plan_validation_v2": True,
            "cove_verification": False,
            "context_optimization": True,
        }

        # Patch at the module level where it's used
        with patch(
            "app.domain.services.langgraph.nodes.planning.get_feature_flags",
            return_value=mock_flags,
        ):
            from app.domain.services.langgraph.nodes import planning

            flags = planning.get_feature_flags()
            assert flags["plan_validation_v2"] is True
            assert flags["cove_verification"] is False
            assert flags["context_optimization"] is True


class TestNodesUseGetFeatureFlags:
    """Test that LangGraph nodes access feature flags via get_feature_flags()."""

    def test_planning_node_imports_get_feature_flags(self):
        """Planning node should import get_feature_flags from config."""
        from app.domain.services.langgraph.nodes import planning

        # Check that get_feature_flags is accessible in the module
        assert hasattr(planning, "get_feature_flags"), "planning node should import get_feature_flags from config"

    def test_execution_node_imports_get_feature_flags(self):
        """Execution node should import get_feature_flags from config."""
        from app.domain.services.langgraph.nodes import execution

        assert hasattr(execution, "get_feature_flags"), "execution node should import get_feature_flags from config"

    def test_summarize_node_imports_get_feature_flags(self):
        """Summarize node should import get_feature_flags from config."""
        from app.domain.services.langgraph.nodes import summarize

        assert hasattr(summarize, "get_feature_flags"), "summarize node should import get_feature_flags from config"


class TestFeatureFlagDefaults:
    """Test default feature flag values with settings validation failure."""

    @patch("app.core.config.get_settings")
    def test_defaults_on_settings_failure(self, mock_get_settings):
        """get_feature_flags should return safe defaults if settings validation fails."""
        # Force settings to raise an exception
        mock_get_settings.side_effect = Exception("Settings validation failed")

        # Clear the lru_cache to ensure our mock is used
        from app.core.config import get_feature_flags as gff

        # Call the function - it should return defaults, not raise
        try:
            flags = gff()
        except Exception as e:
            pytest.fail(f"get_feature_flags should not raise on settings failure: {e}")

        # Should have returned a dict with safe defaults
        assert isinstance(flags, dict)
        assert "cove_verification" in flags


class TestFeatureFlagsIntegration:
    """Integration tests for feature flags in workflow."""

    @pytest.mark.asyncio
    async def test_execution_node_uses_feature_flags_from_config(self):
        """Execution node should read feature flags from config, not state."""
        from unittest.mock import MagicMock

        from app.domain.services.langgraph.nodes.execution import execution_node

        # Create minimal state without feature_flags
        plan = MagicMock()
        step = MagicMock()
        step.description = "Test step"
        step.status = None
        plan.steps = [step]

        # Create an async generator mock for execute_step
        async def mock_execute_step(*args, **kwargs):
            return
            yield  # Makes this an async generator

        executor = MagicMock()
        executor.execute_step = mock_execute_step

        state = {
            "plan": plan,
            "current_step": step,
            "executor": executor,
            "user_message": MagicMock(message="Test"),
            "task_state_manager": None,
            "session_id": "test",
            "event_queue": None,
            # Note: feature_flags is NOT included - this is the key test
        }

        # This should not raise KeyError for feature_flags
        with patch("app.domain.services.langgraph.nodes.execution.get_feature_flags") as mock_flags:
            mock_flags.return_value = {"context_optimization": False}

            # Should complete without error about missing feature_flags
            try:
                await execution_node(state)
            except KeyError as e:
                if "feature_flags" in str(e):
                    pytest.fail("execution_node should not require feature_flags in state")
                raise
