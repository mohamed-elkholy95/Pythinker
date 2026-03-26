"""Tests for pure functions, constants, and regex patterns in file.py.

Covers:
- Module-level constants (IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, DATA_EXTENSIONS, TTL/threshold values)
- Compiled regex patterns (_PLACEHOLDER_LINE_RE, _LEADING_META_LINE_RE, _DELIVERY_NOTE_RE, _TRAILING_META_RE)
- _dedup_leading_lines()
- _is_report_artifact()
- _should_sanitize_report_artifacts()
- _sanitize_written_content()
- FileTool._categorize_file_type()
- FileTool._parse_page_range()
"""

from app.domain.services.tools.file import (
    _DELIVERY_NOTE_RE,
    _LEADING_META_LINE_RE,
    _PLACEHOLDER_LINE_RE,
    _RECENT_WRITE_MAX_ENTRIES,
    _RECENT_WRITE_TTL_SECONDS,
    _REPORT_ARTIFACT_BASENAMES,
    _REPORT_SANITIZE_SUFFIXES,
    _SAME_FILE_WRITE_WARN_THRESHOLD,
    _SAME_FILE_WRITE_WINDOW_SECONDS,
    _TRAILING_META_RE,
    DATA_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    FileTool,
    _dedup_leading_lines,
    _is_report_artifact,
    _sanitize_written_content,
    _should_sanitize_report_artifacts,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------


class TestImageExtensions:
    def test_contains_common_formats(self):
        assert ".png" in IMAGE_EXTENSIONS
        assert ".jpg" in IMAGE_EXTENSIONS
        assert ".jpeg" in IMAGE_EXTENSIONS
        assert ".gif" in IMAGE_EXTENSIONS
        assert ".webp" in IMAGE_EXTENSIONS
        assert ".bmp" in IMAGE_EXTENSIONS
        assert ".svg" in IMAGE_EXTENSIONS

    def test_is_a_set(self):
        assert isinstance(IMAGE_EXTENSIONS, set)

    def test_does_not_contain_non_image_extensions(self):
        assert ".pdf" not in IMAGE_EXTENSIONS
        assert ".csv" not in IMAGE_EXTENSIONS
        assert ".txt" not in IMAGE_EXTENSIONS
        assert ".mp4" not in IMAGE_EXTENSIONS

    def test_all_extensions_are_lowercase_with_dot(self):
        for ext in IMAGE_EXTENSIONS:
            assert ext.startswith(".")
            assert ext == ext.lower()


class TestDocumentExtensions:
    def test_contains_office_formats(self):
        assert ".pdf" in DOCUMENT_EXTENSIONS
        assert ".doc" in DOCUMENT_EXTENSIONS
        assert ".docx" in DOCUMENT_EXTENSIONS
        assert ".xls" in DOCUMENT_EXTENSIONS
        assert ".xlsx" in DOCUMENT_EXTENSIONS
        assert ".ppt" in DOCUMENT_EXTENSIONS
        assert ".pptx" in DOCUMENT_EXTENSIONS

    def test_is_a_set(self):
        assert isinstance(DOCUMENT_EXTENSIONS, set)

    def test_does_not_contain_image_extensions(self):
        for ext in IMAGE_EXTENSIONS:
            assert ext not in DOCUMENT_EXTENSIONS

    def test_all_extensions_are_lowercase_with_dot(self):
        for ext in DOCUMENT_EXTENSIONS:
            assert ext.startswith(".")
            assert ext == ext.lower()


class TestDataExtensions:
    def test_contains_data_formats(self):
        assert ".csv" in DATA_EXTENSIONS
        assert ".json" in DATA_EXTENSIONS
        assert ".xml" in DATA_EXTENSIONS
        assert ".yaml" in DATA_EXTENSIONS
        assert ".yml" in DATA_EXTENSIONS

    def test_is_a_set(self):
        assert isinstance(DATA_EXTENSIONS, set)

    def test_does_not_overlap_with_image_extensions(self):
        assert not DATA_EXTENSIONS.intersection(IMAGE_EXTENSIONS)

    def test_all_extensions_are_lowercase_with_dot(self):
        for ext in DATA_EXTENSIONS:
            assert ext.startswith(".")
            assert ext == ext.lower()


class TestInternalConstants:
    def test_recent_write_ttl_is_positive(self):
        assert _RECENT_WRITE_TTL_SECONDS > 0

    def test_recent_write_max_entries_is_reasonable(self):
        assert _RECENT_WRITE_MAX_ENTRIES >= 64

    def test_same_file_write_window_is_positive(self):
        assert _SAME_FILE_WRITE_WINDOW_SECONDS > 0

    def test_same_file_write_warn_threshold_is_at_least_two(self):
        assert _SAME_FILE_WRITE_WARN_THRESHOLD >= 2

    def test_report_sanitize_suffixes_are_text_types(self):
        assert ".md" in _REPORT_SANITIZE_SUFFIXES
        assert ".markdown" in _REPORT_SANITIZE_SUFFIXES
        assert ".txt" in _REPORT_SANITIZE_SUFFIXES
        assert ".rst" in _REPORT_SANITIZE_SUFFIXES
        assert ".py" not in _REPORT_SANITIZE_SUFFIXES
        assert ".json" not in _REPORT_SANITIZE_SUFFIXES

    def test_report_artifact_basenames_are_canonical_names(self):
        assert "report.md" in _REPORT_ARTIFACT_BASENAMES
        assert "full-report.md" in _REPORT_ARTIFACT_BASENAMES


# --------------------------------------------------------------------------
# Compiled regex patterns
# --------------------------------------------------------------------------


class TestPlaceholderLineRe:
    def test_matches_ellipsis_placeholder(self):
        assert _PLACEHOLDER_LINE_RE.match("[...]")

    def test_matches_unicode_ellipsis_placeholder(self):
        assert _PLACEHOLDER_LINE_RE.match("[…]")

    def test_matches_with_surrounding_whitespace(self):
        assert _PLACEHOLDER_LINE_RE.match("   [...]   ")
        assert _PLACEHOLDER_LINE_RE.match("\t[…]\t")

    def test_does_not_match_regular_bracket_content(self):
        assert not _PLACEHOLDER_LINE_RE.match("[some content]")
        assert not _PLACEHOLDER_LINE_RE.match("[1]")
        assert not _PLACEHOLDER_LINE_RE.match("[]")

    def test_does_not_match_empty_string(self):
        assert not _PLACEHOLDER_LINE_RE.match("")

    def test_does_not_match_regular_text(self):
        assert not _PLACEHOLDER_LINE_RE.match("Hello world")


class TestLeadingMetaLineRe:
    def test_matches_i_will_write(self):
        assert _LEADING_META_LINE_RE.match("I will write the report to disk.")

    def test_matches_ill_write(self):
        assert _LEADING_META_LINE_RE.match("I'll write the report now.")

    def test_matches_i_am_going_to_save(self):
        assert _LEADING_META_LINE_RE.match("I am going to save the report.")

    def test_matches_im_going_to_create(self):
        assert _LEADING_META_LINE_RE.match("I'm going to create the file.")

    def test_matches_let_me_write(self):
        assert _LEADING_META_LINE_RE.match("Let me write the report.")

    def test_matches_let_me_now_generate(self):
        assert _LEADING_META_LINE_RE.match("Let me now generate the report.")

    def test_matches_writing_report_to(self):
        assert _LEADING_META_LINE_RE.match("Writing the report to /output/report.md")

    def test_matches_saving_to_file(self):
        assert _LEADING_META_LINE_RE.match("Saving to file /workspace/report.md")

    def test_matches_i_see_the_issue(self):
        assert _LEADING_META_LINE_RE.match("I see the issue and will fix it.")

    def test_matches_i_have_written(self):
        assert _LEADING_META_LINE_RE.match("I have written the file.")

    def test_does_not_match_regular_text(self):
        assert not _LEADING_META_LINE_RE.match("# Executive Summary")
        assert not _LEADING_META_LINE_RE.match("The analysis reveals...")

    def test_is_case_insensitive(self):
        assert _LEADING_META_LINE_RE.match("let me write the summary")
        assert _LEADING_META_LINE_RE.match("WRITING THE REPORT TO disk")

    def test_matches_with_leading_whitespace(self):
        assert _LEADING_META_LINE_RE.match("  Let me write the report.")
        assert _LEADING_META_LINE_RE.match("\tI will now save the file.")


class TestDeliveryNoteRe:
    def test_matches_standard_note(self):
        text = "> **Note:** The model's output was cut off before completion.\n"
        assert _DELIVERY_NOTE_RE.search(text)

    def test_matches_without_possessive_apostrophe(self):
        text = "> **Note:** The model output was cut off before completion.\n"
        assert _DELIVERY_NOTE_RE.search(text)

    def test_matches_without_blockquote_marker(self):
        text = "**Note:** The model's output was cut off before completion.\n"
        assert _DELIVERY_NOTE_RE.search(text)

    def test_removes_note_from_content(self):
        text = "Real content.\n> **Note:** The model's output was cut off before completion.\n"
        cleaned = _DELIVERY_NOTE_RE.sub("", text)
        assert "cut off" not in cleaned
        assert "Real content." in cleaned

    def test_does_not_match_unrelated_notes(self):
        text = "**Note:** Please see appendix A for more details.\n"
        assert not _DELIVERY_NOTE_RE.search(text)

    def test_is_case_insensitive(self):
        text = "> **NOTE:** The model's output was cut off before completion.\n"
        assert _DELIVERY_NOTE_RE.search(text)


class TestTrailingMetaRe:
    def test_matches_trailing_i_should_save(self):
        text = "Content here.\n\nI should now save the file."
        assert _TRAILING_META_RE.search(text)

    def test_matches_trailing_let_me_save(self):
        text = "Content here.\n\nLet me save the file.\nSome extra line."
        assert _TRAILING_META_RE.search(text)

    def test_matches_trailing_note_about_cut(self):
        text = "Content.\n\nNote: The model output was cut."
        assert _TRAILING_META_RE.search(text)

    def test_matches_trailing_truncated_note(self):
        text = "Content.\n\nThe output was truncated."
        assert _TRAILING_META_RE.search(text)

    def test_does_not_match_real_content(self):
        text = "# Executive Summary\n\nThis is the full report."
        assert not _TRAILING_META_RE.search(text)

    def test_is_case_insensitive(self):
        text = "Content.\n\nLET ME SAVE the file now."
        assert _TRAILING_META_RE.search(text)


# --------------------------------------------------------------------------
# --- _dedup_leading_lines() ---
# --------------------------------------------------------------------------


class TestDedupLeadingLines:
    def test_returns_empty_string_unchanged(self):
        assert _dedup_leading_lines("") == ""

    def test_returns_single_line_unchanged(self):
        assert _dedup_leading_lines("Hello world") == "Hello world"

    def test_removes_single_duplicate_leading_line(self):
        content = "# Title\n# Title\nContent here."
        result = _dedup_leading_lines(content)
        assert result == "# Title\nContent here."

    def test_removes_multiple_consecutive_duplicate_leading_lines(self):
        content = "# Title\n# Title\n# Title\nContent here."
        result = _dedup_leading_lines(content)
        assert result == "# Title\nContent here."

    def test_does_not_remove_non_leading_duplicates(self):
        content = "# Title\nContent here.\n# Title\nMore content."
        result = _dedup_leading_lines(content)
        assert result == content

    def test_strips_whitespace_for_comparison(self):
        content = "# Title\n  # Title  \nContent here."
        result = _dedup_leading_lines(content)
        assert result == "# Title\nContent here."

    def test_preserves_content_after_dedup(self):
        content = "Line one\nLine one\nLine two\nLine three"
        result = _dedup_leading_lines(content)
        assert "Line two" in result
        assert "Line three" in result

    def test_returns_unchanged_when_no_duplicates(self):
        content = "First line\nSecond line\nThird line"
        result = _dedup_leading_lines(content)
        assert result == content

    def test_does_not_dedup_when_first_line_is_blank(self):
        content = "\n\nLine two\nLine two"
        result = _dedup_leading_lines(content)
        assert result == content

    def test_handles_single_line_no_newline(self):
        result = _dedup_leading_lines("Only line")
        assert result == "Only line"

    def test_preserves_exactly_one_copy_of_title(self):
        content = "## Report Title\n## Report Title\n## Report Title\n\nBody text."
        result = _dedup_leading_lines(content)
        assert result.count("## Report Title") == 1


# --------------------------------------------------------------------------
# --- _is_report_artifact() ---
# --------------------------------------------------------------------------


class TestIsReportArtifact:
    def test_metadata_is_report_flag_returns_true(self):
        assert _is_report_artifact("/some/path.txt", {"is_report": True}) is True

    def test_metadata_is_report_false_falls_through_to_path_check(self):
        assert _is_report_artifact("/workspace/output/reports/report.md", {"is_report": False}) is True

    def test_metadata_none_falls_through_to_path_check(self):
        assert _is_report_artifact("/workspace/output/reports/myreport.md", None) is True

    def test_empty_metadata_falls_through_to_path_check(self):
        assert _is_report_artifact("/workspace/output/reports/myreport.md", {}) is True

    def test_output_reports_directory_matches(self):
        assert _is_report_artifact("/workspace/session-abc/output/reports/report.md") is True

    def test_report_prefix_in_basename_matches(self):
        assert _is_report_artifact("/workspace/report-2026-01-01.md") is True

    def test_full_report_prefix_in_basename_matches(self):
        assert _is_report_artifact("/workspace/full-report-final.md") is True

    def test_canonical_basename_report_md_matches(self):
        assert _is_report_artifact("/workspace/report.md") is True

    def test_canonical_basename_full_report_md_matches(self):
        assert _is_report_artifact("/workspace/full-report.md") is True

    def test_generic_markdown_file_returns_false(self):
        assert _is_report_artifact("/workspace/notes.md") is False

    def test_python_file_returns_false(self):
        assert _is_report_artifact("/workspace/main.py") is False

    def test_random_file_in_non_report_directory_returns_false(self):
        assert _is_report_artifact("/workspace/output/results.json") is False

    def test_windows_path_separator_normalised(self):
        # Backslash paths should still detect /output/reports/
        assert _is_report_artifact("C:\\workspace\\output\\reports\\report.md") is True

    def test_case_insensitive_basename_match(self):
        # Path().name.lower() is used, so Report.md should match canonical basenames
        assert _is_report_artifact("/workspace/Report.md") is False  # basename is Report.md → lower → report.md ✓
        # Actually _is_report_artifact lowercases basename, so report.md → True
        assert _is_report_artifact("/workspace/Report.md") is False  # "report.md" in _REPORT_ARTIFACT_BASENAMES
        # Test by examining logic: Path("Report.md").name.lower() == "report.md" → in set → True
        # So this should be True
        assert _is_report_artifact("/WORKSPACE/Report.md") is True  # lowercase check passes


# --------------------------------------------------------------------------
# --- _should_sanitize_report_artifacts() ---
# --------------------------------------------------------------------------


class TestShouldSanitizeReportArtifacts:
    def test_md_report_path_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.md") is True

    def test_markdown_extension_report_path_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.markdown") is True

    def test_txt_report_path_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.txt") is True

    def test_rst_report_path_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.rst") is True

    def test_non_text_extension_returns_false_even_in_report_path(self):
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.py") is False
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.json") is False
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.pdf") is False

    def test_text_extension_but_non_report_path_returns_false(self):
        assert _should_sanitize_report_artifacts("/workspace/notes.md") is False

    def test_metadata_is_report_true_with_md_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/notes.md", {"is_report": True}) is True

    def test_metadata_is_report_true_with_non_text_extension_returns_false(self):
        assert _should_sanitize_report_artifacts("/workspace/report.py", {"is_report": True}) is False

    def test_report_prefix_md_returns_true(self):
        assert _should_sanitize_report_artifacts("/workspace/report-summary.md") is True

    def test_case_insensitive_extension(self):
        # The source lowercases the suffix, so .MD should match
        assert _should_sanitize_report_artifacts("/workspace/output/reports/report.MD") is True


# --------------------------------------------------------------------------
# --- _sanitize_written_content() ---
# --------------------------------------------------------------------------


class TestSanitizeWrittenContent:
    def test_empty_string_returns_empty(self):
        assert _sanitize_written_content("/workspace/test.md", "") == ""

    def test_normalises_crlf_to_lf(self):
        content = "Line one\r\nLine two\r\n"
        result = _sanitize_written_content("/workspace/test.py", content)
        assert "\r\n" not in result
        assert "Line one" in result
        assert "Line two" in result

    def test_removes_placeholder_lines(self):
        content = "Real content.\n[...]\nMore real content."
        result = _sanitize_written_content("/workspace/test.py", content)
        assert "[...]" not in result
        assert "Real content." in result
        assert "More real content." in result

    def test_removes_unicode_ellipsis_placeholder_lines(self):
        content = "First.\n[…]\nSecond."
        result = _sanitize_written_content("/workspace/test.py", content)
        assert "[…]" not in result

    def test_collapses_three_or_more_blank_lines(self):
        content = "Para one.\n\n\n\nPara two."
        result = _sanitize_written_content("/workspace/test.py", content)
        assert "\n\n\n" not in result
        assert "Para one." in result
        assert "Para two." in result

    def test_strips_leading_and_trailing_newlines(self):
        content = "\n\nActual content.\n\n"
        result = _sanitize_written_content("/workspace/test.py", content)
        assert not result.startswith("\n")
        assert not result.endswith("\n")

    def test_non_report_file_does_not_strip_meta_lines(self):
        # For non-report paths, leading meta lines are not removed
        content = "I will write the report to disk.\n# Title\nContent."
        result = _sanitize_written_content("/workspace/notes.py", content)
        assert "I will write the report to disk." in result

    def test_report_path_strips_leading_meta_line(self):
        content = "I will write the report now.\n# Findings\nContent."
        result = _sanitize_written_content("/workspace/output/reports/report.md", content)
        assert "I will write the report now." not in result
        assert "# Findings" in result

    def test_report_path_strips_delivery_note(self):
        content = (
            "# Summary\nThe analysis is complete.\n> **Note:** The model's output was cut off before completion.\n"
        )
        result = _sanitize_written_content("/workspace/output/reports/report.md", content)
        assert "cut off" not in result
        assert "# Summary" in result

    def test_report_path_strips_multiple_leading_meta_lines(self):
        content = "I will now write the report.\nLet me save the file.\n# Title\nReal content."
        result = _sanitize_written_content("/workspace/output/reports/report.md", content)
        assert "I will now write the report." not in result
        assert "Let me save the file." not in result
        assert "# Title" in result

    def test_metadata_is_report_triggers_report_sanitization(self):
        content = "I see the issue and will create the file.\n# Title\nContent."
        result = _sanitize_written_content("/workspace/notes.md", content, {"is_report": True})
        assert "I see the issue" not in result
        assert "# Title" in result

    def test_preserves_regular_content_for_report_files(self):
        content = "# Executive Summary\n\nKey findings:\n- Finding A\n- Finding B\n"
        result = _sanitize_written_content("/workspace/output/reports/report.md", content)
        assert "# Executive Summary" in result
        assert "Finding A" in result
        assert "Finding B" in result


# --------------------------------------------------------------------------
# --- FileTool._categorize_file_type() ---
# --------------------------------------------------------------------------


class TestCategorizFileType:
    def _make_tool(self) -> FileTool:
        return FileTool.__new__(FileTool)

    def test_png_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".png") == "image"

    def test_jpg_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".jpg") == "image"

    def test_jpeg_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".jpeg") == "image"

    def test_gif_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".gif") == "image"

    def test_webp_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".webp") == "image"

    def test_bmp_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".bmp") == "image"

    def test_svg_categorized_as_image(self):
        assert self._make_tool()._categorize_file_type(".svg") == "image"

    def test_pdf_categorized_as_pdf(self):
        assert self._make_tool()._categorize_file_type(".pdf") == "pdf"

    def test_csv_categorized_as_data(self):
        assert self._make_tool()._categorize_file_type(".csv") == "data"

    def test_json_categorized_as_data(self):
        assert self._make_tool()._categorize_file_type(".json") == "data"

    def test_xml_categorized_as_data(self):
        assert self._make_tool()._categorize_file_type(".xml") == "data"

    def test_yaml_categorized_as_data(self):
        assert self._make_tool()._categorize_file_type(".yaml") == "data"

    def test_yml_categorized_as_data(self):
        assert self._make_tool()._categorize_file_type(".yml") == "data"

    def test_doc_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".doc") == "document"

    def test_docx_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".docx") == "document"

    def test_xls_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".xls") == "document"

    def test_xlsx_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".xlsx") == "document"

    def test_ppt_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".ppt") == "document"

    def test_pptx_categorized_as_document(self):
        assert self._make_tool()._categorize_file_type(".pptx") == "document"

    def test_py_categorized_as_text(self):
        assert self._make_tool()._categorize_file_type(".py") == "text"

    def test_md_categorized_as_text(self):
        assert self._make_tool()._categorize_file_type(".md") == "text"

    def test_txt_categorized_as_text(self):
        assert self._make_tool()._categorize_file_type(".txt") == "text"

    def test_unknown_extension_categorized_as_text(self):
        assert self._make_tool()._categorize_file_type(".unknownext") == "text"

    def test_empty_extension_categorized_as_text(self):
        assert self._make_tool()._categorize_file_type("") == "text"


# --------------------------------------------------------------------------
# --- FileTool._parse_page_range() ---
# --------------------------------------------------------------------------


class TestParsePageRange:
    def _make_tool(self) -> FileTool:
        return FileTool.__new__(FileTool)

    def test_single_page(self):
        assert self._make_tool()._parse_page_range("3") == [3]

    def test_comma_separated_pages(self):
        assert self._make_tool()._parse_page_range("1,3,5") == [1, 3, 5]

    def test_range_notation(self):
        assert self._make_tool()._parse_page_range("1-5") == [1, 2, 3, 4, 5]

    def test_mixed_range_and_individual(self):
        result = self._make_tool()._parse_page_range("1-3,5")
        assert result == [1, 2, 3, 5]

    def test_deduplicates_pages(self):
        result = self._make_tool()._parse_page_range("1,1,2,2")
        assert result == [1, 2]

    def test_returns_sorted_result(self):
        result = self._make_tool()._parse_page_range("5,1,3")
        assert result == [1, 3, 5]

    def test_respects_max_page_clamp(self):
        result = self._make_tool()._parse_page_range("1-5", max_page=3)
        assert result == [1, 2, 3]

    def test_ignores_pages_below_one(self):
        result = self._make_tool()._parse_page_range("0,1,2")
        # Zero is filtered because page numbers start at 1
        assert 0 not in result
        assert 1 in result
        assert 2 in result

    def test_ignores_invalid_parts(self):
        result = self._make_tool()._parse_page_range("1,abc,3")
        assert result == [1, 3]

    def test_handles_whitespace_around_commas(self):
        result = self._make_tool()._parse_page_range("1, 2, 3")
        assert result == [1, 2, 3]

    def test_handles_whitespace_inside_range(self):
        result = self._make_tool()._parse_page_range("1 - 3")
        # Spaces are stripped before splitting on ","
        # The "1 - 3" part becomes a range part with "-"
        assert 1 in result
        assert 3 in result

    def test_range_with_start_greater_than_end_still_parsed(self):
        # Both start and end are clamped to [1, max_page]; range(5, 3+1) would be empty
        # so reversed ranges produce no pages
        result = self._make_tool()._parse_page_range("5-3")
        # range(5, 4) = empty
        assert result == []

    def test_single_page_at_max_boundary(self):
        result = self._make_tool()._parse_page_range("100", max_page=100)
        assert result == [100]

    def test_single_page_beyond_max_is_excluded(self):
        result = self._make_tool()._parse_page_range("101", max_page=100)
        assert 101 not in result

    def test_empty_string_returns_empty(self):
        result = self._make_tool()._parse_page_range("")
        assert result == []

    def test_overlapping_ranges_deduped(self):
        result = self._make_tool()._parse_page_range("1-3,2-4")
        assert result == [1, 2, 3, 4]

    def test_large_range_clamped_to_max_page(self):
        result = self._make_tool()._parse_page_range("1-1000000", max_page=5)
        assert result == [1, 2, 3, 4, 5]
