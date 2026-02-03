"""Content Hallucination Detection Service.

Detects potentially hallucinated content in agent outputs, particularly:
- Fabricated engagement metrics (claps, likes, views, shares)
- Made-up statistics without sources
- Specific dates/times without citation
- Prices and monetary values without verification

This is used by the CriticAgent to flag outputs that contain
high-risk patterns that should be verified or removed.

Usage:
    detector = ContentHallucinationDetector()
    result = detector.analyze(output_text, source_attributions)

    if result.has_high_risk_patterns:
        for issue in result.issues:
            print(f"Warning: {issue.description}")
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HallucinationRisk(str, Enum):
    """Risk level for potential hallucination."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HallucinationIssue:
    """A detected potential hallucination issue."""

    pattern_type: str
    matched_text: str
    description: str
    risk: HallucinationRisk
    suggestion: str
    line_context: str | None = None


@dataclass
class HallucinationAnalysisResult:
    """Result of hallucination analysis."""

    issues: list[HallucinationIssue] = field(default_factory=list)
    total_patterns_checked: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0

    @property
    def has_high_risk_patterns(self) -> bool:
        """Check if any high-risk patterns were found."""
        return self.high_risk_count > 0

    @property
    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return len(self.issues) > 0

    def get_summary(self) -> str:
        """Get a summary of detected issues."""
        if not self.issues:
            return "No hallucination risks detected"

        parts = []
        if self.high_risk_count > 0:
            parts.append(f"{self.high_risk_count} high-risk")
        if self.medium_risk_count > 0:
            parts.append(f"{self.medium_risk_count} medium-risk")

        return f"Detected {', '.join(parts)} potential hallucinations"


# High-risk patterns that frequently indicate hallucination
# Each pattern: (regex, pattern_type, risk, description, suggestion)
HIGH_RISK_PATTERNS = [
    # Engagement metrics (very commonly hallucinated)
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(claps?|applause)",
        "engagement_claps",
        HallucinationRisk.HIGH,
        "Clap count without source verification",
        "Remove or mark as '[Metric not verified]'",
    ),
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(likes?|hearts?)",
        "engagement_likes",
        HallucinationRisk.HIGH,
        "Like count without source verification",
        "Remove or mark as '[Metric not verified]'",
    ),
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(views?|reads?|impressions?)",
        "engagement_views",
        HallucinationRisk.HIGH,
        "View/read count without source verification",
        "Remove or mark as '[Metric not verified]'",
    ),
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(shares?|retweets?|reposts?)",
        "engagement_shares",
        HallucinationRisk.HIGH,
        "Share count without source verification",
        "Remove or mark as '[Metric not verified]'",
    ),
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(comments?|responses?|replies?)",
        "engagement_comments",
        HallucinationRisk.HIGH,
        "Comment count without source verification",
        "Remove or mark as '[Metric not verified]'",
    ),
    (
        r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(followers?|subscribers?)",
        "follower_count",
        HallucinationRisk.HIGH,
        "Follower/subscriber count without verification",
        "Remove or verify from source",
    ),
    # Read time (commonly fabricated for articles)
    (
        r"(\d+)\s*(min(ute)?s?|hour?s?)\s*(read|reading\s+time)",
        "read_time",
        HallucinationRisk.HIGH,
        "Read time estimate without source",
        "Remove or state '[Read time not verified]'",
    ),
    # Statistics without attribution
    (
        r"(on\s+)?average(,?\s+of)?\s+\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
        "unattributed_average",
        HallucinationRisk.MEDIUM,
        "Average statistic without source",
        "Add source citation or mark as inferred",
    ),
    (
        r"(median|mean)\s+(?:of\s+)?\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
        "unattributed_statistic",
        HallucinationRisk.MEDIUM,
        "Statistical value without source",
        "Add source citation or remove",
    ),
    (
        r"(\d+(?:\.\d+)?)\s*%\s*(increase|decrease|growth|decline|of)",
        "percentage_claim",
        HallucinationRisk.MEDIUM,
        "Percentage claim without citation",
        "Verify and cite source",
    ),
    # Specific dates without context
    (
        r"(on|since|as of)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        "specific_date",
        HallucinationRisk.MEDIUM,
        "Specific date without source verification",
        "Verify date accuracy from source",
    ),
    (
        r"(published|posted|written|updated)\s+(on\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
        "publication_date",
        HallucinationRisk.MEDIUM,
        "Publication date claim",
        "Verify from page metadata if possible",
    ),
    # Prices (commonly fabricated)
    (
        r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(USD|dollars?)?(?!\s*(/|per))",
        "specific_price",
        HallucinationRisk.MEDIUM,
        "Specific price without source",
        "Verify price from original source",
    ),
    # Rankings and ratings
    (
        r"#\s?(\d+)\s+(in|on|best|top)",
        "ranking_claim",
        HallucinationRisk.MEDIUM,
        "Ranking claim without verification",
        "Verify ranking from authoritative source",
    ),
    (
        r"(\d(?:\.\d)?)\s*/\s*5\s*(stars?|rating)",
        "rating_claim",
        HallucinationRisk.MEDIUM,
        "Rating without source verification",
        "Verify rating from original source",
    ),
    # Quotes without clear attribution
    (
        r'[""]([^""]{50,})[""](?!\s*[-—]\s*[A-Z])',
        "unattributed_quote",
        HallucinationRisk.MEDIUM,
        "Long quote without clear attribution",
        "Add attribution or verify quote accuracy",
    ),
]

# Patterns that suggest proper attribution (reduce risk score)
ATTRIBUTION_PATTERNS = [
    r"according to",
    r"(the\s+)?(article|source|page|author)\s+(states?|says?|mentions?|reports?)",
    r"(as\s+)?(stated|reported|mentioned|noted)\s+(in|by|on)",
    r"\[source\]",
    r"\[citation\]",
    r"based on (the\s+)?(visible|available|accessible)",
]


class ContentHallucinationDetector:
    """Detects potentially hallucinated content in agent outputs.

    Analyzes text for patterns that commonly indicate fabrication:
    - Engagement metrics without visible source data
    - Statistics without citations
    - Specific numbers that require verification

    Works in conjunction with SourceAttribution to identify
    claims that lack proper source backing.
    """

    def __init__(self, patterns: list[tuple] | None = None, check_attribution: bool = True):
        """Initialize the hallucination detector.

        Args:
            patterns: Custom detection patterns
            check_attribution: Whether to check for attribution markers
        """
        self.patterns = patterns or HIGH_RISK_PATTERNS
        self.check_attribution = check_attribution

        # Compile patterns
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE | re.MULTILINE), *rest) for pattern, *rest in self.patterns
        ]

        # Compile attribution patterns
        self._attribution_patterns = [re.compile(p, re.IGNORECASE) for p in ATTRIBUTION_PATTERNS]

    def analyze(self, text: str, verified_claims: set[str] | None = None) -> HallucinationAnalysisResult:
        """Analyze text for potential hallucinations.

        Args:
            text: The text to analyze
            verified_claims: Set of claims known to be verified (optional)

        Returns:
            HallucinationAnalysisResult with detected issues
        """
        result = HallucinationAnalysisResult()
        verified = verified_claims or set()

        # Track matched positions to avoid duplicate issues
        matched_positions: set[tuple] = set()

        for compiled, pattern_type, risk, description, suggestion in self._compiled_patterns:
            result.total_patterns_checked += 1

            for match in compiled.finditer(text):
                # Check if this position was already flagged
                pos_key = (match.start(), match.end())
                if pos_key in matched_positions:
                    continue
                matched_positions.add(pos_key)

                matched_text = match.group(0)

                # Skip if this claim is in verified set
                if self._is_verified(matched_text, verified):
                    continue

                # Check if there's nearby attribution
                effective_risk = risk
                if self.check_attribution and self._has_nearby_attribution(
                    text,
                    match.start(),
                    match.end(),
                ):
                    # Reduce risk if properly attributed
                    if risk == HallucinationRisk.HIGH:
                        effective_risk = HallucinationRisk.MEDIUM
                    elif risk == HallucinationRisk.MEDIUM:
                        effective_risk = HallucinationRisk.LOW
                    elif risk == HallucinationRisk.CRITICAL:
                        effective_risk = HallucinationRisk.HIGH

                # Skip low risk items
                if effective_risk == HallucinationRisk.LOW:
                    continue

                # Get line context
                line_context = self._get_line_context(text, match.start())

                issue = HallucinationIssue(
                    pattern_type=pattern_type,
                    matched_text=matched_text[:100],  # Truncate long matches
                    description=description,
                    risk=effective_risk,
                    suggestion=suggestion,
                    line_context=line_context,
                )
                result.issues.append(issue)

                if effective_risk in (HallucinationRisk.HIGH, HallucinationRisk.CRITICAL):
                    result.high_risk_count += 1
                elif effective_risk == HallucinationRisk.MEDIUM:
                    result.medium_risk_count += 1

        if result.issues:
            logger.debug(
                f"Hallucination analysis: {len(result.issues)} issues found ({result.high_risk_count} high-risk)"
            )

        return result

    def _is_verified(self, matched_text: str, verified: set[str]) -> bool:
        """Check if the matched text corresponds to a verified claim."""
        # Normalize for comparison
        normalized = matched_text.lower().strip()

        return any(normalized in verified_claim.lower() for verified_claim in verified)

    def _has_nearby_attribution(self, text: str, start: int, end: int, window: int = 200) -> bool:
        """Check if there's attribution near the matched text.

        Args:
            text: Full text
            start: Match start position
            end: Match end position
            window: Characters to check before/after

        Returns:
            True if attribution pattern found nearby
        """
        # Get context window
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        context = text[context_start:context_end]

        # Check for attribution patterns
        return any(pattern.search(context) for pattern in self._attribution_patterns)

    def _get_line_context(self, text: str, position: int, context_chars: int = 100) -> str:
        """Get the line containing the position with some context."""
        start = max(0, position - context_chars // 2)
        end = min(len(text), position + context_chars // 2)

        context = text[start:end]

        # Clean up and truncate
        context = context.replace("\n", " ").strip()
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    def get_risk_summary(self, result: HallucinationAnalysisResult) -> str:
        """Generate a summary of risks for inclusion in output validation.

        Args:
            result: Analysis result

        Returns:
            Human-readable summary string
        """
        if not result.issues:
            return ""

        lines = ["Potential hallucination risks detected:"]

        # Group by risk level
        high_risk = [i for i in result.issues if i.risk in (HallucinationRisk.HIGH, HallucinationRisk.CRITICAL)]
        medium_risk = [i for i in result.issues if i.risk == HallucinationRisk.MEDIUM]

        if high_risk:
            lines.append(f"\nHigh Risk ({len(high_risk)}):")
            for issue in high_risk[:5]:  # Limit to 5
                lines.append(f"  - {issue.description}: '{issue.matched_text[:50]}'")
                lines.append(f"    Suggestion: {issue.suggestion}")

        if medium_risk:
            lines.append(f"\nMedium Risk ({len(medium_risk)}):")
            for issue in medium_risk[:3]:  # Limit to 3
                lines.append(f"  - {issue.description}: '{issue.matched_text[:50]}'")

        return "\n".join(lines)

    def extract_quantitative_claims(self, text: str) -> list[str]:
        """Extract all quantitative claims from text for verification.

        Useful for the CriticAgent to get a list of claims that
        should be cross-referenced with source attributions.

        Args:
            text: Text to extract claims from

        Returns:
            List of quantitative claim strings
        """
        claims = []

        # Patterns for quantitative claims
        claim_patterns = [
            r"(\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?[KkMm]?)\s*(?:claps?|likes?|views?|shares?|comments?|followers?)",
            r"(\d+)\s*(?:min(?:ute)?s?|hours?)\s*read",
            r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
            r"(\d+(?:\.\d+)?)\s*%",
            r"(\d+(?:\.\d+)?)\s*/\s*5\s*(?:stars?|rating)",
            r"#(\d+)\s+(?:in|on|best|top)",
        ]

        for pattern in claim_patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            for match in compiled.finditer(text):
                claims.append(match.group(0))

        return list(set(claims))  # Remove duplicates
