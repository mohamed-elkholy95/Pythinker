"""Source quality assessment and filtering models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceReliability(str, Enum):
    """Source reliability tiers."""

    HIGH = "high"  # Academic, official docs, reputable news
    MEDIUM = "medium"  # Known tech blogs, established platforms
    LOW = "low"  # Forums, social media, unknown sources
    UNKNOWN = "unknown"  # Cannot determine


class ContentFreshness(str, Enum):
    """Content freshness categories."""

    CURRENT = "current"  # < 6 months
    RECENT = "recent"  # 6-18 months
    DATED = "dated"  # 18-36 months
    STALE = "stale"  # > 36 months
    UNKNOWN = "unknown"


class SourceQualityScore(BaseModel):
    """Comprehensive source quality assessment."""

    url: str
    domain: str

    # Scoring components (0.0 to 1.0)
    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.5, ge=0.0, le=1.0)
    content_depth_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Metadata
    reliability_tier: SourceReliability = SourceReliability.UNKNOWN
    freshness_category: ContentFreshness = ContentFreshness.UNKNOWN
    publication_date: datetime | None = None
    author_authority: float | None = None

    # Flags
    is_primary_source: bool = False
    has_citations: bool = False
    is_paywalled: bool = False
    requires_login: bool = False

    @property
    def composite_score(self) -> float:
        """Weighted composite quality score."""
        weights = {
            "reliability": 0.35,
            "relevance": 0.30,
            "freshness": 0.20,
            "depth": 0.15,
        }
        return (
            self.reliability_score * weights["reliability"]
            + self.relevance_score * weights["relevance"]
            + self.freshness_score * weights["freshness"]
            + self.content_depth_score * weights["depth"]
        )

    @property
    def passes_threshold(self) -> bool:
        """Check if source passes minimum quality threshold."""
        return self.composite_score >= 0.4 and not self.is_paywalled


class SourceFilterConfig(BaseModel):
    """Configuration for source filtering."""

    min_composite_score: float = Field(default=0.4, ge=0.0, le=1.0)
    min_reliability_score: float = Field(default=0.3, ge=0.0, le=1.0)
    min_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    max_age_days: int | None = Field(default=365 * 2)  # 2 years default

    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)

    require_https: bool = True
    allow_paywalled: bool = False
    prefer_primary_sources: bool = True

    # Domain tier overrides
    high_reliability_domains: list[str] = Field(
        default_factory=lambda: [
            "arxiv.org",
            "github.com",
            "docs.python.org",
            "pytorch.org",
            "tensorflow.org",
            "huggingface.co",
            "openai.com",
            "anthropic.com",
            "nature.com",
            "acm.org",
            "ieee.org",
            "research.google",
            "microsoft.com",
            "aws.amazon.com",
            "cloud.google.com",
            "developer.mozilla.org",
            "w3.org",
            "ietf.org",
        ]
    )
    medium_reliability_domains: list[str] = Field(
        default_factory=lambda: [
            "medium.com",
            "dev.to",
            "stackoverflow.com",
            "towardsdatascience.com",
            "analyticsvidhya.com",
            "hackernews.com",
            "techcrunch.com",
            "arstechnica.com",
            "wired.com",
            "theverge.com",
        ]
    )


class FilteredSourceResult(BaseModel):
    """Result of source filtering operation."""

    accepted_sources: list[SourceQualityScore] = Field(default_factory=list)
    rejected_sources: list[SourceQualityScore] = Field(default_factory=list)
    rejection_reasons: dict[str, str] = Field(default_factory=dict)

    @property
    def acceptance_rate(self) -> float:
        """Percentage of sources accepted."""
        total = len(self.accepted_sources) + len(self.rejected_sources)
        return len(self.accepted_sources) / total if total > 0 else 0.0

    @property
    def total_sources(self) -> int:
        """Total number of sources processed."""
        return len(self.accepted_sources) + len(self.rejected_sources)

    def get_summary(self) -> str:
        """Get a human-readable summary of filtering results."""
        return (
            f"Source Filtering Results:\n"
            f"  Total: {self.total_sources}\n"
            f"  Accepted: {len(self.accepted_sources)}\n"
            f"  Rejected: {len(self.rejected_sources)}\n"
            f"  Acceptance Rate: {self.acceptance_rate:.1%}"
        )
