"""Regression tests for verification revision routing in PlanActFlow."""

from app.domain.models.state_model import AgentStatus
from app.domain.services.flows.plan_act import PlanActFlow


def _make_flow(
    *,
    verification_loops: int,
    max_verification_loops: int,
    plan_validation_failures: int,
    max_plan_validation_failures: int,
) -> PlanActFlow:
    flow = PlanActFlow.__new__(PlanActFlow)
    flow._verification_loops = verification_loops
    flow._max_verification_loops = max_verification_loops
    flow._plan_validation_failures = plan_validation_failures
    flow._max_plan_validation_failures = max_plan_validation_failures
    return flow


def test_route_after_revision_needed_returns_planning_before_loop_limit() -> None:
    flow = _make_flow(
        verification_loops=0,
        max_verification_loops=1,
        plan_validation_failures=0,
        max_plan_validation_failures=3,
    )

    status, reason = flow._route_after_revision_needed()

    assert status == AgentStatus.PLANNING
    assert "revision" in reason
    assert flow._verification_loops == 0
    assert flow._plan_validation_failures == 0


def test_route_after_revision_needed_forces_replanning_when_loop_limit_hit() -> None:
    flow = _make_flow(
        verification_loops=1,
        max_verification_loops=1,
        plan_validation_failures=0,
        max_plan_validation_failures=3,
    )

    status, reason = flow._route_after_revision_needed()

    assert status == AgentStatus.PLANNING
    assert "forcing replanning" in reason
    assert flow._verification_loops == 0
    assert flow._plan_validation_failures == 1


def test_route_after_revision_needed_summarizes_after_repeated_forced_replans() -> None:
    flow = _make_flow(
        verification_loops=1,
        max_verification_loops=1,
        plan_validation_failures=2,
        max_plan_validation_failures=3,
    )

    status, reason = flow._route_after_revision_needed()

    assert status == AgentStatus.SUMMARIZING
    assert "without a valid plan" in reason
    assert flow._plan_validation_failures == 3
    assert flow._verification_loops == 1
