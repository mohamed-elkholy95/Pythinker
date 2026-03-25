"""Tests for claim provenance domain models."""

import pytest

from app.domain.models.claim_provenance import (
    ClaimProvenance,
    ClaimType,
    ClaimVerificationStatus,
)


@pytest.mark.unit
class TestClaimVerificationStatusEnum:
    def test_all_values(self) -> None:
        expected = {"verified", "partial", "inferred", "unverified", "contradicted", "fabricated"}
        assert {s.value for s in ClaimVerificationStatus} == expected


@pytest.mark.unit
class TestClaimTypeEnum:
    def test_all_values(self) -> None:
        expected = {"metric", "fact", "quote", "comparison", "date", "price", "entity", "unknown"}
        assert {t.value for t in ClaimType} == expected


@pytest.mark.unit
class TestClaimProvenance:
    def _make_claim(self, **kwargs) -> ClaimProvenance:
        defaults = {
            "session_id": "sess1",
            "claim_text": "Python 3.12 improved performance by 25%",
        }
        defaults.update(kwargs)
        return ClaimProvenance(**defaults)

    def test_basic_construction(self) -> None:
        claim = self._make_claim()
        assert claim.session_id == "sess1"
        assert claim.verification_status == ClaimVerificationStatus.UNVERIFIED
        assert claim.is_fabricated is False
        assert claim.id  # auto-generated

    def test_claim_hash_generated(self) -> None:
        claim = self._make_claim()
        assert claim.claim_hash != ""
        assert len(claim.claim_hash) == 16

    def test_numeric_detection(self) -> None:
        claim = self._make_claim(claim_text="Model scored 92.5% accuracy")
        assert claim.is_numeric is True
        assert 92.5 in claim.extracted_numbers

    def test_non_numeric_claim(self) -> None:
        claim = self._make_claim(claim_text="Python is a programming language")
        assert claim.is_numeric is False
        assert claim.extracted_numbers == []

    def test_mark_verified_high_similarity(self) -> None:
        claim = self._make_claim()
        claim.mark_verified(
            source_id="src1",
            excerpt="Python 3.12 showed 25% performance improvement",
            similarity=0.9,
        )
        assert claim.verification_status == ClaimVerificationStatus.VERIFIED
        assert claim.source_id == "src1"
        assert claim.is_fabricated is False

    def test_mark_verified_medium_similarity(self) -> None:
        claim = self._make_claim()
        claim.mark_verified(source_id="src1", similarity=0.6)
        assert claim.verification_status == ClaimVerificationStatus.PARTIAL

    def test_mark_verified_low_similarity(self) -> None:
        claim = self._make_claim()
        claim.mark_verified(source_id="src1", similarity=0.3)
        assert claim.verification_status == ClaimVerificationStatus.INFERRED

    def test_mark_fabricated(self) -> None:
        claim = self._make_claim()
        claim.mark_fabricated(reason="No source found")
        assert claim.verification_status == ClaimVerificationStatus.FABRICATED
        assert claim.is_fabricated is True
        assert claim.requires_manual_review is True

    def test_mark_contradicted(self) -> None:
        claim = self._make_claim()
        claim.mark_contradicted(source_id="src1", excerpt="Actually 15% improvement")
        assert claim.verification_status == ClaimVerificationStatus.CONTRADICTED
        assert claim.requires_manual_review is True

    def test_is_grounded_when_verified(self) -> None:
        claim = self._make_claim()
        claim.mark_verified(source_id="src1", similarity=0.85)
        assert claim.is_grounded is True

    def test_is_not_grounded_when_unverified(self) -> None:
        claim = self._make_claim()
        assert claim.is_grounded is False

    def test_claim_hash_deterministic(self) -> None:
        c1 = self._make_claim(claim_text="Test claim")
        c2 = self._make_claim(claim_text="Test claim")
        assert c1.claim_hash == c2.claim_hash

    def test_claim_hash_case_insensitive(self) -> None:
        c1 = self._make_claim(claim_text="Test Claim")
        c2 = self._make_claim(claim_text="test claim")
        assert c1.claim_hash == c2.claim_hash
