"""Regression tests for the summarization handoff and context-reset fix.

Chunk 1 of the deep-research reliability plan.

The pre-fix bug: plan_act.py mutates self.executor.system_prompt += ...
three times in the SUMMARIZING handler (workspace deliverables, session files,
artifact manifest). But BaseAgent._add_to_memory only writes a system
message when memory is empty. At SUMMARIZING time memory is already
populated, so the mutated system_prompt never reaches the LLM.

The fix: build an explicit summarization-context payload and pass it
directly into ExecutionAgent.summarize() as a parameter.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.models.memory import ConversationMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor_with_memory() -> MagicMock:
    """Mock executor with real ConversationMemory (pre-populated, non-empty)."""
    executor = MagicMock()
    executor.system_prompt = "BASE_SYSTEM_PROMPT"
    executor.memory = ConversationMemory()
    # Pre-populate so memory.empty is False (simulates prior execution steps)
    executor.memory.add_message({"role": "system", "content": "INITIAL_PROMPT"})
    executor.memory.add_message({"role": "user", "content": "step 1"})
    executor.memory.add_message({"role": "assistant", "content": "step 1 done"})
    executor._user_request = None
    executor._research_depth = "STANDARD"
    executor._artifact_references = []
    executor._collected_sources = []
    return executor


# ---------------------------------------------------------------------------
# Test 1: system_prompt mutations are invisible to memory
# ---------------------------------------------------------------------------


class TestSystemPromptMutationInvisible:
    """The core bug: mutating system_prompt after memory exists has no effect
    on the message list that the LLM sees."""

    def test_single_mutation_not_in_messages(self) -> None:
        executor = _make_executor_with_memory()
        executor.system_prompt += "\n\n## Workspace Deliverables\nfile1.md\nfile2.md"

        assert "Workspace Deliverables" in executor.system_prompt
        all_contents = [m["content"] for m in executor.memory.get_messages()]
        assert not any("Workspace Deliverables" in c for c in all_contents)

    def test_mutation_invisible_after_add_messages(self) -> None:
        executor = _make_executor_with_memory()
        assert executor.memory.empty is False

        executor.system_prompt += "\n\n## Artifact Manifest\n- report.md"
        executor.memory.add_messages([{"role": "user", "content": "Write report."}])

        system_msgs = [m for m in executor.memory.get_messages() if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "Artifact Manifest" not in system_msgs[0]["content"]

    def test_three_mutations_all_invisible(self) -> None:
        executor = _make_executor_with_memory()
        executor.system_prompt += "\n\n## Workspace Deliverables\nfile1.md"
        executor.system_prompt += "\n\n## Session Deliverables\nfile2.md"
        executor.system_prompt += "\n\n## Deliverables\n- report.md"

        combined = " ".join(m["content"] for m in executor.memory.get_messages())
        assert "Workspace Deliverables" not in combined
        assert "Session Deliverables" not in combined
        assert "report.md" not in combined


# ---------------------------------------------------------------------------
# Test 2: build_summarization_context produces correct payload
# ---------------------------------------------------------------------------


class TestBuildSummarizationContext:
    """Test the PlanActFlow helper that builds the explicit summarization context."""

    def test_builds_context_from_workspace_listing(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        workspace_listing = "report.md  (1234 bytes)\nchart.png  (5678 bytes)"
        attachments = [
            {"filename": "report.md", "storage_key": "reports/report.md"},
            {"filename": "chart.png", "storage_key": "charts/chart.png"},
        ]

        context = PlanActFlow._build_summarization_context(
            workspace_listing=workspace_listing,
            attachments=attachments,
        )

        assert "Workspace Deliverables" in context
        assert "report.md" in context
        assert "chart.png" in context
        assert "Deliverables" in context

    def test_builds_context_without_workspace_listing(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        attachments = [
            {"filename": "report.md", "storage_key": "reports/report.md"},
        ]

        context = PlanActFlow._build_summarization_context(
            workspace_listing=None,
            attachments=attachments,
        )

        assert "Deliverables" in context
        assert "report.md" in context

    def test_builds_empty_context_when_nothing_provided(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing=None,
            attachments=None,
        )

        assert context == ""

    def test_builds_context_from_session_files_listing(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        session_files_listing = "- report.md (1,234 bytes) — text/markdown\n- data.csv (5,678 bytes) — text/csv"

        context = PlanActFlow._build_summarization_context(
            session_files_listing=session_files_listing,
        )

        assert "Session Deliverables" in context
        assert "report.md" in context
        assert "data.csv" in context
        assert "1,234 bytes" in context

    def test_workspace_listing_takes_priority_over_session_files(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing="ws-file.md  (100 bytes)",
            session_files_listing="- session-file.md (200 bytes)",
        )

        assert "Workspace Deliverables" in context
        assert "ws-file.md" in context
        assert "Session Deliverables" not in context
        assert "session-file.md" not in context

    def test_all_three_parts_combined(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        context = PlanActFlow._build_summarization_context(
            workspace_listing="report.md  (1234 bytes)",
            session_files_listing="- data.csv (5678 bytes)",
            attachments=[{"filename": "chart.png"}],
        )

        assert "Workspace Deliverables" in context
        assert "report.md" in context
        assert "chart.png" in context


# ---------------------------------------------------------------------------
# Test 3: summarize() receives and uses explicit context
# ---------------------------------------------------------------------------


class TestSummarizeContextReachesLLM:
    """Verify that summarize() puts summarization_context into the messages
    that reach the LLM."""

    @pytest.mark.asyncio
    async def test_context_appears_in_added_messages(self) -> None:
        from app.domain.services.agents.execution import ExecutionAgent

        class _StopSummarizeError(Exception):
            """Sentinel exception used to stop after the first memory write."""

        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent._user_request = "Compare React vs Vue"
        agent._research_depth = "DEEP"
        agent._collected_sources = []
        agent._response_policy = None
        agent._artifact_references = []
        agent._set_response_generator_artifact_references = MagicMock()

        agent.memory = ConversationMemory()
        agent.memory.add_message({"role": "system", "content": "INITIAL_PROMPT"})

        added_contents: list[str] = []

        async def _track_add(msgs: list[dict]) -> None:
            added_contents.extend(m.get("content", "") for m in msgs)
            agent.memory.add_messages(msgs)
            raise _StopSummarizeError

        agent._add_to_memory = _track_add

        summarization_ctx = "## Workspace Deliverables\nreport.md\n\n## Deliverables\n- report-abc.md"

        with pytest.raises(_StopSummarizeError):
            async for _ev in agent.summarize(
                summarization_context=summarization_ctx,
                all_steps_completed=True,
            ):
                pass

        combined = " ".join(added_contents)
        assert "Workspace Deliverables" in combined, (
            f"Expected 'Workspace Deliverables' in added messages, got: {combined[:500]}"
        )
        assert "report-abc.md" in combined, f"Expected 'report-abc.md' in added messages, got: {combined[:500]}"
