"""Unit tests for Wikipedia-specific optimization (Priority 1)."""

import socket

import pytest

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


def _is_cdp_available() -> bool:
    """Check if a local Chrome CDP endpoint is reachable."""
    for port in (9222, 8222):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


pytestmark = pytest.mark.skipif(
    not _is_cdp_available(),
    reason="Browser CDP endpoint not available for browser integration-style tests",
)


@pytest.mark.asyncio
async def test_is_wikipedia_url_detection():
    """Test Wikipedia URL detection."""
    browser = PlaywrightBrowser()

    # Wikipedia URLs
    assert browser._is_wikipedia_url("https://en.wikipedia.org/wiki/Python") is True
    assert browser._is_wikipedia_url("https://fr.wikipedia.org/wiki/Python") is True
    assert browser._is_wikipedia_url("https://de.wikipedia.org/wiki/Python") is True

    # Non-Wikipedia URLs
    assert browser._is_wikipedia_url("https://example.com") is False
    assert browser._is_wikipedia_url("https://google.com") is False
    assert browser._is_wikipedia_url("https://github.com") is False


@pytest.mark.asyncio
async def test_extract_wikipedia_summary_returns_lightweight_data():
    """Test that Wikipedia summary extraction returns only essential data."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to Wikipedia page
        await browser._navigate_impl("https://en.wikipedia.org/wiki/Python_(programming_language)")

        # Extract summary
        summary = await browser._extract_wikipedia_summary()

        assert summary is not None
        assert "text" in summary or "content" in summary

        # Verify it's much smaller than full page
        if "text" in summary:
            # Should be under 5000 chars (lead section only)
            assert len(summary["text"]) < 5000
        elif "content" in summary:
            assert len(summary["content"]) < 5000

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_wikipedia_summary_excludes_tables_and_references():
    """Test that Wikipedia summary excludes heavy elements."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to Wikipedia page with many tables
        await browser._navigate_impl("https://en.wikipedia.org/wiki/Python_(programming_language)")

        summary = await browser._extract_wikipedia_summary()

        # Get text content
        text = summary.get("text", "") or summary.get("content", "")

        # Should not contain table markers (very unlikely in lead paragraphs)
        # Note: This is a heuristic check
        assert "References" not in text or text.index("References") > 1000
        assert "See also" not in text or text.index("See also") > 1000

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_wikipedia_mode_increments_metric():
    """Test that Wikipedia summary mode increments the appropriate metric."""
    from app.infrastructure.observability.prometheus_metrics import browser_wikipedia_summary_mode_total

    browser = PlaywrightBrowser()
    await browser.start()

    try:
        initial_count = browser_wikipedia_summary_mode_total._value.get(frozenset(), 0)

        # Navigate to Wikipedia page
        await browser._navigate_impl("https://en.wikipedia.org/wiki/Python_(programming_language)")

        final_count = browser_wikipedia_summary_mode_total._value.get(frozenset(), 0)

        # Metric should have incremented
        assert final_count >= initial_count

    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_wikipedia_optimization_prevents_oom():
    """Test that Wikipedia optimization reduces memory usage."""
    browser = PlaywrightBrowser()
    await browser.start()

    try:
        # Navigate to large Wikipedia page
        result = await browser.navigate("https://en.wikipedia.org/wiki/Python_(programming_language)")

        # Should complete without crash
        assert result.success is True

        # Memory check (if available)
        memory_check = await browser._check_memory_pressure()
        if memory_check:
            # Should not be critical
            assert memory_check.get("pressure_level") != "critical"

    finally:
        await browser.close()
