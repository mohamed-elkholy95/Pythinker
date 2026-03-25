"""Unit tests for PatternLearner domain module.

Covers TaskOutcome, TaskPattern, LearnedRecommendation, PatternLearner,
and the module-level singleton helpers.
"""

from datetime import datetime

import pytest

from app.domain.services.agents.learning.pattern_learner import (
    LearnedRecommendation,
    PatternLearner,
    TaskOutcome,
    TaskPattern,
    get_pattern_learner,
    reset_pattern_learner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome(
    *,
    task_id: str = "t1",
    task_type: str = "research",
    success: bool = True,
    duration_ms: float = 1000.0,
    tool_sequence: list[str] | None = None,
    error_types: list[str] | None = None,
    context_factors: dict | None = None,
) -> TaskOutcome:
    return TaskOutcome(
        task_id=task_id,
        task_description=f"Do some {task_type} work",
        task_type=task_type,
        success=success,
        duration_ms=duration_ms,
        tool_sequence=tool_sequence or [],
        error_types=error_types or [],
        context_factors=context_factors or {},
    )


# ---------------------------------------------------------------------------
# TaskOutcome
# ---------------------------------------------------------------------------


class TestTaskOutcome:
    def test_defaults(self):
        o = _outcome()
        assert o.tool_sequence == []
        assert o.error_types == []
        assert o.user_satisfaction is None
        assert o.context_factors == {}
        assert isinstance(o.created_at, datetime)

    def test_created_at_is_utc_aware(self):
        o = _outcome()
        assert o.created_at.tzinfo is not None

    def test_explicit_fields_stored(self):
        o = _outcome(task_id="xyz", task_type="chat", success=False, duration_ms=5000.0)
        assert o.task_id == "xyz"
        assert o.task_type == "chat"
        assert not o.success
        assert o.duration_ms == 5000.0

    def test_user_satisfaction_stored(self):
        o = TaskOutcome(
            task_id="t",
            task_description="desc",
            task_type="t",
            success=True,
            duration_ms=100.0,
            user_satisfaction=0.8,
        )
        assert o.user_satisfaction == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# TaskPattern
# ---------------------------------------------------------------------------


class TestTaskPattern:
    def _pattern(self, **kw) -> TaskPattern:
        defaults: dict = {
            "pattern_id": "p1",
            "pattern_type": "tool_sequence",
            "description": "Test pattern",
        }
        defaults.update(kw)
        return TaskPattern(**defaults)

    def test_defaults(self):
        p = self._pattern()
        assert p.confidence == pytest.approx(0.5)
        assert p.occurrence_count == 0
        assert p.success_rate == pytest.approx(0.0)
        assert p.average_duration_ms == pytest.approx(0.0)
        assert p.tool_sequence == []
        assert p.context_factors == {}

    def test_update_increments_occurrence(self):
        p = self._pattern()
        o = _outcome(success=True, duration_ms=2000.0)
        p.update_with_outcome(o)
        assert p.occurrence_count == 1

    def test_update_confidence_grows(self):
        p = self._pattern()
        initial = p.confidence
        p.update_with_outcome(_outcome(success=True))
        assert p.confidence > initial

    def test_confidence_capped_at_0_95(self):
        p = self._pattern()
        for _ in range(100):
            p.update_with_outcome(_outcome(success=True))
        assert p.confidence <= 0.95

    def test_update_success_rate_ema(self):
        """Success rate moves toward 1.0 on successful outcomes."""
        p = self._pattern()
        for _ in range(10):
            p.update_with_outcome(_outcome(success=True))
        assert p.success_rate > 0.0

    def test_update_failure_depresses_success_rate(self):
        """Failure outcomes pull success rate toward 0."""
        p = self._pattern(success_rate=1.0)
        p.update_with_outcome(_outcome(success=False))
        assert p.success_rate < 1.0

    def test_update_duration_ema(self):
        p = self._pattern()
        p.update_with_outcome(_outcome(duration_ms=4000.0))
        assert p.average_duration_ms == pytest.approx(4000.0 * 0.2)

    def test_last_seen_updated(self):
        p = self._pattern()
        before = p.last_seen
        p.update_with_outcome(_outcome())
        assert p.last_seen >= before


# ---------------------------------------------------------------------------
# LearnedRecommendation
# ---------------------------------------------------------------------------


class TestLearnedRecommendation:
    def test_fields(self):
        r = LearnedRecommendation(
            recommendation_type="tools",
            content="Use search first",
            confidence=0.8,
            source_patterns=["p1"],
            priority=2,
        )
        assert r.recommendation_type == "tools"
        assert r.content == "Use search first"
        assert r.confidence == pytest.approx(0.8)
        assert r.source_patterns == ["p1"]
        assert r.priority == 2

    def test_default_priority(self):
        r = LearnedRecommendation(
            recommendation_type="warning",
            content="Watch out",
            confidence=0.5,
        )
        assert r.priority == 1
        assert r.source_patterns == []


# ---------------------------------------------------------------------------
# PatternLearner — construction
# ---------------------------------------------------------------------------


class TestPatternLearnerInit:
    def test_starts_empty(self):
        learner = PatternLearner()
        stats = learner.get_statistics()
        assert stats["total_outcomes"] == 0
        assert stats["tool_sequence_patterns"] == 0
        assert stats["error_patterns"] == 0
        assert stats["success_factors"] == 0

    def test_constants(self):
        assert PatternLearner.MIN_OCCURRENCES == 3
        assert pytest.approx(0.6) == PatternLearner.CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# PatternLearner — record_outcome
# ---------------------------------------------------------------------------


class TestPatternLearnerRecordOutcome:
    def test_records_outcome_increments_total(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome())
        assert learner.get_statistics()["total_outcomes"] == 1

    def test_tool_sequence_creates_pattern(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(tool_sequence=["search", "browser"]))
        assert learner.get_statistics()["tool_sequence_patterns"] == 1

    def test_same_sequence_does_not_duplicate_pattern(self):
        learner = PatternLearner()
        for _ in range(3):
            learner.record_outcome(_outcome(tool_sequence=["search", "browser"]))
        assert learner.get_statistics()["tool_sequence_patterns"] == 1

    def test_different_sequences_create_separate_patterns(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(tool_sequence=["search"]))
        learner.record_outcome(_outcome(tool_sequence=["browser"]))
        assert learner.get_statistics()["tool_sequence_patterns"] == 2

    def test_error_type_creates_error_pattern(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(success=False, error_types=["TimeoutError"]))
        assert learner.get_statistics()["error_patterns"] == 1

    def test_multiple_errors_in_one_outcome(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(success=False, error_types=["TimeoutError", "NetworkError"]))
        assert learner.get_statistics()["error_patterns"] == 2

    def test_success_creates_factors(self):
        learner = PatternLearner()
        # Fast completion + tool combo trigger two factors
        learner.record_outcome(_outcome(success=True, tool_sequence=["search", "browser"], duration_ms=1000.0))
        assert learner.get_statistics()["success_factors"] >= 1

    def test_failure_does_not_create_success_factors(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(success=False, tool_sequence=["search"], duration_ms=1000.0))
        assert learner.get_statistics()["success_factors"] == 0

    def test_returns_updated_patterns(self):
        learner = PatternLearner()
        patterns = learner.record_outcome(_outcome(tool_sequence=["a", "b"]))
        assert isinstance(patterns, list)
        assert len(patterns) >= 1
        assert all(isinstance(p, TaskPattern) for p in patterns)

    def test_no_tool_sequence_no_seq_pattern(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(tool_sequence=[]))
        assert learner.get_statistics()["tool_sequence_patterns"] == 0

    def test_context_factor_bool_true_triggers_factor(self):
        learner = PatternLearner()
        learner.record_outcome(
            _outcome(
                success=True,
                tool_sequence=["search", "browser"],
                duration_ms=1000.0,
                context_factors={"has_cache": True},
            )
        )
        factors = {p.description for p in learner._success_factors.values()}
        assert any("has_cache" in f for f in factors)

    def test_context_factor_bool_false_not_included(self):
        learner = PatternLearner()
        learner.record_outcome(
            _outcome(
                success=True,
                tool_sequence=[],
                duration_ms=1000.0,
                context_factors={"has_cache": False},
            )
        )
        factors = {p.description for p in learner._success_factors.values()}
        assert not any("has_cache" in f for f in factors)


# ---------------------------------------------------------------------------
# PatternLearner — get_statistics
# ---------------------------------------------------------------------------


class TestPatternLearnerStatistics:
    def test_success_rate_all_success(self):
        learner = PatternLearner()
        for _ in range(4):
            learner.record_outcome(_outcome(success=True))
        assert learner.get_statistics()["success_rate"] == pytest.approx(1.0)

    def test_success_rate_all_failure(self):
        learner = PatternLearner()
        for _ in range(3):
            learner.record_outcome(_outcome(success=False))
        assert learner.get_statistics()["success_rate"] == pytest.approx(0.0)

    def test_success_rate_empty(self):
        learner = PatternLearner()
        assert learner.get_statistics()["success_rate"] == pytest.approx(0.0)

    def test_high_confidence_patterns_counted(self):
        learner = PatternLearner()
        # Drive a pattern's confidence above CONFIDENCE_THRESHOLD (0.6)
        for _ in range(5):
            learner.record_outcome(_outcome(tool_sequence=["search"]))
        # confidence starts at 0.5 and grows by 0.05 each update → 0.75 after 5
        stats = learner.get_statistics()
        assert stats["high_confidence_patterns"] >= 1


# ---------------------------------------------------------------------------
# PatternLearner — get_tool_sequence_for_task
# ---------------------------------------------------------------------------


class TestGetToolSequenceForTask:
    def _prime(self, learner: PatternLearner, task_type: str, n: int = 5) -> None:
        for _ in range(n):
            learner.record_outcome(
                _outcome(
                    task_type=task_type,
                    success=True,
                    tool_sequence=["search", "browser"],
                    duration_ms=2000.0,
                )
            )

    def test_returns_none_when_no_patterns(self):
        learner = PatternLearner()
        assert learner.get_tool_sequence_for_task("research") is None

    def test_returns_sequence_after_sufficient_outcomes(self):
        learner = PatternLearner()
        self._prime(learner, "research")
        seq = learner.get_tool_sequence_for_task("research")
        assert seq is not None
        assert "search" in seq

    def test_respects_min_success_rate_threshold(self):
        learner = PatternLearner()
        # Mix of failures that depress success rate below default 0.6
        for _ in range(3):
            learner.record_outcome(
                _outcome(
                    task_type="analysis",
                    success=False,
                    tool_sequence=["a", "b"],
                )
            )
        # With low success rate, None should be returned for high threshold
        seq = learner.get_tool_sequence_for_task("analysis", min_success_rate=0.9)
        assert seq is None

    def test_sequence_capped_at_5_tools(self):
        learner = PatternLearner()
        long_seq = ["a", "b", "c", "d", "e", "f", "g"]
        for _ in range(5):
            learner.record_outcome(_outcome(task_type="big", success=True, tool_sequence=long_seq, duration_ms=500.0))
        seq = learner.get_tool_sequence_for_task("big")
        assert seq is None or len(seq) <= 5


# ---------------------------------------------------------------------------
# PatternLearner — get_common_errors
# ---------------------------------------------------------------------------


class TestGetCommonErrors:
    def test_returns_empty_when_no_errors(self):
        learner = PatternLearner()
        assert learner.get_common_errors() == []

    def test_returns_errors_sorted_by_occurrence(self):
        learner = PatternLearner()
        for _ in range(3):
            learner.record_outcome(_outcome(success=False, error_types=["TimeoutError"]))
        learner.record_outcome(_outcome(success=False, error_types=["NetworkError"]))
        errors = learner.get_common_errors()
        assert errors[0][0] == "TimeoutError"
        assert errors[0][1] == 3

    def test_limit_respected(self):
        learner = PatternLearner()
        for i in range(7):
            learner.record_outcome(_outcome(success=False, error_types=[f"Err{i}"]))
        assert len(learner.get_common_errors(limit=3)) == 3

    def test_task_type_filter_excludes_non_matching(self):
        learner = PatternLearner()
        learner.record_outcome(_outcome(task_type="research", success=False, error_types=["research timeout"]))
        learner.record_outcome(_outcome(task_type="chat", success=False, error_types=["chat error"]))
        errors = learner.get_common_errors(task_type="research")
        descriptions = [e[0] for e in errors]
        assert any("research" in d for d in descriptions)
        assert not any("chat" in d for d in descriptions)


# ---------------------------------------------------------------------------
# PatternLearner — get_success_factors
# ---------------------------------------------------------------------------


class TestGetSuccessFactors:
    def test_returns_empty_when_no_factors(self):
        learner = PatternLearner()
        assert learner.get_success_factors() == []

    def test_factors_require_min_occurrences(self):
        learner = PatternLearner()
        # Only 2 outcomes — below MIN_OCCURRENCES=3
        for _ in range(2):
            learner.record_outcome(_outcome(success=True, tool_sequence=["a", "b"], duration_ms=1000.0))
        assert learner.get_success_factors() == []

    def test_factors_returned_after_threshold(self):
        learner = PatternLearner()
        for _ in range(5):
            learner.record_outcome(_outcome(success=True, tool_sequence=["a", "b"], duration_ms=1000.0))
        # success_rate rises to >0.7 after multiple successes
        factors = learner.get_success_factors(min_success_rate=0.5)
        assert len(factors) > 0

    def test_sorted_by_success_rate_descending(self):
        learner = PatternLearner()
        for _ in range(5):
            learner.record_outcome(_outcome(success=True, tool_sequence=["a", "b"], duration_ms=500.0))
        factors = learner.get_success_factors(min_success_rate=0.0)
        rates = [f.success_rate for f in factors]
        assert rates == sorted(rates, reverse=True)


# ---------------------------------------------------------------------------
# PatternLearner — get_recommendations
# ---------------------------------------------------------------------------


class TestGetRecommendations:
    def test_empty_learner_returns_no_recommendations(self):
        learner = PatternLearner()
        recs = learner.get_recommendations("do some research", "research")
        assert recs == []

    def test_warning_recommendation_for_repeated_errors(self):
        learner = PatternLearner()
        for _ in range(4):
            # Drive error pattern occurrence above MIN_OCCURRENCES and confidence above threshold
            learner.record_outcome(
                _outcome(
                    task_type="research",
                    success=False,
                    error_types=["research timeout"],
                )
            )
        recs = learner.get_recommendations("do some research work about topic", "research")
        warning_recs = [r for r in recs if r.recommendation_type == "warning"]
        assert len(warning_recs) >= 1

    def test_recommendations_sorted_by_priority(self):
        learner = PatternLearner()
        # Build enough state to get recommendations of different types
        for _ in range(4):
            learner.record_outcome(
                _outcome(
                    task_type="research",
                    success=False,
                    error_types=["research timeout"],
                )
            )
        recs = learner.get_recommendations("do some research work about topic", "research")
        priorities = [r.priority for r in recs]
        assert priorities == sorted(priorities)

    def test_recommendations_are_learned_recommendation_instances(self):
        learner = PatternLearner()
        for _ in range(4):
            learner.record_outcome(
                _outcome(
                    task_type="research",
                    success=False,
                    error_types=["research error"],
                )
            )
        recs = learner.get_recommendations("do some research work", "research")
        assert all(isinstance(r, LearnedRecommendation) for r in recs)


# ---------------------------------------------------------------------------
# PatternLearner — _get_sequence_key
# ---------------------------------------------------------------------------


class TestGetSequenceKey:
    def test_joins_with_arrow(self):
        learner = PatternLearner()
        assert learner._get_sequence_key(["a", "b", "c"]) == "a->b->c"

    def test_capped_at_5(self):
        learner = PatternLearner()
        key = learner._get_sequence_key(["a", "b", "c", "d", "e", "f"])
        assert key == "a->b->c->d->e"

    def test_single_tool(self):
        learner = PatternLearner()
        assert learner._get_sequence_key(["only"]) == "only"


# ---------------------------------------------------------------------------
# PatternLearner — _extract_success_factors
# ---------------------------------------------------------------------------


class TestExtractSuccessFactors:
    def test_fast_completion_factor(self):
        learner = PatternLearner()
        factors = learner._extract_success_factors(_outcome(duration_ms=4000.0, success=True))
        assert "Fast completion" in factors

    def test_moderate_completion_factor(self):
        learner = PatternLearner()
        factors = learner._extract_success_factors(_outcome(duration_ms=15000.0, success=True))
        assert "Moderate completion time" in factors

    def test_slow_completion_no_duration_factor(self):
        learner = PatternLearner()
        factors = learner._extract_success_factors(_outcome(duration_ms=60000.0, success=True))
        assert "Fast completion" not in factors
        assert "Moderate completion time" not in factors

    def test_tool_combo_factor_requires_2_tools(self):
        learner = PatternLearner()
        factors = learner._extract_success_factors(
            _outcome(tool_sequence=["search", "browser"], duration_ms=60000.0, success=True)
        )
        assert any("Tool combo" in f for f in factors)

    def test_single_tool_no_combo_factor(self):
        learner = PatternLearner()
        factors = learner._extract_success_factors(
            _outcome(tool_sequence=["search"], duration_ms=60000.0, success=True)
        )
        assert not any("Tool combo" in f for f in factors)


# ---------------------------------------------------------------------------
# PatternLearner — _pattern_matches_task
# ---------------------------------------------------------------------------


class TestPatternMatchesTask:
    def _make_pattern(self, description: str) -> TaskPattern:
        return TaskPattern(pattern_id="x", pattern_type="tool_sequence", description=description)

    def test_matches_by_task_type(self):
        learner = PatternLearner()
        p = self._make_pattern("Tool sequence for research")
        assert learner._pattern_matches_task(p, "irrelevant description", "research")

    def test_matches_by_keyword_overlap(self):
        learner = PatternLearner()
        p = self._make_pattern("search research data")
        assert learner._pattern_matches_task(p, "search data sources", None)

    def test_no_match_insufficient_overlap(self):
        learner = PatternLearner()
        p = self._make_pattern("zap quux plonk")
        assert not learner._pattern_matches_task(p, "do research tasks here", None)


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingletonHelpers:
    def setup_method(self):
        reset_pattern_learner()

    def teardown_method(self):
        reset_pattern_learner()

    def test_get_pattern_learner_returns_instance(self):
        learner = get_pattern_learner()
        assert isinstance(learner, PatternLearner)

    def test_get_pattern_learner_returns_same_instance(self):
        a = get_pattern_learner()
        b = get_pattern_learner()
        assert a is b

    def test_reset_creates_fresh_instance(self):
        a = get_pattern_learner()
        a.record_outcome(_outcome())
        reset_pattern_learner()
        b = get_pattern_learner()
        assert b is not a
        assert b.get_statistics()["total_outcomes"] == 0
