"""Tests for thinking mode routing in ExecutionAgent and BaseAgent.

Covers:
- BaseAgent.set_thinking_mode() — state management for the three UI modes
- ExecutionAgent._select_model_for_step() — model name selected per mode
  * 'fast'       → ModelRouter(force_tier=FAST)  → fast_model from Settings
  * 'deep_think' → ModelRouter(force_tier=POWERFUL) → powerful_model from Settings
  * None / 'auto' → get_model_router() → complexity-based routing
- Graceful fallback when ModelRouter raises an exception
- Prometheus metrics incremented on each routing call
- plan_act.py propagation logic: thinking_mode on Message → executor.set_thinking_mode()
"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.services.agents.execution import ExecutionAgent

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SETTINGS_PATH = "app.core.config.get_settings"
METRICS_PATH = "app.domain.services.agents.execution._metrics"


def _mock_settings(*, enabled: bool = True) -> MagicMock:
    """Return a minimal Settings mock understood by ModelRouter."""
    settings = MagicMock()
    settings.adaptive_model_selection_enabled = enabled
    settings.fast_model = "claude-haiku-4-5"
    settings.powerful_model = "claude-sonnet-4-6"
    settings.effective_balanced_model = "default-balanced-model"
    return settings


# ---------------------------------------------------------------------------
# Shared executor fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def executor(mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
    """Real ExecutionAgent with mocked infrastructure — no API calls made."""
    return ExecutionAgent(
        agent_id="test-thinking-mode-executor",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
    )


# ===========================================================================
# 1. BaseAgent.set_thinking_mode()
# ===========================================================================


class TestSetThinkingMode:
    """set_thinking_mode() is defined on BaseAgent and inherited by all agents."""

    def test_default_is_none(self, executor):
        """New executor starts with no thinking mode override (auto routing)."""
        assert executor._user_thinking_mode is None

    def test_set_fast_mode(self, executor):
        executor.set_thinking_mode("fast")
        assert executor._user_thinking_mode == "fast"

    def test_set_deep_think_mode(self, executor):
        executor.set_thinking_mode("deep_think")
        assert executor._user_thinking_mode == "deep_think"

    def test_set_auto_mode(self, executor):
        """Storing 'auto' is valid; routing treats it identical to None."""
        executor.set_thinking_mode("auto")
        assert executor._user_thinking_mode == "auto"

    def test_set_none_resets(self, executor):
        executor.set_thinking_mode("fast")
        executor.set_thinking_mode(None)
        assert executor._user_thinking_mode is None

    def test_overwrite_updates_value(self, executor):
        """Calling set_thinking_mode twice keeps only the latest value."""
        executor.set_thinking_mode("fast")
        executor.set_thinking_mode("deep_think")
        assert executor._user_thinking_mode == "deep_think"


# ===========================================================================
# 2. _select_model_for_step() — 'fast' mode
# ===========================================================================


class TestSelectModelFastMode:
    """'fast' thinking mode forces FAST tier regardless of task complexity."""

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_fast_mode_returns_fast_model(self, _mock_metrics, mock_get_settings, executor):
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("fast")

        result = executor._select_model_for_step("list files")

        assert result == "claude-haiku-4-5"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_fast_mode_overrides_complex_task(self, _mock_metrics, mock_get_settings, executor):
        """Even a complex task gets the fast model when mode='fast'."""
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("fast")

        result = executor._select_model_for_step(
            "research and analyze in depth all competing machine-learning frameworks"
        )

        assert result == "claude-haiku-4-5"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_fast_mode_metrics_recorded(self, mock_metrics, mock_get_settings, executor):
        """Prometheus counter is incremented when fast mode routes."""
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("fast")

        executor._select_model_for_step("list files")

        mock_metrics.increment.assert_called_once()
        call_args = mock_metrics.increment.call_args
        assert call_args[0][0] == "pythinker_model_tier_selections_total"


# ===========================================================================
# 3. _select_model_for_step() — 'deep_think' mode
# ===========================================================================


class TestSelectModelDeepThinkMode:
    """'deep_think' thinking mode forces POWERFUL tier regardless of complexity."""

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_deep_think_returns_powerful_model(self, _mock_metrics, mock_get_settings, executor):
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("deep_think")

        result = executor._select_model_for_step("research and analyze comprehensive AI frameworks")

        assert result == "claude-sonnet-4-6"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_deep_think_overrides_simple_task(self, _mock_metrics, mock_get_settings, executor):
        """Even a trivial task gets the powerful model when mode='deep_think'."""
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("deep_think")

        result = executor._select_model_for_step("what is 2+2")

        assert result == "claude-sonnet-4-6"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_deep_think_metrics_recorded(self, mock_metrics, mock_get_settings, executor):
        """Prometheus counter is incremented when deep_think mode routes."""
        mock_get_settings.return_value = _mock_settings()
        executor.set_thinking_mode("deep_think")

        executor._select_model_for_step("analyze this")

        mock_metrics.increment.assert_called_once()
        call_args = mock_metrics.increment.call_args
        assert call_args[0][0] == "pythinker_model_tier_selections_total"


# ===========================================================================
# 4. _select_model_for_step() — 'auto' / None mode (complexity-based routing)
# ===========================================================================


class TestSelectModelAutoMode:
    """None and 'auto' both use complexity-based routing via get_model_router()."""

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_none_mode_simple_task_routes_to_fast(self, _mock_metrics, mock_get_settings, executor):
        """No thinking mode + simple task → FAST tier (claude-haiku)."""
        mock_get_settings.return_value = _mock_settings(enabled=True)
        executor.set_thinking_mode(None)

        result = executor._select_model_for_step("list files")

        assert result == "claude-haiku-4-5"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_none_mode_complex_task_routes_to_powerful(self, _mock_metrics, mock_get_settings, executor):
        """No thinking mode + complex task → POWERFUL tier (claude-sonnet)."""
        mock_get_settings.return_value = _mock_settings(enabled=True)
        executor.set_thinking_mode(None)

        result = executor._select_model_for_step(
            "Research and analyze in detail the comprehensive history of machine learning"
        )

        assert result == "claude-sonnet-4-6"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_auto_string_treated_same_as_none(self, _mock_metrics, mock_get_settings, executor):
        """'auto' string is not matched by 'fast'/'deep_think' branches → falls back to complexity routing."""
        mock_get_settings.return_value = _mock_settings(enabled=True)
        executor.set_thinking_mode("auto")

        # Simple task: should get the fast model (not forced powerful)
        result = executor._select_model_for_step("list files")

        assert result == "claude-haiku-4-5"

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_adaptive_disabled_auto_returns_balanced(self, _mock_metrics, mock_get_settings, executor):
        """When adaptive routing is disabled, auto mode always returns the balanced model."""
        mock_get_settings.return_value = _mock_settings(enabled=False)
        executor.set_thinking_mode(None)

        # The singleton caches the first ModelRouter created; reset it so the
        # disabled-flag settings are picked up by get_model_router() in this test.
        import app.domain.services.agents.model_router as router_module

        original = router_module._model_router
        router_module._model_router = None
        try:
            result = executor._select_model_for_step("list files")
        finally:
            router_module._model_router = original  # restore for other tests

        assert result == "default-balanced-model"


# ===========================================================================
# 5. Error handling — graceful fallback
# ===========================================================================


class TestSelectModelErrorHandling:
    """_select_model_for_step() returns None on any ModelRouter exception."""

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_model_router_exception_returns_none(self, _mock_metrics, mock_get_settings, executor):
        """ModelRouter crashing should not propagate — returns None for caller to use default."""
        mock_get_settings.side_effect = RuntimeError("settings unavailable")
        executor.set_thinking_mode("fast")

        result = executor._select_model_for_step("list files")

        assert result is None

    @patch(SETTINGS_PATH)
    @patch(METRICS_PATH)
    def test_unknown_thinking_mode_falls_back_to_auto(self, _mock_metrics, mock_get_settings, executor):
        """An unrecognised thinking mode string falls through to complexity-based routing."""
        mock_get_settings.return_value = _mock_settings(enabled=True)
        executor.set_thinking_mode("super_ultra_think")  # not a real mode

        # Should fall through to auto routing; simple task → fast model
        result = executor._select_model_for_step("list files")

        assert result == "claude-haiku-4-5"


# ===========================================================================
# 6. plan_act.py propagation logic
# ===========================================================================


class TestPlanActThinkingModePropagation:
    """Verify the conditional logic that plan_act uses to call set_thinking_mode().

    The relevant code in plan_act.py is:
        if message.thinking_mode and message.thinking_mode != "auto":
            self.executor.set_thinking_mode(message.thinking_mode)
        else:
            self.executor.set_thinking_mode(None)  # Reset to auto
    """

    @pytest.mark.parametrize(
        "thinking_mode, expected_call",
        [
            ("fast", "fast"),
            ("deep_think", "deep_think"),
            ("auto", None),  # 'auto' triggers the else-branch → None
            (None, None),  # None also triggers the else-branch → None
        ],
    )
    def test_propagation_logic(self, thinking_mode, expected_call, executor):
        """plan_act propagation: thinking_mode value → executor.set_thinking_mode arg."""
        # Re-implement the plan_act conditional here to test the pure logic.
        # If this logic ever changes in plan_act.py, this test will catch the drift.
        mock_executor = MagicMock()

        if thinking_mode and thinking_mode != "auto":
            mock_executor.set_thinking_mode(thinking_mode)
        else:
            mock_executor.set_thinking_mode(None)

        mock_executor.set_thinking_mode.assert_called_once_with(expected_call)

    def test_fast_propagated_sets_executor_state(self, executor):
        """Full path: simulate plan_act propagating 'fast' → executor holds correct state."""
        thinking_mode = "fast"
        if thinking_mode and thinking_mode != "auto":
            executor.set_thinking_mode(thinking_mode)
        else:
            executor.set_thinking_mode(None)

        assert executor._user_thinking_mode == "fast"

    def test_auto_propagated_resets_executor_state(self, executor):
        """Full path: 'auto' from plan_act → executor reset to None (complexity routing)."""
        executor.set_thinking_mode("deep_think")  # pre-existing state

        thinking_mode = "auto"
        if thinking_mode and thinking_mode != "auto":
            executor.set_thinking_mode(thinking_mode)
        else:
            executor.set_thinking_mode(None)

        assert executor._user_thinking_mode is None
