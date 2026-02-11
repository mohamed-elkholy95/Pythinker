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

Enhanced Features (Phase 3):
- Numeric claim extraction and verification
- Entity claim extraction and verification
- Provenance-based validation
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from app.domain.models.claim_provenance import ProvenanceStore

logger = logging.getLogger(__name__)


class GroundingLevel(str, Enum):
    """Levels of grounding quality."""

    FULLY_GROUNDED = "fully_grounded"  # All claims supported
    PARTIALLY_GROUNDED = "partially_grounded"  # Some claims supported
    WEAKLY_GROUNDED = "weakly_grounded"  # Few claims supported
    UNGROUNDED = "ungrounded"  # No support found


@dataclass
class Claim:
    """A single claim extracted from a response."""

    text: str
    source_support: str | None = None  # Supporting text from source
    grounding_score: float = 0.0
    is_factual: bool = True  # False for opinions/hedged statements


@dataclass
class NumericClaim:
    """A claim containing a numeric value (Phase 3 Enhancement).

    Examples:
        - "Claude scores 92% on MMLU" -> value=92.0, unit="%", entity="Claude", metric="MMLU"
        - "The model achieved 71% success rate" -> value=71.0, unit="%", entity="model", metric="success rate"
    """

    text: str  # Full claim text
    value: float  # The numeric value
    unit: str = ""  # %, $, etc.
    entity: str | None = None  # What/who the number refers to (Claude, GPT-4)
    metric: str | None = None  # What the number measures (MMLU, accuracy)
    context_window: str = ""  # Surrounding text for verification
    is_verified: bool = False
    verification_source: str | None = None
    verification_excerpt: str | None = None


@dataclass
class EntityClaim:
    """A claim about a named entity (Phase 3 Enhancement).

    Examples:
        - "OpenRouter offers free tier for Llama 3" -> entity="OpenRouter", claim_about="free tier"
        - "Anthropic released Claude 3.5" -> entity="Anthropic", claim_about="released Claude 3.5"
    """

    text: str  # Full claim text
    entity: str  # Named entity (company, product, person)
    claim_about: str  # What is being claimed about the entity
    entity_type: str = "unknown"  # company, product, person, model
    is_verified: bool = False
    verification_source: str | None = None


@dataclass
class GroundingResult:
    """Result of grounding validation."""

    overall_score: float  # 0.0 to 1.0
    level: GroundingLevel
    claims: list[Claim]
    ungrounded_claims: list[str]
    grounded_claims: list[str]
    warnings: list[str] = field(default_factory=list)
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
        guidance.extend(f"- {claim}" for claim in self.ungrounded_claims[:5])  # Limit to 5

        guidance.append("\nPlease either:")
        guidance.append("1. Remove or qualify these claims (e.g., 'It appears that...')")
        guidance.append("2. Provide supporting evidence from the source")
        guidance.append("3. Acknowledge uncertainty (e.g., 'I cannot verify...')")

        return "\n".join(guidance)


@dataclass
class EnhancedGroundingResult:
    """Extended grounding result with numeric and entity verification (Phase 3).

    Provides detailed analysis of:
    - Numeric claims and their verification status
    - Entity claims and their grounding
    - Provenance tracking for all claims

    Note: This is a standalone dataclass (not inheriting from GroundingResult)
    to avoid dataclass inheritance complexity.
    """

    # Base grounding fields (same as GroundingResult)
    overall_score: float  # 0.0 to 1.0
    level: GroundingLevel
    claims: list[Claim]
    ungrounded_claims: list[str]
    grounded_claims: list[str]
    warnings: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    # Enhanced fields for numeric/entity verification
    numeric_claims: list[NumericClaim] = field(default_factory=list)
    entity_claims: list[EntityClaim] = field(default_factory=list)
    verified_numeric_count: int = 0
    verified_entity_count: int = 0
    fabricated_numeric_claims: list[str] = field(default_factory=list)
    fabricated_entity_claims: list[str] = field(default_factory=list)

    @property
    def is_acceptable(self) -> bool:
        """Check if grounding level is acceptable for delivery."""
        return self.level in (GroundingLevel.FULLY_GROUNDED, GroundingLevel.PARTIALLY_GROUNDED)

    @property
    def needs_revision(self) -> bool:
        """Check if the response needs revision."""
        return self.level in (GroundingLevel.WEAKLY_GROUNDED, GroundingLevel.UNGROUNDED)

    @property
    def has_fabricated_data(self) -> bool:
        """Check if any fabricated numeric or entity claims detected."""
        return len(self.fabricated_numeric_claims) > 0 or len(self.fabricated_entity_claims) > 0

    @property
    def numeric_verification_rate(self) -> float:
        """Percentage of numeric claims that were verified."""
        total = len(self.numeric_claims)
        return self.verified_numeric_count / total if total > 0 else 1.0

    @property
    def entity_verification_rate(self) -> float:
        """Percentage of entity claims that were verified."""
        total = len(self.entity_claims)
        return self.verified_entity_count / total if total > 0 else 1.0

    def get_fabrication_warnings(self) -> list[str]:
        """Get specific warnings about fabricated data."""
        warnings = [f"FABRICATED METRIC: {claim}" for claim in self.fabricated_numeric_claims]
        warnings.extend(f"UNVERIFIED ENTITY CLAIM: {claim}" for claim in self.fabricated_entity_claims)
        return warnings


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
    GROUNDING_THRESHOLD: ClassVar[float] = 0.4

    # Patterns for hedged/uncertain language (not factual claims)
    HEDGE_PATTERNS: ClassVar[list[str]] = [
        r"\b(might|may|could|possibly|perhaps|likely|probably|seems?|appears?)\b",
        r"\b(I think|I believe|In my opinion|It seems)\b",
        r"\b(approximately|around|about|roughly|estimated)\b",
        r"\b(often|sometimes|usually|generally|typically)\b",
    ]

    # Patterns for citations/references (already grounded)
    CITATION_PATTERNS: ClassVar[list[str]] = [
        r"\[\d+\]",  # [1], [2] style
        r"\(source:.*?\)",  # (source: ...) style
        r"according to",  # Attribution
        r"based on",  # Attribution
    ]

    # Common stop words for similarity calculation
    STOP_WORDS: ClassVar[set[str]] = {
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
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "and",
        "but",
        "or",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
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

        for claim in claims[: self.max_claims_to_check]:
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

    def _extract_claims(self, text: str) -> list[Claim]:
        """Extract factual claims from text.

        Args:
            text: The text to extract claims from

        Returns:
            List of Claim objects
        """
        claims = []

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()

            # Skip if too short
            if len(sentence.split()) < self.min_claim_words:
                continue

            # Skip if it's a question
            if sentence.endswith("?"):
                continue

            # Skip if it's a command/instruction
            if sentence.startswith(("Please", "Note:", "Remember:", "Tip:")):
                continue

            # Check if it's hedged (not a factual claim)
            is_factual = not any(re.search(pattern, sentence, re.IGNORECASE) for pattern in self.HEDGE_PATTERNS)

            # Check if it has citations (already grounded)
            has_citation = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in self.CITATION_PATTERNS)

            claims.append(
                Claim(
                    text=sentence,
                    is_factual=is_factual and not has_citation,
                )
            )

        return claims

    def _calculate_grounding_score(
        self,
        claim: str,
        source: str,
    ) -> tuple[float, str | None]:
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
        source_sentences = re.split(r"(?<=[.!?])\s+", source)
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
        words = re.findall(r"\b[a-z]+\b", text.lower())
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
        if score >= 0.5 and grounded_ratio >= 0.5:
            return GroundingLevel.PARTIALLY_GROUNDED
        if score >= 0.3 or grounded_ratio >= 0.3:
            return GroundingLevel.WEAKLY_GROUNDED
        return GroundingLevel.UNGROUNDED

    def get_stats(self) -> dict[str, Any]:
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


# =============================================================================
# Phase 3: Enhanced Grounding Validator with Numeric/Entity Verification
# =============================================================================


class EnhancedGroundingValidator(GroundingValidator):
    """Enhanced validator with numeric and entity claim verification.

    Phase 3 Enhancement: Verifies specific numbers and entities appear
    in source content, not just word overlap.

    Usage:
        validator = EnhancedGroundingValidator()

        result = await validator.validate_with_provenance(
            response="Claude scores 92% on MMLU benchmark.",
            provenance_store=store,
        )

        if result.has_fabricated_data:
            print(result.get_fabrication_warnings())
    """

    # Patterns for extracting numeric claims
    NUMERIC_PATTERNS: ClassVar[list[re.Pattern]] = [
        # Percentage patterns: "92%", "92.5%", "92 percent"
        re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)", re.IGNORECASE),
        # Currency patterns: "$100", "$1.5M", "100 dollars"
        re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*([KMB])?", re.IGNORECASE),
        re.compile(r"(\d+(?:\.\d+)?)\s*(?:dollars|USD)", re.IGNORECASE),
        # Score patterns: "scored 85", "rating of 4.5"
        re.compile(r"(?:score[ds]?|rating)\s*(?:of\s*)?(\d+(?:\.\d+)?)", re.IGNORECASE),
        # Count patterns: "1000 users", "500 models"
        re.compile(r"(\d+(?:,\d+)*(?:\.\d+)?)\s+(?:users?|models?|tokens?|parameters?)", re.IGNORECASE),
        # Year patterns (for date claims): "in 2024", "since 2023"
        re.compile(r"(?:in|since|from|until)\s+(20\d{2}|19\d{2})", re.IGNORECASE),
    ]

    # Known entity patterns (companies, models, products)
    ENTITY_PATTERNS: ClassVar[list[re.Pattern]] = [
        # AI Companies
        re.compile(r"\b(OpenAI|Anthropic|Google|Meta|Microsoft|Cohere|Mistral|xAI)\b", re.IGNORECASE),
        # AI Models
        re.compile(r"\b(GPT-4|GPT-3\.5|Claude\s*\d*\.?\d*|Llama\s*\d*|Gemini|PaLM|BERT|Mistral)\b", re.IGNORECASE),
        # Platforms
        re.compile(r"\b(OpenRouter|Hugging\s*Face|Azure|AWS|Replicate|Together\s*AI)\b", re.IGNORECASE),
        # Benchmarks
        re.compile(r"\b(MMLU|HellaSwag|ARC|TruthfulQA|GSM8K|HumanEval|MATH|BBH)\b", re.IGNORECASE),
    ]

    # Benchmark names that require numeric verification
    BENCHMARK_NAMES: ClassVar[set[str]] = {
        "mmlu",
        "hellaswag",
        "arc",
        "truthfulqa",
        "gsm8k",
        "humaneval",
        "math",
        "bbh",
        "winogrande",
        "drop",
        "squad",
        "naturalquestions",
        "triviaqa",
        "webqa",
        "coqa",
        "toolbench",
        "bfcl",
        "swe-bench",
    }

    def __init__(
        self,
        grounding_threshold: float = 0.4,
        numeric_tolerance: float = 0.01,
        strict_numeric_mode: bool = True,
    ):
        """Initialize enhanced grounding validator.

        Args:
            grounding_threshold: Minimum similarity for a claim to be grounded
            numeric_tolerance: Tolerance for numeric value matching (0.01 = 1%)
            strict_numeric_mode: If True, all numeric claims must be verified
        """
        super().__init__(grounding_threshold=grounding_threshold)
        self.numeric_tolerance = numeric_tolerance
        self.strict_numeric_mode = strict_numeric_mode

    def extract_numeric_claims(self, text: str) -> list[NumericClaim]:
        """Extract all numeric claims from text.

        Args:
            text: Text to extract numeric claims from

        Returns:
            List of NumericClaim objects
        """
        claims = []
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            for pattern in self.NUMERIC_PATTERNS:
                matches = pattern.finditer(sentence)
                for match in matches:
                    try:
                        # Extract numeric value
                        value_str = match.group(1).replace(",", "")
                        value = float(value_str)

                        # Extract unit if present
                        unit = ""
                        if len(match.groups()) > 1 and match.group(2):
                            unit = match.group(2)
                        elif "%" in sentence[match.start() : match.end() + 5]:
                            unit = "%"

                        # Try to identify entity and metric
                        entity = self._extract_entity_from_context(sentence)
                        metric = self._extract_metric_from_context(sentence)

                        claims.append(
                            NumericClaim(
                                text=sentence,
                                value=value,
                                unit=unit,
                                entity=entity,
                                metric=metric,
                                context_window=sentence,
                            )
                        )
                    except (ValueError, IndexError):
                        continue

        return claims

    def extract_entity_claims(self, text: str) -> list[EntityClaim]:
        """Extract claims about named entities.

        Args:
            text: Text to extract entity claims from

        Returns:
            List of EntityClaim objects
        """
        claims = []
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            for pattern in self.ENTITY_PATTERNS:
                matches = pattern.finditer(sentence)
                for match in matches:
                    entity = match.group(1)
                    entity_type = self._classify_entity(entity)

                    # Extract what is being claimed about the entity
                    claim_about = self._extract_claim_about_entity(sentence, entity)

                    if claim_about:
                        claims.append(
                            EntityClaim(
                                text=sentence,
                                entity=entity,
                                claim_about=claim_about,
                                entity_type=entity_type,
                            )
                        )

        return claims

    def _extract_entity_from_context(self, sentence: str) -> str | None:
        """Extract the entity a number refers to from context."""
        for pattern in self.ENTITY_PATTERNS:
            match = pattern.search(sentence)
            if match:
                return match.group(1)
        return None

    def _extract_metric_from_context(self, sentence: str) -> str | None:
        """Extract the metric a number measures from context."""
        sentence_lower = sentence.lower()
        for benchmark in self.BENCHMARK_NAMES:
            if benchmark in sentence_lower:
                return benchmark.upper()

        # Generic metric patterns
        metric_patterns = [
            r"(?:on|for)\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+(?:benchmark|test|eval)",
            r"(\w+)\s+(?:score|rating|accuracy|success\s+rate)",
        ]

        for pattern in metric_patterns:
            match = re.search(pattern, sentence, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _classify_entity(self, entity: str) -> str:
        """Classify an entity by type."""
        entity_lower = entity.lower()

        companies = {"openai", "anthropic", "google", "meta", "microsoft", "cohere", "mistral", "xai"}
        if entity_lower in companies:
            return "company"

        models = {"gpt-4", "gpt-3.5", "claude", "llama", "gemini", "palm", "bert", "mistral"}
        for model in models:
            if model in entity_lower:
                return "model"

        platforms = {"openrouter", "hugging face", "azure", "aws", "replicate", "together ai"}
        if entity_lower in platforms:
            return "platform"

        benchmarks = self.BENCHMARK_NAMES
        if entity_lower in benchmarks:
            return "benchmark"

        return "unknown"

    def _extract_claim_about_entity(self, sentence: str, entity: str) -> str | None:
        """Extract what is being claimed about an entity."""
        # Remove the entity from the sentence and return the rest as the claim
        claim = sentence.replace(entity, "").strip()
        if len(claim) > 10:  # Meaningful claim
            return claim[:200]  # Truncate long claims
        return None

    def verify_numeric_in_source(
        self,
        claim: NumericClaim,
        source_content: str,
    ) -> bool:
        """Verify that a numeric claim appears in source content.

        Args:
            claim: NumericClaim to verify
            source_content: Source text to check against

        Returns:
            True if the number is found in source with same entity context
        """
        if not source_content:
            return False

        # Extract all numbers from source
        number_pattern = re.compile(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(%|percent)?", re.IGNORECASE)
        source_numbers = []

        for match in number_pattern.finditer(source_content):
            try:
                value_str = match.group(1).replace(",", "")
                value = float(value_str)
                unit = match.group(2) or ""
                # Get surrounding context
                start = max(0, match.start() - 100)
                end = min(len(source_content), match.end() + 100)
                context = source_content[start:end]
                source_numbers.append((value, unit, context))
            except ValueError:
                continue

        # Check if claim's number exists in source
        for source_value, _source_unit, context in source_numbers:
            # Check numeric value match with tolerance
            if abs(source_value - claim.value) <= claim.value * self.numeric_tolerance:
                # If claim has an entity, verify it's in the same context
                if claim.entity:
                    if claim.entity.lower() in context.lower():
                        claim.is_verified = True
                        claim.verification_source = context
                        return True
                else:
                    # No entity specified, just check number exists
                    claim.is_verified = True
                    claim.verification_source = context
                    return True

        return False

    def verify_entity_in_source(
        self,
        claim: EntityClaim,
        source_content: str,
    ) -> bool:
        """Verify that an entity claim is supported by source content.

        Args:
            claim: EntityClaim to verify
            source_content: Source text to check against

        Returns:
            True if entity and claim are found in source
        """
        if not source_content:
            return False

        source_lower = source_content.lower()
        entity_lower = claim.entity.lower()

        # Check if entity exists in source
        if entity_lower not in source_lower:
            return False

        # Check if key claim words exist near entity
        claim_words = set(self._tokenize(claim.claim_about))
        source_words = set(self._tokenize(source_content))

        # At least 30% of claim words should be in source
        common = claim_words & source_words
        if len(common) / len(claim_words) >= 0.3 if claim_words else False:
            claim.is_verified = True
            claim.verification_source = source_content[:500]
            return True

        return False

    async def validate_with_provenance(
        self,
        response: str,
        provenance_store: "ProvenanceStore",
        source_contents: dict[str, str] | None = None,
    ) -> EnhancedGroundingResult:
        """Validate response using provenance store.

        Args:
            response: Response text to validate
            provenance_store: Store with claim provenance data
            source_contents: Optional dict of source_id -> content

        Returns:
            EnhancedGroundingResult with detailed verification
        """
        # First, run standard validation
        basic_result = self.validate(
            source="",  # We'll use provenance instead
            query="",
            response=response,
        )

        # Extract numeric and entity claims
        numeric_claims = self.extract_numeric_claims(response)
        entity_claims = self.extract_entity_claims(response)

        # Build source content from provenance if not provided
        if source_contents is None:
            source_contents = {}
            # Extract content previews from provenance store
            for claim_prov in provenance_store.claims.values():
                if claim_prov.supporting_excerpt:
                    source_contents[claim_prov.source_id or "unknown"] = claim_prov.supporting_excerpt

        # Combine all source content for verification
        all_source_content = "\n".join(source_contents.values())

        # Verify numeric claims
        verified_numeric = 0
        fabricated_numeric = []

        for claim in numeric_claims:
            if self.verify_numeric_in_source(claim, all_source_content):
                verified_numeric += 1
            else:
                fabricated_numeric.append(
                    f"{claim.entity or 'Unknown'}: {claim.value}{claim.unit} ({claim.metric or 'metric'})"
                )

        # Verify entity claims
        verified_entity = 0
        fabricated_entity = []

        for claim in entity_claims:
            if self.verify_entity_in_source(claim, all_source_content):
                verified_entity += 1
            else:
                fabricated_entity.append(f"{claim.entity}: {claim.claim_about[:50]}...")

        # Update grounding level based on verification
        level = (
            GroundingLevel.WEAKLY_GROUNDED
            if (fabricated_numeric or fabricated_entity) and self.strict_numeric_mode
            else basic_result.level
        )

        # Add fabrication warnings
        warnings = list(basic_result.warnings)
        if fabricated_numeric:
            warnings.append(f"{len(fabricated_numeric)} numeric claims could not be verified in sources")
        if fabricated_entity:
            warnings.append(f"{len(fabricated_entity)} entity claims could not be verified")

        return EnhancedGroundingResult(
            overall_score=basic_result.overall_score,
            level=level,
            claims=basic_result.claims,
            ungrounded_claims=basic_result.ungrounded_claims,
            grounded_claims=basic_result.grounded_claims,
            warnings=warnings,
            numeric_claims=numeric_claims,
            entity_claims=entity_claims,
            verified_numeric_count=verified_numeric,
            verified_entity_count=verified_entity,
            fabricated_numeric_claims=fabricated_numeric,
            fabricated_entity_claims=fabricated_entity,
        )

    def validate_against_sources(
        self,
        response: str,
        sources: list[str],
    ) -> EnhancedGroundingResult:
        """Validate response against multiple source contents.

        Args:
            response: Response to validate
            sources: List of source content strings

        Returns:
            EnhancedGroundingResult
        """
        # Combine sources
        all_source_content = "\n\n".join(sources)

        # Standard validation
        basic_result = self.validate(
            source=all_source_content,
            query="",
            response=response,
        )

        # Extract and verify numeric claims
        numeric_claims = self.extract_numeric_claims(response)
        verified_numeric = 0
        fabricated_numeric = []

        for claim in numeric_claims:
            if self.verify_numeric_in_source(claim, all_source_content):
                verified_numeric += 1
            else:
                fabricated_numeric.append(f"{claim.entity or 'Unknown'}: {claim.value}{claim.unit}")

        # Extract and verify entity claims
        entity_claims = self.extract_entity_claims(response)
        verified_entity = 0
        fabricated_entity = []

        for claim in entity_claims:
            if self.verify_entity_in_source(claim, all_source_content):
                verified_entity += 1
            else:
                fabricated_entity.append(f"{claim.entity}: {claim.claim_about[:50]}...")

        # Adjust level based on fabrication
        level = basic_result.level
        if fabricated_numeric and self.strict_numeric_mode:
            level = GroundingLevel.WEAKLY_GROUNDED

        warnings = list(basic_result.warnings)
        if fabricated_numeric:
            warnings.append(f"{len(fabricated_numeric)} numeric claims not found in sources")

        return EnhancedGroundingResult(
            overall_score=basic_result.overall_score,
            level=level,
            claims=basic_result.claims,
            ungrounded_claims=basic_result.ungrounded_claims,
            grounded_claims=basic_result.grounded_claims,
            warnings=warnings,
            numeric_claims=numeric_claims,
            entity_claims=entity_claims,
            verified_numeric_count=verified_numeric,
            verified_entity_count=verified_entity,
            fabricated_numeric_claims=fabricated_numeric,
            fabricated_entity_claims=fabricated_entity,
        )


# Global enhanced validator instance
_enhanced_validator: EnhancedGroundingValidator | None = None


def get_enhanced_grounding_validator() -> EnhancedGroundingValidator:
    """Get the global enhanced grounding validator instance."""
    global _enhanced_validator
    if _enhanced_validator is None:
        _enhanced_validator = EnhancedGroundingValidator()
    return _enhanced_validator


def validate_with_numeric_verification(
    response: str,
    sources: list[str],
) -> EnhancedGroundingResult:
    """Convenience function for enhanced validation with numeric verification.

    Args:
        response: Response to validate
        sources: List of source content strings

    Returns:
        EnhancedGroundingResult
    """
    return get_enhanced_grounding_validator().validate_against_sources(response, sources)


# Convenience functions
_validator: GroundingValidator | None = None


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


# =============================================================================
# Phase 4: Citation Validation for Zero-Hallucination Defense
# =============================================================================


@dataclass
class CitationValidationResult:
    """Result of citation validation.

    Phase 4 Enhancement: Validates that citations actually support claims.
    """

    is_valid: bool
    score: float  # 0.0 to 1.0
    valid_citations: list[str]
    invalid_citations: list[str]
    unverifiable_claims: list[str]
    suggestions: list[str] = field(default_factory=list)


class CitationValidator:
    """Validates that citations support their associated claims.

    Phase 4 Enhancement: Ensures citations in CitedResponse models
    actually correspond to verifiable sources.

    Usage:
        validator = CitationValidator()
        result = await validator.validate_with_citations(
            response=cited_response,
            available_sources=["tool_result_1", "search_result_2"],
        )
    """

    # URL patterns that are considered valid
    VALID_URL_PATTERNS: ClassVar[list[str]] = [
        r"^https?://",  # HTTP/HTTPS URLs
    ]

    # Placeholder URLs that should be rejected
    PLACEHOLDER_PATTERNS: ClassVar[list[str]] = [
        r"example\.com",
        r"placeholder",
        r"test\.test",
        r"localhost",
        r"127\.0\.0\.1",
        r"\[URL\]",
        r"<URL>",
    ]

    def __init__(
        self,
        strict_mode: bool = False,
        require_urls_for_web: bool = True,
    ):
        """Initialize citation validator.

        Args:
            strict_mode: If True, require all claims to have citations
            require_urls_for_web: If True, web citations must have valid URLs
        """
        self.strict_mode = strict_mode
        self.require_urls_for_web = require_urls_for_web

    async def validate_with_citations(
        self,
        response: Any,  # CitedResponse from structured_outputs
        available_sources: list[str] | None = None,
        tool_results: list[dict] | None = None,
    ) -> CitationValidationResult:
        """Validate citations in a CitedResponse.

        Args:
            response: CitedResponse with citations to validate
            available_sources: List of available source IDs
            tool_results: Tool results that can be cited

        Returns:
            CitationValidationResult with validation details
        """
        # Import here to avoid circular dependency
        from app.domain.models.structured_outputs import CitedResponse, SourceType

        valid_citations = []
        invalid_citations = []
        suggestions = []

        # Handle non-CitedResponse inputs
        if not isinstance(response, CitedResponse):
            return CitationValidationResult(
                is_valid=True,
                score=0.5,  # Neutral score for non-cited responses
                valid_citations=[],
                invalid_citations=[],
                unverifiable_claims=[],
                suggestions=["Consider using CitedResponse for better grounding"],
            )

        # No citations provided
        if not response.citations:
            if self.strict_mode:
                return CitationValidationResult(
                    is_valid=False,
                    score=0.0,
                    valid_citations=[],
                    invalid_citations=[],
                    unverifiable_claims=["Response has no citations"],
                    suggestions=["Add citations to support claims"],
                )
            return CitationValidationResult(
                is_valid=True,
                score=0.3,
                valid_citations=[],
                invalid_citations=[],
                unverifiable_claims=[],
                suggestions=["Adding citations would improve response quality"],
            )

        # Validate each citation
        for citation in response.citations:
            is_valid = True
            reason = None

            # Check source type specific requirements
            if citation.source_type == SourceType.WEB:
                if self.require_urls_for_web and not citation.url:
                    is_valid = False
                    reason = "Web citation missing URL"
                elif citation.url:
                    # Validate URL format
                    url_str = str(citation.url)
                    if not self._is_valid_url(url_str):
                        is_valid = False
                        reason = f"Invalid or placeholder URL: {url_str[:50]}"

            elif citation.source_type == SourceType.TOOL_RESULT:
                # Check if tool result exists
                if available_sources and citation.source_id and citation.source_id not in available_sources:
                    is_valid = False
                    reason = f"Referenced tool result not found: {citation.source_id}"

            elif citation.source_type == SourceType.INFERENCE and citation.confidence > 0.7:
                # Inference citations should have low confidence
                suggestions.append(
                    f"Inference citation has high confidence ({citation.confidence}) - consider adding source"
                )

            # Record result
            if is_valid:
                valid_citations.append(citation.text[:100])
            else:
                invalid_citations.append(f"{citation.text[:50]}... ({reason})")

        # Calculate score
        total = len(response.citations)
        valid_count = len(valid_citations)
        score = valid_count / total if total > 0 else 0.0

        # Determine validity
        is_valid = score >= 0.5 or (not self.strict_mode and valid_count > 0)

        return CitationValidationResult(
            is_valid=is_valid,
            score=score,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations,
            unverifiable_claims=[],
            suggestions=suggestions,
        )

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and not a placeholder.

        Args:
            url: URL string to validate

        Returns:
            True if URL is valid
        """
        import re

        # Check for valid URL pattern
        if not any(re.match(pattern, url) for pattern in self.VALID_URL_PATTERNS):
            return False

        # Check for placeholder patterns
        return not any(re.search(pattern, url, re.IGNORECASE) for pattern in self.PLACEHOLDER_PATTERNS)


# Global citation validator instance
_citation_validator: CitationValidator | None = None


def get_citation_validator() -> CitationValidator:
    """Get the global citation validator instance."""
    global _citation_validator
    if _citation_validator is None:
        _citation_validator = CitationValidator()
    return _citation_validator


async def validate_citations(
    response: Any,
    available_sources: list[str] | None = None,
) -> CitationValidationResult:
    """Convenience function to validate citations.

    Args:
        response: CitedResponse to validate
        available_sources: Available source IDs

    Returns:
        CitationValidationResult
    """
    return await get_citation_validator().validate_with_citations(
        response=response,
        available_sources=available_sources,
    )
