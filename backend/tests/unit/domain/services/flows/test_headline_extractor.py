"""Tests for headline extraction from tool results."""

from __future__ import annotations

from app.domain.services.flows.headline_extractor import extract_headline


class TestExtractHeadline:
    """Tests for extract_headline function."""

    def test_empty_string_returns_default(self) -> None:
        result = extract_headline("")
        assert result == "Tool completed (no output)"

    def test_empty_string_with_tool_name(self) -> None:
        result = extract_headline("", tool_name="info_search_web")
        assert result == "info_search_web completed (no output)"

    def test_whitespace_only_returns_default(self) -> None:
        result = extract_headline("   \n  \t  ")
        assert result == "Tool completed (no output)"

    def test_search_results_pattern(self) -> None:
        text = "Found 15 results for 'python asyncio'\nResult 1: ..."
        result = extract_headline(text)
        assert result == "Found 15 results for 'python asyncio'"

    def test_search_single_result(self) -> None:
        text = "Found 1 result for 'specific query'"
        result = extract_headline(text)
        assert result == "Found 1 result for 'specific query'"

    def test_browser_page_title(self) -> None:
        text = "Page title: Example Domain\nContent: ..."
        result = extract_headline(text)
        assert result.startswith("Visited: Example Domain")

    def test_browser_title_variant(self) -> None:
        text = "Title: My Website - Home\nBody content here"
        result = extract_headline(text)
        assert result == "Visited: My Website - Home"

    def test_default_first_line(self) -> None:
        text = "Some tool output\nMore details\nEven more"
        result = extract_headline(text)
        assert result == "Some tool output"

    def test_truncation_at_120_chars(self) -> None:
        long_line = "A" * 200
        result = extract_headline(long_line)
        assert len(result) <= 120
        assert result.endswith("...")

    def test_skips_empty_lines(self) -> None:
        text = "\n\n\nActual content here\nMore lines"
        result = extract_headline(text)
        assert result == "Actual content here"

    def test_all_empty_lines_returns_completed(self) -> None:
        text = "   \n   \n   "
        result = extract_headline(text, tool_name="browser_navigate")
        assert result == "browser_navigate completed (no output)"

    def test_search_count_long_first_line_truncated(self) -> None:
        long_first = "Found 5 results " + "x" * 200
        result = extract_headline(long_first)
        assert len(result) <= 120

    def test_page_title_long_truncated(self) -> None:
        text = "Page title: " + "Y" * 200
        result = extract_headline(text)
        assert len(result) <= 120

    def test_no_tool_name_default(self) -> None:
        result = extract_headline("")
        assert "Tool" in result

    def test_multiline_first_nonempty(self) -> None:
        text = "\n\nFirst real line\nSecond line"
        result = extract_headline(text)
        assert result == "First real line"

    def test_exact_120_chars_not_truncated(self) -> None:
        line = "B" * 120
        result = extract_headline(line)
        assert result == line
        assert "..." not in result

    def test_121_chars_truncated(self) -> None:
        line = "C" * 121
        result = extract_headline(line)
        assert len(result) == 120
        assert result.endswith("...")
