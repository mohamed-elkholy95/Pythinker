"""Tests for ResearchSpider — validates class structure and configuration only.

Integration tests that make real HTTP requests are excluded from the unit suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.infrastructure.external.scraper.research_spider import ResearchSpider


class TestResearchSpiderInit:
    """Verify spider initializes correctly with its class attributes."""

    def test_name_attribute(self):
        spider = ResearchSpider(start_urls=["https://example.com"])
        assert spider.name == "research"

    def test_concurrency_defaults(self):
        spider = ResearchSpider(start_urls=["https://example.com"])
        assert spider.concurrent_requests == 5
        assert spider.concurrent_requests_per_domain == 2

    def test_start_urls_stored(self):
        urls = ["https://example.com", "https://example.org"]
        spider = ResearchSpider(start_urls=urls)
        assert spider.start_urls == urls

    def test_custom_impersonate(self):
        spider = ResearchSpider(start_urls=["https://example.com"], impersonate="firefox")
        assert spider._impersonate == "firefox"

    def test_custom_timeout(self):
        spider = ResearchSpider(start_urls=["https://example.com"], timeout=30)
        assert spider._timeout == 30

    def test_custom_max_text_length(self):
        spider = ResearchSpider(start_urls=["https://example.com"], max_text_length=50000)
        assert spider._max_text_length == 50000

    def test_default_impersonate_is_chrome(self):
        spider = ResearchSpider(start_urls=["https://example.com"])
        assert spider._impersonate == "chrome"


class TestResearchSpiderSessions:
    """Verify configure_sessions registers an HTTP session."""

    def test_session_registered(self):
        spider = ResearchSpider(start_urls=["https://example.com"])
        # SessionManager was configured during __init__
        assert spider._session_manager is not None
        assert spider._session_manager.default_session_id == "http"

    def test_session_count_is_one(self):
        spider = ResearchSpider(start_urls=["https://example.com"])
        assert len(spider._session_manager) == 1


class TestResearchSpiderParseOutput:
    """Verify parse() yields the correct dict structure."""

    @pytest.mark.asyncio
    async def test_parse_yields_expected_keys(self):
        spider = ResearchSpider(start_urls=["https://example.com"])

        # Mock a Response with expected attributes
        mock_response = MagicMock()
        mock_response.get_all_text.return_value = MagicMock(__str__=lambda self: "Hello world content " * 50)
        mock_response.css.return_value = [MagicMock(text="Page Title")]
        mock_response.url = "https://example.com"
        mock_response.status = 200

        items = [item async for item in spider.parse(mock_response)]

        assert len(items) == 1
        item = items[0]
        assert "url" in item
        assert "text" in item
        assert "title" in item
        assert "status" in item
        assert item["status"] == 200

    @pytest.mark.asyncio
    async def test_parse_truncates_at_max_length(self):
        spider = ResearchSpider(start_urls=["https://example.com"], max_text_length=100)

        mock_response = MagicMock()
        long_text = "x" * 1000
        mock_response.get_all_text.return_value = MagicMock(__str__=lambda self: long_text)
        mock_response.css.return_value = []
        mock_response.url = "https://example.com"
        mock_response.status = 200

        items = [item async for item in spider.parse(mock_response)]

        assert len(items[0]["text"]) <= 100

    @pytest.mark.asyncio
    async def test_parse_handles_missing_title(self):
        spider = ResearchSpider(start_urls=["https://example.com"])

        mock_response = MagicMock()
        mock_response.get_all_text.return_value = MagicMock(__str__=lambda self: "content")
        mock_response.css.return_value = []  # No title element
        mock_response.url = "https://example.com"
        mock_response.status = 200

        items = [item async for item in spider.parse(mock_response)]

        assert items[0]["title"] is None


class TestResearchSpiderRequiresStartUrls:
    """Spider must raise when start_urls is empty at stream time (not init time)."""

    def test_empty_start_urls_does_not_raise_at_init(self):
        # Spider should not raise at init time for empty URLs — it raises at stream
        spider = ResearchSpider(start_urls=[])
        assert spider.start_urls == []
