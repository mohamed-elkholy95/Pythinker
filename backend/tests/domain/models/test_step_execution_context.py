"""Tests for StepExecutionContext and PromptSignalConfig domain models."""

import dataclasses

import pytest

from app.domain.models.step_execution_context import (
    PromptSignalConfig,
    StepExecutionContext,
)


class TestPromptSignalConfig:
    """Tests for PromptSignalConfig frozen dataclass."""

    def test_defaults_all_true(self):
        cfg = PromptSignalConfig()
        assert cfg.enable_cot is True
        assert cfg.include_current_date is True
        assert cfg.enable_source_attribution is True
        assert cfg.enable_intent_guidance is True
        assert cfg.enable_anti_hallucination is True

    def test_frozen_immutability(self):
        cfg = PromptSignalConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.enable_cot = False  # type: ignore[misc]

    def test_custom_values(self):
        cfg = PromptSignalConfig(
            enable_cot=False,
            include_current_date=False,
            enable_source_attribution=False,
            enable_intent_guidance=False,
            enable_anti_hallucination=False,
        )
        assert cfg.enable_cot is False
        assert cfg.include_current_date is False

    def test_equality(self):
        a = PromptSignalConfig()
        b = PromptSignalConfig()
        assert a == b

        c = PromptSignalConfig(enable_cot=False)
        assert a != c


class TestStepExecutionContext:
    """Tests for StepExecutionContext frozen dataclass."""

    def _make_minimal(self, **overrides) -> StepExecutionContext:
        defaults = {
            "step_description": "Research AI models",
            "user_message": "Compare Claude and GPT",
            "attachments": "",
            "language": "en",
        }
        defaults.update(overrides)
        return StepExecutionContext(**defaults)

    def test_minimal_construction(self):
        ctx = self._make_minimal()
        assert ctx.step_description == "Research AI models"
        assert ctx.user_message == "Compare Claude and GPT"
        assert ctx.attachments == ""
        assert ctx.language == "en"

    def test_optional_fields_default_none(self):
        ctx = self._make_minimal()
        assert ctx.pressure_signal is None
        assert ctx.task_state is None
        assert ctx.memory_context is None
        assert ctx.search_context is None
        assert ctx.conversation_context is None
        assert ctx.working_context_summary is None
        assert ctx.synthesized_context is None
        assert ctx.error_pattern_signal is None
        assert ctx.locked_entity_reminder is None

    def test_blocker_warnings_default_empty_list(self):
        ctx = self._make_minimal()
        assert ctx.blocker_warnings == []

    def test_signal_config_default(self):
        ctx = self._make_minimal()
        assert ctx.signal_config == PromptSignalConfig()
        assert ctx.signal_config.enable_cot is True

    def test_frozen_immutability(self):
        ctx = self._make_minimal()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.step_description = "Modified"  # type: ignore[misc]

    def test_full_construction(self):
        cfg = PromptSignalConfig(enable_cot=False)
        ctx = StepExecutionContext(
            step_description="Build API",
            user_message="Create REST endpoints",
            attachments="file1.py\nfile2.py",
            language="en",
            pressure_signal="Context is 85% full",
            task_state="Step 3 of 5",
            memory_context="User prefers REST over GraphQL",
            search_context="FastAPI docs say...",
            conversation_context="[Turn 1] User: Build API",
            working_context_summary="Created models.py",
            synthesized_context="Prior steps established DB schema",
            blocker_warnings=["Auth not configured", "DB not migrated"],
            error_pattern_signal="Watch for import errors",
            locked_entity_reminder="Preserve: FastAPI, Python 3.12",
            signal_config=cfg,
        )
        assert ctx.pressure_signal == "Context is 85% full"
        assert ctx.blocker_warnings == ["Auth not configured", "DB not migrated"]
        assert ctx.signal_config.enable_cot is False

    def test_equality(self):
        a = self._make_minimal()
        b = self._make_minimal()
        assert a == b

    def test_inequality_on_different_data(self):
        a = self._make_minimal()
        b = self._make_minimal(step_description="Different step")
        assert a != b

    def test_factory_isolation(self):
        """Two instances have independent blocker_warnings lists."""
        a = self._make_minimal()
        b = self._make_minimal()
        assert a.blocker_warnings is not b.blocker_warnings

    def test_dataclass_replace(self):
        """dataclasses.replace() works on frozen instances."""
        ctx = self._make_minimal()
        updated = dataclasses.replace(ctx, pressure_signal="Warning: 90% full")
        assert updated.pressure_signal == "Warning: 90% full"
        assert ctx.pressure_signal is None  # Original unchanged
