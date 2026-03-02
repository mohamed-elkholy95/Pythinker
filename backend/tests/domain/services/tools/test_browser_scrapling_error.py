"""Regression test: Scrapling 404 returns ToolResult(success=False), not RuntimeError."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.tool_result import ToolResult


@pytest.mark.asyncio
async def test_scrapling_404_returns_tool_result_not_exception():
    """browser.py line ~451 must return ToolResult(success=False), not raise RuntimeError.

    The `search` method (formerly browser_get_content) uses Scrapling for enhanced fetch.
    When Scrapling returns a failed result (e.g. HTTP 404), the code must return a
    ToolResult with success=False instead of raising a RuntimeError.
    """
    from app.domain.services.tools.browser import BrowserTool

    # Create a mock browser with required attributes
    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_browser.navigate_for_display = AsyncMock()

    # Create a mock scraper that returns a 404 failure
    mock_scraper = MagicMock()
    mock_scraped = MagicMock()
    mock_scraped.success = False
    mock_scraped.error = "HTTP 404 Not Found"
    mock_scraped.text = ""
    mock_scraped.html = ""
    mock_scraped.url = "https://vuejs.org/guide/best-practices/"
    mock_scraped.tier_used = "http"
    mock_scraper.fetch_with_escalation = AsyncMock(return_value=mock_scraped)

    tool = BrowserTool(browser=mock_browser, scraper=mock_scraper)

    with patch("app.core.config.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.scraping_enhanced_fetch = True
        mock_get_settings.return_value = settings

        # This MUST NOT raise RuntimeError — it must return ToolResult(success=False)
        result = await tool.search("https://vuejs.org/guide/best-practices/")

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "404" in result.message or "failed" in result.message.lower()
