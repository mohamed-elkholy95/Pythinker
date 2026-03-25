"""Tests for path_state — PathMetrics, PathState, ComplexityAnalysis, PathScoreWeights, TreeOfThoughtsConfig.

Covers:
  - PathStatus / BranchingDecision / TaskComplexity enums
  - PathMetrics: average_confidence, error_rate
  - PathState: start, complete, fail, abandon, select, add_result, record_error, to_dict
  - ComplexityAnalysis: should_branch
  - PathScoreWeights validation
  - TreeOfThoughtsConfig defaults
"""

from __future__ import annotations

from app.domain.models.path_state import (
    BranchingDecision,
    ComplexityAnalysis,
    PathMetrics,
    PathScoreWeights,
    PathState,
    PathStatus,
    TaskComplexity,
    TreeOfThoughtsConfig,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    """Path state enums."""

    def test_path_status_members(self) -> None:
        assert PathStatus.CREATED.value == "created"
        assert PathStatus.SELECTED.value == "selected"
        assert len(PathStatus) == 6

    def test_branching_decision_members(self) -> None:
        assert BranchingDecision.LINEAR.value == "linear"
        assert len(BranchingDecision) == 4

    def test_task_complexity_members(self) -> None:
        assert TaskComplexity.SIMPLE.value == "simple"
        assert len(TaskComplexity) == 4


# ---------------------------------------------------------------------------
# PathMetrics
# ---------------------------------------------------------------------------


class TestPathMetrics:
    """PathMetrics computed properties."""

    def test_average_confidence_empty(self) -> None:
        m = PathMetrics()
        assert m.average_confidence == 0.5

    def test_average_confidence_with_scores(self) -> None:
        m = PathMetrics(confidence_scores=[0.8, 0.6, 1.0])
        assert abs(m.average_confidence - 0.8) < 0.001

    def test_error_rate_zero(self) -> None:
        m = PathMetrics()
        assert m.error_rate == 0.0

    def test_error_rate_some(self) -> None:
        m = PathMetrics(steps_completed=8, errors_encountered=2)
        assert abs(m.error_rate - 0.2) < 0.001

    def test_error_rate_all_errors(self) -> None:
        m = PathMetrics(steps_completed=0, errors_encountered=5)
        assert m.error_rate == 1.0


# ---------------------------------------------------------------------------
# PathState
# ---------------------------------------------------------------------------


class TestPathState:
    """PathState lifecycle transitions."""

    def test_defaults(self) -> None:
        p = PathState()
        assert p.status == PathStatus.CREATED
        assert len(p.id) > 0
        assert p.score == 0.0

    def test_start(self) -> None:
        p = PathState()
        p.start()
        assert p.status == PathStatus.EXPLORING
        assert p.started_at is not None

    def test_complete(self) -> None:
        p = PathState()
        p.start()
        p.complete("The answer is 42")
        assert p.status == PathStatus.COMPLETED
        assert p.final_result == "The answer is 42"
        assert p.completed_at is not None

    def test_fail(self) -> None:
        p = PathState()
        p.start()
        p.fail("out of tokens")
        assert p.status == PathStatus.FAILED
        assert "out of tokens" in p.final_result

    def test_abandon(self) -> None:
        p = PathState()
        p.start()
        p.abandon("low score")
        assert p.status == PathStatus.ABANDONED
        assert "low score" in p.final_result

    def test_select(self) -> None:
        p = PathState()
        p.complete("winner")
        p.select()
        assert p.status == PathStatus.SELECTED

    def test_add_result(self) -> None:
        p = PathState()
        p.add_result("step1", "data", confidence=0.9)
        assert len(p.intermediate_results) == 1
        assert p.metrics.steps_completed == 1
        assert 0.9 in p.metrics.confidence_scores

    def test_record_error(self) -> None:
        p = PathState()
        p.record_error()
        assert p.metrics.errors_encountered == 1

    def test_to_dict(self) -> None:
        p = PathState(description="Test path", strategy="brute force")
        p.add_result("s1", "ok", confidence=0.8)
        d = p.to_dict()
        assert d["description"] == "Test path"
        assert d["strategy"] == "brute force"
        assert d["status"] == "created"
        assert d["metrics"]["steps_completed"] == 1
        assert abs(d["metrics"]["avg_confidence"] - 0.8) < 0.001


# ---------------------------------------------------------------------------
# ComplexityAnalysis
# ---------------------------------------------------------------------------


class TestComplexityAnalysis:
    """ComplexityAnalysis.should_branch."""

    def test_should_branch_linear(self) -> None:
        ca = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            branching_decision=BranchingDecision.LINEAR,
        )
        assert ca.should_branch() is False

    def test_should_branch_strategies(self) -> None:
        ca = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.7,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert ca.should_branch() is True

    def test_should_branch_verification(self) -> None:
        ca = ComplexityAnalysis(
            complexity=TaskComplexity.MODERATE,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_VERIFICATION,
        )
        assert ca.should_branch() is True

    def test_defaults(self) -> None:
        ca = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=1.0,
            branching_decision=BranchingDecision.LINEAR,
        )
        assert ca.suggested_strategies == []
        assert ca.reasoning == ""
        assert ca.estimated_steps == 0


# ---------------------------------------------------------------------------
# PathScoreWeights
# ---------------------------------------------------------------------------


class TestPathScoreWeights:
    """PathScoreWeights Pydantic model."""

    def test_defaults(self) -> None:
        w = PathScoreWeights()
        assert w.result_quality == 0.4
        assert w.confidence == 0.25
        assert w.efficiency == 0.2
        assert w.error_penalty == 0.15


# ---------------------------------------------------------------------------
# TreeOfThoughtsConfig
# ---------------------------------------------------------------------------


class TestTreeOfThoughtsConfig:
    """TreeOfThoughtsConfig defaults."""

    def test_defaults(self) -> None:
        cfg = TreeOfThoughtsConfig()
        assert cfg.enabled is True
        assert cfg.max_paths == 3
        assert cfg.min_paths == 2
        assert cfg.auto_abandon_threshold == 0.3
        assert cfg.min_steps_before_abandon == 2
        assert cfg.complexity_threshold == TaskComplexity.COMPLEX
