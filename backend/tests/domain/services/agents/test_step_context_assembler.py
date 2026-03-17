"""Tests for StepContextAssembler service."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.step_execution_context import (
    PromptSignalConfig,
    StepExecutionContext,
)
from app.domain.services.agents.step_context_assembler import StepContextAssembler


def _make_step(**overrides):
    """Create a mock Step object."""
    step = MagicMock()
    step.id = overrides.get("id", "step-1")
    step.description = overrides.get("description", "Research AI models")
    return step


def _make_plan(**overrides):
    """Create a mock Plan object."""
    plan = MagicMock()
    plan.language = overrides.get("language", "en")
    return plan


def _make_message(**overrides):
    """Create a mock Message object."""
    msg = MagicMock()
    msg.message = overrides.get("message", "Compare Claude and GPT")
    msg.attachments = overrides.get("attachments", [])
    return msg


def _make_context_manager():
    """Create a mock ContextManager."""
    cm = MagicMock()
    cm.get_context_summary.return_value = ""
    cm.get_synthesized_context.return_value = ""
    cm.get_blockers.return_value = []
    return cm


def _make_token_manager():
    """Create a mock TokenManager."""
    tm = MagicMock()
    pressure = MagicMock()
    pressure.to_context_signal.return_value = None
    tm.get_context_pressure.return_value = pressure
    return tm


class TestStepContextAssembler:
    """Tests for StepContextAssembler.assemble()."""

    @pytest.fixture
    def assembler(self):
        """Create assembler with mocked dependencies."""
        return StepContextAssembler(
            context_manager=_make_context_manager(),
            token_manager=_make_token_manager(),
        )

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_minimal_assembly(self, mock_epa, mock_tsm, assembler):
        """Minimal assembly with no optional services produces context with only required fields."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert isinstance(ctx, StepExecutionContext)
        assert ctx.step_description == "Research AI models"
        assert ctx.user_message == "Compare Claude and GPT"
        assert ctx.attachments == ""
        assert ctx.language == "en"
        assert ctx.pressure_signal is None
        assert ctx.task_state is None
        assert ctx.memory_context is None
        assert ctx.conversation_context is None
        assert ctx.search_context is None

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_task_state_signal(self, mock_epa, mock_tsm, assembler):
        """Task state signal is retrieved from task state manager."""
        mock_tsm.return_value.get_context_signal.return_value = "Step 3 of 5 complete"
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.task_state == "Step 3 of 5 complete"

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_pressure_signal(self, mock_epa, mock_tsm):
        """Pressure signal is generated when memory messages are provided."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        tm = _make_token_manager()
        pressure = MagicMock()
        pressure.to_context_signal.return_value = "CONTEXT PRESSURE: 85% used"
        tm.get_context_pressure.return_value = pressure

        assembler = StepContextAssembler(
            context_manager=_make_context_manager(),
            token_manager=tm,
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
            memory_messages=[{"role": "user", "content": "test"}],
        )

        assert ctx.pressure_signal == "CONTEXT PRESSURE: 85% used"
        tm.get_context_pressure.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_no_pressure_signal_without_messages(self, mock_epa, mock_tsm, assembler):
        """No pressure signal when no memory messages are provided."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
            memory_messages=None,
        )

        assert ctx.pressure_signal is None

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_memory_context_assembly(self, mock_epa, mock_tsm):
        """Memory context is assembled from similar tasks, error context, and memories."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        memory_service = AsyncMock()
        memory_service.find_similar_tasks.return_value = [
            {"success": True, "content_summary": "Built a REST API"},
        ]
        memory_service.get_error_context.return_value = None
        memory_service.retrieve_for_task.return_value = ["mem1"]
        memory_service.format_memories_for_context.return_value = "User prefers Python"

        assembler = StepContextAssembler(
            context_manager=_make_context_manager(),
            token_manager=_make_token_manager(),
            memory_service=memory_service,
            user_id="user-123",
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.memory_context is not None
        assert "Past Similar Tasks" in ctx.memory_context
        assert "✓ Success" in ctx.memory_context
        assert "User prefers Python" in ctx.memory_context

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_memory_service_failure_returns_none(self, mock_epa, mock_tsm):
        """Memory service failure is caught gracefully, returns None for memory_context."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        memory_service = AsyncMock()
        memory_service.find_similar_tasks.side_effect = RuntimeError("DB down")

        assembler = StepContextAssembler(
            context_manager=_make_context_manager(),
            token_manager=_make_token_manager(),
            memory_service=memory_service,
            user_id="user-123",
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.memory_context is None

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_error_pattern_signal(self, mock_epa, mock_tsm, assembler):
        """Error pattern signal is generated when relevant tools detected."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = ["browser_navigate"]
        mock_epa.return_value.get_proactive_signals.return_value = "Watch for timeout errors"

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.error_pattern_signal == "Watch for timeout errors"

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_conversation_context_passthrough(self, mock_epa, mock_tsm, assembler):
        """Conversation context is passed through to the result."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
            conversation_context="[Turn 1] User: Build an API",
        )

        assert ctx.conversation_context == "[Turn 1] User: Build an API"

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_search_context_passthrough(self, mock_epa, mock_tsm, assembler):
        """Search context is passed through to the result."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
            pre_planning_search_context="FastAPI 0.109 docs...",
        )

        assert ctx.search_context == "FastAPI 0.109 docs..."

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_blocker_warnings(self, mock_epa, mock_tsm):
        """Blockers from context manager appear in blocker_warnings."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        cm = _make_context_manager()
        blocker1 = MagicMock()
        blocker1.content = "Auth not configured"
        blocker2 = MagicMock()
        blocker2.content = "DB not migrated"
        cm.get_blockers.return_value = [blocker1, blocker2]

        assembler = StepContextAssembler(
            context_manager=cm,
            token_manager=_make_token_manager(),
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.blocker_warnings == ["Auth not configured", "DB not migrated"]

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    @patch("app.core.config.get_settings")
    async def test_locked_entity_reminder(self, mock_settings, mock_epa, mock_tsm, assembler):
        """Locked entity reminder is built from request contract."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None
        mock_settings.return_value.enable_search_fidelity_guardrail = True

        contract = MagicMock()
        contract.locked_entities = ["Claude Sonnet 4.5", "Python 3.12"]

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
            request_contract=contract,
        )

        assert ctx.locked_entity_reminder is not None
        assert "Claude Sonnet 4.5" in ctx.locked_entity_reminder
        assert "Python 3.12" in ctx.locked_entity_reminder

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_result_is_frozen(self, mock_epa, mock_tsm, assembler):
        """Returned StepExecutionContext is frozen (immutable)."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.step_description = "Modified"  # type: ignore[misc]

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_custom_signal_config(self, mock_epa, mock_tsm):
        """Custom signal config is preserved in the result."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        cfg = PromptSignalConfig(enable_cot=False, enable_anti_hallucination=False)
        assembler = StepContextAssembler(
            context_manager=_make_context_manager(),
            token_manager=_make_token_manager(),
            signal_config=cfg,
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.signal_config.enable_cot is False
        assert ctx.signal_config.enable_anti_hallucination is False
        assert ctx.signal_config.include_current_date is True  # Default preserved

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_empty_context_summary_becomes_none(self, mock_epa, mock_tsm):
        """Empty string context summary is normalized to None."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        cm = _make_context_manager()
        cm.get_context_summary.return_value = ""
        cm.get_synthesized_context.return_value = ""

        assembler = StepContextAssembler(
            context_manager=cm,
            token_manager=_make_token_manager(),
        )

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=_make_message(),
        )

        assert ctx.working_context_summary is None
        assert ctx.synthesized_context is None

    @pytest.mark.asyncio
    @patch("app.domain.services.agents.task_state_manager.get_task_state_manager")
    @patch("app.domain.services.agents.error_pattern_analyzer.get_error_pattern_analyzer")
    async def test_attachments_joined(self, mock_epa, mock_tsm, assembler):
        """Message attachments are joined with newlines."""
        mock_tsm.return_value.get_context_signal.return_value = None
        mock_epa.return_value.infer_tools_from_description.return_value = []
        mock_epa.return_value.get_proactive_signals.return_value = None

        msg = _make_message(attachments=["file1.py", "file2.py"])

        ctx = await assembler.assemble(
            plan=_make_plan(),
            step=_make_step(),
            message=msg,
        )

        assert ctx.attachments == "file1.py\nfile2.py"
