"""Tests for app.domain.models.step_execution_context — step execution context.

Covers: PromptSignalConfig defaults, StepExecutionContext creation and immutability.
"""

from __future__ import annotations

import pytest

from app.domain.models.step_execution_context import (
    PromptSignalConfig,
    StepExecutionContext,
)


class TestPromptSignalConfig:
    """Tests for PromptSignalConfig defaults and fields."""

    def test_defaults(self):
        config = PromptSignalConfig()
        assert config.enable_cot is True
        assert config.include_current_date is True
        assert config.enable_source_attribution is True
        assert config.enable_intent_guidance is True
        assert config.enable_anti_hallucination is True

    def test_custom_values(self):
        config = PromptSignalConfig(enable_cot=False, include_current_date=False)
        assert config.enable_cot is False
        assert config.include_current_date is False
        assert config.enable_source_attribution is True

    def test_frozen(self):
        config = PromptSignalConfig()
        with pytest.raises(AttributeError):
            config.enable_cot = False  # type: ignore[misc]

    def test_all_disabled(self):
        config = PromptSignalConfig(
            enable_cot=False,
            include_current_date=False,
            enable_source_attribution=False,
            enable_intent_guidance=False,
            enable_anti_hallucination=False,
        )
        assert config.enable_cot is False
        assert config.enable_anti_hallucination is False


class TestStepExecutionContext:
    """Tests for StepExecutionContext creation and immutability."""

    def _make_ctx(self, **kwargs) -> StepExecutionContext:
        defaults = {
            "step_description": "Search for information",
            "user_message": "Find recent AI papers",
            "attachments": "",
            "language": "en",
        }
        defaults.update(kwargs)
        return StepExecutionContext(**defaults)

    def test_minimal_creation(self):
        ctx = self._make_ctx()
        assert ctx.step_description == "Search for information"
        assert ctx.user_message == "Find recent AI papers"
        assert ctx.language == "en"

    def test_optional_fields_default_to_none(self):
        ctx = self._make_ctx()
        assert ctx.pressure_signal is None
        assert ctx.task_state is None
        assert ctx.memory_context is None
        assert ctx.search_context is None
        assert ctx.conversation_context is None
        assert ctx.working_context_summary is None
        assert ctx.synthesized_context is None
        assert ctx.error_pattern_signal is None
        assert ctx.locked_entity_reminder is None
        assert ctx.report_output_path is None
        assert ctx.mcp_context is None
        assert ctx.profile_patch_text is None

    def test_blocker_warnings_default_empty(self):
        ctx = self._make_ctx()
        assert ctx.blocker_warnings == []

    def test_signal_config_default(self):
        ctx = self._make_ctx()
        assert isinstance(ctx.signal_config, PromptSignalConfig)
        assert ctx.signal_config.enable_cot is True

    def test_frozen(self):
        ctx = self._make_ctx()
        with pytest.raises(AttributeError):
            ctx.step_description = "modified"  # type: ignore[misc]

    def test_with_all_optional_fields(self):
        ctx = self._make_ctx(
            pressure_signal="high",
            task_state="executing",
            memory_context="user prefers dark mode",
            search_context="found 5 results",
            conversation_context="last turn: user asked about AI",
            working_context_summary="summary of work",
            synthesized_context="synthesized info",
            blocker_warnings=["rate limit approaching"],
            error_pattern_signal="timeout pattern detected",
            locked_entity_reminder="entity X is locked",
            report_output_path="/tmp/report.md",
            mcp_context="mcp servers: tool-x",
            profile_patch_text="patch text",
        )
        assert ctx.pressure_signal == "high"
        assert ctx.blocker_warnings == ["rate limit approaching"]
        assert ctx.mcp_context == "mcp servers: tool-x"

    def test_custom_signal_config(self):
        config = PromptSignalConfig(enable_cot=False)
        ctx = self._make_ctx(signal_config=config)
        assert ctx.signal_config.enable_cot is False

    def test_multiple_blocker_warnings(self):
        ctx = self._make_ctx(blocker_warnings=["warn1", "warn2", "warn3"])
        assert len(ctx.blocker_warnings) == 3

    def test_slots_enabled(self):
        ctx = self._make_ctx()
        assert hasattr(ctx, "__slots__")
