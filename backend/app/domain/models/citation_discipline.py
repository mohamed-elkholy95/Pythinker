"""Enhanced citation models for strict source discipline."""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class CitationRequirement(str, Enum):
    """How strictly citations are required."""

    STRICT = "strict"  # Every factual claim must be cited
    MODERATE = "moderate"  # Major claims must be cited
    RELAXED = "relaxed"  # Citations encouraged but not required


class ClaimType(str, Enum):
    """Type of claim being made."""

    FACTUAL = "factual"  # Verifiable fact
    STATISTICAL = "statistical"  # Numeric/statistical claim
    QUOTATION = "quotation"  # Direct quote
    INFERENCE = "inference"  # Derived conclusion
    OPINION = "opinion"  # Subjective statement
    COMMON_KNOWLEDGE = "common"  # Generally known facts


class CitedClaim(BaseModel):
    """A claim with mandatory citation tracking."""

    claim_text: str = Field(..., description="The claim being made")
    claim_type: ClaimType = Field(...)

    # Citation requirements based on claim type
    citation_ids: list[str] = Field(default_factory=list)
    supporting_excerpts: list[str] = Field(default_factory=list)

    # Verification status
    is_verified: bool = Field(default=False)
    verification_method: str | None = Field(default=None)

    # Confidence and caveats
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_caveat: bool = Field(default=False)
    caveat_text: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_citation_requirements(self) -> "CitedClaim":
        """Ensure citations match claim type requirements."""
        # Factual and statistical claims MUST have citations
        if self.claim_type in (ClaimType.FACTUAL, ClaimType.STATISTICAL, ClaimType.QUOTATION):
            if not self.citation_ids:
                self.requires_caveat = True
                self.caveat_text = f"[Unverified {self.claim_type.value} claim]"
                self.confidence = min(self.confidence, 0.3)

        # Inferences should note they are inferred
        if self.claim_type == ClaimType.INFERENCE and not self.caveat_text:
            self.caveat_text = "[Inferred from available data]"

        return self

    def get_display_text(self) -> str:
        """Get claim text with caveat if required."""
        if self.requires_caveat and self.caveat_text:
            return f"{self.claim_text} {self.caveat_text}"
        return self.claim_text


class CitationValidationResult(BaseModel):
    """Result of citation validation for content."""

    is_valid: bool = Field(default=False)
    total_claims: int = Field(default=0)
    cited_claims: int = Field(default=0)
    uncited_factual_claims: int = Field(default=0)

    # Detailed breakdown
    claims: list[CitedClaim] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    weak_citations: list[str] = Field(default_factory=list)

    # Scores
    citation_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_quality: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def overall_score(self) -> float:
        """Overall citation discipline score."""
        return self.citation_coverage * 0.6 + self.citation_quality * 0.4

    def get_report(self) -> str:
        """Generate human-readable validation report."""
        lines = [
            "Citation Validation Report",
            "=" * 40,
            f"Total Claims: {self.total_claims}",
            f"Cited Claims: {self.cited_claims}",
            f"Uncited Factual Claims: {self.uncited_factual_claims}",
            "",
            f"Citation Coverage: {self.citation_coverage:.1%}",
            f"Citation Quality: {self.citation_quality:.1%}",
            f"Overall Score: {self.overall_score:.1%}",
        ]

        if self.missing_citations:
            lines.extend(
                [
                    "",
                    "Missing Citations:",
                    *[f"  - {c}" for c in self.missing_citations[:5]],
                ]
            )

        if self.weak_citations:
            lines.extend(
                [
                    "",
                    "Weak Citations (low confidence sources):",
                    *[f"  - {c}" for c in self.weak_citations[:5]],
                ]
            )

        return "\n".join(lines)

    def get_claims_by_type(self, claim_type: ClaimType) -> list[CitedClaim]:
        """Get all claims of a specific type."""
        return [c for c in self.claims if c.claim_type == claim_type]

    def get_uncited_claims(self) -> list[CitedClaim]:
        """Get all claims without citations."""
        return [c for c in self.claims if not c.citation_ids]


class CitationConfig(BaseModel):
    """Configuration for citation requirements."""

    requirement_level: CitationRequirement = CitationRequirement.MODERATE
    min_coverage_score: float = Field(default=0.7, ge=0.0, le=1.0)
    min_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # What requires citations
    require_citations_for: list[ClaimType] = Field(
        default_factory=lambda: [
            ClaimType.FACTUAL,
            ClaimType.STATISTICAL,
            ClaimType.QUOTATION,
        ]
    )

    # Source quality requirements
    min_source_reliability: float = Field(default=0.4, ge=0.0, le=1.0)
    prefer_primary_sources: bool = True
    max_age_days: int | None = Field(default=730)  # 2 years

    # Enforcement options
    auto_add_caveats: bool = Field(default=True, description="Automatically add caveats to uncited claims")
    fail_on_uncited_factual: bool = Field(default=False, description="Fail validation if any factual claim is uncited")

    def requires_citation(self, claim_type: ClaimType) -> bool:
        """Check if a claim type requires citation under this config."""
        if self.requirement_level == CitationRequirement.STRICT:
            # Everything except common knowledge needs citation
            return claim_type != ClaimType.COMMON_KNOWLEDGE

        if self.requirement_level == CitationRequirement.RELAXED:
            # Only quotations strictly need citation
            return claim_type == ClaimType.QUOTATION

        # Moderate: use configured list
        return claim_type in self.require_citations_for
