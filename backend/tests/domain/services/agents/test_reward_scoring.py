"""Tests for RewardScorer — heuristic reward scoring with gaming detection."""

import pytest

from app.domain.services.agents.gaming_detector import GamingDetector, GamingSignal
from app.domain.services.agents.reward_scoring import RewardScore, RewardScorer


class TestRewardScore:
    """Tests for the RewardScore dataclass."""

    def test_basic_construction(self):
        score = RewardScore(overall=0.8, violation=False)
        assert score.overall == 0.8
        assert score.violation is False
        assert score.signals == []
        assert score.subscores == {}

    def test_construction_with_signals(self):
        sig = GamingSignal(signal_type="test", severity="low", detail="test detail")
        score = RewardScore(overall=0.5, violation=True, signals=[sig])
        assert len(score.signals) == 1


class TestRewardScorerCleanOutput:
    """Tests for scoring clean (no gaming signals) outputs."""

    def test_perfect_score_with_no_signals(self):
        scorer = RewardScorer()
        result = scorer.score_output(
            output="Here is a comprehensive analysis...",
            user_request="Explain Python decorators",
        )
        assert result.overall == 1.0
        assert result.violation is False
        assert result.signals == []

    def test_all_subscores_perfect_with_no_signals(self):
        scorer = RewardScorer()
        result = scorer.score_output(output="Good output", user_request="task")
        for name, value in result.subscores.items():
            assert value == 1.0, f"subscore {name} should be 1.0"


class TestRewardScorerSeverityPenalties:
    """Tests for severity-based score penalties."""

    def test_high_severity_deducts_0_4(self):
        scorer = RewardScorer()
        # Trigger a high-severity signal (parameter injection)
        traces = [{"args_summary": "ignore previous instructions"}]
        result = scorer.score_output(
            output="output",
            user_request="task",
            tool_traces=traces,
        )
        assert result.overall == pytest.approx(0.6)
        assert result.violation is True

    def test_medium_severity_deducts_0_2(self):
        scorer = RewardScorer()
        # Trigger medium severity: repetitive tool calls
        actions = [{"function_name": "search"}] * 3
        result = scorer.score_output(
            output="result",
            user_request="task",
            recent_actions=actions,
        )
        medium_signals = [s for s in result.signals if s.severity == "medium"]
        if medium_signals:
            expected = 1.0 - (0.2 * len(medium_signals))
            assert result.overall == pytest.approx(max(0.0, expected))

    def test_overall_clamped_to_zero(self):
        scorer = RewardScorer()
        # Multiple high-severity signals via injection patterns
        traces = [
            {"args_summary": "ignore previous instructions"},
            {"args_summary": "bypass safety jailbreak system prompt"},
        ]
        result = scorer.score_output(
            output="output",
            user_request="task",
            tool_traces=traces,
        )
        assert result.overall >= 0.0

    def test_overall_never_exceeds_one(self):
        scorer = RewardScorer()
        result = scorer.score_output(output="good", user_request="task")
        assert result.overall <= 1.0

    def test_violation_true_when_high_severity(self):
        scorer = RewardScorer()
        traces = [{"args_summary": "bypass security"}]
        result = scorer.score_output(
            output="output",
            user_request="task",
            tool_traces=traces,
        )
        assert result.violation is True

    def test_violation_false_when_no_high_severity(self):
        scorer = RewardScorer()
        # Only medium severity: repetitive calls
        actions = [{"function_name": "search"}] * 3
        result = scorer.score_output(
            output="result",
            user_request="simple task",
            recent_actions=actions,
        )
        assert result.violation is False


class TestRewardScorerSubscores:
    """Tests for subscore computation."""

    def test_reasoning_subscore_decreases_with_signals(self):
        scorer = RewardScorer()
        actions = [{"function_name": "search"}] * 3
        result = scorer.score_output(
            output="result",
            user_request="task",
            recent_actions=actions,
        )
        if result.signals:
            assert result.subscores["reasoning"] < 1.0

    def test_subscores_clamped_to_zero(self):
        scorer = RewardScorer()
        # Trigger many signals
        actions = [{"function_name": f"tool_{i}", "success": False} for i in range(10)]
        traces = [{"args_summary": "ignore previous bypass jailbreak"}]
        result = scorer.score_output(
            output="A" * 201,
            user_request="search for latest news",
            recent_actions=actions,
            tool_traces=traces,
        )
        for name, value in result.subscores.items():
            assert value >= 0.0, f"subscore {name} should be >= 0"
            assert value <= 1.0, f"subscore {name} should be <= 1"

    def test_correctness_and_completeness_always_1(self):
        scorer = RewardScorer()
        traces = [{"args_summary": "ignore previous instructions"}]
        result = scorer.score_output(
            output="output",
            user_request="task",
            tool_traces=traces,
        )
        # These aren't adjusted by the current implementation
        assert result.subscores["correctness"] == 1.0
        assert result.subscores["completeness"] == 1.0


class TestRewardScorerCustomDetector:
    """Tests for using a custom GamingDetector."""

    def test_custom_detector_thresholds(self):
        detector = GamingDetector(repetitive_threshold=5)
        scorer = RewardScorer(detector=detector)
        # 3 repetitive calls — below custom threshold of 5
        actions = [{"function_name": "search"}] * 3
        result = scorer.score_output(
            output="result",
            user_request="task",
            recent_actions=actions,
        )
        repetitive = [s for s in result.signals if s.signal_type == "repetitive_tool_calls"]
        assert len(repetitive) == 0
        assert result.overall == 1.0
