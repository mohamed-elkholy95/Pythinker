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

    # file_write is a write tool — it should NOT satisfy the "search" requirement
    changed = PlanActFlow._apply_step_action_audit(step, {"file_write"})

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


def test_expected_tools_research_step_passes_with_search() -> None:
    """Step with expected_tools=['search', 'browser'] passes when search was used."""
    step = Step(
        id="3",
        description="Cross-validate benchmark data",
        success=True,
        expected_tools=["search", "browser", "file_read", "file_write"],
    )
    tools_used = {"search", "browser", "file_read", "file_write", "info_search_web"}
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is False
    assert step.success is True


def test_expected_tools_overrides_keyword_inference() -> None:
    """When expected_tools is set, keyword inference is skipped entirely."""
    step = Step(
        id="1",
        description="Execute benchmark script and run tests",
        success=True,
        expected_tools=["shell_exec"],
    )
    tools_used = {"shell_exec"}
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is False


def test_expected_tools_fails_when_none_used() -> None:
    """When none of the expected tools were used, audit fails."""
    step = Step(
        id="1",
        description="Execute script",
        success=True,
        expected_tools=["shell_exec", "code_execute_python"],
    )
    tools_used = {"file_write"}
    result = PlanActFlow._apply_step_action_audit(step, tools_used)
    assert result is True
    assert step.success is False
    assert "declared tools" in step.error
