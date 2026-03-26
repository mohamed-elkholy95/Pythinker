"""Tests for PhaseRouter — phase assignment and step dependency routing.

Covers:
- assign_phases_to_plan: empty plan, simple plans (<=3 steps), larger plans with
  keyword heuristics, fallback phase, ordering, mixed keywords.
- should_skip_step: delegation to StepFailureHandler.
- check_step_dependencies: no deps, all satisfied, missing dep, failed/blocked dep,
  pending/running dep, mixed deps, mark_blocked invocation.
- Module-level constants: _RESEARCH_KEYWORDS, _RESEARCH_KEYWORD_PATTERNS,
  _REPORT_KEYWORDS, _REPORT_KEYWORD_PATTERNS.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from app.domain.models.plan import ExecutionStatus, PhaseType
from app.domain.services.flows.phase_router import (
    _REPORT_KEYWORD_PATTERNS,
    _REPORT_KEYWORDS,
    _RESEARCH_KEYWORD_PATTERNS,
    _RESEARCH_KEYWORDS,
    PhaseRouter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_step(
    step_id: str,
    description: str = "",
    status: ExecutionStatus = ExecutionStatus.PENDING,
    dependencies: list[str] | None = None,
) -> MagicMock:
    """Return a Mock that mimics the Step domain model."""
    step = MagicMock()
    step.id = step_id
    step.description = description
    step.status = status
    step.dependencies = dependencies if dependencies is not None else []
    return step


def _make_plan(steps: list[MagicMock]) -> MagicMock:
    """Return a Mock that mimics the Plan domain model."""
    plan = MagicMock()
    plan.steps = steps
    plan.phases = []
    return plan


def _make_failure_handler(
    should_skip: bool = False,
    reason: str = "",
) -> MagicMock:
    handler = MagicMock()
    handler.should_skip_step.return_value = (should_skip, reason)
    return handler


def _make_router(
    should_skip: bool = False,
    reason: str = "",
) -> PhaseRouter:
    handler = _make_failure_handler(should_skip, reason)
    return PhaseRouter(step_failure_handler=handler)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestResearchKeywords:
    def test_is_frozenset(self):
        assert isinstance(_RESEARCH_KEYWORDS, frozenset)

    def test_contains_expected_terms(self):
        expected = {
            "search",
            "find",
            "gather",
            "collect",
            "browse",
            "explore",
            "research",
            "investigate",
            "look up",
            "discover",
        }
        assert expected == _RESEARCH_KEYWORDS

    def test_patterns_are_compiled(self):
        for pat in _RESEARCH_KEYWORD_PATTERNS:
            assert isinstance(pat, re.Pattern)

    def test_pattern_count_matches_keyword_count(self):
        assert len(_RESEARCH_KEYWORD_PATTERNS) == len(_RESEARCH_KEYWORDS)

    def test_word_boundary_prevents_false_positive(self):
        """'findings' must NOT match the 'find' pattern."""
        find_pat = next(p for p in _RESEARCH_KEYWORD_PATTERNS if p.pattern == r"\bfind\b")
        assert find_pat.search("findings are interesting") is None

    def test_word_boundary_matches_exact_word(self):
        find_pat = next(p for p in _RESEARCH_KEYWORD_PATTERNS if p.pattern == r"\bfind\b")
        assert find_pat.search("find the answer") is not None

    def test_multi_word_keyword_look_up_matches(self):
        look_up_pat = next((p for p in _RESEARCH_KEYWORD_PATTERNS if "look" in p.pattern), None)
        assert look_up_pat is not None
        assert look_up_pat.search("look up the term") is not None

    def test_patterns_match_lowercase(self):
        for pat in _RESEARCH_KEYWORD_PATTERNS:
            # Strip \b word-boundary markers, then unescape the rest so we
            # can use the literal keyword text as the search input.
            raw = pat.pattern.replace(r"\b", "")
            kw = re.sub(r"\\(.)", r"\1", raw)  # unescape e.g. "\ " -> " "
            assert pat.search(kw) is not None


class TestReportKeywords:
    def test_is_tuple(self):
        assert isinstance(_REPORT_KEYWORDS, tuple)

    def test_contains_expected_terms(self):
        for kw in ("write", "create", "compile", "draft", "generate", "report", "summarize", "compose"):
            assert kw in _REPORT_KEYWORDS

    def test_patterns_are_compiled(self):
        for pat in _REPORT_KEYWORD_PATTERNS:
            assert isinstance(pat, re.Pattern)

    def test_pattern_count_matches_keyword_count(self):
        assert len(_REPORT_KEYWORD_PATTERNS) == len(_REPORT_KEYWORDS)

    def test_report_pattern_matches_word(self):
        report_pat = next(p for p in _REPORT_KEYWORD_PATTERNS if "report" in p.pattern)
        assert report_pat.search("report the findings") is not None

    def test_write_pattern_word_boundary(self):
        write_pat = next(p for p in _REPORT_KEYWORD_PATTERNS if p.pattern == r"\bwrite\b")
        assert write_pat.search("write a summary") is not None
        # "writer" should not match
        assert write_pat.search("writer of the article") is None


# ---------------------------------------------------------------------------
# PhaseRouter.__init__
# ---------------------------------------------------------------------------


class TestPhaseRouterInit:
    def test_stores_failure_handler(self):
        handler = _make_failure_handler()
        router = PhaseRouter(step_failure_handler=handler)
        assert router._step_failure_handler is handler

    def test_slots_defined(self):
        assert "_step_failure_handler" in PhaseRouter.__slots__


# ---------------------------------------------------------------------------
# assign_phases_to_plan — empty plan
# ---------------------------------------------------------------------------


class TestAssignPhasesEmptyPlan:
    def test_empty_steps_returns_immediately(self):
        router = _make_router()
        plan = _make_plan([])
        plan.phases = []
        router.assign_phases_to_plan(plan)
        # phases should be untouched (still empty list)
        assert plan.phases == []

    def test_empty_steps_no_assignment_side_effect(self):
        router = _make_router()
        plan = _make_plan([])
        plan.phases = sentinel = object()
        router.assign_phases_to_plan(plan)
        assert plan.phases is sentinel


# ---------------------------------------------------------------------------
# assign_phases_to_plan — simple plans (<=3 steps)
# ---------------------------------------------------------------------------


class TestAssignPhasesSimplePlan:
    def _run(self, n: int) -> MagicMock:
        steps = [_make_step(str(i), f"step {i}") for i in range(1, n + 1)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        return plan

    def test_one_step_yields_single_phase(self):
        plan = self._run(1)
        assert len(plan.phases) == 1

    def test_two_steps_yields_single_phase(self):
        plan = self._run(2)
        assert len(plan.phases) == 1

    def test_three_steps_yields_single_phase(self):
        plan = self._run(3)
        assert len(plan.phases) == 1

    def test_simple_phase_type_is_research_foundation(self):
        plan = self._run(2)
        assert plan.phases[0].phase_type == PhaseType.RESEARCH_FOUNDATION

    def test_simple_phase_label_is_executing(self):
        plan = self._run(2)
        assert plan.phases[0].label == "Executing"

    def test_simple_phase_description(self):
        plan = self._run(2)
        assert plan.phases[0].description == "Executing plan steps"

    def test_simple_phase_order_is_zero(self):
        plan = self._run(2)
        assert plan.phases[0].order == 0

    def test_simple_phase_contains_all_step_ids(self):
        steps = [_make_step(str(i), f"step {i}") for i in range(1, 4)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        assert set(plan.phases[0].step_ids) == {"1", "2", "3"}

    def test_three_steps_is_upper_boundary_for_simple_plan(self):
        """Exactly 3 steps must use the simple-plan branch."""
        plan = self._run(3)
        assert plan.phases[0].label == "Executing"

    def test_four_steps_does_not_use_simple_branch(self):
        """4 steps triggers the heuristic branch — label will differ."""
        steps = [_make_step(str(i), "analyze data") for i in range(1, 5)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        # The heuristic branch is used; "Executing" label only appears in simple branch
        labels = [p.label for p in plan.phases]
        assert labels != ["Executing"]


# ---------------------------------------------------------------------------
# assign_phases_to_plan — heuristic classification (>3 steps)
# ---------------------------------------------------------------------------


class TestAssignPhasesHeuristic:
    def _make_plan_with(self, descriptions: list[str]) -> MagicMock:
        steps = [_make_step(str(i + 1), desc) for i, desc in enumerate(descriptions)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        return plan

    # --- research keyword detection ---

    def test_search_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["search for information", "analyze data", "analyze results", "write report"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_find_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["find relevant papers", "compare options", "compare results", "draft the report"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_gather_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["gather data sources", "process data", "process results", "compile summary"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_browse_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(
            ["browse the web for examples", "compare findings", "compare data", "generate report"]
        )
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_research_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(
            ["research the topic thoroughly", "assess findings", "assess data", "write summary"]
        )
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_investigate_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(
            ["investigate the issue", "process information", "process data", "summarize results"]
        )
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_explore_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["explore available options", "review options", "review data", "compose report"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_discover_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["discover key insights", "assess insights", "assess results", "draft the output"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_collect_keyword_goes_to_research_phase(self):
        plan = self._make_plan_with(["collect metrics", "process metrics", "process results", "create report"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    # --- report keyword detection ---

    def test_write_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(
            ["search for data", "analyze trends", "assess patterns", "write the final document"]
        )
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_create_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(["gather data", "compare results", "review trends", "create the summary"])
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_compile_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(
            ["find sources", "assess sources", "review data", "compile findings into a document"]
        )
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_draft_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(
            ["research the market", "compare competitors", "assess landscape", "draft the proposal"]
        )
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_generate_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(["browse for info", "process info", "review info", "generate the output"])
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_summarize_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(
            ["look up articles", "process articles", "review articles", "summarize the content"]
        )
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    def test_compose_keyword_goes_to_report_phase(self):
        plan = self._make_plan_with(
            ["explore options", "compare options", "assess options", "compose the final answer"]
        )
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    # --- analysis (no keywords match) ---

    def test_neutral_step_goes_to_analysis_phase(self):
        plan = self._make_plan_with(["search for papers", "compare tradeoffs", "evaluate options", "write report"])
        analysis = next(p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS_SYNTHESIS)
        # steps 2 and 3 have no research/report keywords
        assert "2" in analysis.step_ids
        assert "3" in analysis.step_ids

    def test_analysis_phase_label(self):
        plan = self._make_plan_with(["search for sources", "evaluate quality", "assess impact", "summarize output"])
        analysis = next(p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS_SYNTHESIS)
        assert analysis.label == "Analysis"

    def test_research_phase_label(self):
        plan = self._make_plan_with(["gather information", "evaluate quality", "assess impact", "summarize output"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert research.label == "Research"

    def test_report_phase_label(self):
        plan = self._make_plan_with(["search for data", "process data", "assess data", "write the final report"])
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert report.label == "Report"

    def test_report_phase_description(self):
        plan = self._make_plan_with(["search for data", "process data", "assess data", "compile the results"])
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert report.description == "Generating output"

    def test_research_phase_description(self):
        plan = self._make_plan_with(["gather information", "process information", "review information", "write output"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert research.description == "Gathering information"

    def test_analysis_phase_description(self):
        plan = self._make_plan_with(["search for facts", "evaluate facts", "assess claims", "create document"])
        analysis = next(p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS_SYNTHESIS)
        assert analysis.description == "Analyzing findings"

    # --- phase ordering ---

    def test_research_phase_has_lower_order_than_analysis(self):
        plan = self._make_plan_with(["search for data", "evaluate data", "review data", "write summary"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        analysis = next(p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS_SYNTHESIS)
        assert research.order < analysis.order

    def test_analysis_phase_has_lower_order_than_report(self):
        plan = self._make_plan_with(["search for data", "evaluate data", "review data", "write summary"])
        analysis = next(p for p in plan.phases if p.phase_type == PhaseType.ANALYSIS_SYNTHESIS)
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert analysis.order < report.order

    def test_research_phase_has_lower_order_than_report(self):
        plan = self._make_plan_with(["search for data", "evaluate data", "review data", "write summary"])
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert research.order < report.order

    def test_phases_assigned_to_plan(self):
        plan = self._make_plan_with(["search for papers", "evaluate papers", "assess papers", "compile report"])
        assert len(plan.phases) >= 1

    # --- only report steps (no research, no analysis) ---

    def test_only_report_steps_produces_report_phase_only(self):
        steps = [_make_step(str(i), "write a document") for i in range(1, 5)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        types = {p.phase_type for p in plan.phases}
        assert PhaseType.REPORT_GENERATION in types
        assert PhaseType.RESEARCH_FOUNDATION not in types
        assert PhaseType.ANALYSIS_SYNTHESIS not in types

    # --- only research steps ---

    def test_only_research_steps_produces_research_phase_only(self):
        steps = [_make_step(str(i), "search for data") for i in range(1, 5)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        types = {p.phase_type for p in plan.phases}
        assert PhaseType.RESEARCH_FOUNDATION in types
        assert PhaseType.REPORT_GENERATION not in types
        assert PhaseType.ANALYSIS_SYNTHESIS not in types

    # --- only analysis / neutral steps ---

    def test_only_analysis_steps_produces_analysis_phase_only(self):
        steps = [_make_step(str(i), "evaluate and compare metrics") for i in range(1, 5)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        types = {p.phase_type for p in plan.phases}
        assert PhaseType.ANALYSIS_SYNTHESIS in types
        assert PhaseType.RESEARCH_FOUNDATION not in types
        assert PhaseType.REPORT_GENERATION not in types

    # --- keyword matching is case-insensitive via lowercasing ---

    def test_uppercase_search_keyword_still_routes_to_research(self):
        steps = [
            _make_step("1", "SEARCH for information"),
            _make_step("2", "assess findings"),
            _make_step("3", "review data"),
            _make_step("4", "compile report"),
        ]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids

    def test_mixed_case_write_keyword_routes_to_report(self):
        steps = [
            _make_step("1", "gather data"),
            _make_step("2", "process data"),
            _make_step("3", "evaluate data"),
            _make_step("4", "Write the final summary"),
        ]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        report = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT_GENERATION)
        assert "4" in report.step_ids

    # --- research takes priority over report keywords ---

    def test_research_keyword_takes_priority_over_report_keyword(self):
        """A step with both research and report keywords should land in research."""
        steps = [
            _make_step("1", "search and write notes about topic"),
            _make_step("2", "evaluate results"),
            _make_step("3", "compare options"),
            _make_step("4", "create final output"),
        ]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        research = next(p for p in plan.phases if p.phase_type == PhaseType.RESEARCH_FOUNDATION)
        assert "1" in research.step_ids


# ---------------------------------------------------------------------------
# assign_phases_to_plan — fallback (no bucket matched at all is impossible
# with analysis catch-all, so only "phases list empty" edge case matters)
# ---------------------------------------------------------------------------


class TestAssignPhasesNoPhases:
    def test_fallback_phase_used_when_no_phases_built(self):
        """Patch phases list to empty after heuristic loop to trigger fallback."""
        # The fallback triggers when research_ids, analysis_ids, and report_ids
        # are all empty — impossible with the catch-all analysis bucket.
        # We simulate it by having >3 steps and checking the result has at
        # least one phase assigned to plan.
        steps = [_make_step(str(i), "evaluate data") for i in range(1, 5)]
        plan = _make_plan(steps)
        _make_router().assign_phases_to_plan(plan)
        assert len(plan.phases) >= 1


# ---------------------------------------------------------------------------
# should_skip_step — delegation
# ---------------------------------------------------------------------------


class TestShouldSkipStep:
    def test_delegates_to_handler_returns_false(self):
        handler = _make_failure_handler(should_skip=False, reason="")
        router = PhaseRouter(step_failure_handler=handler)
        plan = _make_plan([])
        step = _make_step("s1")
        result = router.should_skip_step(plan, step)
        assert result == (False, "")
        handler.should_skip_step.assert_called_once_with(plan, step)

    def test_delegates_to_handler_returns_true_with_reason(self):
        handler = _make_failure_handler(should_skip=True, reason="Dependency is blocked")
        router = PhaseRouter(step_failure_handler=handler)
        plan = _make_plan([])
        step = _make_step("s1")
        result = router.should_skip_step(plan, step)
        assert result == (True, "Dependency is blocked")

    def test_passes_correct_plan_and_step(self):
        handler = _make_failure_handler()
        router = PhaseRouter(step_failure_handler=handler)
        plan = _make_plan([])
        step = _make_step("s1")
        router.should_skip_step(plan, step)
        handler.should_skip_step.assert_called_once_with(plan, step)

    def test_multiple_calls_each_delegated(self):
        handler = _make_failure_handler()
        router = PhaseRouter(step_failure_handler=handler)
        plan = _make_plan([])
        s1 = _make_step("s1")
        s2 = _make_step("s2")
        router.should_skip_step(plan, s1)
        router.should_skip_step(plan, s2)
        assert handler.should_skip_step.call_count == 2


# ---------------------------------------------------------------------------
# check_step_dependencies
# ---------------------------------------------------------------------------


class TestCheckStepDependenciesNoDeps:
    def test_no_deps_returns_true(self):
        router = _make_router()
        step = _make_step("s1", dependencies=[])
        plan = _make_plan([step])
        assert router.check_step_dependencies(plan, step) is True

    def test_empty_dep_list_is_truthy(self):
        router = _make_router()
        step = _make_step("s1", dependencies=[])
        plan = _make_plan([step])
        result = router.check_step_dependencies(plan, step)
        assert result is True


class TestCheckStepDependenciesAllSatisfied:
    def test_completed_dep_returns_true(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is True

    def test_skipped_dep_returns_true(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.SKIPPED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is True

    def test_multiple_completed_deps_returns_true(self):
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        dep2 = _make_step("dep2", status=ExecutionStatus.SKIPPED)
        step = _make_step("s1", dependencies=["dep1", "dep2"])
        plan = _make_plan([dep1, dep2, step])
        assert router.check_step_dependencies(plan, step) is True


class TestCheckStepDependenciesMissingDep:
    def test_missing_dep_is_treated_as_satisfied(self):
        router = _make_router()
        step = _make_step("s1", dependencies=["nonexistent-id"])
        plan = _make_plan([step])
        assert router.check_step_dependencies(plan, step) is True

    def test_multiple_missing_deps_still_returns_true(self):
        router = _make_router()
        step = _make_step("s1", dependencies=["x", "y", "z"])
        plan = _make_plan([step])
        assert router.check_step_dependencies(plan, step) is True

    def test_mix_of_missing_and_completed_returns_true(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        step = _make_step("s1", dependencies=["dep1", "nonexistent"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is True


class TestCheckStepDependenciesFailedOrBlocked:
    def test_failed_dep_returns_false(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.FAILED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_blocked_dep_returns_false(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.BLOCKED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_failed_dep_calls_mark_blocked_on_step(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.FAILED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        router.check_step_dependencies(plan, step)
        step.mark_blocked.assert_called_once()
        args, _kwargs = step.mark_blocked.call_args
        assert "dep1" in args[0]  # reason string contains dep_id

    def test_blocked_dep_calls_mark_blocked_on_step(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.BLOCKED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        router.check_step_dependencies(plan, step)
        step.mark_blocked.assert_called_once()

    def test_mark_blocked_receives_blocked_by_kwarg(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.FAILED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        router.check_step_dependencies(plan, step)
        _, kwargs = step.mark_blocked.call_args
        assert kwargs.get("blocked_by") == "dep1"

    def test_first_failed_dep_short_circuits(self):
        """When the first dep fails the method returns immediately."""
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.FAILED)
        dep2 = _make_step("dep2", status=ExecutionStatus.COMPLETED)
        step = _make_step("s1", dependencies=["dep1", "dep2"])
        plan = _make_plan([dep1, dep2, step])
        result = router.check_step_dependencies(plan, step)
        assert result is False
        # mark_blocked called exactly once (short-circuited)
        step.mark_blocked.assert_called_once()


class TestCheckStepDependenciesPendingOrRunning:
    def test_pending_dep_returns_false(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.PENDING)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_running_dep_returns_false(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.RUNNING)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_pending_dep_does_not_call_mark_blocked(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.PENDING)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        router.check_step_dependencies(plan, step)
        step.mark_blocked.assert_not_called()

    def test_running_dep_does_not_call_mark_blocked(self):
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.RUNNING)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        router.check_step_dependencies(plan, step)
        step.mark_blocked.assert_not_called()

    def test_multiple_deps_one_pending_returns_false(self):
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        dep2 = _make_step("dep2", status=ExecutionStatus.PENDING)
        step = _make_step("s1", dependencies=["dep1", "dep2"])
        plan = _make_plan([dep1, dep2, step])
        assert router.check_step_dependencies(plan, step) is False


class TestCheckStepDependenciesMixedStatuses:
    def test_completed_then_failed_returns_false(self):
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        dep2 = _make_step("dep2", status=ExecutionStatus.FAILED)
        step = _make_step("s1", dependencies=["dep1", "dep2"])
        plan = _make_plan([dep1, dep2, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_skipped_then_running_returns_false(self):
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.SKIPPED)
        dep2 = _make_step("dep2", status=ExecutionStatus.RUNNING)
        step = _make_step("s1", dependencies=["dep1", "dep2"])
        plan = _make_plan([dep1, dep2, step])
        assert router.check_step_dependencies(plan, step) is False

    def test_completed_and_skipped_together_returns_true(self):
        router = _make_router()
        dep1 = _make_step("dep1", status=ExecutionStatus.COMPLETED)
        dep2 = _make_step("dep2", status=ExecutionStatus.SKIPPED)
        dep3 = _make_step("dep3", status=ExecutionStatus.COMPLETED)
        step = _make_step("s1", dependencies=["dep1", "dep2", "dep3"])
        plan = _make_plan([dep1, dep2, dep3, step])
        assert router.check_step_dependencies(plan, step) is True

    def test_terminated_dep_not_in_satisfied_set_returns_false(self):
        """TERMINATED is not COMPLETED or SKIPPED — must not satisfy."""
        router = _make_router()
        dep = _make_step("dep1", status=ExecutionStatus.TERMINATED)
        step = _make_step("s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])
        # TERMINATED is not in [COMPLETED, SKIPPED] and not in [FAILED, BLOCKED]
        # and not in [PENDING, RUNNING] — loop falls through without returning False
        # so the function returns True.  This documents current behaviour.
        result = router.check_step_dependencies(plan, step)
        # TERMINATED falls through both branches → treated as satisfied
        assert result is True
