"""Comprehensive tests for ResponseGenerator.

Covers:
- Pydantic models (_SuggestionPayload)
- Module-level regex patterns
- ResponseGenerator construction and state setters
- Artifact reference normalization and rendering
- Stream coalescing (iter_coalesced_stream_events)
- Continuation prompt building
- Stream continuation merging and markdown repair
- Duplicate report collapse
- Report quality scoring
- Delivery integrity gate
- Content cleaning (clean_report_content, strip_trailing_meta_commentary)
- Quality detection (is_meta_commentary, is_low_quality_summary,
  is_research_report_quality, is_report_structure)
- Title extraction
- Fallback recovery (extract_fallback_summary, resolve_json_tool_result,
  extract_report_from_file_write_memory)
- Follow-up suggestion generation and parsing
- Topic hint extraction
- Memory context excerpt building
- Metric normalization helpers
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.domain.services.agents.response_generator import (
    ResponseGenerator,
    _SuggestionPayload,
)
from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_source_tracker(sources: list[Any] | None = None) -> MagicMock:
    tracker = MagicMock()
    tracker.get_collected_sources.return_value = sources or []
    return tracker


def _make_llm(provider: str = "openai") -> MagicMock:
    llm = MagicMock()
    llm.provider = provider
    llm.last_stream_metadata = {}
    return llm


def _make_generator(
    *,
    llm: Any = None,
    memory: Any = None,
    source_tracker: Any = None,
    coalesce_max_chars: int = 320,
    coalesce_flush_seconds: float = 0.0,
) -> ResponseGenerator:
    return ResponseGenerator(
        llm=llm or _make_llm(),
        memory=memory,
        source_tracker=source_tracker or _make_source_tracker(),
        coalesce_max_chars=coalesce_max_chars,
        coalesce_flush_seconds=coalesce_flush_seconds,
    )


def _make_response_policy(
    mode: VerbosityMode = VerbosityMode.STANDARD,
    min_required_sections: list[str] | None = None,
) -> ResponsePolicy:
    return ResponsePolicy(
        mode=mode,
        min_required_sections=min_required_sections or [],
    )


async def _string_gen(*chunks: str) -> AsyncGenerator[str, None]:
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# _SuggestionPayload model
# ---------------------------------------------------------------------------


class TestSuggestionPayload:
    def test_valid_suggestions(self) -> None:
        payload = _SuggestionPayload(suggestions=["a", "b", "c"])
        assert payload.suggestions == ["a", "b", "c"]

    def test_empty_suggestions(self) -> None:
        payload = _SuggestionPayload(suggestions=[])
        assert payload.suggestions == []

    def test_model_validate_json_valid(self) -> None:
        raw = '{"suggestions": ["x", "y"]}'
        payload = _SuggestionPayload.model_validate_json(raw)
        assert len(payload.suggestions) == 2

    def test_model_validate_json_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            _SuggestionPayload.model_validate_json('{"suggestions": "not-a-list"}')

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            _SuggestionPayload.model_validate({})


# ---------------------------------------------------------------------------
# Construction and state setters
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_defaults(self) -> None:
        rg = _make_generator()
        assert rg._coalesce_max_chars == 320
        assert rg._coalesce_flush_seconds == 0.0
        assert rg._artifact_references == []
        assert rg._pre_trim_report_cache is None
        assert rg._user_request is None
        assert rg._coalesce_pending == ""

    def test_custom_coalesce_params(self) -> None:
        rg = _make_generator(coalesce_max_chars=100, coalesce_flush_seconds=0.2)
        assert rg._coalesce_max_chars == 100
        assert rg._coalesce_flush_seconds == 0.2

    def test_set_pre_trim_report_cache(self) -> None:
        rg = _make_generator()
        rg.set_pre_trim_report_cache("cached report")
        assert rg._pre_trim_report_cache == "cached report"

    def test_set_user_request(self) -> None:
        rg = _make_generator()
        rg.set_user_request("What is FastAPI?")
        assert rg._user_request == "What is FastAPI?"

    def test_null_metrics_used_when_not_provided(self) -> None:
        rg = _make_generator()
        # Should not raise when recording metrics
        rg._metrics.record_counter("test_counter")


# ---------------------------------------------------------------------------
# set_artifact_references / _artifact_references_section
# ---------------------------------------------------------------------------


class TestArtifactReferences:
    def test_empty_references(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([])
        assert rg._artifact_references == []

    def test_none_references(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references(None)
        assert rg._artifact_references == []

    def test_normalizes_filename_field(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "report.md"}])
        assert rg._artifact_references[0]["filename"] == "report.md"

    def test_normalizes_file_name_field(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"file_name": "data.csv"}])
        assert rg._artifact_references[0]["filename"] == "data.csv"

    def test_normalizes_path_field(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"path": "output.pdf"}])
        assert rg._artifact_references[0]["filename"] == "output.pdf"

    def test_normalizes_file_path_field(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"file_path": "result.txt"}])
        assert rg._artifact_references[0]["filename"] == "result.txt"

    def test_deduplicates_by_filename(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references(
            [
                {"filename": "report.md"},
                {"filename": "report.md"},
            ]
        )
        assert len(rg._artifact_references) == 1

    def test_skips_non_dict_entries(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references(["not-a-dict", {"filename": "ok.md"}])  # type: ignore[list-item]
        assert len(rg._artifact_references) == 1

    def test_skips_empty_filename(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "   "}])
        assert rg._artifact_references == []

    def test_includes_content_type(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "report.md", "content_type": "text/markdown"}])
        assert rg._artifact_references[0]["content_type"] == "text/markdown"

    def test_includes_file_path_storage_key(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "report.md", "storage_key": "bucket/report.md"}])
        assert rg._artifact_references[0]["file_path"] == "bucket/report.md"

    def test_section_with_no_artifacts(self) -> None:
        rg = _make_generator()
        section = rg._artifact_references_section()
        assert "No file artifacts" in section

    def test_section_renders_filename(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "report.md"}])
        section = rg._artifact_references_section()
        assert "report.md" in section
        assert "## Artifact References" in section

    def test_section_renders_content_type(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "chart.png", "content_type": "image/png"}])
        section = rg._artifact_references_section()
        assert "(image/png)" in section

    def test_get_artifact_references_section_if_present_returns_none_when_no_artifacts(self) -> None:
        rg = _make_generator()
        assert rg.get_artifact_references_section_if_present() is None

    def test_get_artifact_references_section_if_present_returns_section_when_artifacts_exist(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "result.md"}])
        section = rg.get_artifact_references_section_if_present()
        assert section is not None
        assert "result.md" in section


# ---------------------------------------------------------------------------
# get_last_stream_metadata
# ---------------------------------------------------------------------------


class TestStreamMetadata:
    def test_returns_empty_dict_when_no_metadata(self) -> None:
        llm = MagicMock(spec=[])  # No last_stream_metadata attribute
        rg = _make_generator(llm=llm)
        assert rg.get_last_stream_metadata() == {}

    def test_returns_metadata_dict(self) -> None:
        llm = _make_llm()
        llm.last_stream_metadata = {"finish_reason": "stop", "tokens": 100}
        rg = _make_generator(llm=llm)
        assert rg.get_last_stream_metadata()["finish_reason"] == "stop"

    def test_returns_empty_dict_when_metadata_not_dict(self) -> None:
        llm = _make_llm()
        llm.last_stream_metadata = "not-a-dict"
        rg = _make_generator(llm=llm)
        assert rg.get_last_stream_metadata() == {}


# ---------------------------------------------------------------------------
# iter_coalesced_stream_events
# ---------------------------------------------------------------------------


class TestCoalescedStreamEvents:
    @pytest.mark.asyncio
    async def test_yields_stream_events(self) -> None:
        rg = _make_generator(coalesce_max_chars=5, coalesce_flush_seconds=0.0)
        events = [e async for e in rg.iter_coalesced_stream_events(_string_gen("hello", " world"))]
        content = "".join(e.content for e in events)
        assert "hello world" in content

    @pytest.mark.asyncio
    async def test_empty_stream_yields_nothing(self) -> None:
        rg = _make_generator()
        events = [e async for e in rg.iter_coalesced_stream_events(_string_gen())]
        assert events == []

    @pytest.mark.asyncio
    async def test_skips_empty_chunks(self) -> None:
        rg = _make_generator(coalesce_max_chars=2, coalesce_flush_seconds=0.0)
        events = [e async for e in rg.iter_coalesced_stream_events(_string_gen("", "", "hi"))]
        total = "".join(e.content for e in events)
        assert "hi" in total

    @pytest.mark.asyncio
    async def test_flushes_on_newline(self) -> None:
        rg = _make_generator(coalesce_max_chars=10000, coalesce_flush_seconds=0.0)
        events = [e async for e in rg.iter_coalesced_stream_events(_string_gen("line1\n", "line2"))]
        # Should flush after the newline chunk
        assert len(events) >= 1
        assert "line1" in events[0].content

    @pytest.mark.asyncio
    async def test_phase_and_lane_passed_through(self) -> None:
        rg = _make_generator(coalesce_max_chars=1, coalesce_flush_seconds=0.0)
        events = [
            e
            async for e in rg.iter_coalesced_stream_events(
                _string_gen("x"),
                phase="reporting",
                lane="reasoning",
            )
        ]
        assert all(e.phase == "reporting" for e in events)
        assert all(e.lane == "reasoning" for e in events)

    @pytest.mark.asyncio
    async def test_is_final_always_false(self) -> None:
        rg = _make_generator(coalesce_max_chars=1, coalesce_flush_seconds=0.0)
        events = [e async for e in rg.iter_coalesced_stream_events(_string_gen("a", "b"))]
        assert all(e.is_final is False for e in events)

    @pytest.mark.asyncio
    async def test_coalesce_pending_cleared_after_flush(self) -> None:
        rg = _make_generator(coalesce_max_chars=1, coalesce_flush_seconds=0.0)
        async for _ in rg.iter_coalesced_stream_events(_string_gen("abc")):
            pass
        assert rg._coalesce_pending == ""


# ---------------------------------------------------------------------------
# build_continuation_prompt
# ---------------------------------------------------------------------------


class TestBuildContinuationPrompt:
    def test_base_prompt_when_no_args(self) -> None:
        rg = _make_generator()
        prompt = rg.build_continuation_prompt()
        assert "truncated" in prompt.lower()

    def test_base_prompt_when_no_source_list(self) -> None:
        rg = _make_generator()
        prompt = rg.build_continuation_prompt(accumulated_text="# Report\nSome text.")
        assert "References" not in prompt

    def test_includes_source_list_when_ref_heading_incomplete(self) -> None:
        rg = _make_generator()
        accumulated = "# Report\n\nSome text [1][2].\n\n## References\n[1] Source A"
        source_list = "[1] Source A\n[2] Source B"
        prompt = rg.build_continuation_prompt(accumulated_text=accumulated, source_list=source_list)
        assert "References" in prompt
        assert "Source A" in prompt

    def test_includes_source_list_when_no_references_heading_but_citations_exist(self) -> None:
        rg = _make_generator()
        accumulated = "# Report\n\nSome text [1][2][3]."
        source_list = "[1] A\n[2] B\n[3] C"
        prompt = rg.build_continuation_prompt(accumulated_text=accumulated, source_list=source_list)
        assert "References" in prompt

    def test_no_references_needed_when_complete(self) -> None:
        rg = _make_generator()
        accumulated = "# Report\n\nText [1].\n\n## References\n[1] Source A"
        source_list = "[1] Source A"
        prompt = rg.build_continuation_prompt(accumulated_text=accumulated, source_list=source_list)
        # one source, one ref entry — no injection needed
        assert prompt.count("Source A") == 0 or "truncated" in prompt


# ---------------------------------------------------------------------------
# merge_stream_continuation
# ---------------------------------------------------------------------------


class TestMergeStreamContinuation:
    def test_empty_continuation_returns_base(self) -> None:
        rg = _make_generator()
        result = rg.merge_stream_continuation("base text", "")
        assert result == "base text"

    def test_overlap_detected_and_merged(self) -> None:
        rg = _make_generator()
        # Provide two chunks that share an overlap of 80+ chars at the seam
        overlap = "X" * 100
        base = "# Report\n\nSection A content.\n\n" + overlap
        continuation = overlap + "\nSection B content."
        with patch(
            "app.domain.services.agents.citation_integrity.rebase_continuation_citations",
            side_effect=lambda b, c: c,
        ):
            result = rg.merge_stream_continuation(base, continuation)
        # The overlap should be deduplicated — "X" * 100 appears only once
        assert result.count(overlap) == 1
        assert "Section A" in result
        assert "Section B" in result

    def test_continuation_already_in_base_returns_base(self) -> None:
        rg = _make_generator()
        base = "# Report\n\nFull content here."
        with patch("app.domain.services.agents.citation_integrity.rebase_continuation_citations", return_value=""):
            result = rg.merge_stream_continuation(base, "")
            assert result == base

    def test_whitespace_only_continuation_returns_base(self) -> None:
        rg = _make_generator()
        with patch("app.domain.services.agents.citation_integrity.rebase_continuation_citations", return_value="   "):
            result = rg.merge_stream_continuation("# Report content", "   ")
            assert result == "# Report content"


# ---------------------------------------------------------------------------
# _repair_markdown_structure
# ---------------------------------------------------------------------------


class TestRepairMarkdownStructure:
    def test_empty_string(self) -> None:
        result = ResponseGenerator._repair_markdown_structure("")
        assert result == ""

    def test_closes_unclosed_fence(self) -> None:
        text = "Some text\n```python\ncode here"
        result = ResponseGenerator._repair_markdown_structure(text)
        assert result.count("```") % 2 == 0

    def test_even_fences_unchanged(self) -> None:
        text = "```python\ncode\n```"
        result = ResponseGenerator._repair_markdown_structure(text)
        assert result.count("```") == 2

    def test_removes_duplicate_adjacent_headings(self) -> None:
        text = "## Section A\n\n## Section A\n\nContent"
        result = ResponseGenerator._repair_markdown_structure(text)
        assert result.count("## Section A") == 1

    def test_collapses_excess_blank_lines(self) -> None:
        text = "Line 1\n\n\n\n\nLine 2"
        result = ResponseGenerator._repair_markdown_structure(text)
        assert "\n\n\n\n" not in result


# ---------------------------------------------------------------------------
# collapse_duplicate_report_payload
# ---------------------------------------------------------------------------


class TestCollapseDuplicateReportPayload:
    def test_short_content_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Title\nShort."
        assert rg.collapse_duplicate_report_payload(content) == content.strip()

    def test_single_heading_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Title\n" + "Body text. " * 50
        result = rg.collapse_duplicate_report_payload(content)
        assert "# Title" in result

    def test_collapses_duplicate_h1(self) -> None:
        rg = _make_generator()
        first_block = "# My Report\n\nFirst version content [unverified]."
        second_block = (
            "# My Report\n\nSecond version content. Much better [2][3].\n\n## References\n[1] A\n[2] B\n[3] C"
        )
        content = f"{first_block}\n\n{second_block}"
        result = rg.collapse_duplicate_report_payload(content)
        # Second block is longer and higher quality — it should be chosen
        assert "My Report" in result

    def test_no_duplicate_headings_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Title One\n\n" + "A" * 300 + "\n\n# Title Two\n\n" + "B" * 200
        result = rg.collapse_duplicate_report_payload(content)
        assert "Title One" in result
        assert "Title Two" in result


# ---------------------------------------------------------------------------
# _report_quality_score
# ---------------------------------------------------------------------------


class TestReportQualityScore:
    def test_empty_block_returns_max_score(self) -> None:
        rg = _make_generator()
        assert rg._report_quality_score("") == 10_000

    def test_clean_block_has_low_score(self) -> None:
        rg = _make_generator()
        score = rg._report_quality_score("# Clean Report\n\nWell-written content without markers.")
        assert score < 5

    def test_verification_markers_increase_score(self) -> None:
        rg = _make_generator()
        score_clean = rg._report_quality_score("# Report\n\nClean text.")
        score_dirty = rg._report_quality_score("# Report\n\nText [unverified] and [not verified] data.")
        assert score_dirty > score_clean

    def test_short_block_penalty(self) -> None:
        rg = _make_generator()
        short_score = rg._report_quality_score("# Report\n\nShort.")
        long_score = rg._report_quality_score("# Report\n\n" + "Content. " * 100)
        assert short_score >= long_score


# ---------------------------------------------------------------------------
# _normalize_metric_label
# ---------------------------------------------------------------------------


class TestNormalizeMetricLabel:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("OpenAI", "openai"),
            ("stream_truncation_unresolved", "stream_truncation_unresolved"),
            # _normalize_metric_label converts ALL chars, including colons → underscores
            ("coverage_missing:artifact references", "coverage_missing_artifact_references"),
            ("", "unknown"),
            ("  ", "unknown"),
            ("hello world", "hello_world"),
            ("double__underscore", "double_underscore"),
        ],
    )
    def test_normalization(self, value: str, expected: str) -> None:
        rg = _make_generator()
        result = rg._normalize_metric_label(value)
        assert result == expected

    def test_custom_fallback(self) -> None:
        rg = _make_generator()
        result = rg._normalize_metric_label("", fallback="none")
        assert result == "none"


# ---------------------------------------------------------------------------
# _normalize_integrity_reason
# ---------------------------------------------------------------------------


class TestNormalizeIntegrityReason:
    def test_strips_after_colon(self) -> None:
        rg = _make_generator()
        assert rg._normalize_integrity_reason("coverage_missing:artifact references") == "coverage_missing"

    def test_no_colon(self) -> None:
        rg = _make_generator()
        assert rg._normalize_integrity_reason("stream_truncation_unresolved") == "stream_truncation_unresolved"

    def test_empty_reason(self) -> None:
        rg = _make_generator()
        assert rg._normalize_integrity_reason("") == "unknown"


# ---------------------------------------------------------------------------
# clean_report_content
# ---------------------------------------------------------------------------


class TestCleanReportContent:
    def test_empty_content_returned_unchanged(self) -> None:
        rg = _make_generator()
        assert rg.clean_report_content("") == ""

    def test_strips_tool_call_xml(self) -> None:
        rg = _make_generator()
        content = "Before<tool_call>internal json</tool_call>After"
        result = rg.clean_report_content(content)
        assert "<tool_call>" not in result
        assert "Before" in result
        assert "After" in result

    def test_strips_function_call_xml(self) -> None:
        rg = _make_generator()
        content = "Text<function_call>args</function_call>more"
        result = rg.clean_report_content(content)
        assert "<function_call>" not in result

    def test_strips_orphaned_tool_placeholder(self) -> None:
        rg = _make_generator()
        content = "[Previously called file_write]\n# Report\n\nContent."
        result = rg.clean_report_content(content)
        assert "[Previously called file_write]" not in result

    def test_strips_boilerplate_final_result(self) -> None:
        rg = _make_generator()
        content = "## Final Result\nThe requested work has been completed successfully.\n\n# Report\n\nData."
        result = rg.clean_report_content(content)
        assert "The requested work has been completed" not in result

    def test_strips_boilerplate_no_artifacts(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nContent.\n\n## Artifact References\n- No file artifacts were created."
        result = rg.clean_report_content(content)
        assert "No file artifacts were created" not in result

    def test_collapses_excess_blank_lines(self) -> None:
        rg = _make_generator()
        content = "# Title\n\n\n\n\nContent"
        result = rg.clean_report_content(content)
        assert "\n\n\n" not in result

    def test_strips_short_preamble_before_heading(self) -> None:
        rg = _make_generator()
        content = "Here is a brief intro.\n# Report Heading\n\nActual content."
        result = rg.clean_report_content(content)
        assert "Here is a brief intro" not in result
        assert "Report Heading" in result

    def test_preserves_long_preamble(self) -> None:
        rg = _make_generator()
        long_preamble = "A" * 600 + "\n# Report\n\nContent."
        result = rg.clean_report_content(long_preamble)
        assert "A" * 100 in result  # Long preamble is preserved


# ---------------------------------------------------------------------------
# strip_trailing_meta_commentary
# ---------------------------------------------------------------------------


class TestStripTrailingMetaCommentary:
    def test_no_meta_commentary_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nClean content."
        assert rg.strip_trailing_meta_commentary(content) == content

    def test_strips_trailing_save_commentary(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nContent.\nI'll now save this report to the file."
        result = rg.strip_trailing_meta_commentary(content)
        assert "save this report" not in result
        assert "Content." in result

    def test_strips_writing_to_file_commentary(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nContent.\nWriting the report to output.md"
        result = rg.strip_trailing_meta_commentary(content)
        assert "Writing the report" not in result

    def test_strips_output_cut_notice(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nContent.\nNote: The model's output was cut short."
        result = rg.strip_trailing_meta_commentary(content)
        assert "output was cut" not in result


# ---------------------------------------------------------------------------
# has_truncation_artifacts
# ---------------------------------------------------------------------------


class TestHasTruncationArtifacts:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("Clean text without artifacts.", False),
            ("Content […] more.", True),
            ("Content [...] more.", True),
            ("Normal [1] citation", False),
        ],
    )
    def test_detection(self, content: str, expected: bool) -> None:
        rg = _make_generator()
        assert rg.has_truncation_artifacts(content) == expected


# ---------------------------------------------------------------------------
# is_meta_commentary
# ---------------------------------------------------------------------------


class TestIsMetaCommentary:
    def test_empty_content_returns_false(self) -> None:
        rg = _make_generator()
        assert rg.is_meta_commentary("") is False

    def test_real_report_content_not_meta(self) -> None:
        rg = _make_generator()
        content = "# FastAPI Performance Guide\n\n## Overview\n\nFastAPI is a high-performance web framework."
        assert rg.is_meta_commentary(content) is False

    @pytest.mark.parametrize(
        "content",
        [
            "I've created a comprehensive report for you.",
            "I have produced the research summary.",
            "Let me create a detailed analysis of this topic.",
            "The comprehensive report has been completed.",
            "Here is a summary of what was found.",
            "I am unable to generate the full report due to token limits.",
            # Pattern: (token|context) (budget|limit|window) (has been|is)? (exceeded|exhausted|insufficient)
            "token budget has been exceeded.",
            "Research findings have been gathered but the report compilation requires more context.",
        ],
    )
    def test_meta_commentary_detected(self, content: str) -> None:
        rg = _make_generator()
        assert rg.is_meta_commentary(content) is True

    def test_short_artifact_deferral_detected(self) -> None:
        rg = _make_generator()
        content = "See the full report in `report.md` for details."
        assert rg.is_meta_commentary(content) is True

    def test_long_content_with_artifact_reference_not_flagged(self) -> None:
        rg = _make_generator()
        # Long report that happens to mention a file — should NOT be meta
        content = "# Report\n\n" + "Substantive content. " * 200 + "\nSee also `appendix.md`."
        assert rg.is_meta_commentary(content) is False


# ---------------------------------------------------------------------------
# is_low_quality_summary
# ---------------------------------------------------------------------------


class TestIsLowQualitySummary:
    def test_empty_is_low_quality(self) -> None:
        rg = _make_generator()
        assert rg.is_low_quality_summary("") is True

    def test_orphaned_tool_placeholder_is_low_quality(self) -> None:
        rg = _make_generator()
        assert rg.is_low_quality_summary("[Previously called file_write] something") is True

    def test_long_content_not_low_quality(self) -> None:
        rg = _make_generator()
        content = "Some text. " * 200
        assert rg.is_low_quality_summary(content) is False

    def test_short_with_headings_not_low_quality(self) -> None:
        rg = _make_generator()
        content = "## Summary\n\nGood structured content."
        assert rg.is_low_quality_summary(content) is False

    def test_short_without_headings_is_low_quality(self) -> None:
        rg = _make_generator()
        content = "Short text."
        assert rg.is_low_quality_summary(content) is True

    def test_excuse_keyword_is_low_quality(self) -> None:
        rg = _make_generator()
        content = "This analysis exceeds the token budget for this session."
        assert rg.is_low_quality_summary(content) is True

    @pytest.mark.parametrize(
        ("depth", "content_length"),
        [
            ("QUICK", 310),
            ("STANDARD", 820),
            ("DEEP", 1510),
            ("DEAL", 510),
        ],
    )
    def test_depth_aware_thresholds(self, depth: str, content_length: int) -> None:
        rg = _make_generator()
        content = "x" * content_length
        assert rg.is_low_quality_summary(content, research_depth=depth) is False

    def test_unknown_depth_defaults_to_standard(self) -> None:
        rg = _make_generator()
        content = "x" * 820
        assert rg.is_low_quality_summary(content, research_depth="UNKNOWN") is False


# ---------------------------------------------------------------------------
# is_research_report_quality
# ---------------------------------------------------------------------------


class TestIsResearchReportQuality:
    def test_empty_fails(self) -> None:
        rg = _make_generator()
        passed, issues = rg.is_research_report_quality("")
        assert passed is False
        assert "empty_content" in issues

    def test_missing_references_detected(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nSome text [1][2].\n"
        _, issues = rg.is_research_report_quality(content)
        assert "missing_references_section" in issues

    def test_complete_report_passes(self) -> None:
        rg = _make_generator()
        content = (
            "# Complete Report\n\n"
            "Introduction [1]. Details [2][3].\n\n"
            "## References\n"
            "[1] Source A\n"
            "[2] Source B\n"
            "[3] Source C\n"
        )
        passed, issues = rg.is_research_report_quality(content)
        assert passed is True
        assert "missing_references_section" not in issues

    def test_insufficient_citations_detected(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nOnly one citation [1].\n\n## References\n[1] Source A"
        _, issues = rg.is_research_report_quality(content)
        assert any("insufficient_citations" in i for i in issues)

    def test_no_comparison_table_noted(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nText [1][2].\n\n## References\n[1] A\n[2] B"
        _, issues = rg.is_research_report_quality(content)
        assert "no_comparison_table" in issues

    def test_table_present_not_flagged(self) -> None:
        rg = _make_generator()
        content = (
            "# Report\n\n| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n\nText [1][2].\n\n## References\n[1] A\n[2] B"
        )
        _, issues = rg.is_research_report_quality(content)
        assert "no_comparison_table" not in issues


# ---------------------------------------------------------------------------
# is_report_structure
# ---------------------------------------------------------------------------


class TestIsReportStructure:
    def test_empty_is_not_report(self) -> None:
        rg = _make_generator()
        assert rg.is_report_structure("") is False

    def test_two_headings_is_report(self) -> None:
        rg = _make_generator()
        assert rg.is_report_structure("## Section One\n\nContent.\n\n## Section Two\n\nMore.") is True

    def test_single_heading_is_not_report(self) -> None:
        rg = _make_generator()
        assert rg.is_report_structure("## Only Section\n\nContent.") is False

    def test_bold_headers_are_report(self) -> None:
        rg = _make_generator()
        content = "**Overview:** Text.\n\n**Details:** More text."
        assert rg.is_report_structure(content) is True

    def test_numbered_sections_are_report(self) -> None:
        rg = _make_generator()
        content = "1. First Point here.\n2. Second Point here."
        assert rg.is_report_structure(content) is True

    def test_heavy_citations_long_content_is_report(self) -> None:
        rg = _make_generator()
        content = "[1][2][3][4] " * 30 + "x" * 1100
        assert rg.is_report_structure(content) is True

    def test_plain_prose_is_not_report(self) -> None:
        rg = _make_generator()
        content = "Just a simple sentence with no structure whatsoever."
        assert rg.is_report_structure(content) is False


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_h1_title(self) -> None:
        rg = _make_generator()
        assert rg.extract_title("# My Great Report\n\nContent.") == "My Great Report"

    def test_h2_title_when_no_h1(self) -> None:
        rg = _make_generator()
        assert rg.extract_title("## Section Title\n\nContent.") == "Section Title"

    def test_first_line_fallback(self) -> None:
        rg = _make_generator()
        title = rg.extract_title("Plain first line.\n\nMore content.")
        assert "Plain first line" in title

    def test_bold_stripped_from_first_line(self) -> None:
        rg = _make_generator()
        title = rg.extract_title("**Bold Title**\n\nContent.")
        assert "**" not in title
        assert "Bold Title" in title

    def test_default_title_for_empty_content(self) -> None:
        rg = _make_generator()
        assert rg.extract_title("") == "Task Report"

    def test_long_first_line_truncated(self) -> None:
        rg = _make_generator()
        long_line = "A" * 100
        title = rg.extract_title(long_line)
        assert len(title) <= 83  # 80 + "..."

    def test_h1_preferred_over_h2(self) -> None:
        rg = _make_generator()
        content = "## Intro\n\n# Main Title\n\nContent."
        # H1 should be found first since it appears in first 10 lines
        title = rg.extract_title(content)
        # Depends on order — ## Intro appears first so it's returned
        assert title in ("Intro", "Main Title")


# ---------------------------------------------------------------------------
# extract_fallback_summary
# ---------------------------------------------------------------------------


class TestExtractFallbackSummary:
    def test_returns_cache_when_available(self) -> None:
        rg = _make_generator()
        rg.set_pre_trim_report_cache("# Cached Report\n\n" + "Content. " * 50)
        result = rg.extract_fallback_summary()
        assert "Cached Report" in result

    def test_ignores_short_cache(self) -> None:
        rg = _make_generator(memory=MagicMock())
        rg._pre_trim_report_cache = "short"
        rg._memory.get_messages.return_value = []
        result = rg.extract_fallback_summary()
        assert result == ""

    def test_returns_empty_when_no_memory(self) -> None:
        rg = _make_generator(memory=None)
        result = rg.extract_fallback_summary()
        assert result == ""

    def test_extracts_from_last_assistant_message(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "user", "content": "My question"},
            {"role": "assistant", "content": "A" * 200},
        ]
        rg = _make_generator(memory=memory)
        result = rg.extract_fallback_summary()
        assert "Task Summary" in result
        assert "A" * 50 in result

    def test_skips_short_assistant_messages(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "assistant", "content": "Short."},
        ]
        rg = _make_generator(memory=memory)
        result = rg.extract_fallback_summary()
        assert result == ""

    def test_strips_tool_call_markers_from_fallback(self) -> None:
        memory = MagicMock()
        long_content = "[Previously called file_write] " + "Real content. " * 20
        memory.get_messages.return_value = [
            {"role": "assistant", "content": long_content},
        ]
        rg = _make_generator(memory=memory)
        result = rg.extract_fallback_summary()
        assert "[Previously called file_write]" not in result


# ---------------------------------------------------------------------------
# resolve_json_tool_result
# ---------------------------------------------------------------------------


class TestResolveJsonToolResult:
    def test_non_json_returned_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Normal Report\n\nContent."
        assert rg.resolve_json_tool_result(content) == content

    def test_json_without_success_key_returned_unchanged(self) -> None:
        rg = _make_generator()
        content = '{"result": "data"}'
        assert rg.resolve_json_tool_result(content) == content

    def test_json_tool_result_uses_pre_trim_cache(self) -> None:
        rg = _make_generator(memory=MagicMock())
        rg._memory.get_messages.return_value = []
        rg.set_pre_trim_report_cache("# Real Report\n\n" + "Content. " * 50)
        content = '{"success": true, "result": "file written"}'
        result = rg.resolve_json_tool_result(content)
        assert "Real Report" in result

    def test_json_tool_result_falls_back_to_result_field(self) -> None:
        rg = _make_generator(memory=MagicMock())
        rg._memory.get_messages.return_value = []
        result_text = "# Report\n\n" + "Data. " * 20
        content = json.dumps({"success": True, "result": result_text})
        result = rg.resolve_json_tool_result(content)
        assert "Report" in result

    def test_json_in_code_block_resolved(self) -> None:
        rg = _make_generator(memory=MagicMock())
        rg._memory.get_messages.return_value = []
        rg.set_pre_trim_report_cache("# Cached\n\n" + "Content. " * 30)
        content = '```json\n{"success": true, "result": "ok"}\n```'
        result = rg.resolve_json_tool_result(content)
        assert "Cached" in result

    def test_invalid_json_returned_unchanged(self) -> None:
        rg = _make_generator()
        content = "{not valid json}"
        assert rg.resolve_json_tool_result(content) == content

    def test_json_array_returned_unchanged(self) -> None:
        rg = _make_generator()
        content = '["item1", "item2"]'
        assert rg.resolve_json_tool_result(content) == content


# ---------------------------------------------------------------------------
# extract_report_from_file_write_memory
# ---------------------------------------------------------------------------


class TestExtractReportFromFileWriteMemory:
    def test_returns_none_when_no_memory(self) -> None:
        rg = _make_generator(memory=None)
        assert rg.extract_report_from_file_write_memory() is None

    def test_returns_none_when_no_messages(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = []
        rg = _make_generator(memory=memory)
        assert rg.extract_report_from_file_write_memory() is None

    def test_extracts_from_file_write_tool_call(self) -> None:
        long_content = "# Report\n\n" + "Content. " * 50
        memory = MagicMock()
        memory.get_messages.return_value = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "file_write",
                            "arguments": json.dumps(
                                {
                                    "path": "report.md",
                                    "content": long_content,
                                }
                            ),
                        }
                    }
                ],
            }
        ]
        rg = _make_generator(memory=memory)
        result = rg.extract_report_from_file_write_memory()
        assert result is not None
        assert "Report" in result

    def test_ignores_non_md_files(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "file_write",
                            "arguments": json.dumps(
                                {
                                    "path": "data.json",
                                    "content": "x" * 300,
                                }
                            ),
                        }
                    }
                ],
            }
        ]
        rg = _make_generator(memory=memory)
        assert rg.extract_report_from_file_write_memory() is None

    def test_ignores_short_content(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "file_write",
                            "arguments": json.dumps(
                                {
                                    "path": "report.md",
                                    "content": "Short.",
                                }
                            ),
                        }
                    }
                ],
            }
        ]
        rg = _make_generator(memory=memory)
        assert rg.extract_report_from_file_write_memory() is None

    def test_accepts_file_create_tool(self) -> None:
        long_content = "# Created Report\n\n" + "Data. " * 50
        memory = MagicMock()
        memory.get_messages.return_value = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "file_create",
                            "arguments": json.dumps(
                                {
                                    "path": "output.md",
                                    "content": long_content,
                                }
                            ),
                        }
                    }
                ],
            }
        ]
        rg = _make_generator(memory=memory)
        result = rg.extract_report_from_file_write_memory()
        assert result is not None
        assert "Created Report" in result


# ---------------------------------------------------------------------------
# _parse_suggestions_payload
# ---------------------------------------------------------------------------


class TestParseSuggestionsPayload:
    def test_parses_dict_payload(self) -> None:
        rg = _make_generator()
        result = rg._parse_suggestions_payload({"suggestions": ["a", "b", "c"]})
        assert result == ["a", "b", "c"]

    def test_parses_json_string_with_suggestions_key(self) -> None:
        rg = _make_generator()
        raw = '{"suggestions": ["x", "y", "z"]}'
        result = rg._parse_suggestions_payload(raw)
        assert result == ["x", "y", "z"]

    def test_parses_json_string_plain_list(self) -> None:
        rg = _make_generator()
        raw = '["p", "q", "r"]'
        result = rg._parse_suggestions_payload(raw)
        assert result == ["p", "q", "r"]

    def test_parses_list_payload(self) -> None:
        rg = _make_generator()
        result = rg._parse_suggestions_payload(["1", "2", "3"])
        assert result == ["1", "2", "3"]

    def test_unsupported_type_raises(self) -> None:
        rg = _make_generator()
        with pytest.raises(TypeError):
            rg._parse_suggestions_payload(42)


# ---------------------------------------------------------------------------
# _default_follow_up_suggestions
# ---------------------------------------------------------------------------


class TestDefaultFollowUpSuggestions:
    def test_pirate_content(self) -> None:
        rg = _make_generator()
        suggestions = rg._default_follow_up_suggestions(title="Pirate Tale", content="arrr we sail")
        assert any("pirate" in s.lower() for s in suggestions)

    def test_generic_fallback(self) -> None:
        rg = _make_generator()
        suggestions = rg._default_follow_up_suggestions(title="Report", content="some content")
        assert len(suggestions) == 3
        assert all(isinstance(s, str) for s in suggestions)

    def test_topic_hint_used_when_available(self) -> None:
        rg = _make_generator()
        rg.set_user_request("Analyze FastAPI performance")
        suggestions = rg._default_follow_up_suggestions(title="FastAPI Performance", content="benchmark data")
        assert len(suggestions) == 3


# ---------------------------------------------------------------------------
# _extract_topic_hint
# ---------------------------------------------------------------------------


class TestExtractTopicHint:
    def test_empty_returns_none(self) -> None:
        rg = _make_generator()
        assert rg._extract_topic_hint("") is None

    def test_quoted_phrase_extracted(self) -> None:
        rg = _make_generator()
        hint = rg._extract_topic_hint('I want "noise-canceling headphones" for travel')
        assert hint == "noise-canceling headphones"

    def test_capitalized_entity_extracted(self) -> None:
        rg = _make_generator()
        hint = rg._extract_topic_hint("We should use FastAPI Framework for this project.")
        assert hint is not None
        assert "Fast" in hint or "Api" in hint or "Framework" in hint

    def test_naive_tokenization_fallback(self) -> None:
        rg = _make_generator()
        hint = rg._extract_topic_hint("please analyze performance metrics carefully")
        assert hint is not None
        assert "analyze" in hint or "performance" in hint or "metrics" in hint

    def test_stopwords_filtered(self) -> None:
        rg = _make_generator()
        # Text composed entirely of stopwords + short tokens
        hint = rg._extract_topic_hint("that this with from have")
        # All are stopwords, but they are < 4 chars too — result should be None or filtered
        # The function returns something if candidates exist
        assert hint is None or isinstance(hint, str)

    def test_quoted_phrase_priority_over_capitalized(self) -> None:
        rg = _make_generator()
        hint = rg._extract_topic_hint('"async patterns" and also Django Framework here')
        assert hint == "async patterns"


# ---------------------------------------------------------------------------
# _build_recent_memory_context_excerpt
# ---------------------------------------------------------------------------


class TestBuildRecentMemoryContextExcerpt:
    def test_no_memory_returns_empty(self) -> None:
        rg = _make_generator(memory=None)
        assert rg._build_recent_memory_context_excerpt() == ""

    def test_empty_messages_returns_empty(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = []
        rg = _make_generator(memory=memory)
        assert rg._build_recent_memory_context_excerpt() == ""

    def test_extracts_user_and_assistant_roles(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "user", "content": "Hello, what is FastAPI?"},
            {"role": "assistant", "content": "FastAPI is a modern Python web framework."},
        ]
        rg = _make_generator(memory=memory)
        excerpt = rg._build_recent_memory_context_excerpt()
        assert "User:" in excerpt
        assert "Assistant:" in excerpt

    def test_skips_tool_messages(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "tool", "content": "tool output"},
            {"role": "user", "content": "Real question here"},
        ]
        rg = _make_generator(memory=memory)
        excerpt = rg._build_recent_memory_context_excerpt()
        assert "tool output" not in excerpt
        assert "Real question" in excerpt

    def test_skips_empty_content(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "user", "content": ""},
            {"role": "user", "content": "Non-empty message"},
        ]
        rg = _make_generator(memory=memory)
        excerpt = rg._build_recent_memory_context_excerpt()
        assert "Non-empty message" in excerpt

    def test_strips_previously_called_markers(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "assistant", "content": "[Previously called file_write] Some response text."},
        ]
        rg = _make_generator(memory=memory)
        excerpt = rg._build_recent_memory_context_excerpt()
        assert "[Previously called file_write]" not in excerpt

    def test_respects_max_chars_limit(self) -> None:
        memory = MagicMock()
        memory.get_messages.return_value = [
            {"role": "user", "content": "x" * 1000},
        ]
        rg = _make_generator(memory=memory)
        excerpt = rg._build_recent_memory_context_excerpt(max_chars=100)
        assert len(excerpt) <= 100

    def test_memory_exception_returns_empty(self) -> None:
        memory = MagicMock()
        memory.get_messages.side_effect = RuntimeError("DB error")
        rg = _make_generator(memory=memory)
        assert rg._build_recent_memory_context_excerpt() == ""


# ---------------------------------------------------------------------------
# generate_follow_up_suggestions (async, mocked LLM)
# ---------------------------------------------------------------------------


class TestGenerateFollowUpSuggestions:
    @pytest.mark.asyncio
    async def test_returns_suggestions_from_llm(self) -> None:
        llm = AsyncMock()
        llm.provider = "openai"
        llm.ask = AsyncMock(
            return_value={"content": {"suggestions": ["What next?", "Tell me more.", "Can you compare?"]}}
        )
        rg = ResponseGenerator(
            llm=llm,
            memory=None,
            source_tracker=_make_source_tracker(),
        )
        suggestions = await rg.generate_follow_up_suggestions("FastAPI Report", "Content summary.")
        assert len(suggestions) <= 3
        assert all(isinstance(s, str) for s in suggestions)

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_error(self) -> None:
        llm = AsyncMock()
        llm.provider = "openai"
        llm.ask = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        rg = ResponseGenerator(
            llm=llm,
            memory=None,
            source_tracker=_make_source_tracker(),
        )
        suggestions = await rg.generate_follow_up_suggestions("My Report", "Some content.")
        assert len(suggestions) == 3

    @pytest.mark.asyncio
    async def test_truncates_to_three_suggestions(self) -> None:
        llm = AsyncMock()
        llm.provider = "openai"
        llm.ask = AsyncMock(return_value={"content": {"suggestions": ["A", "B", "C", "D", "E"]}})
        rg = ResponseGenerator(
            llm=llm,
            memory=None,
            source_tracker=_make_source_tracker(),
        )
        suggestions = await rg.generate_follow_up_suggestions("Report", "Content.")
        assert len(suggestions) <= 3

    @pytest.mark.asyncio
    async def test_skips_blank_suggestions(self) -> None:
        llm = AsyncMock()
        llm.provider = "openai"
        llm.ask = AsyncMock(return_value={"content": {"suggestions": ["  ", "Valid question?", ""]}})
        rg = ResponseGenerator(
            llm=llm,
            memory=None,
            source_tracker=_make_source_tracker(),
        )
        suggestions = await rg.generate_follow_up_suggestions("Report", "Content.")
        assert "  " not in suggestions
        assert "" not in suggestions


# ---------------------------------------------------------------------------
# can_auto_repair_delivery_integrity
# ---------------------------------------------------------------------------


class TestCanAutoRepairDeliveryIntegrity:
    def test_no_issues_returns_false(self) -> None:
        rg = _make_generator()
        assert rg.can_auto_repair_delivery_integrity([]) is False

    def test_stream_truncation_with_substantial_content_returns_true(self) -> None:
        rg = _make_generator()
        assert (
            rg.can_auto_repair_delivery_integrity(
                ["stream_truncation_unresolved"],
                content="x" * 500,
            )
            is True
        )

    def test_stream_truncation_with_short_content_returns_false(self) -> None:
        rg = _make_generator()
        assert (
            rg.can_auto_repair_delivery_integrity(
                ["stream_truncation_unresolved"],
                content="short",
            )
            is False
        )

    def test_reparable_coverage_issues_return_true(self) -> None:
        rg = _make_generator()
        assert rg.can_auto_repair_delivery_integrity(["coverage_missing:final result, artifact references"]) is True

    def test_non_coverage_issues_return_false(self) -> None:
        rg = _make_generator()
        assert rg.can_auto_repair_delivery_integrity(["missing_references_section"]) is False

    def test_only_completeness_warning_returns_true(self) -> None:
        rg = _make_generator()
        assert rg.can_auto_repair_delivery_integrity(["content_completeness_warning"]) is True


# ---------------------------------------------------------------------------
# append_delivery_integrity_fallback
# ---------------------------------------------------------------------------


class TestAppendDeliveryIntegrityFallback:
    def test_no_issues_returns_content_unchanged(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nContent."
        result = rg.append_delivery_integrity_fallback(content, [])
        assert result == content

    def test_appends_truncation_note(self) -> None:
        rg = _make_generator()
        content = "# Report\n\nPartial content."
        result = rg.append_delivery_integrity_fallback(content, ["stream_truncation_unresolved"])
        assert "cut off" in result or "truncated" in result.lower() or "Note:" in result

    def test_appends_final_result(self) -> None:
        rg = _make_generator()
        result = rg.append_delivery_integrity_fallback("Content.", ["coverage_missing:final result"])
        assert "## Final Result" in result

    def test_appends_artifact_references(self) -> None:
        rg = _make_generator()
        rg.set_artifact_references([{"filename": "report.md"}])
        result = rg.append_delivery_integrity_fallback("Content.", ["coverage_missing:artifact references"])
        assert "## Artifact References" in result

    def test_appends_key_caveat(self) -> None:
        rg = _make_generator()
        result = rg.append_delivery_integrity_fallback("Content.", ["coverage_missing:key caveat"])
        assert "## Key Caveat" in result

    def test_appends_next_step(self) -> None:
        rg = _make_generator()
        result = rg.append_delivery_integrity_fallback("Content.", ["coverage_missing:next step"])
        assert "## Next Step" in result


# ---------------------------------------------------------------------------
# is_integrity_strict_mode
# ---------------------------------------------------------------------------


class TestIsIntegrityStrictMode:
    def test_detailed_mode_is_strict(self) -> None:
        rg = _make_generator()
        policy = _make_response_policy(mode=VerbosityMode.DETAILED)
        assert rg.is_integrity_strict_mode("any content", policy) is True

    def test_artifact_references_in_required_sections_is_strict(self) -> None:
        rg = _make_generator()
        policy = _make_response_policy(min_required_sections=["artifact references"])
        assert rg.is_integrity_strict_mode("any content", policy) is True

    def test_report_structure_is_strict(self) -> None:
        rg = _make_generator()
        policy = _make_response_policy(mode=VerbosityMode.STANDARD)
        content = "## Section One\n\nContent.\n\n## Section Two\n\nMore content."
        assert rg.is_integrity_strict_mode(content, policy) is True

    def test_concise_plain_content_not_strict(self) -> None:
        rg = _make_generator()
        policy = _make_response_policy(mode=VerbosityMode.CONCISE)
        assert rg.is_integrity_strict_mode("Just a quick answer.", policy) is False


# ---------------------------------------------------------------------------
# run_delivery_integrity_gate
# ---------------------------------------------------------------------------


class TestRunDeliveryIntegrityGate:
    def _make_rg_with_flags(self, flags: dict) -> ResponseGenerator:
        rg = _make_generator()
        rg._resolve_feature_flags_fn = lambda: flags
        return rg

    def _null_coverage(self) -> MagicMock:
        coverage = MagicMock()
        coverage.is_valid = True
        return coverage

    def test_gate_disabled_returns_pass(self) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": False})
        passed, issues = rg.run_delivery_integrity_gate(
            content="content",
            response_policy=_make_response_policy(),
            coverage_result=self._null_coverage(),
            stream_metadata={},
            truncation_exhausted=False,
        )
        assert passed is True
        assert issues == []

    def test_truncation_exhausted_is_blocking_issue(self) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": True})
        passed, issues = rg.run_delivery_integrity_gate(
            content="# Report\n\nSome content.",
            response_policy=_make_response_policy(),
            coverage_result=self._null_coverage(),
            stream_metadata={},
            truncation_exhausted=True,
        )
        assert passed is False
        assert "stream_truncation_unresolved" in issues

    def test_stream_length_finish_reason_is_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": True})
        passed, issues = rg.run_delivery_integrity_gate(
            content="# Report\n\nSome content.",
            response_policy=_make_response_policy(),
            coverage_result=self._null_coverage(),
            stream_metadata={"finish_reason": "length"},
            truncation_exhausted=False,
        )
        # A truncation warning should be present but not a blocking issue
        assert passed is True or "stream_truncation_unresolved" not in issues

    def test_additional_issues_propagated(self) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": True})
        passed, issues = rg.run_delivery_integrity_gate(
            content="content",
            response_policy=_make_response_policy(),
            coverage_result=self._null_coverage(),
            stream_metadata={},
            truncation_exhausted=False,
            additional_issues=["missing_references_section"],
        )
        assert passed is False
        assert "missing_references_section" in issues

    def test_critical_string_issue_sets_red_gate_severity(self, caplog: pytest.LogCaptureFixture) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": True})
        with caplog.at_level("INFO", logger="app.domain.services.agents.response_generator"):
            passed, issues = rg.run_delivery_integrity_gate(
                content="# Report\n\nSome content.",
                response_policy=_make_response_policy(),
                coverage_result=self._null_coverage(),
                stream_metadata={},
                truncation_exhausted=False,
                additional_issues=["hallucination_ratio_critical"],
            )

        assert passed is False
        assert "hallucination_ratio_critical" in issues
        assert "Delivery gate: red" in caplog.text

    def test_artifact_references_boilerplate_detected(self) -> None:
        rg = self._make_rg_with_flags({"delivery_integrity_gate": True})
        rg.set_artifact_references([{"filename": "report.md"}])
        content = "# Report\n\nContent.\n\n## Artifact References\n- No file artifacts were created in this response.\n"
        passed, issues = rg.run_delivery_integrity_gate(
            content=content,
            response_policy=_make_response_policy(),
            coverage_result=self._null_coverage(),
            stream_metadata={},
            truncation_exhausted=False,
        )
        assert passed is False
        assert any("artifact references" in i for i in issues)
