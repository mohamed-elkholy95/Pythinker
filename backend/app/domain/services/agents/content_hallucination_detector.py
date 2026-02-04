"""Content Hallucination Detection Service.

Detects potentially hallucinated content in agent outputs, particularly:
- Fabricated engagement metrics (claps, likes, views, shares)
- Made-up statistics without sources
- Specific dates/times without citation
- Prices and monetary values without verification
- Cross-claim contradictions within text

This is used by the CriticAgent to flag outputs that contain
high-risk patterns that should be verified or removed.

Usage:
    detector = ContentHallucinationDetector()
    result = detector.analyze(output_text, source_attributions)

    if result.has_high_risk_patterns:
        for issue in result.issues:
            print(f"Warning: {issue.description}")

    # Contradiction detection
    contradictions = detector.detect_contradictions(output_text)
    for c in contradictions:
        print(f"Contradiction: {c.claim1} vs {c.claim2}")
"""

import logging
import re
from collections import defaultdict
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


@dataclass
class Claim:
    """A claim extracted from text for contradiction analysis."""

    text: str
    entities: list[str]
    numeric_value: float | None = None
    metric: str | None = None
    polarity: float | None = None  # -1 to 1, negative=bad, positive=good
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class ContradictionResult:
    """A detected contradiction between two claims."""

    claim1: str
    claim2: str
    entity: str
    confidence: float  # 0 to 1
    contradiction_type: str = "general"


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

    # -------------------------------------------------------------------------
    # Contradiction Detection
    # -------------------------------------------------------------------------

    def detect_contradictions(self, text: str) -> list[ContradictionResult]:
        """Detect internally contradictory claims in text.

        Examples:
        - "The API returns JSON" ... "The response is XML"
        - "Performance improved 20%" ... "Speed decreased significantly"
        - "Supports Python 3.8+" ... "Requires Python 3.10 minimum"

        Args:
            text: The text to analyze for contradictions

        Returns:
            List of detected contradictions with source locations
        """
        contradictions: list[ContradictionResult] = []

        # Extract claim pairs with entities
        claims = self._extract_claims_with_entities(text)

        # Track which claim pairs we've already checked
        checked_pairs: set[tuple[int, int]] = set()

        # Group claims by entity/subject (with fuzzy matching)
        entity_claims: dict[str, list[Claim]] = defaultdict(list)
        for claim in claims:
            for entity in claim.entities:
                # Add to exact entity group
                entity_claims[entity.lower()].append(claim)
                # Also add to base entity group (e.g., "python 3.8" -> "python")
                base_entity = entity.lower().split()[0] if " " in entity else None
                if base_entity and base_entity != entity.lower():
                    entity_claims[base_entity].append(claim)

        # Check for contradictions within entity groups
        for entity, entity_claim_list in entity_claims.items():
            if len(entity_claim_list) < 2:
                continue

            for i, claim1 in enumerate(entity_claim_list):
                for claim2 in entity_claim_list[i + 1 :]:
                    # Create a unique key for this claim pair
                    pair_key = (id(claim1), id(claim2))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    if self._claims_contradict(claim1, claim2):
                        contradictions.append(
                            ContradictionResult(
                                claim1=claim1.text,
                                claim2=claim2.text,
                                entity=entity,
                                confidence=self._contradiction_confidence(claim1, claim2),
                                contradiction_type=self._get_contradiction_type(claim1, claim2),
                            )
                        )

        # Also check for format/version contradictions across ALL claims
        # regardless of shared entities (these are often implicit contradictions)
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i + 1 :]:
                pair_key = (id(claim1), id(claim2))
                if pair_key in checked_pairs:
                    continue

                # Check for format contradiction
                if self._check_format_contradiction(claim1.text, claim2.text):
                    checked_pairs.add(pair_key)
                    # Find common entity or use a generic one
                    common_entity = self._find_common_context(claim1, claim2)
                    contradictions.append(
                        ContradictionResult(
                            claim1=claim1.text,
                            claim2=claim2.text,
                            entity=common_entity,
                            confidence=0.75,
                            contradiction_type="format",
                        )
                    )
                    continue

                # Check for version contradiction
                if self._check_version_contradiction(claim1.text, claim2.text):
                    checked_pairs.add(pair_key)
                    common_entity = self._find_common_context(claim1, claim2)
                    contradictions.append(
                        ContradictionResult(
                            claim1=claim1.text,
                            claim2=claim2.text,
                            entity=common_entity,
                            confidence=0.8,
                            contradiction_type="version",
                        )
                    )

        if contradictions:
            logger.debug(f"Contradiction detection: {len(contradictions)} contradictions found")

        return contradictions

    def _find_common_context(self, claim1: Claim, claim2: Claim) -> str:
        """Find a common context or entity between two claims.

        Args:
            claim1: First claim
            claim2: Second claim

        Returns:
            A common entity or a descriptive context string
        """
        # First try to find shared entities
        shared = set(claim1.entities) & set(claim2.entities)
        if shared:
            return next(iter(shared))

        # Look for semantic similarity in entity types
        entity_groups = [
            ({"api", "endpoint", "response", "request", "payload"}, "api"),
            ({"performance", "speed", "latency", "throughput", "query", "queries"}, "performance"),
            ({"file", "directory", "path"}, "filesystem"),
            ({"database", "mongodb", "postgresql", "mysql", "redis", "index", "indexing"}, "database"),
        ]

        for group, label in entity_groups:
            if (group & set(claim1.entities)) and (group & set(claim2.entities)):
                return label

        # Default to a generic context
        if claim1.entities:
            return claim1.entities[0]
        if claim2.entities:
            return claim2.entities[0]
        return "output"

    def _extract_claims_with_entities(self, text: str) -> list[Claim]:
        """Extract claims from text with associated entities.

        A claim is a sentence or clause that makes an assertion about
        something identifiable (entity).

        Args:
            text: Text to extract claims from

        Returns:
            List of Claim objects with entities, metrics, and polarity
        """
        claims: list[Claim] = []

        # Split into sentences (simple approach)
        sentence_pattern = re.compile(r"[.!?]+\s+|\n+")
        sentences = sentence_pattern.split(text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short fragments
                continue

            # Extract entities (nouns/technical terms)
            entities = self._extract_entities(sentence)
            if not entities:
                continue

            # Extract numeric value and metric if present
            numeric_value, metric = self._extract_numeric_metric(sentence)

            # Determine polarity (sentiment direction)
            polarity = self._extract_polarity(sentence)

            # Find position in original text
            start_pos = text.find(sentence)
            end_pos = start_pos + len(sentence) if start_pos >= 0 else 0

            claims.append(
                Claim(
                    text=sentence,
                    entities=entities,
                    numeric_value=numeric_value,
                    metric=metric,
                    polarity=polarity,
                    start_pos=start_pos,
                    end_pos=end_pos,
                )
            )

        return claims

    def _extract_entities(self, text: str) -> list[str]:
        """Extract entity names from text.

        Identifies technical terms, proper nouns, and key subjects.

        Args:
            text: Text to extract entities from

        Returns:
            List of entity strings (lowercase)
        """
        entities: list[str] = []

        # Technical terms and identifiers
        tech_patterns = [
            # Programming languages and versions
            r"\b(Python|Java|JavaScript|TypeScript|Ruby|Go|Rust|C\+\+|C#|PHP|Swift|Kotlin)"
            r"(?:\s+(\d+(?:\.\d+)*))?",
            # Frameworks and libraries
            r"\b(React|Vue|Angular|Django|Flask|FastAPI|Express|Spring|Rails|Laravel)\b",
            # Data formats
            r"\b(JSON|XML|YAML|CSV|HTML|Markdown)\b",
            # Protocols and standards
            r"\b(REST|GraphQL|gRPC|HTTP|HTTPS|WebSocket|TCP|UDP)\b",
            # Databases
            r"\b(MongoDB|PostgreSQL|MySQL|Redis|Elasticsearch|SQLite|Oracle)\b",
            # Cloud/Infrastructure
            r"\b(AWS|Azure|GCP|Docker|Kubernetes|Linux|Windows|macOS)\b",
            # API-related terms
            r"\b(API|endpoint|response|request|payload|header)\b",
            # Performance metrics
            r"\b(performance|speed|latency|throughput|memory|CPU|bandwidth)\b",
            # Database-related terms
            r"\b(query|queries|database|index|indexing)\b",
            # General technical nouns
            r"\b(file|directory|path|server|client|application|system|framework)\b",
        ]

        for pattern in tech_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entity = match.group(0).lower()
                if entity not in entities:
                    entities.append(entity)

        # Also extract quoted terms as potential entities
        quoted_pattern = re.compile(r'["\']([^"\']+)["\']')
        for match in quoted_pattern.finditer(text):
            quoted = match.group(1).lower()
            if len(quoted) > 2 and quoted not in entities:
                entities.append(quoted)

        return entities

    def _extract_numeric_metric(self, text: str) -> tuple[float | None, str | None]:
        """Extract numeric value and associated metric from text.

        Args:
            text: Text to extract from

        Returns:
            Tuple of (numeric_value, metric_name) or (None, None)
        """
        # Pattern for numeric values with metrics
        patterns = [
            # Percentages
            (r"(\d+(?:\.\d+)?)\s*%\s*(increase|decrease|improvement|reduction|growth|decline)?", "percentage"),
            # Time durations
            (r"(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?|ms|milliseconds?)", "duration"),
            # Sizes
            (r"(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB|bytes?)", "size"),
            # Versions
            (r"(?:version\s+)?(\d+(?:\.\d+)+)", "version"),
            # Generic numbers with units
            (r"(\d+(?:\.\d+)?)\s*(times?|x|fold)", "multiplier"),
        ]

        for pattern, metric_type in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(",", ""))
                    # Include qualifier in metric if present
                    qualifier = match.group(2) if len(match.groups()) > 1 and match.group(2) else ""
                    metric = f"{metric_type}_{qualifier}".strip("_").lower()
                    return value, metric
                except (ValueError, IndexError):
                    continue

        return None, None

    def _extract_polarity(self, text: str) -> float | None:
        """Extract sentiment polarity from text.

        Args:
            text: Text to analyze

        Returns:
            Float from -1 (negative) to 1 (positive), or None if neutral/unclear
        """
        text_lower = text.lower()

        # Positive indicators
        positive_words = [
            "improve",
            "improved",
            "improvement",
            "increase",
            "increased",
            "better",
            "faster",
            "enhanced",
            "optimized",
            "efficient",
            "supports",
            "support",
            "includes",
            "include",
            "enables",
            "enable",
            "success",
            "successful",
            "advantage",
            "benefit",
            "growth",
            "gain",
        ]

        # Negative indicators
        negative_words = [
            "decrease",
            "decreased",
            "decline",
            "declined",
            "slower",
            "worse",
            "degraded",
            "reduced",
            "reduction",
            "fail",
            "failed",
            "failure",
            "error",
            "bug",
            "issue",
            "problem",
            "loss",
            "disadvantage",
            "limitation",
            "does not support",
            "doesn't support",
            "not support",
            "does not include",
            "doesn't include",
            "not include",
            "cannot",
            "can't",
        ]

        positive_score = sum(1 for word in positive_words if word in text_lower)
        negative_score = sum(1 for word in negative_words if word in text_lower)

        # Check for negation that flips meaning
        negation_patterns = [r"\bnot\b", r"\bno\b", r"\bnever\b", r"\bwithout\b", r"\bdoesn't\b", r"\bdon't\b"]
        has_negation = any(re.search(p, text_lower) for p in negation_patterns)

        if positive_score == 0 and negative_score == 0:
            return None

        total = positive_score + negative_score
        polarity = (positive_score - negative_score) / total

        # Flip polarity if negation is present (simple heuristic)
        if has_negation and abs(polarity) > 0.3:
            polarity = -polarity * 0.5  # Reduce confidence when flipping

        return polarity

    def _claims_contradict(self, claim1: Claim, claim2: Claim) -> bool:
        """Check if two claims contradict each other.

        Args:
            claim1: First claim
            claim2: Second claim

        Returns:
            True if claims contradict each other
        """
        # Numeric contradiction: different numbers for same metric
        if (
            claim1.numeric_value is not None
            and claim2.numeric_value is not None
            and claim1.metric == claim2.metric
            and claim1.metric is not None
        ):
            # Avoid division by zero
            min_val = min(claim1.numeric_value, claim2.numeric_value)
            max_val = max(claim1.numeric_value, claim2.numeric_value)
            if min_val > 0:
                ratio = max_val / min_val
                if ratio > 1.5:  # 50% difference threshold
                    return True

        # Polarity contradiction: opposite sentiments about same entity
        if (
            claim1.polarity is not None
            and claim2.polarity is not None
            and claim1.polarity * claim2.polarity < 0  # Opposite signs
            and abs(claim1.polarity) > 0.3
            and abs(claim2.polarity) > 0.3
        ):
            return True

        # Negation contradiction: "supports X" vs "does not support X"
        # We extract the object from one claim and check if the other negates it
        verb_patterns = [
            ("support", r"supports?\s+(\w+)"),
            ("require", r"requires?\s+(\w+)"),
            ("include", r"includes?\s+(\w+)"),
            ("return", r"returns?\s+(\w+)"),
            ("use", r"uses?\s+(\w+)"),
            ("provide", r"provides?\s+(\w+)"),
            ("enable", r"enables?\s+(\w+)"),
            ("allow", r"allows?\s+(\w+)"),
        ]

        for verb, pattern in verb_patterns:
            # Check claim1 positive, claim2 negative
            match1 = re.search(pattern, claim1.text, re.I)
            if match1:
                obj = match1.group(1)
                neg_pattern = rf"(?:does\s+)?not\s+{verb}\s+{re.escape(obj)}"
                if re.search(neg_pattern, claim2.text, re.I):
                    return True

            # Check claim1 negative, claim2 positive
            match2 = re.search(pattern, claim2.text, re.I)
            if match2:
                obj = match2.group(1)
                neg_pattern = rf"(?:does\s+)?not\s+{verb}\s+{re.escape(obj)}"
                if re.search(neg_pattern, claim1.text, re.I):
                    return True

        # Format/type contradictions: "returns JSON" vs "returns XML"
        if self._check_format_contradiction(claim1.text, claim2.text):
            return True

        # Version contradictions: "requires Python 3.8" vs "requires Python 3.10"
        return self._check_version_contradiction(claim1.text, claim2.text)

    def _check_format_contradiction(self, text1: str, text2: str) -> bool:
        """Check if texts claim different formats for same context.

        Args:
            text1: First text
            text2: Second text

        Returns:
            True if format contradiction detected
        """
        # Data format groups that are mutually exclusive
        format_groups = [
            {"json", "xml", "yaml", "csv", "html"},
            {"rest", "graphql", "grpc", "soap"},
            {"sync", "async", "synchronous", "asynchronous"},
            {"get", "post", "put", "delete", "patch"},
        ]

        text1_lower = text1.lower()
        text2_lower = text2.lower()

        for format_group in format_groups:
            formats_in_text1 = {fmt for fmt in format_group if re.search(rf"\b{fmt}\b", text1_lower)}
            formats_in_text2 = {fmt for fmt in format_group if re.search(rf"\b{fmt}\b", text2_lower)}

            # If both texts mention formats from same group but different formats
            if formats_in_text1 and formats_in_text2 and formats_in_text1 != formats_in_text2:
                # Check they're in similar context (returns, uses, requires, is, in, as, etc.)
                context_patterns = [
                    r"returns?\b",
                    r"uses?\b",
                    r"requires?\b",
                    r"\bin\b",
                    r"\bas\b",
                    r"\bis\b",
                    r"structured\b",
                    r"format",
                    r"response",
                    r"data",
                    r"endpoint",
                    r"service",
                    r"quer",  # query/queries
                ]
                # If either text has a context pattern, it's likely a real claim
                has_context1 = any(re.search(pattern, text1_lower) for pattern in context_patterns)
                has_context2 = any(re.search(pattern, text2_lower) for pattern in context_patterns)
                if has_context1 and has_context2:
                    return True

        return False

    def _check_version_contradiction(self, text1: str, text2: str) -> bool:
        """Check if texts claim different version requirements.

        Args:
            text1: First text
            text2: Second text

        Returns:
            True if version contradiction detected
        """
        # Pattern for version requirements
        version_pattern = re.compile(
            r"(?:requires?|supports?|needs?|minimum|compatible with)\s+"
            r"(?:Python|Java|Node(?:\.js)?|Ruby|Go|PHP|version)\s*"
            r"(\d+(?:\.\d+)*)\+?",
            re.IGNORECASE,
        )

        match1 = version_pattern.search(text1)
        match2 = version_pattern.search(text2)

        if match1 and match2:
            version1 = match1.group(1)
            version2 = match2.group(1)

            if version1 != version2:
                # Parse versions to compare
                try:
                    v1_parts = [int(x) for x in version1.split(".")]
                    v2_parts = [int(x) for x in version2.split(".")]

                    # Pad to same length
                    max_len = max(len(v1_parts), len(v2_parts))
                    v1_parts.extend([0] * (max_len - len(v1_parts)))
                    v2_parts.extend([0] * (max_len - len(v2_parts)))

                    # Check if versions are significantly different
                    if v1_parts != v2_parts:
                        return True
                except ValueError:
                    # If parsing fails, just compare strings
                    return version1 != version2

        return False

    def _contradiction_confidence(self, claim1: Claim, claim2: Claim) -> float:
        """Calculate confidence score for a contradiction.

        Args:
            claim1: First claim
            claim2: Second claim

        Returns:
            Confidence score from 0 to 1
        """
        confidence = 0.5  # Base confidence

        # Higher confidence for numeric contradictions
        if claim1.numeric_value is not None and claim2.numeric_value is not None and claim1.metric == claim2.metric:
            min_val = min(claim1.numeric_value, claim2.numeric_value)
            max_val = max(claim1.numeric_value, claim2.numeric_value)
            if min_val > 0:
                ratio = max_val / min_val
                # Higher ratio = higher confidence
                confidence = min(0.95, 0.5 + (ratio - 1) * 0.1)

        # Higher confidence for strong polarity contradictions
        if claim1.polarity is not None and claim2.polarity is not None and claim1.polarity * claim2.polarity < 0:
            polarity_diff = abs(claim1.polarity - claim2.polarity)
            confidence = max(confidence, 0.4 + polarity_diff * 0.3)

        # Higher confidence for negation patterns
        negation_found = any(
            pattern in claim1.text.lower() or pattern in claim2.text.lower()
            for pattern in ["does not", "doesn't", "not support", "not include", "not require"]
        )
        if negation_found:
            confidence = max(confidence, 0.7)

        # Higher confidence for more shared entities
        shared_entities = set(claim1.entities) & set(claim2.entities)
        if len(shared_entities) > 1:
            confidence = min(0.95, confidence + 0.1 * len(shared_entities))

        return min(confidence, 1.0)

    def _get_contradiction_type(self, claim1: Claim, claim2: Claim) -> str:
        """Determine the type of contradiction.

        Args:
            claim1: First claim
            claim2: Second claim

        Returns:
            String describing the contradiction type
        """
        # Check numeric
        if claim1.numeric_value is not None and claim2.numeric_value is not None and claim1.metric == claim2.metric:
            return "numeric"

        # Check polarity
        if claim1.polarity is not None and claim2.polarity is not None and claim1.polarity * claim2.polarity < 0:
            return "polarity"

        # Check negation
        negation_in_1 = any(
            pattern in claim1.text.lower() for pattern in ["does not", "doesn't", "not support", "not include"]
        )
        negation_in_2 = any(
            pattern in claim2.text.lower() for pattern in ["does not", "doesn't", "not support", "not include"]
        )
        if negation_in_1 != negation_in_2:
            return "negation"

        # Check format
        if self._check_format_contradiction(claim1.text, claim2.text):
            return "format"

        # Check version
        if self._check_version_contradiction(claim1.text, claim2.text):
            return "version"

        return "general"
