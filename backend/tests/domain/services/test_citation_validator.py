"""Tests for self-contained data models in citation_validator.py.

Covers CitationSemanticResult and EnhancedCitationValidationResult dataclasses,
their default values, and all property/method logic without requiring an LLM.
"""

from unittest.mock import MagicMock

import pytest

from app.domain.services.citation_validator import (
    CitationSemanticResult,
    EnhancedCitationValidationResult,
)

# =============================================================================
# CitationSemanticResult — default values
# =============================================================================


class TestCitationSemanticResultDefaults:
    def test_required_fields_are_stored(self) -> None:
        result = CitationSemanticResult(claim_text="The sky is blue.", citation_id="src-1")
        assert result.claim_text == "The sky is blue."
        assert result.citation_id == "src-1"

    def test_source_url_defaults_to_none(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.source_url is None

    def test_is_semantically_matched_defaults_to_false(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.is_semantically_matched is False

    def test_semantic_score_defaults_to_zero(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.semantic_score == 0.0

    def test_has_numeric_claim_defaults_to_false(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.has_numeric_claim is False

    def test_numeric_verified_defaults_to_false(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.numeric_verified is False

    def test_has_entity_claim_defaults_to_false(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.has_entity_claim is False

    def test_entity_verified_defaults_to_false(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.entity_verified is False

    def test_claimed_number_defaults_to_none(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.claimed_number is None

    def test_source_number_defaults_to_none(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.source_number is None

    def test_claimed_entity_defaults_to_none(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.claimed_entity is None

    def test_supporting_excerpt_defaults_to_none(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.supporting_excerpt is None

    def test_verification_method_defaults_to_keyword(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.verification_method == "keyword"

    def test_issues_defaults_to_empty_list(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1")
        assert result.issues == []

    def test_issues_list_is_not_shared_between_instances(self) -> None:
        """Each instance must get its own list (field default_factory guard)."""
        a = CitationSemanticResult(claim_text="a", citation_id="1")
        b = CitationSemanticResult(claim_text="b", citation_id="2")
        a.issues.append("problem")
        assert b.issues == []


# =============================================================================
# CitationSemanticResult.is_valid property
# =============================================================================


class TestCitationSemanticResultIsValid:
    def test_is_valid_true_when_semantically_matched(self) -> None:
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.1,  # low score — matched flag dominates
        )
        assert result.is_valid is True

    def test_is_valid_true_when_score_meets_threshold(self) -> None:
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            is_semantically_matched=False,
            semantic_score=0.5,
        )
        assert result.is_valid is True

    def test_is_valid_true_when_score_exceeds_threshold(self) -> None:
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            is_semantically_matched=False,
            semantic_score=0.9,
        )
        assert result.is_valid is True

    def test_is_valid_false_when_score_below_threshold_and_not_matched(self) -> None:
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            is_semantically_matched=False,
            semantic_score=0.49,
        )
        assert result.is_valid is False

    def test_is_valid_false_when_numeric_claim_not_verified(self) -> None:
        """Unverified numeric claim makes the result invalid regardless of score."""
        result = CitationSemanticResult(
            claim_text="The temperature is 37°C.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=False,
        )
        assert result.is_valid is False

    def test_is_valid_true_when_numeric_claim_verified(self) -> None:
        result = CitationSemanticResult(
            claim_text="The temperature is 37°C.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=True,
        )
        assert result.is_valid is True

    def test_is_valid_false_when_entity_claim_not_verified(self) -> None:
        """Unverified entity claim makes the result invalid regardless of score."""
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_entity_claim=True,
            entity_verified=False,
        )
        assert result.is_valid is False

    def test_is_valid_true_when_entity_claim_verified(self) -> None:
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_entity_claim=True,
            entity_verified=True,
        )
        assert result.is_valid is True

    def test_is_valid_false_when_both_numeric_and_entity_unverified(self) -> None:
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4 with 1T parameters.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=False,
            has_entity_claim=True,
            entity_verified=False,
        )
        assert result.is_valid is False

    def test_is_valid_false_when_numeric_unverified_even_if_entity_verified(self) -> None:
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4 with 1T parameters.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=False,
            has_entity_claim=True,
            entity_verified=True,
        )
        assert result.is_valid is False

    def test_is_valid_false_when_entity_unverified_even_if_numeric_verified(self) -> None:
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4 with 1T parameters.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=True,
            has_entity_claim=True,
            entity_verified=False,
        )
        assert result.is_valid is False

    def test_is_valid_true_when_both_numeric_and_entity_verified(self) -> None:
        result = CitationSemanticResult(
            claim_text="OpenAI released GPT-4 with 1T parameters.",
            citation_id="1",
            is_semantically_matched=True,
            semantic_score=0.8,
            has_numeric_claim=True,
            numeric_verified=True,
            has_entity_claim=True,
            entity_verified=True,
        )
        assert result.is_valid is True


# =============================================================================
# CitationSemanticResult.confidence property
# =============================================================================


class TestCitationSemanticResultConfidence:
    def test_confidence_with_only_semantic_score(self) -> None:
        """When no numeric or entity claims, confidence equals semantic_score."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.7,
        )
        assert result.confidence == pytest.approx(0.7)

    def test_confidence_with_zero_semantic_score(self) -> None:
        result = CitationSemanticResult(claim_text="claim", citation_id="1", semantic_score=0.0)
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_with_numeric_verified(self) -> None:
        """Average of semantic_score (0.6) + numeric score (1.0) = 0.8."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.6,
            has_numeric_claim=True,
            numeric_verified=True,
        )
        assert result.confidence == pytest.approx(0.8)

    def test_confidence_with_numeric_not_verified(self) -> None:
        """Average of semantic_score (0.6) + numeric score (0.0) = 0.3."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.6,
            has_numeric_claim=True,
            numeric_verified=False,
        )
        assert result.confidence == pytest.approx(0.3)

    def test_confidence_with_entity_verified(self) -> None:
        """Average of semantic_score (0.5) + entity score (1.0) = 0.75."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.5,
            has_entity_claim=True,
            entity_verified=True,
        )
        assert result.confidence == pytest.approx(0.75)

    def test_confidence_with_entity_not_verified(self) -> None:
        """Average of semantic_score (0.5) + entity score (0.0) = 0.25."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.5,
            has_entity_claim=True,
            entity_verified=False,
        )
        assert result.confidence == pytest.approx(0.25)

    def test_confidence_with_both_numeric_and_entity_verified(self) -> None:
        """Average of [0.6, 1.0, 1.0] = 0.8667."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.6,
            has_numeric_claim=True,
            numeric_verified=True,
            has_entity_claim=True,
            entity_verified=True,
        )
        assert result.confidence == pytest.approx(0.8667, abs=1e-3)

    def test_confidence_with_both_unverified(self) -> None:
        """Average of [0.9, 0.0, 0.0] = 0.3."""
        result = CitationSemanticResult(
            claim_text="claim",
            citation_id="1",
            semantic_score=0.9,
            has_numeric_claim=True,
            numeric_verified=False,
            has_entity_claim=True,
            entity_verified=False,
        )
        assert result.confidence == pytest.approx(0.3)


# =============================================================================
# EnhancedCitationValidationResult — helper to build instance
# =============================================================================


def _make_enhanced(
    semantic_results: list[CitationSemanticResult] | None = None,
    semantically_failed_count: int = 0,
    numeric_failed_count: int = 0,
    semantically_verified_count: int = 0,
    numeric_verified_count: int = 0,
) -> EnhancedCitationValidationResult:
    base_result = MagicMock()
    return EnhancedCitationValidationResult(
        base_result=base_result,
        semantic_results=semantic_results or [],
        semantically_verified_count=semantically_verified_count,
        semantically_failed_count=semantically_failed_count,
        numeric_verified_count=numeric_verified_count,
        numeric_failed_count=numeric_failed_count,
    )


def _make_valid_semantic_result(citation_id: str = "1") -> CitationSemanticResult:
    return CitationSemanticResult(
        claim_text="valid claim",
        citation_id=citation_id,
        is_semantically_matched=True,
        semantic_score=0.8,
    )


def _make_invalid_semantic_result(citation_id: str = "2") -> CitationSemanticResult:
    """Returns a result where is_valid == False (no match, low score)."""
    return CitationSemanticResult(
        claim_text="invalid claim",
        citation_id=citation_id,
        is_semantically_matched=False,
        semantic_score=0.1,
    )


# =============================================================================
# EnhancedCitationValidationResult — has_semantic_issues property
# =============================================================================


class TestEnhancedCitationValidationResultHasSemanticIssues:
    def test_no_issues_when_all_counts_are_zero(self) -> None:
        enhanced = _make_enhanced(semantically_failed_count=0, numeric_failed_count=0)
        assert enhanced.has_semantic_issues is False

    def test_has_issues_when_semantically_failed_count_positive(self) -> None:
        enhanced = _make_enhanced(semantically_failed_count=1, numeric_failed_count=0)
        assert enhanced.has_semantic_issues is True

    def test_has_issues_when_numeric_failed_count_positive(self) -> None:
        enhanced = _make_enhanced(semantically_failed_count=0, numeric_failed_count=2)
        assert enhanced.has_semantic_issues is True

    def test_has_issues_when_both_counts_positive(self) -> None:
        enhanced = _make_enhanced(semantically_failed_count=3, numeric_failed_count=1)
        assert enhanced.has_semantic_issues is True

    def test_verified_counts_do_not_trigger_issues(self) -> None:
        enhanced = _make_enhanced(
            semantically_verified_count=5,
            numeric_verified_count=3,
            semantically_failed_count=0,
            numeric_failed_count=0,
        )
        assert enhanced.has_semantic_issues is False


# =============================================================================
# EnhancedCitationValidationResult — get_failed_citations()
# =============================================================================


class TestEnhancedCitationValidationResultGetFailedCitations:
    def test_returns_empty_list_when_no_semantic_results(self) -> None:
        enhanced = _make_enhanced(semantic_results=[])
        assert enhanced.get_failed_citations() == []

    def test_returns_empty_list_when_all_results_valid(self) -> None:
        valid1 = _make_valid_semantic_result("a")
        valid2 = _make_valid_semantic_result("b")
        enhanced = _make_enhanced(semantic_results=[valid1, valid2])
        assert enhanced.get_failed_citations() == []

    def test_returns_all_when_all_results_invalid(self) -> None:
        inv1 = _make_invalid_semantic_result("x")
        inv2 = _make_invalid_semantic_result("y")
        enhanced = _make_enhanced(semantic_results=[inv1, inv2])
        failed = enhanced.get_failed_citations()
        assert len(failed) == 2
        assert inv1 in failed
        assert inv2 in failed

    def test_filters_only_invalid_results(self) -> None:
        valid = _make_valid_semantic_result("ok")
        invalid = _make_invalid_semantic_result("bad")
        enhanced = _make_enhanced(semantic_results=[valid, invalid])
        failed = enhanced.get_failed_citations()
        assert len(failed) == 1
        assert failed[0] is invalid

    def test_invalid_due_to_unverified_numeric_claim_is_included(self) -> None:
        result = CitationSemanticResult(
            claim_text="Revenue grew by 42%",
            citation_id="num-1",
            is_semantically_matched=True,
            semantic_score=0.9,
            has_numeric_claim=True,
            numeric_verified=False,
        )
        enhanced = _make_enhanced(semantic_results=[result])
        failed = enhanced.get_failed_citations()
        assert len(failed) == 1
        assert failed[0] is result

    def test_invalid_due_to_unverified_entity_claim_is_included(self) -> None:
        result = CitationSemanticResult(
            claim_text="Tesla manufactures electric vehicles.",
            citation_id="ent-1",
            is_semantically_matched=True,
            semantic_score=0.85,
            has_entity_claim=True,
            entity_verified=False,
        )
        enhanced = _make_enhanced(semantic_results=[result])
        failed = enhanced.get_failed_citations()
        assert len(failed) == 1
        assert failed[0] is result


# =============================================================================
# EnhancedCitationValidationResult — get_semantic_summary()
# =============================================================================


class TestEnhancedCitationValidationResultGetSemanticSummary:
    def test_summary_contains_verified_count(self) -> None:
        valid1 = _make_valid_semantic_result("a")
        valid2 = _make_valid_semantic_result("b")
        enhanced = _make_enhanced(
            semantic_results=[valid1, valid2],
            semantically_verified_count=2,
        )
        summary = enhanced.get_semantic_summary()
        assert "2/2" in summary

    def test_summary_contains_numeric_verified_count(self) -> None:
        enhanced = _make_enhanced(
            semantic_results=[_make_valid_semantic_result()],
            semantically_verified_count=1,
            numeric_verified_count=3,
            numeric_failed_count=1,
        )
        summary = enhanced.get_semantic_summary()
        assert "3" in summary

    def test_summary_contains_numeric_failed_count(self) -> None:
        enhanced = _make_enhanced(
            semantic_results=[_make_invalid_semantic_result()],
            semantically_failed_count=1,
            numeric_failed_count=2,
        )
        summary = enhanced.get_semantic_summary()
        assert "2" in summary

    def test_summary_format_starts_with_semantic_label(self) -> None:
        enhanced = _make_enhanced()
        summary = enhanced.get_semantic_summary()
        assert summary.startswith("Semantic:")

    def test_summary_contains_numeric_label(self) -> None:
        enhanced = _make_enhanced()
        summary = enhanced.get_semantic_summary()
        assert "Numeric:" in summary

    def test_summary_with_zero_counts(self) -> None:
        enhanced = _make_enhanced(semantic_results=[])
        summary = enhanced.get_semantic_summary()
        assert "0/0" in summary
        assert "0 verified" in summary
        assert "0 failed" in summary

    def test_summary_reflects_total_semantic_results_length(self) -> None:
        results = [_make_valid_semantic_result(str(i)) for i in range(5)]
        enhanced = _make_enhanced(
            semantic_results=results,
            semantically_verified_count=5,
        )
        summary = enhanced.get_semantic_summary()
        assert "5/5" in summary

    def test_summary_is_a_string(self) -> None:
        enhanced = _make_enhanced()
        assert isinstance(enhanced.get_semantic_summary(), str)
