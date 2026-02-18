"""Tests for build_execution_prompt_from_context() — parity and new features."""

from __future__ import annotations

from unittest.mock import patch

from app.domain.models.step_execution_context import (
    PromptSignalConfig,
    StepExecutionContext,
)
from app.domain.services.prompts.execution import (
    build_execution_prompt,
    build_execution_prompt_from_context,
)


def _make_ctx(**overrides) -> StepExecutionContext:
    """Create a minimal StepExecutionContext for testing."""
    defaults = {
        "step_description": "Search for Python tutorials",
        "user_message": "Find Python tutorials",
        "attachments": "",
        "language": "en",
    }
    defaults.update(overrides)
    return StepExecutionContext(**defaults)


class TestParityWithLegacy:
    """Verify build_execution_prompt_from_context produces identical output to legacy."""

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_minimal_parity(self, _mock_date):
        """Minimal prompt with only required fields produces identical output."""
        legacy = build_execution_prompt(
            step="Do something simple",
            message="Hello",
            attachments="",
            language="en",
        )
        ctx = _make_ctx(
            step_description="Do something simple",
            user_message="Hello",
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_with_memory_context_parity(self, _mock_date):
        """Memory context injection produces identical output."""
        memory = "User prefers dark mode"
        legacy = build_execution_prompt(
            step="Simple step",
            message="Hello",
            attachments="",
            language="en",
            memory_context=memory,
        )
        ctx = _make_ctx(
            step_description="Simple step",
            user_message="Hello",
            memory_context=memory,
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_with_conversation_context_parity(self, _mock_date):
        """Conversation context injection produces identical output."""
        conv = "[Turn 1] User: Build API"
        legacy = build_execution_prompt(
            step="Simple step",
            message="Hello",
            attachments="",
            language="en",
            conversation_context=conv,
        )
        ctx = _make_ctx(
            step_description="Simple step",
            user_message="Hello",
            conversation_context=conv,
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_with_all_signals_disabled_parity(self, _mock_date):
        """All signals disabled produces identical output."""
        cfg = PromptSignalConfig(
            enable_cot=False,
            include_current_date=False,
            enable_source_attribution=False,
            enable_intent_guidance=False,
            enable_anti_hallucination=False,
        )
        legacy = build_execution_prompt(
            step="Simple step",
            message="Hello",
            attachments="",
            language="en",
            enable_cot=False,
            include_current_date=False,
            enable_source_attribution=False,
            enable_intent_guidance=False,
            enable_anti_hallucination=False,
        )
        ctx = _make_ctx(
            step_description="Simple step",
            user_message="Hello",
            signal_config=cfg,
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_with_pressure_and_task_state_parity(self, _mock_date):
        """Pressure signal and task state produce identical output."""
        legacy = build_execution_prompt(
            step="Simple step",
            message="Hello",
            attachments="",
            language="en",
            pressure_signal="85% context used",
            task_state="Step 3 of 5",
        )
        ctx = _make_ctx(
            step_description="Simple step",
            user_message="Hello",
            pressure_signal="85% context used",
            task_state="Step 3 of 5",
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_with_search_context_parity(self, _mock_date):
        """Search context produces identical output."""
        legacy = build_execution_prompt(
            step="Simple step",
            message="Hello",
            attachments="",
            language="en",
            search_context="FastAPI 0.109 docs...",
        )
        ctx = _make_ctx(
            step_description="Simple step",
            user_message="Hello",
            search_context="FastAPI 0.109 docs...",
        )
        new = build_execution_prompt_from_context(ctx)
        assert legacy == new


class TestPostPromptAppendages:
    """Test the new post-prompt appendage features in build_execution_prompt_from_context."""

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_working_context_appended(self, _mock_date):
        """Working context summary is appended after the main prompt."""
        ctx = _make_ctx(working_context_summary="Created models.py and routes.py")
        result = build_execution_prompt_from_context(ctx)
        assert "## Working Context" in result
        assert "Created models.py and routes.py" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_synthesized_context_appended(self, _mock_date):
        """Synthesized context is appended after the main prompt."""
        ctx = _make_ctx(synthesized_context="## Prior Step Insights\nDB schema established")
        result = build_execution_prompt_from_context(ctx)
        assert "Prior Step Insights" in result
        assert "DB schema established" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_blocker_warnings_appended(self, _mock_date):
        """Blocker warnings are appended with proper formatting."""
        ctx = _make_ctx(blocker_warnings=["Auth not configured", "DB not migrated"])
        result = build_execution_prompt_from_context(ctx)
        assert "Active Blockers" in result
        assert "- Auth not configured" in result
        assert "- DB not migrated" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_error_pattern_signal_appended(self, _mock_date):
        """Error pattern signal is appended with proper heading."""
        ctx = _make_ctx(error_pattern_signal="Watch for timeout errors in browser tools")
        result = build_execution_prompt_from_context(ctx)
        assert "Proactive Guidance" in result
        assert "Watch for timeout errors" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_locked_entity_reminder_appended(self, _mock_date):
        """Locked entity reminder is appended."""
        reminder = "\n\n## IMPORTANT\nPreserve: Claude Sonnet 4.5, Python 3.12"
        ctx = _make_ctx(locked_entity_reminder=reminder)
        result = build_execution_prompt_from_context(ctx)
        assert "Claude Sonnet 4.5" in result
        assert "Python 3.12" in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_empty_appendages_not_included(self, _mock_date):
        """None/empty appendages don't add to the prompt."""
        ctx = _make_ctx()
        result = build_execution_prompt_from_context(ctx)
        assert "Working Context" not in result
        assert "Active Blockers" not in result
        assert "Proactive Guidance" not in result

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_empty_blocker_list_not_included(self, _mock_date):
        """Empty blocker_warnings list doesn't add a blockers section."""
        ctx = _make_ctx(blocker_warnings=[])
        result = build_execution_prompt_from_context(ctx)
        assert "Active Blockers" not in result


class TestSignalConfigToggles:
    """Test that individual signal config toggles work correctly."""

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_date_disabled(self, mock_date):
        """include_current_date=False skips date injection."""
        cfg = PromptSignalConfig(include_current_date=False)
        ctx = _make_ctx(signal_config=cfg)
        result = build_execution_prompt_from_context(ctx)
        assert "[DATE]" not in result
        mock_date.assert_not_called()

    @patch("app.domain.services.prompts.execution.get_current_date_signal", return_value="[DATE]")
    def test_date_enabled(self, mock_date):
        """include_current_date=True includes date."""
        cfg = PromptSignalConfig(include_current_date=True)
        ctx = _make_ctx(signal_config=cfg)
        result = build_execution_prompt_from_context(ctx)
        assert "[DATE]" in result
