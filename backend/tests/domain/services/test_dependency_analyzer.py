from __future__ import annotations

from app.domain.models.plan import Plan, Step
from app.domain.services.validation.dependency_analyzer import analyze_dependencies


def _make_step(step_id: str, dependencies: list[str] | None = None) -> Step:
    return Step(id=step_id, description=f"Desc for {step_id}", dependencies=dependencies or [])


def _make_plan(steps: list[Step]) -> Plan:
    return Plan(steps=steps)


class TestAnalyzeDependenciesNoDuplicates:
    def test_empty_plan_returns_no_issues(self) -> None:
        plan = _make_plan([])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_single_step_no_deps_clean(self) -> None:
        plan = _make_plan([_make_step("s1")])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_multiple_steps_no_deps_clean(self) -> None:
        steps = [_make_step(f"s{i}") for i in range(5)]
        plan = _make_plan(steps)
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_backward_dependency_no_warning(self) -> None:
        # s2 depends on s1 (s1 comes before s2) — valid ordering
        s1 = _make_step("s1")
        s2 = _make_step("s2", dependencies=["s1"])
        plan = _make_plan([s1, s2])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_chain_of_backward_dependencies_clean(self) -> None:
        s1 = _make_step("s1")
        s2 = _make_step("s2", dependencies=["s1"])
        s3 = _make_step("s3", dependencies=["s2"])
        plan = _make_plan([s1, s2, s3])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_returns_tuple_of_two_lists(self) -> None:
        plan = _make_plan([_make_step("s1")])
        result = analyze_dependencies(plan)
        assert isinstance(result, tuple)
        assert len(result) == 2
        errors, warnings = result
        assert isinstance(errors, list)
        assert isinstance(warnings, list)


class TestAnalyzeDependenciesDuplicateIds:
    def test_two_steps_same_id_raises_error(self) -> None:
        s1a = _make_step("dup")
        s1b = _make_step("dup")
        plan = _make_plan([s1a, s1b])
        errors, warnings = analyze_dependencies(plan)
        assert len(errors) == 1
        assert "dup" in errors[0]

    def test_duplicate_error_message_mentions_id(self) -> None:
        s1 = _make_step("my-step")
        s2 = _make_step("my-step")
        plan = _make_plan([s1, s2])
        errors, _ = analyze_dependencies(plan)
        assert "my-step" in errors[0]

    def test_three_steps_one_duplicate_reports_once(self) -> None:
        # Only the second occurrence of "dup" triggers the error
        s1 = _make_step("s1")
        dup_a = _make_step("dup")
        dup_b = _make_step("dup")
        plan = _make_plan([s1, dup_a, dup_b])
        errors, _ = analyze_dependencies(plan)
        assert len(errors) == 1

    def test_three_duplicate_steps_reports_two_errors(self) -> None:
        # First occurrence is "seen", 2nd and 3rd each generate an error
        steps = [_make_step("dup") for _ in range(3)]
        plan = _make_plan(steps)
        errors, _ = analyze_dependencies(plan)
        assert len(errors) == 2

    def test_multiple_distinct_duplicates(self) -> None:
        a1 = _make_step("a")
        a2 = _make_step("a")
        b1 = _make_step("b")
        b2 = _make_step("b")
        plan = _make_plan([a1, a2, b1, b2])
        errors, _ = analyze_dependencies(plan)
        assert len(errors) == 2


class TestAnalyzeDependenciesForwardDependency:
    def test_step_depends_on_later_step_emits_warning(self) -> None:
        # s1 depends on s2, but s2 comes after s1 — forward dependency
        s1 = _make_step("s1", dependencies=["s2"])
        s2 = _make_step("s2")
        plan = _make_plan([s1, s2])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert len(warnings) == 1
        assert "s1" in warnings[0]
        assert "s2" in warnings[0]

    def test_forward_dep_warning_message_content(self) -> None:
        s1 = _make_step("alpha", dependencies=["beta"])
        s2 = _make_step("beta")
        plan = _make_plan([s1, s2])
        _, warnings = analyze_dependencies(plan)
        assert "alpha" in warnings[0]
        assert "beta" in warnings[0]

    def test_multiple_forward_deps_emit_multiple_warnings(self) -> None:
        s1 = _make_step("s1", dependencies=["s2", "s3"])
        s2 = _make_step("s2")
        s3 = _make_step("s3")
        plan = _make_plan([s1, s2, s3])
        _, warnings = analyze_dependencies(plan)
        assert len(warnings) == 2

    def test_dep_on_nonexistent_step_ignored(self) -> None:
        # Dependency on unknown ID should not produce any issue
        s1 = _make_step("s1", dependencies=["ghost"])
        plan = _make_plan([s1])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []

    def test_no_forward_deps_no_warnings(self) -> None:
        s1 = _make_step("s1")
        s2 = _make_step("s2", dependencies=["s1"])
        s3 = _make_step("s3", dependencies=["s1", "s2"])
        plan = _make_plan([s1, s2, s3])
        errors, warnings = analyze_dependencies(plan)
        assert errors == []
        assert warnings == []


class TestAnalyzeDependenciesBothIssues:
    def test_duplicate_and_forward_dep_both_reported(self) -> None:
        # Duplicate IDs produce errors; forward dep produces warning
        s1 = _make_step("s1", dependencies=["s3"])  # forward dep
        s2 = _make_step("s2")
        s2dup = _make_step("s2")  # duplicate
        s3 = _make_step("s3")
        plan = _make_plan([s1, s2, s2dup, s3])
        errors, warnings = analyze_dependencies(plan)
        assert len(errors) >= 1
        assert len(warnings) >= 1
