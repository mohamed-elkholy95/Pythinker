"""Claim Provenance Model for Hallucination Prevention.

Links claims in reports to their source evidence, enabling
verification that claims are grounded in actual visited content.
"""

import hashlib
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ClaimVerificationStatus(str, Enum):
    """Status of claim verification."""

    VERIFIED = "verified"  # Claim found in source content
    PARTIAL = "partial"  # Claim partially supported
    INFERRED = "inferred"  # Derived from context, not directly stated
    UNVERIFIED = "unverified"  # No matching source found
    CONTRADICTED = "contradicted"  # Source contradicts claim
    FABRICATED = "fabricated"  # Claim appears to be made up


class ClaimType(str, Enum):
    """Type of claim for categorization."""

    METRIC = "metric"  # "Model X scored 71%"
    FACT = "fact"  # "Python was released in 1991"
    QUOTE = "quote"  # Direct quote from source
    COMPARISON = "comparison"  # "Model A is better than Model B"
    DATE = "date"  # Temporal claims
    PRICE = "price"  # Cost/pricing claims
    ENTITY = "entity"  # Claims about named entities
    UNKNOWN = "unknown"


class ClaimProvenance(BaseModel):
    """Links a claim in a report to its source evidence.

    This is the core model for audit trails. Each factual claim in a report
    should have a corresponding ClaimProvenance record.

    Usage:
        provenance = ClaimProvenance(
            session_id="abc123",
            claim_text="Claude 3.5 Sonnet scored 88.7% on MMLU",
            claim_type=ClaimType.METRIC,
        )

        # Mark as verified when source is found
        provenance.mark_verified(
            source_id="source456",
            tool_event_id="event789",
            excerpt="Claude 3.5 Sonnet achieved 88.7% on the MMLU benchmark",
            similarity=0.95,
        )
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    report_id: str | None = None  # Links to ReportEvent.id

    # The claim itself
    claim_text: str  # "Claude 3.5 Sonnet scored 88.7% on MMLU"
    claim_type: ClaimType = ClaimType.UNKNOWN
    claim_hash: str = ""  # For deduplication, set in __init__

    # Source linkage (primary evidence)
    source_id: str | None = None  # References VisitedSource.id
    tool_event_id: str | None = None  # References ToolEvent.id
    source_url: str | None = None  # URL for quick reference

    # Evidence from source
    supporting_excerpt: str | None = None  # Exact text from source
    excerpt_location: str | None = None  # "paragraph 3", "table row 2"
    similarity_score: float = 0.0  # Semantic similarity claim↔excerpt

    # Verification
    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    verification_method: str | None = None  # "exact_match", "semantic", "llm"
    verified_at: datetime | None = None
    verifier_confidence: float = 0.0

    # Audit trail
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "system"  # "execution_agent", "critic", "manual"

    # Flags
    is_fabricated: bool = False  # True if no source found
    requires_manual_review: bool = False
    is_numeric: bool = False  # True if claim contains numbers
    extracted_numbers: list[float] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        """Generate claim hash after initialization."""
        if not self.claim_hash:
            self.claim_hash = self._generate_hash(self.claim_text)

        # Detect if claim is numeric
        import re
        numbers = re.findall(r'\d+(?:\.\d+)?', self.claim_text)
        if numbers:
            self.is_numeric = True
            self.extracted_numbers = [float(n) for n in numbers]

    @staticmethod
    def _generate_hash(text: str) -> str:
        """Generate hash for claim deduplication."""
        normalized = text.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def mark_verified(
        self,
        source_id: str,
        tool_event_id: str | None = None,
        source_url: str | None = None,
        excerpt: str | None = None,
        similarity: float = 1.0,
        method: str = "semantic",
    ) -> None:
        """Mark claim as verified with source evidence.

        Args:
            source_id: ID of the VisitedSource that supports this claim
            tool_event_id: ID of the ToolEvent that produced the source
            source_url: URL for quick reference
            excerpt: Supporting excerpt from source
            similarity: Semantic similarity score
            method: Verification method used
        """
        self.source_id = source_id
        self.tool_event_id = tool_event_id
        self.source_url = source_url
        self.supporting_excerpt = excerpt
        self.similarity_score = similarity

        if similarity >= 0.8:
            self.verification_status = ClaimVerificationStatus.VERIFIED
        elif similarity >= 0.5:
            self.verification_status = ClaimVerificationStatus.PARTIAL
        else:
            self.verification_status = ClaimVerificationStatus.INFERRED

        self.verification_method = method
        self.verified_at = datetime.utcnow()
        self.verifier_confidence = similarity
        self.is_fabricated = False

    def mark_fabricated(self, reason: str | None = None) -> None:
        """Mark claim as potentially fabricated (no source found).

        Args:
            reason: Optional reason for marking as fabricated
        """
        self.verification_status = ClaimVerificationStatus.FABRICATED
        self.is_fabricated = True
        self.requires_manual_review = True
        self.verified_at = datetime.utcnow()
        if reason:
            self.verification_method = f"fabricated: {reason}"

    def mark_contradicted(self, source_id: str, excerpt: str) -> None:
        """Mark claim as contradicted by source.

        Args:
            source_id: ID of the source that contradicts
            excerpt: Contradicting excerpt
        """
        self.source_id = source_id
        self.supporting_excerpt = excerpt
        self.verification_status = ClaimVerificationStatus.CONTRADICTED
        self.requires_manual_review = True
        self.verified_at = datetime.utcnow()

    @property
    def is_grounded(self) -> bool:
        """Check if claim is sufficiently grounded."""
        return self.verification_status in (
            ClaimVerificationStatus.VERIFIED,
            ClaimVerificationStatus.PARTIAL,
        )

    @property
    def needs_caveat(self) -> bool:
        """Check if claim needs a caveat/disclaimer."""
        return self.verification_status in (
            ClaimVerificationStatus.INFERRED,
            ClaimVerificationStatus.UNVERIFIED,
        )

    @property
    def is_problematic(self) -> bool:
        """Check if claim has verification problems."""
        return self.verification_status in (
            ClaimVerificationStatus.FABRICATED,
            ClaimVerificationStatus.CONTRADICTED,
            ClaimVerificationStatus.UNVERIFIED,
        )

    def get_attribution_text(self) -> str | None:
        """Get attribution text for this claim if verified.

        Returns:
            Attribution text like "According to [source]..." or None
        """
        if not self.is_grounded:
            return None

        if self.source_url:
            return f"According to {self.source_url}"
        if self.source_id:
            return f"[Source: {self.source_id[:8]}]"
        return None

    def get_warning_text(self) -> str | None:
        """Get warning text if claim has issues.

        Returns:
            Warning message or None
        """
        warnings = {
            ClaimVerificationStatus.FABRICATED: f"FABRICATED: No source found for: {self.claim_text[:50]}...",
            ClaimVerificationStatus.CONTRADICTED: f"CONTRADICTED: Source contradicts: {self.claim_text[:50]}...",
            ClaimVerificationStatus.UNVERIFIED: f"UNVERIFIED: Cannot verify: {self.claim_text[:50]}...",
            ClaimVerificationStatus.INFERRED: f"INFERRED: Not directly stated: {self.claim_text[:50]}...",
        }
        return warnings.get(self.verification_status)


class ProvenanceStore(BaseModel):
    """Session-scoped storage for claim provenance.

    Provides methods for looking up and managing provenance data.
    """

    session_id: str
    claims: dict[str, ClaimProvenance] = Field(default_factory=dict)  # claim_hash -> provenance
    verified_claims: set[str] = Field(default_factory=set)  # claim_hashes of verified claims

    def add_claim(self, provenance: ClaimProvenance) -> None:
        """Add a claim provenance record.

        Args:
            provenance: ClaimProvenance to add
        """
        self.claims[provenance.claim_hash] = provenance
        if provenance.is_grounded:
            self.verified_claims.add(provenance.claim_hash)

    def get_claim(self, claim_text: str) -> ClaimProvenance | None:
        """Get provenance for a claim by text.

        Args:
            claim_text: Claim text to look up

        Returns:
            ClaimProvenance or None
        """
        claim_hash = ClaimProvenance._generate_hash(claim_text)
        return self.claims.get(claim_hash)

    def is_claim_verified(self, claim_text: str) -> bool:
        """Check if a claim is verified.

        Args:
            claim_text: Claim text to check

        Returns:
            True if claim is verified
        """
        claim_hash = ClaimProvenance._generate_hash(claim_text)
        return claim_hash in self.verified_claims

    def get_unverified_claims(self) -> list[ClaimProvenance]:
        """Get all unverified claims."""
        return [
            c for c in self.claims.values()
            if not c.is_grounded
        ]

    def get_fabricated_claims(self) -> list[ClaimProvenance]:
        """Get all fabricated claims."""
        return [
            c for c in self.claims.values()
            if c.is_fabricated
        ]

    def get_numeric_claims(self) -> list[ClaimProvenance]:
        """Get all numeric claims (need special verification)."""
        return [
            c for c in self.claims.values()
            if c.is_numeric
        ]

    def get_verification_summary(self) -> dict:
        """Get summary statistics of claim verification.

        Returns:
            Dict with verification statistics
        """
        total = len(self.claims)
        verified = sum(1 for c in self.claims.values() if c.verification_status == ClaimVerificationStatus.VERIFIED)
        partial = sum(1 for c in self.claims.values() if c.verification_status == ClaimVerificationStatus.PARTIAL)
        inferred = sum(1 for c in self.claims.values() if c.verification_status == ClaimVerificationStatus.INFERRED)
        unverified = sum(1 for c in self.claims.values() if c.verification_status == ClaimVerificationStatus.UNVERIFIED)
        fabricated = sum(1 for c in self.claims.values() if c.is_fabricated)
        contradicted = sum(1 for c in self.claims.values() if c.verification_status == ClaimVerificationStatus.CONTRADICTED)

        grounded_rate = (verified + partial) / total if total > 0 else 0

        return {
            "total_claims": total,
            "verified": verified,
            "partial": partial,
            "inferred": inferred,
            "unverified": unverified,
            "fabricated": fabricated,
            "contradicted": contradicted,
            "grounded_rate": grounded_rate,
            "has_critical_issues": fabricated > 0 or contradicted > 0,
        }
