"""Self-Consistency Checker for Hallucination Reduction.

Based on the paper "Self-Consistency Improves Chain of Thought Reasoning
in Language Models" (Wang et al., 2022).

Key insight: By sampling multiple reasoning paths and selecting the most
consistent answer through majority voting, we can significantly reduce
hallucinations and improve accuracy.

The self-consistency approach:
1. Generate multiple (3-5) responses to the same query
2. Extract the key claims/answers from each response
3. Use majority voting to select the most consistent claims
4. Return the consolidated answer with confidence scores

Usage:
    checker = SelfConsistencyChecker(llm, json_parser, num_samples=3)
    result = await checker.check_consistency(
        query="What is the capital of France?",
        context="Optional context for grounding",
    )

    if result.is_high_confidence:
        return result.consensus_answer
    else:
        # Multiple conflicting answers - needs human review
        return result.get_detailed_breakdown()
"""

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class ConsistencyLevel(str, Enum):
    """Level of consistency across sampled responses."""

    UNANIMOUS = "unanimous"  # All samples agree
    STRONG = "strong"  # >80% agreement
    MODERATE = "moderate"  # 50-80% agreement
    WEAK = "weak"  # <50% agreement
    CONFLICTING = "conflicting"  # No clear majority


@dataclass
class ClaimConsistency:
    """Consistency analysis for a single claim."""

    claim: str
    occurrences: int
    total_samples: int
    consistency_ratio: float
    variants: list[str] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        """Check if claim is consistent across samples."""
        return self.consistency_ratio >= 0.5

    @property
    def is_strongly_consistent(self) -> bool:
        """Check if claim is strongly consistent."""
        return self.consistency_ratio >= 0.8


@dataclass
class SelfConsistencyResult:
    """Result of self-consistency checking."""

    query: str
    num_samples: int
    consensus_answer: str
    confidence_score: float
    consistency_level: ConsistencyLevel
    claim_consistencies: list[ClaimConsistency]
    all_responses: list[str]
    processing_time_ms: float = 0.0

    @property
    def is_high_confidence(self) -> bool:
        """Check if result has high confidence."""
        return (
            self.confidence_score >= 0.8
            and self.consistency_level in [ConsistencyLevel.UNANIMOUS, ConsistencyLevel.STRONG]
        )

    @property
    def has_conflicts(self) -> bool:
        """Check if there are conflicting claims."""
        return any(not c.is_consistent for c in self.claim_consistencies)

    def get_consistent_claims(self) -> list[str]:
        """Get claims that are consistent across samples."""
        return [c.claim for c in self.claim_consistencies if c.is_consistent]

    def get_inconsistent_claims(self) -> list[ClaimConsistency]:
        """Get claims with low consistency."""
        return [c for c in self.claim_consistencies if not c.is_consistent]

    def get_summary(self) -> str:
        """Get a summary of the consistency analysis."""
        consistent = sum(1 for c in self.claim_consistencies if c.is_consistent)
        total = len(self.claim_consistencies)
        return (
            f"Consistency: {self.consistency_level.value}, "
            f"Confidence: {self.confidence_score:.2f}, "
            f"Claims: {consistent}/{total} consistent"
        )


# Prompts for self-consistency
CLAIM_EXTRACTION_PROMPT = """Extract the key factual claims from this response.

Response:
---
{response}
---

Extract ALL factual claims as a JSON list. Each claim should be:
1. A single, atomic fact (not a compound statement)
2. Verifiable (something that could be true or false)
3. Specific (includes names, numbers, dates where applicable)

Respond with JSON:
{{
    "claims": ["claim 1", "claim 2", ...],
    "main_answer": "The primary answer to the question"
}}
"""

CONSOLIDATION_PROMPT = """You have analyzed {num_samples} responses to the same question.
Here is the consistency analysis:

Question: {query}

## Consistent Claims (agreed by majority):
{consistent_claims}

## Inconsistent Claims (conflicting across responses):
{inconsistent_claims}

## All Responses:
{all_responses}

---

Generate a consolidated answer that:
1. ONLY includes claims that are consistent across samples
2. Explicitly notes uncertainty for inconsistent claims
3. Does NOT include claims that were contradicted
4. Preserves the factual accuracy of consistent information

Consolidated answer:"""


class SelfConsistencyChecker:
    """Implements self-consistency checking for hallucination reduction.

    The approach samples multiple responses and uses majority voting to
    identify the most reliable claims. This is particularly effective for:
    - Factual questions where there's a single correct answer
    - Numerical queries (dates, statistics, benchmarks)
    - Comparative analyses

    Attributes:
        llm: Language model for generation
        json_parser: Parser for structured responses
        num_samples: Number of samples to generate (default: 3)
        temperature: Temperature for sampling diversity
        consolidate_output: Whether to generate consolidated answer
    """

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        num_samples: int = 3,
        temperature: float = 0.7,
        consolidate_output: bool = True,
    ):
        """Initialize the self-consistency checker.

        Args:
            llm: Language model for generation
            json_parser: Parser for JSON responses
            num_samples: Number of samples to generate (3-5 recommended)
            temperature: Temperature for sampling (higher = more diverse)
            consolidate_output: Whether to consolidate to single answer
        """
        self.llm = llm
        self.json_parser = json_parser
        self.num_samples = min(max(num_samples, 2), 5)  # Clamp to 2-5
        self.temperature = temperature
        self.consolidate_output = consolidate_output

        # Statistics
        self._stats = {
            "total_checks": 0,
            "high_confidence": 0,
            "conflicts_detected": 0,
        }

    async def check_consistency(
        self,
        query: str,
        context: str | None = None,
        system_prompt: str | None = None,
    ) -> SelfConsistencyResult:
        """Run self-consistency check on a query.

        Generates multiple responses and analyzes their consistency.

        Args:
            query: The question/query to answer
            context: Optional context for grounding
            system_prompt: Optional system prompt

        Returns:
            SelfConsistencyResult with consistency analysis
        """
        import time

        start_time = time.time()
        self._stats["total_checks"] += 1

        # Step 1: Generate multiple samples
        logger.info(f"Self-consistency: Generating {self.num_samples} samples...")
        responses = await self._generate_samples(query, context, system_prompt)

        if len(responses) < 2:
            logger.warning("Self-consistency: Not enough samples generated")
            return self._create_fallback_result(query, responses, start_time)

        # Step 2: Extract claims from each response
        logger.info("Self-consistency: Extracting claims from samples...")
        all_claims = await self._extract_claims(responses)

        # Step 3: Analyze consistency across claims
        logger.info("Self-consistency: Analyzing claim consistency...")
        claim_consistencies = self._analyze_consistency(all_claims)

        # Step 4: Determine overall consistency level
        consistency_level = self._calculate_consistency_level(claim_consistencies)
        confidence_score = self._calculate_confidence(claim_consistencies, consistency_level)

        # Step 5: Generate consolidated answer if needed
        if self.consolidate_output and len(claim_consistencies) > 0:
            consensus_answer = await self._generate_consensus(
                query, claim_consistencies, responses
            )
        else:
            # Use the first response if not consolidating
            consensus_answer = responses[0] if responses else ""

        # Update stats
        if confidence_score >= 0.8:
            self._stats["high_confidence"] += 1
        if consistency_level in [ConsistencyLevel.WEAK, ConsistencyLevel.CONFLICTING]:
            self._stats["conflicts_detected"] += 1

        processing_time = (time.time() - start_time) * 1000

        result = SelfConsistencyResult(
            query=query,
            num_samples=len(responses),
            consensus_answer=consensus_answer,
            confidence_score=confidence_score,
            consistency_level=consistency_level,
            claim_consistencies=claim_consistencies,
            all_responses=responses,
            processing_time_ms=processing_time,
        )

        logger.info(f"Self-consistency: {result.get_summary()}")
        return result

    async def _generate_samples(
        self,
        query: str,
        context: str | None,
        system_prompt: str | None,
    ) -> list[str]:
        """Generate multiple response samples in parallel.

        Args:
            query: The query to answer
            context: Optional context
            system_prompt: Optional system prompt

        Returns:
            List of response strings
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = query
        if context:
            user_content = f"Context:\n{context}\n\nQuestion: {query}"
        messages.append({"role": "user", "content": user_content})

        async def generate_one() -> str:
            try:
                response = await self.llm.ask(
                    messages=messages,
                    temperature=self.temperature,
                )
                return response.get("content", "")
            except Exception as e:
                logger.warning(f"Sample generation failed: {e}")
                return ""

        # Generate samples in parallel
        tasks = [generate_one() for _ in range(self.num_samples)]
        responses = await asyncio.gather(*tasks)

        # Filter out empty responses
        return [r for r in responses if r.strip()]

    async def _extract_claims(self, responses: list[str]) -> list[list[str]]:
        """Extract factual claims from each response.

        Args:
            responses: List of response strings

        Returns:
            List of claim lists (one per response)
        """
        async def extract_from_one(response: str) -> list[str]:
            try:
                prompt = CLAIM_EXTRACTION_PROMPT.format(response=response[:3000])
                result = await self.llm.ask(
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                content = result.get("content", "{}")
                parsed = await self.json_parser.parse(content)
                return parsed.get("claims", [])
            except Exception as e:
                logger.warning(f"Claim extraction failed: {e}")
                return []

        tasks = [extract_from_one(r) for r in responses]
        return list(await asyncio.gather(*tasks))

    def _analyze_consistency(self, all_claims: list[list[str]]) -> list[ClaimConsistency]:
        """Analyze consistency of claims across samples.

        Args:
            all_claims: List of claim lists from each sample

        Returns:
            List of ClaimConsistency objects
        """
        if not all_claims:
            return []

        # Normalize and count claims
        claim_counter: Counter = Counter()
        claim_variants: dict[str, list[str]] = {}

        for claims in all_claims:
            for claim in claims:
                normalized = self._normalize_claim(claim)
                claim_counter[normalized] += 1

                if normalized not in claim_variants:
                    claim_variants[normalized] = []
                claim_variants[normalized].append(claim)

        # Build consistency results
        num_samples = len(all_claims)
        results = []

        for normalized, count in claim_counter.items():
            consistency = ClaimConsistency(
                claim=claim_variants[normalized][0],  # Use first variant as canonical
                occurrences=count,
                total_samples=num_samples,
                consistency_ratio=count / num_samples,
                variants=claim_variants[normalized],
            )
            results.append(consistency)

        # Sort by consistency ratio (highest first)
        results.sort(key=lambda c: c.consistency_ratio, reverse=True)
        return results

    def _normalize_claim(self, claim: str) -> str:
        """Normalize a claim for comparison.

        Handles minor variations in wording while preserving meaning.

        Args:
            claim: The claim string

        Returns:
            Normalized claim string
        """
        import re

        # Lowercase
        normalized = claim.lower().strip()

        # Remove common filler words
        fillers = ["the", "a", "an", "is", "are", "was", "were", "has", "have", "been"]
        words = normalized.split()
        words = [w for w in words if w not in fillers]
        normalized = " ".join(words)

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove trailing punctuation
        normalized = normalized.rstrip(".,;:")

        return normalized

    def _calculate_consistency_level(
        self, claim_consistencies: list[ClaimConsistency]
    ) -> ConsistencyLevel:
        """Calculate overall consistency level.

        Args:
            claim_consistencies: List of claim consistency analyses

        Returns:
            ConsistencyLevel enum value
        """
        if not claim_consistencies:
            return ConsistencyLevel.WEAK

        # Calculate average consistency
        avg_ratio = sum(c.consistency_ratio for c in claim_consistencies) / len(claim_consistencies)

        # Check for unanimous agreement
        if all(c.consistency_ratio >= 1.0 for c in claim_consistencies):
            return ConsistencyLevel.UNANIMOUS

        # Check for strong agreement
        if avg_ratio >= 0.8:
            return ConsistencyLevel.STRONG

        # Check for moderate agreement
        if avg_ratio >= 0.5:
            return ConsistencyLevel.MODERATE

        # Check for weak agreement
        if avg_ratio >= 0.3:
            return ConsistencyLevel.WEAK

        return ConsistencyLevel.CONFLICTING

    def _calculate_confidence(
        self,
        claim_consistencies: list[ClaimConsistency],
        consistency_level: ConsistencyLevel,
    ) -> float:
        """Calculate overall confidence score.

        Args:
            claim_consistencies: Claim consistency analyses
            consistency_level: Calculated consistency level

        Returns:
            Confidence score 0.0-1.0
        """
        if not claim_consistencies:
            return 0.5

        # Base confidence on average consistency
        avg_ratio = sum(c.consistency_ratio for c in claim_consistencies) / len(claim_consistencies)

        # Boost for higher consistency levels
        level_boost = {
            ConsistencyLevel.UNANIMOUS: 0.2,
            ConsistencyLevel.STRONG: 0.1,
            ConsistencyLevel.MODERATE: 0.0,
            ConsistencyLevel.WEAK: -0.1,
            ConsistencyLevel.CONFLICTING: -0.2,
        }

        confidence = avg_ratio + level_boost.get(consistency_level, 0.0)

        # Clamp to 0.0-1.0
        return max(0.0, min(1.0, confidence))

    async def _generate_consensus(
        self,
        query: str,
        claim_consistencies: list[ClaimConsistency],
        responses: list[str],
    ) -> str:
        """Generate a consolidated consensus answer.

        Args:
            query: Original query
            claim_consistencies: Analyzed claims
            responses: All original responses

        Returns:
            Consolidated answer string
        """
        # Format consistent claims
        consistent = [c.claim for c in claim_consistencies if c.is_consistent]
        consistent_text = "\n".join(f"- {c}" for c in consistent) if consistent else "None"

        # Format inconsistent claims
        inconsistent = [c for c in claim_consistencies if not c.is_consistent]
        inconsistent_text = "\n".join(
            f"- {c.claim} (appeared in {c.occurrences}/{c.total_samples} samples)"
            for c in inconsistent
        ) if inconsistent else "None"

        # Format all responses
        responses_text = "\n---\n".join(
            f"Response {i+1}:\n{r[:1000]}" for i, r in enumerate(responses)
        )

        prompt = CONSOLIDATION_PROMPT.format(
            num_samples=len(responses),
            query=query,
            consistent_claims=consistent_text,
            inconsistent_claims=inconsistent_text,
            all_responses=responses_text,
        )

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
            )
            return result.get("content", responses[0] if responses else "")
        except Exception as e:
            logger.warning(f"Consensus generation failed: {e}")
            return responses[0] if responses else ""

    def _create_fallback_result(
        self,
        query: str,
        responses: list[str],
        start_time: float,
    ) -> SelfConsistencyResult:
        """Create a fallback result when checking fails.

        Args:
            query: Original query
            responses: Available responses
            start_time: When processing started

        Returns:
            SelfConsistencyResult with limited data
        """
        import time

        return SelfConsistencyResult(
            query=query,
            num_samples=len(responses),
            consensus_answer=responses[0] if responses else "",
            confidence_score=0.5,
            consistency_level=ConsistencyLevel.WEAK,
            claim_consistencies=[],
            all_responses=responses,
            processing_time_ms=(time.time() - start_time) * 1000,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get checker statistics.

        Returns:
            Dictionary of statistics
        """
        total = self._stats["total_checks"]
        return {
            **self._stats,
            "high_confidence_rate": (
                f"{self._stats['high_confidence'] / total:.1%}" if total > 0 else "N/A"
            ),
            "conflict_rate": (
                f"{self._stats['conflicts_detected'] / total:.1%}" if total > 0 else "N/A"
            ),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "total_checks": 0,
            "high_confidence": 0,
            "conflicts_detected": 0,
        }


# Convenience function
async def check_self_consistency(
    llm: LLM,
    json_parser: JsonParser,
    query: str,
    context: str | None = None,
    num_samples: int = 3,
) -> SelfConsistencyResult:
    """Convenience function to run self-consistency check.

    Args:
        llm: Language model
        json_parser: JSON parser
        query: Query to answer
        context: Optional context
        num_samples: Number of samples

    Returns:
        SelfConsistencyResult
    """
    checker = SelfConsistencyChecker(llm, json_parser, num_samples)
    return await checker.check_consistency(query, context)
