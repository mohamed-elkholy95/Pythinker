"""Unit tests for graceful crash degradation (Priority 1)."""

import urllib.request
from unittest.mock import patch

import pytest

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


def _is_cdp_available() -> bool:
    """Check if a local Chrome CDP /json/version endpoint is reachable via HTTP.

    TCP-only checks are insufficient: a personal Chrome on port 9222 passes TCP
    but fails Playwright's connect_over_cdp (which requires the HTTP endpoint).
    This check validates the HTTP layer that Playwright actually uses.
    """
    for port in (9222, 8222):
        try:
            url = f"http://127.0.0.1:{port}/json/version"
            with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except Exception:  # noqa: S110
            pass
    return False


pytestmark = pytest.mark.skipif(
    not _is_cdp_available(),
    reason="Browser CDP endpoint not available for browser integration-style tests",
)


@pytest.mark.asyncio
async def test_browser_crash_returns_partial_results():
    """Test that browser crashes return partial results instead of failing."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Mock a browser crash during extraction
        with patch.object(browser, "_extract_page_content", side_effect=Exception("Browser crashed")):
            result = await browser.navigate("https://example.com")

            # Should return partial data but report failure state to caller
            assert result.success is False
            assert result.data.get("partial") is True or "partial" in result.message.lower()

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_graceful_degradation_on_memory_crash():
    """Test graceful handling of memory-related crashes."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Mock OOM-like crash
        with patch.object(browser, "_extract_interactive_elements", side_effect=MemoryError("Out of memory")):
            result = await browser.navigate("https://example.com")

            # Should handle gracefully with explicit failure semantics
            assert result.success is False or "memory" in result.message.lower()

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_graceful_degradation_preserves_basic_data():
    """Test that graceful degradation preserves at least URL and title."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Mock partial crash (after basic data extracted)
        original_extract = browser._extract_page_content

        async def mock_extract():
            # Call original to get basic data
            await original_extract()
            # Then crash
            raise Exception("Simulated crash")

        with patch.object(browser, "_extract_page_content", side_effect=mock_extract):
            result = await browser.navigate("https://example.com")

            # Should have at least URL
            assert result.data.get("url") or result.data.get("current_url")

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_config_disables_graceful_degradation():
    """Test that graceful degradation can be disabled via config."""
    from app.core.config import get_settings

    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Mock config to disable graceful degradation
        with (
            patch.object(get_settings(), "browser_graceful_degradation", False),
            patch.object(browser, "_extract_page_content", side_effect=Exception("Browser crashed")),
            pytest.raises(Exception, match="Browser crashed"),
        ):
            await browser.navigate("https://example.com")

    finally:
        await browser.close()
