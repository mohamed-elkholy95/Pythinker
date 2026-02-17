"""Source filtering and quality assessment service."""

import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from app.domain.models.source_quality import (
    ContentFreshness,
    FilteredSourceResult,
    SourceFilterConfig,
    SourceQualityScore,
    SourceReliability,
)

logger = logging.getLogger(__name__)


class SourceFilterService:
    """Filters and scores sources based on quality criteria."""

    def __init__(self, config: SourceFilterConfig | None = None):
        self.config = config or SourceFilterConfig()

    def filter_sources(
        self,
        sources: list[dict],
        query: str,
    ) -> FilteredSourceResult:
        """Filter sources based on quality criteria.

        Args:
            sources: Raw source data (url, content, metadata)
            query: Original search query for relevance scoring

        Returns:
            FilteredSourceResult with accepted/rejected sources
        """
        result = FilteredSourceResult()

        for source in sources:
            score = self.assess_quality(source, query)

            rejection_reason = self._check_rejection(score)
            if rejection_reason:
                result.rejected_sources.append(score)
                result.rejection_reasons[score.url] = rejection_reason
            else:
                result.accepted_sources.append(score)

        # Sort accepted by composite score
        result.accepted_sources.sort(key=lambda s: s.composite_score, reverse=True)

        logger.info(
            f"Source filtering: {len(result.accepted_sources)} accepted, {len(result.rejected_sources)} rejected"
        )

        return result

    def assess_quality(self, source: dict, query: str) -> SourceQualityScore:
        """Assess quality of a single source."""
        url = source.get("url", "")
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        # Determine reliability tier
        reliability_tier = self._assess_reliability_tier(domain)
        reliability_score = self._tier_to_score(reliability_tier)

        # Assess freshness
        pub_date = self._extract_publication_date(source)
        freshness_cat, freshness_score = self._assess_freshness(pub_date)

        # Assess relevance to query
        relevance_score = self._assess_relevance(source, query)

        # Assess content depth
        depth_score = self._assess_content_depth(source)

        return SourceQualityScore(
            url=url,
            domain=domain,
            reliability_score=reliability_score,
            relevance_score=relevance_score,
            freshness_score=freshness_score,
            content_depth_score=depth_score,
            reliability_tier=reliability_tier,
            freshness_category=freshness_cat,
            publication_date=pub_date,
            is_primary_source=self._is_primary_source(source, domain),
            has_citations=self._has_citations(source),
            is_paywalled=source.get("is_paywalled", False),
            requires_login=source.get("requires_login", False),
        )

    def _assess_reliability_tier(self, domain: str) -> SourceReliability:
        """Determine source reliability tier from domain."""
        # Check high reliability domains
        for high_domain in self.config.high_reliability_domains:
            if high_domain in domain or domain.endswith(high_domain):
                return SourceReliability.HIGH

        # Check medium reliability domains
        for med_domain in self.config.medium_reliability_domains:
            if med_domain in domain or domain.endswith(med_domain):
                return SourceReliability.MEDIUM

        # Check blocked domains
        for blocked in self.config.blocked_domains:
            if blocked in domain:
                return SourceReliability.LOW

        # Check for educational/government domains
        if domain.endswith(".edu") or domain.endswith(".gov"):
            return SourceReliability.HIGH

        # Check for organization domains
        if domain.endswith(".org"):
            return SourceReliability.MEDIUM

        return SourceReliability.UNKNOWN

    def _tier_to_score(self, tier: SourceReliability) -> float:
        """Convert reliability tier to numeric score."""
        return {
            SourceReliability.HIGH: 0.9,
            SourceReliability.MEDIUM: 0.65,
            SourceReliability.LOW: 0.3,
            SourceReliability.UNKNOWN: 0.5,
        }[tier]

    def _assess_freshness(self, pub_date: datetime | None) -> tuple[ContentFreshness, float]:
        """Assess content freshness from publication date."""
        if not pub_date:
            return ContentFreshness.UNKNOWN, 0.5

        age = datetime.now(UTC) - pub_date

        if age < timedelta(days=180):
            return ContentFreshness.CURRENT, 1.0
        if age < timedelta(days=540):
            return ContentFreshness.RECENT, 0.75
        if age < timedelta(days=1080):
            return ContentFreshness.DATED, 0.5
        return ContentFreshness.STALE, 0.25

    def _assess_relevance(self, source: dict, query: str) -> float:
        """Assess relevance of source to query using keyword matching."""
        content = source.get("content", "") + " " + source.get("title", "")
        content_lower = content.lower()

        # Extract query terms (filter out common stop words)
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "for",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "from",
            "with",
            "by",
            "of",
            "about",
        }
        query_terms = set(re.findall(r"\w+", query.lower())) - stop_words

        if not query_terms:
            return 0.5

        # Count matching terms
        matches = sum(1 for term in query_terms if term in content_lower)
        base_score = matches / len(query_terms)

        # Boost for exact phrase match
        if query.lower() in content_lower:
            base_score = min(base_score + 0.2, 1.0)

        # Boost for title match
        title_lower = source.get("title", "").lower()
        if any(term in title_lower for term in query_terms):
            base_score = min(base_score + 0.1, 1.0)

        return base_score

    def _assess_content_depth(self, source: dict) -> float:
        """Assess depth/comprehensiveness of content."""
        content = source.get("content", "")

        # Word count heuristic
        word_count = len(content.split())

        if word_count > 2000:
            base_score = 0.9
        elif word_count > 1000:
            base_score = 0.7
        elif word_count > 500:
            base_score = 0.5
        elif word_count > 200:
            base_score = 0.3
        else:
            base_score = 0.1

        # Boost for structured content indicators
        structured_indicators = [
            r"#{1,6}\s",  # Markdown headers
            r"<h[1-6]",  # HTML headers
            r"\d+\.\s",  # Numbered lists
            r"[-*]\s",  # Bullet lists
            r"```",  # Code blocks
            r"\|.*\|",  # Tables
        ]

        for pattern in structured_indicators:
            if re.search(pattern, content):
                base_score = min(base_score + 0.05, 1.0)

        return base_score

    def _check_rejection(self, score: SourceQualityScore) -> str | None:
        """Check if source should be rejected."""
        if score.composite_score < self.config.min_composite_score:
            return f"Composite score {score.composite_score:.2f} below threshold {self.config.min_composite_score}"

        if score.reliability_score < self.config.min_reliability_score:
            return f"Reliability score {score.reliability_score:.2f} below threshold"

        if score.relevance_score < self.config.min_relevance_score:
            return f"Relevance score {score.relevance_score:.2f} below threshold"

        if score.is_paywalled and not self.config.allow_paywalled:
            return "Source is paywalled"

        if self.config.blocked_domains and any(d in score.domain for d in self.config.blocked_domains):
            return f"Domain {score.domain} is blocked"

        # Check URL scheme if HTTPS required
        if self.config.require_https:
            parsed = urlparse(score.url)
            if parsed.scheme and parsed.scheme != "https":
                return "HTTPS required but source uses HTTP"

        return None

    def _extract_publication_date(self, source: dict) -> datetime | None:
        """Extract publication date from source metadata."""
        # Try various date fields
        date_fields = ["published_date", "date", "publish_date", "created_at", "pubDate", "datePublished"]

        for field in date_fields:
            if source.get(field):
                try:
                    if isinstance(source[field], datetime):
                        return source[field]
                    date_str = str(source[field])
                    # Handle ISO format
                    if "T" in date_str or "Z" in date_str:
                        return datetime.fromisoformat(date_str)
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%Y"]:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except (ValueError, AttributeError):
                    continue

        # Try extracting from content
        content = source.get("content", "")
        date_patterns = [
            r"(\d{4}-\d{2}-\d{2})",
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, content[:500])
            if match:
                try:
                    date_str = match.group(1)
                    if "-" in date_str:
                        return datetime.strptime(date_str, "%Y-%m-%d")
                except (ValueError, IndexError):
                    continue

        return None

    def _is_primary_source(self, source: dict, domain: str) -> bool:
        """Determine if source is a primary source."""
        primary_indicators = ["official", "documentation", "docs", "api", "reference", "spec", "specification"]
        title = source.get("title", "").lower()
        url = source.get("url", "").lower()

        # Check title and URL for indicators
        if any(ind in title or ind in url for ind in primary_indicators):
            return True

        # Check domain patterns
        return "docs." in domain or domain.startswith("api.")

    def _has_citations(self, source: dict) -> bool:
        """Check if source has its own citations/references."""
        content = source.get("content", "")
        citation_patterns = [
            r"\[\d+\]",  # [1], [2], etc.
            r"et al\.",  # Academic citation indicator
            r"\bReferences\b",
            r"\bBibliography\b",
            r"\bCitations?\b",
            r"doi:\s*\d+",  # DOI references
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in citation_patterns)
