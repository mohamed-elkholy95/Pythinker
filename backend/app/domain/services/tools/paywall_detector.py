"""Paywall Detection Service.

Detects paywalls and gated content in web pages to provide accurate
access status information for source attribution.

Supports detection via:
- Text pattern matching (subscription prompts, pricing)
- CSS class/ID detection (paywall, subscription-wall)
- Content truncation indicators
- Login/subscription CTAs

Usage:
    detector = PaywallDetector()
    result = detector.detect(html_content, text_content)

    if result.detected:
        print(f"Paywall detected: {result.confidence:.0%} confidence")
        print(f"Indicators: {result.indicators}")
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Text patterns indicating paywall or gated content
PAYWALL_TEXT_PATTERNS = [
    # Subscription prompts
    (r"subscribe\s+to\s+(read|continue|access|unlock)", 0.9),
    (r"(become|sign up as)\s+a\s+(premium\s+)?member", 0.85),
    (r"(premium|member|subscriber)\s+(only|exclusive)\s+content", 0.9),
    (r"this\s+(article|content|story)\s+is\s+for\s+(premium\s+)?members", 0.95),
    (r"create\s+(a\s+|an\s+)?(free\s+)?account\s+to\s+(read|continue|access)", 0.8),
    (r"sign\s+(in|up)\s+to\s+(read|continue|access|view)", 0.75),
    # Pricing indicators
    (r"\$\d+(\.\d{2})?\s*(/|per)\s*(month|year|mo|yr)", 0.85),
    (r"(starting\s+at|from|only)\s+\$\d+", 0.7),
    (r"(monthly|annual|yearly)\s+subscription", 0.75),
    (r"free\s+trial", 0.5),
    # Access limitations
    (r"you('ve|'re|\s+have)\s+(reached|hit)\s+(your\s+)?(free\s+)?(article|story)\s+limit", 0.95),
    (r"\d+\s+(free\s+)?(articles?|stories?)\s+(remaining|left)", 0.8),
    (r"(unlock|access)\s+unlimited\s+(articles?|content|stories?)", 0.85),
    (r"read\s+the\s+full\s+(article|story)", 0.6),
    # Medium-specific patterns
    (r"member-only\s+story", 0.95),
    (r"friend\s+link", 0.7),
    # Generic gating
    (r"continue\s+reading\s+with\s+a\s+subscription", 0.9),
    (r"(join|upgrade)\s+to\s+(read|continue|access)", 0.85),
    (r"exclusive\s+to\s+(subscribers|members)", 0.9),
]

# CSS classes/IDs that indicate paywall elements
PAYWALL_CSS_PATTERNS = [
    # Direct paywall indicators
    (r"paywall", 0.95),
    (r"subscription[-_]?wall", 0.95),
    (r"member[-_]?gate", 0.9),
    (r"premium[-_]?content[-_]?(gate|wall|block)", 0.9),
    (r"locked[-_]?content", 0.85),
    (r"article[-_]?truncated", 0.85),
    (r"metered[-_]?(paywall|content)", 0.9),
    # Login/subscription prompts
    (r"subscribe[-_]?(modal|popup|overlay|cta)", 0.8),
    (r"login[-_]?(required|prompt|gate)", 0.75),
    (r"(sign[-_]?up|register)[-_]?(modal|popup|overlay)", 0.7),
    # Content hiding
    (r"content[-_]?hidden", 0.8),
    (r"blur[-_]?overlay", 0.75),
    (r"fade[-_]?out[-_]?(overlay|gradient)", 0.7),
]

# HTML attributes to check for CSS patterns
CSS_ATTRIBUTES = ["class", "id", "data-testid", "data-component"]


@dataclass
class PaywallDetectionResult:
    """Result of paywall detection analysis."""

    detected: bool = False
    confidence: float = 0.0
    indicators: list[str] = field(default_factory=list)
    access_type: str = "full"  # full, partial, blocked

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "indicators": self.indicators,
            "access_type": self.access_type,
        }


class PaywallDetector:
    """Detects paywalls and gated content in web pages.

    Uses multiple detection strategies:
    1. Text pattern matching for subscription prompts
    2. CSS class/ID detection for paywall elements
    3. Content structure analysis for truncation
    4. Ratio analysis for visible vs hidden content
    """

    def __init__(
        self,
        text_patterns: list[tuple[str, float]] | None = None,
        css_patterns: list[tuple[str, float]] | None = None,
        confidence_threshold: float = 0.6,
    ):
        """Initialize the paywall detector.

        Args:
            text_patterns: Custom text patterns (pattern, weight) tuples
            css_patterns: Custom CSS patterns (pattern, weight) tuples
            confidence_threshold: Minimum confidence to flag as paywall
        """
        self.text_patterns = text_patterns or PAYWALL_TEXT_PATTERNS
        self.css_patterns = css_patterns or PAYWALL_CSS_PATTERNS
        self.confidence_threshold = confidence_threshold

        # Compile regex patterns for efficiency
        self._compiled_text = [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in self.text_patterns]
        self._compiled_css = [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in self.css_patterns]

    def detect(self, html: str, text: str | None = None, url: str | None = None) -> PaywallDetectionResult:
        """Detect if content is behind a paywall.

        Args:
            html: Raw HTML content
            text: Extracted text content (optional, for efficiency)
            url: Source URL (optional, for domain-specific rules)

        Returns:
            PaywallDetectionResult with detection details
        """
        indicators: list[str] = []
        weights: list[float] = []

        # Check text patterns
        search_text = text or html
        text_indicators, text_weights = self._check_text_patterns(search_text)
        indicators.extend(text_indicators)
        weights.extend(text_weights)

        # Check CSS patterns in HTML
        css_indicators, css_weights = self._check_css_patterns(html)
        indicators.extend(css_indicators)
        weights.extend(css_weights)

        # Check for content truncation
        truncation_score = self._check_truncation(html, text)
        if truncation_score > 0.5:
            indicators.append(f"content_truncation (score: {truncation_score:.2f})")
            weights.append(truncation_score * 0.8)

        # Check domain-specific patterns
        if url:
            domain_indicators, domain_weights = self._check_domain_patterns(url, html)
            indicators.extend(domain_indicators)
            weights.extend(domain_weights)

        # Calculate overall confidence
        if weights:
            # Use weighted average with diminishing returns for multiple indicators
            sorted_weights = sorted(weights, reverse=True)
            confidence = sorted_weights[0]
            for i, w in enumerate(sorted_weights[1:], 1):
                # Each additional indicator adds less (diminishing returns)
                confidence += w * (0.5**i)
            confidence = min(confidence, 0.99)  # Cap at 99%
        else:
            confidence = 0.0

        # Determine access type
        if confidence >= 0.8:
            access_type = "blocked"
        elif confidence >= self.confidence_threshold:
            access_type = "partial"
        else:
            access_type = "full"

        detected = confidence >= self.confidence_threshold

        if detected:
            logger.debug(f"Paywall detected with {confidence:.0%} confidence. Indicators: {indicators[:5]}")

        return PaywallDetectionResult(
            detected=detected,
            confidence=confidence,
            indicators=indicators,
            access_type=access_type,
        )

    def _check_text_patterns(self, text: str) -> tuple[list[str], list[float]]:
        """Check text for paywall indicator patterns."""
        indicators = []
        weights = []

        for pattern, weight in self._compiled_text:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0)[:50]  # Truncate for readability
                indicators.append(f"text_pattern: '{matched_text}'")
                weights.append(weight)

        return indicators, weights

    def _check_css_patterns(self, html: str) -> tuple[list[str], list[float]]:
        """Check HTML for paywall-related CSS classes/IDs."""
        indicators = []
        weights = []
        seen_patterns: set[str] = set()

        # Extract all class and id attributes
        attr_pattern = re.compile(r'(?:class|id|data-testid|data-component)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

        for match in attr_pattern.finditer(html):
            attr_value = match.group(1).lower()

            for pattern, weight in self._compiled_css:
                if pattern.search(attr_value):
                    pattern_key = pattern.pattern
                    if pattern_key not in seen_patterns:
                        seen_patterns.add(pattern_key)
                        indicators.append(f"css_pattern: '{attr_value[:30]}'")
                        weights.append(weight)

        return indicators, weights

    def _check_truncation(self, html: str, text: str | None) -> float:
        """Detect content truncation indicators.

        Returns a score from 0.0 to 1.0 indicating likelihood of truncation.
        """
        score = 0.0

        # Check for "read more" / "continue reading" patterns
        read_more_pattern = re.compile(r"(read|continue|view)\s+(more|full|the\s+rest)", re.IGNORECASE)
        if read_more_pattern.search(html):
            score += 0.3

        # Check for ellipsis followed by subscription CTA
        ellipsis_pattern = re.compile(r"\.{3,}.*?(subscribe|sign\s+up|member)", re.IGNORECASE | re.DOTALL)
        if ellipsis_pattern.search(html):
            score += 0.4

        # Check for gradient fade overlays (visual truncation)
        fade_pattern = re.compile(r"(gradient|fade|blur).*?(overlay|mask)", re.IGNORECASE)
        if fade_pattern.search(html):
            score += 0.3

        # Check text length vs typical article length
        if text:
            # Very short "articles" might be truncated
            word_count = len(text.split())
            if 50 < word_count < 300:
                # Suspicious length - might be preview only
                score += 0.2

        return min(score, 1.0)

    def _check_domain_patterns(self, url: str, html: str) -> tuple[list[str], list[float]]:
        """Check domain-specific paywall patterns."""
        indicators = []
        weights = []

        url_lower = url.lower()
        html_lower = html.lower()

        # Medium-specific patterns
        if ("medium.com" in url_lower or "towardsdatascience.com" in url_lower) and (
            "member-only" in html_lower or "metered-paywall" in html_lower
        ):
            indicators.append("medium_member_only")
            weights.append(0.95)

        # Substack patterns
        if "substack.com" in url_lower and ("paywall" in html_lower or "subscribe to read" in html_lower):
            indicators.append("substack_paywall")
            weights.append(0.9)

        # News site patterns
        news_domains = ["nytimes.com", "wsj.com", "washingtonpost.com", "ft.com"]
        if (
            any(domain in url_lower for domain in news_domains)
            and "subscribe" in html_lower
            and "article" in html_lower
        ):
            indicators.append("news_subscription_gate")
            weights.append(0.8)

        return indicators, weights

    def get_access_status_message(self, result: PaywallDetectionResult) -> str:
        """Generate a human-readable access status message.

        Args:
            result: Detection result

        Returns:
            Status message for inclusion in tool results
        """
        if not result.detected:
            return "Full content accessible"

        if result.access_type == "blocked":
            return (
                f"Content behind paywall ({result.confidence:.0%} confidence). "
                f"Only preview available. Indicators: {', '.join(result.indicators[:3])}"
            )
        return f"Partial content accessible ({result.confidence:.0%} paywall confidence). Some content may be gated."
