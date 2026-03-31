"""Tests for decide_browse_search_route (fast vs full plan-act routing)."""

from __future__ import annotations

from app.domain.services.flows.fast_path import QueryIntent, decide_browse_search_route


class TestDecideBrowseSearchRoute:
    def test_simple_go_to_uses_fast(self) -> None:
        ok, reason = decide_browse_search_route("go to https://example.com", QueryIntent.DIRECT_BROWSE)
        assert ok is True
        assert reason == "simple_nav_or_search"

    def test_open_reddit_short_uses_fast(self) -> None:
        ok, reason = decide_browse_search_route("open reddit", QueryIntent.DIRECT_BROWSE)
        assert ok is True
        assert reason == "simple_nav_or_search"

    def test_type_message_uses_full(self) -> None:
        ok, reason = decide_browse_search_route(
            "open browser and go to reddit and type hello man people",
            QueryIntent.DIRECT_BROWSE,
        )
        assert ok is False
        assert reason == "browser_interaction_beyond_navigation"

    def test_research_report_uses_full(self) -> None:
        ok, reason = decide_browse_search_route(
            "open site and write a comprehensive research report with citations",
            QueryIntent.DIRECT_BROWSE,
        )
        assert ok is False
        assert "research" in reason or "comparison" in reason

    def test_multi_step_cue_uses_full(self) -> None:
        ok, reason = decide_browse_search_route(
            "go to example.com and then go to news.ycombinator.com",
            QueryIntent.DIRECT_BROWSE,
        )
        assert ok is False
        assert reason == "multi_step_cue"

    def test_web_search_short_uses_fast(self) -> None:
        ok, reason = decide_browse_search_route("search for python asyncio tips", QueryIntent.WEB_SEARCH)
        assert ok is True

    def test_web_search_long_query_uses_full(self) -> None:
        q = "search " + "word " * 50
        ok, reason = decide_browse_search_route(q, QueryIntent.WEB_SEARCH)
        assert ok is False
        assert reason == "web_search_query_too_long"

    def test_non_browse_intent(self) -> None:
        ok, reason = decide_browse_search_route("hello", QueryIntent.TASK)
        assert ok is False
        assert reason == "intent_not_browse_or_search"
