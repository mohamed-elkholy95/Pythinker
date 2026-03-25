"""Tests for SelfHealingLoop: recovery strategies, error pattern tracking,
reflection triggers, and data-model serialization.
"""

from datetime import datetime
from unittest.mock import MagicMock

from app.domain.services.agents.error_handler import ErrorContext, ErrorType
from app.domain.services.agents.self_healing_loop import (
    ERROR_STRATEGY_MAP,
    TOOL_ALTERNATIVES,
    RecoveryAttempt,
    RecoveryStrategy,
    SelfHealingLoop,
    SelfReflectionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error_context(
    error_type: ErrorType = ErrorType.UNKNOWN,
    message: str = "test error",
) -> ErrorContext:
    """Build a minimal ErrorContext for use in tests."""
    return ErrorContext(error_type=error_type, message=message)


# ---------------------------------------------------------------------------
# RecoveryStrategy enum
# ---------------------------------------------------------------------------


class TestRecoveryStrategyEnum:
    """Tests for the RecoveryStrategy enum members and string values."""

    def test_all_nine_members_present(self):
        members = {s.name for s in RecoveryStrategy}
        assert members == {
            "RETRY",
            "RETRY_WITH_CONTEXT",
            "ALTERNATIVE_TOOL",
            "ALTERNATIVE_APPROACH",
            "SIMPLIFY",
            "DECOMPOSE",
            "SKIP",
            "ESCALATE",
            "ROLLBACK",
        }

    def test_str_enum_inherits_str(self):
        assert isinstance(RecoveryStrategy.RETRY, str)

    def test_retry_value(self):
        assert RecoveryStrategy.RETRY.value == "retry"

    def test_retry_with_context_value(self):
        assert RecoveryStrategy.RETRY_WITH_CONTEXT.value == "retry_with_context"

    def test_alternative_tool_value(self):
        assert RecoveryStrategy.ALTERNATIVE_TOOL.value == "alternative_tool"

    def test_alternative_approach_value(self):
        assert RecoveryStrategy.ALTERNATIVE_APPROACH.value == "alternative_approach"

    def test_simplify_value(self):
        assert RecoveryStrategy.SIMPLIFY.value == "simplify"

    def test_decompose_value(self):
        assert RecoveryStrategy.DECOMPOSE.value == "decompose"

    def test_skip_value(self):
        assert RecoveryStrategy.SKIP.value == "skip"

    def test_escalate_value(self):
        assert RecoveryStrategy.ESCALATE.value == "escalate"

    def test_rollback_value(self):
        assert RecoveryStrategy.ROLLBACK.value == "rollback"

    def test_string_comparison_works(self):
        # str-enum allows comparison against plain strings
        assert RecoveryStrategy.RETRY == "retry"


# ---------------------------------------------------------------------------
# RecoveryAttempt dataclass
# ---------------------------------------------------------------------------


class TestRecoveryAttempt:
    """Tests for the RecoveryAttempt dataclass."""

    def _make(self, **kwargs) -> RecoveryAttempt:
        defaults = {
            "strategy": RecoveryStrategy.RETRY,
            "error_type": ErrorType.TIMEOUT,
            "original_error": "original error text",
        }
        defaults.update(kwargs)
        return RecoveryAttempt(**defaults)

    def test_default_success_is_false(self):
        attempt = self._make()
        assert attempt.success is False

    def test_default_result_is_none(self):
        attempt = self._make()
        assert attempt.result is None

    def test_default_duration_ms_is_none(self):
        attempt = self._make()
        assert attempt.duration_ms is None

    def test_timestamp_defaults_to_utc_aware(self):
        attempt = self._make()
        assert attempt.timestamp.tzinfo is not None

    def test_to_dict_uses_strategy_value(self):
        attempt = self._make(strategy=RecoveryStrategy.SIMPLIFY)
        d = attempt.to_dict()
        assert d["strategy"] == "simplify"

    def test_to_dict_uses_error_type_value(self):
        attempt = self._make(error_type=ErrorType.JSON_PARSE)
        d = attempt.to_dict()
        assert d["error_type"] == "json_parse"

    def test_to_dict_truncates_original_error_to_200_chars(self):
        long_error = "e" * 500
        attempt = self._make(original_error=long_error)
        d = attempt.to_dict()
        assert len(d["original_error"]) == 200

    def test_to_dict_short_error_is_not_truncated(self):
        short_error = "short error"
        attempt = self._make(original_error=short_error)
        d = attempt.to_dict()
        assert d["original_error"] == short_error

    def test_to_dict_includes_timestamp_as_isoformat(self):
        attempt = self._make()
        d = attempt.to_dict()
        # Should be a valid ISO 8601 string
        parsed = datetime.fromisoformat(d["timestamp"])
        assert parsed is not None

    def test_to_dict_success_and_result_fields(self):
        attempt = self._make(success=True, result="ok", duration_ms=42)
        d = attempt.to_dict()
        assert d["success"] is True
        assert d["result"] == "ok"
        assert d["duration_ms"] == 42

    def test_to_dict_error_exactly_200_chars_not_truncated(self):
        exact_error = "x" * 200
        attempt = self._make(original_error=exact_error)
        d = attempt.to_dict()
        assert d["original_error"] == exact_error


# ---------------------------------------------------------------------------
# SelfReflectionResult dataclass
# ---------------------------------------------------------------------------


class TestSelfReflectionResult:
    """Tests for the SelfReflectionResult dataclass default values."""

    def _make(self, **kwargs) -> SelfReflectionResult:
        defaults = {
            "iteration": 1,
            "observations": [],
            "issues_identified": [],
            "recommendations": [],
        }
        defaults.update(kwargs)
        return SelfReflectionResult(**defaults)

    def test_should_adjust_strategy_defaults_to_false(self):
        result = self._make()
        assert result.should_adjust_strategy is False

    def test_suggested_strategy_defaults_to_none(self):
        result = self._make()
        assert result.suggested_strategy is None

    def test_timestamp_is_utc_aware(self):
        result = self._make()
        assert result.timestamp.tzinfo is not None

    def test_fields_stored_correctly(self):
        result = self._make(
            iteration=3,
            observations=["obs1"],
            issues_identified=["issue1"],
            recommendations=["rec1"],
            should_adjust_strategy=True,
            suggested_strategy=RecoveryStrategy.DECOMPOSE,
        )
        assert result.iteration == 3
        assert result.observations == ["obs1"]
        assert result.issues_identified == ["issue1"]
        assert result.recommendations == ["rec1"]
        assert result.should_adjust_strategy is True
        assert result.suggested_strategy == RecoveryStrategy.DECOMPOSE


# ---------------------------------------------------------------------------
# ERROR_STRATEGY_MAP
# ---------------------------------------------------------------------------


class TestErrorStrategyMap:
    """Tests for the ERROR_STRATEGY_MAP constant."""

    def test_all_error_types_present_in_map(self):
        """Every ErrorType listed in the map is present as a key."""
        expected_types = {
            ErrorType.JSON_PARSE,
            ErrorType.TOKEN_LIMIT,
            ErrorType.TOOL_EXECUTION,
            ErrorType.LLM_API,
            ErrorType.LLM_EMPTY_RESPONSE,
            ErrorType.MCP_CONNECTION,
            ErrorType.TIMEOUT,
            ErrorType.STUCK_LOOP,
            ErrorType.UNKNOWN,
        }
        assert expected_types.issubset(set(ERROR_STRATEGY_MAP.keys()))

    def test_json_parse_starts_with_retry_with_context(self):
        strategies = ERROR_STRATEGY_MAP[ErrorType.JSON_PARSE]
        assert strategies[0] == RecoveryStrategy.RETRY_WITH_CONTEXT

    def test_token_limit_starts_with_simplify(self):
        strategies = ERROR_STRATEGY_MAP[ErrorType.TOKEN_LIMIT]
        assert strategies[0] == RecoveryStrategy.SIMPLIFY

    def test_tool_execution_includes_retry_and_alternative_tool(self):
        strategies = ERROR_STRATEGY_MAP[ErrorType.TOOL_EXECUTION]
        assert RecoveryStrategy.RETRY in strategies
        assert RecoveryStrategy.ALTERNATIVE_TOOL in strategies

    def test_stuck_loop_starts_with_alternative_approach(self):
        strategies = ERROR_STRATEGY_MAP[ErrorType.STUCK_LOOP]
        assert strategies[0] == RecoveryStrategy.ALTERNATIVE_APPROACH

    def test_all_map_values_are_nonempty_lists(self):
        for error_type, strategies in ERROR_STRATEGY_MAP.items():
            assert isinstance(strategies, list), f"{error_type} value should be a list"
            assert len(strategies) > 0, f"{error_type} strategy list should not be empty"


# ---------------------------------------------------------------------------
# TOOL_ALTERNATIVES
# ---------------------------------------------------------------------------


class TestToolAlternatives:
    """Tests for the TOOL_ALTERNATIVES constant."""

    def test_browser_navigate_has_alternatives(self):
        assert "browser_navigate" in TOOL_ALTERNATIVES
        assert len(TOOL_ALTERNATIVES["browser_navigate"]) > 0

    def test_info_search_web_has_alternatives(self):
        assert "info_search_web" in TOOL_ALTERNATIVES
        assert len(TOOL_ALTERNATIVES["info_search_web"]) > 0

    def test_browser_navigate_alternatives_are_strings(self):
        for alt in TOOL_ALTERNATIVES["browser_navigate"]:
            assert isinstance(alt, str)

    def test_info_search_web_alternatives_are_strings(self):
        for alt in TOOL_ALTERNATIVES["info_search_web"]:
            assert isinstance(alt, str)


# ---------------------------------------------------------------------------
# SelfHealingLoop initialisation
# ---------------------------------------------------------------------------


class TestSelfHealingLoopInit:
    """Tests for SelfHealingLoop.__init__ defaults and custom values."""

    def test_default_max_recovery_attempts(self):
        loop = SelfHealingLoop()
        assert loop._max_recovery_attempts == 3

    def test_default_reflection_interval(self):
        loop = SelfHealingLoop()
        assert loop._reflection_interval == 5

    def test_custom_max_recovery_attempts(self):
        loop = SelfHealingLoop(max_recovery_attempts=7)
        assert loop._max_recovery_attempts == 7

    def test_custom_reflection_interval(self):
        loop = SelfHealingLoop(reflection_interval=10)
        assert loop._reflection_interval == 10

    def test_initial_recovery_attempts_list_is_empty(self):
        loop = SelfHealingLoop()
        assert loop._recovery_attempts == []

    def test_initial_current_attempt_count_is_zero(self):
        loop = SelfHealingLoop()
        assert loop._current_attempt_count == 0

    def test_initial_error_patterns_is_empty(self):
        loop = SelfHealingLoop()
        assert loop._error_patterns == {}

    def test_pattern_threshold_default(self):
        loop = SelfHealingLoop()
        assert loop._pattern_threshold == 3

    def test_error_handler_created_when_none_passed(self):
        loop = SelfHealingLoop()
        assert loop._error_handler is not None

    def test_custom_error_handler_stored(self):
        handler = MagicMock()
        loop = SelfHealingLoop(error_handler=handler)
        assert loop._error_handler is handler


# ---------------------------------------------------------------------------
# SelfHealingLoop._get_error_signature
# ---------------------------------------------------------------------------


class TestGetErrorSignature:
    """Tests for _get_error_signature method."""

    def test_signature_format_contains_error_type_value(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.TIMEOUT, "request timed out")
        sig = loop._get_error_signature(ctx)
        assert sig.startswith("timeout:")

    def test_signature_includes_message_prefix(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.JSON_PARSE, "unexpected token at position 5")
        sig = loop._get_error_signature(ctx)
        assert "unexpected token at position 5" in sig

    def test_signature_truncates_message_to_50_chars(self):
        loop = SelfHealingLoop()
        long_message = "a" * 100
        ctx = _make_error_context(ErrorType.UNKNOWN, long_message)
        sig = loop._get_error_signature(ctx)
        message_part = sig.split(":", 1)[1]
        assert len(message_part) == 50

    def test_signature_short_message_not_padded(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.UNKNOWN, "short")
        sig = loop._get_error_signature(ctx)
        assert sig == "unknown:short"

    def test_different_error_types_produce_different_signatures(self):
        loop = SelfHealingLoop()
        ctx_a = _make_error_context(ErrorType.TIMEOUT, "same message")
        ctx_b = _make_error_context(ErrorType.JSON_PARSE, "same message")
        assert loop._get_error_signature(ctx_a) != loop._get_error_signature(ctx_b)


# ---------------------------------------------------------------------------
# SelfHealingLoop._track_error_pattern
# ---------------------------------------------------------------------------


class TestTrackErrorPattern:
    """Tests for _track_error_pattern method."""

    def test_first_occurrence_sets_count_to_one(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.TOOL_EXECUTION, "tool failed")
        loop._track_error_pattern(ctx)
        sig = loop._get_error_signature(ctx)
        assert loop._error_patterns[sig] == 1

    def test_multiple_occurrences_increment_count(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.LLM_API, "rate limit")
        for _ in range(5):
            loop._track_error_pattern(ctx)
        sig = loop._get_error_signature(ctx)
        assert loop._error_patterns[sig] == 5

    def test_different_errors_tracked_independently(self):
        loop = SelfHealingLoop()
        ctx_a = _make_error_context(ErrorType.TIMEOUT, "timeout error")
        ctx_b = _make_error_context(ErrorType.JSON_PARSE, "parse error")
        loop._track_error_pattern(ctx_a)
        loop._track_error_pattern(ctx_a)
        loop._track_error_pattern(ctx_b)
        sig_a = loop._get_error_signature(ctx_a)
        sig_b = loop._get_error_signature(ctx_b)
        assert loop._error_patterns[sig_a] == 2
        assert loop._error_patterns[sig_b] == 1

    def test_threshold_reached_when_count_equals_pattern_threshold(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.STUCK_LOOP, "stuck in loop")
        # Drive count up to the threshold; no exception should be raised
        for _ in range(loop._pattern_threshold):
            loop._track_error_pattern(ctx)
        sig = loop._get_error_signature(ctx)
        assert loop._error_patterns[sig] >= loop._pattern_threshold

    def test_count_continues_incrementing_beyond_threshold(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.UNKNOWN, "mystery")
        for _ in range(10):
            loop._track_error_pattern(ctx)
        sig = loop._get_error_signature(ctx)
        assert loop._error_patterns[sig] == 10


# ---------------------------------------------------------------------------
# SelfHealingLoop.can_attempt_recovery / increment / reset
# ---------------------------------------------------------------------------


class TestRecoveryCounterManagement:
    """Tests for recovery attempt counter lifecycle."""

    def test_can_attempt_recovery_true_when_below_max(self):
        loop = SelfHealingLoop(max_recovery_attempts=3)
        assert loop.can_attempt_recovery() is True

    def test_can_attempt_recovery_false_after_max_increments(self):
        loop = SelfHealingLoop(max_recovery_attempts=2)
        loop.increment_recovery_counter()
        loop.increment_recovery_counter()
        assert loop.can_attempt_recovery() is False

    def test_reset_counter_restores_ability_to_attempt(self):
        loop = SelfHealingLoop(max_recovery_attempts=1)
        loop.increment_recovery_counter()
        assert loop.can_attempt_recovery() is False
        loop.reset_recovery_counter()
        assert loop.can_attempt_recovery() is True

    def test_reset_clears_tried_strategies(self):
        loop = SelfHealingLoop()
        loop._tried_strategies["key"] = [RecoveryStrategy.RETRY]
        loop.reset_recovery_counter()
        assert loop._tried_strategies == {}


# ---------------------------------------------------------------------------
# SelfHealingLoop.select_recovery_strategy
# ---------------------------------------------------------------------------


class TestSelectRecoveryStrategy:
    """Tests for strategy selection logic."""

    def test_selects_first_candidate_on_first_call(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.JSON_PARSE, "bad json")
        strategy = loop.select_recovery_strategy(ctx)
        assert strategy == ERROR_STRATEGY_MAP[ErrorType.JSON_PARSE][0]

    def test_cycles_to_next_strategy_on_second_call(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.JSON_PARSE, "bad json")
        first = loop.select_recovery_strategy(ctx)
        second = loop.select_recovery_strategy(ctx)
        assert first != second

    def test_escalates_when_all_strategies_exhausted(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.UNKNOWN, "mystery error")
        # UNKNOWN has only [RETRY, ESCALATE]; exhaust both
        loop.select_recovery_strategy(ctx)
        loop.select_recovery_strategy(ctx)
        # Third call: all tried → escalate
        strategy = loop.select_recovery_strategy(ctx)
        assert strategy == RecoveryStrategy.ESCALATE

    def test_uses_known_successful_strategy(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.TOOL_EXECUTION, "tool error")
        error_key = f"{ErrorType.TOOL_EXECUTION.value}:general"
        loop._successful_strategies[error_key] = RecoveryStrategy.ALTERNATIVE_TOOL
        strategy = loop.select_recovery_strategy(ctx)
        assert strategy == RecoveryStrategy.ALTERNATIVE_TOOL


# ---------------------------------------------------------------------------
# SelfHealingLoop.get_alternative_tools
# ---------------------------------------------------------------------------


class TestGetAlternativeTools:
    """Tests for TOOL_ALTERNATIVES lookup."""

    def test_returns_alternatives_for_known_tool(self):
        loop = SelfHealingLoop()
        alts = loop.get_alternative_tools("browser_navigate")
        assert alts == TOOL_ALTERNATIVES["browser_navigate"]

    def test_returns_empty_list_for_unknown_tool(self):
        loop = SelfHealingLoop()
        alts = loop.get_alternative_tools("nonexistent_tool_xyz")
        assert alts == []

    def test_partial_match_returns_alternatives(self):
        loop = SelfHealingLoop()
        # "browser_navigate" contains "navigate"; no partial match defined for this case,
        # but "file_read" is in TOOL_ALTERNATIVES, so "file" partial match works:
        alts = loop.get_alternative_tools("file_read")
        assert len(alts) > 0


# ---------------------------------------------------------------------------
# SelfHealingLoop.should_reflect / perform_reflection
# ---------------------------------------------------------------------------


class TestShouldReflect:
    """Tests for the reflection trigger logic."""

    def test_should_reflect_false_at_iteration_zero(self):
        loop = SelfHealingLoop(reflection_interval=5)
        # _iteration_count starts at 0
        assert loop.should_reflect() is False

    def test_should_reflect_true_at_exact_interval(self):
        loop = SelfHealingLoop(reflection_interval=5)
        loop._iteration_count = 5
        assert loop.should_reflect() is True

    def test_should_reflect_false_between_intervals(self):
        loop = SelfHealingLoop(reflection_interval=5)
        loop._iteration_count = 3
        assert loop.should_reflect() is False

    def test_perform_reflection_increments_iteration(self):
        loop = SelfHealingLoop()
        loop.perform_reflection()
        assert loop._iteration_count == 1

    def test_perform_reflection_returns_self_reflection_result(self):
        loop = SelfHealingLoop()
        result = loop.perform_reflection()
        assert isinstance(result, SelfReflectionResult)

    def test_perform_reflection_appended_to_reflections_list(self):
        loop = SelfHealingLoop()
        loop.perform_reflection()
        assert len(loop._reflections) == 1


# ---------------------------------------------------------------------------
# SelfHealingLoop.get_recovery_stats
# ---------------------------------------------------------------------------


class TestGetRecoveryStats:
    """Tests for the recovery statistics output."""

    def test_stats_initial_state(self):
        loop = SelfHealingLoop()
        stats = loop.get_recovery_stats()
        assert stats["total_attempts"] == 0
        assert stats["successful_recoveries"] == 0
        assert stats["success_rate"] == 0
        assert stats["current_attempt_count"] == 0

    def test_stats_reflect_max_recovery_attempts(self):
        loop = SelfHealingLoop(max_recovery_attempts=7)
        assert loop.get_recovery_stats()["max_recovery_attempts"] == 7

    def test_stats_include_error_patterns(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.TIMEOUT, "timed out")
        loop._track_error_pattern(ctx)
        stats = loop.get_recovery_stats()
        assert len(stats["error_patterns"]) == 1


# ---------------------------------------------------------------------------
# SelfHealingLoop.clear_history
# ---------------------------------------------------------------------------


class TestClearHistory:
    """Tests for clear_history method."""

    def test_clear_history_resets_recovery_attempts(self):
        loop = SelfHealingLoop()
        loop._recovery_attempts.append(
            RecoveryAttempt(
                strategy=RecoveryStrategy.RETRY,
                error_type=ErrorType.TIMEOUT,
                original_error="err",
            )
        )
        loop.clear_history()
        assert loop._recovery_attempts == []

    def test_clear_history_resets_error_patterns(self):
        loop = SelfHealingLoop()
        ctx = _make_error_context(ErrorType.LLM_API, "rate limit")
        loop._track_error_pattern(ctx)
        loop.clear_history()
        assert loop._error_patterns == {}

    def test_clear_history_resets_iteration_count(self):
        loop = SelfHealingLoop()
        loop._iteration_count = 10
        loop.clear_history()
        assert loop._iteration_count == 0

    def test_clear_history_resets_reflections(self):
        loop = SelfHealingLoop()
        loop.perform_reflection()
        loop.clear_history()
        assert loop._reflections == []
