"""Tests for failure prediction intervention recommendations."""

from __future__ import annotations

from app.domain.services.prediction.interventions import recommend_intervention


class TestRecommendIntervention:
    def test_high_prob_stuck_pattern_returns_replan(self) -> None:
        assert recommend_intervention(0.90, ["stuck_pattern"]) == "replan"

    def test_high_prob_high_error_rate_returns_replan(self) -> None:
        assert recommend_intervention(0.85, ["high_error_rate"]) == "replan"

    def test_high_prob_token_pressure_returns_compress(self) -> None:
        assert recommend_intervention(0.95, ["token_pressure"]) == "compress_context"

    def test_high_prob_default_returns_escalate(self) -> None:
        assert recommend_intervention(0.90, ["unknown_factor"]) == "escalate"

    def test_high_prob_no_factors_returns_escalate(self) -> None:
        assert recommend_intervention(0.85, []) == "escalate"

    def test_medium_prob_recent_failures_returns_reflect(self) -> None:
        assert recommend_intervention(0.75, ["recent_failures"]) == "reflect"

    def test_medium_prob_stalled_returns_adjust(self) -> None:
        assert recommend_intervention(0.70, ["stalled"]) == "adjust_strategy"

    def test_medium_prob_default_returns_monitor(self) -> None:
        assert recommend_intervention(0.72, ["other"]) == "monitor"

    def test_low_prob_returns_monitor(self) -> None:
        assert recommend_intervention(0.50, ["stuck_pattern"]) == "monitor"

    def test_zero_prob_returns_monitor(self) -> None:
        assert recommend_intervention(0.0, []) == "monitor"

    def test_boundary_085_is_high(self) -> None:
        assert recommend_intervention(0.85, []) == "escalate"

    def test_boundary_070_is_medium(self) -> None:
        assert recommend_intervention(0.70, []) == "monitor"

    def test_boundary_below_070_is_low(self) -> None:
        assert recommend_intervention(0.69, ["stuck_pattern"]) == "monitor"

    def test_combined_high_factors_stuck_wins(self) -> None:
        result = recommend_intervention(0.90, ["stuck_pattern", "token_pressure"])
        assert result == "replan"
