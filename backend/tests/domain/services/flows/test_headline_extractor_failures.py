"""Tests for headline extraction with failed tool results."""
from app.domain.services.flows.headline_extractor import extract_headline


class TestHeadlineExtractorFailures:
    """Empty tool results should indicate failure, not success."""

    def test_empty_result_shows_failure_not_success(self):
        headline = extract_headline("", tool_name="file_read")
        assert "completed" not in headline.lower()
        assert "no result" in headline.lower()

    def test_empty_result_includes_tool_name(self):
        headline = extract_headline("", tool_name="file_read")
        assert "file_read" in headline

    def test_whitespace_only_result_shows_failure(self):
        headline = extract_headline("   \n  ", tool_name="browser_navigate")
        assert "completed" not in headline.lower()
        assert "no result" in headline.lower()
