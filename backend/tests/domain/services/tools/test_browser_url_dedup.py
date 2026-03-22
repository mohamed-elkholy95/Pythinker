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
    # Tracking-variant is rejected as a repeat visit (success=False with explanation)
    assert second.success is False
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


@pytest.mark.asyncio
async def test_browser_navigate_treats_http_https_as_same_page() -> None:
    """Scheme-only variants should be treated as repeated page visits."""
    mock_browser = MagicMock()
    mock_browser.navigate = AsyncMock(
        return_value=ToolResult(success=True, message="ok", data={"content": "page"}),
    )

    tool = BrowserTool(browser=mock_browser)

    first = await tool.browser_navigate("http://example.com/deals")
    second = await tool.browser_navigate("https://example.com/deals")

    assert first.success is True
    # Scheme-variant is rejected as a repeat visit (success=False with explanation)
    assert second.success is False
    assert "already visited" in (second.message or "").lower()
    assert mock_browser.navigate.await_count == 1


@pytest.mark.asyncio
async def test_browser_navigate_treats_default_ports_as_same_page() -> None:
    """Default 80/443 ports should not bypass duplicate-visit suppression."""
    mock_browser = MagicMock()
    mock_browser.navigate = AsyncMock(
        return_value=ToolResult(success=True, message="ok", data={"content": "page"}),
    )

    tool = BrowserTool(browser=mock_browser)

    first = await tool.browser_navigate("http://example.com:80/deals")
    second = await tool.browser_navigate("https://example.com:443/deals")

    assert first.success is True
    # Port-variant is rejected as a repeat visit (success=False with explanation)
    assert second.success is False
    assert "already visited" in (second.message or "").lower()
    assert mock_browser.navigate.await_count == 1


@pytest.mark.asyncio
async def test_browser_navigate_marks_http_404_as_failed_retrieval() -> None:
    """HTTP error responses should be surfaced as failed retrievals."""
    mock_browser = MagicMock()
    mock_browser.navigate = AsyncMock(
        return_value=ToolResult(
            success=True,
            message="ok",
            data={
                "url": "https://example.com/missing",
                "status": 404,
                "content": "Not Found",
            },
        ),
    )

    tool = BrowserTool(browser=mock_browser)
    result = await tool.browser_navigate("https://example.com/missing")

    assert result.success is False
    assert "404" in (result.message or "")
