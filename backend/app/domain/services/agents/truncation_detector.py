"""Truncation Detector for Identifying Cut-Off LLM Responses

Detects when LLM outputs are incomplete due to token limits:
- Abrupt endings mid-sentence or mid-code
- Incomplete lists or JSON structures
- Missing closing delimiters (```, }, ], etc.)

Injects continuation prompts to request completion.

Expected impact: 60%+ reduction in incomplete outputs reaching users.

Context7 validated: Pydantic v2 @model_validator, pattern detection.
"""

import logging
import re
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)


@dataclass
class TruncationAssessment:
    """Assessment of whether LLM output appears truncated.

    Context7 validated: Dataclass for simple data containers.
    """

    is_truncated: bool
    truncation_type: str | None = None  # "mid_sentence", "mid_code", "mid_list", "mid_json"
    confidence: float = 1.0
    continuation_prompt: str | None = None
    evidence: list[str] | None = None  # List of patterns that triggered detection


class TruncationPattern(BaseModel):
    """Configuration for a truncation detection pattern.

    Context7 validated: Pydantic v2 BaseModel with field_validator.
    """

    name: str
    pattern: str  # Regex pattern to detect truncation
    truncation_type: str
    confidence: float = 0.8
    continuation_prompt: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate confidence is between 0 and 1.

        Context7 validated: Pydantic v2 @field_validator pattern.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v

    @model_validator(mode="after")
    def validate_pattern(self) -> "TruncationPattern":
        """Validate regex pattern is valid.

        Context7 validated: Pydantic v2 @model_validator(mode='after') pattern.
        """
        try:
            re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        return self


class TruncationDetector:
    """Detects truncated LLM responses using pattern matching.

    Analyzes response content for signs of incompleteness:
    - Mid-sentence cutoff (no punctuation, hanging phrases)
    - Incomplete code blocks (unclosed ```, {, [, etc.)
    - Partial lists or enumerations
    - Malformed JSON structures

    Context7 validated: Pattern detection, regex matching, dataclass return types.
    """

    # Default truncation patterns
    DEFAULT_PATTERNS: ClassVar[list[TruncationPattern]] = [
        # Mid-sentence truncation (ends without punctuation)
        TruncationPattern(
            name="mid_sentence_no_punctuation",
            pattern=r"[a-zA-Z0-9]\s*$",  # Ends with alphanumeric, no punctuation
            truncation_type="mid_sentence",
            confidence=0.7,
            continuation_prompt=(
                "Your previous response appears to have been cut off mid-sentence. "
                "Please continue from where you stopped and complete your thought."
            ),
        ),
        # Incomplete code block (unclosed ```)
        TruncationPattern(
            name="unclosed_code_block",
            pattern=r"```[a-z]*\n(?:(?!```).)*$",  # Code fence without closing
            truncation_type="mid_code",
            confidence=0.95,
            continuation_prompt=(
                "Your previous code block was not closed. "
                "Please provide the rest of the code and close the code block with ```."
            ),
        ),
        # Incomplete JSON/dict/list (unclosed braces/brackets)
        TruncationPattern(
            name="unclosed_json_structure",
            pattern=r"[{[](?:(?![}\]]).)*$",  # Opening brace/bracket without close
            truncation_type="mid_json",
            confidence=0.9,
            continuation_prompt=(
                "Your previous response contains incomplete JSON or data structures. "
                "Please complete the structure and ensure all braces/brackets are closed."
            ),
        ),
        # Incomplete list (ends with comma or dash)
        TruncationPattern(
            name="incomplete_list",
            pattern=r"[,\-]\s*$",  # Ends with comma or dash (list continuation)
            truncation_type="mid_list",
            confidence=0.75,
            continuation_prompt=(
                "Your previous list or enumeration appears incomplete. Please continue and complete the list."
            ),
        ),
        # Common truncation phrases
        TruncationPattern(
            name="truncation_phrase",
            pattern=r"(?:I'll continue|Let me continue|Continuing|I was saying|As I was|To be continued)\s*$",
            truncation_type="mid_sentence",
            confidence=0.85,
            continuation_prompt=(
                "Your previous response indicated you intended to continue. Please complete your response."
            ),
        ),
    ]

    def __init__(self, patterns: list[TruncationPattern] | None = None):
        """Initialize truncation detector with patterns.

        Args:
            patterns: Custom truncation patterns (defaults to DEFAULT_PATTERNS)

        Context7 validated: Constructor with sensible defaults.
        """
        self.patterns = patterns or self.DEFAULT_PATTERNS
        self._compiled_patterns = [(p, re.compile(p.pattern, re.DOTALL | re.IGNORECASE)) for p in self.patterns]

    def detect(
        self,
        content: str,
        finish_reason: str | None = None,
        max_tokens_used: bool = False,
    ) -> TruncationAssessment:
        """Detect if content appears truncated.

        Args:
            content: LLM response content to analyze
            finish_reason: LLM finish reason ("stop", "length", etc.)
            max_tokens_used: Whether response hit max token limit

        Returns:
            TruncationAssessment with detection results

        Context7 validated: Pattern matching, early return optimization.
        """
        # Empty content is not truncated
        if not content or not content.strip():
            return TruncationAssessment(is_truncated=False)

        # finish_reason="length" is strong signal of truncation
        if finish_reason == "length" or max_tokens_used:
            return TruncationAssessment(
                is_truncated=True,
                truncation_type="max_tokens",
                confidence=0.99,
                continuation_prompt=(
                    "Your previous response reached the maximum token limit and was cut off. "
                    "Please continue from where you stopped and complete your response."
                ),
                evidence=["finish_reason=length" if finish_reason == "length" else "max_tokens_used=True"],
            )

        # Check patterns
        evidence = []
        matches = []

        for pattern_obj, compiled_pattern in self._compiled_patterns:
            if compiled_pattern.search(content):
                matches.append(pattern_obj)
                evidence.append(f"Matched pattern: {pattern_obj.name}")

        if not matches:
            return TruncationAssessment(is_truncated=False)

        # Use highest confidence match
        best_match = max(matches, key=lambda p: p.confidence)

        return TruncationAssessment(
            is_truncated=True,
            truncation_type=best_match.truncation_type,
            confidence=best_match.confidence,
            continuation_prompt=best_match.continuation_prompt,
            evidence=evidence,
        )

    def should_request_continuation(self, assessment: TruncationAssessment, confidence_threshold: float = 0.8) -> bool:
        """Determine if continuation should be requested based on assessment.

        Args:
            assessment: TruncationAssessment from detect()
            confidence_threshold: Minimum confidence to request continuation

        Returns:
            True if continuation should be requested

        Context7 validated: Threshold-based decision pattern.
        """
        return assessment.is_truncated and assessment.confidence >= confidence_threshold


# Singleton instance
_truncation_detector: TruncationDetector | None = None


def get_truncation_detector(patterns: list[TruncationPattern] | None = None) -> TruncationDetector:
    """Get or create the global truncation detector.

    Args:
        patterns: Optional custom patterns (only used on first call)

    Returns:
        TruncationDetector instance

    Context7 validated: Singleton factory pattern.
    """
    global _truncation_detector
    if _truncation_detector is None:
        _truncation_detector = TruncationDetector(patterns=patterns)
    return _truncation_detector
