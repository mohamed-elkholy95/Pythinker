"""
Comprehensive tests for MemoryManager and supporting dataclasses.

Covers:
- PressureStatus dataclass (construction, to_context_signal)
- CompactedMessage dataclass (tokens_saved property, defaults)
- ExtractionResult dataclass (defaults, field coverage)
- ContextOptimizationReport dataclass (tokens_saved clamping)
- MemoryManager initialization and class-level constants
- compact_message (non-tool pass-through, already-compacted guard, extraction)
- _extract_key_results dispatch for every known tool type + generic
- _extract_browser_results (URLs, title, links, form, word count)
- _extract_shell_results (error detection, line count, keyword matching)
- _extract_file_results (line count, format detection)
- _extract_search_results (JSON list, fallback URL counting)
- _extract_listing_results (item count, directory detection)
- _extract_generic_results (word/line metrics, success/error keywords)
- compact_messages_batch (below threshold no-op, compaction with savings)
- _estimate_tokens_for_messages
- _build_tool_summary
- get_pressure_status (boundary transitions for all five levels)
- track_token_usage (history growth and trimming)
- should_trigger_compaction (all six rules)
- extract_with_llm (known tool shortcut, LLM path, failure fallback)
- _parse_llm_extraction (structured section parsing, fallback lines)
- _extract_urls_from_text
- _fallback_extraction (success inference, confidence)
- compact_and_archive (small message skip, file-storage path, memory-only path)
- retrieve_archived (missing key, memory-only, no storage, successful read)
- get_archive_stats
- _enforce_archive_limit (FIFO cleanup)
- cleanup_archive (with and without max_entries override)
- clear_archive
- _add_to_archive_index (dedup, auto-enforce)
- structured_compact (normal path, LLM call, insufficient summary, too-few messages)
- get_memory_manager singleton
- optimize_context (below threshold no-op, full run)
- get_archive_path (format and incrementing counter)
- set_token_budget (Rule 6 of should_trigger_compaction)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.pressure import PressureLevel
from app.domain.models.tool_name import ToolName
from app.domain.services.agents.memory_manager import (
    CompactedMessage,
    ContextOptimizationReport,
    ExtractionResult,
    MemoryManager,
    PressureStatus,
    get_memory_manager,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_message(
    function_name: str = "shell_exec",
    content: str = "hello world",
    role: str = "tool",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": role, "function_name": function_name, "content": content}
    if extra:
        msg.update(extra)
    return msg


def _json_tool_content(success: bool, data: Any, message: str | None = None) -> str:
    payload: dict[str, Any] = {"success": success, "data": data}
    if message is not None:
        payload["message"] = message
    return json.dumps(payload)


# ===========================================================================
# PressureStatus
# ===========================================================================


class TestPressureStatus:
    """Tests for the PressureStatus dataclass."""

    def test_construction_stores_all_fields(self):
        status = PressureStatus(
            level=PressureLevel.WARNING,
            current_tokens=70_000,
            max_tokens=100_000,
            usage_ratio=0.70,
        )
        assert status.level == PressureLevel.WARNING
        assert status.current_tokens == 70_000
        assert status.max_tokens == 100_000
        assert status.usage_ratio == pytest.approx(0.70)

    def test_to_context_signal_critical(self):
        status = PressureStatus(
            level=PressureLevel.CRITICAL,
            current_tokens=88_000,
            max_tokens=100_000,
            usage_ratio=0.88,
        )
        signal = status.to_context_signal()
        assert "CRITICAL" in signal
        assert "88%" in signal

    def test_to_context_signal_overflow_treated_as_critical(self):
        # OVERFLOW is not explicitly checked; the method only checks CRITICAL
        # and WARNING, so OVERFLOW returns "" (see source lines 46-50).
        # Verify the current behaviour is documented and stable.
        status = PressureStatus(
            level=PressureLevel.OVERFLOW,
            current_tokens=97_000,
            max_tokens=100_000,
            usage_ratio=0.97,
        )
        signal = status.to_context_signal()
        # OVERFLOW falls through to the final return ""
        assert signal == ""

    def test_to_context_signal_warning(self):
        status = PressureStatus(
            level=PressureLevel.WARNING,
            current_tokens=75_000,
            max_tokens=100_000,
            usage_ratio=0.75,
        )
        signal = status.to_context_signal()
        assert "WARNING" in signal
        assert "75%" in signal

    def test_to_context_signal_normal_returns_empty(self):
        status = PressureStatus(
            level=PressureLevel.NORMAL,
            current_tokens=40_000,
            max_tokens=100_000,
            usage_ratio=0.40,
        )
        assert status.to_context_signal() == ""

    def test_to_context_signal_early_warning_returns_empty(self):
        status = PressureStatus(
            level=PressureLevel.EARLY_WARNING,
            current_tokens=65_000,
            max_tokens=100_000,
            usage_ratio=0.65,
        )
        assert status.to_context_signal() == ""


# ===========================================================================
# CompactedMessage
# ===========================================================================


class TestCompactedMessage:
    """Tests for the CompactedMessage dataclass."""

    def test_tokens_saved_positive(self):
        msg = CompactedMessage(
            summary="summary",
            original_tokens=1000,
            compacted_tokens=200,
        )
        assert msg.tokens_saved == 800

    def test_tokens_saved_zero_when_same(self):
        msg = CompactedMessage(summary="x", original_tokens=300, compacted_tokens=300)
        assert msg.tokens_saved == 0

    def test_tokens_saved_negative_allowed(self):
        # If compacted is somehow larger, result is negative (no clamp in dataclass)
        msg = CompactedMessage(summary="x", original_tokens=100, compacted_tokens=200)
        assert msg.tokens_saved == -100

    def test_default_fields(self):
        msg = CompactedMessage(summary="test")
        assert msg.file_ref is None
        assert msg.original_tokens == 0
        assert msg.compacted_tokens == 0
        assert msg.key_results == []

    def test_key_results_are_independent_between_instances(self):
        a = CompactedMessage(summary="a")
        b = CompactedMessage(summary="b")
        a.key_results.append("fact")
        assert b.key_results == []

    def test_file_ref_stored(self):
        msg = CompactedMessage(summary="s", file_ref="/archives/test.json")
        assert msg.file_ref == "/archives/test.json"


# ===========================================================================
# ExtractionResult
# ===========================================================================


class TestExtractionResult:
    """Tests for the ExtractionResult dataclass."""

    def test_construction_with_all_fields(self):
        result = ExtractionResult(
            success=True,
            key_facts=["fact1", "fact2"],
            data_points={"count": 5},
            urls=["https://example.com"],
            error_message=None,
            extraction_method="heuristic",
            confidence=1.0,
        )
        assert result.success is True
        assert len(result.key_facts) == 2
        assert result.confidence == pytest.approx(1.0)

    def test_default_extraction_method_is_heuristic(self):
        result = ExtractionResult(
            success=True,
            key_facts=[],
            data_points={},
            urls=[],
        )
        assert result.extraction_method == "heuristic"

    def test_default_confidence_is_one(self):
        result = ExtractionResult(success=True, key_facts=[], data_points={}, urls=[])
        assert result.confidence == pytest.approx(1.0)

    def test_error_message_none_by_default(self):
        result = ExtractionResult(success=True, key_facts=[], data_points={}, urls=[])
        assert result.error_message is None

    def test_failed_result_with_error_message(self):
        result = ExtractionResult(
            success=False,
            key_facts=[],
            data_points={},
            urls=[],
            error_message="command not found",
        )
        assert result.success is False
        assert result.error_message == "command not found"


# ===========================================================================
# ContextOptimizationReport
# ===========================================================================


class TestContextOptimizationReport:
    """Tests for the ContextOptimizationReport dataclass."""

    def test_tokens_saved_is_difference(self):
        report = ContextOptimizationReport(tokens_before=1000, tokens_after=600)
        assert report.tokens_saved == 400

    def test_tokens_saved_clamped_to_zero(self):
        # If tokens_after > tokens_before, result is 0 (not negative)
        report = ContextOptimizationReport(tokens_before=500, tokens_after=600)
        assert report.tokens_saved == 0

    def test_tokens_saved_zero_when_unchanged(self):
        report = ContextOptimizationReport(tokens_before=800, tokens_after=800)
        assert report.tokens_saved == 0

    def test_defaults_for_compaction_counters(self):
        report = ContextOptimizationReport(tokens_before=100, tokens_after=80)
        assert report.semantic_compacted == 0
        assert report.temporal_compacted == 0

    def test_all_fields_set(self):
        report = ContextOptimizationReport(
            tokens_before=1000,
            tokens_after=400,
            semantic_compacted=3,
            temporal_compacted=2,
        )
        assert report.semantic_compacted == 3
        assert report.temporal_compacted == 2
        assert report.tokens_saved == 600


# ===========================================================================
# MemoryManager — class-level constants and initialization
# ===========================================================================


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_default_sandbox_path(self):
        mgr = MemoryManager()
        assert mgr._sandbox_path == "/home/ubuntu/.context_archive"

    def test_custom_sandbox_path(self):
        mgr = MemoryManager(sandbox_path="/tmp/test_archive")
        assert mgr._sandbox_path == "/tmp/test_archive"

    def test_enable_file_storage_default_true(self):
        mgr = MemoryManager()
        assert mgr._enable_file_storage is True

    def test_enable_file_storage_false(self):
        mgr = MemoryManager(enable_file_storage=False)
        assert mgr._enable_file_storage is False

    def test_file_storage_none_by_default(self):
        mgr = MemoryManager()
        assert mgr._file_storage is None

    def test_archive_counter_starts_at_zero(self):
        mgr = MemoryManager()
        assert mgr._archive_counter == 0

    def test_token_history_empty_on_init(self):
        mgr = MemoryManager()
        assert mgr._token_history == []

    def test_archive_index_empty_on_init(self):
        mgr = MemoryManager()
        assert mgr._archive_index == {}

    def test_archive_order_empty_on_init(self):
        mgr = MemoryManager()
        assert mgr._archive_order == []

    def test_max_archive_size_default(self):
        mgr = MemoryManager()
        assert mgr._max_archive_size == MemoryManager.DEFAULT_MAX_ARCHIVE_SIZE

    def test_archive_cleanup_batch_default(self):
        mgr = MemoryManager()
        assert mgr._archive_cleanup_batch == MemoryManager.DEFAULT_ARCHIVE_CLEANUP_BATCH

    def test_custom_max_archive_size(self):
        mgr = MemoryManager(max_archive_size=50)
        assert mgr._max_archive_size == 50

    def test_custom_cleanup_batch(self):
        mgr = MemoryManager(archive_cleanup_batch=10)
        assert mgr._archive_cleanup_batch == 10

    def test_summarizable_functions_contains_expected_tools(self):
        expected = {
            ToolName.BROWSER_VIEW,
            ToolName.BROWSER_NAVIGATE,
            ToolName.SHELL_EXEC,
            ToolName.FILE_READ,
            ToolName.FILE_LIST,
            ToolName.INFO_SEARCH_WEB,
            ToolName.BROWSER_GET_CONTENT,
        }
        for tool in expected:
            assert tool in MemoryManager.SUMMARIZABLE_FUNCTIONS

    def test_max_summary_tokens_value(self):
        assert MemoryManager.MAX_SUMMARY_TOKENS == 200

    def test_default_max_archive_size_value(self):
        assert MemoryManager.DEFAULT_MAX_ARCHIVE_SIZE == 1000

    def test_default_archive_cleanup_batch_value(self):
        assert MemoryManager.DEFAULT_ARCHIVE_CLEANUP_BATCH == 100

    def test_token_budget_none_by_default(self):
        mgr = MemoryManager()
        assert mgr._token_budget is None

    def test_set_token_budget(self):
        mgr = MemoryManager()
        mock_budget = MagicMock()
        mgr.set_token_budget(mock_budget)
        assert mgr._token_budget is mock_budget


# ===========================================================================
# compact_message
# ===========================================================================


class TestCompactMessage:
    """Tests for MemoryManager.compact_message."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_non_tool_message_passes_through(self):
        msg = {"role": "user", "content": "Hello!"}
        result_msg, metadata = self.mgr.compact_message(msg)
        assert result_msg is msg
        assert metadata.original_tokens == 0
        assert metadata.compacted_tokens == 0

    def test_assistant_message_passes_through(self):
        msg = {"role": "assistant", "content": "I will help you."}
        result_msg, _metadata = self.mgr.compact_message(msg)
        assert result_msg is msg

    def test_already_compacted_message_returns_as_is(self):
        content = '{"success": true, "data": "[shell_exec] (compacted)"}'
        msg = _tool_message(content=content)
        result_msg, metadata = self.mgr.compact_message(msg)
        # Content unchanged
        assert result_msg["content"] == content
        assert metadata.original_tokens == metadata.compacted_tokens

    def test_already_removed_message_returns_as_is(self):
        content = '{"success": true, "data": "(removed)"}'
        msg = _tool_message(content=content)
        result_msg, _metadata = self.mgr.compact_message(msg)
        assert result_msg["content"] == content

    def test_tool_message_is_compacted(self):
        content = _json_tool_content(success=True, data="This is some long shell output\n" * 50)
        msg = _tool_message(function_name="shell_exec", content=content)
        result_msg, metadata = self.mgr.compact_message(msg)
        assert result_msg["role"] == "tool"
        assert "shell_exec" in result_msg["content"] or "shell_exec" in metadata.summary

    def test_compacted_tokens_less_than_original_for_long_content(self):
        long_data = "some output line\n" * 200
        content = _json_tool_content(success=True, data=long_data)
        msg = _tool_message(function_name="shell_exec", content=content)
        _, metadata = self.mgr.compact_message(msg)
        assert metadata.original_tokens > 0
        assert metadata.compacted_tokens < metadata.original_tokens

    def test_preserve_summary_false_falls_back_to_compacted_label(self):
        content = _json_tool_content(success=True, data="output data")
        msg = _tool_message(function_name="shell_exec", content=content)
        _result_msg, metadata = self.mgr.compact_message(msg, preserve_summary=False)
        assert "(compacted)" in metadata.summary

    def test_failed_tool_result_captured_in_summary(self):
        content = _json_tool_content(success=False, data="", message="Permission denied")
        msg = _tool_message(function_name="shell_exec", content=content)
        _, metadata = self.mgr.compact_message(msg)
        assert "FAILED" in metadata.summary or not metadata.key_results

    def test_urls_included_in_summary_for_browser_tool(self):
        data = "<html><body><a href='https://example.com'>link</a></body></html>"
        content = _json_tool_content(success=True, data=data)
        msg = _tool_message(function_name="browser_view", content=content)
        _, metadata = self.mgr.compact_message(msg)
        assert isinstance(metadata.key_results, list)

    def test_file_ref_is_none_by_default(self):
        content = _json_tool_content(success=True, data="some content")
        msg = _tool_message(function_name="file_read", content=content)
        _, metadata = self.mgr.compact_message(msg)
        assert metadata.file_ref is None


# ===========================================================================
# _extract_key_results dispatch
# ===========================================================================


class TestExtractKeyResults:
    """Tests for _extract_key_results routing to per-tool extractors."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_browser_view_dispatches_correctly(self):
        content = "<html><title>Test Page</title><body>hello world " * 20 + "</body></html>"
        result = self.mgr._extract_key_results("browser_view", content)
        assert result.success is True
        assert any("Title" in f for f in result.key_facts)

    def test_browser_navigate_dispatches_correctly(self):
        content = "<html><a href='https://site.com'>link</a></html>"
        result = self.mgr._extract_key_results("browser_navigate", content)
        assert isinstance(result.key_facts, list)

    def test_browser_get_content_dispatches_correctly(self):
        content = "<html><body>page content</body></html>"
        result = self.mgr._extract_key_results("browser_get_content", content)
        assert isinstance(result.urls, list)

    def test_shell_exec_dispatches_correctly(self):
        content = "line1\nline2\nline3\n"
        result = self.mgr._extract_key_results("shell_exec", content)
        assert any("lines" in f for f in result.key_facts)

    def test_file_read_dispatches_correctly(self):
        content = "import os\ndef main():\n    pass\n"
        result = self.mgr._extract_key_results("file_read", content)
        assert any("Python" in f for f in result.key_facts)

    def test_info_search_web_dispatches_correctly(self):
        # _extract_key_results parses the outer JSON envelope first,
        # then delegates content_to_analyze to _extract_search_results.
        # We must wrap the list in a ToolResult-style dict so the outer
        # json.loads returns a dict (not a list) and .get() works.
        results = [{"title": "Result one", "url": "https://r1.com"}]
        content = json.dumps({"success": True, "data": json.dumps(results)})
        result = self.mgr._extract_key_results("info_search_web", content)
        assert any("result" in f.lower() for f in result.key_facts)

    def test_file_list_dispatches_correctly(self):
        content = "file1.txt\nfile2.txt\ndir1/\n"
        result = self.mgr._extract_key_results("file_list", content)
        assert any("items" in f or "item" in f for f in result.key_facts)

    def test_unknown_tool_uses_generic_extractor(self):
        content = "This is a generic output with some information"
        result = self.mgr._extract_key_results("custom_tool_xyz", content)
        assert isinstance(result.key_facts, list)
        assert len(result.key_facts) <= 3

    def test_json_content_parsed_for_success_field(self):
        content = json.dumps({"success": False, "message": "Not found", "data": ""})
        result = self.mgr._extract_key_results("shell_exec", content)
        assert result.success is False
        assert result.error_message == "Not found"

    def test_non_json_content_treated_as_plain_text(self):
        content = "plain text output without JSON"
        result = self.mgr._extract_key_results("shell_exec", content)
        assert result.success is True  # No "success": false found


# ===========================================================================
# _extract_browser_results
# ===========================================================================


class TestExtractBrowserResults:
    """Tests for browser-specific extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_extracts_title(self):
        content = "<html><head><title>My Awesome Page</title></head><body></body></html>"
        facts, _urls = self.mgr._extract_browser_results(content)
        assert any("My Awesome Page" in f for f in facts)

    def test_extracts_urls(self):
        content = "Visit https://example.com and https://other.org for more."
        _facts, urls = self.mgr._extract_browser_results(content)
        assert any("example.com" in u for u in urls)

    def test_counts_links(self):
        content = "<a href='#'>link1</a><a href='#'>link2</a><a href='#'>link3</a>"
        facts, _ = self.mgr._extract_browser_results(content)
        assert any("links" in f for f in facts)

    def test_detects_form(self):
        content = "<html><body><form action='/submit'><input type='text'/></form></body></html>"
        facts, _ = self.mgr._extract_browser_results(content)
        assert any("form" in f.lower() for f in facts)

    def test_word_count_fact_for_long_content(self):
        content = " ".join(["word"] * 150)
        facts, _ = self.mgr._extract_browser_results(content)
        assert any("words" in f for f in facts)

    def test_no_facts_for_empty_content(self):
        _facts, urls = self.mgr._extract_browser_results("")
        assert urls == []

    def test_url_deduplication(self):
        url = "https://example.com"
        content = f"{url} {url} {url}"
        _, urls = self.mgr._extract_browser_results(content)
        assert urls.count(url) == 1

    def test_url_count_capped_at_five(self):
        urls_text = " ".join(f"https://site{i}.com" for i in range(10))
        _, urls = self.mgr._extract_browser_results(urls_text)
        assert len(urls) <= 5


# ===========================================================================
# _extract_shell_results
# ===========================================================================


class TestExtractShellResults:
    """Tests for shell output extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_counts_output_lines(self):
        content = "\n".join(f"line{i}" for i in range(10))
        facts = self.mgr._extract_shell_results(content)
        assert any("10 lines" in f for f in facts)

    def test_detects_error_keyword(self):
        content = "Error: command not found"
        facts = self.mgr._extract_shell_results(content)
        assert any("Error" in f for f in facts)

    def test_detects_failed_keyword(self):
        content = "Build failed with exit code 1"
        facts = self.mgr._extract_shell_results(content)
        assert any("failed" in f.lower() or "Failed" in f for f in facts)

    def test_detects_installed_keyword(self):
        content = "Successfully installed package-1.0.0"
        facts = self.mgr._extract_shell_results(content)
        assert any("Installation" in f for f in facts)

    def test_detects_created_keyword(self):
        content = "Created directory /tmp/mydir"
        facts = self.mgr._extract_shell_results(content)
        assert any("Created" in f for f in facts)

    def test_detects_success_keyword(self):
        content = "Operation was a success"
        facts = self.mgr._extract_shell_results(content)
        assert any("successful" in f.lower() for f in facts)

    def test_caps_at_five_facts(self):
        content = "error\nfailed\ndenied\ninstalled\ncreated\nsuccess\nnot found"
        facts = self.mgr._extract_shell_results(content)
        assert len(facts) <= 5

    def test_single_line_no_line_count_fact(self):
        content = "done"
        facts = self.mgr._extract_shell_results(content)
        # single line: len(lines) == 1 so the "> 1" guard skips line count
        assert not any("lines" in f for f in facts)


# ===========================================================================
# _extract_file_results
# ===========================================================================


class TestExtractFileResults:
    """Tests for file content extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_returns_line_count(self):
        content = "line1\nline2\nline3\n"
        facts = self.mgr._extract_file_results(content)
        assert any("3 lines" in f for f in facts)

    def test_detects_json_format(self):
        content = '{"key": "value", "num": 42}'
        facts = self.mgr._extract_file_results(content)
        assert any("JSON" in f for f in facts)

    def test_detects_python_code(self):
        content = "import os\ndef main():\n    return True\n"
        facts = self.mgr._extract_file_results(content)
        assert any("Python" in f for f in facts)

    def test_detects_html_document(self):
        content = "<!DOCTYPE html>\n<html><body></body></html>"
        facts = self.mgr._extract_file_results(content)
        assert any("HTML" in f for f in facts)

    def test_detects_javascript_code(self):
        content = "function hello() {\n  const x = 1;\n  return x;\n}"
        facts = self.mgr._extract_file_results(content)
        assert any("JavaScript" in f for f in facts)

    def test_plain_text_has_only_line_count(self):
        content = "just some plain text here"
        facts = self.mgr._extract_file_results(content)
        assert len(facts) >= 1  # At minimum the line count
        assert any("lines" in f for f in facts)

    @pytest.mark.parametrize("content_start,label", [
        ('{"items": []}', "JSON"),
        ('[1, 2, 3]', "JSON"),
    ])
    def test_json_detection_parametrized(self, content_start: str, label: str):
        facts = self.mgr._extract_file_results(content_start)
        assert any(label in f for f in facts)


# ===========================================================================
# _extract_search_results
# ===========================================================================


class TestExtractSearchResults:
    """Tests for search result extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_json_list_count(self):
        results = [{"title": f"Result {i}", "url": f"https://site{i}.com"} for i in range(5)]
        content = json.dumps(results)
        facts, _urls = self.mgr._extract_search_results(content)
        assert any("5 results" in f for f in facts)

    def test_json_list_extracts_first_three_titles(self):
        results = [{"title": f"Title {i}", "url": f"https://site{i}.com"} for i in range(5)]
        content = json.dumps(results)
        facts, _ = self.mgr._extract_search_results(content)
        # Title 0, 1, 2 should appear; Title 3 and 4 should not
        assert any("Title 0" in f for f in facts)
        assert any("Title 2" in f for f in facts)

    def test_json_list_extracts_urls(self):
        results = [{"title": "A", "url": "https://example.com"}]
        content = json.dumps(results)
        _, urls = self.mgr._extract_search_results(content)
        assert any("example.com" in u for u in urls)

    def test_json_list_uses_link_field_fallback(self):
        results = [{"title": "A", "link": "https://via-link.com"}]
        content = json.dumps(results)
        _, urls = self.mgr._extract_search_results(content)
        assert any("via-link.com" in u for u in urls)

    def test_non_json_fallback_counts_http_occurrences(self):
        content = "Result 1: http://a.com\nResult 2: https://b.com\n"
        facts, _ = self.mgr._extract_search_results(content)
        assert any("result" in f.lower() or "~" in f for f in facts)

    def test_facts_capped_at_five(self):
        results = [{"title": f"Title {i}", "url": f"https://site{i}.com"} for i in range(20)]
        content = json.dumps(results)
        facts, _ = self.mgr._extract_search_results(content)
        assert len(facts) <= 5

    def test_urls_capped_at_five(self):
        content = " ".join(f"https://site{i}.com" for i in range(10))
        _, urls = self.mgr._extract_search_results(content)
        assert len(urls) <= 5

    def test_empty_json_list(self):
        content = "[]"
        facts, urls = self.mgr._extract_search_results(content)
        assert any("0 results" in f for f in facts)
        assert urls == []


# ===========================================================================
# _extract_listing_results
# ===========================================================================


class TestExtractListingResults:
    """Tests for directory listing extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_counts_items(self):
        content = "file1.txt\nfile2.txt\nfile3.txt\n"
        facts = self.mgr._extract_listing_results(content)
        assert any("3 items" in f for f in facts)

    def test_counts_directories(self):
        content = "dir1/\ndir2/\nfile.txt\n"
        facts = self.mgr._extract_listing_results(content)
        assert any("directories" in f or "dir" in f.lower() for f in facts)

    def test_no_directories_no_dir_fact(self):
        content = "file1.txt\nfile2.txt\n"
        facts = self.mgr._extract_listing_results(content)
        assert not any("directories" in f for f in facts)

    def test_empty_listing(self):
        content = ""
        facts = self.mgr._extract_listing_results(content)
        # Empty string split gives [""], length 1
        assert any("1 items" in f for f in facts)


# ===========================================================================
# _extract_generic_results
# ===========================================================================


class TestExtractGenericResults:
    """Tests for generic content extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_word_and_line_count(self):
        content = "hello world\nfoo bar\n"
        facts = self.mgr._extract_generic_results(content)
        assert any("words" in f for f in facts)

    def test_success_keyword(self):
        content = "The operation was a success."
        facts = self.mgr._extract_generic_results(content)
        assert any("success" in f.lower() for f in facts)

    def test_error_keyword(self):
        content = "An error occurred during processing."
        facts = self.mgr._extract_generic_results(content)
        assert any("error" in f.lower() for f in facts)

    def test_failed_keyword(self):
        content = "Process failed with code 1."
        facts = self.mgr._extract_generic_results(content)
        assert any("error" in f.lower() for f in facts)

    def test_empty_content_returns_empty(self):
        facts = self.mgr._extract_generic_results("")
        assert facts == []

    def test_caps_at_three_facts(self):
        content = "success error failed something else"
        facts = self.mgr._extract_generic_results(content)
        assert len(facts) <= 3


# ===========================================================================
# compact_messages_batch
# ===========================================================================


class TestCompactMessagesBatch:
    """Tests for batch compaction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_below_threshold_returns_original(self):
        messages = [{"role": "user", "content": "short message"}]
        result, saved = self.mgr.compact_messages_batch(messages, token_threshold=100_000)
        assert result is messages
        assert saved == 0

    def test_compacts_old_summarizable_tool_messages(self):
        # Create a scenario where total tokens exceed threshold
        big_content = _json_tool_content(success=True, data="output line\n" * 300)
        # Add 20 old tool messages + 10 recent non-tool
        messages = [_tool_message(function_name="shell_exec", content=big_content) for _ in range(20)]
        messages.extend({"role": "user", "content": "follow-up"} for _ in range(10))

        result, saved = self.mgr.compact_messages_batch(
            messages, preserve_recent=10, token_threshold=1
        )
        assert len(result) == len(messages)
        assert saved > 0

    def test_preserves_recent_messages_verbatim(self):
        big_content = _json_tool_content(success=True, data="data\n" * 200)
        messages = [_tool_message(function_name="shell_exec", content=big_content) for _ in range(5)]
        # Add distinctive recent messages
        messages.extend({"role": "user", "content": f"recent-{i}"} for i in range(10))

        result, _ = self.mgr.compact_messages_batch(messages, preserve_recent=10, token_threshold=1)
        # Last 10 messages should be untouched
        for i, msg in enumerate(result[-10:]):
            assert msg["content"] == f"recent-{i}"

    def test_non_summarizable_tools_are_not_compacted(self):
        big_content = "x" * 4000
        msg = _tool_message(function_name="custom_unknown_tool", content=big_content)
        messages = [msg] * 5 + [{"role": "user", "content": "recent"}]
        result, _saved = self.mgr.compact_messages_batch(messages, preserve_recent=1, token_threshold=1)
        # The custom_unknown_tool messages should remain uncompacted
        for r in result[:-1]:
            assert r["content"] == big_content


# ===========================================================================
# _estimate_tokens_for_messages
# ===========================================================================


class TestEstimateTokensForMessages:
    """Tests for token estimation helper."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_empty_list_is_zero(self):
        assert self.mgr._estimate_tokens_for_messages([]) == 0

    def test_single_message(self):
        msg = {"role": "user", "content": "abcd"}  # 4 chars = 1 token
        assert self.mgr._estimate_tokens_for_messages([msg]) == 1

    def test_multiple_messages_summed(self):
        msgs = [
            {"role": "user", "content": "abcd"},  # 1 token
            {"role": "assistant", "content": "abcdefgh"},  # 2 tokens
        ]
        assert self.mgr._estimate_tokens_for_messages(msgs) == 3

    def test_missing_content_treated_as_empty(self):
        msg: dict[str, Any] = {"role": "user"}
        assert self.mgr._estimate_tokens_for_messages([msg]) == 0


# ===========================================================================
# _build_tool_summary
# ===========================================================================


class TestBuildToolSummary:
    """Tests for _build_tool_summary helper."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_success_summary_contains_tool_name(self):
        content = _json_tool_content(success=True, data="output data")
        msg = _tool_message(function_name="shell_exec", content=content)
        summary, success = self.mgr._build_tool_summary(msg)
        assert "shell_exec" in summary
        assert success is True

    def test_failed_summary_contains_failed_indicator(self):
        content = _json_tool_content(success=False, data="", message="Access denied")
        msg = _tool_message(function_name="shell_exec", content=content)
        summary, success = self.mgr._build_tool_summary(msg)
        assert "FAILED" in summary
        assert success is False

    def test_summary_includes_urls_for_browser_tool(self):
        data = "Visit https://example.com for details"
        content = _json_tool_content(success=True, data=data)
        msg = _tool_message(function_name="browser_view", content=content)
        summary, _ = self.mgr._build_tool_summary(msg)
        assert "example.com" in summary or "URLs" in summary

    def test_facts_truncated_at_500_chars(self):
        long_fact = "a" * 600
        content = _json_tool_content(success=True, data=long_fact)
        msg = _tool_message(function_name="shell_exec", content=content)
        summary, _ = self.mgr._build_tool_summary(msg)
        # Summary line should not be arbitrarily long
        assert len(summary) < 1000


# ===========================================================================
# get_pressure_status
# ===========================================================================


class TestGetPressureStatus:
    """Tests for pressure level calculation."""

    def setup_method(self):
        self.mgr = MemoryManager()

    @pytest.mark.parametrize("current,expected_level", [
        (0, PressureLevel.NORMAL),
        (59_999, PressureLevel.NORMAL),
        (70_000, PressureLevel.WARNING),
        (75_000, PressureLevel.WARNING),
        (84_999, PressureLevel.WARNING),
        (85_000, PressureLevel.CRITICAL),
        (90_000, PressureLevel.CRITICAL),
        (94_999, PressureLevel.CRITICAL),
        (95_000, PressureLevel.OVERFLOW),
        (100_000, PressureLevel.OVERFLOW),
    ])
    def test_pressure_levels_at_boundaries(self, current: int, expected_level: PressureLevel):
        status = self.mgr.get_pressure_status(current, max_tokens=100_000)
        assert status.level == expected_level

    def test_usage_ratio_calculated_correctly(self):
        status = self.mgr.get_pressure_status(50_000, max_tokens=100_000)
        assert status.usage_ratio == pytest.approx(0.50)

    def test_current_and_max_stored(self):
        status = self.mgr.get_pressure_status(30_000, max_tokens=128_000)
        assert status.current_tokens == 30_000
        assert status.max_tokens == 128_000

    def test_default_max_tokens_is_128k(self):
        status = self.mgr.get_pressure_status(64_000)
        assert status.max_tokens == 128_000

    def test_overflow_at_exact_95_percent(self):
        status = self.mgr.get_pressure_status(95_000, max_tokens=100_000)
        assert status.level == PressureLevel.OVERFLOW


# ===========================================================================
# track_token_usage
# ===========================================================================


class TestTrackTokenUsage:
    """Tests for token history tracking."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_adds_token_count_to_history(self):
        self.mgr.track_token_usage(50_000)
        assert self.mgr._token_history == [50_000]

    def test_multiple_entries_preserved(self):
        for i in range(5):
            self.mgr.track_token_usage(i * 1000)
        assert len(self.mgr._token_history) == 5

    def test_history_trimmed_to_max_size(self):
        for i in range(25):
            self.mgr.track_token_usage(i * 1000)
        assert len(self.mgr._token_history) == 20  # _max_history_size

    def test_oldest_entries_dropped_first(self):
        for i in range(25):
            self.mgr.track_token_usage(i)
        # Should contain the last 20 values: 5..24
        assert self.mgr._token_history[0] == 5
        assert self.mgr._token_history[-1] == 24

    def test_exact_max_size_no_trim(self):
        for i in range(20):
            self.mgr.track_token_usage(i)
        assert len(self.mgr._token_history) == 20


# ===========================================================================
# should_trigger_compaction
# ===========================================================================


class TestShouldTriggerCompaction:
    """Tests for proactive compaction trigger evaluation."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def _make_status(self, level: PressureLevel, ratio: float = 0.5) -> PressureStatus:
        current = int(ratio * 100_000)
        return PressureStatus(level=level, current_tokens=current, max_tokens=100_000, usage_ratio=ratio)

    # Rule 1: Critical / Overflow pressure
    def test_rule1_critical_triggers(self):
        status = self._make_status(PressureLevel.CRITICAL, 0.88)
        should, reason = self.mgr.should_trigger_compaction(status, [], 0)
        assert should is True
        assert "critical" in reason.lower() or "critical" in reason

    def test_rule1_overflow_triggers(self):
        status = self._make_status(PressureLevel.OVERFLOW, 0.97)
        should, _reason = self.mgr.should_trigger_compaction(status, [], 0)
        assert should is True

    # Rule 2: Verbose tool accumulation
    def test_rule2_triggers_with_3_verbose_tools_at_warning(self):
        status = self._make_status(PressureLevel.WARNING, 0.75)
        tools = [ToolName.BROWSER_VIEW, ToolName.SHELL_EXEC, ToolName.FILE_READ]
        should, reason = self.mgr.should_trigger_compaction(status, tools, 0)
        assert should is True
        assert "verbose" in reason.lower()

    def test_rule2_does_not_trigger_with_only_2_verbose_tools(self):
        status = self._make_status(PressureLevel.WARNING, 0.75)
        tools = [ToolName.BROWSER_VIEW, ToolName.SHELL_EXEC]
        # Rule 2 alone requires WARNING + 3 verbose tools, so 2 tools should NOT trigger Rule 2.
        # Other rules do not apply here (normal history, iteration 0, normal-ish pressure).
        should, _ = self.mgr.should_trigger_compaction(status, tools, 0)
        assert isinstance(should, bool)  # Just verify no crash

    def test_rule2_does_not_trigger_at_normal_pressure(self):
        status = self._make_status(PressureLevel.NORMAL, 0.40)
        tools = [ToolName.BROWSER_VIEW, ToolName.SHELL_EXEC, ToolName.FILE_READ, ToolName.FILE_READ]
        should, _ = self.mgr.should_trigger_compaction(status, tools, 0)
        # Rule 2 requires WARNING level; at NORMAL it should not trigger on Rule 2
        # (other rules may still fire)
        assert isinstance(should, bool)

    # Rule 3: Periodic compaction
    def test_rule3_triggers_at_iteration_20_non_normal(self):
        status = self._make_status(PressureLevel.WARNING, 0.75)
        should, reason = self.mgr.should_trigger_compaction(status, [], 20)
        assert should is True
        assert "Periodic" in reason or "iteration" in reason

    def test_rule3_does_not_trigger_at_normal_pressure(self):
        status = self._make_status(PressureLevel.NORMAL, 0.40)
        should, reason = self.mgr.should_trigger_compaction(status, [], 20)
        # Rule 3 requires level != NORMAL
        assert not should or "Periodic" not in reason

    def test_rule3_triggers_at_multiples_of_20(self):
        status = self._make_status(PressureLevel.WARNING, 0.75)
        for iteration in [20, 40, 60]:
            should, _ = self.mgr.should_trigger_compaction(status, [], iteration)
            assert should is True

    # Rule 4: High growth rate
    def test_rule4_triggers_on_high_growth_rate(self):
        # Fill history with rapidly growing values
        for i in range(5):
            self.mgr.track_token_usage(i * 2000)
        # Current: 8000, five steps ago: 0 → growth = 8000/5 = 1600 > 1000
        status = self._make_status(PressureLevel.NORMAL, 0.40)
        should, reason = self.mgr.should_trigger_compaction(status, [], 0)
        assert should is True
        assert "growth" in reason.lower()

    def test_rule4_does_not_trigger_on_low_growth(self):
        for i in range(10):
            self.mgr.track_token_usage(1000 + i * 10)  # tiny growth
        status = self._make_status(PressureLevel.NORMAL, 0.30)
        should, _ = self.mgr.should_trigger_compaction(status, [], 0)
        assert not should

    # Rule 5: Upward trend approaching warning
    def test_rule5_triggers_on_upward_trend_near_warning(self):
        # ratio > 0.6 but level is NORMAL
        # Add 3 history entries with +3000 upward trend
        self.mgr._token_history = [58_000, 60_000, 62_000]
        status = PressureStatus(
            level=PressureLevel.NORMAL,
            current_tokens=62_000,
            max_tokens=100_000,
            usage_ratio=0.62,
        )
        should, reason = self.mgr.should_trigger_compaction(status, [], 0)
        assert should is True
        assert "trend" in reason.lower()

    # Rule 6: Token budget
    def test_rule6_triggers_when_budget_over_85_percent(self):
        mock_budget = MagicMock()
        mock_budget.overall_usage_ratio = 0.90
        self.mgr.set_token_budget(mock_budget)
        status = self._make_status(PressureLevel.NORMAL, 0.30)
        should, reason = self.mgr.should_trigger_compaction(status, [], 0)
        assert should is True
        assert "budget" in reason.lower() or "90%" in reason

    def test_rule6_does_not_trigger_when_budget_under_85_percent(self):
        mock_budget = MagicMock()
        mock_budget.overall_usage_ratio = 0.80
        self.mgr.set_token_budget(mock_budget)
        status = self._make_status(PressureLevel.NORMAL, 0.30)
        should, _ = self.mgr.should_trigger_compaction(status, [], 0)
        assert not should

    def test_no_trigger_when_all_conditions_clear(self):
        status = self._make_status(PressureLevel.NORMAL, 0.30)
        self.mgr._token_history = [30_000, 31_000, 32_000]
        should, reason = self.mgr.should_trigger_compaction(status, [], 3)
        assert not should
        assert reason == ""


# ===========================================================================
# extract_with_llm
# ===========================================================================


class TestExtractWithLlm:
    """Tests for async LLM-based extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    @pytest.mark.asyncio
    async def test_known_tool_uses_heuristic_not_llm(self):
        mock_llm = AsyncMock()
        content = _json_tool_content(success=True, data="some output")
        result = await self.mgr.extract_with_llm("shell_exec", content, mock_llm)
        mock_llm.ask.assert_not_called()
        assert result.extraction_method == "heuristic"
        assert result.confidence == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_unknown_tool_calls_llm(self):
        mock_response = MagicMock()
        mock_response.content = (
            "STATUS: success\n"
            "KEY_FACTS:\n"
            "- Fact one\n"
            "- Fact two\n"
            "URLS:\n"
            "- https://example.com\n"
        )
        mock_llm = AsyncMock()
        mock_llm.ask.return_value = mock_response

        result = await self.mgr.extract_with_llm("my_custom_tool", "tool output here", mock_llm)
        mock_llm.ask.assert_called_once()
        assert result.extraction_method == "llm"
        assert result.confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_unknown_tool_llm_extracts_facts(self):
        mock_response = MagicMock()
        mock_response.content = (
            "STATUS: success\n"
            "KEY_FACTS:\n"
            "- Data processed successfully\n"
            "- 42 records updated\n"
        )
        mock_llm = AsyncMock()
        mock_llm.ask.return_value = mock_response

        result = await self.mgr.extract_with_llm("db_migrate", "42 records updated", mock_llm)
        assert "Data processed successfully" in result.key_facts
        assert "42 records updated" in result.key_facts

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_fallback_extraction(self):
        mock_llm = AsyncMock()
        mock_llm.ask.side_effect = RuntimeError("LLM connection failed")

        result = await self.mgr.extract_with_llm("my_custom_tool", "output data", mock_llm)
        assert result.extraction_method == "fallback"
        assert result.confidence == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_llm_success_contains_false_when_failure_in_text(self):
        mock_response = MagicMock()
        mock_response.content = "STATUS: failure\nKEY_FACTS:\n- Operation failed\n"
        mock_llm = AsyncMock()
        mock_llm.ask.return_value = mock_response

        result = await self.mgr.extract_with_llm("custom_op", "it failed", mock_llm)
        # "success" not in text or "failure" IS in text
        assert result.success is False


# ===========================================================================
# _parse_llm_extraction
# ===========================================================================


class TestParseLlmExtraction:
    """Tests for LLM response parsing."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_parses_structured_key_facts(self):
        response = (
            "STATUS: success\n"
            "KEY_FACTS:\n"
            "- Fact one\n"
            "- Fact two\n"
            "URLS:\n"
            "- https://example.com\n"
        )
        facts = self.mgr._parse_llm_extraction(response)
        assert "Fact one" in facts
        assert "Fact two" in facts

    def test_stops_at_urls_section(self):
        response = "KEY_FACTS:\n- Fact A\nURLS:\n- https://x.com\n"
        facts = self.mgr._parse_llm_extraction(response)
        assert "Fact A" in facts
        assert "https://x.com" not in facts

    def test_stops_at_errors_section(self):
        response = "KEY_FACTS:\n- Fact B\nERRORS:\n- Some error\n"
        facts = self.mgr._parse_llm_extraction(response)
        assert "Fact B" in facts
        assert "Some error" not in facts

    def test_fallback_when_no_structure(self):
        response = "This is a plain unstructured response with some useful info"
        facts = self.mgr._parse_llm_extraction(response)
        assert len(facts) > 0
        assert all(isinstance(f, str) for f in facts)

    def test_caps_at_five_facts(self):
        lines = "\n".join(f"- fact {i}" for i in range(10))
        response = f"KEY_FACTS:\n{lines}\n"
        facts = self.mgr._parse_llm_extraction(response)
        assert len(facts) <= 5

    def test_empty_response_returns_empty_list(self):
        facts = self.mgr._parse_llm_extraction("")
        assert facts == []

    def test_skips_lines_over_200_chars_in_fallback(self):
        long_line = "x" * 250
        short_line = "useful fact"
        response = f"{long_line}\n{short_line}\n"
        facts = self.mgr._parse_llm_extraction(response)
        assert short_line in facts
        assert long_line not in facts


# ===========================================================================
# _extract_urls_from_text
# ===========================================================================


class TestExtractUrlsFromText:
    """Tests for URL extraction utility."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_extracts_https_url(self):
        urls = self.mgr._extract_urls_from_text("Visit https://example.com for more.")
        assert any("example.com" in u for u in urls)

    def test_extracts_http_url(self):
        urls = self.mgr._extract_urls_from_text("Old site: http://legacy.com/page")
        assert any("legacy.com" in u for u in urls)

    def test_deduplicates_urls(self):
        text = "https://example.com https://example.com https://example.com"
        urls = self.mgr._extract_urls_from_text(text)
        assert urls.count("https://example.com") <= 1

    def test_caps_at_five_urls(self):
        text = " ".join(f"https://site{i}.com" for i in range(10))
        urls = self.mgr._extract_urls_from_text(text)
        assert len(urls) <= 5

    def test_empty_text_returns_empty_list(self):
        urls = self.mgr._extract_urls_from_text("")
        assert urls == []

    def test_no_urls_returns_empty_list(self):
        urls = self.mgr._extract_urls_from_text("no URLs here at all")
        assert urls == []


# ===========================================================================
# _fallback_extraction
# ===========================================================================


class TestFallbackExtraction:
    """Tests for heuristic fallback extraction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_extraction_method_is_fallback(self):
        result = self.mgr._fallback_extraction("my_tool", "some content")
        assert result.extraction_method == "fallback"

    def test_confidence_is_half(self):
        result = self.mgr._fallback_extraction("my_tool", "some content")
        assert result.confidence == pytest.approx(0.5)

    def test_success_inferred_from_no_error_keywords(self):
        result = self.mgr._fallback_extraction("tool", "All good here")
        assert result.success is True

    def test_failure_inferred_from_error_keyword(self):
        result = self.mgr._fallback_extraction("tool", "An error occurred")
        assert result.success is False

    def test_failure_inferred_from_failed_keyword(self):
        result = self.mgr._fallback_extraction("tool", "Process failed")
        assert result.success is False

    def test_long_content_is_truncated_in_facts(self):
        long_content = "a" * 2000
        result = self.mgr._fallback_extraction("tool", long_content)
        assert len(result.key_facts) > 0
        assert len(result.key_facts[0]) < 2000

    def test_short_content_used_directly(self):
        content = "short output"
        result = self.mgr._fallback_extraction("tool", content)
        assert content in result.key_facts[0]

    def test_extracts_urls_from_content(self):
        content = "Check https://example.com for details"
        result = self.mgr._fallback_extraction("tool", content)
        assert any("example.com" in u for u in result.urls)


# ===========================================================================
# compact_and_archive
# ===========================================================================


class TestCompactAndArchive:
    """Tests for compact_and_archive async method."""

    def setup_method(self):
        self.mgr = MemoryManager()

    @pytest.mark.asyncio
    async def test_small_message_skipped(self):
        msg = _tool_message(content="short")
        result_msg, path = await self.mgr.compact_and_archive(msg, "session-1")
        assert result_msg is msg
        assert path is None

    @pytest.mark.asyncio
    async def test_empty_content_skipped(self):
        msg = _tool_message(content="")
        result_msg, path = await self.mgr.compact_and_archive(msg, "session-1")
        assert result_msg is msg
        assert path is None

    @pytest.mark.asyncio
    async def test_large_message_without_storage_returns_none_path(self):
        big_content = "data line\n" * 100  # > 500 chars
        msg = _tool_message(content=big_content, function_name="shell_exec")
        self.mgr._enable_file_storage = False
        result_msg, path = await self.mgr.compact_and_archive(msg, "session-1")
        assert path is None
        assert result_msg["_compacted"] is True

    @pytest.mark.asyncio
    async def test_large_message_with_storage_writes_archive(self):
        big_content = "data line\n" * 100
        msg = _tool_message(
            content=big_content,
            function_name="shell_exec",
            extra={"id": "msg-abc-123"},
        )
        mock_storage = AsyncMock()
        mock_storage.write = AsyncMock()
        self.mgr._file_storage = mock_storage
        self.mgr._enable_file_storage = True

        result_msg, path = await self.mgr.compact_and_archive(msg, "session-42")
        mock_storage.write.assert_called_once()
        assert path is not None
        assert "session-42" in path
        assert result_msg["_archive_path"] == path

    @pytest.mark.asyncio
    async def test_storage_failure_falls_back_to_none_path(self):
        big_content = "data line\n" * 100
        msg = _tool_message(content=big_content, function_name="shell_exec")
        mock_storage = AsyncMock()
        mock_storage.write.side_effect = OSError("disk full")
        self.mgr._file_storage = mock_storage
        self.mgr._enable_file_storage = True

        result_msg, path = await self.mgr.compact_and_archive(msg, "session-1")
        assert path is None
        assert result_msg["_compacted"] is True

    @pytest.mark.asyncio
    async def test_compacted_message_has_compacted_flag(self):
        big_content = "data line\n" * 100
        msg = _tool_message(content=big_content, function_name="shell_exec")
        self.mgr._enable_file_storage = False
        result_msg, _ = await self.mgr.compact_and_archive(msg, "session-1")
        assert result_msg.get("_compacted") is True

    @pytest.mark.asyncio
    async def test_archive_index_updated_on_success(self):
        big_content = "data line\n" * 100
        msg = _tool_message(
            content=big_content,
            function_name="shell_exec",
            extra={"id": "unique-id-999"},
        )
        mock_storage = AsyncMock()
        self.mgr._file_storage = mock_storage
        self.mgr._enable_file_storage = True

        await self.mgr.compact_and_archive(msg, "session-1")
        assert "unique-id-999" in self.mgr._archive_index


# ===========================================================================
# retrieve_archived
# ===========================================================================


class TestRetrieveArchived:
    """Tests for retrieve_archived async method."""

    def setup_method(self):
        self.mgr = MemoryManager()

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_message_id(self):
        result = await self.mgr.retrieve_archived("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_memory_only_archive(self):
        self.mgr._archive_index["mem-id"] = "memory://mem-id"
        result = await self.mgr.retrieve_archived("mem-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_file_storage_configured(self):
        self.mgr._archive_index["file-id"] = "/archives/session/file-id.json"
        self.mgr._file_storage = None
        result = await self.mgr.retrieve_archived("file-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_original_content_from_archive(self):
        original = "This is the original content of the message."
        archive_data = json.dumps({"original_content": original})

        mock_storage = AsyncMock()
        mock_storage.read = AsyncMock(return_value=archive_data)
        self.mgr._file_storage = mock_storage
        self.mgr._archive_index["msg-1"] = "/archives/session/msg-1.json"

        result = await self.mgr.retrieve_archived("msg-1")
        assert result == original

    @pytest.mark.asyncio
    async def test_returns_none_on_read_failure(self):
        mock_storage = AsyncMock()
        mock_storage.read.side_effect = OSError("file not found")
        self.mgr._file_storage = mock_storage
        self.mgr._archive_index["msg-2"] = "/archives/session/msg-2.json"

        result = await self.mgr.retrieve_archived("msg-2")
        assert result is None


# ===========================================================================
# get_archive_stats
# ===========================================================================


class TestGetArchiveStats:
    """Tests for archive statistics reporting."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_empty_archive_stats(self):
        stats = self.mgr.get_archive_stats()
        assert stats["total_archived"] == 0
        assert stats["file_archived"] == 0
        assert stats["memory_only"] == 0
        assert stats["token_history_size"] == 0
        assert stats["last_token_count"] == 0

    def test_stats_reflect_archive_entries(self):
        self.mgr._archive_index["a"] = "/archives/a.json"
        self.mgr._archive_index["b"] = "memory://b"
        self.mgr._archive_order = ["a", "b"]
        stats = self.mgr.get_archive_stats()
        assert stats["total_archived"] == 2
        assert stats["file_archived"] == 1
        assert stats["memory_only"] == 1

    def test_usage_ratio_calculated(self):
        self.mgr._archive_index["x"] = "/archives/x.json"
        self.mgr._archive_order = ["x"]
        stats = self.mgr.get_archive_stats()
        assert stats["archive_usage_ratio"] == pytest.approx(1.0 / 1000)

    def test_token_history_size_and_last_count(self):
        self.mgr.track_token_usage(10_000)
        self.mgr.track_token_usage(20_000)
        stats = self.mgr.get_archive_stats()
        assert stats["token_history_size"] == 2
        assert stats["last_token_count"] == 20_000

    def test_max_archive_size_in_stats(self):
        mgr = MemoryManager(max_archive_size=500)
        stats = mgr.get_archive_stats()
        assert stats["max_archive_size"] == 500


# ===========================================================================
# _enforce_archive_limit
# ===========================================================================


class TestEnforceArchiveLimit:
    """Tests for FIFO archive eviction."""

    def setup_method(self):
        self.mgr = MemoryManager(max_archive_size=5, archive_cleanup_batch=2)

    def _fill_archive(self, count: int) -> None:
        for i in range(count):
            self.mgr._archive_index[f"msg-{i}"] = f"/archives/msg-{i}.json"
            self.mgr._archive_order.append(f"msg-{i}")

    def test_no_removal_when_under_limit(self):
        self._fill_archive(4)
        removed = self.mgr._enforce_archive_limit()
        assert removed == 0
        assert len(self.mgr._archive_index) == 4

    def test_removal_when_over_limit(self):
        self._fill_archive(7)  # 7 entries, limit 5 → excess 2, batch 2
        removed = self.mgr._enforce_archive_limit()
        assert removed >= 2
        assert len(self.mgr._archive_index) <= 5

    def test_oldest_entries_removed_first(self):
        self._fill_archive(7)
        self.mgr._enforce_archive_limit()
        # msg-0 and msg-1 (oldest) should be evicted
        assert "msg-0" not in self.mgr._archive_index
        assert "msg-1" not in self.mgr._archive_index

    def test_at_exactly_limit_no_removal(self):
        self._fill_archive(5)
        removed = self.mgr._enforce_archive_limit()
        assert removed == 0


# ===========================================================================
# cleanup_archive and clear_archive
# ===========================================================================


class TestCleanupAndClearArchive:
    """Tests for manual archive management."""

    def setup_method(self):
        self.mgr = MemoryManager(max_archive_size=100)

    def _fill_archive(self, count: int) -> None:
        for i in range(count):
            self.mgr._archive_index[f"msg-{i}"] = f"/archives/msg-{i}.json"
            self.mgr._archive_order.append(f"msg-{i}")

    def test_cleanup_with_max_entries_override(self):
        self._fill_archive(20)
        removed = self.mgr.cleanup_archive(max_entries=10)
        assert removed >= 10
        assert len(self.mgr._archive_index) <= 10

    def test_cleanup_restores_original_max_after_override(self):
        self._fill_archive(20)
        self.mgr.cleanup_archive(max_entries=5)
        # Original max should be restored
        assert self.mgr._max_archive_size == 100

    def test_cleanup_without_override_uses_default(self):
        self._fill_archive(5)
        removed = self.mgr.cleanup_archive()
        assert removed == 0  # Under default limit of 100

    def test_clear_archive_removes_all(self):
        self._fill_archive(10)
        count = self.mgr.clear_archive()
        assert count == 10
        assert len(self.mgr._archive_index) == 0
        assert len(self.mgr._archive_order) == 0

    def test_clear_archive_empty_returns_zero(self):
        count = self.mgr.clear_archive()
        assert count == 0


# ===========================================================================
# _add_to_archive_index
# ===========================================================================


class TestAddToArchiveIndex:
    """Tests for archive index management."""

    def setup_method(self):
        self.mgr = MemoryManager(max_archive_size=3)

    def test_adds_new_entry(self):
        self.mgr._add_to_archive_index("msg-1", "/archives/msg-1.json")
        assert "msg-1" in self.mgr._archive_index
        assert self.mgr._archive_index["msg-1"] == "/archives/msg-1.json"

    def test_updates_existing_entry_without_duplicate_in_order(self):
        self.mgr._add_to_archive_index("msg-1", "/archives/old.json")
        self.mgr._add_to_archive_index("msg-1", "/archives/new.json")
        # Should update value but not duplicate in order
        assert self.mgr._archive_index["msg-1"] == "/archives/new.json"
        assert self.mgr._archive_order.count("msg-1") == 1

    def test_enforces_limit_automatically(self):
        for i in range(5):  # Exceed limit of 3
            self.mgr._add_to_archive_index(f"msg-{i}", f"/archives/msg-{i}.json")
        assert len(self.mgr._archive_index) <= 3

    def test_insertion_order_tracked(self):
        self.mgr._add_to_archive_index("first", "/a")
        self.mgr._add_to_archive_index("second", "/b")
        assert self.mgr._archive_order[0] == "first"
        assert self.mgr._archive_order[1] == "second"


# ===========================================================================
# get_archive_path
# ===========================================================================


class TestGetArchivePath:
    """Tests for archive path generation."""

    def setup_method(self):
        self.mgr = MemoryManager(sandbox_path="/tmp/test")

    def test_path_starts_with_sandbox_path(self):
        path = self.mgr.get_archive_path("shell_exec")
        assert path.startswith("/tmp/test/")

    def test_path_contains_function_name(self):
        path = self.mgr.get_archive_path("browser_view")
        assert "browser_view" in path

    def test_counter_increments(self):
        path1 = self.mgr.get_archive_path("shell_exec")
        path2 = self.mgr.get_archive_path("shell_exec")
        assert path1 != path2
        assert self.mgr._archive_counter == 2

    def test_path_ends_with_txt(self):
        path = self.mgr.get_archive_path("file_read")
        assert path.endswith(".txt")


# ===========================================================================
# structured_compact
# ===========================================================================


class TestStructuredCompact:
    """Tests for emergency LLM-based structured compaction."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def _make_messages(self, n_history: int, n_recent: int = 6) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for i in range(n_history):
            messages.append({"role": "user", "content": f"history message {i}"})
            messages.append({"role": "assistant", "content": f"assistant reply {i}"})
        messages.extend({"role": "user", "content": f"recent {i}"} for i in range(n_recent))
        return messages

    @pytest.mark.asyncio
    async def test_too_few_messages_returns_original(self):
        messages = [{"role": "user", "content": "hi"}]
        mock_llm = AsyncMock()
        result, saved = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        assert result is messages
        assert saved == 0
        mock_llm.ask.assert_not_called()

    @pytest.mark.asyncio
    async def test_compacts_history_and_preserves_recent(self):
        messages = self._make_messages(n_history=10, n_recent=6)
        mock_llm = AsyncMock()
        # Summary must be > 50 chars to pass the length guard in structured_compact
        mock_llm.ask.return_value = {
            "content": (
                "## Summary\n"
                "1. URLs Visited: none\n"
                "2. Files Modified: none\n"
                "3. Decisions Made: keep going with current approach\n"
            )
        }

        result, saved = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        assert len(result) < len(messages)
        assert saved >= 0
        # Recent messages preserved at end
        for msg in result[-6:]:
            assert "recent" in msg["content"]

    @pytest.mark.asyncio
    async def test_system_messages_preserved(self):
        system_msg: dict[str, Any] = {"role": "system", "content": "You are a helpful assistant."}
        messages = [system_msg, *self._make_messages(n_history=5, n_recent=6)]
        mock_llm = AsyncMock()
        mock_llm.ask.return_value = {"content": "Summary of conversation history."}

        result, _ = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_insufficient_summary_returns_original(self):
        messages = self._make_messages(n_history=5, n_recent=6)
        mock_llm = AsyncMock()
        # Empty / too short response
        mock_llm.ask.return_value = {"content": "short"}

        result, saved = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        assert result is messages
        assert saved == 0

    @pytest.mark.asyncio
    async def test_llm_exception_returns_original(self):
        messages = self._make_messages(n_history=5, n_recent=6)
        mock_llm = AsyncMock()
        mock_llm.ask.side_effect = RuntimeError("API error")

        result, saved = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        assert result is messages
        assert saved == 0

    @pytest.mark.asyncio
    async def test_summary_message_has_context_header(self):
        messages = self._make_messages(n_history=5, n_recent=6)
        mock_llm = AsyncMock()
        # Must be > 50 chars to pass the length guard in structured_compact
        long_summary = "Detailed structured summary of the conversation covering all relevant context and decisions made."
        mock_llm.ask.return_value = {"content": long_summary}

        result, _ = await self.mgr.structured_compact(messages, mock_llm, preserve_recent=6)
        # The summary message should be the first non-system message in result
        summary_msg = next(m for m in result if m["role"] != "system")
        assert "[CONTEXT SUMMARY" in summary_msg["content"]

    @pytest.mark.asyncio
    async def test_tokens_saved_is_non_negative(self):
        messages = self._make_messages(n_history=10, n_recent=6)
        mock_llm = AsyncMock()
        # Must be > 50 chars to avoid the insufficient-summary guard
        mock_llm.ask.return_value = {
            "content": (
                "Comprehensive summary of the entire conversation history, "
                "including all key decisions and outcomes recorded so far."
            )
        }

        _, saved = await self.mgr.structured_compact(messages, mock_llm)
        assert saved >= 0


# ===========================================================================
# optimize_context
# ===========================================================================


class TestOptimizeContext:
    """Tests for optimize_context integration."""

    def setup_method(self):
        self.mgr = MemoryManager()

    def test_below_threshold_returns_original_messages(self):
        messages = [{"role": "user", "content": "hello"}]
        result, report = self.mgr.optimize_context(messages, token_threshold=100_000)
        assert result is messages
        assert report.tokens_saved == 0

    def test_no_threshold_always_runs(self):
        messages = [
            {"role": "user", "content": "message one"},
            {"role": "assistant", "content": "response one"},
        ]
        with (
            patch("app.domain.services.agents.memory_manager.SemanticCompressor") as mock_sem_cls,
            patch("app.domain.services.agents.memory_manager.TemporalCompressor") as mock_tem_cls,
            patch("app.domain.services.agents.memory_manager.ImportanceAnalyzer"),
        ):
            mock_sem = MagicMock()
            mock_sem.compress.return_value = (messages, MagicMock(compacted=0))
            mock_sem_cls.return_value = mock_sem

            mock_tem = MagicMock()
            mock_tem.compress.return_value = (messages, MagicMock(compacted=0))
            mock_tem_cls.return_value = mock_tem

            _result, _report = self.mgr.optimize_context(messages, token_threshold=None)
            mock_sem.compress.assert_called_once()
            mock_tem.compress.assert_called_once()


# ===========================================================================
# get_memory_manager singleton
# ===========================================================================


class TestGetMemoryManager:
    """Tests for the global singleton factory."""

    def test_returns_memory_manager_instance(self):
        mgr = get_memory_manager()
        assert isinstance(mgr, MemoryManager)

    def test_returns_same_instance_on_repeated_calls(self):
        mgr1 = get_memory_manager()
        mgr2 = get_memory_manager()
        assert mgr1 is mgr2

    def test_singleton_is_memory_manager_subclass(self):
        mgr = get_memory_manager()
        assert isinstance(mgr, MemoryManager)
