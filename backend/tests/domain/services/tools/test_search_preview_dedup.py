"""Regression tests for SearchTool live-preview URL deduplication."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
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

    assert mock_browser.navigate_for_display.await_count == 1
    assert not tool._previewing_result_urls
    normalized = SearchTool._normalize_preview_url("https://example.com/deals/headphones")
    assert normalized in tool._previewed_result_urls


@pytest.mark.asyncio
async def test_browse_top_results_emits_progress_checkpoints_for_replay() -> None:
    mock_browser = MagicMock()
    mock_browser.navigate_for_display = AsyncMock(return_value=True)
    mock_browser._background_browse_cancelled = False
    tool = SearchTool(search_engine=MagicMock(), browser=mock_browser)
    tool._active_tool_call_id = "call-search-1"
    tool._active_function_name = "info_search_web"
    tool._start_time = time.monotonic()

    search_data = SearchResults(
        query="headphones",
        date_range=None,
        total_results=2,
        results=[
            SearchResultItem(
                title="Result 1",
                link="https://example.com/deals/headphones",
                snippet="deal 1",
            ),
            SearchResultItem(
                title="Result 2",
                link="https://example.com/reviews/headphones",
                snippet="deal 2",
            ),
        ],
    )

    with patch("app.domain.services.tools.search.asyncio.sleep", new=AsyncMock(return_value=None)):
        await tool._browse_top_results(
            search_data,
            count=2,
            emit_progress=True,
            progress_query="headphones",
            progress_step_offset=1,
            progress_total_steps=4,
            dwell_seconds=0,
        )

    events = [event async for event in tool.drain_progress_events()]

    assert len(events) == 2
    assert events[0].tool_call_id == "call-search-1"
    assert events[0].checkpoint_data == {
        "action": "navigate",
        "action_function": "browser_navigate",
        "url": "https://example.com/deals/headphones",
        "index": 1,
        "query": "headphones",
        "step": 2,
        "command_category": "browse",
    }
    assert events[1].checkpoint_data["url"] == "https://example.com/reviews/headphones"


@pytest.mark.asyncio
async def test_info_search_web_uses_recorded_preview_instead_of_background_preview() -> None:
    search_engine = MagicMock()
    search_engine.provider_name = "test"
    search_engine.search = AsyncMock(
        return_value=ToolResult(
            success=True,
            message="Results",
            data=SearchResults(
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
            ),
        )
    )
    tool = SearchTool(search_engine=search_engine, browser=MagicMock(), search_prefer_browser=False)
    tool._dedup_skip = False
    tool._browse_top_results = AsyncMock()
    tool._schedule_background_preview = AsyncMock()

    result = await tool.info_search_web("headphones")

    tool._browse_top_results.assert_awaited_once()
    tool._schedule_background_preview.assert_not_called()
    assert "recorded in the session timeline" in (result.message or "")
