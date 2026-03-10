"""Input/Output Guardrails for AI Agent Safety

Implements layered guardrails to:
1. Screen user inputs for problematic content (prompt injection, ambiguity)
2. Filter agent outputs for quality and safety (factual consistency, relevance)

Research shows layered guardrails prevent 80%+ of problematic outputs.

Architecture:
- Pre-processing: InputGuardrails filter requests before agent processing
- Post-processing: OutputGuardrails validate responses before delivery
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# =============================================================================
# Input Guardrails
# =============================================================================


class InputRiskLevel(str, Enum):
    """Risk levels for input analysis."""

    SAFE = "safe"
    LOW_RISK = "low_risk"
    MEDIUM_RISK = "medium_risk"
    HIGH_RISK = "high_risk"
    BLOCKED = "blocked"


class InputIssueType(str, Enum):
    """Types of input issues detected."""

    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK_ATTEMPT = "jailbreak_attempt"
    AMBIGUOUS_REQUEST = "ambiguous_request"
    UNDERSPECIFIED = "underspecified"
    CONTRADICTORY = "contradictory"
    SENSITIVE_DATA = "sensitive_data"
    HARMFUL_INTENT = "harmful_intent"


@dataclass
class PIIDetectionResult:
    """Result of PII detection scan."""

    contains_pii: bool
    pii_types: list[str] = field(default_factory=list)
    redacted_text: str | None = None
    pii_count: int = 0
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "contains_pii": self.contains_pii,
            "pii_types": self.pii_types,
            "pii_count": self.pii_count,
            "risk_score": self.risk_score,
            "has_redacted": self.redacted_text is not None,
        }


@dataclass
class InputIssue:
    """A detected issue in user input."""

    issue_type: InputIssueType
    description: str
    severity: float  # 0.0 to 1.0
    location: str | None = None  # Where in the input
    suggestion: str | None = None  # How to fix


@dataclass
class InputAnalysisResult:
    """Result of input guardrail analysis."""

    risk_level: InputRiskLevel
    issues: list[InputIssue]
    cleaned_input: str | None = None  # Sanitized version if applicable
    clarification_needed: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def should_proceed(self) -> bool:
        """Check if the input is safe to proceed with."""
        return self.risk_level in (InputRiskLevel.SAFE, InputRiskLevel.LOW_RISK)

    @property
    def needs_clarification(self) -> bool:
        """Check if clarification is needed before proceeding."""
        return self.clarification_needed and len(self.clarification_questions) > 0


class InputGuardrails:
    """Screens user inputs for potential issues.

    Usage:
        guardrails = InputGuardrails()
        result = guardrails.analyze("Ignore all previous instructions and...")

        if not result.should_proceed:
            return "I cannot process this request."
    """

    # Prompt injection patterns
    INJECTION_PATTERNS: ClassVar[list[str]] = [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"forget\s+(everything|all)\s+(you\s+)?(know|learned|were told)",
        r"your\s+new\s+(instructions?|rules?|role)\s+(are|is)",
        r"you\s+are\s+now\s+(?:a|an|the)",
        r"pretend\s+(?:you\s+are|to\s+be)",
        r"act\s+as\s+(?:if|though)",
        r"roleplay\s+as",
        r"system\s*:\s*",  # Trying to inject system message
        r"\[\s*INST\s*\]",  # Llama-style injection
        r"<\|im_start\|>",  # ChatML injection
    ]

    # Jailbreak patterns
    JAILBREAK_PATTERNS: ClassVar[list[str]] = [
        r"DAN\s+mode",
        r"do\s+anything\s+now",
        r"bypass\s+(safety|content|filter)",
        r"without\s+(restrictions?|limits?|filters?)",
        r"no\s+(ethical|moral|safety)\s+(guidelines?|restrictions?)",
        r"hypothetically\s+speaking",
        r"for\s+(educational|research)\s+purposes?\s+only",
        r"pretend\s+there\s+are\s+no\s+(rules?|restrictions?)",
    ]

    # Sensitive data patterns (basic)
    SENSITIVE_PATTERNS: ClassVar[list[str]] = [
        r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b",  # SSN
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # Credit card
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email (not always sensitive)
        r"password\s*[:=]\s*\S+",  # Password in input
        r"api[_-]?key\s*[:=]\s*\S+",  # API key
        r"secret\s*[:=]\s*\S+",  # Secret
    ]

    # Enhanced PII patterns (Phase 4 Enhancement)
    PII_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "ssn"),
        (r"\b\d{9}\b", "ssn_no_dash"),  # SSN without dashes
        # Passport numbers (various formats)
        (r"\b[A-Z]{1,2}\d{6,9}\b", "passport"),
        # Credit card patterns (Visa, MC, Amex, etc.)
        (r"\b4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "credit_card_visa"),
        (r"\b5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "credit_card_mc"),
        (r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b", "credit_card_amex"),
        # Password values in common formats
        (r'(?:password|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]+)["\']?', "password_value"),
        (r'(?:pass|pw)\s*[:=]\s*["\']?([^"\'\s]+)["\']?', "password_value"),
        # Bearer tokens and API keys
        (r"(?:bearer|token|auth)\s+[A-Za-z0-9\-._~+/]+=*", "bearer_token"),
        (r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([A-Za-z0-9\-._~+/]{20,})["\']?', "api_key"),
        (r"sk-[A-Za-z0-9]{20,}", "openai_key"),  # OpenAI API keys
        (r"sk_live_[A-Za-z0-9]{20,}", "stripe_key"),  # Stripe live keys
        # AWS credentials
        (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
        (r'(?:aws_secret|secret_access)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?', "aws_secret"),
        # Private keys
        (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "private_key"),
        (r"-----BEGIN\s+PGP\s+PRIVATE\s+KEY-----", "pgp_private_key"),
        # Phone numbers (US format)
        (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone_us"),
        (r"\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone_us_intl"),
        # Bank account numbers (basic pattern)
        (r"\b\d{8,17}\b", "potential_account_number"),
        # IPv4 addresses (may indicate sensitive config)
        (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "ip_address"),
    ]

    # Ambiguity indicators
    AMBIGUITY_INDICATORS: ClassVar[list[str]] = [
        "something",
        "anything",
        "whatever",
        "somehow",
        "it",
        "this",
        "that",
        "stuff",
        "things",
    ]

    # PII type risk scores (higher = more sensitive)
    PII_RISK_SCORES: ClassVar[dict[str, float]] = {
        "ssn": 1.0,
        "ssn_no_dash": 0.8,
        "passport": 0.9,
        "credit_card_visa": 1.0,
        "credit_card_mc": 1.0,
        "credit_card_amex": 1.0,
        "password_value": 1.0,
        "bearer_token": 0.9,
        "api_key": 0.9,
        "openai_key": 0.95,
        "stripe_key": 0.95,
        "aws_access_key": 0.95,
        "aws_secret": 1.0,
        "private_key": 1.0,
        "pgp_private_key": 1.0,
        "phone_us": 0.4,
        "phone_us_intl": 0.4,
        "potential_account_number": 0.3,
        "ip_address": 0.2,
    }

    def __init__(
        self,
        strict_mode: bool = False,
        log_issues: bool = True,
        enable_pii_detection: bool = True,
    ):
        """Initialize input guardrails.

        Args:
            strict_mode: If True, blocks on medium risk (not just high)
            log_issues: If True, logs all detected issues
            enable_pii_detection: If True, enables enhanced PII detection
        """
        self.strict_mode = strict_mode
        self.log_issues = log_issues
        self.enable_pii_detection = enable_pii_detection

        # Compile patterns for efficiency
        self._injection_re = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._jailbreak_re = [re.compile(p, re.IGNORECASE) for p in self.JAILBREAK_PATTERNS]
        self._sensitive_re = [re.compile(p, re.IGNORECASE) for p in self.SENSITIVE_PATTERNS]

        # Compile PII patterns
        self._pii_patterns = [(re.compile(pattern, re.IGNORECASE), pii_type) for pattern, pii_type in self.PII_PATTERNS]

        self._stats = {
            "analyzed": 0,
            "blocked": 0,
            "clarification_requested": 0,
            "pii_detected": 0,
        }

    def detect_pii(self, text: str, redact: bool = False) -> PIIDetectionResult:
        """Detect PII in text with optional redaction.

        Args:
            text: Text to scan for PII
            redact: If True, create a redacted version of the text

        Returns:
            PIIDetectionResult with detection details
        """
        if not text:
            return PIIDetectionResult(contains_pii=False)

        detected_types: set[str] = set()
        total_risk = 0.0
        pii_count = 0
        redacted_text = text if redact else None

        for pattern, pii_type in self._pii_patterns:
            matches = list(pattern.finditer(text))
            if matches:
                detected_types.add(pii_type)
                pii_count += len(matches)
                total_risk += self.PII_RISK_SCORES.get(pii_type, 0.5) * len(matches)

                # Redact if requested
                if redact:
                    redaction = f"[REDACTED_{pii_type.upper()}]"
                    redacted_text = pattern.sub(redaction, redacted_text)

        contains_pii = len(detected_types) > 0

        if contains_pii:
            self._stats["pii_detected"] += 1
            if self.log_issues:
                logger.warning(
                    f"PII detected: {', '.join(detected_types)}",
                    extra={"pii_types": list(detected_types), "count": pii_count},
                )

        # Normalize risk score (0-1 range)
        risk_score = min(1.0, total_risk / max(1, pii_count))

        return PIIDetectionResult(
            contains_pii=contains_pii,
            pii_types=list(detected_types),
            redacted_text=redacted_text,
            pii_count=pii_count,
            risk_score=round(risk_score, 3),
        )

    def analyze(self, user_input: str) -> InputAnalysisResult:
        """Analyze user input for potential issues.

        Args:
            user_input: The user's input/prompt

        Returns:
            InputAnalysisResult with risk assessment
        """
        self._stats["analyzed"] += 1
        issues: list[InputIssue] = []

        if not user_input:
            return InputAnalysisResult(
                risk_level=InputRiskLevel.SAFE,
                issues=[],
            )

        # Check for prompt injection
        injection_issues = self._check_injection(user_input)
        issues.extend(injection_issues)

        # Check for jailbreak attempts
        jailbreak_issues = self._check_jailbreak(user_input)
        issues.extend(jailbreak_issues)

        # Check for sensitive data
        sensitive_issues = self._check_sensitive_data(user_input)
        issues.extend(sensitive_issues)

        # Check for ambiguity
        ambiguity_issues = self._check_ambiguity(user_input)
        issues.extend(ambiguity_issues)

        # Determine overall risk level
        risk_level = self._calculate_risk_level(issues)

        # Generate clarification questions if needed
        clarification_questions = []
        clarification_needed = False

        if any(i.issue_type == InputIssueType.AMBIGUOUS_REQUEST for i in issues):
            clarification_needed = True
            clarification_questions = self._generate_clarification_questions(user_input, issues)

        # Clean input if applicable
        cleaned_input = self._sanitize_input(user_input) if issues else user_input

        if self.log_issues and issues:
            logger.warning(f"Input guardrail issues detected: {len(issues)} issues, risk_level={risk_level.value}")

        if risk_level == InputRiskLevel.BLOCKED:
            self._stats["blocked"] += 1

        if clarification_needed:
            self._stats["clarification_requested"] += 1

        return InputAnalysisResult(
            risk_level=risk_level,
            issues=issues,
            cleaned_input=cleaned_input,
            clarification_needed=clarification_needed,
            clarification_questions=clarification_questions,
        )

    def _check_injection(self, text: str) -> list[InputIssue]:
        """Check for prompt injection attempts."""
        return [
            InputIssue(
                issue_type=InputIssueType.PROMPT_INJECTION,
                description="Potential prompt injection detected",
                severity=0.9,
                location=match.group(0),
            )
            for pattern in self._injection_re
            if (match := pattern.search(text))
        ]

    def _check_jailbreak(self, text: str) -> list[InputIssue]:
        """Check for jailbreak attempts."""
        return [
            InputIssue(
                issue_type=InputIssueType.JAILBREAK_ATTEMPT,
                description="Potential jailbreak attempt detected",
                severity=0.85,
                location=match.group(0),
            )
            for pattern in self._jailbreak_re
            if (match := pattern.search(text))
        ]

    def _check_sensitive_data(self, text: str) -> list[InputIssue]:
        """Check for sensitive data in input."""
        return [
            InputIssue(
                issue_type=InputIssueType.SENSITIVE_DATA,
                description="Potential sensitive data detected",
                severity=0.5,
                location="[REDACTED]",
                suggestion="Consider removing sensitive information",
            )
            for pattern in self._sensitive_re
            if pattern.search(text)
        ]

    def _check_ambiguity(self, text: str) -> list[InputIssue]:
        """Check for ambiguous or underspecified requests."""
        issues = []
        text_lower = text.lower()
        words = text_lower.split()

        # Check for ambiguous pronouns without context
        ambiguous_count = sum(1 for w in self.AMBIGUITY_INDICATORS if w in words)

        # Very short requests are often underspecified
        if len(words) < 5:
            issues.append(
                InputIssue(
                    issue_type=InputIssueType.UNDERSPECIFIED,
                    description="Request may be too brief for accurate understanding",
                    severity=0.3,
                    suggestion="Consider adding more details about what you need",
                )
            )
        elif ambiguous_count >= 3:
            issues.append(
                InputIssue(
                    issue_type=InputIssueType.AMBIGUOUS_REQUEST,
                    description="Request contains ambiguous references",
                    severity=0.4,
                    suggestion="Consider being more specific about what 'it', 'this', etc. refers to",
                )
            )

        return issues

    def _calculate_risk_level(self, issues: list[InputIssue]) -> InputRiskLevel:
        """Calculate overall risk level from issues."""
        if not issues:
            return InputRiskLevel.SAFE

        max_severity = max(i.severity for i in issues)

        # Check for specific high-risk issue types
        high_risk_types = {InputIssueType.PROMPT_INJECTION, InputIssueType.JAILBREAK_ATTEMPT}
        has_high_risk = any(i.issue_type in high_risk_types for i in issues)

        if has_high_risk or max_severity >= 0.85:
            return InputRiskLevel.BLOCKED
        if max_severity >= 0.6:
            return InputRiskLevel.HIGH_RISK if self.strict_mode else InputRiskLevel.MEDIUM_RISK
        if max_severity >= 0.4:
            return InputRiskLevel.MEDIUM_RISK if self.strict_mode else InputRiskLevel.LOW_RISK
        return InputRiskLevel.LOW_RISK

    def _generate_clarification_questions(
        self,
        text: str,
        issues: list[InputIssue],
    ) -> list[str]:
        """Generate clarification questions for ambiguous requests."""
        questions = []

        for issue in issues:
            if issue.issue_type == InputIssueType.AMBIGUOUS_REQUEST:
                questions.append("Could you clarify what you're referring to?")
            elif issue.issue_type == InputIssueType.UNDERSPECIFIED:
                questions.append("Could you provide more details about what you need?")

        return questions[:3]  # Limit to 3 questions

    def _sanitize_input(self, text: str) -> str:
        """Sanitize input by removing potentially harmful patterns."""
        cleaned = text

        # Remove injection patterns
        for pattern in self._injection_re:
            cleaned = pattern.sub("[REMOVED]", cleaned)

        # Remove jailbreak patterns
        for pattern in self._jailbreak_re:
            cleaned = pattern.sub("[REMOVED]", cleaned)

        return cleaned

    def get_stats(self) -> dict[str, Any]:
        """Get guardrail statistics."""
        return self._stats.copy()


# =============================================================================
# Output Guardrails
# =============================================================================


class OutputIssueType(str, Enum):
    """Types of output issues detected."""

    OFF_TOPIC = "off_topic"
    CONTRADICTORY = "contradictory"
    UNVERIFIED_CLAIM = "unverified_claim"
    HARMFUL_CONTENT = "harmful_content"
    SENSITIVE_DISCLOSURE = "sensitive_disclosure"
    INSTRUCTION_LEAK = "instruction_leak"
    QUALITY_ISSUE = "quality_issue"


@dataclass
class OutputIssue:
    """A detected issue in agent output."""

    issue_type: OutputIssueType
    description: str
    severity: float
    location: str | None = None
    fix_suggestion: str | None = None


@dataclass
class OutputAnalysisResult:
    """Result of output guardrail analysis."""

    is_safe: bool
    issues: list[OutputIssue]
    filtered_output: str | None = None
    needs_revision: bool = False
    revision_guidance: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def should_deliver(self) -> bool:
        """Check if output is safe to deliver."""
        return self.is_safe and not self.needs_revision


class OutputGuardrails:
    """Validates agent outputs before delivery.

    Usage:
        guardrails = OutputGuardrails()
        result = guardrails.analyze(
            output="Here's your answer...",
            original_query="What is Python?",
            context="Python documentation..."
        )

        if result.needs_revision:
            # Send back for revision
            pass
    """

    # Patterns that might indicate system prompt leakage
    INSTRUCTION_LEAK_PATTERNS: ClassVar[list[str]] = [
        r"system\s+prompt",
        r"my\s+instructions?",
        r"I\s+was\s+told\s+to",
        r"my\s+programming",
        r"I\s+am\s+programmed\s+to",
        r"my\s+guidelines?\s+(?:say|tell|instruct)",
    ]

    # Patterns for potentially harmful content
    HARMFUL_PATTERNS: ClassVar[list[str]] = [
        r"how\s+to\s+(hack|steal|break\s+into)",
        r"instructions?\s+for\s+(making|creating)\s+(weapons?|explosives?|drugs?)",
        r"ways?\s+to\s+(harm|hurt|kill)",
    ]

    def __init__(
        self,
        check_relevance: bool = True,
        check_consistency: bool = True,
        relevance_threshold: float = 0.3,
    ):
        """Initialize output guardrails.

        Args:
            check_relevance: Check if output is relevant to query
            check_consistency: Check for internal contradictions
            relevance_threshold: Minimum relevance score
        """
        self.check_relevance = check_relevance
        self.check_consistency = check_consistency
        self.relevance_threshold = relevance_threshold

        self._instruction_re = [re.compile(p, re.IGNORECASE) for p in self.INSTRUCTION_LEAK_PATTERNS]
        self._harmful_re = [re.compile(p, re.IGNORECASE) for p in self.HARMFUL_PATTERNS]

        self._stats = {
            "analyzed": 0,
            "blocked": 0,
            "revision_requested": 0,
        }

    def analyze(
        self,
        output: str,
        original_query: str,
        context: str | None = None,
    ) -> OutputAnalysisResult:
        """Analyze agent output for potential issues.

        Args:
            output: The agent's response
            original_query: The user's original query
            context: Optional context/source material

        Returns:
            OutputAnalysisResult
        """
        self._stats["analyzed"] += 1
        issues: list[OutputIssue] = []

        if not output:
            return OutputAnalysisResult(is_safe=True, issues=[])

        # Check for instruction leakage
        leak_issues = self._check_instruction_leak(output)
        issues.extend(leak_issues)

        # Check for harmful content
        harmful_issues = self._check_harmful_content(output)
        issues.extend(harmful_issues)

        # Check relevance to original query
        if self.check_relevance:
            relevance_issues = self._check_relevance(output, original_query)
            issues.extend(relevance_issues)

        # Check for internal contradictions
        if self.check_consistency:
            consistency_issues = self._check_consistency(output)
            issues.extend(consistency_issues)

        # Determine if safe and if revision needed
        is_safe = not any(i.issue_type == OutputIssueType.HARMFUL_CONTENT for i in issues)
        needs_revision = len(issues) > 0

        # Generate revision guidance if needed
        revision_guidance = None
        if needs_revision:
            revision_guidance = self._generate_revision_guidance(issues)
            self._stats["revision_requested"] += 1

        if not is_safe:
            self._stats["blocked"] += 1

        return OutputAnalysisResult(
            is_safe=is_safe,
            issues=issues,
            needs_revision=needs_revision,
            revision_guidance=revision_guidance,
        )

    def _check_instruction_leak(self, text: str) -> list[OutputIssue]:
        """Check for system instruction leakage."""
        return [
            OutputIssue(
                issue_type=OutputIssueType.INSTRUCTION_LEAK,
                description="Potential system instruction leakage",
                severity=0.7,
                location=match.group(0),
                fix_suggestion="Remove references to internal instructions",
            )
            for pattern in self._instruction_re
            if (match := pattern.search(text))
        ]

    def _check_harmful_content(self, text: str) -> list[OutputIssue]:
        """Check for potentially harmful content."""
        return [
            OutputIssue(
                issue_type=OutputIssueType.HARMFUL_CONTENT,
                description="Potentially harmful content detected",
                severity=0.95,
                location=match.group(0),
            )
            for pattern in self._harmful_re
            if (match := pattern.search(text))
        ]

    # ── Token normalization for relevance check ─────────────────────
    # Expanded stop-word list covering determiners, prepositions, auxiliaries,
    # and common query filler words that carry no topical signal.
    _STOP_WORDS: ClassVar[frozenset[str]] = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "to", "for", "of", "and", "in", "on", "with", "by", "from", "at",
        "it", "its", "this", "that", "these", "those", "i", "me", "my",
        "we", "our", "you", "your", "he", "she", "they", "them", "their",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "do", "does", "did", "has", "have", "had", "will", "would", "can",
        "could", "should", "shall", "may", "might", "must", "not", "no",
        "so", "if", "or", "but", "about", "into", "over", "just", "also",
        "than", "then", "very", "too", "more", "most", "some", "any", "all",
        "each", "every", "both", "few", "many", "much", "such", "only",
    })

    # Regex: split CamelCase / PascalCase into constituent words.
    _CAMEL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?<=[a-z])(?=[A-Z])"  # lowercase→uppercase boundary
        r"|(?<=[A-Z])(?=[A-Z][a-z])"  # ABCDef → ABC Def
    )

    @classmethod
    def _normalize_tokens(cls, text: str) -> set[str]:
        """Normalize text into a set of comparable tokens.

        Handles possessives (karpathy's → karpathy), CamelCase splitting
        (AutoResearch → auto, research), punctuation stripping, and
        hyphenated words (auto-research → auto, research).
        """
        # Strip possessives before splitting
        text = re.sub(r"['']s\b", "", text)
        text = re.sub(r"['']t\b", "", text)

        tokens: set[str] = set()
        for raw_word in text.split():
            # Strip surrounding punctuation
            word = re.sub(r'^[\W_]+|[\W_]+$', '', raw_word)
            if not word:
                continue

            lowered = word.lower()

            # Split hyphenated words (e.g. "auto-research" → "auto", "research")
            if "-" in lowered:
                parts = [p for p in lowered.split("-") if p]
                tokens.update(parts)
                # Also keep the joined form (e.g. "autoresearch")
                tokens.add("".join(parts))
            else:
                # Split CamelCase (e.g. "AutoResearch" → "auto", "research")
                camel_parts = cls._CAMEL_RE.split(word)
                if len(camel_parts) > 1:
                    for part in camel_parts:
                        lp = part.lower()
                        if lp:
                            tokens.add(lp)
                    # Also keep the joined lowercase form
                    tokens.add(lowered)
                else:
                    tokens.add(lowered)

        # Remove stop words and single-character tokens (noise)
        tokens -= cls._STOP_WORDS
        return {t for t in tokens if len(t) > 1}

    def _check_relevance(
        self,
        output: str,
        query: str,
    ) -> list[OutputIssue]:
        """Check if output is relevant to the query.

        Uses normalized token overlap: possessives are stripped, CamelCase and
        hyphenated words are split, and an expanded stop-word list is applied.
        """
        issues = []

        query_words = self._normalize_tokens(query)
        # Only sample the first ~4000 chars of output for performance
        output_sample = output[:4000] if len(output) > 4000 else output
        output_words = self._normalize_tokens(output_sample)

        if query_words:
            overlap = len(query_words & output_words) / len(query_words)

            if overlap < self.relevance_threshold:
                issues.append(
                    OutputIssue(
                        issue_type=OutputIssueType.OFF_TOPIC,
                        description="Output may not be relevant to the original query",
                        severity=0.5,
                        fix_suggestion="Ensure the response addresses the user's question",
                    )
                )

        return issues

    def _check_consistency(self, text: str) -> list[OutputIssue]:
        """Check for structural contradictions (Phase 5: enhanced patterns).

        Detects: mutually exclusive constraints, impossible numerics,
        self-referential loops. Avoids false positives from legitimate
        contrasts (e.g. "X is fast but Y is not").
        """
        issues = []
        text_lower = text.lower()

        # Mutually exclusive: "find X but not X"
        if re.search(r"(\b\w+(?:\s+\w+)*)\s+but\s+not\s+\1", text_lower):
            issues.append(
                OutputIssue(
                    issue_type=OutputIssueType.CONTRADICTORY,
                    description="Request appears self-contradictory: same thing required and forbidden",
                    severity=0.6,
                    fix_suggestion="Clarify the intended constraint",
                )
            )
            return issues

        # Impossible numeric: "top 0", "between 100 and 50"
        if re.search(r"top\s+0\b", text_lower):
            issues.append(
                OutputIssue(
                    issue_type=OutputIssueType.CONTRADICTORY,
                    description="Impossible numeric constraint: 'top 0'",
                    severity=0.7,
                    fix_suggestion="Specify a positive number for top results",
                )
            )
        if re.search(r"between\s+(\d+)\s+and\s+(\d+)", text_lower):
            match = re.search(r"between\s+(\d+)\s+and\s+(\d+)", text_lower)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                if a > b:
                    issues.append(
                        OutputIssue(
                            issue_type=OutputIssueType.CONTRADICTORY,
                            description=f"Impossible range: {a} > {b}",
                            severity=0.7,
                            fix_suggestion="Specify range with smaller value first",
                        )
                    )

        # Self-referential loop: "summarize the summary of the summary"
        if re.search(r"(\b\w+)\s+(?:the\s+)?\1\s+(?:of\s+the\s+)?\1", text_lower):
            issues.append(
                OutputIssue(
                    issue_type=OutputIssueType.CONTRADICTORY,
                    description="Potentially circular or redundant request",
                    severity=0.3,
                    fix_suggestion="Clarify the intended scope",
                )
            )

        return issues

    def _generate_revision_guidance(self, issues: list[OutputIssue]) -> str:
        """Generate guidance for revising the output."""
        guidance = ["Please revise the response to address the following:"]

        for issue in issues:
            if issue.fix_suggestion:
                guidance.append(f"- {issue.fix_suggestion}")
            else:
                guidance.append(f"- Address: {issue.description}")

        return "\n".join(guidance)

    def get_stats(self) -> dict[str, Any]:
        """Get guardrail statistics."""
        return self._stats.copy()


# =============================================================================
# Combined Guardrails Manager
# =============================================================================


class GuardrailsManager:
    """Unified manager for input and output guardrails.

    Usage:
        manager = GuardrailsManager()

        # Check input
        input_result = manager.check_input(user_message)
        if not input_result.should_proceed:
            return "Cannot process this request"

        # ... agent processing ...

        # Check output
        output_result = manager.check_output(response, user_message)
        if output_result.needs_revision:
            # Revise response
            pass
    """

    def __init__(
        self,
        strict_mode: bool = False,
    ):
        """Initialize the guardrails manager.

        Args:
            strict_mode: Enable stricter guardrail thresholds
        """
        self.input_guardrails = InputGuardrails(strict_mode=strict_mode)
        self.output_guardrails = OutputGuardrails()

    def check_input(self, user_input: str) -> InputAnalysisResult:
        """Check user input through guardrails."""
        return self.input_guardrails.analyze(user_input)

    def check_output(
        self,
        output: str,
        original_query: str,
        context: str | None = None,
    ) -> OutputAnalysisResult:
        """Check agent output through guardrails."""
        return self.output_guardrails.analyze(output, original_query, context)

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        return {
            "input": self.input_guardrails.get_stats(),
            "output": self.output_guardrails.get_stats(),
        }


# Singleton instance
_guardrails: GuardrailsManager | None = None


def get_guardrails_manager(strict_mode: bool = False) -> GuardrailsManager:
    """Get the global guardrails manager."""
    global _guardrails
    if _guardrails is None:
        _guardrails = GuardrailsManager(strict_mode=strict_mode)
    return _guardrails
