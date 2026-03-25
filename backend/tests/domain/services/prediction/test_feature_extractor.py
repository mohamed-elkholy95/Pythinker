"""Tests for feature_extractor module.

Covers FailureFeatures dataclass and extract_features() function across all
code paths: None progress, valid ProgressMetrics, action-list edge cases,
stuck_analysis confidence extraction, and token_usage_pct pass-through.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.services.prediction.feature_extractor import (
    FailureFeatures,
    extract_features,
)

# ---------------------------------------------------------------------------
# FailureFeatures dataclass
# ---------------------------------------------------------------------------


class TestFailureFeaturesDataclass:
    """Tests for the FailureFeatures dataclass structure and defaults."""

    def test_required_fields_set_correctly(self):
        """All required fields are stored as provided."""
        ff = FailureFeatures(
            error_rate=0.25,
            error_count=3,
            stalled=True,
            recent_failure_rate=0.4,
            consecutive_failures=2,
        )

        assert ff.error_rate == 0.25
        assert ff.error_count == 3
        assert ff.stalled is True
        assert ff.recent_failure_rate == 0.4
        assert ff.consecutive_failures == 2

    def test_optional_token_usage_pct_defaults_to_none(self):
        """token_usage_pct is None when not supplied."""
        ff = FailureFeatures(
            error_rate=0.0,
            error_count=0,
            stalled=False,
            recent_failure_rate=0.0,
            consecutive_failures=0,
        )

        assert ff.token_usage_pct is None

    def test_optional_stuck_confidence_defaults_to_zero(self):
        """stuck_confidence defaults to 0.0 when not supplied."""
        ff = FailureFeatures(
            error_rate=0.0,
            error_count=0,
            stalled=False,
            recent_failure_rate=0.0,
            consecutive_failures=0,
        )

        assert ff.stuck_confidence == 0.0

    def test_optional_fields_accept_explicit_values(self):
        """token_usage_pct and stuck_confidence accept non-default values."""
        ff = FailureFeatures(
            error_rate=0.1,
            error_count=1,
            stalled=False,
            recent_failure_rate=0.2,
            consecutive_failures=0,
            token_usage_pct=0.75,
            stuck_confidence=0.9,
        )

        assert ff.token_usage_pct == 0.75
        assert ff.stuck_confidence == 0.9


# ---------------------------------------------------------------------------
# extract_features — None progress
# ---------------------------------------------------------------------------


class TestExtractFeaturesNoneProgress:
    """Behaviour when progress=None is passed to extract_features()."""

    def test_defaults_with_no_progress_and_no_actions(self):
        """All counters are zero / False when progress and actions are both absent."""
        result = extract_features(progress=None)

        assert result.error_count == 0
        assert result.error_rate == 0.0
        assert result.stalled is False
        assert result.recent_failure_rate == 0.0
        assert result.consecutive_failures == 0
        assert result.token_usage_pct is None
        assert result.stuck_confidence == 0.0

    def test_returns_failure_features_instance(self):
        """Return value is a FailureFeatures dataclass instance."""
        result = extract_features(progress=None)

        assert isinstance(result, FailureFeatures)

    def test_none_progress_uses_action_count_for_total(self):
        """Without progress, total_actions falls back to len(recent_actions)."""
        # 3 actions: 1 success, 2 failures — but error_rate is still 0.0
        # because total_actions is only used when progress is not None.
        actions = [
            {"success": True},
            {"success": False},
            {"success": False},
        ]
        result = extract_features(progress=None, recent_actions=actions)

        # error_rate stays 0.0 because the guard is `if progress and total_actions`
        assert result.error_rate == 0.0
        # recent_failure_rate IS computed from the actions list
        assert result.recent_failure_rate == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# extract_features — valid ProgressMetrics (MagicMock)
# ---------------------------------------------------------------------------


class TestExtractFeaturesWithProgress:
    """Behaviour when a ProgressMetrics object is supplied."""

    @pytest.fixture()
    def make_progress(self):
        """Factory: returns a MagicMock with ProgressMetrics-compatible attrs."""

        def _make(
            error_count: int = 0,
            successful_actions: int = 0,
            failed_actions: int = 0,
            is_stalled: bool = False,
        ) -> MagicMock:
            m = MagicMock()
            m.error_count = error_count
            m.successful_actions = successful_actions
            m.failed_actions = failed_actions
            m.is_stalled = is_stalled
            return m

        return _make

    def test_error_rate_computed_from_progress(self, make_progress):
        """error_rate = failed_actions / total_actions when progress is present."""
        progress = make_progress(successful_actions=6, failed_actions=2)
        result = extract_features(progress=progress)

        assert result.error_rate == pytest.approx(2 / 8)

    def test_error_count_taken_from_progress(self, make_progress):
        """error_count is pulled directly from progress.error_count."""
        progress = make_progress(error_count=7)
        result = extract_features(progress=progress)

        assert result.error_count == 7

    def test_stalled_flag_propagated(self, make_progress):
        """stalled mirrors progress.is_stalled."""
        progress = make_progress(is_stalled=True)
        result = extract_features(progress=progress)

        assert result.stalled is True

    def test_stalled_false_propagated(self, make_progress):
        """stalled is False when progress.is_stalled is False."""
        progress = make_progress(is_stalled=False)
        result = extract_features(progress=progress)

        assert result.stalled is False

    def test_zero_total_actions_gives_zero_error_rate(self, make_progress):
        """No division by zero when both successful_actions and failed_actions are 0."""
        progress = make_progress(successful_actions=0, failed_actions=0)
        result = extract_features(progress=progress)

        assert result.error_rate == 0.0

    def test_all_actions_failed_gives_error_rate_one(self, make_progress):
        """error_rate is 1.0 when every action failed."""
        progress = make_progress(successful_actions=0, failed_actions=5)
        result = extract_features(progress=progress)

        assert result.error_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# extract_features — consecutive_failures
# ---------------------------------------------------------------------------


class TestConsecutiveFailures:
    """Counting runs of failures at the tail of the action list."""

    def test_no_actions_gives_zero_consecutive(self):
        """Empty action list → consecutive_failures == 0."""
        result = extract_features(progress=None, recent_actions=[])

        assert result.consecutive_failures == 0

    def test_all_successes_gives_zero_consecutive(self):
        """No failures at all → consecutive_failures == 0."""
        actions = [{"success": True}, {"success": True}, {"success": True}]
        result = extract_features(progress=None, recent_actions=actions)

        assert result.consecutive_failures == 0

    def test_trailing_failures_counted_correctly(self):
        """Three trailing failures after a success → consecutive_failures == 3."""
        actions = [
            {"success": True},
            {"success": False},
            {"success": False},
            {"success": False},
        ]
        result = extract_features(progress=None, recent_actions=actions)

        assert result.consecutive_failures == 3

    def test_success_in_middle_resets_count(self):
        """A success in the middle stops the count — only trailing failures counted."""
        actions = [
            {"success": False},
            {"success": False},
            {"success": True},
            {"success": False},
        ]
        result = extract_features(progress=None, recent_actions=actions)

        assert result.consecutive_failures == 1

    def test_all_failures_counted(self):
        """When every action failed, count equals the full list length."""
        actions = [{"success": False}] * 4
        result = extract_features(progress=None, recent_actions=actions)

        assert result.consecutive_failures == 4

    def test_missing_success_key_treated_as_success(self):
        """Actions without a 'success' key default to True (stops consecutive count)."""
        # last action has no key → treated as success → breaks the streak
        actions = [
            {"success": False},
            {"success": False},
            {},  # no 'success' key — defaults to True
        ]
        result = extract_features(progress=None, recent_actions=actions)

        assert result.consecutive_failures == 0


# ---------------------------------------------------------------------------
# extract_features — recent_failure_rate
# ---------------------------------------------------------------------------


class TestRecentFailureRate:
    """recent_failure_rate is computed on the last 5 actions."""

    def test_recent_failure_rate_uses_last_five(self):
        """Only the 5 most-recent actions count towards recent_failure_rate."""
        # 10 actions: 5 old successes followed by 5 new failures
        actions = [{"success": True}] * 5 + [{"success": False}] * 5
        result = extract_features(progress=None, recent_actions=actions)

        assert result.recent_failure_rate == pytest.approx(1.0)

    def test_recent_failure_rate_empty_actions(self):
        """Empty list → rate is 0.0 (denominator is max(1, 0) == 1)."""
        result = extract_features(progress=None, recent_actions=[])

        assert result.recent_failure_rate == 0.0

    def test_recent_failure_rate_mixed_window(self):
        """2 failures in a 4-action window → rate == 0.5."""
        actions = [
            {"success": True},
            {"success": False},
            {"success": True},
            {"success": False},
        ]
        result = extract_features(progress=None, recent_actions=actions)

        assert result.recent_failure_rate == pytest.approx(0.5)

    def test_recent_failure_rate_all_successes(self):
        """All successes → recent_failure_rate == 0.0."""
        actions = [{"success": True}] * 6
        result = extract_features(progress=None, recent_actions=actions)

        assert result.recent_failure_rate == 0.0


# ---------------------------------------------------------------------------
# extract_features — stuck_analysis confidence extraction
# ---------------------------------------------------------------------------


class TestStuckAnalysis:
    """stuck_confidence is extracted from stuck_analysis.confidence."""

    def test_none_stuck_analysis_gives_zero_confidence(self):
        """stuck_analysis=None → stuck_confidence == 0.0."""
        result = extract_features(progress=None, stuck_analysis=None)

        assert result.stuck_confidence == 0.0

    def test_valid_confidence_attribute_extracted(self):
        """An object with .confidence is read and cast to float."""
        analysis = MagicMock()
        analysis.confidence = 0.72

        result = extract_features(progress=None, stuck_analysis=analysis)

        assert result.stuck_confidence == pytest.approx(0.72)

    def test_confidence_missing_defaults_to_zero(self):
        """getattr returns 0.0 when .confidence is absent."""
        analysis = object()  # plain object — no .confidence attribute

        result = extract_features(progress=None, stuck_analysis=analysis)

        assert result.stuck_confidence == 0.0

    def test_bad_confidence_value_falls_back_to_zero(self):
        """If float() conversion raises, stuck_confidence falls back to 0.0."""
        analysis = MagicMock()
        analysis.confidence = "not-a-number"

        result = extract_features(progress=None, stuck_analysis=analysis)

        assert result.stuck_confidence == 0.0

    def test_confidence_one_extracted_correctly(self):
        """Boundary value: confidence == 1.0 is preserved exactly."""
        analysis = MagicMock()
        analysis.confidence = 1.0

        result = extract_features(progress=None, stuck_analysis=analysis)

        assert result.stuck_confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# extract_features — token_usage_pct pass-through
# ---------------------------------------------------------------------------


class TestTokenUsagePct:
    """token_usage_pct is passed through unchanged."""

    def test_token_usage_pct_none_by_default(self):
        """Omitting token_usage_pct leaves it as None."""
        result = extract_features(progress=None)

        assert result.token_usage_pct is None

    def test_token_usage_pct_passed_through(self):
        """Explicit float value is returned unchanged."""
        result = extract_features(progress=None, token_usage_pct=0.88)

        assert result.token_usage_pct == pytest.approx(0.88)

    def test_token_usage_pct_zero_passed_through(self):
        """Zero is a valid value and must not be swallowed."""
        result = extract_features(progress=None, token_usage_pct=0.0)

        assert result.token_usage_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Combined / integration-style scenarios
# ---------------------------------------------------------------------------


class TestExtractFeaturesCombined:
    """Composite scenarios exercising multiple fields together."""

    def test_full_scenario_with_progress_and_actions(self):
        """All fields populated correctly in a realistic scenario."""
        progress = MagicMock()
        progress.error_count = 3
        progress.successful_actions = 7
        progress.failed_actions = 3
        progress.is_stalled = False

        analysis = MagicMock()
        analysis.confidence = 0.55

        actions = [
            {"success": True},
            {"success": True},
            {"success": False},
            {"success": False},
            {"success": False},
        ]

        result = extract_features(
            progress=progress,
            recent_actions=actions,
            stuck_analysis=analysis,
            token_usage_pct=0.60,
        )

        assert result.error_count == 3
        assert result.error_rate == pytest.approx(3 / 10)
        assert result.stalled is False
        assert result.recent_failure_rate == pytest.approx(3 / 5)
        assert result.consecutive_failures == 3
        assert result.stuck_confidence == pytest.approx(0.55)
        assert result.token_usage_pct == pytest.approx(0.60)

    def test_stalled_with_zero_error_rate(self):
        """Stalled flag can be True even with a zero error rate."""
        progress = MagicMock()
        progress.error_count = 0
        progress.successful_actions = 5
        progress.failed_actions = 0
        progress.is_stalled = True

        result = extract_features(progress=progress, recent_actions=[])

        assert result.stalled is True
        assert result.error_rate == 0.0
        assert result.recent_failure_rate == 0.0

    def test_none_recent_actions_treated_as_empty_list(self):
        """Passing recent_actions=None is equivalent to an empty list."""
        result_none = extract_features(progress=None, recent_actions=None)
        result_empty = extract_features(progress=None, recent_actions=[])

        assert result_none.consecutive_failures == result_empty.consecutive_failures
        assert result_none.recent_failure_rate == result_empty.recent_failure_rate
