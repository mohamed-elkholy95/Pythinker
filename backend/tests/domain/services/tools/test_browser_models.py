"""Tests for browser.py — enum, constants, and pure utility functions.

Covers:
- BrowserIntent enum values and string membership
- BROWSER_INTENT_CONFIG structure and per-intent semantics
- OPEN_ACCESS_DOMAINS constant membership
- html_to_text() pure conversion function
- BrowserTool._normalize_url_for_visit_tracking() classmethod
- BrowserTool._extract_focused_content() instance method
"""

from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

from app.domain.services.tools.browser import (
    BROWSER_INTENT_CONFIG,
    OPEN_ACCESS_DOMAINS,
    BrowserIntent,
    BrowserTool,
    html_to_text,
)

# ---------------------------------------------------------------------------
# BrowserIntent enum
# ---------------------------------------------------------------------------


class TestBrowserIntentEnum:
    def test_navigational_value(self) -> None:
        assert BrowserIntent.NAVIGATIONAL.value == "navigational"

    def test_informational_value(self) -> None:
        assert BrowserIntent.INFORMATIONAL.value == "informational"

    def test_transactional_value(self) -> None:
        assert BrowserIntent.TRANSACTIONAL.value == "transactional"

    def test_all_members_present(self) -> None:
        names = {m.name for m in BrowserIntent}
        assert names == {"NAVIGATIONAL", "INFORMATIONAL", "TRANSACTIONAL"}

    def test_is_str_subclass(self) -> None:
        assert isinstance(BrowserIntent.NAVIGATIONAL, str)
        assert BrowserIntent.INFORMATIONAL == "informational"

    def test_lookup_by_value(self) -> None:
        assert BrowserIntent("navigational") is BrowserIntent.NAVIGATIONAL
        assert BrowserIntent("informational") is BrowserIntent.INFORMATIONAL
        assert BrowserIntent("transactional") is BrowserIntent.TRANSACTIONAL

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            BrowserIntent("unknown")

    def test_case_sensitivity(self) -> None:
        with pytest.raises(ValueError):
            BrowserIntent("Navigational")


# ---------------------------------------------------------------------------
# BROWSER_INTENT_CONFIG constant
# ---------------------------------------------------------------------------


class TestBrowserIntentConfig:
    def test_all_intents_have_entries(self) -> None:
        for intent in BrowserIntent:
            assert intent in BROWSER_INTENT_CONFIG, f"Missing config for {intent}"

    def test_navigational_config_keys(self) -> None:
        cfg = BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL]
        assert "auto_scroll" in cfg
        assert "extract_interactive" in cfg
        assert "extract_content" in cfg
        assert "wait_for_network_idle" in cfg
        assert "max_content_length" in cfg

    def test_informational_config_keys(self) -> None:
        cfg = BROWSER_INTENT_CONFIG[BrowserIntent.INFORMATIONAL]
        assert "auto_scroll" in cfg
        assert "extract_interactive" in cfg
        assert "extract_content" in cfg
        assert "wait_for_network_idle" in cfg
        assert "max_content_length" in cfg

    def test_transactional_config_keys(self) -> None:
        cfg = BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]
        assert "auto_scroll" in cfg
        assert "extract_interactive" in cfg
        assert "extract_content" in cfg
        assert "wait_for_network_idle" in cfg
        assert "max_content_length" in cfg

    def test_navigational_extracts_content(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL]["extract_content"] is True

    def test_navigational_extracts_interactive(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL]["extract_interactive"] is True

    def test_informational_focus_on_content_not_interactions(self) -> None:
        cfg = BROWSER_INTENT_CONFIG[BrowserIntent.INFORMATIONAL]
        assert cfg["extract_content"] is True
        assert cfg["extract_interactive"] is False

    def test_informational_waits_for_network_idle(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.INFORMATIONAL]["wait_for_network_idle"] is True

    def test_informational_max_content_length_largest(self) -> None:
        nav = BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL]["max_content_length"]
        info = BROWSER_INTENT_CONFIG[BrowserIntent.INFORMATIONAL]["max_content_length"]
        trans = BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["max_content_length"]
        assert info > nav, "Informational should allow more content than navigational"
        assert info > trans, "Informational should allow more content than transactional"

    def test_transactional_does_not_scroll(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["auto_scroll"] is False

    def test_transactional_extracts_interactive_elements(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["extract_interactive"] is True

    def test_transactional_does_not_extract_content(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["extract_content"] is False

    def test_transactional_waits_for_network_idle(self) -> None:
        assert BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["wait_for_network_idle"] is True

    def test_transactional_max_content_length_smallest(self) -> None:
        nav = BROWSER_INTENT_CONFIG[BrowserIntent.NAVIGATIONAL]["max_content_length"]
        trans = BROWSER_INTENT_CONFIG[BrowserIntent.TRANSACTIONAL]["max_content_length"]
        assert trans < nav, "Transactional should have the smallest max_content_length"

    def test_max_content_length_positive_integers(self) -> None:
        for intent, cfg in BROWSER_INTENT_CONFIG.items():
            val = cfg["max_content_length"]
            assert isinstance(val, int), f"{intent}: max_content_length must be int"
            assert val > 0, f"{intent}: max_content_length must be positive"


# ---------------------------------------------------------------------------
# OPEN_ACCESS_DOMAINS constant
# ---------------------------------------------------------------------------


class TestOpenAccessDomains:
    def test_is_set(self) -> None:
        assert isinstance(OPEN_ACCESS_DOMAINS, set)

    def test_nonempty(self) -> None:
        assert len(OPEN_ACCESS_DOMAINS) > 0

    def test_known_open_domains_present(self) -> None:
        expected = {
            "docs.python.org",
            "github.com",
            "en.wikipedia.org",
            "stackoverflow.com",
            "arxiv.org",
            "pypi.org",
            "docs.pydantic.dev",
            "fastapi.tiangolo.com",
        }
        for domain in expected:
            assert domain in OPEN_ACCESS_DOMAINS, f"Expected {domain} in OPEN_ACCESS_DOMAINS"

    def test_all_entries_are_strings(self) -> None:
        for domain in OPEN_ACCESS_DOMAINS:
            assert isinstance(domain, str), f"Domain entry must be str, got {type(domain)}"

    def test_no_empty_entries(self) -> None:
        for domain in OPEN_ACCESS_DOMAINS:
            assert domain.strip(), "Empty string found in OPEN_ACCESS_DOMAINS"

    def test_no_scheme_prefixes(self) -> None:
        for domain in OPEN_ACCESS_DOMAINS:
            assert not urlparse(domain).scheme, f"Domain {domain!r} should not have scheme prefix"

    def test_no_trailing_slashes(self) -> None:
        for domain in OPEN_ACCESS_DOMAINS:
            assert not domain.endswith("/"), f"Domain {domain!r} must not have trailing slash"


# ---------------------------------------------------------------------------
# html_to_text() pure function
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_plain_text_passthrough(self) -> None:
        result = html_to_text("Hello world")
        assert "Hello world" in result

    def test_strips_script_tags(self) -> None:
        html = "<script>alert('xss')</script>Hello"
        result = html_to_text(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_strips_style_tags(self) -> None:
        html = "<style>body { color: red }</style>Content"
        result = html_to_text(html)
        assert "color" not in result
        assert "Content" in result

    def test_strips_html_comments(self) -> None:
        html = "<!-- hidden -->visible"
        result = html_to_text(html)
        assert "hidden" not in result
        assert "visible" in result

    def test_converts_h1_to_markdown(self) -> None:
        html = "<h1>Main Title</h1>"
        result = html_to_text(html)
        assert "# Main Title" in result

    def test_converts_h2_to_markdown(self) -> None:
        html = "<h2>Sub Title</h2>"
        result = html_to_text(html)
        assert "## Sub Title" in result

    def test_converts_h3_to_markdown(self) -> None:
        html = "<h3>Section</h3>"
        result = html_to_text(html)
        assert "### Section" in result

    def test_converts_anchor_to_markdown_link(self) -> None:
        html = '<a href="https://example.com">click here</a>'
        result = html_to_text(html)
        assert "[click here](https://example.com)" in result

    def test_converts_list_items_to_bullet(self) -> None:
        html = "<ul><li>Item one</li><li>Item two</li></ul>"
        result = html_to_text(html)
        assert "- Item one" in result
        assert "- Item two" in result

    def test_converts_table_cells_to_pipe_format(self) -> None:
        html = "<table><tr><th>Name</th><th>Age</th></tr></table>"
        result = html_to_text(html)
        assert "| Name" in result
        assert "| Age" in result

    def test_decodes_html_entities(self) -> None:
        html = "a &amp; b &lt; c &gt; d &quot;e&quot; &#39;f&#39;"
        result = html_to_text(html)
        assert "a & b < c > d" in result
        assert '"e"' in result
        assert "'f'" in result

    def test_nbsp_converted_to_space(self) -> None:
        html = "hello&nbsp;world"
        result = html_to_text(html)
        assert "hello world" in result

    def test_strips_remaining_html_tags(self) -> None:
        html = "<div><p><span>plain text</span></p></div>"
        result = html_to_text(html)
        assert "<div>" not in result
        assert "<p>" not in result
        assert "<span>" not in result
        assert "plain text" in result

    def test_max_length_truncates_output(self) -> None:
        html = "a" * 200
        result = html_to_text(html, max_length=50)
        assert len(result) <= 50

    def test_default_max_length_is_50000(self) -> None:
        long_html = "word " * 20000  # ~100k chars
        result = html_to_text(long_html)
        assert len(result) <= 50000

    def test_empty_input_returns_empty(self) -> None:
        result = html_to_text("")
        assert result == ""

    def test_multiline_script_stripped(self) -> None:
        html = "<script>\nvar x = 1;\nvar y = 2;\n</script>After"
        result = html_to_text(html)
        assert "var x" not in result
        assert "After" in result

    def test_no_excessive_blank_lines(self) -> None:
        html = "<p>Para1</p><p></p><p></p><p></p><p>Para2</p>"
        result = html_to_text(html)
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in result

    def test_normalizes_multiple_spaces(self) -> None:
        html = "hello    world"
        result = html_to_text(html)
        assert "hello world" in result

    def test_br_tag_converted_to_newline(self) -> None:
        html = "line1<br>line2"
        result = html_to_text(html)
        assert "line1" in result
        assert "line2" in result


# ---------------------------------------------------------------------------
# BrowserTool._normalize_url_for_visit_tracking() classmethod
# ---------------------------------------------------------------------------


class TestNormalizeUrlForVisitTracking:
    """Tests for the URL normalization classmethod used for deduplication."""

    def _norm(self, url: str) -> str:
        return BrowserTool._normalize_url_for_visit_tracking(url)

    def test_basic_url_normalizes(self) -> None:
        result = self._norm("https://example.com/page")
        assert result == "https://example.com/page"

    def test_trailing_slash_stripped_from_path(self) -> None:
        assert self._norm("https://example.com/page/") == self._norm("https://example.com/page")

    def test_root_path_preserved(self) -> None:
        result = self._norm("https://example.com/")
        parsed = urlparse(result)
        assert parsed.netloc == "example.com"
        assert parsed.path == "/"

    def test_fragment_stripped(self) -> None:
        with_fragment = self._norm("https://example.com/page#section")
        without_fragment = self._norm("https://example.com/page")
        assert with_fragment == without_fragment

    def test_utm_source_stripped(self) -> None:
        with_utm = self._norm("https://example.com/page?utm_source=newsletter")
        without_utm = self._norm("https://example.com/page")
        assert with_utm == without_utm

    def test_utm_medium_stripped(self) -> None:
        with_utm = self._norm("https://example.com/page?utm_medium=email")
        without_utm = self._norm("https://example.com/page")
        assert with_utm == without_utm

    def test_utm_campaign_stripped(self) -> None:
        with_utm = self._norm("https://example.com/page?utm_campaign=sale")
        without_utm = self._norm("https://example.com/page")
        assert with_utm == without_utm

    def test_fbclid_stripped(self) -> None:
        with_tracker = self._norm("https://example.com/page?fbclid=abc123")
        without_tracker = self._norm("https://example.com/page")
        assert with_tracker == without_tracker

    def test_gclid_stripped(self) -> None:
        with_tracker = self._norm("https://example.com/page?gclid=xyz")
        without_tracker = self._norm("https://example.com/page")
        assert with_tracker == without_tracker

    def test_real_query_params_preserved(self) -> None:
        url_a = self._norm("https://example.com/search?q=python")
        url_b = self._norm("https://example.com/search?q=rust")
        assert url_a != url_b

    def test_http_and_https_normalized_to_same(self) -> None:
        http = self._norm("http://example.com/page")
        https = self._norm("https://example.com/page")
        assert http == https

    def test_default_port_80_stripped(self) -> None:
        with_port = self._norm("http://example.com:80/page")
        without_port = self._norm("https://example.com/page")
        assert with_port == without_port

    def test_default_port_443_stripped(self) -> None:
        with_port = self._norm("https://example.com:443/page")
        without_port = self._norm("https://example.com/page")
        assert with_port == without_port

    def test_non_standard_port_preserved(self) -> None:
        with_port = self._norm("https://example.com:8080/page")
        without_port = self._norm("https://example.com/page")
        assert with_port != without_port

    def test_hostname_lowercased(self) -> None:
        upper = self._norm("https://EXAMPLE.COM/page")
        lower = self._norm("https://example.com/page")
        assert upper == lower

    def test_query_params_sorted(self) -> None:
        url_a = self._norm("https://example.com/?b=2&a=1")
        url_b = self._norm("https://example.com/?a=1&b=2")
        assert url_a == url_b

    def test_empty_string_returns_empty(self) -> None:
        assert self._norm("") == ""

    def test_whitespace_only_stripped(self) -> None:
        result = self._norm("   ")
        assert result == ""

    def test_mixed_tracking_and_real_params(self) -> None:
        url_with_tracking = self._norm("https://example.com/search?q=ai&utm_source=newsletter")
        url_clean = self._norm("https://example.com/search?q=ai")
        assert url_with_tracking == url_clean

    def test_url_without_netloc_handled(self) -> None:
        # A bare path or relative URL should not crash
        result = self._norm("/relative/path")
        assert isinstance(result, str)

    def test_multiple_utm_params_all_stripped(self) -> None:
        url = "https://example.com/page?utm_source=a&utm_medium=b&utm_campaign=c&utm_content=d"
        result = self._norm(url)
        assert "utm_" not in result


# ---------------------------------------------------------------------------
# BrowserTool._extract_focused_content() instance method
# ---------------------------------------------------------------------------


def _make_tool() -> BrowserTool:
    """Create a BrowserTool with a minimal mock browser for unit tests."""
    mock_browser = MagicMock()
    return BrowserTool(browser=mock_browser)


class TestExtractFocusedContent:
    def test_no_focus_returns_full_text_up_to_max(self) -> None:
        tool = _make_tool()
        text = "This is some content."
        result = tool._extract_focused_content(text, focus=None)
        assert result == text

    def test_no_focus_truncates_at_max_length(self) -> None:
        tool = _make_tool()
        text = "x" * 10000
        result = tool._extract_focused_content(text, focus=None, max_length=100)
        assert len(result) == 100

    def test_empty_text_returns_empty(self) -> None:
        tool = _make_tool()
        result = tool._extract_focused_content("", focus="pricing")
        assert result == ""

    def test_focus_prefers_matching_paragraphs(self) -> None:
        tool = _make_tool()
        text = "Irrelevant paragraph.\n\nPricing starts at $10/month.\n\nAnother irrelevant section."
        result = tool._extract_focused_content(text, focus="pricing", max_length=50000)
        assert "Pricing starts at $10/month" in result

    def test_focus_label_added_when_significant_filtering_occurs(self) -> None:
        tool = _make_tool()
        # One short matching paragraph vs. many long irrelevant paragraphs.
        # max_content_length is set small enough that zero-score paragraphs are
        # excluded by the 30%-context budget, so the result is well below 50% of
        # the original text and the "[FOCUSED CONTENT:]" label is prepended.
        matching = "pricing info"
        irrelevant = "x" * 500  # long, fills up context budget quickly
        paragraphs = [matching] + [irrelevant] * 30
        text = "\n\n".join(paragraphs)
        result = tool._extract_focused_content(text, focus="pricing", max_length=1000)
        assert "[FOCUSED CONTENT: pricing]" in result

    def test_focus_phrase_match_boosts_score(self) -> None:
        tool = _make_tool()
        # One paragraph contains the exact focus phrase, another only has partial words
        high_signal = "The pricing tiers are listed here."
        low_signal = "Here is some pricing data."
        text = f"{low_signal}\n\n{high_signal}"
        result = tool._extract_focused_content(text, focus="pricing tiers", max_length=50000)
        # The paragraph with the full phrase should appear in results
        assert "pricing tiers" in result

    def test_result_does_not_exceed_max_length(self) -> None:
        tool = _make_tool()
        paragraphs = [f"paragraph {i} with relevant pricing info" for i in range(100)]
        text = "\n\n".join(paragraphs)
        result = tool._extract_focused_content(text, focus="pricing", max_length=200)
        assert len(result) <= 200

    def test_no_matching_paragraphs_returns_truncated_original(self) -> None:
        tool = _make_tool()
        text = "nothing relevant here\n\nmore unrelated content"
        result = tool._extract_focused_content(text, focus="pricing", max_length=50000)
        # When no paragraphs score > 0, falls back to returning text[:max_length]
        assert isinstance(result, str)
        assert len(result) > 0

    def test_single_paragraph_with_focus_word(self) -> None:
        tool = _make_tool()
        text = "The cost and pricing model is per seat."
        result = tool._extract_focused_content(text, focus="pricing", max_length=50000)
        assert "pricing" in result

    def test_focus_matching_is_case_insensitive(self) -> None:
        tool = _make_tool()
        text = "PRICING information is on this page."
        result = tool._extract_focused_content(text, focus="pricing", max_length=50000)
        assert "PRICING" in result
