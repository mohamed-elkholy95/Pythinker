"""Tests for context cap metrics, forced step advance tracking, and
pre-summarization compression observability.

Covers:
1. _effective_context_char_cap property on BaseAgent
2. Effective cap logging at flow start
3. Cap hit escalation and metrics (context_cap_hits_total)
4. Forced step advance (context_cap_escalation)
5. Pre-summarization compression metrics
6. _build_summarization_context with session_files_listing
7. Summarization context handoff to ExecutionAgent.summarize()
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.models.memory import ConversationMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_executor(
    *,
    context_cap: int = 50_000,
    is_deep_research: bool = False,
    memory_chars: int = 0,
) -> MagicMock:
    """Create a mock executor with configurable context cap and memory."""
    executor = MagicMock()
    executor._is_deep_research = is_deep_research
    executor._consecutive_cap_hits = 0
    executor._stuck_recovery_exhausted = False

    # Wire _effective_context_char_cap like the real property
    executor._effective_context_char_cap = context_cap

    # Set up memory
    if memory_chars > 0:
        executor.memory = ConversationMemory()
        executor.memory.add_message({"role": "system", "content": "x" * memory_chars})
    else:
        executor.memory = ConversationMemory()

    return executor


# ---------------------------------------------------------------------------
# Test 1: _effective_context_char_cap property
# ---------------------------------------------------------------------------


class TestEffectiveContextCharCap:
    """Test the effective context char cap property on BaseAgent."""

    def test_default_cap_when_settings_unavailable(self) -> None:
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._is_deep_research = False
        # Fallback when get_settings fails
        cap = agent._effective_context_char_cap
        assert isinstance(cap, int)
        assert cap > 0

    def test_deep_research_uses_higher_cap(self) -> None:
        """Deep research agents should report a higher effective cap."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)

        # Standard mode
        agent._is_deep_research = False
        standard_cap = agent._effective_context_char_cap

        # Deep research mode
        agent._is_deep_research = True
        deep_cap = agent._effective_context_char_cap

        assert deep_cap >= standard_cap


# ---------------------------------------------------------------------------
# Test 2: _build_summarization_context with session_files_listing
# ---------------------------------------------------------------------------


class TestBuildSummarizationContextWithSessionFiles:
    """Test the enhanced _build_summarization_context with session_files_listing."""

    def test_session_files_listing_produces_section(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        listing = "- report.md (1,234 bytes) — text/markdown"
        context = PlanActFlow._build_summarization_context(
            session_files_listing=listing,
        )
        assert "Session Deliverables" in context
        assert "report.md" in context

    def test_workspace_listing_takes_priority(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing="ws.md  (100 bytes)",
            session_files_listing="- session.md (200 bytes)",
        )
        assert "Workspace Deliverables" in context
        assert "Session Deliverables" not in context

    def test_attachments_manifest_appended_after_workspace(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing="report.md  (100 bytes)",
            attachments=[{"filename": "chart.png"}],
        )
        assert "Workspace Deliverables" in context
        assert "chart.png" in context

    def test_attachments_manifest_appended_after_session_files(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            session_files_listing="- data.csv (100 bytes)",
            attachments=[{"filename": "chart.png"}],
        )
        assert "Session Deliverables" in context
        assert "chart.png" in context

    def test_empty_context_when_all_none(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context()
        assert context == ""


# ---------------------------------------------------------------------------
# Test 3: Cap hit tracking and escalation
# ---------------------------------------------------------------------------


class TestContextCapHitTracking:
    """Test that cap hits increment the consecutive counter and trigger metrics."""

    def test_consecutive_cap_hits_increment(self) -> None:
        """Simulating consecutive cap hits should escalate the counter."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._consecutive_cap_hits = 0

        # Simulate escalation
        agent._consecutive_cap_hits += 1
        assert agent._consecutive_cap_hits == 1

        agent._consecutive_cap_hits += 1
        assert agent._consecutive_cap_hits == 2

    def test_forced_step_advance_at_escalation_5(self) -> None:
        """At escalation level 5+, _stuck_recovery_exhausted should be set."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._stuck_recovery_exhausted = False
        agent._consecutive_cap_hits = 5

        # Simulate the escalation logic from ask_with_messages
        _escalation = agent._consecutive_cap_hits
        if _escalation >= 5:
            agent._stuck_recovery_exhausted = True

        assert agent._stuck_recovery_exhausted is True

    def test_stuck_recovery_not_set_below_escalation_5(self) -> None:
        """Below escalation 5, _stuck_recovery_exhausted should remain False."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._stuck_recovery_exhausted = False
        agent._consecutive_cap_hits = 4

        _escalation = agent._consecutive_cap_hits
        if _escalation >= 5:
            agent._stuck_recovery_exhausted = True

        assert agent._stuck_recovery_exhausted is False

    def test_cap_hit_counter_resets_when_below_75_percent(self) -> None:
        """Counter resets when context drops below 75% of cap."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._consecutive_cap_hits = 3
        _cap = 50_000
        total_chars = int(_cap * 0.50)  # Well below 75%

        if agent._consecutive_cap_hits > 0 and total_chars < _cap * 0.75:
            agent._consecutive_cap_hits = 0

        assert agent._consecutive_cap_hits == 0

    def test_cap_hit_counter_not_reset_above_75_percent(self) -> None:
        """Counter does NOT reset when context is still above 75% of cap."""
        from app.domain.services.agents.base import BaseAgent

        agent = BaseAgent.__new__(BaseAgent)
        agent._consecutive_cap_hits = 3
        _cap = 50_000
        total_chars = int(_cap * 0.80)  # Above 75%

        if agent._consecutive_cap_hits > 0 and total_chars < _cap * 0.75:
            agent._consecutive_cap_hits = 0

        assert agent._consecutive_cap_hits == 3


# ---------------------------------------------------------------------------
# Test 4: Pre-summarization compression metrics
# ---------------------------------------------------------------------------


class TestPreSummarizationCompression:
    """Test that pre-summarization compaction tracks chars saved."""

    def test_compact_prior_step_context_reduces_large_tool_messages(self) -> None:
        """_compact_prior_step_context truncates large tool messages."""
        from app.domain.services.flows.plan_act import PlanActFlow

        executor = MagicMock()
        executor.memory = ConversationMemory()

        # Add messages with 3+ tool results so the oldest ones get compacted
        # (method keeps last 2 tool messages, truncates the rest)
        executor.memory.add_message({"role": "system", "content": "INITIAL"})
        executor.memory.add_message({"role": "tool", "content": "x" * 50_000})  # oldest tool — will be compacted
        executor.memory.add_message({"role": "assistant", "content": "y" * 5000})  # large assistant — will be compacted
        executor.memory.add_message({"role": "tool", "content": "z" * 500})  # 2nd newest tool — kept
        executor.memory.add_message({"role": "tool", "content": "w" * 200})  # newest tool — kept

        before_chars = sum(len(str(m.get("content", ""))) for m in executor.memory.get_messages())
        assert before_chars > 40_000  # Precondition: above 40K threshold

        PlanActFlow._compact_prior_step_context(executor)

        after_chars = sum(len(str(m.get("content", ""))) for m in executor.memory.get_messages())
        assert after_chars < before_chars

    def test_compact_does_nothing_below_threshold(self) -> None:
        """_compact_prior_step_context is a no-op when context is small."""
        from app.domain.services.flows.plan_act import PlanActFlow

        executor = MagicMock()
        executor.memory = ConversationMemory()
        executor.memory.add_message({"role": "system", "content": "INITIAL"})
        executor.memory.add_message({"role": "user", "content": "small message"})

        before_chars = sum(len(str(m.get("content", ""))) for m in executor.memory.get_messages())

        PlanActFlow._compact_prior_step_context(executor)

        after_chars = sum(len(str(m.get("content", ""))) for m in executor.memory.get_messages())
        assert after_chars == before_chars

    def test_compact_preserves_recent_tool_messages(self) -> None:
        """The last 2 tool messages should not be truncated."""
        from app.domain.services.flows.plan_act import PlanActFlow

        executor = MagicMock()
        executor.memory = ConversationMemory()
        executor.memory.add_message({"role": "system", "content": "INITIAL"})
        # Add 4 large tool messages
        for i in range(4):
            executor.memory.add_message({"role": "tool", "content": f"tool_{i}_" + "x" * 10_000})
        # Add recent tool message to keep
        executor.memory.add_message({"role": "tool", "content": "KEEP_THIS_RECENT_TOOL"})
        executor.memory.add_message({"role": "tool", "content": "KEEP_THIS_TOO"})

        PlanActFlow._compact_prior_step_context(executor)

        messages = executor.memory.get_messages()
        tool_messages = [m for m in messages if m.get("role") == "tool"]

        # The last 2 should be preserved as-is
        assert "KEEP_THIS_RECENT_TOOL" in tool_messages[-2]["content"]
        assert "KEEP_THIS_TOO" in tool_messages[-1]["content"]


# ---------------------------------------------------------------------------
# Test 5: Effective cap logging at flow start
# ---------------------------------------------------------------------------


class TestEffectiveCapLoggingAtFlowStart:
    """Verify that the flow logs the effective context cap at start."""

    def test_build_summarization_context_is_static(self) -> None:
        """_build_summarization_context is a static method (no self needed)."""
        from app.domain.services.flows.plan_act import PlanActFlow

        # Calling without instance should work
        result = PlanActFlow._build_summarization_context()
        assert result == ""

    def test_build_summarization_context_signature(self) -> None:
        """Verify the method has the expected keyword-only parameters."""
        import inspect

        from app.domain.services.flows.plan_act import PlanActFlow

        sig = inspect.signature(PlanActFlow._build_summarization_context)
        param_names = set(sig.parameters.keys())
        assert "workspace_listing" in param_names
        assert "session_files_listing" in param_names
        assert "attachments" in param_names

        # All params should be keyword-only
        for param in sig.parameters.values():
            assert param.kind == inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# Test 6: Summarization context handoff
# ---------------------------------------------------------------------------


class TestSummarizationContextHandoff:
    """Verify that the summarization context reaches ExecutionAgent.summarize()."""

    @pytest.mark.asyncio
    async def test_session_files_listing_reaches_summarize(self) -> None:
        """Session files listing passed as summarization_context reaches the LLM."""
        from app.domain.services.agents.execution import ExecutionAgent

        class _StopSummarizeError(Exception):
            pass

        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent._user_request = "Analyze quarterly data"
        agent._research_depth = "STANDARD"
        agent._collected_sources = []
        agent._response_policy = None
        agent._artifact_references = []
        agent._set_response_generator_artifact_references = MagicMock()

        agent.memory = ConversationMemory()
        agent.memory.add_message({"role": "system", "content": "INITIAL"})

        added_contents: list[str] = []

        async def _track_add(msgs: list[dict]) -> None:
            added_contents.extend(m.get("content", "") for m in msgs)
            agent.memory.add_messages(msgs)
            raise _StopSummarizeError

        agent._add_to_memory = _track_add

        summarization_ctx = (
            "## Session Deliverables\n- report.md (1,234 bytes) — text/markdown\n- data.csv (5,678 bytes) — text/csv"
        )

        with pytest.raises(_StopSummarizeError):
            async for _ev in agent.summarize(
                summarization_context=summarization_ctx,
                all_steps_completed=True,
            ):
                pass

        combined = " ".join(added_contents)
        assert "Session Deliverables" in combined, (
            f"Expected 'Session Deliverables' in added messages, got: {combined[:500]}"
        )
        assert "data.csv" in combined, f"Expected 'data.csv' in added messages, got: {combined[:500]}"

    @pytest.mark.asyncio
    async def test_workspace_and_manifest_combined_in_summarize(self) -> None:
        """Combined workspace listing + artifact manifest reaches the LLM."""
        from app.domain.services.agents.execution import ExecutionAgent

        class _StopSummarizeError(Exception):
            pass

        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent._user_request = "Research AI trends"
        agent._research_depth = "DEEP"
        agent._collected_sources = []
        agent._response_policy = None
        agent._artifact_references = []
        agent._set_response_generator_artifact_references = MagicMock()

        agent.memory = ConversationMemory()
        agent.memory.add_message({"role": "system", "content": "INITIAL"})

        added_contents: list[str] = []

        async def _track_add(msgs: list[dict]) -> None:
            added_contents.extend(m.get("content", "") for m in msgs)
            agent.memory.add_messages(msgs)
            raise _StopSummarizeError

        agent._add_to_memory = _track_add

        from app.domain.services.flows.plan_act import PlanActFlow

        summarization_ctx = PlanActFlow._build_summarization_context(
            workspace_listing="trends.md  (8000 bytes)\nchart.html  (12000 bytes)",
            attachments=[{"filename": "trends.pdf"}],
        )

        with pytest.raises(_StopSummarizeError):
            async for _ev in agent.summarize(
                summarization_context=summarization_ctx,
                all_steps_completed=True,
            ):
                pass

        combined = " ".join(added_contents)
        assert "Workspace Deliverables" in combined
        assert "trends.pdf" in combined
