"""Tests for ErrorPatternAnalyzer — error pattern detection and guidance."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.error_handler import ErrorContext, ErrorType
from app.domain.services.agents.error_pattern_analyzer import (
    DetectedPattern,
    ErrorPatternAnalyzer,
    PatternType,
    ToolErrorRecord,
    get_error_pattern_analyzer,
)

# ── Helpers ─────────────────────────────────────────────────────────


def _make_error_context(error_type: ErrorType, message: str = "error") -> ErrorContext:
    return ErrorContext(error_type=error_type, message=message)


def _fill_timeout_errors(analyzer: ErrorPatternAnalyzer, tool: str = "shell", count: int = 3) -> None:
    for _ in range(count):
        analyzer.record_error(tool, _make_error_context(ErrorType.TIMEOUT, "timed out"))


def _fill_json_errors(analyzer: ErrorPatternAnalyzer, tool: str = "llm", count: int = 2) -> None:
    for _ in range(count):
        analyzer.record_error(tool, _make_error_context(ErrorType.JSON_PARSE, "invalid json"))


def _fill_rate_limit_errors(analyzer: ErrorPatternAnalyzer, tool: str = "api", count: int = 2) -> None:
    for _ in range(count):
        analyzer.record_error(tool, _make_error_context(ErrorType.LLM_API, "rate limit exceeded"))


def _fill_same_errors(analyzer: ErrorPatternAnalyzer, tool: str = "search", msg: str = "Connection refused", count: int = 3) -> None:
    for _ in range(count):
        analyzer.record_error(tool, _make_error_context(ErrorType.TOOL_EXECUTION, msg))


# ── PatternType enum ─────────────────────────────────────────────────


class TestPatternTypeEnum:
    def test_all_members_present(self):
        members = {p.value for p in PatternType}
        assert "timeout_repeated" in members
        assert "json_parse_loop" in members
        assert "tool_failure_streak" in members
        assert "rate_limit_burst" in members
        assert "stuck_on_tool" in members
        assert "same_error_repeated" in members

    def test_is_string_enum(self):
        assert isinstance(PatternType.TIMEOUT_REPEATED, str)
        assert PatternType.JSON_PARSE_LOOP == "json_parse_loop"

    def test_count(self):
        assert len(PatternType) == 6


# ── DetectedPattern ─────────────────────────────────────────────────


class TestDetectedPattern:
    def test_to_context_signal_contains_pattern_type(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.TIMEOUT_REPEATED,
            confidence=0.8,
            occurrences=4,
            time_window=timedelta(minutes=5),
            affected_tools=["shell"],
            suggestion="Try smaller operations.",
        )
        signal = pattern.to_context_signal()
        assert "PATTERN DETECTED" in signal
        assert "timeout_repeated" in signal

    def test_to_context_signal_contains_occurrences(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.JSON_PARSE_LOOP,
            confidence=0.5,
            occurrences=3,
            time_window=timedelta(seconds=300),
            affected_tools=["llm"],
            suggestion="Fix JSON formatting.",
        )
        signal = pattern.to_context_signal()
        assert "3" in signal

    def test_to_context_signal_contains_suggestion(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.RATE_LIMIT_BURST,
            confidence=0.6,
            occurrences=2,
            time_window=timedelta(minutes=5),
            affected_tools=[],
            suggestion="Wait before making additional requests.",
        )
        signal = pattern.to_context_signal()
        assert "SUGGESTION" in signal
        assert "Wait before making additional requests." in signal

    def test_to_context_signal_contains_time_window_seconds(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.TOOL_FAILURE_STREAK,
            confidence=0.7,
            occurrences=4,
            time_window=timedelta(seconds=300),
            affected_tools=["search"],
            suggestion="Use a different tool.",
        )
        signal = pattern.to_context_signal()
        assert "300" in signal

    def test_default_details_is_empty_dict(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.SAME_ERROR_REPEATED,
            confidence=0.9,
            occurrences=5,
            time_window=timedelta(minutes=5),
            affected_tools=["tool"],
            suggestion="Try another strategy.",
        )
        assert pattern.details == {}

    def test_custom_details_stored(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.TIMEOUT_REPEATED,
            confidence=0.8,
            occurrences=3,
            time_window=timedelta(minutes=5),
            affected_tools=["shell"],
            suggestion="Break into smaller parts.",
            details={"timeout_counts": {"shell": 3}},
        )
        assert pattern.details["timeout_counts"] == {"shell": 3}

    def test_confidence_range_zero(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.JSON_PARSE_LOOP,
            confidence=0.0,
            occurrences=0,
            time_window=timedelta(minutes=5),
            affected_tools=[],
            suggestion="No suggestion.",
        )
        assert pattern.confidence == 0.0

    def test_confidence_range_one(self):
        pattern = DetectedPattern(
            pattern_type=PatternType.JSON_PARSE_LOOP,
            confidence=1.0,
            occurrences=10,
            time_window=timedelta(minutes=5),
            affected_tools=["a", "b"],
            suggestion="High confidence.",
        )
        assert pattern.confidence == 1.0


# ── ToolErrorRecord ─────────────────────────────────────────────────


class TestToolErrorRecord:
    def test_construction(self):
        record = ToolErrorRecord(
            tool_name="search",
            error_type=ErrorType.TIMEOUT,
            error_message="timed out",
            timestamp=datetime.now(UTC),
        )
        assert record.tool_name == "search"
        assert record.error_type == ErrorType.TIMEOUT
        assert record.error_message == "timed out"

    def test_default_metadata_empty(self):
        record = ToolErrorRecord(
            tool_name="shell",
            error_type=ErrorType.JSON_PARSE,
            error_message="bad json",
            timestamp=datetime.now(UTC),
        )
        assert record.metadata == {}

    def test_custom_metadata_stored(self):
        ts = datetime.now(UTC)
        record = ToolErrorRecord(
            tool_name="file",
            error_type=ErrorType.TOOL_EXECUTION,
            error_message="file not found",
            timestamp=ts,
            metadata={"path": "/tmp/test.txt"},
        )
        assert record.metadata["path"] == "/tmp/test.txt"
        assert record.timestamp == ts

    def test_all_error_types_accepted(self):
        for error_type in ErrorType:
            record = ToolErrorRecord(
                tool_name="tool",
                error_type=error_type,
                error_message="test",
                timestamp=datetime.now(UTC),
            )
            assert record.error_type == error_type


# ── ErrorPatternAnalyzer construction ───────────────────────────────


class TestAnalyzerConstruction:
    def test_default_max_history(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer._max_history == 100

    def test_custom_max_history(self):
        analyzer = ErrorPatternAnalyzer(max_history=50)
        assert analyzer._max_history == 50

    def test_default_user_id_none(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer._user_id is None

    def test_custom_user_id(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        assert analyzer._user_id == "user-123"

    def test_initial_state_empty(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer._error_history == []
        assert len(analyzer._tool_error_counts) == 0
        assert len(analyzer._consecutive_failures) == 0
        assert analyzer._last_success_time == {}
        assert analyzer._prewarned_tools == {}


# ── record_error ─────────────────────────────────────────────────────


class TestRecordError:
    def test_records_single_error(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        assert len(analyzer._error_history) == 1
        assert analyzer.get_stats()["total_errors"] == 1

    def test_increments_tool_error_count(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        assert analyzer._tool_error_counts["search"] == 2

    def test_separate_counts_per_tool(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("browser", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("browser", _make_error_context(ErrorType.TIMEOUT))
        assert analyzer._tool_error_counts["search"] == 1
        assert analyzer._tool_error_counts["browser"] == 2

    def test_consecutive_failures_increment(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        assert analyzer._consecutive_failures["search"] == 2

    def test_history_trimmed_at_max(self):
        analyzer = ErrorPatternAnalyzer(max_history=5)
        for i in range(10):
            analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT, f"error {i}"))
        assert len(analyzer._error_history) == 5

    def test_history_keeps_newest_on_trim(self):
        analyzer = ErrorPatternAnalyzer(max_history=3)
        for i in range(5):
            analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT, f"error {i}"))
        # Only the last 3 should be kept
        messages = [r.error_message for r in analyzer._error_history]
        assert "error 2" in messages
        assert "error 3" in messages
        assert "error 4" in messages
        assert "error 0" not in messages

    def test_metadata_stored(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error(
            "search",
            _make_error_context(ErrorType.TIMEOUT),
            metadata={"query": "test"},
        )
        assert analyzer._error_history[0].metadata == {"query": "test"}

    def test_metadata_defaults_to_empty(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        assert analyzer._error_history[0].metadata == {}

    def test_error_message_truncated_at_500(self):
        analyzer = ErrorPatternAnalyzer()
        long_message = "x" * 600
        analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT, long_message))
        assert len(analyzer._error_history[0].error_message) == 500

    def test_error_message_short_not_truncated(self):
        analyzer = ErrorPatternAnalyzer()
        short_message = "short error"
        analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT, short_message))
        assert analyzer._error_history[0].error_message == short_message

    def test_error_record_has_utc_timestamp(self):
        analyzer = ErrorPatternAnalyzer()
        before = datetime.now(UTC)
        analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT))
        after = datetime.now(UTC)
        ts = analyzer._error_history[0].timestamp
        assert before <= ts <= after
        assert ts.tzinfo is not None


# ── record_success ───────────────────────────────────────────────────


class TestRecordSuccess:
    def test_resets_consecutive_failures(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        assert analyzer._consecutive_failures["search"] == 2
        analyzer.record_success("search")
        assert analyzer._consecutive_failures["search"] == 0

    def test_updates_last_success_time(self):
        analyzer = ErrorPatternAnalyzer()
        before = datetime.now(UTC)
        analyzer.record_success("search")
        after = datetime.now(UTC)
        assert "search" in analyzer._last_success_time
        assert before <= analyzer._last_success_time["search"] <= after

    def test_success_does_not_affect_other_tools(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        analyzer.record_success("browser")
        assert analyzer._consecutive_failures["search"] == 2
        assert analyzer._consecutive_failures["browser"] == 0

    def test_success_on_tool_with_no_errors(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_success("tool_never_failed")
        assert analyzer._consecutive_failures["tool_never_failed"] == 0
        assert "tool_never_failed" in analyzer._last_success_time

    def test_success_last_time_updates_on_repeat(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_success("tool")
        t1 = analyzer._last_success_time["tool"]
        analyzer.record_success("tool")
        t2 = analyzer._last_success_time["tool"]
        assert t2 >= t1


# ── analyze_patterns / empty history ─────────────────────────────────


class TestEmptyHistory:
    def test_no_patterns_when_empty(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.analyze_patterns() == []

    def test_no_patterns_when_all_errors_outside_window(self):
        analyzer = ErrorPatternAnalyzer()
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        analyzer._error_history = [
            ToolErrorRecord(
                tool_name="shell",
                error_type=ErrorType.TIMEOUT,
                error_message="old timeout",
                timestamp=old_time,
            )
            for _ in range(5)
        ]
        assert analyzer.analyze_patterns() == []

    def test_no_patterns_with_single_error(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT))
        # 1 timeout is below threshold of 3
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 0


# ── Timeout Pattern ─────────────────────────────────────────────────


class TestTimeoutPattern:
    def test_detects_at_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert len(timeout_patterns) == 1

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=2)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 0

    def test_most_affected_tool_in_affected_tools(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        _fill_timeout_errors(analyzer, "browser", count=1)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert timeout_patterns[0].affected_tools == ["shell"]

    def test_most_affected_tool_is_browser_when_more(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=2)
        _fill_timeout_errors(analyzer, "browser", count=3)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert timeout_patterns[0].affected_tools == ["browser"]

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=5)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert timeout_patterns[0].confidence == 1.0  # 5/5 = 1.0

    def test_confidence_partial(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        # confidence = min(3/5, 1.0) = 0.6
        assert timeout_patterns[0].confidence == pytest.approx(0.6)

    def test_suggestion_mentions_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert "shell" in timeout_patterns[0].suggestion

    def test_details_contain_timeout_counts(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=4)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert "timeout_counts" in timeout_patterns[0].details
        assert timeout_patterns[0].details["timeout_counts"]["shell"] == 4

    def test_uses_pattern_window_time_window(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert timeout_patterns[0].time_window == ErrorPatternAnalyzer.PATTERN_WINDOW

    def test_non_timeout_errors_not_counted(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("shell", _make_error_context(ErrorType.JSON_PARSE, "bad json"))
        analyzer.record_error("shell", _make_error_context(ErrorType.TOOL_EXECUTION, "exec error"))
        analyzer.record_error("shell", _make_error_context(ErrorType.LLM_API, "api error"))
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 0


# ── JSON Parse Pattern ──────────────────────────────────────────────


class TestJsonParsePattern:
    def test_detects_at_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=2)
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        assert len(json_patterns) == 1

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=1)
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        assert len(json_patterns) == 0

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=4)
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        # confidence = min(4/4, 1.0) = 1.0
        assert json_patterns[0].confidence == 1.0

    def test_confidence_partial(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=2)
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        # confidence = min(2/4, 1.0) = 0.5
        assert json_patterns[0].confidence == pytest.approx(0.5)

    def test_affected_tools_contains_all_tools(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("llm", _make_error_context(ErrorType.JSON_PARSE, "bad json 1"))
        analyzer.record_error("parser", _make_error_context(ErrorType.JSON_PARSE, "bad json 2"))
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        affected = set(json_patterns[0].affected_tools)
        assert "llm" in affected
        assert "parser" in affected

    def test_details_contain_error_samples(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("llm", _make_error_context(ErrorType.JSON_PARSE, "unexpected token"))
        analyzer.record_error("llm", _make_error_context(ErrorType.JSON_PARSE, "trailing comma"))
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        assert "error_samples" in json_patterns[0].details
        assert len(json_patterns[0].details["error_samples"]) <= 3

    def test_suggestion_mentions_json_formatting(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=2)
        json_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.JSON_PARSE_LOOP
        ]
        suggestion = json_patterns[0].suggestion.lower()
        assert "json" in suggestion


# ── Failure Streak Pattern ──────────────────────────────────────────


class TestFailureStreakPattern:
    def test_detects_consecutive_failures_at_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert len(streak_patterns) == 1
        assert "search" in streak_patterns[0].affected_tools

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(2):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert len(streak_patterns) == 0

    def test_success_breaks_streak(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        analyzer.record_success("search")
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert len(streak_patterns) == 0

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(5):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert streak_patterns[0].confidence == 1.0

    def test_suggestion_mentions_tool_name(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("browser", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert "browser" in streak_patterns[0].suggestion

    def test_details_contain_error_types(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "exec fail"))
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT, "timed out"))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "exec fail 2"))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        assert "error_types" in streak_patterns[0].details
        assert "last_error" in streak_patterns[0].details

    def test_multiple_tools_returns_first_streak(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("tool_a", _make_error_context(ErrorType.TOOL_EXECUTION))
        for _ in range(3):
            analyzer.record_error("tool_b", _make_error_context(ErrorType.TOOL_EXECUTION))
        streak_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TOOL_FAILURE_STREAK
        ]
        # At least one streak detected
        assert len(streak_patterns) >= 1


# ── Rate Limit Pattern ──────────────────────────────────────────────


class TestRateLimitPattern:
    def test_detects_rate_limit_burst(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_rate_limit_errors(analyzer, count=2)
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert len(rate_patterns) == 1

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "rate limit exceeded"))
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert len(rate_patterns) == 0

    def test_no_detection_for_non_rate_llm_errors(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "server error 500"))
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "connection refused"))
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert len(rate_patterns) == 0

    def test_rate_message_case_insensitive(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "RATE LIMIT EXCEEDED"))
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "Rate limit hit"))
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert len(rate_patterns) == 1

    def test_affected_tools_empty_for_rate_limit(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_rate_limit_errors(analyzer, count=2)
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert rate_patterns[0].affected_tools == []

    def test_details_contain_rate_limit_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_rate_limit_errors(analyzer, count=3)
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert rate_patterns[0].details["rate_limit_count"] == 3

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_rate_limit_errors(analyzer, count=4)
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        # confidence = min(4/4, 1.0) = 1.0
        assert rate_patterns[0].confidence == 1.0

    def test_suggestion_mentions_wait(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_rate_limit_errors(analyzer, count=2)
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert "wait" in rate_patterns[0].suggestion.lower()

    def test_non_llm_api_errors_not_counted(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.TIMEOUT, "rate limit timed out"))
        analyzer.record_error("api", _make_error_context(ErrorType.TIMEOUT, "rate limit timed out"))
        rate_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.RATE_LIMIT_BURST
        ]
        assert len(rate_patterns) == 0


# ── Same Error Repeated Pattern ─────────────────────────────────────


class TestSameErrorPattern:
    def test_detects_same_error_at_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, msg="Connection refused", count=3)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert len(same_patterns) == 1

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, msg="Connection refused", count=2)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert len(same_patterns) == 0

    def test_different_errors_no_detection(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error A"))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error B"))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error C"))
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert len(same_patterns) == 0

    def test_suggestion_mentions_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, msg="File not found", count=3)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert "3" in same_patterns[0].suggestion

    def test_details_contain_repeated_error(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, msg="DNS lookup failed", count=3)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert "repeated_error" in same_patterns[0].details
        assert "dns lookup failed" in same_patterns[0].details["repeated_error"]

    def test_normalization_case_insensitive(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("tool", _make_error_context(ErrorType.TOOL_EXECUTION, "connection REFUSED"))
        analyzer.record_error("tool", _make_error_context(ErrorType.TOOL_EXECUTION, "Connection Refused"))
        analyzer.record_error("tool", _make_error_context(ErrorType.TOOL_EXECUTION, "CONNECTION refused"))
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert len(same_patterns) == 1

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, msg="same error", count=5)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        # confidence = min(5/5, 1.0) = 1.0
        assert same_patterns[0].confidence == 1.0

    def test_affected_tools_set_to_tool_with_most_recent(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_same_errors(analyzer, tool="search", msg="Network error", count=3)
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert "search" in same_patterns[0].affected_tools


# ── Window filtering ────────────────────────────────────────────────


class TestWindowFiltering:
    def test_old_timeout_errors_ignored(self):
        analyzer = ErrorPatternAnalyzer()
        # Inject 3 old timeout errors (outside 5-minute window)
        old_time = datetime.now(UTC) - timedelta(minutes=6)
        for _ in range(3):
            analyzer._error_history.append(
                ToolErrorRecord(
                    tool_name="shell",
                    error_type=ErrorType.TIMEOUT,
                    error_message="timed out",
                    timestamp=old_time,
                )
            )
        # All old — no timeout pattern should be detected
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 0

    def test_recent_errors_only_in_window(self):
        analyzer = ErrorPatternAnalyzer()
        # 2 old + 3 new timeout errors
        old_time = datetime.now(UTC) - timedelta(minutes=6)
        for _ in range(2):
            analyzer._error_history.append(
                ToolErrorRecord(
                    tool_name="shell",
                    error_type=ErrorType.TIMEOUT,
                    error_message="old timeout",
                    timestamp=old_time,
                )
            )
        # 3 fresh ones via record_error
        _fill_timeout_errors(analyzer, "shell", count=3)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 1
        # Only 3 recent ones contributed
        assert timeout_patterns[0].occurrences == 3


# ── Multiple patterns simultaneously ────────────────────────────────


class TestMultiplePatterns:
    def test_can_detect_multiple_patterns_at_once(self):
        analyzer = ErrorPatternAnalyzer()
        # Trigger timeout pattern
        _fill_timeout_errors(analyzer, "shell", count=3)
        # Trigger JSON parse pattern
        _fill_json_errors(analyzer, "llm", count=2)
        patterns = analyzer.analyze_patterns()
        pattern_types = {p.pattern_type for p in patterns}
        assert PatternType.TIMEOUT_REPEATED in pattern_types
        assert PatternType.JSON_PARSE_LOOP in pattern_types

    def test_can_detect_timeout_and_rate_limit(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        _fill_rate_limit_errors(analyzer, "api", count=2)
        patterns = analyzer.analyze_patterns()
        pattern_types = {p.pattern_type for p in patterns}
        assert PatternType.TIMEOUT_REPEATED in pattern_types
        assert PatternType.RATE_LIMIT_BURST in pattern_types


# ── get_guidance_for_tool ───────────────────────────────────────────


class TestGetGuidanceForTool:
    def test_returns_guidance_when_pattern_exists(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        guidance = analyzer.get_guidance_for_tool("shell")
        assert guidance is not None
        assert "shell" in guidance.lower()

    def test_returns_none_when_no_pattern(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_guidance_for_tool("shell") is None

    def test_returns_none_for_unaffected_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        assert analyzer.get_guidance_for_tool("browser") is None

    def test_returns_guidance_for_streak_tool(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        guidance = analyzer.get_guidance_for_tool("search")
        assert guidance is not None

    def test_returns_guidance_string_type(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        guidance = analyzer.get_guidance_for_tool("shell")
        assert isinstance(guidance, str)

    def test_returns_none_for_empty_history(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_guidance_for_tool("anything") is None


# ── get_all_pattern_signals ─────────────────────────────────────────


class TestGetAllPatternSignals:
    def test_returns_empty_list_when_no_patterns(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_all_pattern_signals() == []

    def test_returns_signal_strings(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        signals = analyzer.get_all_pattern_signals()
        assert len(signals) >= 1
        assert all(isinstance(s, str) for s in signals)

    def test_signals_contain_pattern_detected(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        signals = analyzer.get_all_pattern_signals()
        assert any("PATTERN DETECTED" in s for s in signals)

    def test_signals_contain_suggestion(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        signals = analyzer.get_all_pattern_signals()
        assert any("SUGGESTION" in s for s in signals)

    def test_multiple_patterns_multiple_signals(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        _fill_json_errors(analyzer, "llm", count=2)
        signals = analyzer.get_all_pattern_signals()
        assert len(signals) >= 2


# ── get_proactive_signals ───────────────────────────────────────────


class TestGetProactiveSignals:
    def test_returns_none_when_likely_tools_is_none(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_proactive_signals(None) is None

    def test_returns_none_when_likely_tools_is_empty(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_proactive_signals([]) is None

    def test_returns_none_when_no_errors(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_proactive_signals(["shell", "browser"]) is None

    def test_returns_caution_for_affected_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        warning = analyzer.get_proactive_signals(["shell"])
        assert warning is not None
        assert "CAUTION" in warning

    def test_caution_contains_pattern_type(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        warning = analyzer.get_proactive_signals(["shell"])
        assert "timeout_repeated" in warning

    def test_no_warning_for_completely_unaffected_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        # Only shell is affected; no rate-limit pattern (empty affected_tools) either
        warning = analyzer.get_proactive_signals(["file"])
        assert warning is None

    def test_includes_historical_prewarned_tool(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools["search"] = "Search often times out on complex queries"
        warning = analyzer.get_proactive_signals(["search"])
        assert warning is not None
        assert "HISTORICAL" in warning

    def test_historical_warning_not_duplicated(self):
        analyzer = ErrorPatternAnalyzer()
        msg = "Search often times out"
        analyzer._prewarned_tools["search"] = msg
        warning = analyzer.get_proactive_signals(["search"])
        assert warning is not None
        # Message should appear once (HISTORICAL prefix)
        assert warning.count(msg) == 1

    def test_rate_limit_warning_shown_for_any_tool_when_high_confidence(self):
        analyzer = ErrorPatternAnalyzer()
        # 2 rate limits -> confidence = 2/4 = 0.5 (exactly at boundary)
        _fill_rate_limit_errors(analyzer, count=2)
        # Rate limit pattern has empty affected_tools and confidence 0.5
        warning = analyzer.get_proactive_signals(["shell"])
        assert warning is not None
        assert "WARNING" in warning

    def test_rate_limit_not_shown_below_confidence_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        # Only 1 rate-limit error -> no pattern detected, returns None
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "rate limit exceeded"))
        warning = analyzer.get_proactive_signals(["shell"])
        assert warning is None

    def test_multiple_prewarned_tools_in_signal(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools["search"] = "Search is slow"
        analyzer._prewarned_tools["browser"] = "Browser crashes"
        warning = analyzer.get_proactive_signals(["search", "browser"])
        assert "HISTORICAL" in warning
        assert warning.count("HISTORICAL") == 2

    def test_returns_string_when_warnings_present(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        warning = analyzer.get_proactive_signals(["shell"])
        assert isinstance(warning, str)


# ── infer_tools_from_description ────────────────────────────────────


class TestInferToolsFromDescription:
    @pytest.fixture
    def analyzer(self):
        return ErrorPatternAnalyzer()

    @pytest.mark.parametrize(
        ("description", "expected_tool"),
        [
            ("Run the install command", "shell"),
            ("Execute the build script", "shell"),
            ("Use terminal to check logs", "shell"),
            ("Run bash script to deploy", "shell"),
            ("Install dependencies", "shell"),
            ("Navigate to the login page", "browser"),
            ("Browse the documentation website", "browser"),
            ("Click the submit button", "browser"),
            ("Open the URL in browser", "browser"),
            ("Visit the page and check", "browser"),
            ("Read the configuration file", "file"),
            ("Write the output to disk", "file"),
            ("Save the results to a file", "file"),
            ("Create file with the content", "file"),
            ("Edit the config", "file"),
            ("Search for Python tutorials", "search"),
            ("Find the error code in documentation", "search"),
            ("Lookup the API reference", "search"),
            ("Google the error message", "search"),
            ("Query the database", "search"),
            ("Ask the user for confirmation", "message"),
            ("Tell the user the task is done", "message"),
            ("Inform user of the results", "message"),
        ],
    )
    def test_infers_correct_tool(self, analyzer: ErrorPatternAnalyzer, description: str, expected_tool: str):
        tools = analyzer.infer_tools_from_description(description)
        assert expected_tool in tools

    def test_returns_empty_for_vague_description(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("Do something interesting today")
        assert tools == []

    def test_returns_multiple_tools(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("Search the web and browse the website")
        assert "search" in tools
        assert "browser" in tools

    def test_returns_shell_and_file(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("Run the script and save the output to a file")
        assert "shell" in tools
        assert "file" in tools

    def test_empty_description_returns_empty(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("")
        assert tools == []

    def test_case_insensitive_matching(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("NAVIGATE TO THE WEBSITE")
        assert "browser" in tools

    def test_returns_list(self, analyzer: ErrorPatternAnalyzer):
        tools = analyzer.infer_tools_from_description("run the command")
        assert isinstance(tools, list)


# ── clear_history ───────────────────────────────────────────────────


class TestClearHistory:
    def test_clears_error_history(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        analyzer.clear_history()
        assert analyzer._error_history == []

    def test_clears_tool_error_counts(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        analyzer.clear_history()
        assert len(analyzer._tool_error_counts) == 0

    def test_clears_consecutive_failures(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        analyzer.clear_history()
        assert len(analyzer._consecutive_failures) == 0

    def test_clears_last_success_time(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_success("shell")
        analyzer.clear_history()
        assert analyzer._last_success_time == {}

    def test_patterns_empty_after_clear(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=5)
        analyzer.clear_history()
        assert analyzer.analyze_patterns() == []

    def test_stats_zeroed_after_clear(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        analyzer.record_success("browser")
        analyzer.clear_history()
        stats = analyzer.get_stats()
        assert stats["total_errors"] == 0
        assert stats["tool_error_counts"] == {}
        assert stats["consecutive_failures"] == {}


# ── get_stats ───────────────────────────────────────────────────────


class TestGetStats:
    def test_stats_structure(self):
        analyzer = ErrorPatternAnalyzer()
        stats = analyzer.get_stats()
        expected_keys = {"total_errors", "tool_error_counts", "consecutive_failures", "active_patterns", "prewarned_tools"}
        assert expected_keys.issubset(stats.keys())

    def test_total_errors_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        assert analyzer.get_stats()["total_errors"] == 3

    def test_tool_error_counts_accurate(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=2)
        _fill_json_errors(analyzer, "llm", count=3)
        stats = analyzer.get_stats()
        assert stats["tool_error_counts"]["shell"] == 2
        assert stats["tool_error_counts"]["llm"] == 3

    def test_consecutive_failures_in_stats(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(4):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        stats = analyzer.get_stats()
        assert stats["consecutive_failures"]["search"] == 4

    def test_active_patterns_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        stats = analyzer.get_stats()
        assert stats["active_patterns"] >= 1

    def test_prewarned_tools_count(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools["search"] = "warning"
        analyzer._prewarned_tools["browser"] = "another warning"
        stats = analyzer.get_stats()
        assert stats["prewarned_tools"] == 2

    def test_empty_stats(self):
        analyzer = ErrorPatternAnalyzer()
        stats = analyzer.get_stats()
        assert stats["total_errors"] == 0
        assert stats["active_patterns"] == 0
        assert stats["prewarned_tools"] == 0


# ── set_user_id ─────────────────────────────────────────────────────


class TestSetUserId:
    def test_sets_user_id(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer._user_id is None
        analyzer.set_user_id("user-abc")
        assert analyzer._user_id == "user-abc"

    def test_overwrites_existing_user_id(self):
        analyzer = ErrorPatternAnalyzer(user_id="old-user")
        analyzer.set_user_id("new-user")
        assert analyzer._user_id == "new-user"


# ── persist_patterns (async) ────────────────────────────────────────


class TestPersistPatterns:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_user_id(self):
        analyzer = ErrorPatternAnalyzer()
        mock_memory = AsyncMock()
        result = await analyzer.persist_patterns(mock_memory)
        assert result == 0
        mock_memory.store_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_patterns(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()
        result = await analyzer.persist_patterns(mock_memory)
        assert result == 0
        mock_memory.store_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_persist_low_confidence_patterns(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        # 3 timeouts => confidence = 3/5 = 0.6, which is < 0.7 threshold
        _fill_timeout_errors(analyzer, "shell", count=3)
        mock_memory = AsyncMock()
        result = await analyzer.persist_patterns(mock_memory)
        assert result == 0
        mock_memory.store_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_high_confidence_pattern(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        # 5 timeouts => confidence = min(5/5, 1.0) = 1.0, >= 0.7
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        result = await analyzer.persist_patterns(mock_memory)
        assert result >= 1
        mock_memory.store_memory.assert_called()

    @pytest.mark.asyncio
    async def test_persists_with_correct_user_id(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-xyz")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        assert call_kwargs["user_id"] == "user-xyz"

    @pytest.mark.asyncio
    async def test_persists_with_error_pattern_memory_type(self):
        from app.domain.models.long_term_memory import MemoryType

        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        assert call_kwargs["memory_type"] == MemoryType.ERROR_PATTERN

    @pytest.mark.asyncio
    async def test_persists_with_correct_content(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        # Multiple patterns may be persisted (timeout + streak + same_error);
        # verify every call carries non-empty string content
        all_calls = mock_memory.store_memory.call_args_list
        assert len(all_calls) >= 1
        for call in all_calls:
            content = call[1]["content"]
            assert isinstance(content, str) and len(content) > 0

    @pytest.mark.asyncio
    async def test_persists_metadata_with_pattern_type(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        # Multiple patterns may be persisted; verify timeout is among them
        all_calls = mock_memory.store_memory.call_args_list
        pattern_types = [call[1]["metadata"]["pattern_type"] for call in all_calls]
        assert PatternType.TIMEOUT_REPEATED.value in pattern_types

    @pytest.mark.asyncio
    async def test_persists_metadata_with_confidence(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        metadata = call_kwargs["metadata"]
        assert "confidence" in metadata
        assert metadata["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_persists_high_importance_for_very_high_confidence(self):
        from app.domain.models.long_term_memory import MemoryImportance

        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        # 5 timeouts -> confidence = 1.0 >= 0.9 -> HIGH importance
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        assert call_kwargs["importance"] == MemoryImportance.HIGH

    @pytest.mark.asyncio
    async def test_persists_medium_importance_for_medium_confidence(self):
        from app.domain.models.long_term_memory import MemoryImportance

        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        # 4 timeouts -> confidence = 4/5 = 0.8 (>= 0.7, < 0.9) -> MEDIUM importance
        _fill_timeout_errors(analyzer, "shell", count=4)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        assert call_kwargs["importance"] == MemoryImportance.MEDIUM

    @pytest.mark.asyncio
    async def test_handles_store_memory_exception_gracefully(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        mock_memory.store_memory.side_effect = Exception("Storage failure")
        # Should not raise, should return 0
        result = await analyzer.persist_patterns(mock_memory)
        assert result == 0

    @pytest.mark.asyncio
    async def test_tags_include_pattern_type(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        # Multiple patterns may be persisted; verify timeout pattern call has correct tags
        all_calls = mock_memory.store_memory.call_args_list
        all_tags_flat = [tag for call in all_calls for tag in call[1]["tags"]]
        assert "error_pattern" in all_tags_flat
        assert PatternType.TIMEOUT_REPEATED.value in all_tags_flat

    @pytest.mark.asyncio
    async def test_tags_include_affected_tools(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        tags = call_kwargs["tags"]
        assert "shell" in tags

    @pytest.mark.asyncio
    async def test_metadata_includes_time_window_seconds(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        _fill_timeout_errors(analyzer, "shell", count=5)
        mock_memory = AsyncMock()
        await analyzer.persist_patterns(mock_memory)
        call_kwargs = mock_memory.store_memory.call_args[1]
        metadata = call_kwargs["metadata"]
        assert "time_window_seconds" in metadata
        assert metadata["time_window_seconds"] == ErrorPatternAnalyzer.PATTERN_WINDOW.total_seconds()


# ── load_user_patterns (async) ──────────────────────────────────────


class TestLoadUserPatterns:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_user_id(self):
        analyzer = ErrorPatternAnalyzer()
        mock_memory = AsyncMock()
        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 0
        mock_memory.retrieve_relevant.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_results(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()
        mock_memory.retrieve_relevant.return_value = []
        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 0

    @pytest.mark.asyncio
    async def test_calls_retrieve_relevant_with_user_id(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()
        mock_memory.retrieve_relevant.return_value = []
        await analyzer.load_user_patterns(mock_memory)
        call_kwargs = mock_memory.retrieve_relevant.call_args[1]
        assert call_kwargs["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_calls_retrieve_relevant_with_error_pattern_type(self):
        from app.domain.models.long_term_memory import MemoryType

        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()
        mock_memory.retrieve_relevant.return_value = []
        await analyzer.load_user_patterns(mock_memory)
        call_kwargs = mock_memory.retrieve_relevant.call_args[1]
        assert MemoryType.ERROR_PATTERN in call_kwargs["memory_types"]

    @pytest.mark.asyncio
    async def test_loads_prewarned_tools_from_results(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()

        # Build a mock result with affected_tools metadata
        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "Shell times out on long commands"
        mock_memory_entry.metadata = {"affected_tools": ["shell"]}

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 1
        assert "shell" in analyzer._prewarned_tools
        assert analyzer._prewarned_tools["shell"] == "Shell times out on long commands"

    @pytest.mark.asyncio
    async def test_loads_multiple_tools_from_single_result(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()

        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "Browser and search tools are unreliable"
        mock_memory_entry.metadata = {"affected_tools": ["browser", "search"]}

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 2
        assert "browser" in analyzer._prewarned_tools
        assert "search" in analyzer._prewarned_tools

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_prewarned_tool(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        analyzer._prewarned_tools["shell"] = "original warning"
        mock_memory = AsyncMock()

        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "new warning from history"
        mock_memory_entry.metadata = {"affected_tools": ["shell"]}

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        result = await analyzer.load_user_patterns(mock_memory)
        # Shell already pre-warned; not overwritten
        assert result == 0
        assert analyzer._prewarned_tools["shell"] == "original warning"

    @pytest.mark.asyncio
    async def test_handles_missing_metadata_gracefully(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()

        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "Some error pattern"
        mock_memory_entry.metadata = None  # Missing metadata

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        # Should not raise, metadata defaults to {} via `or {}`
        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_empty_affected_tools(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()

        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "Generic error pattern"
        mock_memory_entry.metadata = {"affected_tools": []}

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_retrieve_exception_gracefully(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()
        mock_memory.retrieve_relevant.side_effect = Exception("DB connection failed")

        result = await analyzer.load_user_patterns(mock_memory)
        assert result == 0

    @pytest.mark.asyncio
    async def test_loaded_patterns_feed_proactive_signals(self):
        analyzer = ErrorPatternAnalyzer(user_id="user-123")
        mock_memory = AsyncMock()

        mock_memory_entry = MagicMock()
        mock_memory_entry.content = "Shell is historically unreliable"
        mock_memory_entry.metadata = {"affected_tools": ["shell"]}

        mock_result = MagicMock()
        mock_result.memory = mock_memory_entry

        mock_memory.retrieve_relevant.return_value = [mock_result]

        await analyzer.load_user_patterns(mock_memory)

        # Now proactive signals should include historical warning for "shell"
        warning = analyzer.get_proactive_signals(["shell"])
        assert warning is not None
        assert "HISTORICAL" in warning
        assert "Shell is historically unreliable" in warning


# ── Singleton ───────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_instance(self):
        analyzer = get_error_pattern_analyzer()
        assert isinstance(analyzer, ErrorPatternAnalyzer)

    def test_is_stable(self):
        a1 = get_error_pattern_analyzer()
        a2 = get_error_pattern_analyzer()
        assert a1 is a2

    def test_singleton_is_error_pattern_analyzer(self):
        analyzer = get_error_pattern_analyzer()
        assert type(analyzer).__name__ == "ErrorPatternAnalyzer"


# ── Threshold constants ──────────────────────────────────────────────


class TestThresholdConstants:
    def test_timeout_threshold(self):
        assert ErrorPatternAnalyzer.TIMEOUT_THRESHOLD == 3

    def test_json_parse_threshold(self):
        assert ErrorPatternAnalyzer.JSON_PARSE_THRESHOLD == 2

    def test_tool_failure_threshold(self):
        assert ErrorPatternAnalyzer.TOOL_FAILURE_THRESHOLD == 3

    def test_rate_limit_threshold(self):
        assert ErrorPatternAnalyzer.RATE_LIMIT_THRESHOLD == 2

    def test_same_error_threshold(self):
        assert ErrorPatternAnalyzer.SAME_ERROR_THRESHOLD == 3

    def test_pattern_window_is_5_minutes(self):
        assert timedelta(minutes=5) == ErrorPatternAnalyzer.PATTERN_WINDOW


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_exactly_at_timeout_threshold_triggers(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=ErrorPatternAnalyzer.TIMEOUT_THRESHOLD)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 1

    def test_one_below_timeout_threshold_no_trigger(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=ErrorPatternAnalyzer.TIMEOUT_THRESHOLD - 1)
        timeout_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.TIMEOUT_REPEATED
        ]
        assert len(timeout_patterns) == 0

    def test_error_message_at_exactly_100_chars_normalized(self):
        analyzer = ErrorPatternAnalyzer()
        msg = "x" * 100  # Exactly 100 chars
        for _ in range(3):
            analyzer.record_error("tool", _make_error_context(ErrorType.TOOL_EXECUTION, msg))
        same_patterns = [
            p for p in analyzer.analyze_patterns()
            if p.pattern_type == PatternType.SAME_ERROR_REPEATED
        ]
        assert len(same_patterns) == 1

    def test_large_number_of_errors_doesnt_crash(self):
        analyzer = ErrorPatternAnalyzer(max_history=200)
        for i in range(150):
            analyzer.record_error("tool", _make_error_context(ErrorType.TIMEOUT, f"error {i % 5}"))
        patterns = analyzer.analyze_patterns()
        assert isinstance(patterns, list)

    def test_prewarned_tool_not_in_history_still_shows(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools["legacy_tool"] = "This tool has historically crashed"
        warning = analyzer.get_proactive_signals(["legacy_tool"])
        assert warning is not None
        assert "HISTORICAL" in warning

    def test_analyze_patterns_does_not_mutate_history(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=5)
        count_before = len(analyzer._error_history)
        analyzer.analyze_patterns()
        analyzer.analyze_patterns()
        assert len(analyzer._error_history) == count_before
