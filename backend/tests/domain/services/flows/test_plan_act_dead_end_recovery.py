"""Regression tests for zero-progress dead-end recovery in PlanActFlow."""

from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.flows.plan_act import PlanActFlow


def _make_flow_with_plan(step_statuses: list[ExecutionStatus]) -> PlanActFlow:
    flow = PlanActFlow.__new__(PlanActFlow)
    flow.plan = Plan(
        goal="test",
        message="test",
        steps=[
            Step(
                id=f"step-{idx}",
                description=f"step {idx}",
                status=status,
            )
            for idx, status in enumerate(step_statuses, start=1)
        ],
    )
    flow._zero_progress_dead_end_replans = 0
    flow._max_zero_progress_dead_end_replans = 1
    return flow


def test_is_zero_progress_dead_end_true_when_only_failed_or_blocked() -> None:
    flow = _make_flow_with_plan([ExecutionStatus.FAILED, ExecutionStatus.BLOCKED, ExecutionStatus.BLOCKED])

    assert flow._is_zero_progress_dead_end() is True


def test_is_zero_progress_dead_end_false_when_any_step_completed() -> None:
    flow = _make_flow_with_plan([ExecutionStatus.COMPLETED, ExecutionStatus.BLOCKED, ExecutionStatus.FAILED])

    assert flow._is_zero_progress_dead_end() is False


def test_is_zero_progress_dead_end_false_when_pending_steps_remain() -> None:
    flow = _make_flow_with_plan([ExecutionStatus.FAILED, ExecutionStatus.PENDING])

    assert flow._is_zero_progress_dead_end() is False


def test_is_zero_progress_dead_end_false_when_plan_missing() -> None:
    flow = PlanActFlow.__new__(PlanActFlow)
    flow.plan = None
    flow._zero_progress_dead_end_replans = 0
    flow._max_zero_progress_dead_end_replans = 1

    assert flow._is_zero_progress_dead_end() is False


def test_consume_zero_progress_replan_attempt_allows_once_then_blocks() -> None:
    flow = _make_flow_with_plan([ExecutionStatus.BLOCKED])
    flow._max_zero_progress_dead_end_replans = 2

    assert flow._consume_zero_progress_replan_attempt() is True
    assert flow._zero_progress_dead_end_replans == 1
    assert flow._consume_zero_progress_replan_attempt() is True
    assert flow._zero_progress_dead_end_replans == 2
    assert flow._consume_zero_progress_replan_attempt() is False
    assert flow._zero_progress_dead_end_replans == 2
