"""Unit tests for graceful crash degradation (Priority 1)."""

from unittest.mock import patch

import pytest

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


@pytest.mark.asyncio
async def test_browser_crash_returns_partial_results():
    """Test that browser crashes return partial results instead of failing."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Mock a browser crash during extraction
        with patch.object(browser, "_extract_page_content", side_effect=Exception("Browser crashed")):
            result = await browser.navigate("https://example.com")

            # Should return success with partial flag
            assert result.success is True
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

            # Should handle gracefully
            assert result.success is True or "memory" in result.message.lower()

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
            pytest.raises(Exception),
        ):
            await browser.navigate("https://example.com")

    finally:
        await browser.close()
