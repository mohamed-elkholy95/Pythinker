from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.browser import BrowserTool


@pytest.mark.asyncio
async def test_browser_navigate_treats_tracking_variants_as_repeat() -> None:
    """Tracking-only URL variants should be rejected as repeat navigations."""
    mock_browser = MagicMock()
    mock_browser.navigate = AsyncMock(
        return_value=ToolResult(success=True, message="ok", data={"content": "page"}),
    )

    tool = BrowserTool(browser=mock_browser)

    first = await tool.browser_navigate("https://example.com/deals?utm_source=newsletter")
    second = await tool.browser_navigate("https://example.com/deals?utm_medium=email")

    assert first.success is True
    assert second.success is True
    assert "already visited" in (second.message or "").lower()
    assert mock_browser.navigate.await_count == 1


@pytest.mark.asyncio
async def test_browser_navigate_keeps_real_query_variants_distinct() -> None:
    """Different non-tracking query params should remain distinct URLs."""
    mock_browser = MagicMock()
    mock_browser.navigate = AsyncMock(
        return_value=ToolResult(success=True, message="ok", data={"content": "page"}),
    )

    tool = BrowserTool(browser=mock_browser)

    first = await tool.browser_navigate("https://example.com/search?q=cursor")
    second = await tool.browser_navigate("https://example.com/search?q=copilot")

    assert first.success is True
    assert second.success is True
    assert mock_browser.navigate.await_count == 2
