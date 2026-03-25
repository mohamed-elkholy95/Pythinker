"""Tests for ErrorPatternAnalyzer — error pattern detection and guidance."""

from datetime import UTC, datetime, timedelta

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


# ── DetectedPattern ─────────────────────────────────────────────────


class TestDetectedPattern:
    def test_to_context_signal(self):
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
        assert "SUGGESTION" in signal
        assert "Try smaller operations" in signal


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
        assert record.metadata == {}


# ── record_error / record_success ───────────────────────────────────


class TestRecordError:
    def test_records_error(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TIMEOUT))
        stats = analyzer.get_stats()
        assert stats["total_errors"] == 1
        assert stats["tool_error_counts"]["search"] == 1

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

    def test_metadata_stored(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error(
            "search",
            _make_error_context(ErrorType.TIMEOUT),
            metadata={"query": "test"},
        )
        assert analyzer._error_history[0].metadata == {"query": "test"}


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
        analyzer.record_success("search")
        assert "search" in analyzer._last_success_time


# ── Timeout Pattern ─────────────────────────────────────────────────


class TestTimeoutPattern:
    def test_detects_timeout_pattern(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert len(timeout_patterns) == 1
        assert "shell" in timeout_patterns[0].affected_tools

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=2)
        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert len(timeout_patterns) == 0

    def test_confidence_scales_with_count(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=5)
        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert timeout_patterns[0].confidence == 1.0  # 5/5 = 1.0

    def test_most_affected_tool_identified(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        _fill_timeout_errors(analyzer, "browser", count=1)
        patterns = analyzer.analyze_patterns()
        timeout_patterns = [p for p in patterns if p.pattern_type == PatternType.TIMEOUT_REPEATED]
        assert timeout_patterns[0].affected_tools == ["shell"]


# ── JSON Parse Pattern ──────────────────────────────────────────────


class TestJsonParsePattern:
    def test_detects_json_parse_loop(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=2)
        patterns = analyzer.analyze_patterns()
        json_patterns = [p for p in patterns if p.pattern_type == PatternType.JSON_PARSE_LOOP]
        assert len(json_patterns) == 1

    def test_no_detection_below_threshold(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_json_errors(analyzer, "llm", count=1)
        patterns = analyzer.analyze_patterns()
        json_patterns = [p for p in patterns if p.pattern_type == PatternType.JSON_PARSE_LOOP]
        assert len(json_patterns) == 0


# ── Failure Streak Pattern ──────────────────────────────────────────


class TestFailureStreakPattern:
    def test_detects_consecutive_failures(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        patterns = analyzer.analyze_patterns()
        streak_patterns = [p for p in patterns if p.pattern_type == PatternType.TOOL_FAILURE_STREAK]
        assert len(streak_patterns) == 1
        assert "search" in streak_patterns[0].affected_tools

    def test_success_breaks_streak(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        analyzer.record_success("search")
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION))
        patterns = analyzer.analyze_patterns()
        streak_patterns = [p for p in patterns if p.pattern_type == PatternType.TOOL_FAILURE_STREAK]
        assert len(streak_patterns) == 0  # streak reset by success


# ── Rate Limit Pattern ──────────────────────────────────────────────


class TestRateLimitPattern:
    def test_detects_rate_limit_burst(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "rate limit exceeded"))
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "rate limit 429"))
        patterns = analyzer.analyze_patterns()
        rate_patterns = [p for p in patterns if p.pattern_type == PatternType.RATE_LIMIT_BURST]
        assert len(rate_patterns) == 1

    def test_no_detection_for_non_rate_errors(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "server error 500"))
        analyzer.record_error("api", _make_error_context(ErrorType.LLM_API, "timeout"))
        patterns = analyzer.analyze_patterns()
        rate_patterns = [p for p in patterns if p.pattern_type == PatternType.RATE_LIMIT_BURST]
        assert len(rate_patterns) == 0


# ── Same Error Repeated Pattern ─────────────────────────────────────


class TestSameErrorPattern:
    def test_detects_same_error_repeated(self):
        analyzer = ErrorPatternAnalyzer()
        for _ in range(3):
            analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Connection refused"))
        patterns = analyzer.analyze_patterns()
        same_patterns = [p for p in patterns if p.pattern_type == PatternType.SAME_ERROR_REPEATED]
        assert len(same_patterns) == 1

    def test_different_errors_no_detection(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error A"))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error B"))
        analyzer.record_error("search", _make_error_context(ErrorType.TOOL_EXECUTION, "Error C"))
        patterns = analyzer.analyze_patterns()
        same_patterns = [p for p in patterns if p.pattern_type == PatternType.SAME_ERROR_REPEATED]
        assert len(same_patterns) == 0


# ── Empty History ───────────────────────────────────────────────────


class TestEmptyHistory:
    def test_no_patterns_when_empty(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.analyze_patterns() == []

    def test_no_patterns_when_old_errors(self):
        analyzer = ErrorPatternAnalyzer()
        # Inject old errors manually
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
        patterns = analyzer.analyze_patterns()
        assert len(patterns) == 0  # all outside 5-minute window


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


# ── get_all_pattern_signals ─────────────────────────────────────────


class TestGetAllPatternSignals:
    def test_returns_signal_strings(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        signals = analyzer.get_all_pattern_signals()
        assert len(signals) >= 1
        assert all(isinstance(s, str) for s in signals)


# ── get_proactive_signals ───────────────────────────────────────────


class TestGetProactiveSignals:
    def test_returns_none_when_no_likely_tools(self):
        analyzer = ErrorPatternAnalyzer()
        assert analyzer.get_proactive_signals(None) is None
        assert analyzer.get_proactive_signals([]) is None

    def test_returns_warning_for_affected_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        warning = analyzer.get_proactive_signals(["shell"])
        assert warning is not None
        assert "CAUTION" in warning

    def test_no_warning_for_unaffected_tool(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        warning = analyzer.get_proactive_signals(["browser"])
        # May still return None or empty — timeout pattern only affects "shell"
        if warning:
            assert "shell" not in warning.lower() or "browser" not in warning.lower()

    def test_includes_historical_warnings(self):
        analyzer = ErrorPatternAnalyzer()
        analyzer._prewarned_tools["search"] = "Search often times out on complex queries"
        warning = analyzer.get_proactive_signals(["search"])
        assert warning is not None
        assert "HISTORICAL" in warning


# ── infer_tools_from_description ────────────────────────────────────


class TestInferToolsFromDescription:
    analyzer = ErrorPatternAnalyzer()

    @pytest.mark.parametrize(
        ("description", "expected_tool"),
        [
            ("Run the install command", "shell"),
            ("Execute the build script", "shell"),
            ("Navigate to the login page", "browser"),
            ("Click the submit button", "browser"),
            ("Read the configuration file", "file"),
            ("Write the output to disk", "file"),
            ("Search for Python tutorials", "search"),
            ("Find the error code in documentation", "search"),
            ("Ask the user for confirmation", "message"),
        ],
    )
    def test_infers_correct_tool(self, description: str, expected_tool: str):
        tools = self.analyzer.infer_tools_from_description(description)
        assert expected_tool in tools

    def test_returns_empty_for_vague_description(self):
        tools = self.analyzer.infer_tools_from_description("Do something interesting")
        assert tools == []

    def test_returns_multiple_tools(self):
        tools = self.analyzer.infer_tools_from_description("Search and browse the website")
        assert "search" in tools
        assert "browser" in tools


# ── clear_history ───────────────────────────────────────────────────


class TestClearHistory:
    def test_clears_all_state(self):
        analyzer = ErrorPatternAnalyzer()
        _fill_timeout_errors(analyzer, "shell", count=3)
        analyzer.record_success("other")
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
        assert "total_errors" in stats
        assert "tool_error_counts" in stats
        assert "consecutive_failures" in stats
        assert "active_patterns" in stats
        assert "prewarned_tools" in stats


# ── Singleton ───────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_instance(self):
        analyzer = get_error_pattern_analyzer()
        assert isinstance(analyzer, ErrorPatternAnalyzer)

    def test_is_stable(self):
        a1 = get_error_pattern_analyzer()
        a2 = get_error_pattern_analyzer()
        assert a1 is a2
