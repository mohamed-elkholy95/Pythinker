"""Tests for ToolExecutionProfiler, ToolExecutionMetrics, and related utilities."""

import pytest

from app.domain.services.tools.tool_profiler import (
    ExecutionRecord,
    ToolExecutionMetrics,
    ToolExecutionProfiler,
    get_tool_profiler,
    reset_tool_profiler,
)

# ---------------------------------------------------------------------------
# ToolExecutionMetrics
# ---------------------------------------------------------------------------


class TestToolExecutionMetricsZeroDivisionSafety:
    def test_avg_duration_ms_no_calls_returns_zero(self) -> None:
        m = ToolExecutionMetrics(tool_name="search")
        assert m.avg_duration_ms == 0.0

    def test_success_rate_no_calls_returns_zero(self) -> None:
        m = ToolExecutionMetrics(tool_name="search")
        assert m.success_rate == 0.0

    def test_failure_rate_no_calls_returns_zero(self) -> None:
        m = ToolExecutionMetrics(tool_name="search")
        assert m.failure_rate == 0.0

    def test_min_duration_ms_no_calls_is_inf(self) -> None:
        """min_duration_ms starts at +inf when there are no calls."""
        m = ToolExecutionMetrics(tool_name="search")
        assert m.min_duration_ms == float("inf")

    def test_to_dict_min_duration_no_calls_is_none(self) -> None:
        """to_dict must expose None for min_duration when no calls recorded."""
        m = ToolExecutionMetrics(tool_name="search")
        result = m.to_dict()
        assert result["min_duration_ms"] is None


class TestToolExecutionMetricsRecordSuccess:
    def test_success_increments_call_and_success_count(self) -> None:
        m = ToolExecutionMetrics(tool_name="browser")
        m.record_execution(100.0, success=True)
        assert m.call_count == 1
        assert m.success_count == 1
        assert m.failure_count == 0

    def test_success_resets_consecutive_failures(self) -> None:
        m = ToolExecutionMetrics(tool_name="browser")
        m.record_execution(50.0, success=False, error="err")
        m.record_execution(50.0, success=False, error="err")
        assert m.consecutive_failures == 2
        m.record_execution(50.0, success=True)
        assert m.consecutive_failures == 0

    def test_success_does_not_set_last_error(self) -> None:
        m = ToolExecutionMetrics(tool_name="browser")
        m.record_execution(10.0, success=True)
        assert m.last_error is None
        assert m.last_error_time is None

    def test_last_used_is_set_on_success(self) -> None:
        m = ToolExecutionMetrics(tool_name="browser")
        assert m.last_used is None
        m.record_execution(10.0, success=True)
        assert m.last_used is not None


class TestToolExecutionMetricsRecordFailure:
    def test_failure_increments_failure_count(self) -> None:
        m = ToolExecutionMetrics(tool_name="terminal")
        m.record_execution(200.0, success=False, error="timeout")
        assert m.call_count == 1
        assert m.failure_count == 1
        assert m.success_count == 0

    def test_consecutive_failures_accumulate(self) -> None:
        m = ToolExecutionMetrics(tool_name="terminal")
        for i in range(4):
            m.record_execution(10.0 * (i + 1), success=False, error="err")
        assert m.consecutive_failures == 4

    def test_last_error_message_stored(self) -> None:
        m = ToolExecutionMetrics(tool_name="terminal")
        m.record_execution(30.0, success=False, error="connection refused")
        assert m.last_error == "connection refused"
        assert m.last_error_time is not None


class TestToolExecutionMetricsCalculations:
    def test_avg_duration_single_call(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        m.record_execution(300.0, success=True)
        assert m.avg_duration_ms == pytest.approx(300.0)

    def test_avg_duration_multiple_calls(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        m.record_execution(100.0, success=True)
        m.record_execution(200.0, success=True)
        m.record_execution(300.0, success=True)
        assert m.avg_duration_ms == pytest.approx(200.0)

    def test_success_rate_all_success(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        for _ in range(5):
            m.record_execution(10.0, success=True)
        assert m.success_rate == pytest.approx(100.0)

    def test_success_rate_mixed(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        m.record_execution(10.0, success=True)
        m.record_execution(10.0, success=False, error="x")
        m.record_execution(10.0, success=True)
        m.record_execution(10.0, success=False, error="x")
        assert m.success_rate == pytest.approx(50.0)

    def test_failure_rate_complements_success_rate(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        m.record_execution(10.0, success=True)
        m.record_execution(10.0, success=False, error="x")
        assert m.success_rate + m.failure_rate == pytest.approx(100.0)

    def test_min_max_duration_tracked(self) -> None:
        m = ToolExecutionMetrics(tool_name="file")
        m.record_execution(500.0, success=True)
        m.record_execution(50.0, success=True)
        m.record_execution(250.0, success=True)
        assert m.min_duration_ms == pytest.approx(50.0)
        assert m.max_duration_ms == pytest.approx(500.0)


class TestToolExecutionMetricsToDict:
    def test_to_dict_keys(self) -> None:
        m = ToolExecutionMetrics(tool_name="shell")
        m.record_execution(120.0, success=True)
        d = m.to_dict()
        expected_keys = {
            "tool_name",
            "call_count",
            "success_count",
            "failure_count",
            "success_rate",
            "failure_rate",
            "avg_duration_ms",
            "min_duration_ms",
            "max_duration_ms",
            "last_used",
            "last_error",
            "consecutive_failures",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values_rounded(self) -> None:
        m = ToolExecutionMetrics(tool_name="shell")
        m.record_execution(100.0 / 3.0, success=True)
        d = m.to_dict()
        # avg and rates must be rounded to 2 decimal places
        assert d["avg_duration_ms"] == round(m.avg_duration_ms, 2)
        assert d["success_rate"] == round(m.success_rate, 2)
        assert d["failure_rate"] == round(m.failure_rate, 2)

    def test_to_dict_last_used_iso_format(self) -> None:
        m = ToolExecutionMetrics(tool_name="shell")
        m.record_execution(10.0, success=True)
        d = m.to_dict()
        assert isinstance(d["last_used"], str)
        # ISO 8601 contains a 'T' separator
        assert "T" in d["last_used"]

    def test_to_dict_last_used_none_when_no_calls(self) -> None:
        m = ToolExecutionMetrics(tool_name="shell")
        d = m.to_dict()
        assert d["last_used"] is None

    def test_to_dict_tool_name_preserved(self) -> None:
        m = ToolExecutionMetrics(tool_name="my_custom_tool")
        d = m.to_dict()
        assert d["tool_name"] == "my_custom_tool"


# ---------------------------------------------------------------------------
# ToolExecutionProfiler
# ---------------------------------------------------------------------------


class TestToolExecutionProfilerRecordExecution:
    def test_auto_creates_metrics_on_first_record(self) -> None:
        profiler = ToolExecutionProfiler()
        assert profiler.get_metrics("browser") is None
        profiler.record_execution("browser", duration_ms=100.0, success=True)
        assert profiler.get_metrics("browser") is not None

    def test_successive_records_accumulate(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("search", duration_ms=50.0, success=True)
        profiler.record_execution("search", duration_ms=150.0, success=True)
        m = profiler.get_metrics("search")
        assert m is not None
        assert m.call_count == 2
        assert m.avg_duration_ms == pytest.approx(100.0)

    def test_failure_record_stores_error(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("file", duration_ms=20.0, success=False, error="disk full")
        m = profiler.get_metrics("file")
        assert m is not None
        assert m.last_error == "disk full"

    def test_record_adds_to_history(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("terminal", duration_ms=80.0, success=True)
        history = profiler.get_recent_history()
        assert len(history) == 1
        assert history[0].tool_name == "terminal"

    def test_separate_tools_tracked_independently(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.record_execution("toolB", duration_ms=20.0, success=False, error="e")
        assert profiler.get_metrics("toolA") is not None
        assert profiler.get_metrics("toolB") is not None
        assert profiler.get_metrics("toolA").call_count == 1  # type: ignore[union-attr]
        assert profiler.get_metrics("toolB").failure_count == 1  # type: ignore[union-attr]


class TestToolExecutionProfilerSlowTools:
    def test_slow_tool_detected_above_threshold(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=100.0)
        profiler.record_execution("slow_search", duration_ms=500.0, success=True)
        slow = profiler.get_slow_tools()
        assert len(slow) == 1
        assert slow[0].tool_name == "slow_search"

    def test_fast_tool_not_in_slow_list(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=100.0)
        profiler.record_execution("fast_tool", duration_ms=10.0, success=True)
        assert profiler.get_slow_tools() == []

    def test_slow_tools_sorted_by_avg_duration_descending(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=100.0)
        profiler.record_execution("toolA", duration_ms=300.0, success=True)
        profiler.record_execution("toolB", duration_ms=200.0, success=True)
        profiler.record_execution("toolC", duration_ms=400.0, success=True)
        slow = profiler.get_slow_tools()
        names = [m.tool_name for m in slow]
        assert names == ["toolC", "toolA", "toolB"]

    def test_tool_with_zero_calls_excluded_from_slow(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=0.0)
        # Manually create metrics entry without any calls
        profiler._metrics["ghost"] = ToolExecutionMetrics(tool_name="ghost")  # type: ignore[attr-defined]
        assert profiler.get_slow_tools() == []


class TestToolExecutionProfilerUnreliableTools:
    def test_unreliable_tool_detected(self) -> None:
        # Default unreliable_threshold = 0.2 (20%), so >20% failure = unreliable
        profiler = ToolExecutionProfiler(unreliable_threshold=0.2)
        profiler.record_execution("flaky", duration_ms=10.0, success=True)
        profiler.record_execution("flaky", duration_ms=10.0, success=False, error="e")
        # 50% failure rate — exceeds 20%
        unreliable = profiler.get_unreliable_tools()
        assert any(m.tool_name == "flaky" for m in unreliable)

    def test_reliable_tool_not_in_unreliable_list(self) -> None:
        profiler = ToolExecutionProfiler(unreliable_threshold=0.2)
        for _ in range(10):
            profiler.record_execution("stable", duration_ms=10.0, success=True)
        assert profiler.get_unreliable_tools() == []

    def test_unreliable_tools_sorted_by_failure_rate_descending(self) -> None:
        profiler = ToolExecutionProfiler(unreliable_threshold=0.1)
        for _ in range(3):
            profiler.record_execution("toolA", duration_ms=10.0, success=False, error="e")
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        for _ in range(2):
            profiler.record_execution("toolB", duration_ms=10.0, success=False, error="e")
        for _ in range(2):
            profiler.record_execution("toolB", duration_ms=10.0, success=True)
        result = profiler.get_unreliable_tools()
        assert result[0].tool_name == "toolA"
        assert result[1].tool_name == "toolB"


class TestToolExecutionProfilerConsecutiveFailures:
    def test_tools_meeting_min_failures_returned(self) -> None:
        profiler = ToolExecutionProfiler()
        for _ in range(5):
            profiler.record_execution("bad_tool", duration_ms=5.0, success=False, error="err")
        result = profiler.get_tools_with_consecutive_failures(min_failures=3)
        assert any(m.tool_name == "bad_tool" for m in result)

    def test_tool_below_min_failures_excluded(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("ok_tool", duration_ms=5.0, success=False, error="err")
        profiler.record_execution("ok_tool", duration_ms=5.0, success=False, error="err")
        result = profiler.get_tools_with_consecutive_failures(min_failures=3)
        assert result == []

    def test_default_min_failures_is_three(self) -> None:
        profiler = ToolExecutionProfiler()
        for _ in range(3):
            profiler.record_execution("edge", duration_ms=5.0, success=False, error="e")
        result = profiler.get_tools_with_consecutive_failures()
        assert any(m.tool_name == "edge" for m in result)

    def test_after_success_no_longer_in_consecutive_failures(self) -> None:
        profiler = ToolExecutionProfiler()
        for _ in range(5):
            profiler.record_execution("tool", duration_ms=5.0, success=False, error="e")
        profiler.record_execution("tool", duration_ms=5.0, success=True)
        result = profiler.get_tools_with_consecutive_failures(min_failures=1)
        assert result == []


class TestToolExecutionProfilerHistoryLimit:
    def test_history_trimmed_to_limit(self) -> None:
        profiler = ToolExecutionProfiler(history_limit=5)
        for i in range(10):
            profiler.record_execution(f"tool_{i}", duration_ms=float(i), success=True)
        assert len(profiler.get_recent_history(limit=100)) == 5

    def test_history_keeps_most_recent_entries(self) -> None:
        profiler = ToolExecutionProfiler(history_limit=3)
        for i in range(5):
            profiler.record_execution("tool", duration_ms=float(i * 10), success=True)
        history = profiler.get_recent_history(limit=10)
        durations = [r.duration_ms for r in history]
        # Should contain the last 3 durations: 20, 30, 40
        assert durations == [20.0, 30.0, 40.0]

    def test_get_recent_history_respects_limit_param(self) -> None:
        profiler = ToolExecutionProfiler(history_limit=100)
        for _ in range(20):
            profiler.record_execution("t", duration_ms=1.0, success=True)
        history = profiler.get_recent_history(limit=5)
        assert len(history) == 5


class TestToolExecutionProfilerGetRecentHistoryFilter:
    def test_filter_by_tool_name(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("alpha", duration_ms=10.0, success=True)
        profiler.record_execution("beta", duration_ms=20.0, success=True)
        profiler.record_execution("alpha", duration_ms=30.0, success=True)
        history = profiler.get_recent_history(tool_name="alpha")
        assert all(r.tool_name == "alpha" for r in history)
        assert len(history) == 2

    def test_filter_returns_empty_for_unknown_tool(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("tool", duration_ms=10.0, success=True)
        assert profiler.get_recent_history(tool_name="nonexistent") == []

    def test_no_filter_returns_all_tools(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("alpha", duration_ms=10.0, success=True)
        profiler.record_execution("beta", duration_ms=20.0, success=True)
        history = profiler.get_recent_history()
        tool_names = {r.tool_name for r in history}
        assert "alpha" in tool_names
        assert "beta" in tool_names


class TestToolExecutionProfilerExecutionSummary:
    def test_summary_no_metrics_returns_zeroed_dict(self) -> None:
        profiler = ToolExecutionProfiler()
        summary = profiler.get_execution_summary()
        assert summary["total_calls"] == 0
        assert summary["total_failures"] == 0
        assert summary["overall_success_rate"] == 0.0
        assert summary["slowest_tool"] is None
        assert summary["most_used_tool"] is None
        assert summary["most_unreliable_tool"] is None
        assert summary["tools"] == {}

    def test_summary_with_data_aggregates_correctly(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=100.0, success=True)
        profiler.record_execution("toolA", duration_ms=100.0, success=True)
        profiler.record_execution("toolB", duration_ms=500.0, success=False, error="err")
        summary = profiler.get_execution_summary()
        assert summary["total_calls"] == 3
        assert summary["total_failures"] == 1
        assert summary["overall_success_rate"] == pytest.approx(round(2 / 3 * 100, 2))

    def test_summary_identifies_slowest_tool(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("fast", duration_ms=10.0, success=True)
        profiler.record_execution("slow", duration_ms=9000.0, success=True)
        summary = profiler.get_execution_summary()
        assert summary["slowest_tool"] == "slow"

    def test_summary_identifies_most_used_tool(self) -> None:
        profiler = ToolExecutionProfiler()
        for _ in range(3):
            profiler.record_execution("frequent", duration_ms=5.0, success=True)
        profiler.record_execution("rare", duration_ms=5.0, success=True)
        summary = profiler.get_execution_summary()
        assert summary["most_used_tool"] == "frequent"
        assert summary["most_used_count"] == 3

    def test_summary_identifies_most_unreliable_tool(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("reliable", duration_ms=10.0, success=True)
        profiler.record_execution("flaky", duration_ms=10.0, success=False, error="e")
        summary = profiler.get_execution_summary()
        assert summary["most_unreliable_tool"] == "flaky"

    def test_summary_tools_dict_contains_all_tool_names(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("alpha", duration_ms=10.0, success=True)
        profiler.record_execution("beta", duration_ms=20.0, success=True)
        summary = profiler.get_execution_summary()
        assert "alpha" in summary["tools"]
        assert "beta" in summary["tools"]

    def test_summary_no_unreliable_tool_when_all_succeed(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("safe", duration_ms=10.0, success=True)
        summary = profiler.get_execution_summary()
        assert summary["most_unreliable_tool"] is None
        assert summary["most_unreliable_rate"] is None


class TestToolExecutionProfilerReset:
    def test_reset_single_tool_clears_metrics(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.record_execution("toolB", duration_ms=20.0, success=True)
        profiler.reset("toolA")
        m = profiler.get_metrics("toolA")
        assert m is not None
        assert m.call_count == 0

    def test_reset_single_tool_preserves_other_tools(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.record_execution("toolB", duration_ms=20.0, success=True)
        profiler.reset("toolA")
        m = profiler.get_metrics("toolB")
        assert m is not None
        assert m.call_count == 1

    def test_reset_single_tool_removes_its_history(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.record_execution("toolB", duration_ms=20.0, success=True)
        profiler.reset("toolA")
        history = profiler.get_recent_history(tool_name="toolA")
        assert history == []

    def test_reset_all_clears_all_metrics(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.record_execution("toolB", duration_ms=10.0, success=True)
        profiler.reset()
        assert profiler.get_all_metrics() == {}

    def test_reset_all_clears_history(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("toolA", duration_ms=10.0, success=True)
        profiler.reset()
        assert profiler.get_recent_history() == []

    def test_reset_unknown_tool_is_safe(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.reset("does_not_exist")  # must not raise


class TestToolExecutionProfilerSetThresholds:
    def test_set_slow_threshold_changes_slow_detection(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=10000.0)
        profiler.record_execution("moderate", duration_ms=500.0, success=True)
        assert profiler.get_slow_tools() == []
        profiler.set_thresholds(slow_threshold_ms=100.0)
        assert len(profiler.get_slow_tools()) == 1

    def test_set_unreliable_threshold_changes_detection(self) -> None:
        profiler = ToolExecutionProfiler(unreliable_threshold=0.9)
        profiler.record_execution("t", duration_ms=10.0, success=False, error="e")
        profiler.record_execution("t", duration_ms=10.0, success=True)
        # 50% failure rate — with threshold=0.9 it's not unreliable
        assert profiler.get_unreliable_tools() == []
        profiler.set_thresholds(unreliable_threshold=0.2)
        # Now 50% > 20%, tool becomes unreliable
        assert len(profiler.get_unreliable_tools()) == 1

    def test_set_thresholds_with_none_args_is_noop(self) -> None:
        profiler = ToolExecutionProfiler(slow_threshold_ms=5000.0, unreliable_threshold=0.3)
        profiler.set_thresholds(slow_threshold_ms=None, unreliable_threshold=None)
        # Internal values must remain unchanged
        assert profiler._slow_threshold_ms == 5000.0  # type: ignore[attr-defined]
        assert profiler._unreliable_threshold == 0.3  # type: ignore[attr-defined]


class TestToolExecutionProfilerGetAllMetrics:
    def test_returns_copy_not_reference(self) -> None:
        profiler = ToolExecutionProfiler()
        profiler.record_execution("tool", duration_ms=10.0, success=True)
        snapshot = profiler.get_all_metrics()
        snapshot["injected"] = ToolExecutionMetrics(tool_name="injected")
        # Original must be unaffected
        assert "injected" not in profiler.get_all_metrics()

    def test_empty_when_no_recordings(self) -> None:
        profiler = ToolExecutionProfiler()
        assert profiler.get_all_metrics() == {}


# ---------------------------------------------------------------------------
# ExecutionRecord dataclass
# ---------------------------------------------------------------------------


class TestExecutionRecord:
    def test_fields_stored_correctly(self) -> None:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        record = ExecutionRecord(
            tool_name="search",
            timestamp=now,
            duration_ms=250.0,
            success=True,
            error=None,
            args_summary="query=python",
        )
        assert record.tool_name == "search"
        assert record.timestamp == now
        assert record.duration_ms == 250.0
        assert record.success is True
        assert record.error is None
        assert record.args_summary == "query=python"

    def test_optional_fields_default_to_none(self) -> None:
        from datetime import UTC, datetime

        record = ExecutionRecord(
            tool_name="t",
            timestamp=datetime.now(UTC),
            duration_ms=1.0,
            success=False,
        )
        assert record.error is None
        assert record.args_summary is None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    def setup_method(self) -> None:
        """Reset global state before each test in this class."""
        reset_tool_profiler()

    def test_get_tool_profiler_returns_same_instance(self) -> None:
        p1 = get_tool_profiler()
        p2 = get_tool_profiler()
        assert p1 is p2

    def test_get_tool_profiler_returns_profiler_instance(self) -> None:
        profiler = get_tool_profiler()
        assert isinstance(profiler, ToolExecutionProfiler)

    def test_reset_tool_profiler_clears_data(self) -> None:
        profiler = get_tool_profiler()
        profiler.record_execution("search", duration_ms=50.0, success=True)
        assert profiler.get_metrics("search") is not None
        reset_tool_profiler()
        # After reset the same singleton has empty metrics
        assert profiler.get_metrics("search") is None

    def test_reset_tool_profiler_preserves_singleton_identity(self) -> None:
        p1 = get_tool_profiler()
        reset_tool_profiler()
        p2 = get_tool_profiler()
        # reset_tool_profiler calls .reset() on the existing instance,
        # it does NOT replace the instance — both references must still work
        assert p1 is p2
