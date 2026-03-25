"""Tests for FailureTracker — adaptive circuit breaker failure tracking."""

from datetime import UTC, datetime, timedelta
from app.core.failure_tracker import FailureEvent, FailureStats, FailureTracker


# ── FailureEvent ────────────────────────────────────────────────────


class TestFailureEvent:
    def test_basic_construction(self):
        event = FailureEvent(
            timestamp=datetime.now(UTC),
            error_type="timeout",
            detail="Request timed out after 30s",
        )
        assert event.error_type == "timeout"
        assert event.detail == "Request timed out after 30s"

    def test_detail_defaults_none(self):
        event = FailureEvent(timestamp=datetime.now(UTC), error_type="error")
        assert event.detail is None


# ── FailureStats ────────────────────────────────────────────────────


class TestFailureStats:
    def test_basic_construction(self):
        stats = FailureStats(total=10, recent=3, failure_rate=0.3)
        assert stats.total == 10
        assert stats.recent == 3
        assert stats.failure_rate == 0.3
        assert stats.error_types == {}

    def test_with_error_types(self):
        stats = FailureStats(
            total=5,
            recent=2,
            failure_rate=0.4,
            error_types={"timeout": 2, "connection": 3},
        )
        assert stats.error_types["timeout"] == 2


# ── record_failure ──────────────────────────────────────────────────


class TestRecordFailure:
    def test_records_single_failure(self):
        tracker = FailureTracker()
        tracker.record_failure("api_call", "timeout", "Request timed out")
        stats = tracker.get_stats("api_call")
        assert stats.total == 1
        assert stats.recent == 1

    def test_records_multiple_failures(self):
        tracker = FailureTracker()
        tracker.record_failure("api_call", "timeout")
        tracker.record_failure("api_call", "connection")
        tracker.record_failure("api_call", "timeout")
        stats = tracker.get_stats("api_call")
        assert stats.total == 3

    def test_separate_names_tracked_independently(self):
        tracker = FailureTracker()
        tracker.record_failure("api_a", "timeout")
        tracker.record_failure("api_b", "connection")
        assert tracker.get_stats("api_a").total == 1
        assert tracker.get_stats("api_b").total == 1

    def test_history_limit_enforced(self):
        tracker = FailureTracker(history_limit=5)
        for i in range(10):
            tracker.record_failure("op", f"error_{i}")
        stats = tracker.get_stats("op")
        assert stats.total == 5  # trimmed to last 5


# ── record_success ──────────────────────────────────────────────────


class TestRecordSuccess:
    def test_records_success(self):
        tracker = FailureTracker()
        tracker.record_success("api_call")
        stats = tracker.get_stats("api_call")
        assert stats.failure_rate == 0.0

    def test_success_history_limit(self):
        tracker = FailureTracker(history_limit=3)
        for _ in range(5):
            tracker.record_success("op")
        # Internal success list trimmed to 3
        stats = tracker.get_stats("op")
        assert stats.failure_rate == 0.0


# ── get_stats ───────────────────────────────────────────────────────


class TestGetStats:
    def test_empty_stats(self):
        tracker = FailureTracker()
        stats = tracker.get_stats("nonexistent")
        assert stats.total == 0
        assert stats.recent == 0
        assert stats.failure_rate == 0.0
        assert stats.error_types == {}

    def test_failure_rate_calculation(self):
        tracker = FailureTracker()
        tracker.record_failure("op", "timeout")
        tracker.record_success("op")
        tracker.record_success("op")
        stats = tracker.get_stats("op")
        # 1 failure + 2 successes = 1/3 ≈ 0.333
        assert 0.3 < stats.failure_rate < 0.4

    def test_failure_rate_all_failures(self):
        tracker = FailureTracker()
        tracker.record_failure("op", "timeout")
        tracker.record_failure("op", "error")
        stats = tracker.get_stats("op")
        assert stats.failure_rate == 1.0

    def test_error_types_counted(self):
        tracker = FailureTracker()
        tracker.record_failure("op", "timeout")
        tracker.record_failure("op", "timeout")
        tracker.record_failure("op", "connection")
        stats = tracker.get_stats("op")
        assert stats.error_types["timeout"] == 2
        assert stats.error_types["connection"] == 1

    def test_old_events_not_in_recent(self):
        tracker = FailureTracker(window_seconds=60)
        # Record a failure with an old timestamp
        old_event = FailureEvent(
            timestamp=datetime.now(UTC) - timedelta(seconds=120),
            error_type="timeout",
        )
        tracker._events["op"] = [old_event]
        tracker.record_failure("op", "new_error")
        stats = tracker.get_stats("op")
        # Only the new error should be recent
        assert stats.total == 2  # both in history
        assert stats.recent == 1  # only new one in window


# ── get_recent_errors ───────────────────────────────────────────────


class TestGetRecentErrors:
    def test_returns_last_n_errors(self):
        tracker = FailureTracker()
        for i in range(10):
            tracker.record_failure("op", f"error_{i}")
        recent = tracker.get_recent_errors("op", limit=3)
        assert len(recent) == 3
        assert recent[-1].error_type == "error_9"

    def test_returns_all_if_fewer_than_limit(self):
        tracker = FailureTracker()
        tracker.record_failure("op", "error_0")
        recent = tracker.get_recent_errors("op", limit=5)
        assert len(recent) == 1

    def test_returns_empty_for_unknown_name(self):
        tracker = FailureTracker()
        recent = tracker.get_recent_errors("nonexistent")
        assert recent == []


# ── reset ───────────────────────────────────────────────────────────


class TestReset:
    def test_clears_failures_and_successes(self):
        tracker = FailureTracker()
        tracker.record_failure("op", "timeout")
        tracker.record_success("op")
        tracker.reset("op")
        stats = tracker.get_stats("op")
        assert stats.total == 0
        assert stats.recent == 0
        assert stats.failure_rate == 0.0

    def test_reset_only_affects_target_name(self):
        tracker = FailureTracker()
        tracker.record_failure("op_a", "timeout")
        tracker.record_failure("op_b", "error")
        tracker.reset("op_a")
        assert tracker.get_stats("op_a").total == 0
        assert tracker.get_stats("op_b").total == 1

    def test_reset_idempotent_on_nonexistent(self):
        tracker = FailureTracker()
        tracker.reset("nonexistent")  # should not raise
