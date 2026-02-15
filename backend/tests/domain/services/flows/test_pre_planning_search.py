"""Tests for pre-planning search: detector, query generation, executor."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.pre_planning_search import (
    PrePlanningSearchDetector,
    PrePlanningSearchExecutor,
    PrePlanningSearchResult,
)

# ---------------------------------------------------------------------------
# Detector tests
# ---------------------------------------------------------------------------


class TestPrePlanningSearchDetector:
    """Tests for heuristic-based search trigger detection."""

    @pytest.mark.parametrize(
        "message",
        [
            "compare Claude latest vs GLM latest vs Kimi latest",
            "what is the latest version of GPT?",
            "current pricing for Claude API",
            "newest features in React 2026",
            "benchmark results for Claude vs GPT",
            "compare specs of iPhone 16 vs Galaxy S26",
            "what are the recent changes in Python 3.14?",
        ],
    )
    def test_triggers_correctly(self, message: str) -> None:
        should, reasons = PrePlanningSearchDetector.should_search(message)
        assert should is True
        assert len(reasons) >= 1

    @pytest.mark.parametrize(
        "message",
        [
            "write a Python function to sort a list",
            "refactor this class to use dependency injection",
            "fix bug in the login flow",
            "hello, how are you?",
            "hi there",
            "what is a binary tree",
            "explain how DNS works",
            "implement a REST API endpoint",
            "create file config.yaml",
        ],
    )
    def test_skips_correctly(self, message: str) -> None:
        should, reasons = PrePlanningSearchDetector.should_search(message)
        assert should is False
        assert reasons == []

    def test_temporal_keyword_detected(self) -> None:
        should, reasons = PrePlanningSearchDetector.should_search("latest Claude model pricing")
        assert should is True
        assert any("temporal:" in r for r in reasons)

    def test_comparison_keyword_detected(self) -> None:
        should, reasons = PrePlanningSearchDetector.should_search("compare Claude vs GPT features")
        assert should is True
        assert any("comparison:" in r for r in reasons)

    def test_research_keyword_detected(self) -> None:
        should, reasons = PrePlanningSearchDetector.should_search("Claude API pricing tiers")
        assert should is True
        assert any("research:" in r for r in reasons)


# ---------------------------------------------------------------------------
# Query generation tests
# ---------------------------------------------------------------------------


class TestQueryGeneration:
    """Tests for search query extraction from user messages."""

    def test_comparison_entities_extracted(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries(
            "compare Claude vs GPT vs Gemini",
            ["comparison:vs"],
        )
        assert len(queries) == 3
        assert any("Claude" in q for q in queries)
        assert any("GPT" in q for q in queries)
        assert any("Gemini" in q for q in queries)

    def test_versus_spelled_out(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries(
            "compare Claude versus GPT",
            ["comparison:versus"],
        )
        assert len(queries) == 2

    def test_and_separator(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries(
            "compare Claude and GPT",
            ["comparison:compare"],
        )
        assert len(queries) == 2

    def test_single_entity_fallback(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries(
            "latest Claude model",
            ["temporal:latest"],
        )
        assert len(queries) == 1
        assert "2026" in queries[0]

    def test_max_three_queries(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries(
            "compare A vs B vs C vs D vs E",
            ["comparison:vs"],
        )
        assert len(queries) <= 3

    def test_empty_message_fallback(self) -> None:
        queries = PrePlanningSearchExecutor.generate_search_queries("", ["temporal:latest"])
        assert len(queries) == 1


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


def _make_search_engine(results: list[SearchResultItem] | None = None, should_fail: bool = False) -> AsyncMock:
    """Create a mock SearchEngine."""
    engine = AsyncMock()
    if should_fail:
        engine.search.side_effect = RuntimeError("Search API error")
    elif results is not None:
        engine.search.return_value = ToolResult.ok(
            data=SearchResults(query="test", total_results=len(results), results=results)
        )
    else:
        engine.search.return_value = ToolResult.ok(
            data=SearchResults(query="test", total_results=0, results=[])
        )
    return engine


class TestPrePlanningSearchExecutor:
    """Tests for the search executor."""

    @pytest.mark.asyncio
    async def test_successful_execution(self) -> None:
        items = [
            SearchResultItem(title="Claude 4.5 Released", link="https://a.com", snippet="Latest Claude model"),
            SearchResultItem(title="GPT-5 Announced", link="https://b.com", snippet="OpenAI's newest"),
        ]
        engine = _make_search_engine(items)
        executor = PrePlanningSearchExecutor(engine)

        result = await executor.execute("compare Claude vs GPT", ["comparison:vs"])

        assert result.triggered is True
        assert result.total_results >= 1
        assert result.search_context != ""
        assert result.duration_ms >= 0
        assert len(result.queries) >= 1

    @pytest.mark.asyncio
    async def test_search_failure_returns_empty(self) -> None:
        engine = _make_search_engine(should_fail=True)
        executor = PrePlanningSearchExecutor(engine)

        result = await executor.execute("latest Claude model", ["temporal:latest"])

        assert result.triggered is True
        assert result.search_context == ""
        assert result.total_results == 0

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        engine = _make_search_engine(results=[])
        executor = PrePlanningSearchExecutor(engine)

        result = await executor.execute("latest Claude model", ["temporal:latest"])

        assert result.triggered is True
        assert result.search_context == ""
        assert result.total_results == 0

    @pytest.mark.asyncio
    async def test_deduplicates_by_url(self) -> None:
        items = [
            SearchResultItem(title="Same Page", link="https://a.com", snippet="First"),
            SearchResultItem(title="Same Page V2", link="https://a.com", snippet="Duplicate"),
            SearchResultItem(title="Different Page", link="https://b.com", snippet="Second"),
        ]
        engine = _make_search_engine(items)
        executor = PrePlanningSearchExecutor(engine)

        result = await executor.execute("latest Claude", ["temporal:latest"])

        # Should have deduplicated — only 2 unique URLs
        assert result.total_results == 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Test that individual query timeouts are handled gracefully."""
        engine = AsyncMock()

        async def slow_search(*args, **kwargs):
            await asyncio.sleep(10)  # Way longer than timeout

        engine.search = slow_search

        executor = PrePlanningSearchExecutor(engine)
        executor.QUERY_TIMEOUT_S = 0.1  # Very short timeout for testing

        result = await executor.execute("latest Claude", ["temporal:latest"])

        assert result.triggered is True
        assert result.search_context == ""


# ---------------------------------------------------------------------------
# Context formatting tests
# ---------------------------------------------------------------------------


class TestContextFormatting:
    """Tests for search result formatting."""

    def test_format_caps_at_max_chars(self) -> None:
        items = [(f"Title {i}", f"https://url{i}.com", "x" * 200) for i in range(20)]
        context = PrePlanningSearchExecutor._format_context(items)
        assert len(context) <= PrePlanningSearchExecutor.MAX_CONTEXT_CHARS + 100  # slight tolerance

    def test_format_empty(self) -> None:
        context = PrePlanningSearchExecutor._format_context([])
        assert context == ""

    def test_format_includes_title_and_snippet(self) -> None:
        items = [("My Title", "https://example.com", "My snippet text")]
        context = PrePlanningSearchExecutor._format_context(items)
        assert "My Title" in context
        assert "My snippet text" in context


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestPrePlanningSearchResult:
    """Tests for the result dataclass."""

    def test_default_values(self) -> None:
        result = PrePlanningSearchResult(triggered=False)
        assert result.triggered is False
        assert result.search_context == ""
        assert result.total_results == 0
        assert result.duration_ms == 0.0
        assert result.queries == []

    def test_frozen(self) -> None:
        result = PrePlanningSearchResult(triggered=True, search_context="test")
        with pytest.raises(AttributeError):
            result.triggered = False  # type: ignore[misc]
