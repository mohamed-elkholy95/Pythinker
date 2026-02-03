"""Source Attribution Model for tracking claim provenance.

Tracks where every claim comes from to prevent hallucinations and ensure
proper attribution of facts vs inferences.

Usage:
    attribution = SourceAttribution(
        claim="The article has 1.5K claps",
        source_type=SourceType.DIRECT_CONTENT,
        source_url="https://medium.com/article",
        access_status=AccessStatus.FULL,
        confidence=0.95,
        raw_excerpt="Article stats: 1.5K claps"
    )
"""

from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Type of source for a claim."""

    DIRECT_CONTENT = "direct"  # Explicitly stated in source
    INFERRED = "inferred"  # Derived from context
    UNAVAILABLE = "unavailable"  # Could not access source


class AccessStatus(str, Enum):
    """Access status when fetching content."""

    FULL = "full"  # Full content accessible
    PARTIAL = "partial"  # Preview only (e.g., truncated)
    PAYWALL = "paywall"  # Behind paywall
    LOGIN_REQUIRED = "login_required"  # Requires authentication
    ERROR = "error"  # Failed to access


class SourceAttribution(BaseModel):
    """Attribution for a single claim or piece of information.

    Tracks the provenance of claims to distinguish between:
    - Direct quotes or facts from sources
    - Inferences made from available data
    - Information that couldn't be accessed
    """

    claim: str = Field(description="The claim or piece of information")
    source_type: SourceType = Field(description="How this information was obtained")
    source_url: str | None = Field(default=None, description="URL of the source")
    access_status: AccessStatus = Field(
        default=AccessStatus.FULL, description="Access status when retrieving this information"
    )
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confidence in this attribution (0.0-1.0)")
    raw_excerpt: str | None = Field(default=None, description="Actual text excerpt from source supporting this claim")

    def is_verified(self) -> bool:
        """Check if this claim is verified from direct content."""
        return (
            self.source_type == SourceType.DIRECT_CONTENT
            and self.access_status == AccessStatus.FULL
            and self.confidence >= 0.8
        )

    def requires_caveat(self) -> bool:
        """Check if this claim needs a caveat when presented."""
        return (
            self.source_type == SourceType.INFERRED
            or self.access_status in (AccessStatus.PARTIAL, AccessStatus.PAYWALL)
            or self.confidence < 0.7
        )

    def get_attribution_prefix(self) -> str:
        """Get the appropriate prefix for presenting this claim.

        Returns:
            Prefix string like "According to [source]" or "[Inferred]"
        """
        if self.source_type == SourceType.INFERRED:
            return "[Inferred] "
        if self.access_status == AccessStatus.PARTIAL:
            return "[Partial access] "
        if self.access_status == AccessStatus.PAYWALL:
            return "[Behind paywall] "
        if self.source_type == SourceType.UNAVAILABLE:
            return "[Not accessible] "
        if self.source_url:
            return f"According to {self.source_url}: "
        return ""


class ContentAccessResult(BaseModel):
    """Result of accessing content from a URL.

    Contains both the content and metadata about access status
    for downstream attribution tracking.
    """

    url: str = Field(description="URL that was accessed")
    content: str = Field(description="Extracted text content")
    access_status: AccessStatus = Field(description="How much content was accessible")
    paywall_confidence: float = Field(
        ge=0.0, le=1.0, default=0.0, description="Confidence that content is behind a paywall"
    )
    truncated: bool = Field(default=False, description="Whether content was truncated")
    original_length: int | None = Field(default=None, description="Original content length before truncation")
    paywall_indicators: list[str] = Field(default_factory=list, description="Detected paywall indicators")

    def get_access_message(self) -> str:
        """Get a human-readable access status message."""
        if self.access_status == AccessStatus.FULL:
            return "Full content accessible"
        if self.access_status == AccessStatus.PARTIAL:
            return "Only partial content accessible (preview)"
        if self.access_status == AccessStatus.PAYWALL:
            indicators = ", ".join(self.paywall_indicators[:3]) if self.paywall_indicators else "subscription required"
            return f"Content behind paywall ({indicators})"
        if self.access_status == AccessStatus.LOGIN_REQUIRED:
            return "Login required to access content"
        return "Error accessing content"


class AttributionSummary(BaseModel):
    """Summary of attributions for an output.

    Provides aggregate statistics about source quality and
    potential issues with the generated content.
    """

    total_claims: int = Field(default=0, description="Total number of claims tracked")
    verified_claims: int = Field(default=0, description="Claims from direct sources")
    inferred_claims: int = Field(default=0, description="Claims derived from context")
    unavailable_claims: int = Field(default=0, description="Claims from inaccessible sources")
    average_confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Average confidence across all claims")
    has_paywall_sources: bool = Field(default=False, description="Whether any sources were paywalled")
    attributions: list[SourceAttribution] = Field(default_factory=list, description="Individual attribution records")

    def add_attribution(self, attribution: SourceAttribution) -> None:
        """Add an attribution and update summary statistics."""
        self.attributions.append(attribution)
        self.total_claims += 1

        if attribution.source_type == SourceType.DIRECT_CONTENT:
            self.verified_claims += 1
        elif attribution.source_type == SourceType.INFERRED:
            self.inferred_claims += 1
        else:
            self.unavailable_claims += 1

        if attribution.access_status == AccessStatus.PAYWALL:
            self.has_paywall_sources = True

        # Update average confidence
        total_conf = sum(a.confidence for a in self.attributions)
        self.average_confidence = total_conf / len(self.attributions)

    def get_reliability_score(self) -> float:
        """Get an overall reliability score for the content.

        Returns:
            Score from 0.0 to 1.0 indicating content reliability
        """
        if self.total_claims == 0:
            return 1.0

        # Weight verified claims higher
        verified_weight = 1.0
        inferred_weight = 0.6
        unavailable_weight = 0.2

        weighted_sum = (
            self.verified_claims * verified_weight
            + self.inferred_claims * inferred_weight
            + self.unavailable_claims * unavailable_weight
        )

        max_possible = self.total_claims * verified_weight

        return (weighted_sum / max_possible) * self.average_confidence

    def needs_caveats(self) -> bool:
        """Check if the content needs caveats about source quality."""
        return (
            self.inferred_claims > self.verified_claims
            or self.has_paywall_sources
            or self.average_confidence < 0.7
            or self.unavailable_claims > 0
        )
