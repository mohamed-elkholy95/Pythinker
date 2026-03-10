"""Unit tests for ResearchExecutionPolicy — ToolInterceptor orchestrator.

Tests cover:
- Intercepts info_search_web and wide_research tools
- Ignores non-search tools and failed tool results
- Preserves original search results (no override_memory_content)
- Appends evidence summary as extra_messages
- Delegates can_synthesize to SynthesisGuard
- Accumulates evidence across multiple search calls
- Feeds evidence to SourceTracker via add_source
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    EvidenceRecord,
    QueryContext,
    SelectedSource,
    SourceType,
    SynthesisGateResult,
    SynthesisGateVerdict,
    ToolCallContext,
)
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.research_execution_policy import ResearchExecutionPolicy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _search_results(count: int = 5) -> SearchResults:
    return SearchResults(
        query="test",
        total_results=count,
        results=[
            SearchResultItem(
                title=f"R{i}",
                link=f"https://s{i}.com/p",
                snippet=f"C{i}.",
            )
            for i in range(count)
        ],
    )


def _tool_result(sr: SearchResults | None = None) -> ToolResult:
    return ToolResult(success=True, message="OK", data=sr or _search_results())


def _context(fn: str = "info_search_web") -> ToolCallContext:
    return ToolCallContext(
        tool_call_id="c1",
        function_name=fn,
        function_args={"query": "test"},
        step_id="s1",
        session_id="sess",
        research_mode="deep_research",
    )


def _selected_source(i: int = 0) -> SelectedSource:
    return SelectedSource(
        url=f"https://s{i}.com/p",
        domain=f"s{i}.com",
        title=f"Source {i}",
        original_snippet=f"Snippet {i}",
        original_rank=i,
        query="test",
        relevance_score=0.8,
        authority_score=0.7,
        freshness_score=1.0,
        rank_score=0.5,
        composite_score=0.75,
        source_type=SourceType.independent,
        source_importance="medium",
        selection_reason="Independent source (authority=0.70); composite=0.750",
    )


def _evidence_record(i: int = 0) -> EvidenceRecord:
    return EvidenceRecord(
        url=f"https://s{i}.com/p",
        domain=f"s{i}.com",
        title=f"Source {i}",
        source_type=SourceType.independent,
        authority_score=0.7,
        source_importance="medium",
        excerpt=f"Evidence excerpt {i}",
        content_length=5000,
        access_method=AccessMethod.scrapling_http,
        fetch_tier_reached=1,
        extraction_duration_ms=200,
        timestamp=_NOW,
        confidence_bucket=ConfidenceBucket.high,
        hard_fail_reasons=[],
        soft_fail_reasons=[],
        soft_point_total=0,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_selector() -> MagicMock:
    selector = MagicMock()
    selector.select.return_value = [_selected_source(i) for i in range(4)]
    return selector


@pytest.fixture
def mock_evidence_service() -> AsyncMock:
    service = AsyncMock()
    service.acquire.return_value = [_evidence_record(i) for i in range(4)]
    return service


@pytest.fixture
def mock_guard() -> MagicMock:
    guard = MagicMock()
    guard.evaluate.return_value = SynthesisGateResult(
        verdict=SynthesisGateVerdict.pass_,
        reasons=[],
        total_fetched=4,
        high_confidence_count=4,
        official_source_found=True,
        independent_source_found=True,
        thresholds_applied={
            "min_fetched": 3,
            "min_high_confidence": 2,
            "require_official": True,
            "require_independent": True,
            "relaxed": False,
        },
    )
    return guard


@pytest.fixture
def mock_source_tracker() -> MagicMock:
    tracker = MagicMock()
    tracker.add_source = MagicMock()
    return tracker


@pytest.fixture
def config() -> SimpleNamespace:
    return SimpleNamespace(
        research_telemetry_enabled=False,
        research_source_select_count=4,
    )


@pytest.fixture
def emit_event() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def policy(
    mock_selector: MagicMock,
    mock_evidence_service: AsyncMock,
    mock_guard: MagicMock,
    config: SimpleNamespace,
    mock_source_tracker: MagicMock,
) -> ResearchExecutionPolicy:
    return ResearchExecutionPolicy(
        source_selector=mock_selector,
        evidence_service=mock_evidence_service,
        synthesis_guard=mock_guard,
        config=config,
        source_tracker=mock_source_tracker,
    )


# ---------------------------------------------------------------------------
# TestInterceptsSearchTools
# ---------------------------------------------------------------------------


class TestInterceptsSearchTools:
    """ResearchExecutionPolicy intercepts search tools and ignores others."""

    @pytest.mark.asyncio
    async def test_intercepts_info_search_web(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
        mock_evidence_service: AsyncMock,
    ) -> None:
        """on_tool_result returns a result for info_search_web calls."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        mock_selector.select.assert_called_once()
        mock_evidence_service.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_intercepts_wide_research(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
    ) -> None:
        """on_tool_result also intercepts wide_research tool calls."""
        ctx = _context("wide_research")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        mock_selector.select.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_non_search_tool(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
    ) -> None:
        """on_tool_result returns None for non-search tools like file_read."""
        ctx = _context("file_read")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is None
        mock_selector.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_failed_search_result(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
    ) -> None:
        """on_tool_result returns None when the tool result is a failure."""
        ctx = _context("info_search_web")
        tr = ToolResult(success=False, message="Search failed", data=None)

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is None
        mock_selector.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_results(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
    ) -> None:
        """on_tool_result returns None when search returns no results."""
        ctx = _context("info_search_web")
        tr = ToolResult(success=True, message="OK", data=SearchResults(query="test", total_results=0, results=[]))

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is None
        mock_selector.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_none_data(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
    ) -> None:
        """on_tool_result returns None when tool_result.data is None."""
        ctx = _context("info_search_web")
        tr = ToolResult(success=True, message="OK", data=None)

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is None
        mock_selector.select.assert_not_called()


# ---------------------------------------------------------------------------
# TestEvidenceInjection
# ---------------------------------------------------------------------------


class TestEvidenceInjection:
    """Evidence summary is injected as extra_messages without overriding memory."""

    @pytest.mark.asyncio
    async def test_does_not_override_memory_content(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """The original search results are preserved in memory (no override)."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        assert result.override_memory_content is None

    @pytest.mark.asyncio
    async def test_appends_evidence_summary_as_extra_messages(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """Returns extra_messages with the evidence summary as a system message."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        assert result.extra_messages is not None
        assert len(result.extra_messages) == 1
        msg = result.extra_messages[0]
        assert msg["role"] == "system"
        assert "Research Evidence Acquired" in msg["content"]

    @pytest.mark.asyncio
    async def test_evidence_summary_contains_source_urls(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """Evidence summary lists URLs from acquired evidence records."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        content = result.extra_messages[0]["content"]
        # At least one URL from the evidence records should appear
        assert "https://s0.com/p" in content

    @pytest.mark.asyncio
    async def test_evidence_summary_instruction_present(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """Evidence summary ends with an instruction to use evidence."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        content = result.extra_messages[0]["content"]
        assert "Do not rely on search snippets alone" in content

    @pytest.mark.asyncio
    async def test_suppress_memory_content_is_false(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """suppress_memory_content is False — original results stay in memory."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is not None
        assert result.suppress_memory_content is False

    @pytest.mark.asyncio
    async def test_progress_events_emitted(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """ProgressEvents are emitted during the pipeline run."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        # At minimum, the policy emits "Selecting" and "Acquiring" progress events
        assert emit_event.call_count >= 2


# ---------------------------------------------------------------------------
# TestSynthesisGate
# ---------------------------------------------------------------------------


class TestSynthesisGate:
    """can_synthesize delegates to SynthesisGuard and evidence accumulates."""

    def test_can_synthesize_delegates_to_guard(
        self,
        policy: ResearchExecutionPolicy,
        mock_guard: MagicMock,
    ) -> None:
        """can_synthesize calls guard.evaluate with accumulated evidence."""
        result = policy.can_synthesize()

        mock_guard.evaluate.assert_called_once_with(
            [],  # no evidence yet
            0,  # no search results yet
            None,  # no query context
        )
        assert result.verdict == SynthesisGateVerdict.pass_

    def test_can_synthesize_passes_query_context(
        self,
        policy: ResearchExecutionPolicy,
        mock_guard: MagicMock,
    ) -> None:
        """can_synthesize forwards the current query_context to the guard."""
        ctx = QueryContext(task_intent="Find pricing info", time_sensitive=True)
        policy.set_query_context(ctx)

        policy.can_synthesize()

        mock_guard.evaluate.assert_called_once_with([], 0, ctx)

    @pytest.mark.asyncio
    async def test_accumulates_evidence_across_multiple_calls(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_evidence_service: AsyncMock,
    ) -> None:
        """evidence_records accumulates after multiple on_tool_result calls."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        await policy.on_tool_result(tr, "s1", ctx, emit_event)
        await policy.on_tool_result(tr, "s2", ctx, emit_event)

        # 4 records per call x 2 calls = 8
        assert len(policy.evidence_records) == 8

    @pytest.mark.asyncio
    async def test_total_search_results_accumulates(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_guard: MagicMock,
    ) -> None:
        """total_search_results increments across multiple on_tool_result calls."""
        ctx = _context("info_search_web")
        sr = _search_results(5)
        tr = _tool_result(sr)

        await policy.on_tool_result(tr, "s1", ctx, emit_event)
        await policy.on_tool_result(tr, "s2", ctx, emit_event)

        # Now call can_synthesize — it should pass total_search_results=2
        policy.can_synthesize()
        _, call_total, _ = mock_guard.evaluate.call_args[0]
        assert call_total == 2

    @pytest.mark.asyncio
    async def test_evidence_records_property_returns_copy(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
    ) -> None:
        """evidence_records returns a copy; mutating it does not affect internal state."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        await policy.on_tool_result(tr, "s1", ctx, emit_event)
        records_copy = policy.evidence_records
        records_copy.clear()

        # Internal state unaffected
        assert len(policy.evidence_records) == 4


# ---------------------------------------------------------------------------
# TestSourceTrackerIntegration
# ---------------------------------------------------------------------------


class TestSourceTrackerIntegration:
    """Evidence records are fed to SourceTracker via add_source."""

    @pytest.mark.asyncio
    async def test_add_source_called_for_each_evidence_record(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_source_tracker: MagicMock,
    ) -> None:
        """add_source is called once per acquired evidence record."""
        ctx = _context("info_search_web")
        tr = _tool_result()

        await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        # 4 evidence records → 4 add_source calls
        assert mock_source_tracker.add_source.call_count == 4

    @pytest.mark.asyncio
    async def test_add_source_receives_source_citation(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_source_tracker: MagicMock,
    ) -> None:
        """add_source receives SourceCitation objects (not raw EvidenceRecords)."""
        from app.domain.models.source_citation import SourceCitation

        ctx = _context("info_search_web")
        tr = _tool_result()

        await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        for call in mock_source_tracker.add_source.call_args_list:
            citation = call[0][0]
            assert isinstance(citation, SourceCitation)

    @pytest.mark.asyncio
    async def test_add_source_not_called_when_no_sources_selected(
        self,
        policy: ResearchExecutionPolicy,
        emit_event: AsyncMock,
        mock_selector: MagicMock,
        mock_source_tracker: MagicMock,
    ) -> None:
        """add_source is not called when selector returns no sources."""
        mock_selector.select.return_value = []

        ctx = _context("info_search_web")
        tr = _tool_result()

        result = await policy.on_tool_result(tr, "serialized", ctx, emit_event)

        assert result is None
        mock_source_tracker.add_source.assert_not_called()
