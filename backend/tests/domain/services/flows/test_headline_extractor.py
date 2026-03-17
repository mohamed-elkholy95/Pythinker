"""Tests for extracting one-line headlines from tool results."""

from app.domain.services.flows.headline_extractor import extract_headline


def test_search_result_headline() -> None:
    tool_result = "Found 12 results for 'renewable energy trends':\n1. Solar power growth...\n2. Wind energy..."
    headline = extract_headline(tool_result, tool_name="web_search")
    assert "12" in headline or "renewable" in headline.lower()
    assert len(headline) <= 120


def test_browser_result_headline() -> None:
    tool_result = "Navigated to https://example.com/article\nPage title: Understanding AI Agents"
    headline = extract_headline(tool_result, tool_name="browser_navigate")
    assert "AI Agents" in headline or "example.com" in headline


def test_empty_result_headline() -> None:
    headline = extract_headline("", tool_name="web_search")
    assert headline
    assert "web_search" in headline


def test_long_result_truncated() -> None:
    tool_result = "A" * 500
    headline = extract_headline(tool_result, tool_name="terminal")
    assert len(headline) <= 120


def test_default_first_line() -> None:
    tool_result = "Command executed successfully\nOutput: data.csv created"
    headline = extract_headline(tool_result)
    assert headline == "Command executed successfully"


def test_whitespace_only_result() -> None:
    headline = extract_headline("   \n\t  ", tool_name="shell")
    assert "shell" in headline
    assert "completed" in headline


def test_search_result_no_tool_name() -> None:
    tool_result = "Found 5 results for 'python asyncio':\n1. Real Python tutorial"
    headline = extract_headline(tool_result)
    assert "Found 5 results" in headline
    assert len(headline) <= 120


def test_browser_title_extracted() -> None:
    tool_result = "Status: 200\nTitle: GitHub - Python asyncio documentation"
    headline = extract_headline(tool_result, tool_name="browser")
    assert "Visited:" in headline
    assert "GitHub" in headline


def test_exactly_120_chars_not_truncated() -> None:
    tool_result = "B" * 120
    headline = extract_headline(tool_result)
    assert len(headline) == 120
    assert "..." not in headline


def test_long_line_gets_ellipsis() -> None:
    tool_result = "C" * 200
    headline = extract_headline(tool_result)
    assert headline.endswith("...")
    assert len(headline) == 120


def test_no_tool_name_fallback() -> None:
    headline = extract_headline("", tool_name="")
    assert "Tool" in headline
    assert "completed" in headline


def test_multiline_skips_blank_lines() -> None:
    tool_result = "\n\n\nActual content here\nSecond line"
    headline = extract_headline(tool_result)
    assert headline == "Actual content here"
