"""Tests for evidence domain models used in the deterministic research pipeline.

Covers all enums, dataclasses, Pydantic models, Protocol, and the
evidence_to_source_citation mapper function.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceAssessment,
    ConfidenceBucket,
    EvidenceRecord,
    HardFailReason,
    PromotionDecision,
    QueryContext,
    SelectedSource,
    SoftFailReason,
    SourceType,
    SynthesisGateResult,
    SynthesisGateVerdict,
    ToolCallContext,
    ToolInterceptorResult,
    evidence_to_source_citation,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestSourceType:
    """All SourceType enum values must be present and correct."""

    def test_official_value(self) -> None:
        assert SourceType.official == "official"

    def test_authoritative_neutral_value(self) -> None:
        assert SourceType.authoritative_neutral == "authoritative_neutral"

    def test_independent_value(self) -> None:
        assert SourceType.independent == "independent"

    def test_ugc_low_trust_value(self) -> None:
        assert SourceType.ugc_low_trust == "ugc_low_trust"

    def test_all_members(self) -> None:
        members = {m.value for m in SourceType}
        assert members == {"official", "authoritative_neutral", "independent", "ugc_low_trust"}


class TestConfidenceBucket:
    """All ConfidenceBucket enum values must be present and correct."""

    def test_high_value(self) -> None:
        assert ConfidenceBucket.high == "high"

    def test_medium_value(self) -> None:
        assert ConfidenceBucket.medium == "medium"

    def test_low_value(self) -> None:
        assert ConfidenceBucket.low == "low"

    def test_all_members(self) -> None:
        members = {m.value for m in ConfidenceBucket}
        assert members == {"high", "medium", "low"}


class TestPromotionDecision:
    """All PromotionDecision enum values must be present and correct."""

    def test_no_verify_value(self) -> None:
        assert PromotionDecision.no_verify == "no_verify"

    def test_verify_if_high_importance_value(self) -> None:
        assert PromotionDecision.verify_if_high_importance == "verify_if_high_importance"

    def test_required_value(self) -> None:
        assert PromotionDecision.required == "required"

    def test_all_members(self) -> None:
        members = {m.value for m in PromotionDecision}
        assert members == {"no_verify", "verify_if_high_importance", "required"}


class TestAccessMethod:
    """All AccessMethod enum values must be present and correct."""

    def test_scrapling_http_value(self) -> None:
        assert AccessMethod.scrapling_http == "scrapling_http"

    def test_scrapling_dynamic_value(self) -> None:
        assert AccessMethod.scrapling_dynamic == "scrapling_dynamic"

    def test_scrapling_stealthy_value(self) -> None:
        assert AccessMethod.scrapling_stealthy == "scrapling_stealthy"

    def test_browser_promoted_value(self) -> None:
        assert AccessMethod.browser_promoted == "browser_promoted"

    def test_browser_fallback_value(self) -> None:
        assert AccessMethod.browser_fallback == "browser_fallback"

    def test_all_members(self) -> None:
        members = {m.value for m in AccessMethod}
        assert members == {
            "scrapling_http",
            "scrapling_dynamic",
            "scrapling_stealthy",
            "browser_promoted",
            "browser_fallback",
        }


class TestHardFailReason:
    """All HardFailReason enum values must be present and correct."""

    def test_block_paywall_challenge_value(self) -> None:
        assert HardFailReason.block_paywall_challenge == "block_paywall_challenge"

    def test_js_shell_empty_value(self) -> None:
        assert HardFailReason.js_shell_empty == "js_shell_empty"

    def test_extraction_failure_value(self) -> None:
        assert HardFailReason.extraction_failure == "extraction_failure"

    def test_required_field_missing_value(self) -> None:
        assert HardFailReason.required_field_missing == "required_field_missing"

    def test_severe_content_mismatch_value(self) -> None:
        assert HardFailReason.severe_content_mismatch == "severe_content_mismatch"

    def test_all_members(self) -> None:
        members = {m.value for m in HardFailReason}
        assert members == {
            "block_paywall_challenge",
            "js_shell_empty",
            "extraction_failure",
            "required_field_missing",
            "severe_content_mismatch",
        }


class TestSoftFailReason:
    """All SoftFailReason enum values must be present and correct."""

    def test_thin_content_value(self) -> None:
        assert SoftFailReason.thin_content == "thin_content"

    def test_boilerplate_heavy_value(self) -> None:
        assert SoftFailReason.boilerplate_heavy == "boilerplate_heavy"

    def test_missing_entities_value(self) -> None:
        assert SoftFailReason.missing_entities == "missing_entities"

    def test_no_publish_date_value(self) -> None:
        assert SoftFailReason.no_publish_date == "no_publish_date"

    def test_weak_content_density_value(self) -> None:
        assert SoftFailReason.weak_content_density == "weak_content_density"

    def test_partial_structured_extraction_value(self) -> None:
        assert SoftFailReason.partial_structured_extraction == "partial_structured_extraction"

    def test_all_members(self) -> None:
        members = {m.value for m in SoftFailReason}
        assert members == {
            "thin_content",
            "boilerplate_heavy",
            "missing_entities",
            "no_publish_date",
            "weak_content_density",
            "partial_structured_extraction",
        }


class TestSynthesisGateVerdict:
    """All SynthesisGateVerdict enum values must be present and correct."""

    def test_pass_value(self) -> None:
        assert SynthesisGateVerdict.pass_ == "pass"

    def test_soft_fail_value(self) -> None:
        assert SynthesisGateVerdict.soft_fail == "soft_fail"

    def test_hard_fail_value(self) -> None:
        assert SynthesisGateVerdict.hard_fail == "hard_fail"

    def test_all_members(self) -> None:
        members = {m.value for m in SynthesisGateVerdict}
        assert members == {"pass", "soft_fail", "hard_fail"}


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestToolCallContext:
    """ToolCallContext must be frozen (immutable) and slots-based."""

    def _make(self, **overrides: object) -> ToolCallContext:
        defaults: dict[str, object] = {
            "tool_call_id": "tc-001",
            "function_name": "info_search_web",
            "function_args": {"query": "test"},
            "step_id": "step-42",
            "session_id": "sess-abc",
            "research_mode": "deep",
        }
        defaults.update(overrides)
        return ToolCallContext(**defaults)  # type: ignore[arg-type]

    def test_basic_creation(self) -> None:
        ctx = self._make()
        assert ctx.tool_call_id == "tc-001"
        assert ctx.function_name == "info_search_web"
        assert ctx.function_args == {"query": "test"}
        assert ctx.step_id == "step-42"
        assert ctx.session_id == "sess-abc"
        assert ctx.research_mode == "deep"

    def test_frozen_raises_on_mutation(self) -> None:
        ctx = self._make()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            ctx.tool_call_id = "new-id"  # type: ignore[misc]

    def test_optional_step_id_none(self) -> None:
        ctx = self._make(step_id=None)
        assert ctx.step_id is None

    def test_optional_research_mode_none(self) -> None:
        ctx = self._make(research_mode=None)
        assert ctx.research_mode is None


class TestToolInterceptorResult:
    """ToolInterceptorResult defaults and field assignment."""

    def test_all_defaults(self) -> None:
        result = ToolInterceptorResult()
        assert result.override_memory_content is None
        assert result.extra_messages is None
        assert result.suppress_memory_content is False

    def test_with_override_memory_content(self) -> None:
        result = ToolInterceptorResult(override_memory_content="enriched content")
        assert result.override_memory_content == "enriched content"

    def test_with_extra_messages(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = ToolInterceptorResult(extra_messages=msgs)
        assert result.extra_messages == msgs

    def test_with_suppress_memory_content_true(self) -> None:
        result = ToolInterceptorResult(suppress_memory_content=True)
        assert result.suppress_memory_content is True

    def test_mutable_not_frozen(self) -> None:
        """ToolInterceptorResult should be mutable (not frozen)."""
        result = ToolInterceptorResult()
        result.suppress_memory_content = True
        assert result.suppress_memory_content is True


class TestQueryContext:
    """QueryContext must be frozen and have correct defaults."""

    def test_all_defaults(self) -> None:
        ctx = QueryContext()
        assert ctx.task_intent is None
        assert ctx.required_entities is None
        assert ctx.time_sensitive is False
        assert ctx.comparative is False

    def test_custom_values(self) -> None:
        ctx = QueryContext(
            task_intent="compare products",
            required_entities=["Apple", "Samsung"],
            time_sensitive=True,
            comparative=True,
        )
        assert ctx.task_intent == "compare products"
        assert ctx.required_entities == ["Apple", "Samsung"]
        assert ctx.time_sensitive is True
        assert ctx.comparative is True

    def test_frozen_raises_on_mutation(self) -> None:
        ctx = QueryContext()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            ctx.time_sensitive = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestSelectedSource:
    """SelectedSource creation with all required and optional fields."""

    def _make(self, **overrides: object) -> SelectedSource:
        defaults: dict[str, object] = {
            "url": "https://example.com/article",
            "domain": "example.com",
            "title": "Example Article",
            "original_snippet": "This is the original snippet.",
            "original_rank": 1,
            "query": "example query",
            "relevance_score": 0.9,
            "authority_score": 0.8,
            "freshness_score": 0.7,
            "rank_score": 0.85,
            "composite_score": 0.82,
            "source_type": SourceType.official,
            "source_importance": "high",
            "selection_reason": "Top-ranked official source.",
        }
        defaults.update(overrides)
        return SelectedSource(**defaults)  # type: ignore[arg-type]

    def test_basic_creation(self) -> None:
        src = self._make()
        assert src.url == "https://example.com/article"
        assert src.domain == "example.com"
        assert src.title == "Example Article"
        assert src.original_rank == 1
        assert src.relevance_score == 0.9
        assert src.composite_score == 0.82
        assert src.source_type == SourceType.official
        assert src.source_importance == "high"

    def test_default_domain_diversity_applied(self) -> None:
        src = self._make()
        assert src.domain_diversity_applied is False

    def test_domain_diversity_applied_true(self) -> None:
        src = self._make(domain_diversity_applied=True)
        assert src.domain_diversity_applied is True

    def test_source_type_ugc_low_trust(self) -> None:
        src = self._make(source_type=SourceType.ugc_low_trust, source_importance="low")
        assert src.source_type == SourceType.ugc_low_trust
        assert src.source_importance == "low"

    def test_source_importance_medium(self) -> None:
        src = self._make(source_importance="medium")
        assert src.source_importance == "medium"


class TestConfidenceAssessment:
    """ConfidenceAssessment for high and low confidence variants."""

    def test_high_confidence_no_fails(self) -> None:
        assessment = ConfidenceAssessment(
            hard_fails=[],
            soft_fails=[],
            confidence_bucket=ConfidenceBucket.high,
            promotion_decision=PromotionDecision.no_verify,
        )
        assert assessment.hard_fails == []
        assert assessment.soft_fails == []
        assert assessment.soft_point_total == 0
        assert assessment.confidence_bucket == ConfidenceBucket.high
        assert assessment.promotion_decision == PromotionDecision.no_verify
        assert assessment.shadow_score == 1.0
        assert assessment.content_length == 0
        assert assessment.boilerplate_ratio == 0.0
        assert assessment.entity_match_ratio == 0.0

    def test_low_confidence_with_fails(self) -> None:
        assessment = ConfidenceAssessment(
            hard_fails=[HardFailReason.js_shell_empty],
            soft_fails=[SoftFailReason.thin_content, SoftFailReason.no_publish_date],
            soft_point_total=4,
            confidence_bucket=ConfidenceBucket.low,
            promotion_decision=PromotionDecision.required,
            shadow_score=0.4,
            content_length=150,
            boilerplate_ratio=0.75,
            entity_match_ratio=0.1,
        )
        assert HardFailReason.js_shell_empty in assessment.hard_fails
        assert SoftFailReason.thin_content in assessment.soft_fails
        assert assessment.soft_point_total == 4
        assert assessment.confidence_bucket == ConfidenceBucket.low
        assert assessment.promotion_decision == PromotionDecision.required
        assert assessment.shadow_score == 0.4
        assert assessment.boilerplate_ratio == 0.75

    def test_medium_confidence_verify_if_high_importance(self) -> None:
        assessment = ConfidenceAssessment(
            hard_fails=[],
            soft_fails=[SoftFailReason.missing_entities],
            soft_point_total=2,
            confidence_bucket=ConfidenceBucket.medium,
            promotion_decision=PromotionDecision.verify_if_high_importance,
        )
        assert assessment.confidence_bucket == ConfidenceBucket.medium
        assert assessment.promotion_decision == PromotionDecision.verify_if_high_importance


class TestEvidenceRecord:
    """EvidenceRecord creation, immutability (frozen), and field variants."""

    def _make(self, **overrides: object) -> EvidenceRecord:
        defaults: dict[str, object] = {
            "url": "https://example.com/article",
            "domain": "example.com",
            "title": "Example Article",
            "source_type": SourceType.official,
            "authority_score": 0.9,
            "source_importance": "high",
            "excerpt": "This is a factual excerpt about the topic.",
            "content_length": 2500,
            "access_method": AccessMethod.scrapling_http,
            "fetch_tier_reached": 1,
            "extraction_duration_ms": 350,
            "timestamp": datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC),
            "confidence_bucket": ConfidenceBucket.high,
            "hard_fail_reasons": [],
            "soft_fail_reasons": [],
        }
        defaults.update(overrides)
        return EvidenceRecord(**defaults)  # type: ignore[arg-type]

    def test_basic_creation(self) -> None:
        record = self._make()
        assert record.url == "https://example.com/article"
        assert record.domain == "example.com"
        assert record.title == "Example Article"
        assert record.source_type == SourceType.official
        assert record.authority_score == 0.9
        assert record.source_importance == "high"
        assert record.content_length == 2500
        assert record.access_method == AccessMethod.scrapling_http
        assert record.fetch_tier_reached == 1
        assert record.extraction_duration_ms == 350
        assert record.confidence_bucket == ConfidenceBucket.high

    def test_default_optional_fields(self) -> None:
        record = self._make()
        assert record.content_ref is None
        assert record.soft_point_total == 0
        assert record.browser_promoted is False
        assert record.browser_changed_outcome is False
        assert record.original_snippet is None
        assert record.original_rank == 0
        assert record.query == ""

    def test_frozen_raises_on_mutation(self) -> None:
        record = self._make()
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            record.url = "https://other.com"  # type: ignore[misc]

    def test_browser_promoted_variant(self) -> None:
        record = self._make(
            access_method=AccessMethod.browser_promoted,
            browser_promoted=True,
            browser_changed_outcome=True,
            fetch_tier_reached=3,
        )
        assert record.access_method == AccessMethod.browser_promoted
        assert record.browser_promoted is True
        assert record.browser_changed_outcome is True
        assert record.fetch_tier_reached == 3

    def test_failed_variant_with_hard_fail_reasons(self) -> None:
        record = self._make(
            confidence_bucket=ConfidenceBucket.low,
            hard_fail_reasons=["js_shell_empty", "extraction_failure"],
            soft_fail_reasons=["thin_content"],
            soft_point_total=2,
        )
        assert record.confidence_bucket == ConfidenceBucket.low
        assert "js_shell_empty" in record.hard_fail_reasons
        assert "thin_content" in record.soft_fail_reasons
        assert record.soft_point_total == 2

    def test_content_ref_and_original_fields(self) -> None:
        record = self._make(
            content_ref="ref://store/abc123",
            original_snippet="Original search snippet text.",
            original_rank=3,
            query="best python frameworks 2026",
        )
        assert record.content_ref == "ref://store/abc123"
        assert record.original_snippet == "Original search snippet text."
        assert record.original_rank == 3
        assert record.query == "best python frameworks 2026"


class TestSynthesisGateResult:
    """SynthesisGateResult pass and fail variants."""

    def test_pass_verdict_defaults(self) -> None:
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=["Sufficient high-confidence evidence"],
            thresholds_applied={"min_high_confidence": 2, "require_official": False},
        )
        assert result.verdict == SynthesisGateVerdict.pass_
        assert len(result.reasons) == 1
        assert result.total_fetched == 0
        assert result.high_confidence_count == 0
        assert result.official_source_found is False
        assert result.independent_source_found is False

    def test_pass_verdict_with_counts(self) -> None:
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=["Sufficient evidence"],
            total_fetched=8,
            high_confidence_count=5,
            official_source_found=True,
            independent_source_found=True,
            thresholds_applied={"min_high_confidence": 3, "require_official": True},
        )
        assert result.total_fetched == 8
        assert result.high_confidence_count == 5
        assert result.official_source_found is True
        assert result.independent_source_found is True

    def test_soft_fail_verdict(self) -> None:
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.soft_fail,
            reasons=["Only 1 high-confidence source, minimum is 2"],
            total_fetched=5,
            high_confidence_count=1,
            thresholds_applied={"min_high_confidence": 2},
        )
        assert result.verdict == SynthesisGateVerdict.soft_fail
        assert "Only 1 high-confidence source" in result.reasons[0]

    def test_hard_fail_verdict(self) -> None:
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.hard_fail,
            reasons=["No sources passed extraction", "All URLs returned paywall"],
            total_fetched=3,
            high_confidence_count=0,
            thresholds_applied={"min_total_fetched": 1},
        )
        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert len(result.reasons) == 2
        assert result.high_confidence_count == 0

    def test_thresholds_dict_int_and_bool(self) -> None:
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
            thresholds_applied={"min_total": 3, "require_official": True},
        )
        assert result.thresholds_applied["min_total"] == 3
        assert result.thresholds_applied["require_official"] is True


# ---------------------------------------------------------------------------
# Mapper function tests
# ---------------------------------------------------------------------------


class TestEvidenceToSourceCitation:
    """evidence_to_source_citation maps access methods to correct source_type."""

    def _make_record(self, access_method: AccessMethod) -> EvidenceRecord:
        return EvidenceRecord(
            url="https://example.com/page",
            domain="example.com",
            title="Test Page",
            source_type=SourceType.independent,
            authority_score=0.7,
            source_importance="medium",
            excerpt="Some excerpt text.",
            content_length=1200,
            access_method=access_method,
            fetch_tier_reached=1,
            extraction_duration_ms=200,
            timestamp=datetime(2026, 3, 10, tzinfo=UTC),
            confidence_bucket=ConfidenceBucket.medium,
            hard_fail_reasons=[],
            soft_fail_reasons=[],
        )

    def test_scrapling_http_maps_to_search(self) -> None:
        record = self._make_record(AccessMethod.scrapling_http)
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "search"
        assert citation.url == "https://example.com/page"
        assert citation.title == "Test Page"

    def test_scrapling_dynamic_maps_to_search(self) -> None:
        record = self._make_record(AccessMethod.scrapling_dynamic)
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "search"

    def test_scrapling_stealthy_maps_to_search(self) -> None:
        record = self._make_record(AccessMethod.scrapling_stealthy)
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "search"

    def test_browser_promoted_maps_to_browser(self) -> None:
        record = self._make_record(AccessMethod.browser_promoted)
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "browser"

    def test_browser_fallback_maps_to_browser(self) -> None:
        record = self._make_record(AccessMethod.browser_fallback)
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "browser"

    def test_citation_fields_populated(self) -> None:
        record = self._make_record(AccessMethod.scrapling_http)
        citation = evidence_to_source_citation(record)
        assert citation.url == record.url
        assert citation.title == record.title
        assert citation.snippet == record.excerpt
        assert isinstance(citation.access_time, datetime)

    def test_citation_access_time_is_record_timestamp(self) -> None:
        record = self._make_record(AccessMethod.scrapling_http)
        citation = evidence_to_source_citation(record)
        assert citation.access_time == record.timestamp
