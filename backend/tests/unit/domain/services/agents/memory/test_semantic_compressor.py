"""
Unit tests for SemanticCompressor and SemanticCompressionStats.

Covers:
- Non-tool messages are always passed through unchanged
- Tool messages within the recent window are always passed through unchanged
- High-importance tool messages (score >= 0.5) are passed through
- First occurrence of a fingerprint is stored, not compacted
- Duplicate fingerprints are compacted and stats incremented
- Already-compacted messages ('(compacted)' / '(removed)' markers) are skipped
- Custom summary_builder is called correctly
- Default summary builder: truncates at 140 chars, appends '...'
- Fingerprint normalization: digits stripped, whitespace collapsed, function_name prefix
- stats.compacted and stats.duplicates are accurate
- Empty message list returns empty list with zero stats
- preserve_recent=0 means the "recent window" covers all messages (threshold=total)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.memory.importance_analyzer import ImportanceAnalyzer
from app.domain.services.agents.memory.semantic_compressor import (
    SemanticCompressionStats,
    SemanticCompressor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_msg(content: str, function_name: str = "search") -> dict[str, Any]:
    return {"role": "tool", "content": content, "function_name": function_name}


def _user_msg(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def _assistant_msg(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _system_msg(content: str) -> dict[str, Any]:
    return {"role": "system", "content": content}


# ---------------------------------------------------------------------------
# SemanticCompressionStats dataclass
# ---------------------------------------------------------------------------


class TestSemanticCompressionStats:
    def test_defaults_are_zero(self):
        s = SemanticCompressionStats()
        assert s.compacted == 0
        assert s.duplicates == 0

    def test_fields_can_be_set(self):
        s = SemanticCompressionStats(compacted=3, duplicates=2)
        assert s.compacted == 3
        assert s.duplicates == 2


# ---------------------------------------------------------------------------
# SemanticCompressor initialisation
# ---------------------------------------------------------------------------


class TestSemanticCompressorInit:
    def test_default_summary_builder_used_when_none_provided(self):
        compressor = SemanticCompressor()
        assert compressor._summary_builder is SemanticCompressor._default_summary

    def test_custom_summary_builder_is_stored(self):
        builder = lambda msg: ("custom", True)  # noqa: E731
        compressor = SemanticCompressor(summary_builder=builder)
        assert compressor._summary_builder is builder


# ---------------------------------------------------------------------------
# Non-tool messages are passed through unchanged
# ---------------------------------------------------------------------------


class TestNonToolMessagesPassThrough:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_user_message_always_passes_through(self, compressor):
        msgs = [_user_msg("hello")]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert result == msgs
        assert stats.compacted == 0

    def test_assistant_message_always_passes_through(self, compressor):
        msgs = [_assistant_msg("I will help.")]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert result == msgs
        assert stats.compacted == 0

    def test_system_message_always_passes_through(self, compressor):
        msgs = [_system_msg("Be a helpful assistant.")]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert result == msgs
        assert stats.compacted == 0

    def test_mixed_non_tool_messages_all_pass_through(self, compressor):
        msgs = [
            _system_msg("Instructions"),
            _user_msg("What is 2+2?"),
            _assistant_msg("It is 4."),
        ]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert result == msgs
        assert stats.compacted == 0


# ---------------------------------------------------------------------------
# Tool messages in the recent window are always passed through
# ---------------------------------------------------------------------------


class TestToolMessagesInRecentWindow:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_single_tool_message_with_preserve_recent_1_passes_through(self, compressor):
        """With total=1 and preserve_recent=1, index 0 is recent → pass through."""
        msgs = [_tool_msg("output A")]
        result, stats = compressor.compress(msgs, preserve_recent=1)
        assert result == msgs
        assert stats.compacted == 0

    def test_last_n_tool_messages_in_window_not_compacted(self, compressor):
        """10 identical tool messages with preserve_recent=10 → no compaction."""
        msgs = [_tool_msg("same output") for _ in range(10)]
        result, stats = compressor.compress(msgs, preserve_recent=10)
        assert len(result) == 10
        assert stats.compacted == 0

    def test_tool_message_at_exact_boundary_passes_through(self, compressor):
        """index == total - preserve_recent is within the recent window."""
        msgs = [_tool_msg("output") for _ in range(20)]
        # index 15 is the boundary (20 - 5 = 15)
        result, stats = compressor.compress(msgs, preserve_recent=5)
        # Indices 15–19 are recent: 5 messages pass through without compaction check.
        # Indices 0–14 (15 messages) are old, but since they're all identical,
        # the first one stores the fingerprint and all subsequent ones are duplicates.
        # First occurrence at index 0 → not compacted; 1–14 → compacted (14 duplicates)
        assert stats.duplicates == 14


# ---------------------------------------------------------------------------
# First occurrence of a fingerprint is NOT compacted
# ---------------------------------------------------------------------------


class TestFirstOccurrenceNotCompacted:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_unique_tool_message_not_compacted(self, compressor):
        msgs = [_tool_msg("unique output for this call")]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert result[0]["content"] == "unique output for this call"
        assert stats.compacted == 0

    def test_two_different_outputs_both_preserved(self, compressor):
        msgs = [
            _tool_msg("result: item A from search"),
            _tool_msg("result: item B from search"),
        ]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        # After digit stripping: "result: item a from search" vs "result: item b from search"
        # These are different fingerprints → both preserved
        assert stats.compacted == 0
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Duplicate detection and compaction
# ---------------------------------------------------------------------------


class TestDuplicateCompaction:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_duplicate_tool_message_is_compacted(self, compressor):
        msgs = [
            _tool_msg("search result page: item A"),
            _tool_msg("search result page: item A"),  # identical → duplicate
        ]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert stats.compacted == 1
        assert stats.duplicates == 1

    def test_compacted_message_has_duplicate_suppressed_text(self, compressor):
        msgs = [
            _tool_msg("search result page: item A"),
            _tool_msg("search result page: item A"),
        ]
        result, _ = compressor.compress(msgs, preserve_recent=0)
        # Second message is compacted; parse its content as ToolResult JSON
        compacted_content = json.loads(result[1]["content"])
        assert "Duplicate tool output suppressed" in compacted_content["data"]

    def test_compacted_message_has_semantic_compacted_flag(self, compressor):
        msgs = [
            _tool_msg("same content here abc"),
            _tool_msg("same content here abc"),
        ]
        result, _ = compressor.compress(msgs, preserve_recent=0)
        assert result[1].get("_semantic_compacted") is True

    def test_three_duplicates_compacts_two(self, compressor):
        msgs = [_tool_msg("repeated output") for _ in range(3)]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert stats.compacted == 2
        assert stats.duplicates == 2

    def test_original_message_dict_not_mutated(self, compressor):
        original = _tool_msg("original content abc")
        duplicate = _tool_msg("original content abc")
        compressor.compress([original, duplicate], preserve_recent=0)
        # The original dict should not have been mutated
        assert "_semantic_compacted" not in original

    def test_function_name_differentiates_fingerprints(self, compressor):
        """Same content but different function_name → different fingerprint → not duplicate."""
        msgs = [
            {"role": "tool", "content": "same output", "function_name": "search"},
            {"role": "tool", "content": "same output", "function_name": "browser"},
        ]
        result, stats = compressor.compress(msgs, preserve_recent=0)
        assert stats.compacted == 0


# ---------------------------------------------------------------------------
# Already-compacted messages are skipped
# ---------------------------------------------------------------------------


class TestAlreadyCompactedMessages:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_message_with_compacted_marker_passes_through(self, compressor):
        msg = _tool_msg("(compacted) previous output was here")
        result, stats = compressor.compress([msg], preserve_recent=0)
        assert result == [msg]
        assert stats.compacted == 0

    def test_message_with_removed_marker_passes_through(self, compressor):
        msg = _tool_msg("(removed) old content")
        result, stats = compressor.compress([msg], preserve_recent=0)
        assert result == [msg]
        assert stats.compacted == 0

    def test_already_compacted_then_duplicate_only_compacts_duplicate(self, compressor):
        """If the first message has '(compacted)', the second identical one should
        still be compared against stored fingerprints. Since '(compacted)' messages
        are skipped entirely (not stored in seen), second also passes through."""
        msg_compacted = _tool_msg("(compacted) some search result data")
        msg_fresh = _tool_msg("some search result data")
        result, stats = compressor.compress([msg_compacted, msg_fresh], preserve_recent=0)
        # msg_compacted is skipped → fingerprint never stored → msg_fresh is first → not duplicate
        assert stats.compacted == 0


# ---------------------------------------------------------------------------
# Custom summary builder
# ---------------------------------------------------------------------------


class TestCustomSummaryBuilder:
    def test_custom_builder_is_called_on_duplicate(self):
        call_log: list[dict] = []

        def builder(msg: dict) -> tuple[str, bool]:
            call_log.append(msg)
            return ("custom summary text", False)

        compressor = SemanticCompressor(summary_builder=builder)
        msgs = [
            _tool_msg("duplicate content xyz"),
            _tool_msg("duplicate content xyz"),
        ]
        result, _ = compressor.compress(msgs, preserve_recent=0)
        assert len(call_log) == 1  # called once for the duplicate
        # Verify custom summary appears in output
        parsed = json.loads(result[1]["content"])
        assert "custom summary text" in parsed["data"]

    def test_custom_builder_success_false_propagates(self):
        compressor = SemanticCompressor(summary_builder=lambda m: ("err summary", False))
        msgs = [_tool_msg("same abc"), _tool_msg("same abc")]
        result, _ = compressor.compress(msgs, preserve_recent=0)
        parsed = json.loads(result[1]["content"])
        assert parsed["success"] is False


# ---------------------------------------------------------------------------
# Default summary builder
# ---------------------------------------------------------------------------


class TestDefaultSummaryBuilder:
    def test_short_content_not_truncated(self):
        msg = _tool_msg("short output")
        summary, success = SemanticCompressor._default_summary(msg)
        assert summary == "short output"
        assert success is True

    def test_content_at_exactly_140_chars_not_truncated(self):
        msg = _tool_msg("x" * 140)
        summary, _ = SemanticCompressor._default_summary(msg)
        assert summary == "x" * 140
        assert not summary.endswith("...")

    def test_content_longer_than_140_chars_truncated_with_ellipsis(self):
        msg = _tool_msg("a" * 200)
        summary, _ = SemanticCompressor._default_summary(msg)
        assert summary.endswith("...")
        assert len(summary) <= 143  # 140 chars + "..."

    def test_newlines_replaced_with_spaces(self):
        msg = _tool_msg("line1\nline2\nline3")
        summary, _ = SemanticCompressor._default_summary(msg)
        assert "\n" not in summary

    def test_empty_content_returns_empty_summary(self):
        msg = _tool_msg("")
        summary, success = SemanticCompressor._default_summary(msg)
        assert summary == ""
        assert success is True


# ---------------------------------------------------------------------------
# Fingerprint normalization
# ---------------------------------------------------------------------------


class TestFingerprintNormalization:
    def test_digits_stripped_from_fingerprint(self):
        """Messages differing only in numeric parts share the same fingerprint."""
        msg_a = {"role": "tool", "content": "Found 10 results on page 1", "function_name": "search"}
        msg_b = {"role": "tool", "content": "Found 20 results on page 2", "function_name": "search"}
        fp_a = SemanticCompressor._fingerprint(msg_a)
        fp_b = SemanticCompressor._fingerprint(msg_b)
        assert fp_a == fp_b

    def test_whitespace_collapsed_in_fingerprint(self):
        msg_a = {"role": "tool", "content": "some   content  here", "function_name": "tool"}
        msg_b = {"role": "tool", "content": "some content here", "function_name": "tool"}
        assert SemanticCompressor._fingerprint(msg_a) == SemanticCompressor._fingerprint(msg_b)

    def test_function_name_prefixed_in_fingerprint(self):
        msg_a = {"role": "tool", "content": "abc", "function_name": "alpha"}
        msg_b = {"role": "tool", "content": "abc", "function_name": "beta"}
        assert SemanticCompressor._fingerprint(msg_a) != SemanticCompressor._fingerprint(msg_b)

    def test_fingerprint_case_insensitive(self):
        msg_a = {"role": "tool", "content": "OUTPUT DATA", "function_name": "f"}
        msg_b = {"role": "tool", "content": "output data", "function_name": "f"}
        assert SemanticCompressor._fingerprint(msg_a) == SemanticCompressor._fingerprint(msg_b)

    def test_missing_function_name_defaults_to_tool(self):
        msg = {"role": "tool", "content": "result"}
        fp = SemanticCompressor._fingerprint(msg)
        assert fp.startswith("tool:")

    def test_fingerprint_truncated_to_200_content_chars(self):
        long_content = "a" * 300
        msg = {"role": "tool", "content": long_content, "function_name": "f"}
        fp = SemanticCompressor._fingerprint(msg)
        # prefix "f:" + 200 chars
        assert len(fp) == 2 + 200


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestSemanticCompressorEdgeCases:
    @pytest.fixture
    def compressor(self) -> SemanticCompressor:
        return SemanticCompressor()

    def test_empty_message_list_returns_empty_with_zero_stats(self, compressor):
        result, stats = compressor.compress([], preserve_recent=10)
        assert result == []
        assert stats.compacted == 0
        assert stats.duplicates == 0

    def test_preserve_recent_larger_than_total_all_messages_pass_through(self, compressor):
        msgs = [_tool_msg("same") for _ in range(5)]
        result, stats = compressor.compress(msgs, preserve_recent=100)
        assert len(result) == 5
        assert stats.compacted == 0

    def test_custom_importance_analyzer_used_when_provided(self, compressor):
        """Provide an analyzer that always returns high importance → no compaction."""
        msgs = [_tool_msg("data xyz"), _tool_msg("data xyz")]
        custom_analyzer = ImportanceAnalyzer()
        # Patch is_low_importance to always return False (high importance)
        custom_analyzer.is_low_importance = lambda score, threshold=0.5: False  # type: ignore[method-assign]
        result, stats = compressor.compress(msgs, preserve_recent=0, importance_analyzer=custom_analyzer)
        assert stats.compacted == 0

    def test_output_length_equals_input_length(self, compressor):
        """SemanticCompressor never removes messages, only replaces content."""
        msgs = [_tool_msg("val abc")] * 5
        result, _ = compressor.compress(msgs, preserve_recent=0)
        assert len(result) == len(msgs)

    def test_low_importance_tool_message_not_in_window_not_compacted_if_unique(self, compressor):
        """A low-importance tool message that's the first occurrence is stored, not compacted."""
        msg = _tool_msg("a" * 10)  # short, low importance (score=0.3 < 0.5)
        result, stats = compressor.compress([msg], preserve_recent=0)
        assert stats.compacted == 0
        assert result[0] is msg
