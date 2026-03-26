"""Tests for app.domain.models.citation_discipline — citation discipline models.

Covers: CitationRequirement, ClaimType, CitedClaim validators, CitationValidationResult
(overall_score, get_report, get_claims_by_type, get_uncited_claims), CitationConfig
(requires_citation logic for strict/moderate/relaxed).
"""

from __future__ import annotations

import pytest

from app.domain.models.citation_discipline import (
    CitationConfig,
    CitationRequirement,
    CitationValidationResult,
    CitedClaim,
    ClaimType,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TestEnums:
    def test_citation_requirement_values(self):
        assert set(CitationRequirement) == {
            CitationRequirement.STRICT,
            CitationRequirement.MODERATE,
            CitationRequirement.RELAXED,
        }

    def test_claim_type_values(self):
        expected = {"factual", "statistical", "quotation", "inference", "opinion", "common"}
        actual = {c.value for c in ClaimType}
        assert actual == expected


# ---------------------------------------------------------------------------
# CitedClaim
# ---------------------------------------------------------------------------
class TestCitedClaim:
    def test_factual_uncited_gets_caveat(self):
        claim = CitedClaim(
            claim_text="Python is the most popular language",
            claim_type=ClaimType.FACTUAL,
        )
        assert claim.requires_caveat is True
        assert "Unverified factual claim" in claim.caveat_text
        assert claim.confidence <= 0.3

    def test_statistical_uncited_gets_caveat(self):
        claim = CitedClaim(
            claim_text="90% of developers use Git",
            claim_type=ClaimType.STATISTICAL,
        )
        assert claim.requires_caveat is True
        assert "Unverified statistical claim" in claim.caveat_text

    def test_quotation_uncited_gets_caveat(self):
        claim = CitedClaim(
            claim_text='Einstein said "Imagination is more important"',
            claim_type=ClaimType.QUOTATION,
        )
        assert claim.requires_caveat is True

    def test_factual_with_citation_no_caveat(self):
        claim = CitedClaim(
            claim_text="Python was created in 1991",
            claim_type=ClaimType.FACTUAL,
            citation_ids=["src-1"],
        )
        assert claim.requires_caveat is False

    def test_inference_gets_inference_caveat(self):
        claim = CitedClaim(
            claim_text="This suggests a trend",
            claim_type=ClaimType.INFERENCE,
        )
        assert claim.caveat_text == "(Inferred from available data)"

    def test_inference_preserves_custom_caveat(self):
        claim = CitedClaim(
            claim_text="This suggests a trend",
            claim_type=ClaimType.INFERENCE,
            caveat_text="Custom caveat",
        )
        assert claim.caveat_text == "Custom caveat"

    def test_opinion_no_caveat(self):
        claim = CitedClaim(
            claim_text="React is better than Angular",
            claim_type=ClaimType.OPINION,
        )
        assert claim.requires_caveat is False

    def test_common_knowledge_no_caveat(self):
        claim = CitedClaim(
            claim_text="Water boils at 100C at sea level",
            claim_type=ClaimType.COMMON_KNOWLEDGE,
        )
        assert claim.requires_caveat is False

    def test_get_display_text_with_caveat(self):
        claim = CitedClaim(
            claim_text="X is true",
            claim_type=ClaimType.FACTUAL,
        )
        display = claim.get_display_text()
        assert "X is true" in display
        assert "Unverified" in display

    def test_get_display_text_without_caveat(self):
        claim = CitedClaim(
            claim_text="X is true",
            claim_type=ClaimType.FACTUAL,
            citation_ids=["ref-1"],
        )
        assert claim.get_display_text() == "X is true"

    def test_confidence_capped_for_uncited_factual(self):
        claim = CitedClaim(
            claim_text="X is true",
            claim_type=ClaimType.FACTUAL,
            confidence=0.9,  # Should be capped to 0.3
        )
        assert claim.confidence <= 0.3

    def test_confidence_preserved_for_cited(self):
        claim = CitedClaim(
            claim_text="X is true",
            claim_type=ClaimType.FACTUAL,
            citation_ids=["ref-1"],
            confidence=0.9,
        )
        assert claim.confidence == 0.9

    def test_supporting_excerpts(self):
        claim = CitedClaim(
            claim_text="X is true",
            claim_type=ClaimType.FACTUAL,
            citation_ids=["ref-1"],
            supporting_excerpts=["From the paper: X..."],
        )
        assert len(claim.supporting_excerpts) == 1


# ---------------------------------------------------------------------------
# CitationValidationResult
# ---------------------------------------------------------------------------
class TestCitationValidationResult:
    def test_empty_result(self):
        result = CitationValidationResult()
        assert result.is_valid is False
        assert result.total_claims == 0
        assert result.overall_score == 0.0

    def test_overall_score_calculation(self):
        result = CitationValidationResult(
            citation_coverage=1.0,
            citation_quality=1.0,
        )
        assert result.overall_score == pytest.approx(1.0)

    def test_overall_score_weighted(self):
        result = CitationValidationResult(
            citation_coverage=0.5,
            citation_quality=0.5,
        )
        # 0.5 * 0.6 + 0.5 * 0.4 = 0.5
        assert result.overall_score == pytest.approx(0.5)

    def test_overall_score_coverage_weighted_more(self):
        result = CitationValidationResult(
            citation_coverage=1.0,
            citation_quality=0.0,
        )
        # 1.0 * 0.6 + 0.0 * 0.4 = 0.6
        assert result.overall_score == pytest.approx(0.6)

    def test_get_report_contains_key_info(self):
        result = CitationValidationResult(
            total_claims=10,
            cited_claims=8,
            uncited_factual_claims=2,
            citation_coverage=0.8,
            citation_quality=0.7,
            missing_citations=["Claim about X"],
            weak_citations=["Source Y"],
        )
        report = result.get_report()
        assert "Total Claims: 10" in report
        assert "Cited Claims: 8" in report
        assert "Claim about X" in report
        assert "Source Y" in report

    def test_get_report_no_missing(self):
        result = CitationValidationResult(total_claims=5, cited_claims=5)
        report = result.get_report()
        assert "Missing Citations:" not in report

    def test_get_claims_by_type(self):
        claims = [
            CitedClaim(claim_text="fact1", claim_type=ClaimType.FACTUAL, citation_ids=["ref"]),
            CitedClaim(claim_text="opinion1", claim_type=ClaimType.OPINION),
            CitedClaim(claim_text="fact2", claim_type=ClaimType.FACTUAL, citation_ids=["ref2"]),
        ]
        result = CitationValidationResult(claims=claims)
        factual = result.get_claims_by_type(ClaimType.FACTUAL)
        assert len(factual) == 2
        opinions = result.get_claims_by_type(ClaimType.OPINION)
        assert len(opinions) == 1

    def test_get_uncited_claims(self):
        claims = [
            CitedClaim(claim_text="cited", claim_type=ClaimType.OPINION, citation_ids=["ref"]),
            CitedClaim(claim_text="uncited", claim_type=ClaimType.OPINION),
        ]
        result = CitationValidationResult(claims=claims)
        uncited = result.get_uncited_claims()
        assert len(uncited) == 1
        assert uncited[0].claim_text == "uncited"


# ---------------------------------------------------------------------------
# CitationConfig
# ---------------------------------------------------------------------------
class TestCitationConfig:
    def test_defaults(self):
        config = CitationConfig()
        assert config.requirement_level == CitationRequirement.MODERATE
        assert config.min_coverage_score == 0.7
        assert config.auto_add_caveats is True
        assert config.fail_on_uncited_factual is False

    def test_strict_requires_all_except_common(self):
        config = CitationConfig(requirement_level=CitationRequirement.STRICT)
        assert config.requires_citation(ClaimType.FACTUAL) is True
        assert config.requires_citation(ClaimType.STATISTICAL) is True
        assert config.requires_citation(ClaimType.QUOTATION) is True
        assert config.requires_citation(ClaimType.INFERENCE) is True
        assert config.requires_citation(ClaimType.OPINION) is True
        assert config.requires_citation(ClaimType.COMMON_KNOWLEDGE) is False

    def test_relaxed_requires_only_quotation(self):
        config = CitationConfig(requirement_level=CitationRequirement.RELAXED)
        assert config.requires_citation(ClaimType.QUOTATION) is True
        assert config.requires_citation(ClaimType.FACTUAL) is False
        assert config.requires_citation(ClaimType.OPINION) is False

    def test_moderate_uses_configured_list(self):
        config = CitationConfig(requirement_level=CitationRequirement.MODERATE)
        assert config.requires_citation(ClaimType.FACTUAL) is True
        assert config.requires_citation(ClaimType.STATISTICAL) is True
        assert config.requires_citation(ClaimType.QUOTATION) is True
        assert config.requires_citation(ClaimType.INFERENCE) is False
        assert config.requires_citation(ClaimType.OPINION) is False

    def test_custom_require_citations_for(self):
        config = CitationConfig(
            requirement_level=CitationRequirement.MODERATE,
            require_citations_for=[ClaimType.FACTUAL, ClaimType.INFERENCE],
        )
        assert config.requires_citation(ClaimType.FACTUAL) is True
        assert config.requires_citation(ClaimType.INFERENCE) is True
        assert config.requires_citation(ClaimType.STATISTICAL) is False

    def test_max_age_days(self):
        config = CitationConfig()
        assert config.max_age_days == 730  # 2 years

    def test_serialization(self):
        config = CitationConfig()
        data = config.model_dump()
        restored = CitationConfig(**data)
        assert restored.requirement_level == config.requirement_level
