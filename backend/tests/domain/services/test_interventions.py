"""Tests for failure prediction intervention recommendations."""

from __future__ import annotations

from app.domain.services.prediction.interventions import recommend_intervention


class TestInterventionsHighProbability:
    """Probability >= 0.85 branch."""

    def test_stuck_pattern_returns_replan(self) -> None:
        result = recommend_intervention(0.85, ["stuck_pattern"])
        assert result == "replan"

    def test_high_error_rate_returns_replan(self) -> None:
        result = recommend_intervention(0.85, ["high_error_rate"])
        assert result == "replan"

    def test_stuck_pattern_takes_priority_over_token_pressure(self) -> None:
        result = recommend_intervention(0.90, ["stuck_pattern", "token_pressure"])
        assert result == "replan"

    def test_token_pressure_alone_returns_compress_context(self) -> None:
        result = recommend_intervention(0.85, ["token_pressure"])
        assert result == "compress_context"

    def test_token_pressure_above_threshold_returns_compress_context(self) -> None:
        result = recommend_intervention(0.99, ["token_pressure"])
        assert result == "compress_context"

    def test_no_matching_factor_returns_escalate(self) -> None:
        result = recommend_intervention(0.85, [])
        assert result == "escalate"

    def test_unknown_factor_returns_escalate(self) -> None:
        result = recommend_intervention(0.90, ["unknown_factor"])
        assert result == "escalate"

    def test_probability_exactly_085_with_stuck_pattern(self) -> None:
        result = recommend_intervention(0.85, ["stuck_pattern"])
        assert result == "replan"

    def test_probability_exactly_085_no_factors(self) -> None:
        result = recommend_intervention(0.85, [])
        assert result == "escalate"

    def test_probability_10_stuck_pattern(self) -> None:
        result = recommend_intervention(1.0, ["stuck_pattern"])
        assert result == "replan"


class TestInterventionsMediumProbability:
    """0.7 <= probability < 0.85 branch."""

    def test_recent_failures_returns_reflect(self) -> None:
        result = recommend_intervention(0.70, ["recent_failures"])
        assert result == "reflect"

    def test_recent_failures_above_lower_bound(self) -> None:
        result = recommend_intervention(0.80, ["recent_failures"])
        assert result == "reflect"

    def test_stalled_returns_adjust_strategy(self) -> None:
        result = recommend_intervention(0.70, ["stalled"])
        assert result == "adjust_strategy"

    def test_stalled_above_lower_bound(self) -> None:
        result = recommend_intervention(0.75, ["stalled"])
        assert result == "adjust_strategy"

    def test_recent_failures_takes_priority_over_stalled(self) -> None:
        result = recommend_intervention(0.75, ["recent_failures", "stalled"])
        assert result == "reflect"

    def test_no_matching_factor_returns_monitor(self) -> None:
        result = recommend_intervention(0.70, [])
        assert result == "monitor"

    def test_unknown_factor_returns_monitor(self) -> None:
        result = recommend_intervention(0.75, ["some_other_signal"])
        assert result == "monitor"

    def test_probability_just_below_high_threshold(self) -> None:
        # 0.849 is in the medium range; stuck_pattern is only handled at >= 0.85
        # so with recent_failures (a medium-branch factor) we get reflect
        result = recommend_intervention(0.849, ["recent_failures"])
        assert result == "reflect"

    def test_probability_exactly_070_no_factors(self) -> None:
        result = recommend_intervention(0.70, [])
        assert result == "monitor"

    def test_token_pressure_without_stuck_in_medium_range_returns_monitor(self) -> None:
        result = recommend_intervention(0.75, ["token_pressure"])
        assert result == "monitor"


class TestInterventionsLowProbability:
    """Probability < 0.7 branch."""

    def test_below_threshold_returns_monitor(self) -> None:
        result = recommend_intervention(0.69, [])
        assert result == "monitor"

    def test_zero_probability_returns_monitor(self) -> None:
        result = recommend_intervention(0.0, [])
        assert result == "monitor"

    def test_stuck_pattern_with_low_probability_returns_monitor(self) -> None:
        result = recommend_intervention(0.50, ["stuck_pattern"])
        assert result == "monitor"

    def test_all_factors_with_low_probability_returns_monitor(self) -> None:
        factors = ["stuck_pattern", "high_error_rate", "token_pressure", "recent_failures", "stalled"]
        result = recommend_intervention(0.0, factors)
        assert result == "monitor"

    def test_just_below_medium_threshold_returns_monitor(self) -> None:
        result = recommend_intervention(0.699, ["recent_failures"])
        assert result == "monitor"


class TestInterventionsInputTypes:
    def test_accepts_list(self) -> None:
        result = recommend_intervention(0.90, ["stuck_pattern"])
        assert result == "replan"

    def test_accepts_set(self) -> None:
        result = recommend_intervention(0.90, {"stuck_pattern"})
        assert result == "replan"

    def test_accepts_tuple(self) -> None:
        result = recommend_intervention(0.90, ("token_pressure",))
        assert result == "compress_context"

    def test_accepts_generator(self) -> None:
        def factor_gen() -> object:
            yield "recent_failures"

        result = recommend_intervention(0.75, factor_gen())  # type: ignore[arg-type]
        assert result == "reflect"

    def test_returns_string(self) -> None:
        result = recommend_intervention(0.5, [])
        assert isinstance(result, str)
