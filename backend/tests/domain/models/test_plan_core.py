"""Tests for core Plan domain model logic.

Covers ExecutionStatus, Phase, RetryPolicy, Step, Plan, and ValidationResult.
Does NOT duplicate validation, dependency, or quality-metric tests that exist
in other files in this directory.
"""

from __future__ import annotations

import json

import pytest

from app.domain.models.plan import (
    ExecutionStatus,
    Phase,
    PhaseType,
    Plan,
    RetryPolicy,
    Step,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(**kwargs) -> Step:
    defaults = {"description": "Do something useful"}
    defaults.update(kwargs)
    return Step(**defaults)


def _make_phase(phase_type: PhaseType = PhaseType.RESEARCH_FOUNDATION, **kwargs) -> Phase:
    defaults = {"phase_type": phase_type, "label": "Test Phase"}
    defaults.update(kwargs)
    return Phase(**defaults)


def _make_plan_with_steps(count: int = 3) -> Plan:
    steps = [Step(description=f"Step {i + 1}") for i in range(count)]
    return Plan(title="Test Plan", steps=steps)


# ---------------------------------------------------------------------------
# ExecutionStatus — class methods
# ---------------------------------------------------------------------------


class TestExecutionStatusClassMethods:
    def test_get_status_marks_returns_all_seven_statuses(self) -> None:
        marks = ExecutionStatus.get_status_marks()
        assert len(marks) == 7
        expected_keys = {
            "pending",
            "running",
            "completed",
            "failed",
            "blocked",
            "skipped",
            "terminated",
        }
        assert set(marks.keys()) == expected_keys

    def test_get_status_marks_values_are_bracket_strings(self) -> None:
        marks = ExecutionStatus.get_status_marks()
        assert marks["pending"] == "[ ]"
        assert marks["running"] == "[→]"
        assert marks["completed"] == "[✓]"
        assert marks["failed"] == "[✗]"
        assert marks["blocked"] == "[!]"
        assert marks["skipped"] == "[-]"
        assert marks["terminated"] == "[⊘]"

    def test_get_active_statuses_contains_pending_and_running(self) -> None:
        active = ExecutionStatus.get_active_statuses()
        assert set(active) == {"pending", "running"}

    def test_get_terminal_statuses_contains_five_values(self) -> None:
        terminal = ExecutionStatus.get_terminal_statuses()
        assert set(terminal) == {"completed", "failed", "blocked", "skipped", "terminated"}

    def test_get_success_statuses_contains_completed_and_skipped(self) -> None:
        success = ExecutionStatus.get_success_statuses()
        assert set(success) == {"completed", "skipped"}

    def test_get_failure_statuses_contains_failed_and_blocked(self) -> None:
        failure = ExecutionStatus.get_failure_statuses()
        assert set(failure) == {"failed", "blocked"}


# ---------------------------------------------------------------------------
# ExecutionStatus — instance methods per status value
# ---------------------------------------------------------------------------


class TestExecutionStatusInstanceMethods:
    def test_pending_is_active_true(self) -> None:
        assert ExecutionStatus.PENDING.is_active() is True

    def test_pending_is_terminal_false(self) -> None:
        assert ExecutionStatus.PENDING.is_terminal() is False

    def test_pending_is_success_false(self) -> None:
        assert ExecutionStatus.PENDING.is_success() is False

    def test_pending_is_failure_false(self) -> None:
        assert ExecutionStatus.PENDING.is_failure() is False

    def test_running_is_active_true(self) -> None:
        assert ExecutionStatus.RUNNING.is_active() is True

    def test_running_is_terminal_false(self) -> None:
        assert ExecutionStatus.RUNNING.is_terminal() is False

    def test_completed_is_active_false(self) -> None:
        assert ExecutionStatus.COMPLETED.is_active() is False

    def test_completed_is_terminal_true(self) -> None:
        assert ExecutionStatus.COMPLETED.is_terminal() is True

    def test_completed_is_success_true(self) -> None:
        assert ExecutionStatus.COMPLETED.is_success() is True

    def test_completed_is_failure_false(self) -> None:
        assert ExecutionStatus.COMPLETED.is_failure() is False

    def test_failed_is_terminal_true(self) -> None:
        assert ExecutionStatus.FAILED.is_terminal() is True

    def test_failed_is_failure_true(self) -> None:
        assert ExecutionStatus.FAILED.is_failure() is True

    def test_failed_is_success_false(self) -> None:
        assert ExecutionStatus.FAILED.is_success() is False

    def test_blocked_is_terminal_true(self) -> None:
        assert ExecutionStatus.BLOCKED.is_terminal() is True

    def test_blocked_is_failure_true(self) -> None:
        assert ExecutionStatus.BLOCKED.is_failure() is True

    def test_skipped_is_terminal_true(self) -> None:
        assert ExecutionStatus.SKIPPED.is_terminal() is True

    def test_skipped_is_success_true(self) -> None:
        assert ExecutionStatus.SKIPPED.is_success() is True

    def test_skipped_is_failure_false(self) -> None:
        assert ExecutionStatus.SKIPPED.is_failure() is False

    def test_terminated_is_terminal_true(self) -> None:
        assert ExecutionStatus.TERMINATED.is_terminal() is True

    def test_terminated_is_active_false(self) -> None:
        assert ExecutionStatus.TERMINATED.is_active() is False

    def test_terminated_is_success_false(self) -> None:
        assert ExecutionStatus.TERMINATED.is_success() is False

    def test_terminated_is_failure_false(self) -> None:
        assert ExecutionStatus.TERMINATED.is_failure() is False


# ---------------------------------------------------------------------------
# Phase
# ---------------------------------------------------------------------------


class TestPhase:
    def test_default_status_is_pending(self) -> None:
        phase = _make_phase()
        assert phase.status == ExecutionStatus.PENDING

    def test_coerce_status_from_string_running(self) -> None:
        phase = _make_phase(status="running")
        assert phase.status == ExecutionStatus.RUNNING

    def test_coerce_status_from_string_completed(self) -> None:
        phase = _make_phase(status="completed")
        assert phase.status == ExecutionStatus.COMPLETED

    def test_is_active_true_for_pending(self) -> None:
        phase = _make_phase(status=ExecutionStatus.PENDING)
        assert phase.is_active() is True

    def test_is_active_true_for_running(self) -> None:
        phase = _make_phase(status=ExecutionStatus.RUNNING)
        assert phase.is_active() is True

    def test_is_active_false_for_completed(self) -> None:
        phase = _make_phase(status=ExecutionStatus.COMPLETED)
        assert phase.is_active() is False

    def test_is_done_false_for_pending(self) -> None:
        phase = _make_phase(status=ExecutionStatus.PENDING)
        assert phase.is_done() is False

    def test_is_done_true_for_completed(self) -> None:
        phase = _make_phase(status=ExecutionStatus.COMPLETED)
        assert phase.is_done() is True

    def test_is_done_true_for_failed(self) -> None:
        phase = _make_phase(status=ExecutionStatus.FAILED)
        assert phase.is_done() is True

    def test_is_done_true_when_skipped_flag_set(self) -> None:
        # skipped=True forces is_done even if status is PENDING
        phase = _make_phase(status=ExecutionStatus.PENDING, skipped=True)
        assert phase.is_done() is True


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_default_max_retries_is_zero(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 0

    def test_default_backoff_seconds(self) -> None:
        policy = RetryPolicy()
        assert policy.backoff_seconds == 2.0

    def test_default_backoff_multiplier(self) -> None:
        policy = RetryPolicy()
        assert policy.backoff_multiplier == 2.0

    def test_default_retry_on_timeout_true(self) -> None:
        policy = RetryPolicy()
        assert policy.retry_on_timeout is True

    def test_default_retry_on_tool_error_true(self) -> None:
        policy = RetryPolicy()
        assert policy.retry_on_tool_error is True


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


class TestStepCoerceStatus:
    def test_coerce_status_from_string_pending(self) -> None:
        step = _make_step(status="pending")
        assert step.status == ExecutionStatus.PENDING

    def test_coerce_status_from_string_completed(self) -> None:
        step = _make_step(status="completed")
        assert step.status == ExecutionStatus.COMPLETED

    def test_coerce_status_from_string_failed(self) -> None:
        step = _make_step(status="failed")
        assert step.status == ExecutionStatus.FAILED

    def test_coerce_status_from_enum_value_is_unchanged(self) -> None:
        step = _make_step(status=ExecutionStatus.RUNNING)
        assert step.status == ExecutionStatus.RUNNING


class TestStepDisplayLabel:
    def test_display_label_with_action_verb_and_target(self) -> None:
        step = _make_step(action_verb="Search", target_object="Python 3.12 release notes")
        assert step.display_label == "Search Python 3.12 release notes"

    def test_display_label_with_tool_hint(self) -> None:
        step = _make_step(action_verb="Browse", target_object="homepage", tool_hint="browser")
        assert step.display_label == "Browse homepage via browser"

    def test_display_label_fallback_to_description_when_no_action_verb(self) -> None:
        step = _make_step(description="Fallback description", target_object="something")
        assert step.display_label == "Fallback description"

    def test_display_label_fallback_when_no_target_object(self) -> None:
        step = _make_step(description="Only description", action_verb="Write")
        assert step.display_label == "Only description"

    def test_display_label_no_tool_hint_does_not_include_via(self) -> None:
        step = _make_step(action_verb="Analyze", target_object="data")
        assert "via" not in step.display_label


class TestStepIsDoneIsActionable:
    def test_is_done_false_for_pending(self) -> None:
        step = _make_step(status=ExecutionStatus.PENDING)
        assert step.is_done() is False

    def test_is_done_false_for_running(self) -> None:
        step = _make_step(status=ExecutionStatus.RUNNING)
        assert step.is_done() is False

    def test_is_done_true_for_completed(self) -> None:
        step = _make_step(status=ExecutionStatus.COMPLETED)
        assert step.is_done() is True

    def test_is_done_true_for_failed(self) -> None:
        step = _make_step(status=ExecutionStatus.FAILED)
        assert step.is_done() is True

    def test_is_done_true_for_blocked(self) -> None:
        step = _make_step(status=ExecutionStatus.BLOCKED)
        assert step.is_done() is True

    def test_is_done_true_for_terminated(self) -> None:
        step = _make_step(status=ExecutionStatus.TERMINATED)
        assert step.is_done() is True

    def test_is_actionable_true_for_pending(self) -> None:
        step = _make_step(status=ExecutionStatus.PENDING)
        assert step.is_actionable() is True

    def test_is_actionable_false_for_running(self) -> None:
        step = _make_step(status=ExecutionStatus.RUNNING)
        assert step.is_actionable() is False

    def test_is_actionable_false_for_completed(self) -> None:
        step = _make_step(status=ExecutionStatus.COMPLETED)
        assert step.is_actionable() is False


class TestStepMarkBlocked:
    def test_mark_blocked_sets_status(self) -> None:
        step = _make_step()
        step.mark_blocked("dependency failed", blocked_by="abc")
        assert step.status == ExecutionStatus.BLOCKED

    def test_mark_blocked_sets_notes(self) -> None:
        step = _make_step()
        step.mark_blocked("reason text")
        assert step.notes == "reason text"

    def test_mark_blocked_sets_blocked_by(self) -> None:
        step = _make_step()
        step.mark_blocked("reason", blocked_by="step-xyz")
        assert step.blocked_by == "step-xyz"

    def test_mark_blocked_sets_success_false(self) -> None:
        step = _make_step(success=True)
        step.mark_blocked("reason")
        assert step.success is False

    def test_mark_blocked_without_blocked_by_leaves_none(self) -> None:
        step = _make_step()
        step.mark_blocked("reason")
        assert step.blocked_by is None


class TestStepMarkSkipped:
    def test_mark_skipped_sets_status(self) -> None:
        step = _make_step()
        step.mark_skipped("not needed")
        assert step.status == ExecutionStatus.SKIPPED

    def test_mark_skipped_sets_notes(self) -> None:
        step = _make_step()
        step.mark_skipped("optimised away")
        assert step.notes == "optimised away"

    def test_mark_skipped_sets_success_true(self) -> None:
        step = _make_step(success=False)
        step.mark_skipped("reason")
        assert step.success is True


class TestStepGetStatusMark:
    def test_get_status_mark_pending(self) -> None:
        step = _make_step(status=ExecutionStatus.PENDING)
        assert step.get_status_mark() == "[ ]"

    def test_get_status_mark_completed(self) -> None:
        step = _make_step(status=ExecutionStatus.COMPLETED)
        assert step.get_status_mark() == "[✓]"

    def test_get_status_mark_failed(self) -> None:
        step = _make_step(status=ExecutionStatus.FAILED)
        assert step.get_status_mark() == "[✗]"

    def test_get_status_mark_running(self) -> None:
        step = _make_step(status=ExecutionStatus.RUNNING)
        assert step.get_status_mark() == "[→]"

    def test_get_status_mark_blocked(self) -> None:
        step = _make_step(status=ExecutionStatus.BLOCKED)
        assert step.get_status_mark() == "[!]"

    def test_get_status_mark_skipped(self) -> None:
        step = _make_step(status=ExecutionStatus.SKIPPED)
        assert step.get_status_mark() == "[-]"

    def test_get_status_mark_terminated(self) -> None:
        step = _make_step(status=ExecutionStatus.TERMINATED)
        assert step.get_status_mark() == "[⊘]"


# ---------------------------------------------------------------------------
# Plan — field coercion
# ---------------------------------------------------------------------------


class TestPlanCoercion:
    def test_coerce_status_from_string(self) -> None:
        plan = Plan(status="running")
        assert plan.status == ExecutionStatus.RUNNING

    def test_coerce_result_none_remains_none(self) -> None:
        plan = Plan(result=None)
        assert plan.result is None

    def test_coerce_result_string_wrapped_in_message_dict(self) -> None:
        plan = Plan(result="some text")  # type: ignore[arg-type]
        assert plan.result == {"message": "some text"}

    def test_coerce_result_dict_passes_through(self) -> None:
        plan = Plan(result={"key": "value"})
        assert plan.result == {"key": "value"}


# ---------------------------------------------------------------------------
# Plan — step queries
# ---------------------------------------------------------------------------


class TestPlanGetNextStep:
    def test_returns_first_pending_step(self) -> None:
        plan = _make_plan_with_steps(3)
        next_step = plan.get_next_step()
        assert next_step is plan.steps[0]

    def test_returns_none_when_all_completed(self) -> None:
        plan = _make_plan_with_steps(2)
        for step in plan.steps:
            step.status = ExecutionStatus.COMPLETED
        assert plan.get_next_step() is None

    def test_skips_running_and_completed_steps(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.steps[0].status = ExecutionStatus.RUNNING
        plan.steps[1].status = ExecutionStatus.COMPLETED
        next_step = plan.get_next_step()
        assert next_step is plan.steps[2]

    def test_returns_none_for_empty_plan(self) -> None:
        plan = Plan()
        assert plan.get_next_step() is None


class TestPlanBlockedSteps:
    def test_has_blocked_steps_false_when_none_blocked(self) -> None:
        plan = _make_plan_with_steps(2)
        assert plan.has_blocked_steps() is False

    def test_has_blocked_steps_true_when_one_blocked(self) -> None:
        plan = _make_plan_with_steps(2)
        plan.steps[0].status = ExecutionStatus.BLOCKED
        assert plan.has_blocked_steps() is True

    def test_get_blocked_steps_empty_list_when_none_blocked(self) -> None:
        plan = _make_plan_with_steps(2)
        assert plan.get_blocked_steps() == []

    def test_get_blocked_steps_returns_only_blocked(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.steps[1].status = ExecutionStatus.BLOCKED
        blocked = plan.get_blocked_steps()
        assert len(blocked) == 1
        assert blocked[0] is plan.steps[1]


class TestPlanGetRunningStep:
    def test_returns_none_when_no_running_step(self) -> None:
        plan = _make_plan_with_steps(2)
        assert plan.get_running_step() is None

    def test_returns_running_step(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.steps[1].status = ExecutionStatus.RUNNING
        running = plan.get_running_step()
        assert running is plan.steps[1]


class TestPlanGetStepById:
    def test_returns_step_when_found(self) -> None:
        plan = _make_plan_with_steps(2)
        target = plan.steps[1]
        result = plan.get_step_by_id(target.id)
        assert result is target

    def test_returns_none_when_not_found(self) -> None:
        plan = _make_plan_with_steps(2)
        assert plan.get_step_by_id("nonexistent-id") is None


# ---------------------------------------------------------------------------
# Plan — phase queries
# ---------------------------------------------------------------------------


class TestPlanPhaseQueries:
    def _plan_with_phases(self) -> Plan:
        p1 = _make_phase(PhaseType.RESEARCH_FOUNDATION, label="Research", order=1)
        p2 = _make_phase(PhaseType.REPORT_GENERATION, label="Report", order=2)
        return Plan(title="Phased Plan", phases=[p1, p2])

    def test_get_phase_by_type_found(self) -> None:
        plan = self._plan_with_phases()
        phase = plan.get_phase_by_type(PhaseType.RESEARCH_FOUNDATION)
        assert phase is not None
        assert phase.label == "Research"

    def test_get_phase_by_type_not_found(self) -> None:
        plan = self._plan_with_phases()
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is None

    def test_get_phase_by_id_found(self) -> None:
        plan = self._plan_with_phases()
        target = plan.phases[0]
        assert plan.get_phase_by_id(target.id) is target

    def test_get_phase_by_id_not_found(self) -> None:
        plan = self._plan_with_phases()
        assert plan.get_phase_by_id("no-such-id") is None

    def test_get_steps_for_phase_returns_matching_steps(self) -> None:
        phase = _make_phase()
        step1 = Step(description="Step A", phase_id=phase.id)
        step2 = Step(description="Step B", phase_id=phase.id)
        step3 = Step(description="Step C")  # no phase
        plan = Plan(steps=[step1, step2, step3], phases=[phase])
        result = plan.get_steps_for_phase(phase.id)
        assert len(result) == 2
        assert step3 not in result

    def test_get_steps_for_phase_empty_when_no_match(self) -> None:
        plan = Plan(steps=[Step(description="X")])
        assert plan.get_steps_for_phase("phantom-id") == []


# ---------------------------------------------------------------------------
# Plan — get_progress
# ---------------------------------------------------------------------------


class TestPlanGetProgress:
    def test_empty_plan_returns_zero_progress(self) -> None:
        plan = Plan()
        progress = plan.get_progress()
        assert progress["total"] == 0
        assert progress["progress_pct"] == 0.0

    def test_all_completed_returns_100_percent(self) -> None:
        plan = _make_plan_with_steps(4)
        for step in plan.steps:
            step.status = ExecutionStatus.COMPLETED
        progress = plan.get_progress()
        assert progress["total"] == 4
        assert progress["completed"] == 4
        assert progress["progress_pct"] == 100.0

    def test_mixed_statuses_counted_correctly(self) -> None:
        plan = _make_plan_with_steps(5)
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[1].status = ExecutionStatus.SKIPPED
        plan.steps[2].status = ExecutionStatus.RUNNING
        plan.steps[3].status = ExecutionStatus.FAILED
        # steps[4] stays PENDING
        progress = plan.get_progress()
        assert progress["completed"] == 1
        assert progress["skipped"] == 1
        assert progress["running"] == 1
        assert progress["failed"] == 1
        assert progress["pending"] == 1
        # progress_pct counts completed + skipped = 2 out of 5
        assert progress["progress_pct"] == pytest.approx(40.0)

    def test_all_keys_present_in_non_empty_plan(self) -> None:
        plan = _make_plan_with_steps(1)
        progress = plan.get_progress()
        expected_keys = {"total", "completed", "failed", "blocked", "skipped", "pending", "running", "progress_pct"}
        assert set(progress.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Plan — format_progress_text
# ---------------------------------------------------------------------------


class TestPlanFormatProgressText:
    def test_output_contains_plan_title(self) -> None:
        plan = Plan(title="My Report Plan", steps=[Step(description="Do it")])
        text = plan.format_progress_text()
        assert "My Report Plan" in text

    def test_output_contains_step_description(self) -> None:
        plan = Plan(title="T", steps=[Step(description="Fetch data")])
        text = plan.format_progress_text()
        assert "Fetch data" in text

    def test_output_contains_step_status_marks(self) -> None:
        plan = _make_plan_with_steps(2)
        plan.steps[0].status = ExecutionStatus.COMPLETED
        text = plan.format_progress_text()
        assert "[✓]" in text
        assert "[ ]" in text

    def test_output_shows_running_count_when_step_running(self) -> None:
        plan = _make_plan_with_steps(2)
        plan.steps[0].status = ExecutionStatus.RUNNING
        text = plan.format_progress_text()
        assert "running" in text

    def test_output_uses_goal_when_title_empty(self) -> None:
        plan = Plan(title="", goal="Investigate something important", steps=[Step(description="x")])
        text = plan.format_progress_text()
        assert "Investigate" in text

    def test_output_includes_notes_for_blocked_step(self) -> None:
        plan = _make_plan_with_steps(1)
        plan.steps[0].mark_blocked("upstream failure")
        text = plan.format_progress_text()
        assert "upstream failure" in text


# ---------------------------------------------------------------------------
# Plan — unblock_independent_steps
# ---------------------------------------------------------------------------


class TestPlanUnblockIndependentSteps:
    def test_unblock_when_blocker_completed(self) -> None:
        blocker = Step(description="Blocker step")
        blocker.status = ExecutionStatus.COMPLETED
        dependent = Step(description="Dependent step")
        dependent.status = ExecutionStatus.BLOCKED
        dependent.blocked_by = blocker.id
        plan = Plan(steps=[blocker, dependent])
        unblocked = plan.unblock_independent_steps()
        assert dependent.id in unblocked
        assert dependent.status == ExecutionStatus.PENDING
        assert dependent.blocked_by is None

    def test_unblock_when_blocker_skipped(self) -> None:
        blocker = Step(description="Blocker step")
        blocker.status = ExecutionStatus.SKIPPED
        dependent = Step(description="Dependent step")
        dependent.status = ExecutionStatus.BLOCKED
        dependent.blocked_by = blocker.id
        plan = Plan(steps=[blocker, dependent])
        unblocked = plan.unblock_independent_steps()
        assert dependent.id in unblocked
        assert dependent.status == ExecutionStatus.PENDING
        assert "skipped" in dependent.notes

    def test_unblock_when_blocker_failed_with_partial_result(self) -> None:
        blocker = Step(description="Blocker step")
        blocker.status = ExecutionStatus.FAILED
        blocker.result = "partial data"
        dependent = Step(description="Dependent step")
        dependent.status = ExecutionStatus.BLOCKED
        dependent.blocked_by = blocker.id
        plan = Plan(steps=[blocker, dependent])
        unblocked = plan.unblock_independent_steps()
        assert dependent.id in unblocked
        assert "partial results" in dependent.notes

    def test_no_unblock_when_blocker_failed_without_result(self) -> None:
        blocker = Step(description="Blocker step")
        blocker.status = ExecutionStatus.FAILED
        blocker.result = None
        dependent = Step(description="Dependent step")
        dependent.status = ExecutionStatus.BLOCKED
        dependent.blocked_by = blocker.id
        plan = Plan(steps=[blocker, dependent])
        unblocked = plan.unblock_independent_steps()
        assert dependent.id not in unblocked
        assert dependent.status == ExecutionStatus.BLOCKED

    def test_unblock_when_blocker_missing(self) -> None:
        dependent = Step(description="Dependent step")
        dependent.status = ExecutionStatus.BLOCKED
        dependent.blocked_by = "ghost-step-id"
        plan = Plan(steps=[dependent])
        unblocked = plan.unblock_independent_steps()
        assert dependent.id in unblocked
        assert dependent.status == ExecutionStatus.PENDING
        assert dependent.blocked_by is None


# ---------------------------------------------------------------------------
# Plan — mark_blocked_cascade
# ---------------------------------------------------------------------------


class TestPlanMarkBlockedCascade:
    def test_cascade_blocks_direct_dependents(self) -> None:
        root = Step(description="Root")
        root.status = ExecutionStatus.FAILED
        child = Step(description="Child", dependencies=[root.id])
        plan = Plan(steps=[root, child])
        blocked = plan.mark_blocked_cascade(root.id, "root failed")
        assert child.id in blocked
        assert child.status == ExecutionStatus.BLOCKED

    def test_cascade_blocks_transitively(self) -> None:
        root = Step(description="Root")
        root.status = ExecutionStatus.FAILED
        child = Step(description="Child", dependencies=[root.id])
        grandchild = Step(description="Grandchild", dependencies=[child.id])
        plan = Plan(steps=[root, child, grandchild])
        blocked = plan.mark_blocked_cascade(root.id, "root failed")
        assert child.id in blocked
        assert grandchild.id in blocked

    def test_cascade_does_not_block_already_completed_steps(self) -> None:
        root = Step(description="Root")
        root.status = ExecutionStatus.FAILED
        sibling = Step(description="Sibling", dependencies=[root.id])
        sibling.status = ExecutionStatus.COMPLETED
        plan = Plan(steps=[root, sibling])
        blocked = plan.mark_blocked_cascade(root.id, "failed")
        assert sibling.id not in blocked

    def test_cascade_returns_empty_list_when_no_dependents(self) -> None:
        lonely = Step(description="Lonely")
        lonely.status = ExecutionStatus.FAILED
        plan = Plan(steps=[lonely])
        assert plan.mark_blocked_cascade(lonely.id, "failed") == []


# ---------------------------------------------------------------------------
# Plan — infer_sequential_dependencies
# ---------------------------------------------------------------------------


class TestPlanInferSequentialDependencies:
    def test_first_step_has_no_dependency(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.infer_sequential_dependencies()
        assert plan.steps[0].dependencies == []

    def test_second_step_depends_on_first(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.infer_sequential_dependencies()
        assert plan.steps[1].dependencies == [plan.steps[0].id]

    def test_third_step_depends_on_second(self) -> None:
        plan = _make_plan_with_steps(3)
        plan.infer_sequential_dependencies()
        assert plan.steps[2].dependencies == [plan.steps[1].id]

    def test_existing_dependencies_not_overwritten(self) -> None:
        plan = _make_plan_with_steps(3)
        explicit_dep = "explicit-dep-id"
        plan.steps[1].dependencies = [explicit_dep]
        plan.infer_sequential_dependencies()
        # Should not overwrite existing dependency
        assert plan.steps[1].dependencies == [explicit_dep]


# ---------------------------------------------------------------------------
# Plan — sync_phase_statuses
# ---------------------------------------------------------------------------


class TestPlanSyncPhaseStatuses:
    def test_no_op_when_no_phases(self) -> None:
        plan = _make_plan_with_steps(2)
        plan.sync_phase_statuses()  # Should not raise

    def test_all_pending_steps_yield_pending_phase(self) -> None:
        phase = _make_phase()
        steps = [Step(description=f"S{i}", phase_id=phase.id) for i in range(2)]
        plan = Plan(steps=steps, phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.PENDING

    def test_all_completed_steps_yield_completed_phase(self) -> None:
        phase = _make_phase()
        steps = [Step(description=f"S{i}", phase_id=phase.id, status=ExecutionStatus.COMPLETED) for i in range(2)]
        plan = Plan(steps=steps, phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.COMPLETED

    def test_mixed_steps_yield_running_phase(self) -> None:
        phase = _make_phase()
        s1 = Step(description="Done", phase_id=phase.id, status=ExecutionStatus.COMPLETED)
        s2 = Step(description="Pending", phase_id=phase.id, status=ExecutionStatus.PENDING)
        plan = Plan(steps=[s1, s2], phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.RUNNING

    def test_skipped_phase_flag_sets_status_skipped(self) -> None:
        phase = _make_phase(skipped=True)
        steps = [Step(description="S", phase_id=phase.id)]
        plan = Plan(steps=steps, phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.SKIPPED

    def test_phase_with_no_steps_stays_pending(self) -> None:
        phase = _make_phase()
        plan = Plan(steps=[], phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.PENDING

    def test_step_ids_fallback_to_phase_id_lookup(self) -> None:
        """Phase.step_ids empty — falls back to phase_id on steps."""
        phase = _make_phase()
        assert phase.step_ids == []
        steps = [Step(description="S", phase_id=phase.id, status=ExecutionStatus.COMPLETED)]
        plan = Plan(steps=steps, phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.COMPLETED

    def test_all_terminal_with_failed_step_yields_failed_phase(self) -> None:
        phase = _make_phase()
        s1 = Step(description="Completed", phase_id=phase.id, status=ExecutionStatus.COMPLETED)
        s2 = Step(description="Failed", phase_id=phase.id, status=ExecutionStatus.FAILED)
        plan = Plan(steps=[s1, s2], phases=[phase])
        plan.sync_phase_statuses()
        assert phase.status == ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Plan — get_current_phase & advance_phase
# ---------------------------------------------------------------------------


class TestPlanGetCurrentPhase:
    def test_returns_lowest_order_pending_phase(self) -> None:
        p1 = _make_phase(order=2, status=ExecutionStatus.PENDING)
        p2 = _make_phase(order=1, status=ExecutionStatus.PENDING)
        plan = Plan(phases=[p1, p2])
        current = plan.get_current_phase()
        assert current is p2

    def test_skips_completed_phases(self) -> None:
        p1 = _make_phase(order=1, status=ExecutionStatus.COMPLETED)
        p2 = _make_phase(order=2, status=ExecutionStatus.PENDING)
        plan = Plan(phases=[p1, p2])
        current = plan.get_current_phase()
        assert current is p2

    def test_returns_none_when_all_phases_completed(self) -> None:
        p1 = _make_phase(status=ExecutionStatus.COMPLETED)
        plan = Plan(phases=[p1])
        assert plan.get_current_phase() is None

    def test_skips_phases_marked_skipped_flag(self) -> None:
        p1 = _make_phase(order=1, skipped=True, status=ExecutionStatus.PENDING)
        p2 = _make_phase(order=2, status=ExecutionStatus.PENDING)
        plan = Plan(phases=[p1, p2])
        current = plan.get_current_phase()
        assert current is p2


class TestPlanAdvancePhase:
    def test_advance_marks_current_phase_completed(self) -> None:
        p1 = _make_phase(order=1, status=ExecutionStatus.RUNNING)
        p2 = _make_phase(order=2, status=ExecutionStatus.PENDING)
        plan = Plan(phases=[p1, p2])
        plan.advance_phase(p1.id)
        assert p1.status == ExecutionStatus.COMPLETED

    def test_advance_returns_next_pending_phase(self) -> None:
        p1 = _make_phase(order=1, status=ExecutionStatus.RUNNING)
        p2 = _make_phase(order=2, status=ExecutionStatus.PENDING)
        plan = Plan(phases=[p1, p2])
        next_phase = plan.advance_phase(p1.id)
        assert next_phase is p2

    def test_advance_returns_none_when_last_phase(self) -> None:
        p1 = _make_phase(order=1, status=ExecutionStatus.RUNNING)
        plan = Plan(phases=[p1])
        next_phase = plan.advance_phase(p1.id)
        assert next_phase is None


# ---------------------------------------------------------------------------
# Plan — dump_json
# ---------------------------------------------------------------------------


class TestPlanDumpJson:
    def test_dump_json_includes_goal(self) -> None:
        plan = Plan(goal="Find best Python books", steps=[Step(description="Search")])
        data = json.loads(plan.dump_json())
        assert data["goal"] == "Find best Python books"

    def test_dump_json_includes_language(self) -> None:
        plan = Plan(language="fr", steps=[Step(description="Chercher")])
        data = json.loads(plan.dump_json())
        assert data["language"] == "fr"

    def test_dump_json_includes_steps(self) -> None:
        plan = Plan(steps=[Step(description="First step"), Step(description="Second step")])
        data = json.loads(plan.dump_json())
        assert len(data["steps"]) == 2

    def test_dump_json_excludes_title(self) -> None:
        plan = Plan(title="Internal Title", steps=[Step(description="x")])
        data = json.loads(plan.dump_json())
        assert "title" not in data

    def test_dump_json_produces_valid_json_string(self) -> None:
        plan = Plan(goal="g", steps=[Step(description="s")])
        raw = plan.dump_json()
        # Must be valid JSON without raising
        json.loads(raw)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict_passed_true(self) -> None:
        result = ValidationResult(passed=True)
        d = result.to_dict()
        assert d["passed"] is True

    def test_to_dict_passed_false(self) -> None:
        result = ValidationResult(passed=False, errors=["Missing steps"])
        d = result.to_dict()
        assert d["passed"] is False

    def test_to_dict_errors_included(self) -> None:
        result = ValidationResult(passed=False, errors=["err1", "err2"])
        d = result.to_dict()
        assert d["errors"] == ["err1", "err2"]

    def test_to_dict_warnings_included(self) -> None:
        result = ValidationResult(passed=True, warnings=["warn1"])
        d = result.to_dict()
        assert d["warnings"] == ["warn1"]

    def test_to_dict_has_exactly_three_keys(self) -> None:
        result = ValidationResult(passed=True)
        d = result.to_dict()
        assert set(d.keys()) == {"passed", "errors", "warnings"}

    def test_to_dict_default_empty_lists(self) -> None:
        result = ValidationResult(passed=True)
        d = result.to_dict()
        assert d["errors"] == []
        assert d["warnings"] == []
