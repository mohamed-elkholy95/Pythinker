"""Tests for LazyPlanner, LazyPlan, and LazyStep."""

from datetime import UTC, datetime

import pytest

from app.domain.services.agents.planning.lazy_planner import (
    LazyPlan,
    LazyPlanner,
    LazyStep,
    StepDetailLevel,
    get_lazy_planner,
    reset_lazy_planner,
)


# ---------------------------------------------------------------------------
# StepDetailLevel enum
# ---------------------------------------------------------------------------


class TestStepDetailLevel:
    def test_values(self):
        assert StepDetailLevel.SKELETON == "skeleton"
        assert StepDetailLevel.OUTLINE == "outline"
        assert StepDetailLevel.DETAILED == "detailed"
        assert StepDetailLevel.EXECUTED == "executed"


# ---------------------------------------------------------------------------
# LazyStep
# ---------------------------------------------------------------------------


class TestLazyStep:
    def test_defaults(self):
        s = LazyStep(step_id="s1", description="do thing")
        assert s.detail_level == StepDetailLevel.OUTLINE
        assert s.detailed_actions == []
        assert s.tool_requirements == []
        assert s.dependencies == []
        assert s.expanded_at is None
        assert s.executed_at is None

    def test_needs_expansion_skeleton(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.SKELETON)
        assert s.needs_expansion() is True

    def test_needs_expansion_outline(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.OUTLINE)
        assert s.needs_expansion() is True

    def test_needs_expansion_detailed(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.DETAILED)
        assert s.needs_expansion() is False

    def test_needs_expansion_executed(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.EXECUTED)
        assert s.needs_expansion() is False

    def test_is_ready_to_execute(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.DETAILED)
        assert s.is_ready_to_execute() is True

    def test_is_not_ready_outline(self):
        s = LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.OUTLINE)
        assert s.is_ready_to_execute() is False

    def test_expand(self):
        s = LazyStep(step_id="s1", description="d")
        s.expand(detailed_actions=["a1", "a2"], tool_requirements=["shell_exec"])
        assert s.detail_level == StepDetailLevel.DETAILED
        assert s.detailed_actions == ["a1", "a2"]
        assert s.tool_requirements == ["shell_exec"]
        assert s.expanded_at is not None


# ---------------------------------------------------------------------------
# LazyPlan
# ---------------------------------------------------------------------------


class TestLazyPlan:
    def _make_plan(self) -> LazyPlan:
        return LazyPlan(
            plan_id="p1",
            goal="test goal",
            lazy_steps=[
                LazyStep(step_id="s1", description="step 1", detail_level=StepDetailLevel.EXECUTED),
                LazyStep(step_id="s2", description="step 2", detail_level=StepDetailLevel.DETAILED),
                LazyStep(step_id="s3", description="step 3", detail_level=StepDetailLevel.OUTLINE),
            ],
        )

    def test_get_step_found(self):
        plan = self._make_plan()
        assert plan.get_step("s2") is not None
        assert plan.get_step("s2").description == "step 2"

    def test_get_step_not_found(self):
        plan = self._make_plan()
        assert plan.get_step("nope") is None

    def test_get_current_step(self):
        plan = self._make_plan()
        current = plan.get_current_step()
        assert current is not None
        assert current.step_id == "s2"

    def test_get_current_step_all_executed(self):
        plan = LazyPlan(
            plan_id="p1", goal="g",
            lazy_steps=[
                LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.EXECUTED),
            ],
        )
        assert plan.get_current_step() is None

    def test_get_steps_needing_expansion(self):
        plan = self._make_plan()
        plan.expansion_horizon = 2
        needing = plan.get_steps_needing_expansion()
        assert len(needing) == 1
        assert needing[0].step_id == "s3"

    def test_get_steps_needing_expansion_none_needed(self):
        plan = LazyPlan(
            plan_id="p1", goal="g",
            lazy_steps=[
                LazyStep(step_id="s1", description="d", detail_level=StepDetailLevel.DETAILED),
            ],
        )
        assert plan.get_steps_needing_expansion() == []


# ---------------------------------------------------------------------------
# LazyPlanner
# ---------------------------------------------------------------------------


class TestLazyPlanner:
    def test_init_defaults(self):
        p = LazyPlanner()
        assert p._expansion_horizon == 2

    def test_init_custom_horizon(self):
        p = LazyPlanner(expansion_horizon=4)
        assert p._expansion_horizon == 4

    def test_create_lazy_plan(self):
        p = LazyPlanner(expansion_horizon=2)
        plan = p.create_lazy_plan("p1", "test goal", ["s1", "s2", "s3", "s4"])
        assert plan.plan_id == "p1"
        assert len(plan.lazy_steps) == 4
        assert plan.lazy_steps[0].detail_level == StepDetailLevel.DETAILED
        assert plan.lazy_steps[1].detail_level == StepDetailLevel.DETAILED
        assert plan.lazy_steps[2].detail_level == StepDetailLevel.OUTLINE
        assert plan.lazy_steps[3].detail_level == StepDetailLevel.OUTLINE

    def test_create_lazy_plan_truncates_at_max(self):
        p = LazyPlanner()
        steps = [f"step {i}" for i in range(20)]
        plan = p.create_lazy_plan("p1", "g", steps)
        assert len(plan.lazy_steps) == LazyPlanner.MAX_INITIAL_STEPS

    def test_create_lazy_plan_stored(self):
        p = LazyPlanner()
        plan = p.create_lazy_plan("p1", "g", ["s1"])
        assert "p1" in p._active_plans
        assert p._active_plans["p1"] is plan

    def test_expand_step(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1", "s2", "s3"])
        result = p.expand_step("p1", "step_3", ["action1", "action2"], ["shell_exec"])
        assert result is not None
        assert result.detail_level == StepDetailLevel.DETAILED
        assert result.detailed_actions == ["action1", "action2"]

    def test_expand_step_with_context(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1"])
        result = p.expand_step("p1", "step_1", ["a"], context={"key": "value"})
        assert result.expansion_context == {"key": "value"}

    def test_expand_step_missing_plan(self):
        p = LazyPlanner()
        assert p.expand_step("nope", "s1", ["a"]) is None

    def test_expand_step_missing_step(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1"])
        assert p.expand_step("p1", "nonexistent", ["a"]) is None

    def test_mark_step_executed(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1", "s2", "s3"])
        needing = p.mark_step_executed("p1", "step_1", result={"output": "ok"})
        plan = p._active_plans["p1"]
        step = plan.get_step("step_1")
        assert step.detail_level == StepDetailLevel.EXECUTED
        assert step.executed_at is not None
        assert step.expansion_context["result"] == {"output": "ok"}

    def test_mark_step_executed_returns_expansion_needed(self):
        p = LazyPlanner(expansion_horizon=2)
        p.create_lazy_plan("p1", "g", ["s1", "s2", "s3", "s4"])
        # Mark step_1 executed → step_2 already detailed, step_3 needs expansion
        needing = p.mark_step_executed("p1", "step_1")
        step_ids = [s.step_id for s in needing]
        assert "step_3" in step_ids

    def test_mark_step_executed_missing_plan(self):
        p = LazyPlanner()
        assert p.mark_step_executed("nope", "s1") == []

    def test_get_expansion_context(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1", "s2"])
        p.mark_step_executed("p1", "step_1", result={"data": 42})
        ctx = p.get_expansion_context("p1")
        assert "step_1" in ctx
        assert ctx["step_1"]["result"] == {"data": 42}

    def test_get_expansion_context_missing_plan(self):
        p = LazyPlanner()
        assert p.get_expansion_context("nope") == {}

    def test_adapt_remaining_steps(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1", "s2", "s3"])
        adapted = p.adapt_remaining_steps("p1", {"new": "info"})
        # step_1 and step_2 are DETAILED (within horizon), step_3 is OUTLINE
        outline_steps = [s for s in adapted if s.detail_level == StepDetailLevel.OUTLINE]
        assert len(outline_steps) == 1
        assert outline_steps[0].expansion_context["new"] == "info"

    def test_adapt_remaining_steps_missing_plan(self):
        p = LazyPlanner()
        assert p.adapt_remaining_steps("nope", {}) == []

    def test_get_plan_progress(self):
        p = LazyPlanner(expansion_horizon=1)
        p.create_lazy_plan("p1", "g", ["s1", "s2", "s3"])
        p.mark_step_executed("p1", "step_1")
        progress = p.get_plan_progress("p1")
        assert progress["total_steps"] == 3
        assert progress["executed"] == 1
        assert progress["current_step"] == "step_2"
        assert pytest.approx(progress["progress_percent"], abs=0.1) == 33.3

    def test_get_plan_progress_missing_plan(self):
        p = LazyPlanner()
        assert p.get_plan_progress("nope") == {}

    def test_cleanup_plan(self):
        p = LazyPlanner()
        p.create_lazy_plan("p1", "g", ["s1"])
        p.cleanup_plan("p1")
        assert "p1" not in p._active_plans

    def test_cleanup_plan_nonexistent(self):
        p = LazyPlanner()
        p.cleanup_plan("nope")  # should not raise


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_lazy_planner()

    def teardown_method(self):
        reset_lazy_planner()

    def test_get_returns_same(self):
        p1 = get_lazy_planner()
        p2 = get_lazy_planner()
        assert p1 is p2

    def test_reset_creates_new(self):
        p1 = get_lazy_planner()
        reset_lazy_planner()
        p2 = get_lazy_planner()
        assert p1 is not p2
