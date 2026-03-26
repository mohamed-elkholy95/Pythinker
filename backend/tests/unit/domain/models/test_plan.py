"""Tests for Plan, Step, Phase, and ExecutionStatus models.

Covers ExecutionStatus classification methods, Step lifecycle, Plan
navigation (get_next_step, blocked steps, unblocking), Phase status,
and validators.
"""

from app.domain.models.plan import (
    ExecutionStatus,
    Phase,
    PhaseType,
    Plan,
    RetryPolicy,
    Step,
    StepType,
)


# ── ExecutionStatus ──────────────────────────────────────────────────


class TestExecutionStatus:
    """Tests for ExecutionStatus enum and classification methods."""

    def test_all_values(self) -> None:
        assert ExecutionStatus.PENDING == "pending"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.BLOCKED == "blocked"
        assert ExecutionStatus.SKIPPED == "skipped"
        assert ExecutionStatus.TERMINATED == "terminated"

    def test_active_statuses(self) -> None:
        active = ExecutionStatus.get_active_statuses()
        assert "pending" in active
        assert "running" in active
        assert "completed" not in active
        assert "failed" not in active

    def test_terminal_statuses(self) -> None:
        terminal = ExecutionStatus.get_terminal_statuses()
        assert "completed" in terminal
        assert "failed" in terminal
        assert "blocked" in terminal
        assert "skipped" in terminal
        assert "terminated" in terminal
        assert "pending" not in terminal
        assert "running" not in terminal

    def test_success_statuses(self) -> None:
        success = ExecutionStatus.get_success_statuses()
        assert "completed" in success
        assert "skipped" in success
        assert "failed" not in success

    def test_failure_statuses(self) -> None:
        failure = ExecutionStatus.get_failure_statuses()
        assert "failed" in failure
        assert "blocked" in failure
        assert "completed" not in failure

    def test_is_active(self) -> None:
        assert ExecutionStatus.PENDING.is_active() is True
        assert ExecutionStatus.RUNNING.is_active() is True
        assert ExecutionStatus.COMPLETED.is_active() is False
        assert ExecutionStatus.FAILED.is_active() is False

    def test_is_terminal(self) -> None:
        assert ExecutionStatus.COMPLETED.is_terminal() is True
        assert ExecutionStatus.FAILED.is_terminal() is True
        assert ExecutionStatus.BLOCKED.is_terminal() is True
        assert ExecutionStatus.SKIPPED.is_terminal() is True
        assert ExecutionStatus.TERMINATED.is_terminal() is True
        assert ExecutionStatus.PENDING.is_terminal() is False
        assert ExecutionStatus.RUNNING.is_terminal() is False

    def test_is_success(self) -> None:
        assert ExecutionStatus.COMPLETED.is_success() is True
        assert ExecutionStatus.SKIPPED.is_success() is True
        assert ExecutionStatus.FAILED.is_success() is False

    def test_is_failure(self) -> None:
        assert ExecutionStatus.FAILED.is_failure() is True
        assert ExecutionStatus.BLOCKED.is_failure() is True
        assert ExecutionStatus.COMPLETED.is_failure() is False

    def test_status_marks(self) -> None:
        marks = ExecutionStatus.get_status_marks()
        assert marks["pending"] == "[ ]"
        assert marks["running"] == "[→]"
        assert marks["completed"] == "[✓]"
        assert marks["failed"] == "[✗]"
        assert marks["blocked"] == "[!]"
        assert marks["skipped"] == "[-]"
        assert marks["terminated"] == "[⊘]"


# ── RetryPolicy ──────────────────────────────────────────────────────


class TestRetryPolicy:
    """Tests for RetryPolicy defaults."""

    def test_defaults(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 0
        assert policy.backoff_seconds == 2.0
        assert policy.backoff_multiplier == 2.0
        assert policy.retry_on_timeout is True
        assert policy.retry_on_tool_error is True


# ── Step ─────────────────────────────────────────────────────────────


class TestStep:
    """Tests for Step model."""

    def test_default_creation(self) -> None:
        step = Step(description="Search for data")
        assert step.description == "Search for data"
        assert step.status == ExecutionStatus.PENDING
        assert step.success is False
        assert step.step_type == StepType.EXECUTION
        assert step.id is not None

    def test_is_done(self) -> None:
        step = Step(description="test")
        assert step.is_done() is False
        step.status = ExecutionStatus.COMPLETED
        assert step.is_done() is True
        step.status = ExecutionStatus.FAILED
        assert step.is_done() is True

    def test_is_actionable(self) -> None:
        step = Step(description="test")
        assert step.is_actionable() is True
        step.status = ExecutionStatus.RUNNING
        assert step.is_actionable() is False
        step.status = ExecutionStatus.BLOCKED
        assert step.is_actionable() is False

    def test_mark_blocked(self) -> None:
        step = Step(description="test")
        step.mark_blocked("Dependency failed", blocked_by="step-1")
        assert step.status == ExecutionStatus.BLOCKED
        assert step.notes == "Dependency failed"
        assert step.blocked_by == "step-1"
        assert step.success is False

    def test_mark_skipped(self) -> None:
        step = Step(description="test")
        step.mark_skipped("Not needed")
        assert step.status == ExecutionStatus.SKIPPED
        assert step.notes == "Not needed"
        assert step.success is True  # skipped = success

    def test_get_status_mark(self) -> None:
        step = Step(description="test")
        assert step.get_status_mark() == "[ ]"
        step.status = ExecutionStatus.COMPLETED
        assert step.get_status_mark() == "[✓]"

    def test_display_label_with_structured_fields(self) -> None:
        step = Step(
            description="fallback text",
            action_verb="Search",
            target_object="Python 3.12 features",
            tool_hint="web_search",
        )
        label = step.display_label
        assert "Search" in label
        assert "Python 3.12 features" in label
        assert "via web_search" in label

    def test_display_label_fallback_to_description(self) -> None:
        step = Step(description="Do something")
        assert step.display_label == "Do something"

    def test_display_label_no_tool_hint(self) -> None:
        step = Step(
            description="fallback",
            action_verb="Browse",
            target_object="example.com",
        )
        label = step.display_label
        assert "Browse" in label
        assert "example.com" in label
        assert "via" not in label

    def test_status_coercion_from_string(self) -> None:
        step = Step(description="test", status="completed")
        assert step.status == ExecutionStatus.COMPLETED

    def test_metadata_field(self) -> None:
        step = Step(description="test", metadata={"merged_steps": ["a", "b"]})
        assert step.metadata == {"merged_steps": ["a", "b"]}


# ── Phase ────────────────────────────────────────────────────────────


class TestPhase:
    """Tests for Phase model."""

    def test_creation(self) -> None:
        phase = Phase(
            phase_type=PhaseType.RESEARCH_FOUNDATION,
            label="Research",
            description="Gather information",
        )
        assert phase.phase_type == PhaseType.RESEARCH_FOUNDATION
        assert phase.label == "Research"
        assert phase.status == ExecutionStatus.PENDING
        assert phase.skipped is False

    def test_is_active(self) -> None:
        phase = Phase(phase_type=PhaseType.ALIGNMENT, label="Align")
        assert phase.is_active() is True
        phase.status = ExecutionStatus.RUNNING
        assert phase.is_active() is True
        phase.status = ExecutionStatus.COMPLETED
        assert phase.is_active() is False

    def test_is_done(self) -> None:
        phase = Phase(phase_type=PhaseType.ALIGNMENT, label="Align")
        assert phase.is_done() is False
        phase.status = ExecutionStatus.COMPLETED
        assert phase.is_done() is True

    def test_is_done_when_skipped(self) -> None:
        phase = Phase(phase_type=PhaseType.ALIGNMENT, label="Align", skipped=True)
        assert phase.is_done() is True

    def test_status_coercion(self) -> None:
        phase = Phase(phase_type=PhaseType.ALIGNMENT, label="Align", status="running")
        assert phase.status == ExecutionStatus.RUNNING


# ── Plan ─────────────────────────────────────────────────────────────


class TestPlan:
    """Tests for Plan model."""

    def _make_plan(self, step_statuses: list[ExecutionStatus] | None = None) -> Plan:
        steps = []
        for i, status in enumerate(step_statuses or [ExecutionStatus.PENDING] * 3):
            steps.append(Step(id=f"step-{i}", description=f"Step {i}", status=status))
        return Plan(title="Test Plan", goal="Test goal", steps=steps)

    def test_default_creation(self) -> None:
        plan = Plan(title="My Plan")
        assert plan.title == "My Plan"
        assert plan.status == ExecutionStatus.PENDING
        assert plan.steps == []
        assert plan.phases == []

    def test_is_done(self) -> None:
        plan = Plan(title="test")
        assert plan.is_done() is False
        plan.status = ExecutionStatus.COMPLETED
        assert plan.is_done() is True

    def test_get_next_step(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.PENDING,
            ExecutionStatus.PENDING,
        ])
        next_step = plan.get_next_step()
        assert next_step is not None
        assert next_step.id == "step-1"

    def test_get_next_step_none_when_all_done(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.COMPLETED,
        ])
        assert plan.get_next_step() is None

    def test_get_next_step_skips_running(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.RUNNING,
            ExecutionStatus.PENDING,
        ])
        next_step = plan.get_next_step()
        assert next_step is not None
        assert next_step.id == "step-1"

    def test_has_blocked_steps(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.BLOCKED,
            ExecutionStatus.PENDING,
        ])
        assert plan.has_blocked_steps() is True

    def test_has_no_blocked_steps(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.PENDING,
        ])
        assert plan.has_blocked_steps() is False

    def test_get_blocked_steps(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.BLOCKED,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.BLOCKED,
        ])
        blocked = plan.get_blocked_steps()
        assert len(blocked) == 2

    def test_get_running_step(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.RUNNING,
            ExecutionStatus.PENDING,
        ])
        running = plan.get_running_step()
        assert running is not None
        assert running.id == "step-1"

    def test_get_running_step_none(self) -> None:
        plan = self._make_plan([
            ExecutionStatus.COMPLETED,
            ExecutionStatus.PENDING,
        ])
        assert plan.get_running_step() is None

    def test_status_coercion(self) -> None:
        plan = Plan(title="test", status="completed")
        assert plan.status == ExecutionStatus.COMPLETED

    def test_result_coercion_from_string(self) -> None:
        plan = Plan(title="test", result="Some result text")
        assert plan.result == {"message": "Some result text"}

    def test_result_coercion_from_dict(self) -> None:
        plan = Plan(title="test", result={"key": "value"})
        assert plan.result == {"key": "value"}

    def test_result_coercion_from_none(self) -> None:
        plan = Plan(title="test", result=None)
        assert plan.result is None

    def test_unblock_independent_steps_blocker_completed(self) -> None:
        plan = Plan(
            title="test",
            steps=[
                Step(id="s1", description="First", status=ExecutionStatus.COMPLETED),
                Step(
                    id="s2",
                    description="Second",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )
        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked
        assert plan.steps[1].status == ExecutionStatus.PENDING

    def test_unblock_independent_steps_blocker_skipped(self) -> None:
        plan = Plan(
            title="test",
            steps=[
                Step(id="s1", description="First", status=ExecutionStatus.SKIPPED),
                Step(
                    id="s2",
                    description="Second",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )
        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked

    def test_unblock_independent_steps_blocker_failed_with_results(self) -> None:
        plan = Plan(
            title="test",
            steps=[
                Step(id="s1", description="First", status=ExecutionStatus.FAILED, result="partial data"),
                Step(
                    id="s2",
                    description="Second",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )
        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked

    def test_unblock_independent_steps_blocker_failed_no_results(self) -> None:
        plan = Plan(
            title="test",
            steps=[
                Step(id="s1", description="First", status=ExecutionStatus.FAILED, result=None),
                Step(
                    id="s2",
                    description="Second",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )
        unblocked = plan.unblock_independent_steps()
        assert unblocked == []
        assert plan.steps[1].status == ExecutionStatus.BLOCKED

    def test_unblock_independent_steps_missing_blocker(self) -> None:
        plan = Plan(
            title="test",
            steps=[
                Step(
                    id="s2",
                    description="Blocked by missing",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="nonexistent",
                ),
            ],
        )
        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked
        assert plan.steps[0].status == ExecutionStatus.PENDING


# ── PhaseType ────────────────────────────────────────────────────────


class TestPhaseType:
    """Tests for PhaseType enum."""

    def test_all_values(self) -> None:
        assert PhaseType.ALIGNMENT == "alignment"
        assert PhaseType.RESEARCH_FOUNDATION == "research_foundation"
        assert PhaseType.ANALYSIS_SYNTHESIS == "analysis_synthesis"
        assert PhaseType.REPORT_GENERATION == "report_generation"
        assert PhaseType.QUALITY_ASSURANCE == "quality_assurance"
        assert PhaseType.DELIVERY_FEEDBACK == "delivery_feedback"


class TestStepType:
    """Tests for StepType enum."""

    def test_all_values(self) -> None:
        assert StepType.EXECUTION == "execution"
        assert StepType.SELF_REVIEW == "self_review"
        assert StepType.ALIGNMENT == "alignment"
        assert StepType.DELIVERY == "delivery"
        assert StepType.FINALIZATION == "finalization"
