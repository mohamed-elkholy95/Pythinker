"""Regression tests for SearchTool live-preview URL deduplication."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.services.tools.search import SearchTool


def test_normalize_preview_url_collapses_scheme_port_and_tracking_params() -> None:
    raw_a = "http://Example.com:80/deals/?utm_source=newsletter&ref=abc&q=headphones#section"
    raw_b = "https://example.com/deals?q=headphones"

    assert SearchTool._normalize_preview_url(raw_a) == SearchTool._normalize_preview_url(raw_b)


@pytest.mark.asyncio
async def test_browse_top_results_avoids_duplicate_navigation_during_race() -> None:
    mock_browser = MagicMock()
    mock_browser.navigate_for_display = AsyncMock(return_value=True)
    mock_browser._background_browse_cancelled = False
    tool = SearchTool(search_engine=MagicMock(), browser=mock_browser)

    search_data = SearchResults(
        query="headphones",
        date_range=None,
        total_results=1,
        results=[
            SearchResultItem(
                title="Best Headphones",
                link="https://example.com/deals/headphones",
                snippet="deals",
            )
        ],
    )

    with patch("app.domain.services.tools.search.asyncio.sleep", new=AsyncMock(return_value=None)):
        await asyncio.gather(
            tool._browse_top_results(search_data, count=1),
            tool._browse_top_results(search_data, count=1),
        )

    # navigate_for_display is called once for the result URL plus once for
    # the about:blank post-preview renderer cleanup.  The key dedup
    # guarantee is that the *result* URL is navigated exactly once.
    real_url_calls = [
        c
        for c in mock_browser.navigate_for_display.call_args_list
        if c[0][0] != "about:blank"
    ]
    assert len(real_url_calls) == 1, (
        f"Expected 1 real URL navigation, got {len(real_url_calls)}: "
        f"{[c[0][0] for c in real_url_calls]}"
    )
    assert not tool._previewing_result_urls
    normalized = SearchTool._normalize_preview_url("https://example.com/deals/headphones")
    assert normalized in tool._previewed_result_urls
