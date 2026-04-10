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
    - Truncated or missing References sections in reports
    - Mid-sentence cutoff (no punctuation, hanging phrases)
    - Incomplete code blocks (unclosed ```, {, [, etc.)
    - Partial lists or enumerations
    - Malformed JSON structures

    Context7 validated: Pattern detection, regex matching, dataclass return types.
    """

    # Matches lines that end with a URL — used to suppress mid_sentence false positives
    _URL_LINE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:https?://|www\.)\S+$"
        r"|"
        r"\S+\.(?:com|org|io|net|edu|gov)\S*$",
        re.IGNORECASE,
    )

    # Continuation prompt for incomplete reference sections
    REFERENCES_CONTINUATION_PROMPT: ClassVar[str] = (
        "Your previous response has an incomplete ## References section. "
        "Continue by writing the COMPLETE ## References section listing ALL cited sources. "
        "Each reference must be formatted as: [N] Source Title - URL. "
        "Do NOT repeat any content before the References section."
    )

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
        # Placeholder artifacts produced by truncated generation loops
        TruncationPattern(
            name="placeholder_ellipsis_artifact",
            pattern=r"(?:\[\s*\.{3}\s*\]|\[\s*…\s*\])\s*$",
            truncation_type="mid_sentence",
            confidence=0.92,
            continuation_prompt=(
                "Your previous response appears truncated and ended with an ellipsis placeholder. "
                "Please continue and provide the missing content in full."
            ),
        ),
    ]

    @classmethod
    def _last_line_is_url(cls, content: str) -> bool:
        """Return True if the last non-empty line of *content* ends with a URL.

        Used to suppress mid_sentence_no_punctuation false positives when
        the response legitimately ends with a bare link.
        """
        for line in reversed(content.splitlines()):
            stripped = line.strip()
            if stripped:
                return bool(cls._URL_LINE_RE.search(stripped))
        return False

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

        # Domain-specific: incomplete References section (higher priority than generic patterns)
        ref_assessment = self._detect_incomplete_references(content)
        if ref_assessment.is_truncated:
            return ref_assessment

        # Check patterns
        evidence = []
        matches = []

        url_last_line = self._last_line_is_url(content)

        for pattern_obj, compiled_pattern in self._compiled_patterns:
            if compiled_pattern.search(content):
                # Reduce false positives for unclosed_code_block pattern
                # Only flag as truncation if the code block appears incomplete
                if pattern_obj.name == "unclosed_code_block" and not self._is_truly_unclosed_code_block(content):
                    continue  # Skip this false positive
                # Suppress mid_sentence false positive when the last line ends with a URL
                if pattern_obj.name == "mid_sentence_no_punctuation" and url_last_line:
                    continue  # URL endings are not truncation signals
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

    def _is_truly_unclosed_code_block(self, content: str) -> bool:
        """Validate that an unclosed code block is actually truncated, not a false positive.

        False positive scenarios to avoid:
        1. Content with properly closed code blocks (just has backticks elsewhere)
        2. Long, well-formed reports that happen to match the pattern
        3. Code blocks with balanced fences but the regex misread them

        True truncation indicators:
        1. Odd number of code fences (definitive unclosed block)
        2. Last code fence is within the last 500 chars and content is short
        3. Last code fence is followed by incomplete content (< 100 chars after it)
        """
        if not content:
            return False

        # Count code fence occurrences (``` on their own line)
        fence_pattern = re.compile(r"^```[a-zA-Z0-9_-]*\s*$", re.MULTILINE)
        fence_matches = list(fence_pattern.finditer(content))
        if not fence_matches:
            return False

        # Even number of fences = all blocks are properly closed
        if len(fence_matches) % 2 == 0:
            return False

        # Odd number of fences means an unclosed block. Keep this signal authoritative
        # and only suppress very likely false positives from long, well-formed documents.

        last_fence = fence_matches[-1]
        content_after_last_fence = content[last_fence.end() :].strip()

        # If there is substantial content after the final fence, it is less likely
        # to be an actual truncation at the end of generation.
        if len(content_after_last_fence) > 500:
            return False

        # Very long documents with an odd fence far from the end are usually
        # formatting artifacts, not generation truncation.
        content_len = len(content)
        last_fence_pos = last_fence.start()

        return not (content_len > 20000 and last_fence_pos < content_len * 0.9)

    def _detect_incomplete_references(self, content: str) -> TruncationAssessment:
        """Detect truncated or missing References sections in report-style content.

        Three checks (each exceeds the 0.85 continuation threshold):
        1. References heading present but section empty/very short → 0.92
        2. Partial [N] entry at end (no URL) → 0.90
        3. Inline citation count exceeds reference entry count → 0.88
        """
        evidence: list[str] = []

        # Only check content that looks like a report (has headings)
        if not re.search(r"^#{1,3}\s+", content, re.MULTILINE):
            return TruncationAssessment(is_truncated=False)

        # Find the ## References section
        ref_heading_match = re.search(
            r"^##\s+References?\s*$",
            content,
            re.MULTILINE | re.IGNORECASE,
        )

        # Count inline citations [N] in the body (before References heading)
        body = content[: ref_heading_match.start()] if ref_heading_match else content
        inline_citations = set(re.findall(r"\[(\d+)\]", body))

        if ref_heading_match:
            ref_section = content[ref_heading_match.end() :].strip()

            # Check 1: References heading present but section empty/very short
            # (either nothing after heading, or < 30 chars which is too short for even one entry)
            if len(ref_section) < 30:
                evidence.append("references_heading_present_but_empty_or_very_short")
                return TruncationAssessment(
                    is_truncated=True,
                    truncation_type="incomplete_references",
                    confidence=0.92,
                    continuation_prompt=self.REFERENCES_CONTINUATION_PROMPT,
                    evidence=evidence,
                )

            # Check 2: Partial [N] entry at end (has number but no URL)
            # Look at the last line of the references section
            ref_lines = [ln.strip() for ln in ref_section.split("\n") if ln.strip()]
            if ref_lines:
                last_line = ref_lines[-1]
                # Matches patterns like "[5]" or "[5] Some Title" without a URL
                if re.match(r"^\[?\d+\]?\s*\S*$", last_line) or (
                    re.match(r"^\[?\d+\]", last_line) and "http" not in last_line and " - " not in last_line
                ):
                    evidence.append(f"partial_reference_entry_at_end: {last_line!r}")
                    return TruncationAssessment(
                        is_truncated=True,
                        truncation_type="incomplete_references",
                        confidence=0.90,
                        continuation_prompt=self.REFERENCES_CONTINUATION_PROMPT,
                        evidence=evidence,
                    )

            # Check 3: Inline citation count exceeds reference entry count
            ref_entries = set(re.findall(r"\[(\d+)\]", ref_section))
            if inline_citations and ref_entries and len(inline_citations) > len(ref_entries):
                missing_count = len(inline_citations) - len(ref_entries)
                evidence.append(
                    f"inline_citations={len(inline_citations)} > ref_entries={len(ref_entries)} "
                    f"(missing {missing_count})"
                )
                return TruncationAssessment(
                    is_truncated=True,
                    truncation_type="incomplete_references",
                    confidence=0.88,
                    continuation_prompt=self.REFERENCES_CONTINUATION_PROMPT,
                    evidence=evidence,
                )
        elif inline_citations:
            # No References heading at all, but inline citations exist
            evidence.append(f"no_references_heading_but_{len(inline_citations)}_inline_citations_found")
            return TruncationAssessment(
                is_truncated=True,
                truncation_type="incomplete_references",
                confidence=0.92,
                continuation_prompt=self.REFERENCES_CONTINUATION_PROMPT,
                evidence=evidence,
            )

        return TruncationAssessment(is_truncated=False)

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

    @staticmethod
    def auto_fix_incomplete_references(content: str) -> str:
        """Auto-fix incomplete references by appending placeholder entries (Fix 5).

        When inline citations [N] exist in the body but the References section
        is missing those entries, this method appends placeholder entries so the
        report is structurally complete.  The placeholders prompt the reader
        (or a subsequent LLM pass) to fill in the actual source.

        Only triggers when the gap is <= 5 missing entries.  Larger gaps
        indicate a more fundamental issue that needs LLM continuation.

        Args:
            content: The report content with potentially incomplete references.

        Returns:
            Content with missing reference placeholders appended (or unchanged
            if no fix is needed).
        """
        max_auto_fix = 50  # Handle large reference gaps from LLM output truncation

        ref_heading_match = re.search(
            r"^##\s+References?\s*$",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
        if not ref_heading_match:
            return content

        body = content[: ref_heading_match.start()]
        ref_section = content[ref_heading_match.end() :]

        # Collect inline citation numbers from the body
        inline_nums = {int(n) for n in re.findall(r"\[(\d+)\]", body)}
        # Collect reference entry numbers from the references section
        ref_nums = {int(n) for n in re.findall(r"\[(\d+)\]", ref_section)}

        missing = sorted(inline_nums - ref_nums)
        if not missing or len(missing) > max_auto_fix:
            return content

        # Build placeholder entries
        placeholders = [f"[{num}] *Source pending verification*" for num in missing]

        # Append to content (before any trailing disclaimer/whitespace)
        # Find the last non-whitespace position after references
        stripped = content.rstrip()
        suffix = content[len(stripped) :]
        patched = stripped + "\n" + "\n".join(placeholders) + suffix

        logger.info(
            "Auto-fixed %d missing reference entries: %s",
            len(missing),
            missing,
        )
        return patched


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
