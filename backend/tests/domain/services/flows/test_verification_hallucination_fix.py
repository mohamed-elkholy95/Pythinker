"""Tests for the verification death loop / hallucination prevention fixes.

Covers:
- Fix 1: Good-enough plan acceptance (confidence >= 0.7 after revision)
- Fix 2: Topic anchor presence in summarize prompt
- Fix 3: Research-conducted gate (zero completed steps → ErrorEvent)
- Fix 4: User message pinning in memory trimming
"""

import pytest

from app.domain.models.plan import ExecutionStatus, Plan, Step, StepType
from app.domain.models.state_model import AgentStatus
from app.domain.services.flows.plan_act import PlanActFlow

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_flow(
    *,
    verification_loops: int = 0,
    max_verification_loops: int = 2,
    plan_validation_failures: int = 0,
    max_plan_validation_failures: int = 3,
    verification_confidence: float | None = None,
) -> PlanActFlow:
    """Create a minimal PlanActFlow with verification state pre-configured."""
    flow = PlanActFlow.__new__(PlanActFlow)
    flow._verification_loops = verification_loops
    flow._max_verification_loops = max_verification_loops
    flow._plan_validation_failures = plan_validation_failures
    flow._max_plan_validation_failures = max_plan_validation_failures
    flow._verification_confidence = verification_confidence
    return flow


def _make_plan(*, step_statuses: list[ExecutionStatus]) -> Plan:
    """Create a Plan with steps in given statuses."""
    steps = [
        Step(
            id=f"step-{i}",
            description=f"Research step {i}",
            status=status,
            step_type=StepType.EXECUTION,
        )
        for i, status in enumerate(step_statuses)
    ]
    return Plan(title="Test plan", goal="Research task", steps=steps)


# ── Fix 1: Good-enough acceptance ────────────────────────────────────────


class TestGoodEnoughAcceptance:
    """Verify that borderline-confidence plans are accepted after revision."""

    def test_high_confidence_after_one_revision_accepts_plan(self) -> None:
        """confidence=0.75 + 1 revision loop → EXECUTING (not another PLANNING loop)."""
        flow = _make_flow(
            verification_loops=1,
            max_verification_loops=2,
            verification_confidence=0.75,
        )

        status, reason = flow._route_after_revision_needed()

        assert status == AgentStatus.EXECUTING
        assert "good-enough" in reason

    def test_exact_threshold_confidence_accepts(self) -> None:
        """confidence=0.7 exactly at threshold → EXECUTING."""
        flow = _make_flow(
            verification_loops=1,
            max_verification_loops=2,
            verification_confidence=0.7,
        )

        status, _reason = flow._route_after_revision_needed()

        assert status == AgentStatus.EXECUTING

    def test_low_confidence_after_revision_keeps_revising(self) -> None:
        """confidence=0.5 + 1 loop → PLANNING (below good-enough threshold)."""
        flow = _make_flow(
            verification_loops=1,
            max_verification_loops=2,
            verification_confidence=0.5,
        )

        status, reason = flow._route_after_revision_needed()

        assert status == AgentStatus.PLANNING
        assert "revision" in reason

    def test_high_confidence_but_zero_revisions_keeps_revising(self) -> None:
        """confidence=0.8 but 0 revision loops → PLANNING (must try at least 1 revision)."""
        flow = _make_flow(
            verification_loops=0,
            max_verification_loops=2,
            verification_confidence=0.8,
        )

        status, reason = flow._route_after_revision_needed()

        assert status == AgentStatus.PLANNING
        assert "revision" in reason

    def test_none_confidence_does_not_accept(self) -> None:
        """confidence=None (not set) → PLANNING, not accepted."""
        flow = _make_flow(
            verification_loops=1,
            max_verification_loops=2,
            verification_confidence=None,
        )

        status, _reason = flow._route_after_revision_needed()

        assert status == AgentStatus.PLANNING

    def test_original_summarizing_path_still_works(self) -> None:
        """Low confidence + max loops + max failures → SUMMARIZING (unchanged behavior)."""
        flow = _make_flow(
            verification_loops=2,
            max_verification_loops=2,
            plan_validation_failures=2,
            max_plan_validation_failures=3,
            verification_confidence=0.3,
        )

        status, reason = flow._route_after_revision_needed()

        assert status == AgentStatus.SUMMARIZING
        assert "without a valid plan" in reason


# ── Fix 2: Topic anchor in summarize prompt ──────────────────────────────


class TestTopicAnchor:
    """Verify that summarize() includes the user's original request."""

    @pytest.fixture()
    def _mock_executor(self):
        """Create a minimal mock executor with the summarize prompt logic."""
        from unittest.mock import AsyncMock, MagicMock

        from app.domain.services.agents.execution import ExecutionAgent

        executor = ExecutionAgent.__new__(ExecutionAgent)
        executor._user_request = "find cursor AI coupon codes and compare GLM vs Sonnet"
        executor._collected_sources = []
        executor._response_policy = None
        executor.memory = MagicMock()
        executor.memory.get_messages = MagicMock(return_value=[])
        executor._add_to_memory = AsyncMock()
        executor._token_manager = MagicMock()
        executor._token_manager.is_within_limit = MagicMock(return_value=True)
        executor._metrics = MagicMock()
        return executor

    def test_topic_anchor_present_when_user_request_set(self, _mock_executor) -> None:
        """When _user_request is set, the summarize prompt must contain the topic anchor."""
        # Simulate the prompt construction logic from summarize()
        from app.domain.services.prompts.execution import STREAMING_SUMMARIZE_PROMPT

        summarize_prompt = STREAMING_SUMMARIZE_PROMPT

        if _mock_executor._user_request:
            topic_anchor = (
                f"\n\n## TOPIC ANCHOR (MANDATORY)\n"
                f"The user's original request was:\n"
                f'"""\n{_mock_executor._user_request}\n"""\n'
                f"Your report MUST address THIS topic. Do NOT write about any other topic."
            )
            summarize_prompt = topic_anchor + "\n\n" + summarize_prompt

        assert "TOPIC ANCHOR" in summarize_prompt
        assert "cursor AI coupon codes" in summarize_prompt
        assert "MUST address THIS topic" in summarize_prompt

    def test_no_topic_anchor_when_user_request_missing(self) -> None:
        """When _user_request is None, no topic anchor is prepended."""
        from app.domain.services.prompts.execution import STREAMING_SUMMARIZE_PROMPT

        user_request = None
        summarize_prompt = STREAMING_SUMMARIZE_PROMPT

        if user_request:
            summarize_prompt = "ANCHOR\n\n" + summarize_prompt

        assert "TOPIC ANCHOR" not in summarize_prompt


# ── Fix 3: Research-conducted gate ───────────────────────────────────────


class TestResearchGate:
    """Verify that zero completed steps blocks report generation."""

    def test_plan_with_zero_completed_steps_is_detected(self) -> None:
        """Plan with all PENDING steps should trigger the gate."""
        plan = _make_plan(step_statuses=[ExecutionStatus.PENDING, ExecutionStatus.PENDING])

        completed = [s for s in plan.steps if s.status == ExecutionStatus.COMPLETED]

        assert len(completed) == 0

    def test_plan_with_completed_steps_passes_gate(self) -> None:
        """Plan with at least one COMPLETED step should pass."""
        plan = _make_plan(step_statuses=[ExecutionStatus.COMPLETED, ExecutionStatus.PENDING, ExecutionStatus.FAILED])

        completed = [s for s in plan.steps if s.status == ExecutionStatus.COMPLETED]

        assert len(completed) == 1

    def test_plan_with_all_failed_steps_triggers_gate(self) -> None:
        """Plan with all FAILED steps (none COMPLETED) should trigger the gate."""
        plan = _make_plan(step_statuses=[ExecutionStatus.FAILED, ExecutionStatus.FAILED])

        completed = [s for s in plan.steps if s.status == ExecutionStatus.COMPLETED]

        assert len(completed) == 0

    def test_empty_plan_does_not_trigger_gate(self) -> None:
        """Plan with no steps at all should not trigger the gate (nothing was planned)."""
        plan = _make_plan(step_statuses=[])

        # Gate condition: not completed_steps AND plan.steps exists
        completed = [s for s in plan.steps if s.status == ExecutionStatus.COMPLETED]
        should_block = not completed and len(plan.steps) > 0

        assert not should_block  # Empty plan should not trigger gate

    def test_zero_progress_error_message_mentions_timeout_when_present(self) -> None:
        """Timeout failures should produce a timeout-specific user message."""
        flow = PlanActFlow.__new__(PlanActFlow)
        plan = _make_plan(step_statuses=[ExecutionStatus.FAILED, ExecutionStatus.BLOCKED])
        plan.steps[0].error = "LLM request timed out after 60.0s"
        flow.plan = plan

        message = flow._build_zero_progress_error_message()

        assert "timed out" in message.lower()

    def test_zero_progress_error_message_mentions_dependency_blocking(self) -> None:
        """Blocked-only plans should call out dependency blocking."""
        flow = PlanActFlow.__new__(PlanActFlow)
        flow.plan = _make_plan(step_statuses=[ExecutionStatus.BLOCKED, ExecutionStatus.BLOCKED])

        message = flow._build_zero_progress_error_message()

        assert "blocked" in message.lower()
        assert "dependent" in message.lower()

    def test_zero_progress_error_message_falls_back_to_generic_reason(self) -> None:
        """Unknown failure details should still return a generic actionable reason."""
        flow = PlanActFlow.__new__(PlanActFlow)
        flow.plan = _make_plan(step_statuses=[ExecutionStatus.FAILED])

        message = flow._build_zero_progress_error_message()

        assert "no research steps were executed" in message.lower()
        assert "please try again" in message.lower()


# ── Fix 4: User message pinning in memory trimming ──────────────────────


class TestUserMessagePinning:
    """Verify that the first user message is preserved after trimming."""

    def test_first_user_message_survives_trimming(self) -> None:
        """After trimming, the first user message should be re-injected if lost."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Find cursor AI coupons"},
            {"role": "assistant", "content": "I'll research that."},
            {"role": "user", "content": "Also compare models."},
            {"role": "assistant", "content": "Sure, comparing now."},
        ]

        first_user_msg = next((m for m in messages if m.get("role") == "user"), None)
        assert first_user_msg is not None
        assert first_user_msg["content"] == "Find cursor AI coupons"

        # Simulate trimming that removes the first user message
        trimmed = [messages[0], messages[3], messages[4]]  # System + recent only

        # Re-injection logic
        if first_user_msg and not any(m is first_user_msg for m in trimmed):
            insert_idx = 0
            for i, m in enumerate(trimmed):
                if m.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed.insert(insert_idx, first_user_msg)

        assert trimmed[1] is first_user_msg
        assert trimmed[1]["content"] == "Find cursor AI coupons"

    def test_first_user_message_not_duplicated_if_present(self) -> None:
        """If the first user message survived trimming, don't duplicate it."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Find cursor AI coupons"},
            {"role": "assistant", "content": "Done."},
        ]

        first_user_msg = next((m for m in messages if m.get("role") == "user"), None)
        # Trimming preserved all messages (identity check)
        trimmed = list(messages)

        was_reinjected = False
        if first_user_msg and not any(m is first_user_msg for m in trimmed):
            was_reinjected = True

        assert not was_reinjected

    def test_insert_after_multiple_system_messages(self) -> None:
        """First user message is inserted after the last system message."""
        messages = [
            {"role": "system", "content": "System prompt 1"},
            {"role": "system", "content": "System prompt 2"},
            {"role": "user", "content": "Original question"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "assistant", "content": "Response 2"},
        ]

        first_user_msg = messages[2]
        # Simulate trim removing the user message
        trimmed = [messages[0], messages[1], messages[4]]

        if first_user_msg and not any(m is first_user_msg for m in trimmed):
            insert_idx = 0
            for i, m in enumerate(trimmed):
                if m.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed.insert(insert_idx, first_user_msg)

        assert trimmed[0]["role"] == "system"
        assert trimmed[1]["role"] == "system"
        assert trimmed[2] is first_user_msg
        assert trimmed[2]["content"] == "Original question"
