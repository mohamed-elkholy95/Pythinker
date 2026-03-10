"""Integration tests for the deterministic research pipeline.

Tests the full pipeline:
    SourceSelector → EvidenceAcquisitionService → SynthesisGuard

Via the ResearchExecutionPolicy orchestrator (ToolInterceptor).

Covers:
- Full pipeline with good sources → synthesis PASS
- Mixed confidence sources with browser promotion → synthesis still passes
- All hard-fail sources → synthesis HARD_FAIL
- SourceTracker is populated from evidence records
- Non-search tools are not intercepted
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.evidence import (
    ConfidenceBucket,
    SynthesisGateVerdict,
    ToolCallContext,
)
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.evidence_acquisition import EvidenceAcquisitionService
from app.domain.services.agents.research_execution_policy import ResearchExecutionPolicy
from app.domain.services.agents.source_selector import SourceSelector
from app.domain.services.agents.source_tracker import SourceTracker
from app.domain.services.agents.synthesis_guard import SynthesisGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: object) -> SimpleNamespace:
    """Return a SimpleNamespace with all required research pipeline config fields."""
    defaults = dict(
        # Source selection
        research_deterministic_pipeline_enabled=True,
        research_pipeline_mode="enforced",
        research_source_select_count=4,
        research_source_max_per_domain=1,
        research_source_allow_multi_page_domains=True,
        # Scoring weights
        research_weight_relevance=0.35,
        research_weight_authority=0.25,
        research_weight_freshness=0.20,
        research_weight_rank=0.20,
        # Acquisition
        research_acquisition_concurrency=4,
        research_acquisition_timeout_seconds=30.0,
        research_excerpt_chars=2000,
        research_full_content_offload=False,
        # Confidence thresholds
        research_soft_fail_verify_threshold=2,
        research_soft_fail_required_threshold=3,
        research_thin_content_chars=500,
        research_boilerplate_ratio_threshold=0.6,
        # Synthesis gate — default
        research_min_fetched_sources=3,
        research_min_high_confidence=2,
        research_require_official_source=False,  # disable for easier testing
        research_require_independent_source=False,  # disable for easier testing
        # Synthesis gate — relaxed
        research_relaxation_enabled=True,
        research_relaxed_min_fetched_sources=2,
        research_relaxed_min_high_confidence=1,
        research_relaxed_require_official_source=False,
        # Telemetry
        research_telemetry_enabled=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_scraper_response(
    text: str = "Comprehensive content. " * 60,
    tier_used: str = "http",
) -> SimpleNamespace:
    """Return a fake Scrapling response with sufficient content."""
    return SimpleNamespace(
        success=True,
        text=text,
        tier_used=tier_used,
        status_code=200,
        error=None,
    )


def _make_search_results(urls: list[str], query: str = "python testing") -> SearchResults:
    """Build a SearchResults object with distinct URLs."""
    items = [
        SearchResultItem(
            title=f"Article about {query} - Site {i}",
            link=url,
            snippet=f"This site covers {query} in great detail with many examples.",
        )
        for i, url in enumerate(urls, start=1)
    ]
    return SearchResults(query=query, results=items)


def _make_tool_call_context(
    function_name: str = "info_search_web",
    query: str = "python testing",
    session_id: str = "session-abc",
    step_id: str = "step-1",
) -> ToolCallContext:
    return ToolCallContext(
        tool_call_id="tc-001",
        function_name=function_name,
        function_args={"query": query},
        step_id=step_id,
        session_id=session_id,
        research_mode="deep_research",
    )


def _build_pipeline(
    config: SimpleNamespace,
    scraper: AsyncMock,
    browser: AsyncMock | None = None,
) -> tuple[ResearchExecutionPolicy, SourceTracker]:
    """Wire all pipeline components together and return the policy + tracker."""
    selector = SourceSelector(config=config)
    guard = SynthesisGuard(config=config)
    tracker = SourceTracker()
    evidence_svc = EvidenceAcquisitionService(
        scraper=scraper,
        browser=browser,
        tool_result_store=None,
        config=config,
    )
    policy = ResearchExecutionPolicy(
        source_selector=selector,
        evidence_service=evidence_svc,
        synthesis_guard=guard,
        config=config,
        source_tracker=tracker,
    )
    return policy, tracker


# ---------------------------------------------------------------------------
# TestFullPipelineGoodSources
# ---------------------------------------------------------------------------


class TestFullPipelineGoodSources:
    """Pipeline with high-quality sources → evidence records created, gate PASS."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_good_sources(self) -> None:
        """5 search results → selector picks top N → scraper returns rich content
        → HIGH confidence → synthesis gate PASS → extra_messages injected."""
        config = _make_config()
        good_text = "Python testing frameworks cover unit tests and integration tests. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )
        emit_event = AsyncMock()

        policy, tracker = _build_pipeline(config, scraper)

        search_results = _make_search_results(
            urls=[
                "https://docs.python.org/testing",
                "https://pytest.org/getting-started",
                "https://realpython.com/pytest-guide",
                "https://stackoverflow.com/q/12345",  # denylist — excluded
                "https://testingexpert.com/python",
            ],
            query="python testing",
        )
        tool_result = ToolResult.ok(data=search_results)
        context = _make_tool_call_context(query="python testing")

        interceptor_result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=emit_event,
        )

        # Interceptor result must not be None — pipeline fired
        assert interceptor_result is not None

        # extra_messages must contain the evidence summary
        assert interceptor_result.extra_messages is not None
        assert len(interceptor_result.extra_messages) >= 1
        evidence_msg = interceptor_result.extra_messages[0]
        assert evidence_msg["role"] == "system"
        assert "Research Evidence Acquired" in evidence_msg["content"]

        # Evidence records accumulated
        assert len(policy.evidence_records) > 0

        # Synthesis gate evaluates correctly
        gate = policy.can_synthesize()
        # With rich content, multiple sources should be HIGH confidence
        assert gate.verdict in {SynthesisGateVerdict.pass_, SynthesisGateVerdict.soft_fail}

        # emit_event was called (progress events)
        assert emit_event.call_count >= 2

    @pytest.mark.asyncio
    async def test_evidence_summary_lists_all_acquired_sources(self) -> None:
        """Evidence summary in extra_messages includes each acquired source."""
        config = _make_config()
        good_text = "Detailed Python testing content covering many aspects. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=[
                "https://docs.python.org/3/library/unittest.html",
                "https://pytest.org/guide",
                "https://coverage.readthedocs.io",
            ],
            query="python unit testing",
        )
        tool_result = ToolResult.ok(data=search_results)
        context = _make_tool_call_context(query="python unit testing")

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is not None
        content = result.extra_messages[0]["content"]
        # Summary header present
        assert "Sources fetched:" in content
        # Source entries present (### Source N)
        assert "### Source 1:" in content

    @pytest.mark.asyncio
    async def test_synthesis_gate_passes_with_multiple_high_confidence_sources(self) -> None:
        """Gate PASS when >= min_high_confidence sources are HIGH."""
        config = _make_config(
            research_min_fetched_sources=2,
            research_min_high_confidence=2,
        )
        rich_text = "Comprehensive content about Python testing. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=rich_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=[
                "https://docs.python.org/testing",
                "https://pytest.org/guide",
                "https://testingblog.com/python",
                "https://devguide.com/testing",
            ],
            query="python testing",
        )
        tool_result = ToolResult.ok(data=search_results)

        await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        gate = policy.can_synthesize()
        # With rich text, all acquired sources → HIGH confidence
        assert gate.total_fetched >= 2
        assert gate.high_confidence_count >= 2
        assert gate.verdict == SynthesisGateVerdict.pass_


# ---------------------------------------------------------------------------
# TestMixedConfidencePipeline
# ---------------------------------------------------------------------------


class TestMixedConfidencePipeline:
    """Pipeline with mixed content quality — some sources trigger browser promotion."""

    @pytest.mark.asyncio
    async def test_pipeline_with_mixed_confidence(self) -> None:
        """Some sources return thin/empty content → browser promotion → gate still
        passes with enough HIGH confidence sources."""
        config = _make_config(
            research_min_fetched_sources=2,
            research_min_high_confidence=1,
        )
        good_text = "Rich article with detailed Python testing coverage. " * 80
        empty_text = ""  # triggers extraction_failure hard fail → REQUIRED promotion

        call_count = 0

        async def _scrape_side_effect(url: str) -> SimpleNamespace:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_scraper_response(text=good_text)
            return _make_scraper_response(text=empty_text)

        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(side_effect=_scrape_side_effect)

        # Browser returns rich content for promoted sources
        browser = AsyncMock()
        browser.navigate = AsyncMock(
            return_value=SimpleNamespace(
                content="Browser rendered content with full article details. " * 60
            )
        )

        policy, tracker = _build_pipeline(config, scraper, browser=browser)
        search_results = _make_search_results(
            urls=[
                "https://docs.python.org/testing",
                "https://example-thin-site.com/article",
                "https://another-good-site.com/testing",
            ],
            query="python testing",
        )
        tool_result = ToolResult.ok(data=search_results)

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        assert result is not None
        assert len(policy.evidence_records) > 0

        gate = policy.can_synthesize()
        # Should pass or soft_fail given at least some good sources
        assert gate.verdict in {SynthesisGateVerdict.pass_, SynthesisGateVerdict.soft_fail}

    @pytest.mark.asyncio
    async def test_pipeline_accumulates_records_across_multiple_calls(self) -> None:
        """Multiple on_tool_result calls accumulate evidence records."""
        config = _make_config()
        good_text = "Detailed article content for testing purposes. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        emit = AsyncMock()

        # First call
        results1 = _make_search_results(
            urls=["https://site1.com/page", "https://site2.com/page"],
            query="python testing",
        )
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=results1),
            serialized_content="",
            context=_make_tool_call_context(query="python testing"),
            emit_event=emit,
        )
        count_after_first = len(policy.evidence_records)

        # Second call with different query
        results2 = _make_search_results(
            urls=["https://site3.com/page", "https://site4.com/page"],
            query="pytest fixtures",
        )
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=results2),
            serialized_content="",
            context=_make_tool_call_context(query="pytest fixtures", step_id="step-2"),
            emit_event=emit,
        )

        total_records = len(policy.evidence_records)
        assert total_records > count_after_first


# ---------------------------------------------------------------------------
# TestHardFailBlocking
# ---------------------------------------------------------------------------


class TestHardFailBlocking:
    """Pipeline blocks synthesis when all sources hard-fail."""

    @pytest.mark.asyncio
    async def test_pipeline_blocks_synthesis_on_hard_fail(self) -> None:
        """All sources return empty content → all LOW confidence → gate HARD_FAIL."""
        config = _make_config(
            research_min_fetched_sources=3,
            research_min_high_confidence=2,
            research_relaxation_enabled=False,  # disable relaxation so hard fail is enforced
        )
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")  # empty → extraction_failure
        )

        policy, _ = _build_pipeline(config, scraper, browser=None)
        search_results = _make_search_results(
            urls=[
                "https://blocked-site1.com/page",
                "https://blocked-site2.com/page",
                "https://blocked-site3.com/page",
            ],
            query="python testing",
        )
        tool_result = ToolResult.ok(data=search_results)

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        # Interceptor still returns (evidence records are built)
        assert result is not None

        # Gate should HARD_FAIL — insufficient successful fetches
        gate = policy.can_synthesize()
        assert gate.verdict == SynthesisGateVerdict.hard_fail
        assert gate.total_fetched == 0  # all had content_length == 0

    @pytest.mark.asyncio
    async def test_hard_fail_records_have_low_confidence(self) -> None:
        """Evidence records from blocked/empty sources have LOW confidence bucket."""
        config = _make_config()
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")
        )

        policy, _ = _build_pipeline(config, scraper, browser=None)
        search_results = _make_search_results(
            urls=["https://empty-site.com/article"],
            query="python testing",
        )
        tool_result = ToolResult.ok(data=search_results)

        await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        assert len(policy.evidence_records) > 0
        for record in policy.evidence_records:
            assert record.confidence_bucket == ConfidenceBucket.low

    @pytest.mark.asyncio
    async def test_synthesis_gate_reports_failure_reasons(self) -> None:
        """SynthesisGateResult has non-empty reasons when gate fails."""
        config = _make_config(
            research_min_fetched_sources=5,
            research_min_high_confidence=4,
            research_relaxation_enabled=False,
        )
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")
        )

        policy, _ = _build_pipeline(config, scraper)
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=_make_search_results(
                urls=["https://site1.com/a", "https://site2.com/b"],
                query="test",
            )),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        gate = policy.can_synthesize()
        assert gate.verdict == SynthesisGateVerdict.hard_fail
        assert len(gate.reasons) > 0


# ---------------------------------------------------------------------------
# TestSourceTrackerIntegration
# ---------------------------------------------------------------------------


class TestSourceTrackerIntegration:
    """SourceTracker is populated with citations from evidence records."""

    @pytest.mark.asyncio
    async def test_source_tracker_populated_from_evidence(self) -> None:
        """After pipeline runs, SourceTracker contains citations for each acquired source."""
        config = _make_config()
        good_text = "Rich content with detailed information. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, tracker = _build_pipeline(config, scraper)
        urls = [
            "https://docs.python.org/testing",
            "https://pytest.org/guide",
            "https://realpython.com/testing",
        ]
        search_results = _make_search_results(urls=urls, query="python testing")
        tool_result = ToolResult.ok(data=search_results)

        await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        # Tracker should have citations for the acquired sources
        assert tracker.source_count > 0

        # All acquired evidence records should have a corresponding tracker entry
        collected_urls = {s.url for s in tracker.get_collected_sources()}
        for record in policy.evidence_records:
            assert record.url in collected_urls

    @pytest.mark.asyncio
    async def test_source_tracker_not_duplicated_on_same_url(self) -> None:
        """The same URL is not added twice even if both pipeline runs acquire it."""
        config = _make_config()
        good_text = "Rich content here. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, tracker = _build_pipeline(config, scraper)
        # Two identical search result sets pointing to the same URL
        same_url = "https://docs.python.org/testing"
        results = _make_search_results(urls=[same_url], query="python testing")
        tr = ToolResult.ok(data=results)
        emit = AsyncMock()

        await policy.on_tool_result(
            tool_result=tr,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=emit,
        )
        initial_count = tracker.source_count

        await policy.on_tool_result(
            tool_result=tr,
            serialized_content="",
            context=_make_tool_call_context(step_id="step-2"),
            emit_event=emit,
        )

        # Should not double-add the same URL
        assert tracker.source_count == initial_count

    @pytest.mark.asyncio
    async def test_source_tracker_build_numbered_source_list(self) -> None:
        """build_numbered_source_list returns non-empty string after pipeline runs."""
        config = _make_config()
        good_text = "Complete article about Python testing. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, tracker = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=["https://pytest.org/guide", "https://docs.python.org"],
            query="python testing",
        )

        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        bibliography = tracker.build_numbered_source_list()
        assert len(bibliography) > 0
        assert "[1]" in bibliography


# ---------------------------------------------------------------------------
# TestNonSearchToolPassThrough
# ---------------------------------------------------------------------------


class TestNonSearchToolPassThrough:
    """Non-search tools are not intercepted by the pipeline."""

    @pytest.mark.asyncio
    async def test_shell_tool_not_intercepted(self) -> None:
        """Shell tool calls return None (no interception)."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        context = _make_tool_call_context(function_name="execute_shell")
        tool_result = ToolResult.ok(data={"output": "hello world"})

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="hello world",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None
        # No evidence records accumulated for non-search tools
        assert len(policy.evidence_records) == 0

    @pytest.mark.asyncio
    async def test_browser_navigate_not_intercepted(self) -> None:
        """browser_navigate tool calls return None (not a search tool)."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        context = _make_tool_call_context(function_name="browser_navigate")
        tool_result = ToolResult.ok(data={"content": "some page content"})

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="some page content",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_write_file_not_intercepted(self) -> None:
        """write_file tool calls return None (not a search tool)."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        context = _make_tool_call_context(function_name="write_file")
        tool_result = ToolResult.ok(data={"path": "/tmp/out.txt"})

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="File written",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_failed_search_tool_result_not_intercepted(self) -> None:
        """A failed (success=False) search tool result returns None."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        context = _make_tool_call_context(function_name="info_search_web")
        tool_result = ToolResult.error("API rate limit exceeded")

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None
        assert len(policy.evidence_records) == 0

    @pytest.mark.asyncio
    async def test_wide_research_tool_is_intercepted(self) -> None:
        """wide_research tool calls ARE intercepted like info_search_web."""
        config = _make_config()
        good_text = "Detailed information about Python. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )
        policy, _ = _build_pipeline(config, scraper)

        context = _make_tool_call_context(function_name="wide_research", query="Python")
        search_results = _make_search_results(
            urls=["https://python.org", "https://docs.python.org"],
            query="Python",
        )
        tool_result = ToolResult.ok(data=search_results)

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is not None


# ---------------------------------------------------------------------------
# TestEmptyAndEdgeCases
# ---------------------------------------------------------------------------


class TestEmptyAndEdgeCases:
    """Edge cases: empty result sets, missing query, None data."""

    @pytest.mark.asyncio
    async def test_empty_search_results_returns_none(self) -> None:
        """on_tool_result returns None when search results list is empty."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        search_results = SearchResults(query="empty", results=[])
        tool_result = ToolResult.ok(data=search_results)
        context = _make_tool_call_context()

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_none_data_returns_none(self) -> None:
        """on_tool_result returns None when tool_result.data is None."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        tool_result = ToolResult(success=True, data=None)
        context = _make_tool_call_context()

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_all_denylist_urls_filtered_returns_none(self) -> None:
        """All URLs from denylist domains → selector returns empty → None returned."""
        config = _make_config()
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        # All URLs are from denylist domains
        denylist_results = SearchResults(
            query="python testing",
            results=[
                SearchResultItem(
                    title="Reddit thread",
                    link="https://reddit.com/r/python/comments/123",
                    snippet="Python testing discussion",
                ),
                SearchResultItem(
                    title="Twitter post",
                    link="https://twitter.com/pythondev/status/456",
                    snippet="Python testing tweet",
                ),
            ],
        )
        tool_result = ToolResult.ok(data=denylist_results)

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_query_extracted_from_queries_list(self) -> None:
        """Query can be extracted from function_args["queries"] list."""
        config = _make_config()
        good_text = "Article about Python best practices. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)

        # Use "queries" list instead of "query" key
        context = ToolCallContext(
            tool_call_id="tc-002",
            function_name="info_search_web",
            function_args={"queries": ["python best practices", "python style guide"]},
            step_id="step-1",
            session_id="session-xyz",
            research_mode="deep_research",
        )
        search_results = _make_search_results(
            urls=["https://pep8.org", "https://docs.python.org/style"],
            query="python best practices",
        )
        tool_result = ToolResult.ok(data=search_results)

        result = await policy.on_tool_result(
            tool_result=tool_result,
            serialized_content="",
            context=context,
            emit_event=AsyncMock(),
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_can_synthesize_with_no_evidence_returns_hard_fail(self) -> None:
        """can_synthesize() returns HARD_FAIL when no evidence has been acquired."""
        config = _make_config(
            research_min_fetched_sources=1,
            research_relaxation_enabled=False,
        )
        scraper = AsyncMock()
        policy, _ = _build_pipeline(config, scraper)

        # Call can_synthesize without any prior on_tool_result calls
        gate = policy.can_synthesize()
        assert gate.verdict == SynthesisGateVerdict.hard_fail
        assert gate.total_fetched == 0
