"""Tests for PDF URL filtering in spider enrichment."""

from __future__ import annotations

from app.domain.services.tools.search import _is_pdf_url


class TestIsPdfUrl:
    """Test PDF URL detection for spider enrichment filtering."""

    def test_detects_pdf_extension(self):
        assert _is_pdf_url("https://example.com/report.pdf") is True

    def test_detects_pdf_extension_case_insensitive(self):
        assert _is_pdf_url("https://example.com/Report.PDF") is True

    def test_detects_pdf_with_query_params(self):
        assert _is_pdf_url("https://example.com/doc.pdf?token=abc") is True

    def test_allows_html_url(self):
        assert _is_pdf_url("https://example.com/article.html") is False

    def test_allows_no_extension(self):
        assert _is_pdf_url("https://example.com/blog/post") is False

    def test_allows_normal_page(self):
        assert _is_pdf_url("https://www.linkedin.com/pulse/some-article") is False

    def test_detects_pdf_in_path(self):
        assert _is_pdf_url("https://reports.weforum.org/docs/WEF_Report_2025.pdf") is True
