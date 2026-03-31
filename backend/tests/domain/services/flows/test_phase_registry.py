"""Tests for phase_registry.py — PHASE_TEMPLATES, select_phases_for_complexity,
build_phases, get_phase_template, and assign_steps_to_phases."""

from __future__ import annotations

import pytest

from app.domain.models.plan import ExecutionStatus, Phase, PhaseType, Plan, Step, StepType
from app.domain.services.flows.phase_registry import (
    PHASE_TEMPLATES,
    assign_steps_to_phases,
    build_phases,
    get_phase_template,
    select_phases_for_complexity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_PHASE_TYPES = [
    PhaseType.ALIGNMENT,
    PhaseType.RESEARCH_FOUNDATION,
    PhaseType.ANALYSIS_SYNTHESIS,
    PhaseType.REPORT_GENERATION,
    PhaseType.QUALITY_ASSURANCE,
    PhaseType.DELIVERY_FEEDBACK,
]

_ALWAYS_INCLUDED = {
    PhaseType.ALIGNMENT,
    PhaseType.REPORT_GENERATION,
    PhaseType.DELIVERY_FEEDBACK,
}


def _make_plan(steps: list[Step], phases: list[Phase] | None = None) -> Plan:
    return Plan(steps=steps, phases=phases or [])


def _make_step(description: str, phase_id: str | None = None) -> Step:
    return Step(description=description, phase_id=phase_id)


# ---------------------------------------------------------------------------
# PHASE_TEMPLATES structure
# ---------------------------------------------------------------------------


class TestPhaseTemplates:
    def test_has_exactly_six_entries(self) -> None:
        assert len(PHASE_TEMPLATES) == 6

    def test_all_required_keys_present(self) -> None:
        required = {
            "phase_type",
            "label",
            "description",
            "icon",
            "color",
            "order",
            "complexity_threshold",
            "step_hints",
            "default_step_type",
        }
        for template in PHASE_TEMPLATES:
            assert required <= template.keys(), f"Missing keys in {template['phase_type']}"

    def test_phase_types_are_enum_members(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["phase_type"], PhaseType)

    def test_all_six_phase_types_present(self) -> None:
        types = {t["phase_type"] for t in PHASE_TEMPLATES}
        assert types == set(_ALL_PHASE_TYPES)

    def test_orders_are_one_through_six(self) -> None:
        orders = sorted(t["order"] for t in PHASE_TEMPLATES)
        assert orders == [1, 2, 3, 4, 5, 6]

    def test_orders_are_unique(self) -> None:
        orders = [t["order"] for t in PHASE_TEMPLATES]
        assert len(orders) == len(set(orders))

    def test_alignment_is_order_one(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ALIGNMENT)
        assert tmpl["order"] == 1

    def test_report_generation_is_order_four(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.REPORT_GENERATION)
        assert tmpl["order"] == 4

    def test_delivery_feedback_is_order_six(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.DELIVERY_FEEDBACK)
        assert tmpl["order"] == 6

    def test_always_included_phases_have_zero_threshold(self) -> None:
        zero_threshold = {t["phase_type"] for t in PHASE_TEMPLATES if t["complexity_threshold"] == 0.0}
        assert zero_threshold == _ALWAYS_INCLUDED

    def test_analysis_synthesis_threshold_is_0_6(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ANALYSIS_SYNTHESIS)
        assert tmpl["complexity_threshold"] == 0.6

    def test_quality_assurance_threshold_is_0_8(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.QUALITY_ASSURANCE)
        assert tmpl["complexity_threshold"] == 0.8

    def test_research_foundation_threshold_is_0_3(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.RESEARCH_FOUNDATION)
        assert tmpl["complexity_threshold"] == 0.3

    def test_step_hints_are_non_empty_lists(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["step_hints"], list)
            assert len(template["step_hints"]) >= 1, f"Empty step_hints in {template['phase_type']}"

    def test_step_hints_contain_strings(self) -> None:
        for template in PHASE_TEMPLATES:
            for hint in template["step_hints"]:
                assert isinstance(hint, str) and hint.strip()

    def test_default_step_types_are_valid_enum_members(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["default_step_type"], StepType)

    def test_alignment_default_step_type(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ALIGNMENT)
        assert tmpl["default_step_type"] == StepType.ALIGNMENT

    def test_delivery_feedback_default_step_type(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.DELIVERY_FEEDBACK)
        assert tmpl["default_step_type"] == StepType.DELIVERY

    def test_quality_assurance_default_step_type(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.QUALITY_ASSURANCE)
        assert tmpl["default_step_type"] == StepType.SELF_REVIEW

    def test_research_foundation_default_step_type_is_execution(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.RESEARCH_FOUNDATION)
        assert tmpl["default_step_type"] == StepType.EXECUTION

    def test_analysis_synthesis_default_step_type_is_execution(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ANALYSIS_SYNTHESIS)
        assert tmpl["default_step_type"] == StepType.EXECUTION

    def test_report_generation_default_step_type_is_execution(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.REPORT_GENERATION)
        assert tmpl["default_step_type"] == StepType.EXECUTION

    def test_labels_are_non_empty_strings(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["label"], str)
            assert template["label"].strip()

    def test_icons_are_non_empty_strings(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["icon"], str)
            assert template["icon"].strip()

    def test_colors_are_non_empty_strings(self) -> None:
        for template in PHASE_TEMPLATES:
            assert isinstance(template["color"], str)
            assert template["color"].strip()

    def test_alignment_label(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ALIGNMENT)
        assert tmpl["label"] == "Understanding Your Goal"

    def test_quality_assurance_label(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.QUALITY_ASSURANCE)
        assert tmpl["label"] == "Quality Review"

    def test_alignment_icon(self) -> None:
        tmpl = next(t for t in PHASE_TEMPLATES if t["phase_type"] == PhaseType.ALIGNMENT)
        assert tmpl["icon"] == "target"


# ---------------------------------------------------------------------------
# select_phases_for_complexity
# ---------------------------------------------------------------------------


class TestSelectPhasesForComplexity:
    def test_score_zero_returns_three_always_included(self) -> None:
        result = select_phases_for_complexity(0.0)
        assert set(result) == _ALWAYS_INCLUDED

    def test_score_zero_has_exactly_three_phases(self) -> None:
        result = select_phases_for_complexity(0.0)
        assert len(result) == 3

    def test_score_one_returns_all_six(self) -> None:
        result = select_phases_for_complexity(1.0)
        assert set(result) == set(_ALL_PHASE_TYPES)

    def test_score_one_has_exactly_six_phases(self) -> None:
        result = select_phases_for_complexity(1.0)
        assert len(result) == 6

    def test_score_0_3_includes_research_foundation(self) -> None:
        result = select_phases_for_complexity(0.3)
        assert PhaseType.RESEARCH_FOUNDATION in result

    def test_score_0_3_has_four_phases(self) -> None:
        result = select_phases_for_complexity(0.3)
        assert len(result) == 4

    def test_score_0_3_excludes_analysis_synthesis(self) -> None:
        result = select_phases_for_complexity(0.3)
        assert PhaseType.ANALYSIS_SYNTHESIS not in result

    def test_score_0_3_excludes_quality_assurance(self) -> None:
        result = select_phases_for_complexity(0.3)
        assert PhaseType.QUALITY_ASSURANCE not in result

    def test_score_0_29_excludes_research_foundation(self) -> None:
        result = select_phases_for_complexity(0.29)
        assert PhaseType.RESEARCH_FOUNDATION not in result

    def test_score_0_6_includes_analysis_synthesis(self) -> None:
        result = select_phases_for_complexity(0.6)
        assert PhaseType.ANALYSIS_SYNTHESIS in result

    def test_score_0_6_has_five_phases(self) -> None:
        result = select_phases_for_complexity(0.6)
        assert len(result) == 5

    def test_score_0_6_excludes_quality_assurance(self) -> None:
        result = select_phases_for_complexity(0.6)
        assert PhaseType.QUALITY_ASSURANCE not in result

    def test_score_0_59_excludes_analysis_synthesis(self) -> None:
        result = select_phases_for_complexity(0.59)
        assert PhaseType.ANALYSIS_SYNTHESIS not in result

    def test_score_0_8_includes_quality_assurance(self) -> None:
        result = select_phases_for_complexity(0.8)
        assert PhaseType.QUALITY_ASSURANCE in result

    def test_score_0_8_has_six_phases(self) -> None:
        result = select_phases_for_complexity(0.8)
        assert len(result) == 6

    def test_score_0_79_excludes_quality_assurance(self) -> None:
        result = select_phases_for_complexity(0.79)
        assert PhaseType.QUALITY_ASSURANCE not in result

    def test_returns_list_type(self) -> None:
        result = select_phases_for_complexity(0.5)
        assert isinstance(result, list)

    def test_always_included_phases_present_at_any_score(self) -> None:
        for score in [0.0, 0.1, 0.5, 0.9, 1.0]:
            result = select_phases_for_complexity(score)
            for phase_type in _ALWAYS_INCLUDED:
                assert phase_type in result, f"{phase_type} missing at score {score}"

    def test_result_order_matches_phase_templates_declaration_order(self) -> None:
        result = select_phases_for_complexity(1.0)
        template_order = [t["phase_type"] for t in PHASE_TEMPLATES]
        indices = [template_order.index(pt) for pt in result]
        assert indices == sorted(indices)

    def test_first_element_is_alignment_at_full_complexity(self) -> None:
        result = select_phases_for_complexity(1.0)
        assert result[0] == PhaseType.ALIGNMENT

    def test_last_element_is_delivery_feedback_at_full_complexity(self) -> None:
        result = select_phases_for_complexity(1.0)
        assert result[-1] == PhaseType.DELIVERY_FEEDBACK


# ---------------------------------------------------------------------------
# build_phases
# ---------------------------------------------------------------------------


class TestBuildPhases:
    def test_empty_list_returns_empty(self) -> None:
        assert build_phases([]) == []

    def test_returns_list_of_phase_objects(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        assert all(isinstance(p, Phase) for p in phases)

    def test_single_type_returns_one_phase(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        assert len(phases) == 1

    def test_phase_has_correct_phase_type(self) -> None:
        phases = build_phases([PhaseType.REPORT_GENERATION])
        assert phases[0].phase_type == PhaseType.REPORT_GENERATION

    def test_phase_label_matches_template(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        tmpl = get_phase_template(PhaseType.ALIGNMENT)
        assert tmpl is not None
        assert phases[0].label == tmpl["label"]

    def test_phase_description_matches_template(self) -> None:
        phases = build_phases([PhaseType.RESEARCH_FOUNDATION])
        tmpl = get_phase_template(PhaseType.RESEARCH_FOUNDATION)
        assert tmpl is not None
        assert phases[0].description == tmpl["description"]

    def test_phase_icon_matches_template(self) -> None:
        phases = build_phases([PhaseType.QUALITY_ASSURANCE])
        tmpl = get_phase_template(PhaseType.QUALITY_ASSURANCE)
        assert tmpl is not None
        assert phases[0].icon == tmpl["icon"]

    def test_phase_color_matches_template(self) -> None:
        phases = build_phases([PhaseType.DELIVERY_FEEDBACK])
        tmpl = get_phase_template(PhaseType.DELIVERY_FEEDBACK)
        assert tmpl is not None
        assert phases[0].color == tmpl["color"]

    def test_phase_order_matches_template(self) -> None:
        phases = build_phases([PhaseType.ANALYSIS_SYNTHESIS])
        tmpl = get_phase_template(PhaseType.ANALYSIS_SYNTHESIS)
        assert tmpl is not None
        assert phases[0].order == tmpl["order"]

    def test_phase_status_is_pending(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        assert phases[0].status == ExecutionStatus.PENDING

    def test_all_six_types_produces_six_phases(self) -> None:
        phases = build_phases(_ALL_PHASE_TYPES)
        assert len(phases) == 6

    def test_phases_sorted_by_order_ascending(self) -> None:
        # Supply in reverse order to confirm sorting
        reversed_types = list(reversed(_ALL_PHASE_TYPES))
        phases = build_phases(reversed_types)
        orders = [p.order for p in phases]
        assert orders == sorted(orders)

    def test_two_types_out_of_order_still_sorted(self) -> None:
        phases = build_phases([PhaseType.DELIVERY_FEEDBACK, PhaseType.ALIGNMENT])
        assert phases[0].order < phases[1].order

    def test_subset_phases_are_in_order(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.REPORT_GENERATION, PhaseType.DELIVERY_FEEDBACK])
        orders = [p.order for p in phases]
        assert orders == sorted(orders)

    def test_duplicate_types_produce_one_entry(self) -> None:
        # PHASE_TEMPLATES has one entry per type; iterating it deduplicates
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.ALIGNMENT])
        assert len(phases) == 1

    def test_phase_step_ids_initially_empty(self) -> None:
        phases = build_phases([PhaseType.REPORT_GENERATION])
        assert phases[0].step_ids == []

    def test_phases_have_unique_ids(self) -> None:
        phases = build_phases(_ALL_PHASE_TYPES)
        ids = [p.id for p in phases]
        assert len(ids) == len(set(ids))

    def test_alignment_phase_metadata(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        p = phases[0]
        assert p.label == "Understanding Your Goal"
        assert p.icon == "target"
        assert p.color == "blue"
        assert p.order == 1


# ---------------------------------------------------------------------------
# get_phase_template
# ---------------------------------------------------------------------------


class TestGetPhaseTemplate:
    @pytest.mark.parametrize("phase_type", _ALL_PHASE_TYPES)
    def test_returns_dict_for_all_valid_types(self, phase_type: PhaseType) -> None:
        result = get_phase_template(phase_type)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("phase_type", _ALL_PHASE_TYPES)
    def test_returned_template_has_matching_phase_type(self, phase_type: PhaseType) -> None:
        result = get_phase_template(phase_type)
        assert result is not None
        assert result["phase_type"] == phase_type

    def test_alignment_template_has_correct_order(self) -> None:
        tmpl = get_phase_template(PhaseType.ALIGNMENT)
        assert tmpl is not None
        assert tmpl["order"] == 1

    def test_delivery_feedback_template_has_correct_order(self) -> None:
        tmpl = get_phase_template(PhaseType.DELIVERY_FEEDBACK)
        assert tmpl is not None
        assert tmpl["order"] == 6

    def test_quality_assurance_template_label(self) -> None:
        tmpl = get_phase_template(PhaseType.QUALITY_ASSURANCE)
        assert tmpl is not None
        assert tmpl["label"] == "Quality Review"

    def test_quality_assurance_default_step_type(self) -> None:
        tmpl = get_phase_template(PhaseType.QUALITY_ASSURANCE)
        assert tmpl is not None
        assert tmpl["default_step_type"] == StepType.SELF_REVIEW

    def test_returns_same_object_as_in_phase_templates(self) -> None:
        result = get_phase_template(PhaseType.REPORT_GENERATION)
        assert result in PHASE_TEMPLATES

    def test_returns_none_for_string_not_matching_any_template(self) -> None:
        result = get_phase_template("nonexistent_type")  # type: ignore[arg-type]
        assert result is None

    def test_research_foundation_description(self) -> None:
        tmpl = get_phase_template(PhaseType.RESEARCH_FOUNDATION)
        assert tmpl is not None
        assert "research" in tmpl["description"].lower() or "information" in tmpl["description"].lower()


# ---------------------------------------------------------------------------
# assign_steps_to_phases — edge cases
# ---------------------------------------------------------------------------


class TestAssignStepsToPhasesEdgeCases:
    def test_empty_steps_does_nothing(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.REPORT_GENERATION, PhaseType.DELIVERY_FEEDBACK])
        plan = _make_plan(steps=[], phases=phases)
        assign_steps_to_phases(plan)
        for phase in plan.phases:
            assert phase.step_ids == []

    def test_empty_phases_does_nothing(self) -> None:
        step = _make_step("search for information")
        plan = _make_plan(steps=[step], phases=[])
        assign_steps_to_phases(plan)
        assert step.phase_id is None

    def test_no_mutation_when_phases_empty(self) -> None:
        step = _make_step("clarify the objective")
        plan = _make_plan(steps=[step], phases=[])
        assign_steps_to_phases(plan)
        assert step.phase_id is None

    def test_pre_assigned_step_not_reassigned(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.REPORT_GENERATION, PhaseType.DELIVERY_FEEDBACK])
        alignment_phase = next(p for p in phases if p.phase_type == PhaseType.ALIGNMENT)
        # Step description matches REPORT_GENERATION keywords, but phase_id is already set
        step = _make_step("write a report about dragons", phase_id=alignment_phase.id)
        alignment_phase.step_ids.append(step.id)
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        assert step.phase_id == alignment_phase.id

    def test_pre_assigned_step_added_to_phase_step_ids_if_missing(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.REPORT_GENERATION, PhaseType.DELIVERY_FEEDBACK])
        alignment_phase = next(p for p in phases if p.phase_type == PhaseType.ALIGNMENT)
        step = _make_step("clarify the objective", phase_id=alignment_phase.id)
        # Do NOT pre-populate phase.step_ids
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        assert step.id in alignment_phase.step_ids

    def test_pre_assigned_step_not_duplicated_in_step_ids(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.REPORT_GENERATION, PhaseType.DELIVERY_FEEDBACK])
        alignment_phase = next(p for p in phases if p.phase_type == PhaseType.ALIGNMENT)
        step = _make_step("define scope", phase_id=alignment_phase.id)
        alignment_phase.step_ids.append(step.id)  # Already present
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        assert alignment_phase.step_ids.count(step.id) == 1

    def test_no_phases_is_noop(self) -> None:
        plan = Plan(steps=[Step(id="1", description="test")])
        assign_steps_to_phases(plan)
        assert plan.steps[0].phase_id is None


# ---------------------------------------------------------------------------
# assign_steps_to_phases — keyword matching
# ---------------------------------------------------------------------------


class TestAssignStepsToPhasesKeywordMatching:
    def _plan_with_all_phases(self, steps: list[Step]) -> Plan:
        phases = build_phases(_ALL_PHASE_TYPES)
        return _make_plan(steps=steps, phases=phases)

    def _phase_for(self, plan: Plan, phase_type: PhaseType) -> Phase:
        return next(p for p in plan.phases if p.phase_type == phase_type)

    # --- ALIGNMENT keywords ---

    def test_clarify_keyword_maps_to_alignment(self) -> None:
        step = _make_step("clarify the research objective")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ALIGNMENT)
        assert step.phase_id == phase.id

    def test_understand_keyword_maps_to_alignment(self) -> None:
        step = _make_step("understand the user requirements")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ALIGNMENT)
        assert step.phase_id == phase.id

    def test_scope_keyword_maps_to_alignment(self) -> None:
        step = _make_step("define the project scope and constraints")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ALIGNMENT)
        assert step.phase_id == phase.id

    def test_goal_keyword_maps_to_alignment(self) -> None:
        step = _make_step("identify goal and objective")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ALIGNMENT)
        assert step.phase_id == phase.id

    # --- RESEARCH_FOUNDATION keywords ---

    def test_search_keyword_maps_to_research(self) -> None:
        step = _make_step("search the web for relevant sources")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.phase_id == phase.id

    def test_research_keyword_maps_to_research(self) -> None:
        step = _make_step("research Python 3.12 release notes")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.phase_id == phase.id

    def test_gather_keyword_maps_to_research(self) -> None:
        step = _make_step("gather information from credible sources")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.phase_id == phase.id

    def test_browse_keyword_maps_to_research(self) -> None:
        step = _make_step("browse top result pages for context")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.phase_id == phase.id

    def test_investigate_keyword_maps_to_research(self) -> None:
        step = _make_step("investigate the root cause of the issue")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.phase_id == phase.id

    # --- ANALYSIS_SYNTHESIS keywords ---

    def test_analyze_keyword_maps_to_analysis(self) -> None:
        step = _make_step("analyze the collected data for patterns")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ANALYSIS_SYNTHESIS)
        assert step.phase_id == phase.id

    def test_compare_keyword_maps_to_analysis(self) -> None:
        step = _make_step("compare the top three frameworks")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ANALYSIS_SYNTHESIS)
        assert step.phase_id == phase.id

    def test_tradeoff_keyword_maps_to_analysis(self) -> None:
        step = _make_step("evaluate tradeoffs between approaches")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ANALYSIS_SYNTHESIS)
        assert step.phase_id == phase.id

    def test_assess_keyword_maps_to_analysis(self) -> None:
        step = _make_step("assess risks and uncertainties")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ANALYSIS_SYNTHESIS)
        assert step.phase_id == phase.id

    def test_insight_keyword_maps_to_analysis(self) -> None:
        # "assess", "risk", "pattern" each match ANALYSIS_SYNTHESIS — unambiguous winner
        step = _make_step("assess risks and identify patterns in the data")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.ANALYSIS_SYNTHESIS)
        assert step.phase_id == phase.id

    # --- REPORT_GENERATION keywords ---

    def test_report_keyword_maps_to_report_generation(self) -> None:
        step = _make_step("write the final report with citations")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.REPORT_GENERATION)
        assert step.phase_id == phase.id

    def test_draft_keyword_maps_to_report_generation(self) -> None:
        step = _make_step("draft the executive summary section")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.REPORT_GENERATION)
        assert step.phase_id == phase.id

    def test_compile_keyword_maps_to_report_generation(self) -> None:
        step = _make_step("compile all findings into a document")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.REPORT_GENERATION)
        assert step.phase_id == phase.id

    # --- QUALITY_ASSURANCE keywords ---

    def test_quality_keyword_maps_to_qa(self) -> None:
        step = _make_step("quality check the final output")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.QUALITY_ASSURANCE)
        assert step.phase_id == phase.id

    def test_polish_keyword_maps_to_qa(self) -> None:
        step = _make_step("polish the text for readability")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.QUALITY_ASSURANCE)
        assert step.phase_id == phase.id

    def test_proofread_keyword_maps_to_qa(self) -> None:
        # "quality", "proofread", "readab" all match QA — unambiguous winner
        step = _make_step("quality review and proofread for readability")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.QUALITY_ASSURANCE)
        assert step.phase_id == phase.id

    def test_validate_claims_against_sources_maps_to_qa(self) -> None:
        step = _make_step("Review and validate all claims against sources")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.QUALITY_ASSURANCE)
        assert step.phase_id == phase.id
        assert step.step_type == StepType.SELF_REVIEW

    # --- DELIVERY_FEEDBACK keywords ---

    def test_deliver_keyword_maps_to_delivery(self) -> None:
        step = _make_step("deliver the final report to the user")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.DELIVERY_FEEDBACK)
        assert step.phase_id == phase.id

    def test_present_keyword_maps_to_delivery(self) -> None:
        step = _make_step("present findings with confidence score")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.DELIVERY_FEEDBACK)
        assert step.phase_id == phase.id

    def test_submit_keyword_maps_to_delivery(self) -> None:
        # "deliver", "present", "final", "confidence score" all match DELIVERY — unambiguous winner
        step = _make_step("deliver and present final output with confidence score")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        phase = self._phase_for(plan, PhaseType.DELIVERY_FEEDBACK)
        assert step.phase_id == phase.id

    # --- step_type propagation ---

    def test_alignment_keyword_sets_alignment_step_type(self) -> None:
        step = _make_step("clarify the objective and goals")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.step_type == StepType.ALIGNMENT

    def test_research_keyword_sets_execution_step_type(self) -> None:
        step = _make_step("search for recent academic papers")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.step_type == StepType.EXECUTION

    def test_delivery_keyword_sets_delivery_step_type(self) -> None:
        step = _make_step("deliver the final output")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.step_type == StepType.DELIVERY

    def test_qa_keyword_sets_self_review_step_type(self) -> None:
        step = _make_step("proofread and quality review the document")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.step_type == StepType.SELF_REVIEW

    # --- step_ids population ---

    def test_matched_step_id_added_to_phase_step_ids(self) -> None:
        step = _make_step("research current best practices")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        research_phase = self._phase_for(plan, PhaseType.RESEARCH_FOUNDATION)
        assert step.id in research_phase.step_ids

    def test_matched_step_phase_id_is_set(self) -> None:
        step = _make_step("analyze patterns and compare options")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.phase_id is not None

    # --- multi-step scenario ---

    def test_multiple_steps_each_assigned_to_matching_phase(self) -> None:
        steps = [
            _make_step("clarify the objective"),
            _make_step("research existing solutions"),
            _make_step("analyze the tradeoffs"),
            _make_step("draft the final report"),
            _make_step("proofread and quality check"),
            _make_step("deliver the output"),
        ]
        plan = self._plan_with_all_phases(steps)
        assign_steps_to_phases(plan)
        expected = [
            PhaseType.ALIGNMENT,
            PhaseType.RESEARCH_FOUNDATION,
            PhaseType.ANALYSIS_SYNTHESIS,
            PhaseType.REPORT_GENERATION,
            PhaseType.QUALITY_ASSURANCE,
            PhaseType.DELIVERY_FEEDBACK,
        ]
        for step, expected_type in zip(steps, expected, strict=True):
            phase = self._phase_for(plan, expected_type)
            assert step.phase_id == phase.id, f"Step '{step.description}' not in {expected_type}"

    def test_all_steps_assigned_after_call(self) -> None:
        steps = [
            _make_step("understand the user goal"),
            _make_step("search for relevant sources"),
            _make_step("analyze the findings"),
            _make_step("draft the report"),
            _make_step("deliver final report"),
        ]
        plan = self._plan_with_all_phases(steps)
        assign_steps_to_phases(plan)
        for step in plan.steps:
            assert step.phase_id is not None

    # --- absent phase for matched keyword ---

    def test_keyword_match_ignores_phase_not_in_plan(self) -> None:
        """If QUALITY_ASSURANCE phase is absent, its keywords should not cause an error."""
        limited_types = [
            PhaseType.ALIGNMENT,
            PhaseType.RESEARCH_FOUNDATION,
            PhaseType.REPORT_GENERATION,
            PhaseType.DELIVERY_FEEDBACK,
        ]
        phases = build_phases(limited_types)
        step = _make_step("proofread for quality and readability")
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        # Should not raise; step is assigned to some remaining phase
        assert step.phase_id is not None


# ---------------------------------------------------------------------------
# assign_steps_to_phases — positional fallback
# ---------------------------------------------------------------------------


class TestAssignStepsToPhasesPositionalFallback:
    def _plan_with_all_phases(self, steps: list[Step]) -> Plan:
        phases = build_phases(_ALL_PHASE_TYPES)
        return _make_plan(steps=steps, phases=phases)

    def test_unmatched_step_gets_a_phase_assigned(self) -> None:
        step = _make_step("xyzzy nothing matches this at all 12345")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.phase_id is not None

    def test_single_unmatched_step_added_to_some_phase_step_ids(self) -> None:
        step = _make_step("zzz totally ambiguous task")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        all_step_ids = [sid for phase in plan.phases for sid in phase.step_ids]
        assert step.id in all_step_ids

    def test_positional_fallback_sets_step_type(self) -> None:
        step = _make_step("zzz totally ambiguous task")
        plan = self._plan_with_all_phases([step])
        assign_steps_to_phases(plan)
        assert step.step_type in list(StepType)

    def test_first_of_many_unmatched_goes_to_first_phase(self) -> None:
        """Index 0 maps to phase_index 0 (first active phase by order)."""
        steps = [_make_step(f"ambiguous task {i}") for i in range(6)]
        plan = self._plan_with_all_phases(steps)
        assign_steps_to_phases(plan)
        first_phase = min(plan.phases, key=lambda p: p.order)
        assert steps[0].phase_id == first_phase.id

    def test_last_of_many_unmatched_goes_to_last_phase(self) -> None:
        """Index N-1 maps to phase_index len-1 (last active phase by order)."""
        steps = [_make_step(f"ambiguous task {i}") for i in range(6)]
        plan = self._plan_with_all_phases(steps)
        assign_steps_to_phases(plan)
        last_phase = max(plan.phases, key=lambda p: p.order)
        assert steps[-1].phase_id == last_phase.id

    def test_single_step_single_phase_fallback(self) -> None:
        phases = build_phases([PhaseType.REPORT_GENERATION])
        step = _make_step("zzz ambiguous")
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        assert step.phase_id == phases[0].id

    def test_fallback_does_not_duplicate_in_step_ids(self) -> None:
        step = _make_step("zzz ambiguous run twice check")
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        all_ids = [sid for phase in plan.phases for sid in phase.step_ids]
        assert all_ids.count(step.id) == 1

    def test_fallback_step_type_comes_from_template(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        step = _make_step("zzz ambiguous")
        plan = _make_plan(steps=[step], phases=phases)
        assign_steps_to_phases(plan)
        # Only ALIGNMENT template available; its default_step_type is ALIGNMENT
        assert step.step_type == StepType.ALIGNMENT


# ---------------------------------------------------------------------------
# Plan helper methods related to phases (integration)
# ---------------------------------------------------------------------------


class TestPlanPhaseHelpers:
    def test_get_phase_by_type(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        plan = Plan(steps=[], phases=phases)
        p = plan.get_phase_by_type(PhaseType.ALIGNMENT)
        assert p is not None
        assert p.phase_type == PhaseType.ALIGNMENT

    def test_get_phase_by_type_missing(self) -> None:
        plan = Plan(steps=[], phases=[])
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is None

    def test_get_phase_by_id(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT])
        plan = Plan(steps=[], phases=phases)
        p = plan.get_phase_by_id(phases[0].id)
        assert p is not None

    def test_get_current_phase_skips_completed(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        phases[0].status = ExecutionStatus.COMPLETED
        phases[1].status = ExecutionStatus.RUNNING
        plan = Plan(steps=[], phases=phases)
        current = plan.get_current_phase()
        assert current is not None
        assert current.phase_type == PhaseType.DELIVERY_FEEDBACK

    def test_get_current_phase_returns_first_pending(self) -> None:
        phases = build_phases([PhaseType.ALIGNMENT, PhaseType.DELIVERY_FEEDBACK])
        plan = Plan(steps=[], phases=phases)
        current = plan.get_current_phase()
        assert current is not None
        assert current.phase_type == PhaseType.ALIGNMENT

    def test_plan_without_phases_is_compatible(self) -> None:
        plan = Plan(steps=[Step(id="1", description="test")])
        assert plan.phases == []
        assert plan.get_current_phase() is None
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is None

    def test_sync_phase_statuses_all_complete(self) -> None:
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

    def test_sync_phase_statuses_mixed_marks_running(self) -> None:
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

    def test_assign_then_get_steps_for_phase(self) -> None:
        steps = [_make_step("research the topic"), _make_step("gather more sources")]
        phases = build_phases(_ALL_PHASE_TYPES)
        plan = _make_plan(steps=steps, phases=phases)
        assign_steps_to_phases(plan)
        research_phase = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        phase_steps = plan.get_steps_for_phase(research_phase.id)
        for step in phase_steps:
            assert step.phase_id == research_phase.id
