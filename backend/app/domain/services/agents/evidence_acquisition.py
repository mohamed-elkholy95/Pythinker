"""Evidence acquisition service for the deterministic research pipeline.

Acquires evidence for selected sources using Scrapling as the primary
3-tier web extractor.  When extraction confidence is low a browser
promotion path is optionally taken to improve content quality.

Architecture
------------
- Primary path: ScraplingAdapter.fetch_with_escalation (HTTP → Dynamic → Stealthy)
- Promotion path: Browser.navigate (CDP-controlled Chromium)
- Content offload: ToolResultStore (keeps EvidenceRecord compact)
- Confidence routing: ContentConfidenceAssessor (rule-based, no LLM)
- Concurrency: asyncio.gather with per-source timeout
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    EvidenceRecord,
    PromotionDecision,
    QueryContext,
    SelectedSource,
)
from app.domain.services.agents.content_confidence import ContentConfidenceAssessor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier mappings
# ---------------------------------------------------------------------------

_TIER_MAP: dict[str | None, int] = {
    "http": 1,
    "dynamic": 2,
    "stealthy": 3,
}

_ACCESS_METHOD_MAP: dict[int, AccessMethod] = {
    1: AccessMethod.scrapling_http,
    2: AccessMethod.scrapling_dynamic,
    3: AccessMethod.scrapling_stealthy,
}

# Minimum content length from browser to count as a meaningful improvement
_BROWSER_MIN_IMPROVEMENT_CHARS: int = 50


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EvidenceAcquisitionService:
    """Acquires evidence for selected sources with confidence-based browser promotion.

    Args:
        scraper: ScraplingAdapter with ``fetch_with_escalation`` async method.
        browser: Browser protocol with ``navigate`` async method, or None when
            browser promotion is unavailable.
        tool_result_store: ToolResultStore for offloading large content, or None.
        config: Configuration object exposing:
            - research_acquisition_concurrency (int)
            - research_acquisition_timeout_seconds (float)
            - research_excerpt_chars (int)
            - research_full_content_offload (bool)
            - research_soft_fail_verify_threshold (int)
            - research_soft_fail_required_threshold (int)
            - research_thin_content_chars (int)
            - research_boilerplate_ratio_threshold (float)
    """

    def __init__(
        self,
        scraper: Any,
        browser: Any | None,
        tool_result_store: Any | None,
        config: Any,
    ) -> None:
        self._scraper = scraper
        self._browser = browser
        self._store = tool_result_store
        self._config = config
        self._confidence_assessor = ContentConfidenceAssessor(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(
        self,
        sources: list[SelectedSource],
        query_context: QueryContext | None,
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> list[EvidenceRecord]:
        """Acquire evidence for all selected sources concurrently.

        Sources are processed with bounded concurrency via a semaphore.
        Each source acquisition is wrapped in an exception guard so that
        a single failure never cancels the rest.

        Args:
            sources: Sources chosen by SourceSelector.
            query_context: Optional intent context forwarded to the assessor.
            emit_event: Async callable for emitting ProgressEvents.

        Returns:
            List of EvidenceRecords in the same order as ``sources``.
        """
        concurrency = getattr(self._config, "research_acquisition_concurrency", 4)
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded(source: SelectedSource) -> EvidenceRecord:
            async with semaphore:
                return await self._acquire_single(source, query_context, emit_event)

        results = await asyncio.gather(
            *(_bounded(src) for src in sources),
            return_exceptions=False,
        )
        return list(results)

    # ------------------------------------------------------------------
    # Private: per-source acquisition
    # ------------------------------------------------------------------

    async def _acquire_single(
        self,
        source: SelectedSource,
        query_context: QueryContext | None,
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> EvidenceRecord:
        """Acquire evidence for a single source.

        Wraps the full fetch → assess → optionally promote → build record
        pipeline.  Any unhandled exception produces a failed record.
        """
        await emit_event(
            ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message=f"Fetching evidence: {source.domain}",
            )
        )

        start_ms = int(time.monotonic() * 1000)

        try:
            return await self._fetch_and_assess(source, query_context, start_ms)
        except Exception:
            logger.warning(
                "Evidence acquisition failed for %s",
                source.url,
                exc_info=True,
            )
            elapsed_ms = int(time.monotonic() * 1000) - start_ms
            return self._build_failed_record(source, elapsed_ms)

    async def _fetch_and_assess(
        self,
        source: SelectedSource,
        query_context: QueryContext | None,
        start_ms: int,
    ) -> EvidenceRecord:
        """Core acquisition logic: fetch → assess → maybe promote → record."""
        timeout: float = getattr(
            self._config, "research_acquisition_timeout_seconds", 30.0
        )

        # 1. Primary fetch via Scrapling
        scraped = await asyncio.wait_for(
            self._scraper.fetch_with_escalation(source.url),
            timeout=timeout,
        )

        content: str = scraped.text or ""
        tier_used: int = _TIER_MAP.get(scraped.tier_used, 1)

        # 2. Initial confidence assessment
        assessment = self._confidence_assessor.assess(
            content=content,
            url=source.url,
            domain=source.domain,
            title=source.title,
            source_importance=source.source_importance,
            query_context=query_context,
        )

        # 3. Browser promotion decision
        browser_promoted = False
        browser_changed_outcome = False
        access_method = _ACCESS_METHOD_MAP.get(tier_used, AccessMethod.scrapling_http)

        needs_promotion = assessment.promotion_decision == PromotionDecision.required or (
            assessment.promotion_decision == PromotionDecision.verify_if_high_importance
            and source.source_importance == "high"
        )

        if needs_promotion and self._browser is not None:
            browser_content = await self._browser_extract(source.url)
            if browser_content and len(browser_content) > max(
                len(content), _BROWSER_MIN_IMPROVEMENT_CHARS
            ):
                content = browser_content
                browser_promoted = True
                browser_changed_outcome = True
                access_method = AccessMethod.browser_promoted

                # Re-assess with browser content
                assessment = self._confidence_assessor.assess(
                    content=content,
                    url=source.url,
                    domain=source.domain,
                    title=source.title,
                    source_importance=source.source_importance,
                    query_context=query_context,
                )

        # 4. Excerpt + optional offload
        excerpt_chars: int = getattr(self._config, "research_excerpt_chars", 2000)
        excerpt = content[:excerpt_chars]

        content_ref: str | None = None
        if self._store is not None and len(content) > self._store.offload_threshold:
            result_id, _preview = self._store.store(content, "evidence_acquisition")
            content_ref = result_id

        elapsed_ms = int(time.monotonic() * 1000) - start_ms

        return EvidenceRecord(
            url=source.url,
            domain=source.domain,
            title=source.title,
            source_type=source.source_type,
            authority_score=source.authority_score,
            source_importance=source.source_importance,
            excerpt=excerpt,
            content_length=assessment.content_length,
            content_ref=content_ref,
            access_method=access_method,
            fetch_tier_reached=tier_used,
            extraction_duration_ms=elapsed_ms,
            timestamp=datetime.now(UTC),
            confidence_bucket=assessment.confidence_bucket,
            hard_fail_reasons=[r.value for r in assessment.hard_fails],
            soft_fail_reasons=[r.value for r in assessment.soft_fails],
            soft_point_total=assessment.soft_point_total,
            browser_promoted=browser_promoted,
            browser_changed_outcome=browser_changed_outcome,
            original_snippet=source.original_snippet,
            original_rank=source.original_rank,
            query=source.query,
        )

    # ------------------------------------------------------------------
    # Private: browser extraction
    # ------------------------------------------------------------------

    async def _browser_extract(self, url: str) -> str | None:
        """Attempt to extract page content via browser navigation.

        Returns the page content string if successful, or None on any error.
        Never raises — all exceptions are caught and logged as warnings.
        """
        try:
            result = await asyncio.wait_for(
                self._browser.navigate(url),
                timeout=15.0,
            )
            return result.content if result else None
        except Exception:
            logger.warning(
                "Browser extraction failed for %s",
                url,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Private: failed record builder
    # ------------------------------------------------------------------

    def _build_failed_record(
        self,
        source: SelectedSource,
        elapsed_ms: int,
    ) -> EvidenceRecord:
        """Build a minimal EvidenceRecord that signals acquisition failure.

        Used when an unhandled exception occurs during ``_fetch_and_assess``.
        The record is marked as LOW confidence with extraction_failure hard fail,
        which will cause the synthesis gate to flag or exclude it.
        """
        return EvidenceRecord(
            url=source.url,
            domain=source.domain,
            title=source.title,
            source_type=source.source_type,
            authority_score=source.authority_score,
            source_importance=source.source_importance,
            excerpt="",
            content_length=0,
            content_ref=None,
            access_method=AccessMethod.scrapling_http,
            fetch_tier_reached=1,
            extraction_duration_ms=elapsed_ms,
            timestamp=datetime.now(UTC),
            confidence_bucket=ConfidenceBucket.low,
            hard_fail_reasons=["extraction_failure"],
            soft_fail_reasons=[],
            soft_point_total=0,
            browser_promoted=False,
            browser_changed_outcome=False,
            original_snippet=source.original_snippet,
            original_rank=source.original_rank,
            query=source.query,
        )
