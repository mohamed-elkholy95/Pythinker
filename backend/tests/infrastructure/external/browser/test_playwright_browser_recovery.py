"""Targeted tests for Playwright browser crash recovery behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


@pytest.fixture
def browser() -> PlaywrightBrowser:
    with (
        patch("app.infrastructure.external.browser.playwright_browser.get_llm"),
        patch("app.infrastructure.external.browser.playwright_browser.get_settings") as mock_settings,
    ):
        mock_settings.return_value = MagicMock()
        browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
        browser._connection_healthy = True
        browser.browser = MagicMock()
        browser.page = MagicMock()
        browser.page.is_closed = MagicMock(return_value=False)
        browser.page.context = MagicMock()
        browser.page.bring_to_front = AsyncMock()
        browser.page.goto = AsyncMock(side_effect=Exception("Target crashed"))
        browser.page.url = "https://example.com"
        browser.page.title = AsyncMock(return_value="Example")
        browser.restart = AsyncMock(return_value=ToolResult(success=True, data={"url": "https://example.com"}))
        return browser


@pytest.mark.asyncio
async def test_navigate_impl_reinitialize_after_target_crash(browser: PlaywrightBrowser):
    result = await browser._navigate_impl(
        "https://example.com",
        timeout=5000,
        wait_until="load",
        auto_extract=False,
    )

    assert result.success is True
    browser.restart.assert_awaited_once_with("https://example.com")
