"""Tests for plan domain model — ExecutionStatus, Phase, Step, Plan, validation, quality."""

import pytest

from app.domain.models.plan import (
    DimensionScore,
    ExecutionStatus,
    Phase,
    PhaseType,
    Plan,
    PlanQualityAnalyzer,
    PlanQualityMetrics,
    QualityDimension,
    RetryPolicy,
    Step,
    StepType,
    ValidationResult,
)

# ── ExecutionStatus ─────────────────────────────────────────


class TestExecutionStatus:
    def test_all_values(self) -> None:
        expected = {"pending", "running", "completed", "failed", "blocked", "skipped", "terminated"}
        assert {e.value for e in ExecutionStatus} == expected

    def test_status_marks(self) -> None:
        marks = ExecutionStatus.get_status_marks()
        assert marks["completed"] == "[✓]"
        assert marks["failed"] == "[✗]"
        assert marks["pending"] == "[ ]"
        assert marks["running"] == "[→]"
        assert marks["blocked"] == "[!]"
        assert marks["skipped"] == "[-]"
        assert marks["terminated"] == "[⊘]"

    def test_active_statuses(self) -> None:
        active = ExecutionStatus.get_active_statuses()
        assert "pending" in active
        assert "running" in active
        assert "completed" not in active

    def test_terminal_statuses(self) -> None:
        terminal = ExecutionStatus.get_terminal_statuses()
        assert "completed" in terminal
        assert "failed" in terminal
        assert "blocked" in terminal
        assert "skipped" in terminal
        assert "terminated" in terminal
        assert "pending" not in terminal

    def test_success_statuses(self) -> None:
        success = ExecutionStatus.get_success_statuses()
        assert "completed" in success
        assert "skipped" in success
        assert "failed" not in success

    def test_failure_statuses(self) -> None:
        failure = ExecutionStatus.get_failure_statuses()
        assert "failed" in failure
        assert "blocked" in failure

    def test_is_active(self) -> None:
        assert ExecutionStatus.PENDING.is_active() is True
        assert ExecutionStatus.RUNNING.is_active() is True
        assert ExecutionStatus.COMPLETED.is_active() is False

    def test_is_terminal(self) -> None:
        assert ExecutionStatus.COMPLETED.is_terminal() is True
        assert ExecutionStatus.FAILED.is_terminal() is True
        assert ExecutionStatus.PENDING.is_terminal() is False

    def test_is_success(self) -> None:
        assert ExecutionStatus.COMPLETED.is_success() is True
        assert ExecutionStatus.SKIPPED.is_success() is True
        assert ExecutionStatus.FAILED.is_success() is False

    def test_is_failure(self) -> None:
        assert ExecutionStatus.FAILED.is_failure() is True
        assert ExecutionStatus.BLOCKED.is_failure() is True
        assert ExecutionStatus.COMPLETED.is_failure() is False


# ── Phase ───────────────────────────────────────────────────


class TestPhase:
    def test_defaults(self) -> None:
        p = Phase(phase_type=PhaseType.RESEARCH_FOUNDATION, label="Research")
        assert p.status == ExecutionStatus.PENDING
        assert p.order == 0
        assert p.icon == ""
        assert p.step_ids == []
        assert p.skipped is False

    def test_is_active(self) -> None:
        p = Phase(phase_type=PhaseType.ALIGNMENT, label="Align")
        assert p.is_active() is True
        p.status = ExecutionStatus.COMPLETED
        assert p.is_active() is False

    def test_is_done_via_terminal(self) -> None:
        p = Phase(phase_type=PhaseType.ALIGNMENT, label="A", status=ExecutionStatus.COMPLETED)
        assert p.is_done() is True

    def test_is_done_via_skipped(self) -> None:
        p = Phase(phase_type=PhaseType.ALIGNMENT, label="A", skipped=True)
        assert p.is_done() is True

    def test_status_coercion_from_string(self) -> None:
        p = Phase(phase_type=PhaseType.ALIGNMENT, label="A", status="completed")
        assert p.status == ExecutionStatus.COMPLETED


# ── RetryPolicy ─────────────────────────────────────────────


class TestRetryPolicy:
    def test_defaults(self) -> None:
        rp = RetryPolicy()
        assert rp.max_retries == 0
        assert rp.backoff_seconds == 2.0
        assert rp.backoff_multiplier == 2.0
        assert rp.retry_on_timeout is True
        assert rp.retry_on_tool_error is True


# ── Step ────────────────────────────────────────────────────


class TestStep:
    def test_defaults(self) -> None:
        s = Step()
        assert s.status == ExecutionStatus.PENDING
        assert s.success is False
        assert s.dependencies == []
        assert s.step_type == StepType.EXECUTION

    def test_status_coercion(self) -> None:
        s = Step(status="completed")
        assert s.status == ExecutionStatus.COMPLETED

    def test_is_done(self) -> None:
        s = Step(status=ExecutionStatus.COMPLETED)
        assert s.is_done() is True
        s2 = Step(status=ExecutionStatus.PENDING)
        assert s2.is_done() is False

    def test_is_actionable(self) -> None:
        s = Step(status=ExecutionStatus.PENDING)
        assert s.is_actionable() is True
        s.status = ExecutionStatus.RUNNING
        assert s.is_actionable() is False

    def test_mark_blocked(self) -> None:
        s = Step(description="Search results")
        s.mark_blocked("API down", blocked_by="step-1")
        assert s.status == ExecutionStatus.BLOCKED
        assert s.notes == "API down"
        assert s.blocked_by == "step-1"
        assert s.success is False

    def test_mark_skipped(self) -> None:
        s = Step(description="Optional step")
        s.mark_skipped("Not needed")
        assert s.status == ExecutionStatus.SKIPPED
        assert s.success is True
        assert s.notes == "Not needed"

    def test_get_status_mark(self) -> None:
        s = Step(status=ExecutionStatus.COMPLETED)
        assert s.get_status_mark() == "[✓]"

    def test_display_label_structured(self) -> None:
        s = Step(
            description="fallback",
            action_verb="Search",
            target_object="Python docs",
            tool_hint="web_search",
        )
        assert s.display_label == "Search Python docs via web_search"

    def test_display_label_no_tool_hint(self) -> None:
        s = Step(action_verb="Read", target_object="file.py")
        assert s.display_label == "Read file.py"

    def test_display_label_fallback(self) -> None:
        s = Step(description="Do something")
        assert s.display_label == "Do something"


# ── Plan ────────────────────────────────────────────────────


class TestPlan:
    def _make_plan(self, n_steps: int = 3) -> Plan:
        steps = [Step(id=f"s-{i}", description=f"Step {i}") for i in range(n_steps)]
        return Plan(title="Test Plan", goal="Test goal", steps=steps)

    def test_defaults(self) -> None:
        p = Plan()
        assert p.status == ExecutionStatus.PENDING
        assert p.steps == []
        assert p.language == "en"

    def test_status_coercion(self) -> None:
        p = Plan(status="running")
        assert p.status == ExecutionStatus.RUNNING

    def test_result_coercion_string(self) -> None:
        p = Plan(result="done")
        assert p.result == {"message": "done"}

    def test_result_coercion_none(self) -> None:
        p = Plan(result=None)
        assert p.result is None

    def test_result_coercion_dict(self) -> None:
        p = Plan(result={"key": "val"})
        assert p.result == {"key": "val"}

    def test_is_done(self) -> None:
        p = Plan(status=ExecutionStatus.COMPLETED)
        assert p.is_done() is True
        p2 = Plan(status=ExecutionStatus.PENDING)
        assert p2.is_done() is False

    def test_get_next_step(self) -> None:
        plan = self._make_plan()
        plan.steps[0].status = ExecutionStatus.COMPLETED
        nxt = plan.get_next_step()
        assert nxt is not None
        assert nxt.id == "s-1"

    def test_get_next_step_none(self) -> None:
        plan = self._make_plan(2)
        for s in plan.steps:
            s.status = ExecutionStatus.COMPLETED
        assert plan.get_next_step() is None

    def test_has_blocked_steps(self) -> None:
        plan = self._make_plan()
        assert plan.has_blocked_steps() is False
        plan.steps[1].status = ExecutionStatus.BLOCKED
        assert plan.has_blocked_steps() is True

    def test_get_blocked_steps(self) -> None:
        plan = self._make_plan()
        plan.steps[2].status = ExecutionStatus.BLOCKED
        blocked = plan.get_blocked_steps()
        assert len(blocked) == 1
        assert blocked[0].id == "s-2"

    def test_get_running_step(self) -> None:
        plan = self._make_plan()
        assert plan.get_running_step() is None
        plan.steps[1].status = ExecutionStatus.RUNNING
        assert plan.get_running_step().id == "s-1"

    def test_get_progress_empty(self) -> None:
        plan = Plan()
        progress = plan.get_progress()
        assert progress["total"] == 0
        assert progress["progress_pct"] == 0.0

    def test_get_progress_mixed(self) -> None:
        plan = self._make_plan(4)
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[1].status = ExecutionStatus.SKIPPED
        plan.steps[2].status = ExecutionStatus.FAILED
        progress = plan.get_progress()
        assert progress["total"] == 4
        assert progress["completed"] == 1
        assert progress["skipped"] == 1
        assert progress["failed"] == 1
        assert progress["pending"] == 1
        assert progress["progress_pct"] == 50.0

    def test_format_progress_text(self) -> None:
        plan = self._make_plan(2)
        plan.steps[0].status = ExecutionStatus.COMPLETED
        text = plan.format_progress_text()
        assert "1/2 completed" in text
        assert "Step 0" in text

    def test_get_step_by_id(self) -> None:
        plan = self._make_plan()
        assert plan.get_step_by_id("s-0") is not None
        assert plan.get_step_by_id("nonexistent") is None

    def test_get_phase_by_type(self) -> None:
        plan = Plan(phases=[Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="Align")])
        assert plan.get_phase_by_type(PhaseType.ALIGNMENT) is not None
        assert plan.get_phase_by_type(PhaseType.DELIVERY_FEEDBACK) is None

    def test_get_phase_by_id(self) -> None:
        plan = Plan(phases=[Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="Align")])
        assert plan.get_phase_by_id("ph-1") is not None
        assert plan.get_phase_by_id("ph-999") is None

    def test_get_steps_for_phase(self) -> None:
        plan = Plan(
            steps=[
                Step(id="s-1", description="A", phase_id="ph-1"),
                Step(id="s-2", description="B", phase_id="ph-2"),
                Step(id="s-3", description="C", phase_id="ph-1"),
            ]
        )
        assert len(plan.get_steps_for_phase("ph-1")) == 2
        assert len(plan.get_steps_for_phase("ph-2")) == 1

    def test_dump_json(self) -> None:
        plan = self._make_plan(1)
        json_str = plan.dump_json()
        assert "goal" in json_str
        assert "steps" in json_str


# ── Plan: unblock_independent_steps ─────────────────────────


class TestUnblockIndependentSteps:
    def test_unblock_when_blocker_completed(self) -> None:
        s0 = Step(id="s-0", description="A", status=ExecutionStatus.COMPLETED)
        s1 = Step(id="s-1", description="B", status=ExecutionStatus.BLOCKED, blocked_by="s-0")
        plan = Plan(steps=[s0, s1])
        unblocked = plan.unblock_independent_steps()
        assert "s-1" in unblocked
        assert s1.status == ExecutionStatus.PENDING

    def test_unblock_when_blocker_skipped(self) -> None:
        s0 = Step(id="s-0", description="A", status=ExecutionStatus.SKIPPED)
        s1 = Step(id="s-1", description="B", status=ExecutionStatus.BLOCKED, blocked_by="s-0")
        plan = Plan(steps=[s0, s1])
        unblocked = plan.unblock_independent_steps()
        assert "s-1" in unblocked

    def test_unblock_when_blocker_has_partial_results(self) -> None:
        s0 = Step(id="s-0", description="A", status=ExecutionStatus.FAILED, result="partial data")
        s1 = Step(id="s-1", description="B", status=ExecutionStatus.BLOCKED, blocked_by="s-0")
        plan = Plan(steps=[s0, s1])
        unblocked = plan.unblock_independent_steps()
        assert "s-1" in unblocked

    def test_no_unblock_when_blocker_failed_no_result(self) -> None:
        s0 = Step(id="s-0", description="A", status=ExecutionStatus.FAILED, result=None)
        s1 = Step(id="s-1", description="B", status=ExecutionStatus.BLOCKED, blocked_by="s-0")
        plan = Plan(steps=[s0, s1])
        unblocked = plan.unblock_independent_steps()
        assert unblocked == []

    def test_unblock_when_blocker_missing(self) -> None:
        s1 = Step(id="s-1", description="B", status=ExecutionStatus.BLOCKED, blocked_by="s-0")
        plan = Plan(steps=[s1])
        unblocked = plan.unblock_independent_steps()
        assert "s-1" in unblocked


# ── Plan: dependency inference ──────────────────────────────


class TestDependencyInference:
    def test_infer_sequential(self) -> None:
        steps = [Step(id=f"s-{i}", description=f"Step {i}") for i in range(3)]
        plan = Plan(steps=steps)
        plan.infer_sequential_dependencies()
        assert steps[0].dependencies == []
        assert steps[1].dependencies == ["s-0"]
        assert steps[2].dependencies == ["s-1"]

    def test_infer_smart_aggregation(self) -> None:
        steps = [
            Step(id="s-0", description="First, search for data"),
            Step(id="s-1", description="Browse the website"),
            Step(id="s-2", description="Compile all findings into a report"),
        ]
        plan = Plan(steps=steps)
        plan.infer_smart_dependencies()
        assert steps[0].dependencies == []
        assert steps[2].dependencies == ["s-0", "s-1"]

    def test_infer_smart_independent_first(self) -> None:
        steps = [
            Step(id="s-0", description="Start by reading the docs"),
            Step(id="s-1", description="Based on the docs, write code"),
        ]
        plan = Plan(steps=steps)
        plan.infer_smart_dependencies()
        assert steps[0].dependencies == []
        assert steps[1].dependencies == ["s-0"]


# ── Plan: blocked cascade ──────────────────────────────────


class TestBlockedCascade:
    def test_cascade_block(self) -> None:
        steps = [
            Step(id="s-0", description="A"),
            Step(id="s-1", description="B", dependencies=["s-0"]),
            Step(id="s-2", description="C", dependencies=["s-1"]),
        ]
        plan = Plan(steps=steps)
        blocked = plan.mark_blocked_cascade("s-0", "API error")
        assert "s-1" in blocked
        assert "s-2" in blocked
        assert steps[1].status == ExecutionStatus.BLOCKED
        assert steps[2].status == ExecutionStatus.BLOCKED

    def test_no_cascade_if_no_dependents(self) -> None:
        steps = [
            Step(id="s-0", description="A"),
            Step(id="s-1", description="B"),
        ]
        plan = Plan(steps=steps)
        blocked = plan.mark_blocked_cascade("s-0", "fail")
        assert blocked == []


# ── Plan: sync_phase_statuses ──────────────────────────────


class TestSyncPhaseStatuses:
    def test_all_pending(self) -> None:
        steps = [Step(id="s-0", description="A", phase_id="ph-1")]
        phases = [Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="Align", step_ids=["s-0"])]
        plan = Plan(steps=steps, phases=phases)
        plan.sync_phase_statuses()
        assert phases[0].status == ExecutionStatus.PENDING

    def test_all_completed(self) -> None:
        steps = [Step(id="s-0", description="A", phase_id="ph-1", status=ExecutionStatus.COMPLETED)]
        phases = [Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="Align", step_ids=["s-0"])]
        plan = Plan(steps=steps, phases=phases)
        plan.sync_phase_statuses()
        assert phases[0].status == ExecutionStatus.COMPLETED

    def test_mixed_running(self) -> None:
        steps = [
            Step(id="s-0", description="A", phase_id="ph-1", status=ExecutionStatus.COMPLETED),
            Step(id="s-1", description="B", phase_id="ph-1", status=ExecutionStatus.PENDING),
        ]
        phases = [Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A", step_ids=["s-0", "s-1"])]
        plan = Plan(steps=steps, phases=phases)
        plan.sync_phase_statuses()
        assert phases[0].status == ExecutionStatus.RUNNING

    def test_skipped_phase(self) -> None:
        phases = [Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A", skipped=True)]
        plan = Plan(phases=phases)
        plan.sync_phase_statuses()
        assert phases[0].status == ExecutionStatus.SKIPPED

    def test_phase_with_step_ids_fallback(self) -> None:
        steps = [Step(id="s-0", description="A", phase_id="ph-1", status=ExecutionStatus.COMPLETED)]
        phases = [Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A")]
        plan = Plan(steps=steps, phases=phases)
        plan.sync_phase_statuses()
        assert phases[0].status == ExecutionStatus.COMPLETED


class TestGetCurrentPhase:
    def test_returns_first_active(self) -> None:
        phases = [
            Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A", order=0, status=ExecutionStatus.COMPLETED),
            Phase(id="ph-2", phase_type=PhaseType.RESEARCH_FOUNDATION, label="R", order=1),
        ]
        plan = Plan(phases=phases)
        current = plan.get_current_phase()
        assert current is not None
        assert current.id == "ph-2"

    def test_returns_none_all_done(self) -> None:
        phases = [
            Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A", status=ExecutionStatus.COMPLETED),
        ]
        plan = Plan(phases=phases)
        assert plan.get_current_phase() is None


class TestAdvancePhase:
    def test_advance_returns_next(self) -> None:
        phases = [
            Phase(id="ph-1", phase_type=PhaseType.ALIGNMENT, label="A", order=0),
            Phase(id="ph-2", phase_type=PhaseType.RESEARCH_FOUNDATION, label="R", order=1),
        ]
        plan = Plan(phases=phases)
        nxt = plan.advance_phase("ph-1")
        assert phases[0].status == ExecutionStatus.COMPLETED
        assert nxt is not None
        assert nxt.id == "ph-2"


# ── Plan: validate_plan ────────────────────────────────────


class TestValidatePlan:
    def test_valid_plan(self) -> None:
        plan = Plan(steps=[Step(id="s-0", description="Search for data")])
        result = plan.validate_plan()
        assert result.passed is True
        assert result.errors == []

    def test_empty_plan(self) -> None:
        plan = Plan()
        result = plan.validate_plan()
        assert result.passed is False
        assert any("no steps" in e for e in result.errors)

    def test_empty_description(self) -> None:
        plan = Plan(steps=[Step(id="s-0", description="")])
        result = plan.validate_plan()
        assert result.passed is False
        assert any("empty description" in e for e in result.errors)

    def test_orphan_dependency(self) -> None:
        plan = Plan(steps=[Step(id="s-0", description="A", dependencies=["nonexistent"])])
        result = plan.validate_plan()
        assert result.passed is False
        assert any("non-existent step" in e for e in result.errors)

    def test_self_dependency(self) -> None:
        plan = Plan(steps=[Step(id="s-0", description="A", dependencies=["s-0"])])
        result = plan.validate_plan()
        assert result.passed is False
        assert any("depends on itself" in e for e in result.errors)

    def test_many_steps_warning(self) -> None:
        steps = [Step(id=f"s-{i}", description=f"Step {i}") for i in range(15)]
        plan = Plan(steps=steps)
        result = plan.validate_plan()
        assert result.passed is True
        assert any("consider simplifying" in w for w in result.warnings)

    def test_circular_dependency(self) -> None:
        steps = [
            Step(id="s-0", description="A", dependencies=["s-1"]),
            Step(id="s-1", description="B", dependencies=["s-0"]),
        ]
        plan = Plan(steps=steps)
        result = plan.validate_plan()
        assert result.passed is False
        assert any("Circular" in e for e in result.errors)

    def test_duplicate_step_ids(self) -> None:
        steps = [
            Step(id="s-0", description="A"),
            Step(id="s-0", description="B"),
        ]
        plan = Plan(steps=steps)
        result = plan.validate_plan()
        assert result.passed is False
        assert any("Duplicate" in e for e in result.errors)


# ── ValidationResult ────────────────────────────────────────


class TestValidationResult:
    def test_to_dict(self) -> None:
        vr = ValidationResult(passed=True, errors=[], warnings=["Watch out"])
        d = vr.to_dict()
        assert d["passed"] is True
        assert d["warnings"] == ["Watch out"]


# ── DimensionScore ──────────────────────────────────────────


class TestDimensionScore:
    @pytest.mark.parametrize(
        "score,grade",
        [(0.95, "A"), (0.85, "B"), (0.75, "C"), (0.65, "D"), (0.5, "F")],
    )
    def test_grade(self, score: float, grade: str) -> None:
        ds = DimensionScore(dimension=QualityDimension.CLARITY, score=score)
        assert ds.grade == grade


# ── PlanQualityMetrics ──────────────────────────────────────


class TestPlanQualityMetrics:
    def test_needs_improvement(self) -> None:
        m = PlanQualityMetrics(overall_score=0.5)
        assert m.needs_improvement is True

    def test_is_high_quality(self) -> None:
        m = PlanQualityMetrics(overall_score=0.9)
        assert m.is_high_quality is True

    def test_worst_dimension(self) -> None:
        dims = {
            QualityDimension.CLARITY: DimensionScore(dimension=QualityDimension.CLARITY, score=0.9),
            QualityDimension.STRUCTURE: DimensionScore(dimension=QualityDimension.STRUCTURE, score=0.3),
        }
        m = PlanQualityMetrics(dimensions=dims)
        assert m.worst_dimension.dimension == QualityDimension.STRUCTURE

    def test_worst_dimension_empty(self) -> None:
        m = PlanQualityMetrics()
        assert m.worst_dimension is None

    def test_to_dict(self) -> None:
        dims = {
            QualityDimension.CLARITY: DimensionScore(dimension=QualityDimension.CLARITY, score=0.8),
        }
        m = PlanQualityMetrics(dimensions=dims, overall_score=0.8, overall_grade="B")
        d = m.to_dict()
        assert d["overall_grade"] == "B"
        assert "clarity" in d["dimensions"]


# ── PlanQualityAnalyzer ─────────────────────────────────────


class TestPlanQualityAnalyzer:
    def test_analyze_empty_plan(self) -> None:
        plan = Plan(steps=[])
        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)
        assert metrics.overall_score < 0.7  # No steps → low overall quality

    def test_analyze_good_plan(self) -> None:
        steps = [
            Step(id="s-0", description="Search for Python 3.12 release notes using web_search"),
            Step(id="s-1", description="Read the official changelog at python.org"),
            Step(id="s-2", description="Summarize the key new features into a report"),
        ]
        plan = Plan(title="Python 3.12 Research", goal="Research Python 3.12 new features", steps=steps)
        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan, user_request="What's new in Python 3.12?")
        assert metrics.overall_score > 0.5

    def test_analyze_vague_plan(self) -> None:
        steps = [
            Step(id="s-0", description="maybe do something with stuff"),
            Step(id="s-1", description="perhaps look at things etc"),
        ]
        plan = Plan(goal="", steps=steps)
        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)
        clarity = metrics.dimensions.get(QualityDimension.CLARITY)
        assert clarity is not None
        assert clarity.score < 0.8  # Vague language penalized

    def test_risk_factors_detected(self) -> None:
        steps = [
            Step(id="s-0", description="Try to delete production data using sudo"),
        ]
        plan = Plan(goal="Clean up", steps=steps)
        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)
        assert len(metrics.risk_factors) > 0
