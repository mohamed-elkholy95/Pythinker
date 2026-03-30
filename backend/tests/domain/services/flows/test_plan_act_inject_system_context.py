"""Tests for PlanActFlow._inject_system_context — prompt injection with memory visibility.

Validates that:
1. Context is appended to agent.system_prompt
2. If memory is non-empty, the system message in memory is also patched
3. If memory is empty, only system_prompt is mutated (baseline behavior)
4. Prometheus metrics are recorded
5. Empty context is a no-op
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.models.memory import ConversationMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_with_memory(*, empty: bool = False) -> MagicMock:
    """Mock agent with real ConversationMemory.

    Args:
        empty: When True, memory starts empty (no messages).
    """
    agent = MagicMock(spec=["system_prompt", "memory", "name"])
    agent.system_prompt = "BASE_SYSTEM_PROMPT"
    agent.name = "executor"
    agent.memory = ConversationMemory()
    if not empty:
        agent.memory.add_message({"role": "system", "content": "INITIAL_PROMPT"})
        agent.memory.add_message({"role": "user", "content": "step 1"})
        agent.memory.add_message({"role": "assistant", "content": "step 1 done"})
    return agent


# ---------------------------------------------------------------------------
# Test: _inject_system_context basics
# ---------------------------------------------------------------------------


class TestInjectSystemContext:
    """Test PlanActFlow._inject_system_context."""

    def test_appends_to_system_prompt(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=True)
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx = "\n\n## Extra Context\nDo this."
        with patch("app.core.prometheus_metrics.record_system_prompt_injection"):
            flow._inject_system_context(agent, ctx, source="test_source")

        assert agent.system_prompt == "BASE_SYSTEM_PROMPT\n\n## Extra Context\nDo this."

    def test_patches_system_message_in_nonempty_memory(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=False)
        assert agent.memory.empty is False
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx = "\n\n## Profile Patch\nNew instructions."
        with patch("app.core.prometheus_metrics.record_system_prompt_injection"):
            flow._inject_system_context(agent, ctx, source="profile_patch")

        # system_prompt should be extended
        assert "Profile Patch" in agent.system_prompt

        # The system message in memory should also be patched
        system_msgs = [m for m in agent.memory.get_messages() if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "Profile Patch" in system_msgs[0]["content"]
        assert system_msgs[0]["content"].startswith("INITIAL_PROMPT")

    def test_no_memory_patch_when_memory_empty(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=True)
        assert agent.memory.empty is True
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx = "\n\n## Workspace Context\nSave files here."
        with patch("app.core.prometheus_metrics.record_system_prompt_injection"):
            flow._inject_system_context(agent, ctx, source="workspace")

        # system_prompt should be extended
        assert "Workspace Context" in agent.system_prompt

        # No system message in memory yet — nothing to patch
        system_msgs = [m for m in agent.memory.get_messages() if m["role"] == "system"]
        assert len(system_msgs) == 0

    def test_empty_context_is_noop(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=False)
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        with patch("app.core.prometheus_metrics.record_system_prompt_injection") as mock_record:
            flow._inject_system_context(agent, "", source="workspace")
            flow._inject_system_context(agent, None, source="workspace")  # type: ignore[arg-type]

        # system_prompt unchanged
        assert agent.system_prompt == "BASE_SYSTEM_PROMPT"
        # No metric recorded
        mock_record.assert_not_called()

    def test_records_metric(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=True)
        agent.name = "planner"
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx = "\n\n## Deep Research\nBrowser-first strategy."
        with patch("app.core.prometheus_metrics.record_system_prompt_injection") as mock_record:
            flow._inject_system_context(agent, ctx, source="deep_research")

        mock_record.assert_called_once_with(
            agent="planner",
            source="deep_research",
            size_bytes=len(ctx),
        )

    def test_multiple_injections_accumulate(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = _make_agent_with_memory(empty=False)
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx1 = "\n\n## First\nContext one."
        ctx2 = "\n\n## Second\nContext two."

        with patch("app.core.prometheus_metrics.record_system_prompt_injection"):
            flow._inject_system_context(agent, ctx1, source="first")
            flow._inject_system_context(agent, ctx2, source="second")

        # Both contexts in system_prompt
        assert "First" in agent.system_prompt
        assert "Second" in agent.system_prompt

        # Both contexts in memory system message
        system_msgs = [m for m in agent.memory.get_messages() if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "First" in system_msgs[0]["content"]
        assert "Second" in system_msgs[0]["content"]
        assert system_msgs[0]["content"].startswith("INITIAL_PROMPT")

    def test_handles_agent_without_memory_gracefully(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        agent = MagicMock(spec=["system_prompt", "name"])
        agent.system_prompt = "BASE"
        agent.name = "executor"
        # No memory attribute at all
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        ctx = "\n\n## Test\nContent."
        with patch("app.core.prometheus_metrics.record_system_prompt_injection"):
            flow._inject_system_context(agent, ctx, source="test")

        assert "Test" in agent.system_prompt


# ---------------------------------------------------------------------------
# Test: Metric recording integration
# ---------------------------------------------------------------------------


class TestInjectionMetrics:
    """Test that _inject_system_context records Prometheus metrics correctly."""

    def test_metric_source_labels(self) -> None:
        from app.domain.services.flows.plan_act import PlanActFlow

        sources = ["workspace", "profile_patch", "deep_research"]
        flow = object.__new__(PlanActFlow)
        flow._agent_id = "test-agent"
        flow._session_id = "test-session"

        for source in sources:
            agent = _make_agent_with_memory(empty=True)
            agent.name = "executor"
            ctx = f"## {source}\nSome content."

            with patch("app.core.prometheus_metrics.record_system_prompt_injection") as mock_record:
                flow._inject_system_context(agent, ctx, source=source)

            mock_record.assert_called_once_with(
                agent="executor",
                source=source,
                size_bytes=len(ctx),
            )
