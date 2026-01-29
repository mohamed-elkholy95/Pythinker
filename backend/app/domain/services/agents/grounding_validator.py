"""Grounding Validator for Hallucination Prevention

Validates that agent outputs are grounded in source context,
reducing hallucinations by flagging unverifiable claims.

Research shows contextual grounding checks can reduce hallucinations
significantly by ensuring outputs are traceable to source material.

Key concepts:
- Grounding Source: The context/documents the response should be based on
- Query: The user's original question/request
- Response: The agent's output to validate
- Grounding Score: How well the response is supported by the source
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class GroundingLevel(str, Enum):
    """Levels of grounding quality."""
    FULLY_GROUNDED = "fully_grounded"      # All claims supported
    PARTIALLY_GROUNDED = "partially_grounded"  # Some claims supported
    WEAKLY_GROUNDED = "weakly_grounded"    # Few claims supported
    UNGROUNDED = "ungrounded"              # No support found


@dataclass
class Claim:
    """A single claim extracted from a response."""
    text: str
    source_support: Optional[str] = None  # Supporting text from source
    grounding_score: float = 0.0
    is_factual: bool = True  # False for opinions/hedged statements


@dataclass
class GroundingResult:
    """Result of grounding validation."""
    overall_score: float  # 0.0 to 1.0
    level: GroundingLevel
    claims: List[Claim]
    ungrounded_claims: List[str]
    grounded_claims: List[str]
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_acceptable(self) -> bool:
        """Check if grounding level is acceptable for delivery."""
        return self.level in (GroundingLevel.FULLY_GROUNDED, GroundingLevel.PARTIALLY_GROUNDED)

    @property
    def needs_revision(self) -> bool:
        """Check if the response needs revision."""
        return self.level in (GroundingLevel.WEAKLY_GROUNDED, GroundingLevel.UNGROUNDED)

    def get_revision_guidance(self) -> str:
        """Get guidance for revising ungrounded content."""
        if not self.ungrounded_claims:
            return ""

        guidance = ["The following claims could not be verified against the source context:"]
        for claim in self.ungrounded_claims[:5]:  # Limit to 5
            guidance.append(f"- {claim}")

        guidance.append("\nPlease either:")
        guidance.append("1. Remove or qualify these claims (e.g., 'It appears that...')")
        guidance.append("2. Provide supporting evidence from the source")
        guidance.append("3. Acknowledge uncertainty (e.g., 'I cannot verify...')")

        return "\n".join(guidance)


class GroundingValidator:
    """Validates that responses are grounded in source context.

    Usage:
        validator = GroundingValidator()

        result = validator.validate(
            source="Python is a programming language created by Guido van Rossum.",
            query="Who created Python?",
            response="Python was created by Guido van Rossum in 1991."
        )

        if result.needs_revision:
            print(result.get_revision_guidance())
    """

    # Threshold for considering a claim grounded
    GROUNDING_THRESHOLD = 0.4

    # Patterns for hedged/uncertain language (not factual claims)
    HEDGE_PATTERNS = [
        r'\b(might|may|could|possibly|perhaps|likely|probably|seems?|appears?)\b',
        r'\b(I think|I believe|In my opinion|It seems)\b',
        r'\b(approximately|around|about|roughly|estimated)\b',
        r'\b(often|sometimes|usually|generally|typically)\b',
    ]

    # Patterns for citations/references (already grounded)
    CITATION_PATTERNS = [
        r'\[\d+\]',           # [1], [2] style
        r'\(source:.*?\)',    # (source: ...) style
        r'according to',      # Attribution
        r'based on',          # Attribution
    ]

    # Common stop words for similarity calculation
    STOP_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'to', 'of', 'in',
        'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
        'and', 'but', 'or', 'nor', 'so', 'yet', 'both', 'either', 'neither',
        'this', 'that', 'these', 'those', 'it', 'its',
    }

    def __init__(
        self,
        grounding_threshold: float = 0.4,
        min_claim_words: int = 3,
        max_claims_to_check: int = 20,
    ):
        """Initialize the grounding validator.

        Args:
            grounding_threshold: Minimum similarity for a claim to be grounded
            min_claim_words: Minimum words for a sentence to be a claim
            max_claims_to_check: Maximum claims to validate (for performance)
        """
        self.grounding_threshold = grounding_threshold
        self.min_claim_words = min_claim_words
        self.max_claims_to_check = max_claims_to_check

        # Statistics
        self._stats = {
            "validations": 0,
            "fully_grounded": 0,
            "partially_grounded": 0,
            "weakly_grounded": 0,
            "ungrounded": 0,
        }

    def validate(
        self,
        source: str,
        query: str,
        response: str,
    ) -> GroundingResult:
        """Validate that a response is grounded in the source context.

        Args:
            source: The grounding source/context
            query: The user's original query
            response: The agent's response to validate

        Returns:
            GroundingResult with scores and analysis
        """
        self._stats["validations"] += 1

        if not response:
            return GroundingResult(
                overall_score=1.0,
                level=GroundingLevel.FULLY_GROUNDED,
                claims=[],
                ungrounded_claims=[],
                grounded_claims=[],
            )

        # Extract claims from response
        claims = self._extract_claims(response)

        if not claims:
            return GroundingResult(
                overall_score=1.0,
                level=GroundingLevel.FULLY_GROUNDED,
                claims=[],
                ungrounded_claims=[],
                grounded_claims=[],
                warnings=["No factual claims detected in response"],
            )

        # Validate each claim against source
        grounded_claims = []
        ungrounded_claims = []
        total_score = 0.0

        for claim in claims[:self.max_claims_to_check]:
            score, support = self._calculate_grounding_score(claim.text, source)
            claim.grounding_score = score
            claim.source_support = support

            total_score += score

            if score >= self.grounding_threshold:
                grounded_claims.append(claim.text)
            else:
                ungrounded_claims.append(claim.text)

        # Calculate overall score
        overall_score = total_score / len(claims) if claims else 1.0

        # Determine grounding level
        level = self._determine_level(overall_score, len(grounded_claims), len(claims))

        # Update statistics
        self._stats[level.value] += 1

        # Generate warnings
        warnings = []
        if ungrounded_claims:
            warnings.append(f"{len(ungrounded_claims)} claims could not be verified")
        if len(claims) > self.max_claims_to_check:
            warnings.append(f"Only checked {self.max_claims_to_check} of {len(claims)} claims")

        logger.info(
            f"Grounding validation: score={overall_score:.2f}, "
            f"level={level.value}, grounded={len(grounded_claims)}/{len(claims)}"
        )

        return GroundingResult(
            overall_score=overall_score,
            level=level,
            claims=claims,
            ungrounded_claims=ungrounded_claims,
            grounded_claims=grounded_claims,
            warnings=warnings,
        )

    def _extract_claims(self, text: str) -> List[Claim]:
        """Extract factual claims from text.

        Args:
            text: The text to extract claims from

        Returns:
            List of Claim objects
        """
        claims = []

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            sentence = sentence.strip()

            # Skip if too short
            if len(sentence.split()) < self.min_claim_words:
                continue

            # Skip if it's a question
            if sentence.endswith('?'):
                continue

            # Skip if it's a command/instruction
            if sentence.startswith(('Please', 'Note:', 'Remember:', 'Tip:')):
                continue

            # Check if it's hedged (not a factual claim)
            is_factual = not any(
                re.search(pattern, sentence, re.IGNORECASE)
                for pattern in self.HEDGE_PATTERNS
            )

            # Check if it has citations (already grounded)
            has_citation = any(
                re.search(pattern, sentence, re.IGNORECASE)
                for pattern in self.CITATION_PATTERNS
            )

            claims.append(Claim(
                text=sentence,
                is_factual=is_factual and not has_citation,
            ))

        return claims

    def _calculate_grounding_score(
        self,
        claim: str,
        source: str,
    ) -> Tuple[float, Optional[str]]:
        """Calculate how well a claim is grounded in the source.

        Args:
            claim: The claim to check
            source: The source context

        Returns:
            Tuple of (score, supporting_text)
        """
        if not source:
            return 0.0, None

        # Tokenize and normalize
        claim_words = self._tokenize(claim)
        source_words = self._tokenize(source)

        if not claim_words:
            return 1.0, None  # Empty claim is vacuously grounded

        # Calculate word overlap
        common_words = claim_words & source_words
        overlap_score = len(common_words) / len(claim_words) if claim_words else 0

        # Find best matching sentence in source for support
        source_sentences = re.split(r'(?<=[.!?])\s+', source)
        best_match_score = 0.0
        best_match_sentence = None

        for sentence in source_sentences:
            sentence_words = self._tokenize(sentence)
            if not sentence_words:
                continue

            # Jaccard similarity
            intersection = len(claim_words & sentence_words)
            union = len(claim_words | sentence_words)
            similarity = intersection / union if union > 0 else 0

            if similarity > best_match_score:
                best_match_score = similarity
                best_match_sentence = sentence

        # Combine overlap and best match scores
        final_score = (overlap_score * 0.4) + (best_match_score * 0.6)

        return final_score, best_match_sentence

    def _tokenize(self, text: str) -> set:
        """Tokenize text into a set of meaningful words.

        Args:
            text: Text to tokenize

        Returns:
            Set of normalized words
        """
        # Extract words, lowercase, filter stop words
        words = re.findall(r'\b[a-z]+\b', text.lower())
        return {w for w in words if w not in self.STOP_WORDS and len(w) > 2}

    def _determine_level(
        self,
        score: float,
        grounded: int,
        total: int,
    ) -> GroundingLevel:
        """Determine the grounding level based on score and counts.

        Args:
            score: Overall grounding score
            grounded: Number of grounded claims
            total: Total number of claims

        Returns:
            GroundingLevel
        """
        grounded_ratio = grounded / total if total > 0 else 1.0

        if score >= 0.7 and grounded_ratio >= 0.8:
            return GroundingLevel.FULLY_GROUNDED
        elif score >= 0.5 and grounded_ratio >= 0.5:
            return GroundingLevel.PARTIALLY_GROUNDED
        elif score >= 0.3 or grounded_ratio >= 0.3:
            return GroundingLevel.WEAKLY_GROUNDED
        else:
            return GroundingLevel.UNGROUNDED

    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        total = self._stats["validations"]
        return {
            **self._stats,
            "grounded_rate": f"{(self._stats['fully_grounded'] + self._stats['partially_grounded']) / max(total, 1):.1%}",
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        for key in self._stats:
            self._stats[key] = 0


# Convenience functions
_validator: Optional[GroundingValidator] = None


def get_grounding_validator() -> GroundingValidator:
    """Get the global grounding validator instance."""
    global _validator
    if _validator is None:
        _validator = GroundingValidator()
    return _validator


def validate_grounding(
    source: str,
    query: str,
    response: str,
) -> GroundingResult:
    """Convenience function to validate grounding.

    Args:
        source: The grounding source/context
        query: The user's query
        response: The response to validate

    Returns:
        GroundingResult
    """
    return get_grounding_validator().validate(source, query, response)


def check_response_grounded(
    source: str,
    response: str,
    threshold: float = 0.5,
) -> bool:
    """Quick check if a response is adequately grounded.

    Args:
        source: The grounding source
        response: The response to check
        threshold: Minimum acceptable score

    Returns:
        True if response is adequately grounded
    """
    result = validate_grounding(source, "", response)
    return result.overall_score >= threshold
