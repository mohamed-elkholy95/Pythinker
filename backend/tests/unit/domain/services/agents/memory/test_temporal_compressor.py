"""
Unit tests for TemporalCompressor and TemporalCompressionStats.

Covers:
- system/user messages always pass through regardless of position or length
- Messages already marked with _semantic_compacted pass through
- Messages already containing '(compacted)' / '(removed)' pass through
- Messages inside the recent window always pass through
- Tool messages: below tool_max_chars AND high importance → pass through
- Tool messages: above tool_max_chars OR low importance → temporal summary
- Assistant messages: below assistant_max_chars AND high importance → pass through
- Assistant messages: above assistant_max_chars OR low importance → truncated
- Stats tracking: compacted, tool_compacted, assistant_compacted counters
- Custom summary_builder called for tool messages
- Default summary builder: truncates at 160 chars, appends '...'
- _temporal_compacted flag set on compacted messages
- Original dict not mutated
- Empty message list → empty result with zero stats
- Custom max_chars configuration (tool_max_chars, assistant_max_chars)
- Custom importance_analyzer injection
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.memory.importance_analyzer import ImportanceAnalyzer
from app.domain.services.agents.memory.temporal_compressor import (
    TemporalCompressionStats,
    TemporalCompressor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
    return {"role": role, "content": content, **extra}


def _tool_msg(content: str) -> dict[str, Any]:
    return _msg("tool", content, function_name="some_tool")


def _assistant_msg(content: str) -> dict[str, Any]:
    return _msg("assistant", content)


def _user_msg(content: str) -> dict[str, Any]:
    return _msg("user", content)


def _system_msg(content: str) -> dict[str, Any]:
    return _msg("system", content)


# A stub analyzer that always deems messages low-importance (forces compaction paths)
class AlwaysLowImportanceAnalyzer(ImportanceAnalyzer):
    def score_message(self, message, index, total, preserve_recent=10):  # type: ignore[override]
        from app.domain.services.agents.memory.importance_analyzer import ImportanceScore

        return ImportanceScore(score=0.1, reasons=["forced_low"])

    @staticmethod
    def is_low_importance(score: float, threshold: float = 0.5) -> bool:  # type: ignore[override]
        return True


# A stub analyzer that always deems messages high-importance (prevents compaction)
class AlwaysHighImportanceAnalyzer(ImportanceAnalyzer):
    def score_message(self, message, index, total, preserve_recent=10):  # type: ignore[override]
        from app.domain.services.agents.memory.importance_analyzer import ImportanceScore

        return ImportanceScore(score=0.95, reasons=["forced_high"])

    @staticmethod
    def is_low_importance(score: float, threshold: float = 0.5) -> bool:  # type: ignore[override]
        return False


# ---------------------------------------------------------------------------
# TemporalCompressionStats dataclass
# ---------------------------------------------------------------------------


class TestTemporalCompressionStats:
    def test_defaults_are_zero(self):
        s = TemporalCompressionStats()
        assert s.compacted == 0
        assert s.tool_compacted == 0
        assert s.assistant_compacted == 0

    def test_fields_can_be_set(self):
        s = TemporalCompressionStats(compacted=5, tool_compacted=3, assistant_compacted=2)
        assert s.compacted == 5
        assert s.tool_compacted == 3
        assert s.assistant_compacted == 2


# ---------------------------------------------------------------------------
# TemporalCompressor initialisation
# ---------------------------------------------------------------------------


class TestTemporalCompressorInit:
    def test_default_summary_builder_assigned(self):
        tc = TemporalCompressor()
        assert tc._summary_builder is TemporalCompressor._default_summary

    def test_custom_summary_builder_stored(self):
        builder = lambda m: ("s", True)  # noqa: E731
        tc = TemporalCompressor(summary_builder=builder)
        assert tc._summary_builder is builder

    def test_default_tool_max_chars_is_800(self):
        tc = TemporalCompressor()
        assert tc._tool_max_chars == 800

    def test_default_assistant_max_chars_is_600(self):
        tc = TemporalCompressor()
        assert tc._assistant_max_chars == 600

    def test_custom_max_chars_stored(self):
        tc = TemporalCompressor(tool_max_chars=100, assistant_max_chars=50)
        assert tc._tool_max_chars == 100
        assert tc._assistant_max_chars == 50


# ---------------------------------------------------------------------------
# Messages always passed through (exempt from compression)
# ---------------------------------------------------------------------------


class TestExemptMessages:
    @pytest.fixture
    def tc(self) -> TemporalCompressor:
        return TemporalCompressor(tool_max_chars=1, assistant_max_chars=1)

    def test_system_message_passes_through_regardless_of_length(self, tc):
        msg = _system_msg("x" * 2000)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_user_message_passes_through_regardless_of_length(self, tc):
        msg = _user_msg("y" * 2000)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_message_with_semantic_compacted_flag_passes_through(self, tc):
        msg = _tool_msg("x" * 2000)
        msg["_semantic_compacted"] = True
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_message_with_compacted_marker_in_content_passes_through(self, tc):
        msg = _tool_msg("(compacted) previous summary here")
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_message_with_removed_marker_in_content_passes_through(self, tc):
        msg = _assistant_msg("(removed) content that was removed")
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_message_in_recent_window_passes_through(self, tc):
        """Even a long, low-importance tool message in the recent window is untouched."""
        msg = _tool_msg("x" * 2000)
        result, stats = tc.compress([msg], preserve_recent=1, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0


# ---------------------------------------------------------------------------
# Recent window boundary
# ---------------------------------------------------------------------------


class TestRecentWindowBoundary:
    @pytest.fixture
    def tc(self) -> TemporalCompressor:
        return TemporalCompressor(tool_max_chars=1)

    def test_message_at_boundary_index_is_in_recent_window(self, tc):
        """index == total - preserve_recent → in window → not compacted."""
        msgs = [_tool_msg("x" * 100) for _ in range(20)]
        # preserve_recent=5 → boundary at index 15
        result, stats = tc.compress(msgs, preserve_recent=5, importance_analyzer=AlwaysLowImportanceAnalyzer())
        # indices 0–14 (15 messages) are old → compacted
        # indices 15–19 (5 messages) are recent → pass through
        assert stats.compacted == 15

    def test_preserve_recent_larger_than_total_nothing_compacted(self, tc):
        msgs = [_tool_msg("x" * 100) for _ in range(5)]
        result, stats = tc.compress(msgs, preserve_recent=100, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 0

    def test_preserve_recent_zero_means_threshold_equals_total_nothing_recent(self, tc):
        """max(0, total - 0) = total → index < total always → nothing is recent."""
        msgs = [_tool_msg("a" * 100) for _ in range(3)]
        result, stats = tc.compress(msgs, preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 3


# ---------------------------------------------------------------------------
# Tool message compression
# ---------------------------------------------------------------------------


class TestToolMessageCompression:
    @pytest.fixture
    def tc(self) -> TemporalCompressor:
        return TemporalCompressor(tool_max_chars=100)

    def test_short_high_importance_tool_message_passes_through(self, tc):
        """content <= 100 AND high importance → no compaction."""
        msg = _tool_msg("short output")
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysHighImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_long_tool_message_is_compacted(self, tc):
        """content > 100 → always compacted (regardless of importance when using low analyzer)."""
        msg = _tool_msg("x" * 200)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 1
        assert stats.tool_compacted == 1

    def test_short_low_importance_tool_message_is_compacted(self, tc):
        """content <= 100 but low importance → compacted."""
        msg = _tool_msg("short")
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 1
        assert stats.tool_compacted == 1

    def test_compacted_tool_message_has_temporal_summary_in_content(self, tc):
        msg = _tool_msg("x" * 200)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        parsed = json.loads(result[0]["content"])
        assert "Temporal summary:" in parsed["data"]

    def test_compacted_tool_message_has_temporal_compacted_flag(self, tc):
        msg = _tool_msg("x" * 200)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0].get("_temporal_compacted") is True

    def test_tool_message_original_dict_not_mutated(self, tc):
        original = _tool_msg("x" * 200)
        tc.compress([original], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert "_temporal_compacted" not in original
        assert original["content"] == "x" * 200

    def test_tool_compacted_counter_incremented_correctly(self, tc):
        msgs = [_tool_msg("x" * 200) for _ in range(3)]
        _, stats = tc.compress(msgs, preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.tool_compacted == 3
        assert stats.assistant_compacted == 0
        assert stats.compacted == 3


# ---------------------------------------------------------------------------
# Assistant message compression
# ---------------------------------------------------------------------------


class TestAssistantMessageCompression:
    @pytest.fixture
    def tc(self) -> TemporalCompressor:
        return TemporalCompressor(assistant_max_chars=50)

    def test_short_high_importance_assistant_message_passes_through(self, tc):
        msg = _assistant_msg("short reply")
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysHighImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_long_assistant_message_is_truncated(self, tc):
        msg = _assistant_msg("a" * 200)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 1
        assert stats.assistant_compacted == 1

    def test_truncated_assistant_content_ends_with_context_optimization_tag(self, tc):
        msg = _assistant_msg("b" * 200)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0]["content"].endswith("[truncated for context optimization]")

    def test_truncated_content_respects_assistant_max_chars(self, tc):
        msg = _assistant_msg("c" * 200)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        # Should be at most 50 chars + "..." + " [truncated for context optimization]"
        content = result[0]["content"]
        prefix_end = content.index("[truncated for context optimization]")
        truncated_part = content[:prefix_end].strip()
        # The truncated part (before the tag) should be ≤ 53 chars (50 + "...")
        assert len(truncated_part) <= 53

    def test_truncated_assistant_has_temporal_compacted_flag(self, tc):
        msg = _assistant_msg("d" * 200)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0].get("_temporal_compacted") is True

    def test_assistant_original_dict_not_mutated(self, tc):
        original_content = "e" * 200
        original = _assistant_msg(original_content)
        tc.compress([original], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert original["content"] == original_content
        assert "_temporal_compacted" not in original

    def test_assistant_newlines_replaced_with_spaces_in_truncation(self, tc):
        msg = _assistant_msg("line1\nline2\n" * 10)
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        # The truncated content before the tag should have no newlines
        content = result[0]["content"]
        prefix = content.split("[truncated for context optimization]")[0]
        assert "\n" not in prefix

    def test_assistant_content_exactly_at_max_chars_not_truncated(self):
        tc = TemporalCompressor(assistant_max_chars=20)
        msg = _assistant_msg("x" * 20)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        # Length == max_chars, NOT > max_chars → no "..." appended
        assert stats.compacted == 1  # low importance still triggers compaction
        content = result[0]["content"]
        assert not content.startswith("x" * 20 + "...")

    def test_assistant_compacted_counter_incremented_correctly(self, tc):
        msgs = [_assistant_msg("f" * 200) for _ in range(4)]
        _, stats = tc.compress(msgs, preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.assistant_compacted == 4
        assert stats.tool_compacted == 0
        assert stats.compacted == 4


# ---------------------------------------------------------------------------
# Mixed message types
# ---------------------------------------------------------------------------


class TestMixedMessageTypes:
    def test_mixed_messages_correct_stats(self):
        tc = TemporalCompressor(tool_max_chars=10, assistant_max_chars=10)
        msgs = [
            _system_msg("sys prompt"),          # exempt
            _user_msg("user query"),             # exempt
            _tool_msg("x" * 100),               # compacted → tool_compacted
            _assistant_msg("a" * 100),           # compacted → assistant_compacted
            _tool_msg("y" * 5),                  # short, but low importance → compacted
        ]
        _, stats = tc.compress(msgs, preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert stats.compacted == 3
        assert stats.tool_compacted == 2
        assert stats.assistant_compacted == 1

    def test_output_length_always_equals_input_length(self):
        tc = TemporalCompressor(tool_max_chars=1, assistant_max_chars=1)
        msgs = [
            _system_msg("sys"),
            _user_msg("hi"),
            _tool_msg("x" * 100),
            _assistant_msg("y" * 100),
        ]
        result, _ = tc.compress(msgs, preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert len(result) == len(msgs)


# ---------------------------------------------------------------------------
# Custom summary builder
# ---------------------------------------------------------------------------


class TestCustomSummaryBuilderTemporal:
    def test_custom_builder_called_for_compacted_tool_message(self):
        call_log: list[dict] = []

        def builder(msg: dict) -> tuple[str, bool]:
            call_log.append(msg)
            return ("custom temporal summary", True)

        tc = TemporalCompressor(summary_builder=builder, tool_max_chars=1)
        msg = _tool_msg("some tool output here")
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert len(call_log) == 1
        parsed = json.loads(result[0]["content"])
        assert "custom temporal summary" in parsed["data"]

    def test_custom_builder_success_false_propagates_in_tool_result(self):
        tc = TemporalCompressor(summary_builder=lambda m: ("err", False), tool_max_chars=1)
        msg = _tool_msg("some output data")
        result, _ = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        parsed = json.loads(result[0]["content"])
        assert parsed["success"] is False


# ---------------------------------------------------------------------------
# Default summary builder
# ---------------------------------------------------------------------------


class TestDefaultSummaryBuilderTemporal:
    def test_short_content_not_truncated(self):
        msg = _tool_msg("hello world")
        summary, success = TemporalCompressor._default_summary(msg)
        assert summary == "hello world"
        assert success is True

    def test_content_at_exactly_160_chars_not_truncated(self):
        msg = _tool_msg("z" * 160)
        summary, _ = TemporalCompressor._default_summary(msg)
        assert summary == "z" * 160
        assert not summary.endswith("...")

    def test_content_longer_than_160_truncated_with_ellipsis(self):
        msg = _tool_msg("a" * 300)
        summary, _ = TemporalCompressor._default_summary(msg)
        assert summary.endswith("...")
        assert len(summary) <= 163  # 160 + "..."

    def test_newlines_replaced_with_spaces(self):
        msg = _tool_msg("line1\nline2\nline3")
        summary, _ = TemporalCompressor._default_summary(msg)
        assert "\n" not in summary

    def test_empty_content_returns_empty_string(self):
        msg = _tool_msg("")
        summary, success = TemporalCompressor._default_summary(msg)
        assert summary == ""
        assert success is True


# ---------------------------------------------------------------------------
# Unknown roles
# ---------------------------------------------------------------------------


class TestUnknownRoleMessages:
    def test_unknown_role_passes_through_unchanged(self):
        """Messages with roles not in system/user/tool/assistant pass through."""
        tc = TemporalCompressor(tool_max_chars=1, assistant_max_chars=1)
        msg = _msg("function", "some content x" * 100)
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysLowImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestTemporalCompressorEdgeCases:
    @pytest.fixture
    def tc(self) -> TemporalCompressor:
        return TemporalCompressor()

    def test_empty_list_returns_empty_with_zero_stats(self, tc):
        result, stats = tc.compress([], preserve_recent=10)
        assert result == []
        assert stats.compacted == 0
        assert stats.tool_compacted == 0
        assert stats.assistant_compacted == 0

    def test_single_system_message_untouched(self, tc):
        msg = _system_msg("System instruction set")
        result, stats = tc.compress([msg], preserve_recent=0)
        assert result == [msg]
        assert stats.compacted == 0

    def test_default_analyzer_created_when_none_provided(self, tc):
        """When no importance_analyzer is passed, the default ImportanceAnalyzer is used."""
        msg = _tool_msg("x" * 10)  # short content, score=0.3 < 0.6 threshold → compacted
        result, stats = tc.compress([msg], preserve_recent=0)
        # With default analyzer: tool, score=0.3, threshold=0.6 → low importance → compacted
        assert stats.compacted == 1

    def test_none_content_coerced_to_string_safely(self, tc):
        msg = {"role": "tool", "content": None}
        # content="None" which is 4 chars, well below default tool_max_chars=800
        result, stats = tc.compress([msg], preserve_recent=0, importance_analyzer=AlwaysHighImportanceAnalyzer())
        assert result[0] is msg
        assert stats.compacted == 0

    def test_very_long_tool_message_compressed_to_summary(self, tc):
        msg = _tool_msg("huge content " * 1000)
        result, stats = tc.compress([msg], preserve_recent=0)
        assert stats.compacted == 1
        parsed = json.loads(result[0]["content"])
        assert "Temporal summary:" in parsed["data"]
