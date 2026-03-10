"""ResearchExecutionPolicy — deterministic research pipeline orchestrator.

Implements the ToolInterceptor protocol. Intercepts info_search_web and
wide_research tool results, runs the full pipeline:

    SourceSelector → EvidenceAcquisitionService → SynthesisGuard

And injects the acquired evidence as a system message into the LLM
conversation. Evidence records are also registered with SourceTracker for
bibliography building.

Usage::

    policy = ResearchExecutionPolicy(
        source_selector=selector,
        evidence_service=evidence_svc,
        synthesis_guard=guard,
        config=settings,
        source_tracker=tracker,
    )

    # During agent tool loop:
    result = await policy.on_tool_result(tool_result, serialized, ctx, emit_event)
    if result:
        # result.extra_messages contains the evidence system prompt

    # Before synthesis:
    gate_result = policy.can_synthesize()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.models.evidence import (
    ConfidenceBucket,
    EvidenceRecord,
    QueryContext,
    SelectedSource,
    SynthesisGateResult,
    ToolCallContext,
    ToolInterceptorResult,
    evidence_to_source_citation,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.domain.services.agents.evidence_acquisition import EvidenceAcquisitionService
    from app.domain.services.agents.source_selector import SourceSelector
    from app.domain.services.agents.source_tracker import SourceTracker
    from app.domain.services.agents.synthesis_guard import SynthesisGuard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INTERCEPTED_TOOLS: frozenset[str] = frozenset({"info_search_web", "wide_research"})

_CONFIDENCE_LABELS: dict[ConfidenceBucket, str] = {
    ConfidenceBucket.high: "OK",
    ConfidenceBucket.medium: "PARTIAL",
    ConfidenceBucket.low: "WEAK",
}


# ---------------------------------------------------------------------------
# ResearchExecutionPolicy
# ---------------------------------------------------------------------------


class ResearchExecutionPolicy:
    """Deterministic research pipeline. Implements ToolInterceptor protocol.

    Coordinates the SourceSelector → EvidenceAcquisitionService →
    SynthesisGuard pipeline, injects evidence into the LLM conversation,
    and feeds citations into SourceTracker.

    Args:
        source_selector: Rule-based source scorer and selector.
        evidence_service: Concurrent web content fetcher with confidence rating.
        synthesis_guard: Pre-synthesis quality gate.
        config: Settings object exposing research pipeline configuration fields.
        source_tracker: Citation registry for bibliography generation.
    """

    INTERCEPTED_TOOLS: frozenset[str] = _INTERCEPTED_TOOLS

    def __init__(
        self,
        source_selector: SourceSelector,
        evidence_service: EvidenceAcquisitionService,
        synthesis_guard: SynthesisGuard,
        config: Any,
        source_tracker: SourceTracker,
    ) -> None:
        self._selector = source_selector
        self._evidence_service = evidence_service
        self._guard = synthesis_guard
        self._config = config
        self._source_tracker = source_tracker

        # Session-scoped state
        self._evidence_records: list[EvidenceRecord] = []
        self._total_search_results: int = 0
        self._query_context: QueryContext | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_query_context(self, ctx: QueryContext) -> None:
        """Set the query context for the current research session.

        Args:
            ctx: Immutable QueryContext capturing task intent and constraints.
        """
        self._query_context = ctx

    @property
    def evidence_records(self) -> list[EvidenceRecord]:
        """Return a copy of all accumulated evidence records."""
        return self._evidence_records.copy()

    def can_synthesize(self) -> SynthesisGateResult:
        """Evaluate whether accumulated evidence is sufficient for synthesis.

        Delegates to SynthesisGuard with all evidence collected so far.

        Returns:
            A SynthesisGateResult with the verdict and diagnostic reasons.
        """
        return self._guard.evaluate(
            self._evidence_records,
            self._total_search_results,
            self._query_context,
        )

    async def on_tool_result(
        self,
        tool_result: Any,
        serialized_content: str,
        context: ToolCallContext,
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> ToolInterceptorResult | None:
        """Intercept search results and run the deterministic evidence pipeline.

        Returns None for non-search tools, failed results, or empty result sets.
        Returns a ToolInterceptorResult with the evidence summary injected as a
        system message when the pipeline succeeds.

        Args:
            tool_result: The raw ToolResult from the tool execution.
            serialized_content: The string that would be stored in memory.
            context: Immutable context for this tool call.
            emit_event: Async callable for emitting ProgressEvents to the frontend.

        Returns:
            ToolInterceptorResult or None.
        """
        # 1. Only handle search tools
        if context.function_name not in _INTERCEPTED_TOOLS:
            return None

        # 2. Skip failed tool results or absent data
        if not tool_result.success or tool_result.data is None:
            return None

        # 3. Extract results list from SearchResults
        search_data = tool_result.data
        results = getattr(search_data, "results", None) or []
        if not results:
            return None

        # 4. Track total search result count (one increment per tool call)
        self._total_search_results += 1

        query = self._extract_query(context)

        # 5. Select top sources
        await emit_event(
            ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message=f"Selecting top sources from {len(results)} results",
            )
        )
        selected: list[SelectedSource] = self._selector.select(results, query, self._query_context)
        if not selected:
            return None

        # 6. Emit acquisition progress
        domain_list = ", ".join(s.domain for s in selected[:5])
        await emit_event(
            ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message=f"Acquiring evidence from {len(selected)} sources: {domain_list}",
            )
        )

        # 7. Acquire evidence
        acquired: list[EvidenceRecord] = await self._evidence_service.acquire(selected, self._query_context, emit_event)

        # 8. Accumulate records
        self._evidence_records.extend(acquired)

        # 9. Feed each record to SourceTracker
        for record in acquired:
            citation = evidence_to_source_citation(record)
            self._source_tracker.add_source(citation)

        # 10. Format evidence summary
        successful = [r for r in acquired if r.content_length > 0]
        evidence_summary = self._format_evidence_summary(acquired)

        # 11. Emit completion progress
        await emit_event(
            ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message=f"Evidence acquired: {len(successful)}/{len(selected)} sources successful",
            )
        )

        # 12. Log telemetry if enabled
        if getattr(self._config, "research_telemetry_enabled", False):
            self._log_telemetry(selected, acquired, emit_event)

        return ToolInterceptorResult(extra_messages=[{"role": "system", "content": evidence_summary}])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_query(self, context: ToolCallContext) -> str:
        """Extract the search query string from tool call arguments.

        Handles both single-query (``query`` key) and multi-query
        (``queries`` list) argument shapes.

        Args:
            context: The tool call context containing function_args.

        Returns:
            The query string, or an empty string if unavailable.
        """
        args = context.function_args
        if "query" in args:
            return str(args["query"])
        queries = args.get("queries")
        if isinstance(queries, list) and queries:
            return str(queries[0])
        return ""

    def _format_evidence_summary(self, records: list[EvidenceRecord]) -> str:
        """Format acquired evidence records as a Markdown system prompt.

        Args:
            records: EvidenceRecords produced by the acquisition stage.

        Returns:
            Markdown string ready to inject as a system message.
        """
        lines: list[str] = [
            "## Research Evidence Acquired",
            "",
            f"Sources fetched: {len(records)}",
            "",
        ]

        for i, record in enumerate(records, start=1):
            confidence_label = _CONFIDENCE_LABELS.get(record.confidence_bucket, record.confidence_bucket.value.upper())
            lines.append(f"### Source {i}: [{record.title}]({record.url})")
            lines.append(
                f"Type: {record.source_type.value} | "
                f"Confidence: {confidence_label} | "
                f"Content: {record.content_length} chars"
            )
            lines.append("")
            if record.excerpt:
                lines.append(record.excerpt)
            lines.append("")
            lines.append("---")

        lines.append("Use the evidence above for your analysis. Do not rely on search snippets alone.")

        return "\n".join(lines)

    def _log_telemetry(
        self,
        selected: list[SelectedSource],
        records: list[EvidenceRecord],
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> None:
        """Emit structured telemetry for the evidence pipeline run.

        Args:
            selected: Sources chosen by SourceSelector.
            records: EvidenceRecords produced by acquisition.
            emit_event: Async callable (unused here; telemetry goes to logger).
        """
        for record in records:
            logger.info(
                "research_evidence_telemetry",
                extra={
                    "url": record.url,
                    "domain": record.domain,
                    "source_type": record.source_type.value,
                    "confidence_bucket": record.confidence_bucket.value,
                    "content_length": record.content_length,
                    "access_method": record.access_method.value,
                    "fetch_tier_reached": record.fetch_tier_reached,
                    "extraction_duration_ms": record.extraction_duration_ms,
                    "browser_promoted": record.browser_promoted,
                    "hard_fail_reasons": record.hard_fail_reasons,
                    "soft_fail_reasons": record.soft_fail_reasons,
                },
            )
