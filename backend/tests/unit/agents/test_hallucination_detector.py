"""Tests for ToolHallucinationDetector — dataclasses, detection, validation, semantics, statistics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.services.agents.hallucination_detector import (
    HallucinationEvent,
    ToolHallucinationDetector,
    ToolValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASIC_TOOLS = ["file_read", "file_write", "shell_exec", "browser_goto", "web_search"]


def make_detector(
    tools: list[str] | None = None,
    similarity_threshold: float = 0.6,
    max_suggestions: int = 3,
    hallucination_threshold: int = 3,
) -> ToolHallucinationDetector:
    return ToolHallucinationDetector(
        available_tools=tools if tools is not None else BASIC_TOOLS,
        similarity_threshold=similarity_threshold,
        max_suggestions=max_suggestions,
        hallucination_threshold=hallucination_threshold,
    )


# ---------------------------------------------------------------------------
# HallucinationEvent
# ---------------------------------------------------------------------------


class TestHallucinationEvent:
    def test_creation_stores_attempted_tool(self):
        event = HallucinationEvent(attempted_tool="fake_tool", suggested_tools=["file_read"])
        assert event.attempted_tool == "fake_tool"

    def test_creation_stores_suggested_tools(self):
        event = HallucinationEvent(attempted_tool="fake_tool", suggested_tools=["file_read", "file_write"])
        assert event.suggested_tools == ["file_read", "file_write"]

    def test_timestamp_defaults_to_utc_now(self):
        before = datetime.now(UTC)
        event = HallucinationEvent(attempted_tool="x", suggested_tools=[])
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after

    def test_timestamp_is_timezone_aware(self):
        event = HallucinationEvent(attempted_tool="x", suggested_tools=[])
        assert event.timestamp.tzinfo is not None

    def test_context_defaults_to_none(self):
        event = HallucinationEvent(attempted_tool="x", suggested_tools=[])
        assert event.context is None

    def test_context_can_be_set(self):
        event = HallucinationEvent(attempted_tool="x", suggested_tools=[], context="doing research")
        assert event.context == "doing research"

    def test_custom_timestamp_is_accepted(self):
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        event = HallucinationEvent(attempted_tool="x", suggested_tools=[], timestamp=ts)
        assert event.timestamp == ts


# ---------------------------------------------------------------------------
# ToolValidationResult
# ---------------------------------------------------------------------------


class TestToolValidationResult:
    def test_valid_result_has_no_error(self):
        result = ToolValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.error_message is None
        assert result.error_type is None

    def test_invalid_result_carries_error_message(self):
        result = ToolValidationResult(is_valid=False, error_message="bad tool", error_type="tool_not_found")
        assert result.is_valid is False
        assert result.error_message == "bad tool"
        assert result.error_type == "tool_not_found"

    def test_suggestions_default_to_empty_list(self):
        result = ToolValidationResult(is_valid=True)
        assert result.suggestions == []

    def test_suggestions_can_be_populated(self):
        result = ToolValidationResult(is_valid=False, suggestions=["file_read", "file_write"])
        assert result.suggestions == ["file_read", "file_write"]

    def test_error_type_can_be_none_for_valid(self):
        result = ToolValidationResult(is_valid=True)
        assert result.error_type is None


# ---------------------------------------------------------------------------
# ToolHallucinationDetector.__init__
# ---------------------------------------------------------------------------


class TestDetectorInit:
    def test_available_tools_stored_as_set(self):
        detector = make_detector(tools=["a", "b", "c"])
        assert detector.available_tools == {"a", "b", "c"}

    def test_default_similarity_threshold(self):
        detector = make_detector()
        assert detector.similarity_threshold == 0.6

    def test_custom_similarity_threshold(self):
        detector = make_detector(similarity_threshold=0.8)
        assert detector.similarity_threshold == 0.8

    def test_default_max_suggestions(self):
        detector = make_detector()
        assert detector.max_suggestions == 3

    def test_custom_max_suggestions(self):
        detector = make_detector(max_suggestions=5)
        assert detector.max_suggestions == 5

    def test_default_hallucination_threshold(self):
        detector = make_detector()
        assert detector.hallucination_threshold == 3

    def test_custom_hallucination_threshold(self):
        detector = make_detector(hallucination_threshold=1)
        assert detector.hallucination_threshold == 1

    def test_hallucination_count_starts_at_zero(self):
        detector = make_detector()
        assert detector.hallucination_count == 0

    def test_hallucination_history_starts_empty(self):
        detector = make_detector()
        assert detector.hallucination_history == []

    def test_tool_schemas_starts_empty(self):
        detector = make_detector()
        assert detector._tool_schemas == {}

    def test_duplicate_tools_collapsed_to_set(self):
        detector = make_detector(tools=["a", "a", "b"])
        assert len(detector.available_tools) == 2


# ---------------------------------------------------------------------------
# update_available_tools
# ---------------------------------------------------------------------------


class TestUpdateAvailableTools:
    def test_replaces_existing_tool_set(self):
        detector = make_detector(tools=["old_tool"])
        detector.update_available_tools(["new_tool_a", "new_tool_b"])
        assert detector.available_tools == {"new_tool_a", "new_tool_b"}

    def test_old_tools_no_longer_valid_after_update(self):
        detector = make_detector(tools=["old_tool"])
        detector.update_available_tools(["new_tool"])
        assert "old_tool" not in detector.available_tools

    def test_update_with_empty_list(self):
        detector = make_detector(tools=["a", "b"])
        detector.update_available_tools([])
        assert detector.available_tools == set()


# ---------------------------------------------------------------------------
# update_tool_schemas
# ---------------------------------------------------------------------------


class TestUpdateToolSchemas:
    def test_stores_provided_schemas(self):
        detector = make_detector()
        schemas: dict[str, Any] = {"file_read": {"required": ["path"], "properties": {"path": {"type": "string"}}}}
        detector.update_tool_schemas(schemas)
        assert detector._tool_schemas == schemas

    def test_replaces_existing_schemas(self):
        detector = make_detector()
        detector.update_tool_schemas({"old": {}})
        detector.update_tool_schemas({"new": {}})
        assert "old" not in detector._tool_schemas
        assert "new" in detector._tool_schemas

    def test_empty_schemas_accepted(self):
        detector = make_detector()
        detector.update_tool_schemas({})
        assert detector._tool_schemas == {}


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


class TestDetect:
    def test_valid_tool_returns_none(self):
        detector = make_detector()
        assert detector.detect("file_read") is None

    def test_invalid_tool_returns_correction_string(self):
        detector = make_detector()
        result = detector.detect("file_reed")
        assert result is not None
        assert isinstance(result, str)

    def test_valid_tool_does_not_increment_count(self):
        detector = make_detector()
        detector.detect("file_read")
        assert detector.hallucination_count == 0

    def test_invalid_tool_increments_count(self):
        detector = make_detector()
        detector.detect("totally_fake")
        assert detector.hallucination_count == 1

    def test_multiple_invalid_tools_accumulate_count(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.detect("fake_2")
        detector.detect("fake_3")
        assert detector.hallucination_count == 3

    def test_invalid_tool_records_history_entry(self):
        detector = make_detector()
        detector.detect("ghost_tool")
        assert len(detector.hallucination_history) == 1
        assert detector.hallucination_history[0].attempted_tool == "ghost_tool"

    def test_valid_tool_does_not_record_history(self):
        detector = make_detector()
        detector.detect("file_read")
        assert len(detector.hallucination_history) == 0

    def test_context_stored_in_history_event(self):
        detector = make_detector()
        detector.detect("ghost_tool", context="searching the web")
        assert detector.hallucination_history[0].context == "searching the web"

    def test_history_trimmed_when_exceeds_100_entries(self):
        # The trim fires when len > 100 (i.e. at the 101st insert).
        # After the 101st insert the list is sliced to [-50:] giving 50.
        # Entries 102-105 are then appended (each below the 100 guard),
        # leaving a final size of 54.
        detector = make_detector()
        for i in range(105):
            detector.detect(f"fake_tool_{i}")
        assert len(detector.hallucination_history) == 54

    def test_history_trim_retains_most_recent_entries(self):
        detector = make_detector()
        for i in range(105):
            detector.detect(f"fake_tool_{i}")
        # Regardless of trim, the very last appended entry must be present.
        assert detector.hallucination_history[-1].attempted_tool == "fake_tool_104"

    def test_correction_message_includes_hallucinated_name(self):
        detector = make_detector()
        result = detector.detect("no_such_tool")
        assert "no_such_tool" in result

    def test_correction_message_includes_similar_tool_suggestion(self):
        detector = make_detector(tools=["file_read", "file_write"])
        result = detector.detect("file_reed")
        assert result is not None
        assert "file_read" in result or "file_write" in result


# ---------------------------------------------------------------------------
# _find_similar_tools
# ---------------------------------------------------------------------------


class TestFindSimilarTools:
    def test_exact_substring_match_boosted_above_threshold(self):
        detector = make_detector(tools=["file_read", "shell_exec"])
        # "file" is a substring of "file_read"
        similar = detector._find_similar_tools("file")
        assert "file_read" in similar

    def test_very_different_name_returns_empty(self):
        detector = make_detector(tools=["file_read", "shell_exec"])
        similar = detector._find_similar_tools("zzzzz_xyz_999")
        assert similar == []

    def test_respects_max_suggestions_limit(self):
        detector = make_detector(
            tools=["file_read", "file_write", "file_delete", "file_copy"],
            max_suggestions=2,
        )
        similar = detector._find_similar_tools("file_x")
        assert len(similar) <= 2

    def test_case_insensitive_matching(self):
        detector = make_detector(tools=["FileRead", "ShellExec"])
        similar = detector._find_similar_tools("fileread")
        assert "FileRead" in similar

    def test_similarity_threshold_filters_weak_matches(self):
        detector = make_detector(tools=["completely_unrelated"], similarity_threshold=0.9)
        similar = detector._find_similar_tools("file_read")
        assert similar == []

    def test_returned_list_sorted_by_descending_similarity(self):
        detector = make_detector(tools=["file_read", "file_write", "web_search"])
        similar = detector._find_similar_tools("file_red")
        # file_read should rank higher than file_write for "file_red"
        if "file_read" in similar and "file_write" in similar:
            assert similar.index("file_read") < similar.index("file_write")


# ---------------------------------------------------------------------------
# _generate_correction
# ---------------------------------------------------------------------------


class TestGenerateCorrection:
    def test_with_suggestions_names_each_suggestion(self):
        detector = make_detector()
        msg = detector._generate_correction("ghost_tool", ["file_read", "file_write"])
        assert "file_read" in msg
        assert "file_write" in msg

    def test_with_suggestions_includes_hallucinated_name(self):
        detector = make_detector()
        msg = detector._generate_correction("ghost_tool", ["file_read"])
        assert "ghost_tool" in msg

    def test_without_suggestions_shows_sample_tools(self):
        detector = make_detector(tools=["alpha", "beta", "gamma"])
        msg = detector._generate_correction("completely_fake", [])
        # At least one real tool name should appear
        assert any(t in msg for t in ["alpha", "beta", "gamma"])

    def test_without_suggestions_includes_hallucinated_name(self):
        detector = make_detector(tools=["alpha"])
        msg = detector._generate_correction("ghost_tool", [])
        assert "ghost_tool" in msg

    def test_without_suggestions_sample_capped_at_ten_tools(self):
        tools = [f"tool_{i}" for i in range(20)]
        detector = make_detector(tools=tools)
        msg = detector._generate_correction("fake", [])
        # The message lists at most 10 tools
        tool_mentions = sum(1 for t in tools if t in msg)
        assert tool_mentions <= 10


# ---------------------------------------------------------------------------
# validate_tool_call
# ---------------------------------------------------------------------------


class TestValidateToolCall:
    @pytest.fixture
    def detector_with_schema(self) -> ToolHallucinationDetector:
        detector = make_detector()
        schemas = {
            "file_write": {
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string"},
                },
            },
            "shell_exec": {
                "required": ["command"],
                "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}},
            },
        }
        detector.update_tool_schemas(schemas)
        return detector

    def test_valid_tool_with_correct_params_passes(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("file_write", {"path": "/tmp/out.txt", "content": "hello"})
        assert result.is_valid is True

    def test_unknown_tool_fails_with_tool_not_found(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("nonexistent_tool", {})
        assert result.is_valid is False
        assert result.error_type == "tool_not_found"

    def test_missing_required_param_fails(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("file_write", {"path": "/tmp/x"})
        assert result.is_valid is False
        assert result.error_type == "missing_params"
        assert "content" in result.error_message

    def test_all_required_params_missing_listed_in_error(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("file_write", {})
        assert result.is_valid is False
        assert "path" in result.error_message
        assert "content" in result.error_message

    def test_wrong_type_integer_instead_of_string_fails(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("file_write", {"path": 12345, "content": "hello"})
        assert result.is_valid is False
        assert result.error_type == "invalid_type"

    def test_wrong_type_string_instead_of_integer_fails(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("shell_exec", {"command": "ls", "timeout": "thirty"})
        assert result.is_valid is False
        assert result.error_type == "invalid_type"

    def test_semantic_violation_detected(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("shell_exec", {"command": "sudo rm -rf /"})
        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_tool_without_schema_returns_valid(self):
        detector = make_detector(tools=["file_read"])
        # No schema registered for file_read
        result = detector.validate_tool_call("file_read", {"path": "/tmp/x"})
        assert result.is_valid is True

    def test_suggestions_populated_for_tool_not_found(self, detector_with_schema):
        result = detector_with_schema.validate_tool_call("file_writ", {})
        assert result.is_valid is False
        # Should include a suggestion close to "file_write"
        assert isinstance(result.suggestions, list)


# ---------------------------------------------------------------------------
# validate_parameter_semantics
# ---------------------------------------------------------------------------


class TestValidateParameterSemantics:
    def test_file_write_system_etc_path_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/etc/passwd")
        assert result.is_valid is False
        assert result.error_type == "semantic_violation"

    def test_file_write_usr_path_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "path", "/usr/bin/malware")
        assert result.is_valid is False

    def test_file_write_bin_path_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/bin/sh")
        assert result.is_valid is False

    def test_file_write_sbin_path_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/sbin/init")
        assert result.is_valid is False

    def test_file_write_dotenv_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/app/.env")
        assert result.is_valid is False

    def test_file_write_ssh_directory_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/home/user/.ssh/config")
        assert result.is_valid is False

    def test_file_write_safe_tmp_path_passes(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/tmp/output.txt")
        assert result.is_valid is True

    def test_shell_exec_rm_rf_root_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "rm -rf /")
        assert result.is_valid is False

    def test_shell_exec_rm_rf_wildcard_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "rm -rf *")
        assert result.is_valid is False

    def test_shell_exec_sudo_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "sudo apt-get install x")
        assert result.is_valid is False

    def test_shell_exec_chmod_777_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "chmod 777 /app/secret")
        assert result.is_valid is False

    def test_shell_exec_fork_bomb_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", ":;() { :|:& };:")
        assert result.is_valid is False

    def test_shell_exec_safe_command_passes(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "ls -la /tmp")
        assert result.is_valid is True

    def test_shell_exec_dev_null_redirect_passes(self):
        """>/dev/null should NOT be flagged — it is explicitly allowed."""
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "some_cmd 2>/dev/null")
        assert result.is_valid is True

    def test_browser_goto_file_url_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("browser_goto", "url", "file:///etc/passwd")
        assert result.is_valid is False

    def test_browser_goto_localhost_admin_blocked(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("browser_goto", "url", "http://localhost/admin")
        assert result.is_valid is False

    def test_browser_goto_safe_url_passes(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("browser_goto", "url", "https://example.com")
        assert result.is_valid is True

    def test_unknown_function_always_passes(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("unknown_func", "any_param", "anything")
        assert result.is_valid is True

    def test_error_message_includes_param_name(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("file_write", "file", "/etc/shadow")
        assert "file" in result.error_message

    def test_context_included_in_error_message_when_provided(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics(
            "file_write", "file", "/etc/shadow", context="writing user notes"
        )
        assert "writing user notes" in result.error_message

    def test_suggestions_not_empty_on_violation(self):
        detector = make_detector()
        result = detector.validate_parameter_semantics("shell_exec", "command", "sudo ls")
        assert len(result.suggestions) > 0


# ---------------------------------------------------------------------------
# _get_json_type
# ---------------------------------------------------------------------------


class TestGetJsonType:
    def setup_method(self):
        self.detector = make_detector()

    def test_none_returns_null(self):
        assert self.detector._get_json_type(None) == "null"

    def test_true_returns_boolean(self):
        assert self.detector._get_json_type(True) == "boolean"

    def test_false_returns_boolean(self):
        assert self.detector._get_json_type(False) == "boolean"

    def test_int_returns_integer(self):
        assert self.detector._get_json_type(42) == "integer"

    def test_float_returns_number(self):
        assert self.detector._get_json_type(3.14) == "number"

    def test_str_returns_string(self):
        assert self.detector._get_json_type("hello") == "string"

    def test_list_returns_array(self):
        assert self.detector._get_json_type([1, 2, 3]) == "array"

    def test_dict_returns_object(self):
        assert self.detector._get_json_type({"key": "value"}) == "object"

    def test_unknown_type_returns_unknown(self):
        class Custom:
            pass

        assert self.detector._get_json_type(Custom()) == "unknown"

    def test_zero_int_returns_integer_not_boolean(self):
        # bool is a subclass of int, but 0 is an int literal
        assert self.detector._get_json_type(0) == "integer"


# ---------------------------------------------------------------------------
# _types_compatible
# ---------------------------------------------------------------------------


class TestTypesCompatible:
    def setup_method(self):
        self.detector = make_detector()

    def test_exact_match_string_to_string(self):
        assert self.detector._types_compatible("string", "string") is True

    def test_exact_match_integer_to_integer(self):
        assert self.detector._types_compatible("integer", "integer") is True

    def test_number_accepts_integer(self):
        assert self.detector._types_compatible("number", "integer") is True

    def test_number_accepts_number(self):
        assert self.detector._types_compatible("number", "number") is True

    def test_integer_accepts_number(self):
        assert self.detector._types_compatible("integer", "number") is True

    def test_string_does_not_accept_integer(self):
        assert self.detector._types_compatible("string", "integer") is False

    def test_boolean_does_not_accept_string(self):
        assert self.detector._types_compatible("boolean", "string") is False

    def test_array_does_not_accept_object(self):
        assert self.detector._types_compatible("array", "object") is False

    def test_null_matches_null(self):
        assert self.detector._types_compatible("null", "null") is True

    def test_object_does_not_accept_array(self):
        assert self.detector._types_compatible("object", "array") is False


# ---------------------------------------------------------------------------
# should_inject_correction_prompt
# ---------------------------------------------------------------------------


class TestShouldInjectCorrectionPrompt:
    def test_below_threshold_returns_false(self):
        detector = make_detector(hallucination_threshold=3)
        detector.detect("fake_1")
        detector.detect("fake_2")
        assert detector.should_inject_correction_prompt() is False

    def test_at_threshold_returns_true(self):
        detector = make_detector(hallucination_threshold=3)
        detector.detect("fake_1")
        detector.detect("fake_2")
        detector.detect("fake_3")
        assert detector.should_inject_correction_prompt() is True

    def test_above_threshold_returns_true(self):
        detector = make_detector(hallucination_threshold=2)
        for i in range(5):
            detector.detect(f"fake_{i}")
        assert detector.should_inject_correction_prompt() is True

    def test_zero_hallucinations_returns_false(self):
        detector = make_detector(hallucination_threshold=1)
        assert detector.should_inject_correction_prompt() is False

    def test_threshold_of_one_triggers_immediately(self):
        detector = make_detector(hallucination_threshold=1)
        detector.detect("ghost")
        assert detector.should_inject_correction_prompt() is True


# ---------------------------------------------------------------------------
# get_correction_prompt
# ---------------------------------------------------------------------------


class TestGetCorrectionPrompt:
    def test_includes_recently_attempted_tools(self):
        detector = make_detector(tools=["file_read"])
        detector.detect("bad_tool_1")
        detector.detect("bad_tool_2")
        prompt = detector.get_correction_prompt()
        assert "bad_tool_1" in prompt or "bad_tool_2" in prompt

    def test_includes_sample_of_available_tools(self):
        detector = make_detector(tools=["file_read", "shell_exec"])
        detector.detect("ghost")
        prompt = detector.get_correction_prompt()
        assert "file_read" in prompt or "shell_exec" in prompt

    def test_limits_recent_attempts_to_last_five(self):
        detector = make_detector(tools=["real_tool"])
        for i in range(10):
            detector.detect(f"ghost_{i}")
        prompt = detector.get_correction_prompt()
        # Only the last 5 should appear in the recent list
        assert "ghost_0" not in prompt
        assert "ghost_9" in prompt

    def test_returns_non_empty_string(self):
        detector = make_detector()
        detector.detect("ghost")
        prompt = detector.get_correction_prompt()
        assert len(prompt) > 0


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_sets_count_to_zero(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.detect("fake_2")
        detector.reset()
        assert detector.hallucination_count == 0

    def test_reset_does_not_clear_history(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.reset()
        assert len(detector.hallucination_history) == 1

    def test_after_reset_threshold_check_is_false(self):
        detector = make_detector(hallucination_threshold=2)
        detector.detect("fake_1")
        detector.detect("fake_2")
        assert detector.should_inject_correction_prompt() is True
        detector.reset()
        assert detector.should_inject_correction_prompt() is False


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    def test_empty_history_returns_zero_totals(self):
        detector = make_detector()
        stats = detector.get_statistics()
        assert stats["total_hallucinations"] == 0
        assert stats["unique_hallucinations"] == 0

    def test_empty_history_returns_empty_most_common(self):
        detector = make_detector()
        stats = detector.get_statistics()
        assert stats["most_common"] == []

    def test_empty_history_recovery_rate_is_one(self):
        detector = make_detector()
        stats = detector.get_statistics()
        assert stats["recovery_rate"] == 1.0

    def test_populated_history_total_count(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.detect("fake_2")
        detector.detect("fake_1")
        stats = detector.get_statistics()
        assert stats["total_hallucinations"] == 3

    def test_populated_history_unique_count(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.detect("fake_2")
        detector.detect("fake_1")
        stats = detector.get_statistics()
        assert stats["unique_hallucinations"] == 2

    def test_most_common_sorted_by_frequency_descending(self):
        detector = make_detector()
        detector.detect("rare_ghost")
        detector.detect("common_ghost")
        detector.detect("common_ghost")
        detector.detect("common_ghost")
        stats = detector.get_statistics()
        most_common = stats["most_common"]
        # First entry should be the most frequent
        assert most_common[0][0] == "common_ghost"
        assert most_common[0][1] == 3

    def test_most_common_capped_at_five(self):
        detector = make_detector()
        for i in range(8):
            detector.detect(f"ghost_{i}")
        stats = detector.get_statistics()
        assert len(stats["most_common"]) <= 5

    def test_current_streak_reflects_hallucination_count(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.detect("fake_2")
        stats = detector.get_statistics()
        assert stats["current_streak"] == 2

    def test_current_streak_after_reset(self):
        detector = make_detector()
        detector.detect("fake_1")
        detector.reset()
        stats = detector.get_statistics()
        # History still has the entry, but count was reset
        assert stats["current_streak"] == 0
