"""Integration tests for the deterministic research pipeline in shadow mode.

Shadow mode: pipeline runs alongside the existing flow, logs decisions,
but does NOT block synthesis even when evidence quality thresholds fail.

The shadow mode gating logic lives in ExecutionAgent._check_synthesis_gate()
(backend/app/domain/services/agents/execution.py). In shadow mode, that method
calls can_synthesize() (which still evaluates the guard), logs the verdict, then
returns None so that the caller never blocks on a hard_fail.

These tests verify:
1. Shadow mode does not block synthesis (gate returns None / PASS-equivalent)
2. Evidence is still collected and SourceTracker is still populated in shadow mode
3. Insufficient evidence that would HARD_FAIL in enforced mode → PASS in shadow
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
# Helpers (mirrors test_research_pipeline_integration.py)
# ---------------------------------------------------------------------------


def _make_config(**overrides: object) -> SimpleNamespace:
    """Return a SimpleNamespace with all required research pipeline config fields."""
    defaults = {
        # Feature flags
        "research_deterministic_pipeline_enabled": True,
        "research_pipeline_mode": "shadow",  # shadow by default in this test module
        # Source selection
        "research_source_select_count": 4,
        "research_source_max_per_domain": 1,
        "research_source_allow_multi_page_domains": True,
        # Scoring weights
        "research_weight_relevance": 0.35,
        "research_weight_authority": 0.25,
        "research_weight_freshness": 0.20,
        "research_weight_rank": 0.20,
        # Acquisition
        "research_acquisition_concurrency": 4,
        "research_acquisition_timeout_seconds": 30.0,
        "research_excerpt_chars": 2000,
        "research_full_content_offload": False,
        # Confidence thresholds
        "research_soft_fail_verify_threshold": 2,
        "research_soft_fail_required_threshold": 3,
        "research_thin_content_chars": 500,
        "research_boilerplate_ratio_threshold": 0.6,
        # Synthesis gate — strict defaults that would normally block
        "research_min_fetched_sources": 5,
        "research_min_high_confidence": 4,
        "research_require_official_source": True,
        "research_require_independent_source": True,
        # Synthesis gate — relaxed
        "research_relaxation_enabled": False,  # disabled so hard_fail is unambiguous
        "research_relaxed_min_fetched_sources": 3,
        "research_relaxed_min_high_confidence": 2,
        "research_relaxed_require_official_source": False,
        # Telemetry
        "research_telemetry_enabled": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_scraper_response(
    text: str = "Comprehensive article content here. " * 50,
    tier_used: str = "http",
) -> SimpleNamespace:
    return SimpleNamespace(
        success=True,
        text=text,
        tier_used=tier_used,
        status_code=200,
        error=None,
    )


def _make_search_results(urls: list[str], query: str = "shadow mode test") -> SearchResults:
    return SearchResults(
        query=query,
        results=[
            SearchResultItem(
                title=f"Article {i} — {query}",
                link=url,
                snippet=f"Content about {query} on site {i}.",
            )
            for i, url in enumerate(urls, start=1)
        ],
    )


def _make_tool_call_context(
    function_name: str = "info_search_web",
    query: str = "shadow mode test",
    session_id: str = "shadow-session",
    step_id: str = "step-shadow",
) -> ToolCallContext:
    return ToolCallContext(
        tool_call_id="tc-shadow-001",
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
    """Wire pipeline components; config has research_pipeline_mode='shadow'."""
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
# TestShadowModeGate
# ---------------------------------------------------------------------------


class TestShadowModeGate:
    """In shadow mode, the execution agent's _check_synthesis_gate returns None
    (non-blocking) even when can_synthesize() would return HARD_FAIL."""

    @pytest.mark.asyncio
    async def test_shadow_mode_does_not_block_synthesis(self) -> None:
        """Insufficient evidence → can_synthesize() returns HARD_FAIL (guard logic
        still runs), but ExecutionAgent._check_synthesis_gate() returns None in
        shadow mode so synthesis is never blocked."""
        config = _make_config(
            research_pipeline_mode="shadow",
            research_min_fetched_sources=5,
            research_min_high_confidence=4,
            research_relaxation_enabled=False,
        )
        # Scraper returns empty content → all records have content_length == 0
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")
        )

        policy, _ = _build_pipeline(config, scraper)

        # Feed only 1 search result (far below the threshold of 5)
        search_results = _make_search_results(
            urls=["https://thin-site.com/article"],
            query="shadow mode test",
        )
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        # The raw guard verdict would be HARD_FAIL (policy.can_synthesize())
        raw_gate = policy.can_synthesize()
        assert raw_gate.verdict == SynthesisGateVerdict.hard_fail

        # Simulate how ExecutionAgent._check_synthesis_gate() handles shadow mode.
        # get_settings is imported locally inside the method, so we patch the
        # canonical location: app.core.config.get_settings.
        with patch("app.core.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.research_pipeline_mode = "shadow"
            mock_get_settings.return_value = mock_settings

            from app.domain.services.agents.execution import ExecutionAgent

            # Create a minimal ExecutionAgent stub to test _check_synthesis_gate
            agent = object.__new__(ExecutionAgent)
            agent._research_execution_policy = policy  # type: ignore[attr-defined]

            result = agent._check_synthesis_gate()  # type: ignore[attr-defined]

        # Shadow mode → _check_synthesis_gate returns None (never blocks)
        assert result is None

    @pytest.mark.asyncio
    async def test_enforced_mode_blocks_synthesis_on_hard_fail(self) -> None:
        """In enforced mode, HARD_FAIL verdict causes _check_synthesis_gate to
        return the SynthesisGateResult (caller can block synthesis)."""
        config = _make_config(
            research_pipeline_mode="enforced",
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
                urls=["https://thin-site.com/article"],
                query="enforced mode test",
            )),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        with patch("app.core.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.research_pipeline_mode = "enforced"
            mock_get_settings.return_value = mock_settings

            from app.domain.services.agents.execution import ExecutionAgent

            agent = object.__new__(ExecutionAgent)
            agent._research_execution_policy = policy  # type: ignore[attr-defined]

            result = agent._check_synthesis_gate()  # type: ignore[attr-defined]

        # Enforced mode → returns the gate result (non-None) for HARD_FAIL
        assert result is not None
        assert result.verdict == SynthesisGateVerdict.hard_fail

    @pytest.mark.asyncio
    async def test_shadow_mode_logs_verdict(self) -> None:
        """Shadow mode calls can_synthesize() and logs the verdict (no exception)."""
        config = _make_config(research_pipeline_mode="shadow")
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")
        )

        policy, _ = _build_pipeline(config, scraper)
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=_make_search_results(
                urls=["https://some-site.com/page"],
                query="shadow test",
            )),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        with patch("app.core.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.research_pipeline_mode = "shadow"
            mock_get_settings.return_value = mock_settings

            from app.domain.services.agents.execution import ExecutionAgent

            agent = object.__new__(ExecutionAgent)
            agent._research_execution_policy = policy  # type: ignore[attr-defined]

            # Must not raise; shadow mode swallows the gate failure silently
            result = agent._check_synthesis_gate()  # type: ignore[attr-defined]

        assert result is None  # Shadow mode always returns None


# ---------------------------------------------------------------------------
# TestShadowModeEvidenceCollection
# ---------------------------------------------------------------------------


class TestShadowModeEvidenceCollection:
    """Even in shadow mode, evidence is still collected and the tracker is populated.

    Shadow mode only affects the gating decision — the pipeline still runs fully.
    """

    @pytest.mark.asyncio
    async def test_shadow_mode_still_collects_evidence(self) -> None:
        """Evidence records are created in shadow mode (pipeline runs in full)."""
        config = _make_config(research_pipeline_mode="shadow")
        good_text = "Complete article with Python testing details. " * 60
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _tracker = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=[
                "https://docs.python.org/testing",
                "https://pytest.org/guide",
            ],
            query="python testing shadow",
        )

        result = await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(query="python testing shadow"),
            emit_event=AsyncMock(),
        )

        # Pipeline still fired, records created
        assert result is not None
        assert len(policy.evidence_records) > 0

    @pytest.mark.asyncio
    async def test_shadow_mode_source_tracker_populated(self) -> None:
        """SourceTracker is populated in shadow mode exactly like in enforced mode."""
        config = _make_config(research_pipeline_mode="shadow")
        good_text = "Detailed article about Python. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, tracker = _build_pipeline(config, scraper)
        urls = ["https://python.org", "https://docs.python.org/3"]
        search_results = _make_search_results(urls=urls, query="python shadow")

        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(query="python shadow"),
            emit_event=AsyncMock(),
        )

        assert tracker.source_count > 0
        collected_urls = {s.url for s in tracker.get_collected_sources()}
        for record in policy.evidence_records:
            assert record.url in collected_urls

    @pytest.mark.asyncio
    async def test_shadow_mode_extra_messages_injected(self) -> None:
        """on_tool_result still injects evidence summary (extra_messages) in shadow mode."""
        config = _make_config(research_pipeline_mode="shadow")
        good_text = "Complete reference article for Python testing. " * 50
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=["https://testsite.com/python"],
            query="python shadow test",
        )

        result = await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(query="python shadow test"),
            emit_event=AsyncMock(),
        )

        assert result is not None
        assert result.extra_messages is not None
        content = result.extra_messages[0]["content"]
        assert "Research Evidence Acquired" in content

    @pytest.mark.asyncio
    async def test_shadow_mode_records_have_confidence_buckets(self) -> None:
        """Evidence records in shadow mode carry valid confidence buckets."""
        config = _make_config(research_pipeline_mode="shadow")
        good_text = "Detailed Python article covering unit testing in depth. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=["https://realpython.com/testing", "https://coverage.io/guide"],
            query="python testing shadow",
        )

        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(query="python testing shadow"),
            emit_event=AsyncMock(),
        )

        valid_buckets = {ConfidenceBucket.high, ConfidenceBucket.medium, ConfidenceBucket.low}
        for record in policy.evidence_records:
            assert record.confidence_bucket in valid_buckets


# ---------------------------------------------------------------------------
# TestShadowVsEnforcedComparison
# ---------------------------------------------------------------------------


class TestShadowVsEnforcedComparison:
    """Parity tests: shadow and enforced modes collect identical evidence;
    only the gate decision differs."""

    @pytest.mark.asyncio
    async def test_same_evidence_records_in_both_modes(self) -> None:
        """Evidence records are identical whether shadow or enforced mode is active.

        This confirms the mode flag only controls gating, not evidence acquisition.
        """
        good_text = "Rich Python testing article. " * 80
        urls = [
            "https://docs.python.org/testing",
            "https://pytest.org/guide",
            "https://realpython.com/python-testing",
        ]

        async def _run_with_mode(mode: str) -> list:
            cfg = _make_config(
                research_pipeline_mode=mode,
                research_min_fetched_sources=2,
                research_min_high_confidence=1,
                research_relaxation_enabled=True,
            )
            scraper = AsyncMock()
            scraper.fetch_with_escalation = AsyncMock(
                return_value=_make_scraper_response(text=good_text)
            )
            pol, _ = _build_pipeline(cfg, scraper)
            await pol.on_tool_result(
                tool_result=ToolResult.ok(data=_make_search_results(urls=urls)),
                serialized_content="",
                context=_make_tool_call_context(),
                emit_event=AsyncMock(),
            )
            return pol.evidence_records

        shadow_records = await _run_with_mode("shadow")
        enforced_records = await _run_with_mode("enforced")

        assert len(shadow_records) == len(enforced_records)
        shadow_urls = {r.url for r in shadow_records}
        enforced_urls = {r.url for r in enforced_records}
        assert shadow_urls == enforced_urls

    @pytest.mark.asyncio
    async def test_enforced_mode_gate_returns_pass_on_good_evidence(self) -> None:
        """In enforced mode, sufficient evidence still returns PASS (not just shadow)."""
        config = _make_config(
            research_pipeline_mode="enforced",
            research_min_fetched_sources=2,
            research_min_high_confidence=1,
            research_require_official_source=False,
            research_require_independent_source=False,
            research_relaxation_enabled=True,
        )
        good_text = "Comprehensive article with full details about Python. " * 80
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text=good_text)
        )

        policy, _ = _build_pipeline(config, scraper)
        search_results = _make_search_results(
            urls=[
                "https://python.org",
                "https://docs.python.org",
                "https://realpython.com",
            ],
            query="python",
        )

        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=search_results),
            serialized_content="",
            context=_make_tool_call_context(query="python"),
            emit_event=AsyncMock(),
        )

        gate = policy.can_synthesize()
        # With good content and relaxed thresholds, should PASS
        assert gate.verdict in {SynthesisGateVerdict.pass_, SynthesisGateVerdict.soft_fail}

    @pytest.mark.asyncio
    async def test_shadow_mode_can_synthesize_returns_verdict_not_none(self) -> None:
        """policy.can_synthesize() always returns a SynthesisGateResult regardless
        of pipeline mode — it's the execution agent that may return None to skip blocking."""
        config = _make_config(research_pipeline_mode="shadow")
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=_make_scraper_response(text="")
        )

        policy, _ = _build_pipeline(config, scraper)
        await policy.on_tool_result(
            tool_result=ToolResult.ok(data=_make_search_results(
                urls=["https://empty.com"],
                query="empty test",
            )),
            serialized_content="",
            context=_make_tool_call_context(),
            emit_event=AsyncMock(),
        )

        # can_synthesize() itself always returns a real result (not None)
        gate_result = policy.can_synthesize()
        assert gate_result is not None
        assert gate_result.verdict in set(SynthesisGateVerdict)
        # Thresholds applied dict is populated
        assert "min_fetched" in gate_result.thresholds_applied
