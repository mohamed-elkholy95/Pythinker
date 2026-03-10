"""Tests for EvidenceAcquisitionService.

Covers:
- Successful single and concurrent acquisition
- Excerpt truncation and full content offload
- Browser promotion: hard-fail triggers browser, browser changes outcome,
  no promotion when confidence is already high
- Failure handling: scraper exception produces a failed record, browser
  failure falls back gracefully
- Progress event emission
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    QueryContext,
    SelectedSource,
    SourceType,
)
from app.domain.services.agents.evidence_acquisition import EvidenceAcquisitionService
from app.domain.services.agents.tool_result_store import ToolResultStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(**overrides: object) -> SimpleNamespace:
    defaults = {
        "research_acquisition_concurrency": 4,
        "research_acquisition_timeout_seconds": 30.0,
        "research_excerpt_chars": 2000,
        "research_full_content_offload": True,
        "research_soft_fail_verify_threshold": 2,
        "research_soft_fail_required_threshold": 3,
        "research_thin_content_chars": 500,
        "research_boilerplate_ratio_threshold": 0.6,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _source(
    url: str = "https://example.com/article",
    domain: str = "example.com",
    title: str = "Example Article",
    importance: str = "medium",
    rank: int = 1,
) -> SelectedSource:
    return SelectedSource(
        url=url,
        domain=domain,
        title=title,
        original_snippet="A short snippet.",
        original_rank=rank,
        query="test query",
        relevance_score=0.8,
        authority_score=0.7,
        freshness_score=0.6,
        rank_score=0.5,
        composite_score=0.7,
        source_type=SourceType.authoritative_neutral,
        source_importance=importance,  # type: ignore[arg-type]
        selection_reason="high composite score",
        domain_diversity_applied=False,
    )


def _good_scraped(text: str = "Comprehensive content. " * 50) -> SimpleNamespace:
    return SimpleNamespace(
        success=True,
        text=text,
        url="https://example.com/article",
        tier_used="http",
        status_code=200,
        error=None,
        title="Example Article",
        html=None,
        metadata={},
    )


def _failed_scraped(error: str = "Connection refused") -> SimpleNamespace:
    return SimpleNamespace(
        success=False,
        text="",
        url="https://example.com/article",
        tier_used=None,
        status_code=None,
        error=error,
        title=None,
        html=None,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_scraper() -> AsyncMock:
    scraper = AsyncMock()
    scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped())
    return scraper


@pytest.fixture
def mock_browser() -> AsyncMock:
    browser = AsyncMock()
    browser.navigate = AsyncMock(return_value=SimpleNamespace(content="Full browser content with JS rendered. " * 100))
    return browser


@pytest.fixture
def mock_store() -> MagicMock:
    store = MagicMock()
    store.offload_threshold = 4000
    store.should_offload = MagicMock(side_effect=lambda content: len(content) > 4000)
    store.store = MagicMock(return_value=("trs-abc123", "preview..."))
    return store


@pytest.fixture
def emit_event() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# TestSuccessfulAcquisition
# ---------------------------------------------------------------------------


class TestSuccessfulAcquisition:
    """EvidenceAcquisitionService returns correct EvidenceRecords for good sources."""

    @pytest.mark.asyncio
    async def test_single_source_returns_one_record(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records) == 1
        record = records[0]
        assert record.url == "https://example.com/article"
        assert record.domain == "example.com"
        assert record.title == "Example Article"
        assert record.content_length > 0
        assert record.access_method == AccessMethod.scrapling_http
        assert record.fetch_tier_reached == 1

    @pytest.mark.asyncio
    async def test_multiple_sources_all_acquired_concurrently(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        sources = [_source(url=f"https://site{i}.com/page", domain=f"site{i}.com", rank=i) for i in range(1, 5)]
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire(sources, query_context=None, emit_event=emit_event)

        assert len(records) == 4
        assert mock_scraper.fetch_with_escalation.call_count == 4

    @pytest.mark.asyncio
    async def test_excerpt_truncated_to_config_chars(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        emit_event: AsyncMock,
    ) -> None:
        long_text = "word " * 1000  # ~5000 chars
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=long_text))
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=None,
            config=_config(research_excerpt_chars=200),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records[0].excerpt) <= 200

    @pytest.mark.asyncio
    async def test_content_offloaded_when_above_threshold(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # store.offload_threshold is 4000; content "word " * 1000 is ~5000 chars
        long_text = "word " * 1000
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=long_text))
        mock_store.offload_threshold = 4000

        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].content_ref == "trs-abc123"
        mock_store.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_offload_when_content_below_threshold(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        short_text = "word " * 100  # ~500 chars, below 4000
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=short_text))
        mock_store.offload_threshold = 4000

        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].content_ref is None
        mock_store.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_offload_disabled_skips_store_even_for_large_content(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        long_text = "word " * 1000
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=long_text))
        mock_store.offload_threshold = 4000

        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(research_full_content_offload=False),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].content_ref is None
        mock_store.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_tier_mapping_dynamic_sets_tier_2(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        scraper = AsyncMock()
        dynamic_scraped = SimpleNamespace(
            success=True,
            text="Dynamic rendered content. " * 50,
            url="https://example.com/article",
            tier_used="dynamic",
            status_code=200,
            error=None,
            title="Example",
            html=None,
            metadata={},
        )
        scraper.fetch_with_escalation = AsyncMock(return_value=dynamic_scraped)

        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].fetch_tier_reached == 2
        assert records[0].access_method == AccessMethod.scrapling_dynamic

    @pytest.mark.asyncio
    async def test_tier_mapping_stealthy_sets_tier_3(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        scraper = AsyncMock()
        stealthy_scraped = SimpleNamespace(
            success=True,
            text="Stealthy rendered content. " * 50,
            url="https://example.com/article",
            tier_used="stealthy",
            status_code=200,
            error=None,
            title="Example",
            html=None,
            metadata={},
        )
        scraper.fetch_with_escalation = AsyncMock(return_value=stealthy_scraped)

        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].fetch_tier_reached == 3
        assert records[0].access_method == AccessMethod.scrapling_stealthy

    @pytest.mark.asyncio
    async def test_source_metadata_preserved(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        src = _source(importance="high")
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([src], query_context=None, emit_event=emit_event)

        record = records[0]
        assert record.source_importance == "high"
        assert record.original_rank == 1
        assert record.query == "test query"
        assert record.source_type == SourceType.authoritative_neutral


# ---------------------------------------------------------------------------
# TestBrowserPromotion
# ---------------------------------------------------------------------------


class TestBrowserPromotion:
    """Browser promotion triggered by confidence signals."""

    @pytest.mark.asyncio
    async def test_required_promotion_triggers_browser(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Empty content → extraction_failure hard fail → REQUIRED promotion
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text="",  # empty → hard fail
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example",
                html=None,
                metadata={},
            )
        )
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        mock_browser.navigate.assert_called_once()
        assert records[0].browser_promoted is True

    @pytest.mark.asyncio
    async def test_browser_changes_outcome_sets_access_method(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Empty scrapled content → browser provides rich content
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text="",
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example",
                html=None,
                metadata={},
            )
        )
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        record = records[0]
        assert record.access_method == AccessMethod.browser_promoted
        assert record.browser_changed_outcome is True

    @pytest.mark.asyncio
    async def test_no_browser_when_confidence_high(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Good content → high confidence → no browser call
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        mock_browser.navigate.assert_not_called()
        assert records[0].browser_promoted is False

    @pytest.mark.asyncio
    async def test_verify_if_high_importance_triggers_browser_for_high_source(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Content between _MIN_CONTENT_CHARS (50) and thin_content_chars (300) →
        # thin_content soft fail fires, verify_threshold=1 → VERIFY_IF_HIGH_IMPORTANCE
        # source_importance=high → browser should be called
        scraper = AsyncMock()
        # 80 unique words — above 50 char min, below 300 thin threshold, good density
        thin_text = " ".join(f"word{i}" for i in range(80))  # ~560 chars, 80 unique words
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text=thin_text,
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example Article",
                html=None,
                metadata={},
            )
        )
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            # thin_content_chars=600 so thin_text (~560 chars) triggers thin_content soft fail
            # verify_threshold=1 → VERIFY_IF_HIGH_IMPORTANCE
            # required_threshold=4 → does NOT go to REQUIRED
            config=_config(
                research_soft_fail_verify_threshold=1,
                research_soft_fail_required_threshold=4,
                research_thin_content_chars=600,
            ),
        )
        await svc.acquire([_source(importance="high")], query_context=None, emit_event=emit_event)

        mock_browser.navigate.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_if_high_importance_no_browser_for_medium_source(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Same setup but source_importance=medium → browser NOT called
        scraper = AsyncMock()
        thin_text = " ".join(f"word{i}" for i in range(80))  # ~560 chars
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text=thin_text,
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example Article",
                html=None,
                metadata={},
            )
        )
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(
                research_soft_fail_verify_threshold=1,
                research_soft_fail_required_threshold=4,
                research_thin_content_chars=600,
            ),
        )
        await svc.acquire([_source(importance="medium")], query_context=None, emit_event=emit_event)

        mock_browser.navigate.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_browser_when_browser_is_none(
        self,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Empty content → would require browser, but browser=None → graceful
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text="",
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example",
                html=None,
                metadata={},
            )
        )
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=None,
            tool_result_store=mock_store,
            config=_config(),
        )
        # Must not raise
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records) == 1
        assert records[0].browser_promoted is False


# ---------------------------------------------------------------------------
# TestFailureHandling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    """Exception paths produce failed records, never crash the pipeline."""

    @pytest.mark.asyncio
    async def test_scraper_exception_produces_failed_record(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(side_effect=RuntimeError("network error"))
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records) == 1
        record = records[0]
        assert record.content_length == 0
        assert "extraction_failure" in record.hard_fail_reasons
        assert record.confidence_bucket == ConfidenceBucket.low

    @pytest.mark.asyncio
    async def test_timeout_exception_produces_failed_record(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:

        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(side_effect=TimeoutError())
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].confidence_bucket == ConfidenceBucket.low
        assert "extraction_failure" in records[0].hard_fail_reasons

    @pytest.mark.asyncio
    async def test_browser_failure_falls_back_gracefully(
        self,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        # Empty scrape → REQUIRED promotion → browser throws → record still returned
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                text="",
                url="https://example.com/article",
                tier_used="http",
                status_code=200,
                error=None,
                title="Example",
                html=None,
                metadata={},
            )
        )
        failing_browser = AsyncMock()
        failing_browser.navigate = AsyncMock(side_effect=RuntimeError("browser crash"))

        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=failing_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records) == 1
        # Record is returned even though browser failed
        record = records[0]
        assert record.browser_promoted is False
        assert record.browser_changed_outcome is False

    @pytest.mark.asyncio
    async def test_partial_failure_does_not_cancel_other_sources(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        call_count = 0

        async def flaky(url: str, **kwargs: object) -> SimpleNamespace:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first source fails")
            return _good_scraped()

        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(side_effect=flaky)

        sources = [
            _source(url="https://fail.com/page", domain="fail.com", rank=1),
            _source(url="https://ok.com/page", domain="ok.com", rank=2),
        ]
        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire(sources, query_context=None, emit_event=emit_event)

        assert len(records) == 2
        # First is failed, second is successful
        failed = next(r for r in records if r.domain == "fail.com")
        ok = next(r for r in records if r.domain == "ok.com")
        assert failed.confidence_bucket == ConfidenceBucket.low
        assert ok.confidence_bucket in {ConfidenceBucket.high, ConfidenceBucket.medium}


# ---------------------------------------------------------------------------
# TestEventEmission
# ---------------------------------------------------------------------------


class TestEventEmission:
    """EvidenceAcquisitionService emits progress events during acquisition."""

    @pytest.mark.asyncio
    async def test_emits_at_least_one_progress_event_per_source(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        sources = [_source(url=f"https://s{i}.com/p", domain=f"s{i}.com") for i in range(3)]
        await svc.acquire(sources, query_context=None, emit_event=emit_event)

        # At least one event per source
        assert emit_event.call_count >= 3

    @pytest.mark.asyncio
    async def test_emitted_event_contains_domain(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        await svc.acquire([_source(domain="specific-domain.com")], query_context=None, emit_event=emit_event)

        # Find any call that mentions the domain
        all_calls = emit_event.call_args_list
        found = any("specific-domain.com" in str(call) for call in all_calls)
        assert found, "Expected domain name in emitted progress event"

    @pytest.mark.asyncio
    async def test_events_emitted_even_on_failure(
        self,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        scraper = AsyncMock()
        scraper.fetch_with_escalation = AsyncMock(side_effect=RuntimeError("boom"))

        svc = EvidenceAcquisitionService(
            scraper=scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert emit_event.call_count >= 1


# ---------------------------------------------------------------------------
# TestQueryContextPropagation
# ---------------------------------------------------------------------------


class TestQueryContextPropagation:
    """QueryContext is forwarded to the confidence assessor."""

    @pytest.mark.asyncio
    async def test_query_context_passed_to_assessor(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        query_ctx = QueryContext(
            task_intent="Find Python info",
            required_entities=["Python", "Guido"],
            time_sensitive=False,
            comparative=False,
        )
        # Content that clearly contains both entities
        rich_text = "Python is a high-level language created by Guido van Rossum. " * 30
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=rich_text))
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        records = await svc.acquire([_source()], query_context=query_ctx, emit_event=emit_event)

        assert len(records) == 1
        # Entities present → should have high confidence
        assert records[0].confidence_bucket in {ConfidenceBucket.high, ConfidenceBucket.medium}

    @pytest.mark.asyncio
    async def test_none_query_context_handled(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        mock_store: MagicMock,
        emit_event: AsyncMock,
    ) -> None:
        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=mock_store,
            config=_config(),
        )
        # Should not raise
        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert len(records) == 1


# ---------------------------------------------------------------------------
# TestRealToolResultStoreIntegration
# ---------------------------------------------------------------------------


class TestRealToolResultStoreIntegration:
    """Verify EvidenceAcquisitionService works with a real ToolResultStore (not MagicMock)."""

    @pytest.mark.asyncio
    async def test_content_offloaded_with_real_tool_result_store(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        emit_event: AsyncMock,
    ) -> None:
        """Real ToolResultStore integration should offload large content without AttributeError."""
        long_text = "word " * 1000  # ~5000 chars
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=long_text))
        store = ToolResultStore(offload_threshold=4000, preview_chars=120)

        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=store,
            config=_config(),
        )

        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].content_ref is not None
        assert store.retrieve(records[0].content_ref) is not None

    @pytest.mark.asyncio
    async def test_no_offload_with_real_store_below_threshold(
        self,
        mock_scraper: AsyncMock,
        mock_browser: AsyncMock,
        emit_event: AsyncMock,
    ) -> None:
        """Content below threshold should not be offloaded with real ToolResultStore."""
        short_text = "word " * 100  # ~500 chars, below 4000
        mock_scraper.fetch_with_escalation = AsyncMock(return_value=_good_scraped(text=short_text))
        store = ToolResultStore(offload_threshold=4000, preview_chars=120)

        svc = EvidenceAcquisitionService(
            scraper=mock_scraper,
            browser=mock_browser,
            tool_result_store=store,
            config=_config(),
        )

        records = await svc.acquire([_source()], query_context=None, emit_event=emit_event)

        assert records[0].content_ref is None
