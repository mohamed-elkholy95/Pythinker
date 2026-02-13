"""Regression tests for plan-update skip heuristics in PlanActFlow."""

from app.domain.models.plan import Plan, Step
from app.domain.services.flows.plan_act import PlanActFlow


def _make_flow(message: str = "", complexity: float | None = None) -> PlanActFlow:
    flow = PlanActFlow.__new__(PlanActFlow)
    flow.plan = Plan(goal=message, message=message, steps=[])
    flow._cached_complexity = complexity
    return flow


def test_research_step_not_classified_as_read_only() -> None:
    flow = _make_flow()
    step = Step(description="Research model benchmarks across multiple sources")
    assert flow._is_read_only_step(step) is False


def test_plan_update_not_skipped_for_research_with_two_remaining_steps() -> None:
    flow = _make_flow(message="Research AI agents and produce report", complexity=0.8)
    step = Step(description="Research AI agent frameworks", success=True)

    should_skip, _ = flow._should_skip_plan_update(step, remaining_steps=2)

    assert should_skip is False


def test_plan_update_not_skipped_for_research_with_one_remaining_step() -> None:
    flow = _make_flow(message="Investigate browser automation stacks", complexity=0.7)
    step = Step(description="Investigate benchmark differences", success=True)

    should_skip, _ = flow._should_skip_plan_update(step, remaining_steps=1)

    assert should_skip is False


def test_non_research_simple_task_can_skip_update() -> None:
    flow = _make_flow(message="Quick check local status", complexity=0.2)
    step = Step(description="Read the current status output", success=True)

    should_skip, reason = flow._should_skip_plan_update(step, remaining_steps=1)

    assert should_skip is True
    assert "simple task" in reason or "step" in reason
