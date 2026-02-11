"""End-to-end integration tests for Wikipedia navigation (Priority 1)."""

import pytest

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


@pytest.mark.asyncio
@pytest.mark.slow
async def test_wikipedia_navigation_no_crashes():
    """Test that navigating to Wikipedia pages doesn't cause crashes."""
    browser = PlaywrightBrowser()
    await browser.start()

    wikipedia_urls = [
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Artificial_intelligence",
        "https://en.wikipedia.org/wiki/Machine_learning",
        "https://en.wikipedia.org/wiki/Deep_learning",
        "https://en.wikipedia.org/wiki/Natural_language_processing",
    ]

    try:
        for url in wikipedia_urls:
            result = await browser.navigate(url)

            # Should complete without crash
            assert result.success is True

            # Should have some content
            assert result.data is not None

    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_wikipedia_memory_stays_below_threshold():
    """Test that Wikipedia navigation keeps memory usage reasonable."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to large Wikipedia page
        await browser.navigate("https://en.wikipedia.org/wiki/Python_(programming_language)")

        # Check memory pressure
        memory_check = await browser._check_memory_pressure()

        if memory_check:
            # Memory should not be critical (< 800MB)
            assert memory_check["used_mb"] < 800
            assert memory_check["pressure_level"] != "critical"

    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_multiple_wikipedia_navigations_without_restart():
    """Test that multiple Wikipedia navigations work without browser restart."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to 10 Wikipedia pages consecutively
        for i in range(10):
            url = f"https://en.wikipedia.org/wiki/List_of_programming_languages"
            result = await browser.navigate(url)

            assert result.success is True

    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_wikipedia_summary_extraction_is_fast():
    """Test that Wikipedia summary extraction is faster than full extraction."""
    import time

    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to Wikipedia page
        await browser._navigate_impl("https://en.wikipedia.org/wiki/Python_(programming_language)")

        # Time summary extraction
        start = time.perf_counter()
        summary = await browser._extract_wikipedia_summary()
        summary_time = time.perf_counter() - start

        # Should be fast (< 2 seconds)
        assert summary_time < 2.0

        # Should have content
        assert summary is not None

    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_heavy_page_detection_prevents_full_extraction():
    """Test that heavy page detection skips expensive operations."""
    from unittest.mock import patch

    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Track if smart scroll was called
        scroll_called = False

        original_scroll = browser._smart_scroll_for_lazy_content

        async def track_scroll():
            nonlocal scroll_called
            scroll_called = True
            return await original_scroll()

        with patch.object(browser, "_smart_scroll_for_lazy_content", side_effect=track_scroll):
            await browser.navigate("https://en.wikipedia.org/wiki/Python_(programming_language)")

            # Smart scroll should not have been called (heavy page detected)
            assert scroll_called is False

    finally:
        await browser.close()
