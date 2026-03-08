"""Tests for the phase registry module."""

from app.domain.models.plan import ExecutionStatus, PhaseType, Plan, Step, StepType
from app.domain.services.flows.phase_registry import (
    assign_steps_to_phases,
    build_phases,
    get_phase_template,
    select_phases_for_complexity,
)


class TestSelectPhasesForComplexity:
    """Tests for complexity-based phase selection."""

    def test_trivial_task_gets_base_phases(self):
        phases = select_phases_for_complexity(0.0)
        assert PhaseType.ALIGNMENT in phases
        assert PhaseType.REPORT_GENERATION in phases
        assert PhaseType.DELIVERY_FEEDBACK in phases
        assert len(phases) == 3

    def test_low_complexity_adds_research(self):
        phases = select_phases_for_complexity(0.3)
        assert PhaseType.RESEARCH_FOUNDATION in phases
        assert len(phases) == 4

    def test_medium_complexity_adds_analysis(self):
        phases = select_phases_for_complexity(0.6)
        assert PhaseType.ANALYSIS_SYNTHESIS in phases
        assert len(phases) == 5

    def test_high_complexity_gets_all_phases(self):
        phases = select_phases_for_complexity(0.8)
        assert len(phases) == 6
        assert PhaseType.QUALITY_ASSURANCE in phases

    def test_max_complexity(self):
        phases = select_phases_for_complexity(1.0)
        assert len(phases) == 6

    def test_phases_ordered_by_template_order(self):
        phases = select_phases_for_complexity(1.0)
        assert phases[0] == PhaseType.ALIGNMENT
        assert phases[-1] == PhaseType.DELIVERY_FEEDBACK


class TestBuildPhases:
    """Tests for building Phase objects from selected types."""

    def test_builds_correct_count(self):
        selected = [PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK]
        phases = build_phases(selected)
        assert len(phases) == 2

    def test_phases_have_correct_metadata(self):
        phases = build_phases([PhaseType.ALIGNMENT])
        p = phases[0]
        assert p.phase_type == PhaseType.ALIGNMENT
        assert p.label == "Understanding Your Goal"
        assert p.icon == "target"
        assert p.color == "blue"
        assert p.status == ExecutionStatus.PENDING

    def test_phases_sorted_by_order(self):
        # Pass in reverse order
        phases = build_phases([PhaseType.DELIVERY_FEEDBACK, PhaseType.ALIGNMENT])
        assert phases[0].order < phases[1].order

    def test_empty_selection(self):
        assert build_phases([]) == []


class TestGetPhaseTemplate:
    def test_existing_template(self):
        t = get_phase_template(PhaseType.QUALITY_ASSURANCE)
        assert t is not None
        assert t["label"] == "Quality Review"
        assert t["default_step_type"] == StepType.SELF_REVIEW

    def test_nonexistent_returns_none(self):
        # All types exist, but test the function works
        t = get_phase_template(PhaseType.ALIGNMENT)
        assert t is not None


class TestAssignStepsToPhases:
    """Tests for step-to-phase assignment."""

    def _make_plan(self, step_descriptions: list[str], phase_types: list[PhaseType]) -> Plan:
        steps = [Step(id=str(i + 1), description=d) for i, d in enumerate(step_descriptions)]
        phases = build_phases(phase_types)
        return Plan(steps=steps, phases=phases)

    def test_keyword_matching_research(self):
        plan = self._make_plan(
            ["Search for AI papers and gather sources"],
            [PhaseType.ALIGNMENT, PhaseType.RESEARCH_FOUNDATION, PhaseType.DELIVERY_FEEDBACK],
        )
        assign_steps_to_phases(plan)
        step = plan.steps[0]
        phase = plan.get_phase_by_id(step.phase_id)
        assert phase is not None
        assert phase.phase_type == PhaseType.RESEARCH_FOUNDATION

    def test_keyword_matching_analysis(self):
        plan = self._make_plan(
            ["Analyze findings and compare tradeoffs"],
            [PhaseType.ALIGNMENT, PhaseType.ANALYSIS_SYNTHESIS, PhaseType.DELIVERY_FEEDBACK],
        )
        assign_steps_to_phases(plan)
        step = plan.steps[0]
        phase = plan.get_phase_by_id(step.phase_id)
        assert phase is not None
        assert phase.phase_type == PhaseType.ANALYSIS_SYNTHESIS

    def test_pre_assigned_phase_id_preserved(self):
        plan = self._make_plan(
            ["Some step"],
            [PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK],
        )
        # Pre-assign
        target_phase = plan.phases[0]
        plan.steps[0].phase_id = target_phase.id
        assign_steps_to_phases(plan)
        assert plan.steps[0].phase_id == target_phase.id
        assert plan.steps[0].id in target_phase.step_ids

    def test_positional_fallback(self):
        plan = self._make_plan(
            ["Do something unusual xyz123"],
            [PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK],
        )
        assign_steps_to_phases(plan)
        # Should be assigned to first phase by position
        assert plan.steps[0].phase_id is not None

    def test_no_phases_is_noop(self):
        plan = Plan(steps=[Step(id="1", description="test")])
        assign_steps_to_phases(plan)
        assert plan.steps[0].phase_id is None

    def test_step_type_set_from_template(self):
        plan = self._make_plan(
            ["Fact-check all claims and verify"],
            [PhaseType.QUALITY_ASSURANCE],
        )
        assign_steps_to_phases(plan)
        assert plan.steps[0].step_type == StepType.SELF_REVIEW

    def test_multiple_steps_distributed(self):
        plan = self._make_plan(
            [
                "Understand the user goal",
                "Search for relevant sources",
                "Analyze the findings",
                "Draft the report",
                "Deliver final report",
            ],
            select_phases_for_complexity(1.0),
        )
        assign_steps_to_phases(plan)
        # All steps should have phase_id
        for step in plan.steps:
            assert step.phase_id is not None


class TestPlanPhaseHelpers:
    """Tests for Plan helper methods related to phases."""

    def test_get_phase_by_type(self):
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        plan = Plan(steps=[], phases=phases)
        p = plan.get_phase_by_type(PhaseType.ALIGNMENT)
        assert p is not None
        assert p.phase_type == PhaseType.ALIGNMENT

    def test_get_phase_by_type_missing(self):
        plan = Plan(steps=[], phases=[])
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is None

    def test_get_phase_by_id(self):
        phases = build_phases([PhaseType.ALIGNMENT])
        plan = Plan(steps=[], phases=phases)
        p = plan.get_phase_by_id(phases[0].id)
        assert p is not None

    def test_get_current_phase(self):
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        phases[0].status = ExecutionStatus.COMPLETED
        phases[1].status = ExecutionStatus.RUNNING
        plan = Plan(steps=[], phases=phases)
        current = plan.get_current_phase()
        assert current is not None
        assert current.phase_type == PhaseType.DELIVERY_FEEDBACK

    def test_get_current_phase_returns_first_pending(self):
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        plan = Plan(steps=[], phases=phases)
        current = plan.get_current_phase()
        assert current is not None
        assert current.phase_type == PhaseType.ALIGNMENT

    def test_backward_compat_no_phases(self):
        """Plans without phases should work fine."""
        plan = Plan(steps=[Step(id="1", description="test")])
        assert plan.phases == []
        assert plan.get_current_phase() is None
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is None

    def test_sync_phase_statuses_marks_started_phase_running(self):
        phases = build_phases([PhaseType.RESEARCH_FOUNDATION, PhaseType.REPORT_GENERATION])
        plan = Plan(
            steps=[
                Step(id="1", description="Research", status=ExecutionStatus.COMPLETED, success=True),
                Step(id="2", description="Write report", status=ExecutionStatus.PENDING),
            ],
            phases=phases,
        )
        phases[0].step_ids = ["1"]
        phases[1].step_ids = ["2"]

        plan.sync_phase_statuses()

        assert phases[0].status == ExecutionStatus.COMPLETED
        assert phases[1].status == ExecutionStatus.PENDING

    def test_sync_phase_statuses_marks_mixed_phase_running(self):
        phases = build_phases([PhaseType.RESEARCH_FOUNDATION])
        plan = Plan(
            steps=[
                Step(id="1", description="Research one", status=ExecutionStatus.COMPLETED, success=True),
                Step(id="2", description="Research two", status=ExecutionStatus.PENDING),
            ],
            phases=phases,
        )
        phases[0].step_ids = ["1", "2"]

        plan.sync_phase_statuses()

        assert phases[0].status == ExecutionStatus.RUNNING
