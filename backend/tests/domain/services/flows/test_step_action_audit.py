"""Tests for step action audit enforcement in PlanActFlow."""

from app.domain.models.plan import ExecutionStatus, Step
from app.domain.services.flows.plan_act import PlanActFlow


def test_evaluate_step_actions_counts_search_tool_as_search() -> None:
    audit = PlanActFlow._evaluate_step_actions(
        description="Search for recent agent workflow failures",
        tools_used={"search"},
    )

    assert audit["expected"] == {"search"}
    assert audit["fulfilled"] == {"search"}
    assert audit["missed"] == set()


def test_apply_step_action_audit_fails_step_when_required_action_missing() -> None:
    step = Step(
        description="Search for recent agent workflow failures",
        status=ExecutionStatus.COMPLETED,
        success=True,
    )

    changed = PlanActFlow._apply_step_action_audit(step, {"browser_navigate"})

    assert changed is True
    assert step.success is False
    assert step.status == ExecutionStatus.FAILED
    assert step.error == "Step completed without required actions: search"


def test_apply_step_action_audit_fails_write_without_execute_step() -> None:
    step = Step(
        description="Write a benchmark script and run it",
        status=ExecutionStatus.COMPLETED,
        success=True,
    )

    changed = PlanActFlow._apply_step_action_audit(step, {"file_write"})

    assert changed is True
    assert step.success is False
    assert step.status == ExecutionStatus.FAILED
    assert step.error == "Step required execution but no execution tool ran"


def test_apply_step_action_audit_leaves_valid_step_unchanged() -> None:
    step = Step(
        description="Search for recent agent workflow failures",
        status=ExecutionStatus.COMPLETED,
        success=True,
    )

    changed = PlanActFlow._apply_step_action_audit(step, {"search"})

    assert changed is False
    assert step.success is True
    assert step.status == ExecutionStatus.COMPLETED
