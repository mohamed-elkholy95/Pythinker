"""Domain models for the deterministic research pipeline.

Defines all types used across source selection, evidence acquisition,
confidence assessment, synthesis gating, and tool interception.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceType(StrEnum):
    """Classification of a source's authority and trust level."""

    official = "official"
    authoritative_neutral = "authoritative_neutral"
    independent = "independent"
    ugc_low_trust = "ugc_low_trust"


class ConfidenceBucket(StrEnum):
    """Overall confidence level assigned to a fetched evidence record."""

    high = "high"
    medium = "medium"
    low = "low"


class PromotionDecision(StrEnum):
    """Whether browser promotion is needed for a source."""

    no_verify = "no_verify"
    verify_if_high_importance = "verify_if_high_importance"
    required = "required"


class AccessMethod(StrEnum):
    """How the content was accessed during evidence acquisition."""

    scrapling_http = "scrapling_http"
    scrapling_dynamic = "scrapling_dynamic"
    scrapling_stealthy = "scrapling_stealthy"
    browser_promoted = "browser_promoted"
    browser_fallback = "browser_fallback"


class HardFailReason(StrEnum):
    """Reasons that cause a source to be classified as a hard failure.

    Hard fails disqualify the record entirely from synthesis.
    """

    block_paywall_challenge = "block_paywall_challenge"
    js_shell_empty = "js_shell_empty"
    extraction_failure = "extraction_failure"
    required_field_missing = "required_field_missing"
    severe_content_mismatch = "severe_content_mismatch"


class SoftFailReason(StrEnum):
    """Reasons that reduce confidence without fully disqualifying a source.

    Soft fails accumulate points; high totals downgrade the confidence bucket.
    """

    thin_content = "thin_content"
    boilerplate_heavy = "boilerplate_heavy"
    missing_entities = "missing_entities"
    no_publish_date = "no_publish_date"
    weak_content_density = "weak_content_density"
    partial_structured_extraction = "partial_structured_extraction"


class SynthesisGateVerdict(StrEnum):
    """Verdict issued by the synthesis gate after evaluating evidence quality."""

    pass_ = "pass"
    soft_fail = "soft_fail"
    hard_fail = "hard_fail"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Immutable context snapshot for a single tool call interception.

    Attributes:
        tool_call_id: Unique identifier assigned by the LLM for this call.
        function_name: Name of the tool function being called.
        function_args: Parsed argument dict as supplied by the LLM.
        step_id: Identifier of the plan step that triggered this call, if any.
        session_id: Active agent session identifier.
        research_mode: Current research mode (e.g. "deep", "fast"), if any.
    """

    tool_call_id: str
    function_name: str
    function_args: dict[str, Any]
    step_id: str | None
    session_id: str
    research_mode: str | None


@dataclasses.dataclass(slots=True)
class ToolInterceptorResult:
    """Mutable result returned by a ToolInterceptor after processing a tool call.

    Attributes:
        override_memory_content: If set, replaces the serialized memory content
            that will be stored for this tool result.
        extra_messages: Additional messages to inject into the conversation
            immediately after this tool result.
        suppress_memory_content: When True the tool result is not stored in
            the agent's conversational memory.
    """

    override_memory_content: str | None = None
    extra_messages: list[dict[str, Any]] | None = None
    suppress_memory_content: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class QueryContext:
    """Immutable context describing the research query intent.

    Attributes:
        task_intent: High-level intent extracted from the user task, if any.
        required_entities: Entity names that must appear in relevant evidence.
        time_sensitive: Whether results must be recent (e.g. news, prices).
        comparative: Whether the task requires comparing multiple subjects.
    """

    task_intent: str | None = None
    required_entities: list[str] | None = None
    time_sensitive: bool = False
    comparative: bool = False


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SelectedSource(BaseModel):
    """A source chosen by the source selector for evidence acquisition.

    Captures all scoring dimensions used during selection so that downstream
    components can explain and audit source ranking decisions.
    """

    url: str
    domain: str
    title: str
    original_snippet: str
    original_rank: int
    query: str
    relevance_score: float
    authority_score: float
    freshness_score: float
    rank_score: float
    composite_score: float
    source_type: SourceType
    source_importance: Literal["high", "medium", "low"]
    selection_reason: str
    domain_diversity_applied: bool = False


class ConfidenceAssessment(BaseModel):
    """Assessment of the confidence level for a fetched evidence record.

    Aggregates hard and soft failure signals, computes a final
    ConfidenceBucket and a PromotionDecision for browser escalation.
    """

    hard_fails: list[HardFailReason]
    soft_fails: list[SoftFailReason]
    soft_point_total: int = 0
    confidence_bucket: ConfidenceBucket
    promotion_decision: PromotionDecision
    shadow_score: float = 1.0
    content_length: int = 0
    boilerplate_ratio: float = 0.0
    entity_match_ratio: float = 0.0


class EvidenceRecord(BaseModel):
    """Immutable record of evidence fetched from a single source.

    Captured at acquisition time; used by the synthesis gate and the
    report builder.  Frozen to guarantee integrity throughout the pipeline.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    domain: str
    title: str
    source_type: SourceType
    authority_score: float
    source_importance: Literal["high", "medium", "low"]
    excerpt: str
    content_length: int
    content_ref: str | None = None
    access_method: AccessMethod
    fetch_tier_reached: int
    extraction_duration_ms: int
    timestamp: datetime
    confidence_bucket: ConfidenceBucket
    hard_fail_reasons: list[str]
    soft_fail_reasons: list[str]
    soft_point_total: int = 0
    browser_promoted: bool = False
    browser_changed_outcome: bool = False
    original_snippet: str | None = None
    original_rank: int = 0
    query: str = ""


class SynthesisGateResult(BaseModel):
    """Result of the synthesis gate evaluation.

    The gate inspects the full set of EvidenceRecords and decides whether
    the pipeline may proceed to synthesis, should warn, or must abort.
    """

    verdict: SynthesisGateVerdict
    reasons: list[str]
    total_fetched: int = 0
    high_confidence_count: int = 0
    official_source_found: bool = False
    independent_source_found: bool = False
    thresholds_applied: dict[str, int | bool]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ToolInterceptor:
    """Protocol for objects that intercept tool results in the agent loop.

    Implementations can enrich, suppress, or augment tool results before
    they are stored in the agent's conversational memory.
    """

    async def on_tool_result(
        self,
        tool_result: Any,
        serialized_content: str,
        context: ToolCallContext,
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> ToolInterceptorResult | None:
        """Called after a tool executes and before its result is stored.

        Args:
            tool_result: The raw tool result object.
            serialized_content: The string that would be stored in memory.
            context: Immutable context for this tool call.
            emit_event: Callable for emitting pipeline events to the frontend.

        Returns:
            A ToolInterceptorResult to modify memory handling, or None to
            leave the default behaviour unchanged.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


_BROWSER_ACCESS_METHODS: frozenset[AccessMethod] = frozenset(
    {AccessMethod.browser_promoted, AccessMethod.browser_fallback}
)


def evidence_to_source_citation(record: EvidenceRecord) -> Any:
    """Map an EvidenceRecord to a SourceCitation for report bibliography.

    Args:
        record: The immutable evidence record to convert.

    Returns:
        A SourceCitation with source_type="browser" for browser access methods
        and source_type="search" for all scrapling-based access methods.
    """
    from app.domain.models.source_citation import SourceCitation

    source_type: Literal["search", "browser", "file"] = (
        "browser" if record.access_method in _BROWSER_ACCESS_METHODS else "search"
    )
    return SourceCitation(
        url=record.url,
        title=record.title,
        snippet=record.excerpt,
        access_time=record.timestamp,
        source_type=source_type,
    )
