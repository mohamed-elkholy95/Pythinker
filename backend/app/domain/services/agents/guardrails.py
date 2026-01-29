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
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from datetime import datetime

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
class InputIssue:
    """A detected issue in user input."""
    issue_type: InputIssueType
    description: str
    severity: float  # 0.0 to 1.0
    location: Optional[str] = None  # Where in the input
    suggestion: Optional[str] = None  # How to fix


@dataclass
class InputAnalysisResult:
    """Result of input guardrail analysis."""
    risk_level: InputRiskLevel
    issues: List[InputIssue]
    cleaned_input: Optional[str] = None  # Sanitized version if applicable
    clarification_needed: bool = False
    clarification_questions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

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
    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)',
        r'disregard\s+(all\s+)?(previous|prior|above)',
        r'forget\s+(everything|all)\s+(you\s+)?(know|learned|were told)',
        r'your\s+new\s+(instructions?|rules?|role)\s+(are|is)',
        r'you\s+are\s+now\s+(?:a|an|the)',
        r'pretend\s+(?:you\s+are|to\s+be)',
        r'act\s+as\s+(?:if|though)',
        r'roleplay\s+as',
        r'system\s*:\s*',  # Trying to inject system message
        r'\[\s*INST\s*\]',  # Llama-style injection
        r'<\|im_start\|>',  # ChatML injection
    ]

    # Jailbreak patterns
    JAILBREAK_PATTERNS = [
        r'DAN\s+mode',
        r'do\s+anything\s+now',
        r'bypass\s+(safety|content|filter)',
        r'without\s+(restrictions?|limits?|filters?)',
        r'no\s+(ethical|moral|safety)\s+(guidelines?|restrictions?)',
        r'hypothetically\s+speaking',
        r'for\s+(educational|research)\s+purposes?\s+only',
        r'pretend\s+there\s+are\s+no\s+(rules?|restrictions?)',
    ]

    # Sensitive data patterns
    SENSITIVE_PATTERNS = [
        r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b',  # SSN
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email (not always sensitive)
        r'password\s*[:=]\s*\S+',  # Password in input
        r'api[_-]?key\s*[:=]\s*\S+',  # API key
        r'secret\s*[:=]\s*\S+',  # Secret
    ]

    # Ambiguity indicators
    AMBIGUITY_INDICATORS = [
        'something', 'anything', 'whatever', 'somehow',
        'it', 'this', 'that', 'stuff', 'things',
    ]

    def __init__(
        self,
        strict_mode: bool = False,
        log_issues: bool = True,
    ):
        """Initialize input guardrails.

        Args:
            strict_mode: If True, blocks on medium risk (not just high)
            log_issues: If True, logs all detected issues
        """
        self.strict_mode = strict_mode
        self.log_issues = log_issues

        # Compile patterns for efficiency
        self._injection_re = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._jailbreak_re = [re.compile(p, re.IGNORECASE) for p in self.JAILBREAK_PATTERNS]
        self._sensitive_re = [re.compile(p, re.IGNORECASE) for p in self.SENSITIVE_PATTERNS]

        self._stats = {
            "analyzed": 0,
            "blocked": 0,
            "clarification_requested": 0,
        }

    def analyze(self, user_input: str) -> InputAnalysisResult:
        """Analyze user input for potential issues.

        Args:
            user_input: The user's input/prompt

        Returns:
            InputAnalysisResult with risk assessment
        """
        self._stats["analyzed"] += 1
        issues: List[InputIssue] = []

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
            logger.warning(
                f"Input guardrail issues detected: {len(issues)} issues, "
                f"risk_level={risk_level.value}"
            )

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

    def _check_injection(self, text: str) -> List[InputIssue]:
        """Check for prompt injection attempts."""
        issues = []

        for pattern in self._injection_re:
            if match := pattern.search(text):
                issues.append(InputIssue(
                    issue_type=InputIssueType.PROMPT_INJECTION,
                    description="Potential prompt injection detected",
                    severity=0.9,
                    location=match.group(0),
                ))

        return issues

    def _check_jailbreak(self, text: str) -> List[InputIssue]:
        """Check for jailbreak attempts."""
        issues = []

        for pattern in self._jailbreak_re:
            if match := pattern.search(text):
                issues.append(InputIssue(
                    issue_type=InputIssueType.JAILBREAK_ATTEMPT,
                    description="Potential jailbreak attempt detected",
                    severity=0.85,
                    location=match.group(0),
                ))

        return issues

    def _check_sensitive_data(self, text: str) -> List[InputIssue]:
        """Check for sensitive data in input."""
        issues = []

        for pattern in self._sensitive_re:
            if match := pattern.search(text):
                issues.append(InputIssue(
                    issue_type=InputIssueType.SENSITIVE_DATA,
                    description="Potential sensitive data detected",
                    severity=0.5,
                    location="[REDACTED]",
                    suggestion="Consider removing sensitive information",
                ))

        return issues

    def _check_ambiguity(self, text: str) -> List[InputIssue]:
        """Check for ambiguous or underspecified requests."""
        issues = []
        text_lower = text.lower()
        words = text_lower.split()

        # Check for ambiguous pronouns without context
        ambiguous_count = sum(1 for w in self.AMBIGUITY_INDICATORS if w in words)

        # Very short requests are often underspecified
        if len(words) < 5:
            issues.append(InputIssue(
                issue_type=InputIssueType.UNDERSPECIFIED,
                description="Request may be too brief for accurate understanding",
                severity=0.3,
                suggestion="Consider adding more details about what you need",
            ))
        elif ambiguous_count >= 3:
            issues.append(InputIssue(
                issue_type=InputIssueType.AMBIGUOUS_REQUEST,
                description="Request contains ambiguous references",
                severity=0.4,
                suggestion="Consider being more specific about what 'it', 'this', etc. refers to",
            ))

        return issues

    def _calculate_risk_level(self, issues: List[InputIssue]) -> InputRiskLevel:
        """Calculate overall risk level from issues."""
        if not issues:
            return InputRiskLevel.SAFE

        max_severity = max(i.severity for i in issues)

        # Check for specific high-risk issue types
        high_risk_types = {InputIssueType.PROMPT_INJECTION, InputIssueType.JAILBREAK_ATTEMPT}
        has_high_risk = any(i.issue_type in high_risk_types for i in issues)

        if has_high_risk or max_severity >= 0.85:
            return InputRiskLevel.BLOCKED
        elif max_severity >= 0.6:
            return InputRiskLevel.HIGH_RISK if self.strict_mode else InputRiskLevel.MEDIUM_RISK
        elif max_severity >= 0.4:
            return InputRiskLevel.MEDIUM_RISK if self.strict_mode else InputRiskLevel.LOW_RISK
        else:
            return InputRiskLevel.LOW_RISK

    def _generate_clarification_questions(
        self,
        text: str,
        issues: List[InputIssue],
    ) -> List[str]:
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
            cleaned = pattern.sub('[REMOVED]', cleaned)

        # Remove jailbreak patterns
        for pattern in self._jailbreak_re:
            cleaned = pattern.sub('[REMOVED]', cleaned)

        return cleaned

    def get_stats(self) -> Dict[str, Any]:
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
    location: Optional[str] = None
    fix_suggestion: Optional[str] = None


@dataclass
class OutputAnalysisResult:
    """Result of output guardrail analysis."""
    is_safe: bool
    issues: List[OutputIssue]
    filtered_output: Optional[str] = None
    needs_revision: bool = False
    revision_guidance: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

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
    INSTRUCTION_LEAK_PATTERNS = [
        r'system\s+prompt',
        r'my\s+instructions?',
        r'I\s+was\s+told\s+to',
        r'my\s+programming',
        r'I\s+am\s+programmed\s+to',
        r'my\s+guidelines?\s+(?:say|tell|instruct)',
    ]

    # Patterns for potentially harmful content
    HARMFUL_PATTERNS = [
        r'how\s+to\s+(hack|steal|break\s+into)',
        r'instructions?\s+for\s+(making|creating)\s+(weapons?|explosives?|drugs?)',
        r'ways?\s+to\s+(harm|hurt|kill)',
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
        context: Optional[str] = None,
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
        issues: List[OutputIssue] = []

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

    def _check_instruction_leak(self, text: str) -> List[OutputIssue]:
        """Check for system instruction leakage."""
        issues = []

        for pattern in self._instruction_re:
            if match := pattern.search(text):
                issues.append(OutputIssue(
                    issue_type=OutputIssueType.INSTRUCTION_LEAK,
                    description="Potential system instruction leakage",
                    severity=0.7,
                    location=match.group(0),
                    fix_suggestion="Remove references to internal instructions",
                ))

        return issues

    def _check_harmful_content(self, text: str) -> List[OutputIssue]:
        """Check for potentially harmful content."""
        issues = []

        for pattern in self._harmful_re:
            if match := pattern.search(text):
                issues.append(OutputIssue(
                    issue_type=OutputIssueType.HARMFUL_CONTENT,
                    description="Potentially harmful content detected",
                    severity=0.95,
                    location=match.group(0),
                ))

        return issues

    def _check_relevance(
        self,
        output: str,
        query: str,
    ) -> List[OutputIssue]:
        """Check if output is relevant to the query."""
        issues = []

        # Simple word overlap check
        query_words = set(query.lower().split())
        output_words = set(output.lower().split())

        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'to', 'for', 'of', 'and', 'in', 'on', 'with'}
        query_words -= stop_words
        output_words -= stop_words

        if query_words:
            overlap = len(query_words & output_words) / len(query_words)

            if overlap < self.relevance_threshold:
                issues.append(OutputIssue(
                    issue_type=OutputIssueType.OFF_TOPIC,
                    description="Output may not be relevant to the original query",
                    severity=0.5,
                    fix_suggestion="Ensure the response addresses the user's question",
                ))

        return issues

    def _check_consistency(self, text: str) -> List[OutputIssue]:
        """Check for internal contradictions."""
        issues = []

        # Simple check for contradiction patterns
        contradiction_patterns = [
            (r'\bis\b', r'\bis\s+not\b'),
            (r'\bcan\b', r'\bcannot\b'),
            (r'\bwill\b', r'\bwill\s+not\b'),
            (r'\btrue\b', r'\bfalse\b'),
        ]

        for pos_pattern, neg_pattern in contradiction_patterns:
            has_positive = bool(re.search(pos_pattern, text, re.IGNORECASE))
            has_negative = bool(re.search(neg_pattern, text, re.IGNORECASE))

            if has_positive and has_negative:
                # Could be a legitimate contrast, so low severity
                issues.append(OutputIssue(
                    issue_type=OutputIssueType.CONTRADICTORY,
                    description="Output may contain contradictory statements",
                    severity=0.3,
                    fix_suggestion="Review for clarity and consistency",
                ))
                break  # Only report once

        return issues

    def _generate_revision_guidance(self, issues: List[OutputIssue]) -> str:
        """Generate guidance for revising the output."""
        guidance = ["Please revise the response to address the following:"]

        for issue in issues:
            if issue.fix_suggestion:
                guidance.append(f"- {issue.fix_suggestion}")
            else:
                guidance.append(f"- Address: {issue.description}")

        return "\n".join(guidance)

    def get_stats(self) -> Dict[str, Any]:
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
        context: Optional[str] = None,
    ) -> OutputAnalysisResult:
        """Check agent output through guardrails."""
        return self.output_guardrails.analyze(output, original_query, context)

    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics."""
        return {
            "input": self.input_guardrails.get_stats(),
            "output": self.output_guardrails.get_stats(),
        }


# Singleton instance
_guardrails: Optional[GuardrailsManager] = None


def get_guardrails_manager(strict_mode: bool = False) -> GuardrailsManager:
    """Get the global guardrails manager."""
    global _guardrails
    if _guardrails is None:
        _guardrails = GuardrailsManager(strict_mode=strict_mode)
    return _guardrails
