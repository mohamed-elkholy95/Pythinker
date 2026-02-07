"""Chain-of-Verification (CoVe) Implementation.

Based on Meta AI research: "Chain-of-Verification Reduces Hallucination
in Large Language Models" (Dhuliawala et al., 2023)

Key insight: LLMs are more truthful when asked to VERIFY a particular fact
rather than use it in their own answer.

Process:
1. Generate baseline response
2. Plan verification questions for key claims
3. Answer questions independently (key: don't bias with draft)
4. Generate verified response incorporating answers

Research shows CoVe can:
- More than double precision on list generation tasks
- Reduce hallucinated entities from 2.95 to 0.68 on average
- Improve F1 scores on closed-book QA tasks

Usage:
    cove = ChainOfVerification(llm, json_parser)
    result = await cove.verify_and_refine(
        query="Compare the top LLMs for coding",
        response="Claude scores 92% on HumanEval...",
    )

    if result.claims_contradicted > 0:
        return result.verified_response
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class VerificationStatus(str, Enum):
    """Status of a verification check."""

    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"
    NOT_CHECKED = "not_checked"


@dataclass
class VerificationQuestion:
    """A verification question for fact-checking a specific claim."""

    question: str
    claim_being_verified: str
    answer: str | None = None
    status: VerificationStatus = VerificationStatus.NOT_CHECKED
    confidence: float = 0.0


@dataclass
class CoVeResult:
    """Result of Chain-of-Verification process."""

    original_response: str
    verification_questions: list[VerificationQuestion]
    verified_response: str
    claims_verified: int
    claims_contradicted: int
    claims_uncertain: int
    confidence_score: float
    processing_time_ms: float = 0.0

    @property
    def has_contradictions(self) -> bool:
        """Check if any claims were contradicted."""
        return self.claims_contradicted > 0

    @property
    def is_high_confidence(self) -> bool:
        """Check if the result has high confidence."""
        return self.confidence_score >= 0.8 and self.claims_contradicted == 0

    def get_summary(self) -> str:
        """Get a summary of the verification results."""
        total = len(self.verification_questions)
        if total == 0:
            return "No claims to verify"

        return (
            f"Verified: {self.claims_verified}/{total}, "
            f"Contradicted: {self.claims_contradicted}/{total}, "
            f"Uncertain: {self.claims_uncertain}/{total}, "
            f"Confidence: {self.confidence_score:.2f}"
        )


# Prompt templates
VERIFICATION_PLAN_PROMPT = """Analyze the following response and generate verification questions
to fact-check the key claims. Focus on claims that are:
- Specific dates, numbers, statistics, or benchmarks
- Named entities and their attributes (companies, products, people)
- Causal claims and relationships
- Comparative statements between items
- Temporal claims (when things happened)

Response to verify:
---
{response}
---

Generate 3-5 focused verification questions. Each question should:
1. Target ONE specific claim
2. Be answerable with a factual yes/no or specific value
3. Not reference the original response (to avoid bias)

Respond with JSON:
{{
    "questions": [
        {{
            "question": "Specific verification question",
            "claim": "The exact claim being verified from the response"
        }}
    ]
}}
"""

INDEPENDENT_VERIFY_PROMPT = """Answer the following verification question based ONLY on your knowledge.
Do NOT reference any previous context or responses.

CRITICAL: This is an independent fact-check. Answer honestly.

Question: {question}

Respond with JSON:
{{
    "answer": "Your factual answer (be specific)",
    "confidence": 0.0-1.0,
    "can_verify": true/false,
    "explanation": "Brief explanation of your answer"
}}

If you cannot verify the claim, set can_verify to false and explain why.
"""

FINAL_RESPONSE_PROMPT = """You previously generated a response that has been fact-checked.
Review the verification results and produce a corrected version.

ORIGINAL RESPONSE:
---
{original_response}
---

VERIFICATION RESULTS:
{verification_results}

RULES FOR CORRECTION:
1. REMOVE claims that were CONTRADICTED - do not include false information
2. KEEP claims that were VERIFIED - these are confirmed accurate
3. QUALIFY claims that were UNCERTAIN - add hedging language like "reportedly" or remove specific numbers
4. MAINTAIN the original structure, tone, and intent
5. Do NOT add new claims - only correct existing ones
6. If a metric was contradicted, either remove it or mark as "[Unverified]"

Generate the corrected response with hallucinations removed:
"""


class ChainOfVerification:
    """Implements Meta AI's Chain-of-Verification pattern for hallucination reduction.

    The key insight from the research is that LLMs are more accurate when asked
    to verify specific facts than when generating free-form responses. CoVe
    exploits this by:

    1. Generating an initial response
    2. Creating verification questions for key claims
    3. Answering those questions independently (without seeing the original)
    4. Revising the response based on verification results

    The independence in step 3 is crucial - if the model sees its original
    response while verifying, it tends to confirm its own hallucinations.

    Attributes:
        llm: Language model for generation and verification
        json_parser: Parser for structured responses
        max_questions: Maximum verification questions to generate
        parallel_verification: Whether to verify questions in parallel
        min_response_length: Minimum response length to trigger verification
    """

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        max_questions: int = 5,
        parallel_verification: bool = True,
        min_response_length: int = 200,
    ):
        """Initialize Chain-of-Verification.

        Args:
            llm: Language model for generation and verification
            json_parser: Parser for structured JSON responses
            max_questions: Maximum number of verification questions (default: 5)
            parallel_verification: Run verifications in parallel (default: True)
            min_response_length: Minimum response length to trigger CoVe (default: 200)
        """
        self.llm = llm
        self.json_parser = json_parser
        self.max_questions = max_questions
        self.parallel_verification = parallel_verification
        self.min_response_length = min_response_length

        # Statistics
        self._stats = {
            "total_verifications": 0,
            "claims_verified": 0,
            "claims_contradicted": 0,
            "claims_uncertain": 0,
        }

    async def verify_and_refine(
        self,
        query: str,
        response: str,
        context: str | None = None,
        skip_if_short: bool = True,
    ) -> CoVeResult:
        """Run full CoVe pipeline on a response.

        Args:
            query: Original user query (for context)
            response: Response to verify and potentially refine
            context: Optional source context for grounding
            skip_if_short: Skip verification for short responses

        Returns:
            CoVeResult with verified response and metrics
        """
        import time

        start_time = time.time()
        self._stats["total_verifications"] += 1

        # Skip verification for short responses
        if skip_if_short and len(response) < self.min_response_length:
            logger.debug(f"Skipping CoVe: response too short ({len(response)} chars)")
            return CoVeResult(
                original_response=response,
                verification_questions=[],
                verified_response=response,
                claims_verified=0,
                claims_contradicted=0,
                claims_uncertain=0,
                confidence_score=0.7,  # Default confidence for unverified
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 1: Generate verification questions
        logger.info("CoVe Step 1: Planning verification questions...")
        questions = await self._plan_verification(response)

        if not questions:
            logger.info("CoVe: No verification questions generated")
            return CoVeResult(
                original_response=response,
                verification_questions=[],
                verified_response=response,
                claims_verified=0,
                claims_contradicted=0,
                claims_uncertain=0,
                confidence_score=0.8,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 2: Answer questions independently (parallel for speed)
        logger.info(f"CoVe Step 2: Verifying {len(questions)} claims...")
        if self.parallel_verification:
            answered = await self._verify_parallel(questions)
        else:
            answered = await self._verify_sequential(questions)

        # Step 3: Calculate metrics
        verified_count = sum(1 for q in answered if q.status == VerificationStatus.VERIFIED)
        contradicted_count = sum(1 for q in answered if q.status == VerificationStatus.CONTRADICTED)
        uncertain_count = sum(1 for q in answered if q.status == VerificationStatus.UNCERTAIN)

        # Update stats
        self._stats["claims_verified"] += verified_count
        self._stats["claims_contradicted"] += contradicted_count
        self._stats["claims_uncertain"] += uncertain_count

        # Step 4: Generate refined response if needed
        if contradicted_count > 0 or uncertain_count > len(answered) // 2:
            logger.info(f"CoVe Step 3: Refining response ({contradicted_count} contradictions)...")
            verified_response = await self._generate_verified_response(response, answered)
        else:
            logger.info("CoVe: No refinement needed, all claims verified")
            verified_response = response

        # Calculate confidence score
        total = len(answered)
        if total > 0:
            confidence = (verified_count + 0.5 * uncertain_count) / total
        else:
            confidence = 0.8

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"CoVe complete: {verified_count}/{total} verified, "
            f"{contradicted_count} contradicted, {processing_time_ms:.0f}ms"
        )

        return CoVeResult(
            original_response=response,
            verification_questions=answered,
            verified_response=verified_response,
            claims_verified=verified_count,
            claims_contradicted=contradicted_count,
            claims_uncertain=uncertain_count,
            confidence_score=confidence,
            processing_time_ms=processing_time_ms,
        )

    async def _plan_verification(self, response: str) -> list[VerificationQuestion]:
        """Generate verification questions for claims in response.

        Args:
            response: Response to analyze for claims

        Returns:
            List of verification questions
        """
        prompt = VERIFICATION_PLAN_PROMPT.format(response=response[:4000])  # Truncate

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            content = result.get("content", "")
            parsed = await self.json_parser.parse(content)

            questions_data = parsed.get("questions", [])
            questions = []

            for q in questions_data[: self.max_questions]:
                if isinstance(q, dict) and "question" in q:
                    questions.append(
                        VerificationQuestion(
                            question=q["question"],
                            claim_being_verified=q.get("claim", ""),
                        )
                    )

            logger.debug(f"Generated {len(questions)} verification questions")
            return questions

        except Exception as e:
            logger.warning(f"Failed to plan verification: {e}")
            return []

    async def _verify_single(self, question: VerificationQuestion) -> VerificationQuestion:
        """Verify a single claim independently.

        The key here is independence - we don't show the original response
        to avoid confirmation bias.

        Args:
            question: Question to verify

        Returns:
            Question with answer and status filled in
        """
        prompt = INDEPENDENT_VERIFY_PROMPT.format(question=question.question)

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            content = result.get("content", "")
            parsed = await self.json_parser.parse(content)

            question.answer = parsed.get("answer", "")
            question.confidence = float(parsed.get("confidence", 0.5))

            can_verify = parsed.get("can_verify", True)
            explanation = parsed.get("explanation", "").lower()

            # Determine verification status
            if not can_verify:
                question.status = VerificationStatus.UNCERTAIN
            elif "incorrect" in explanation or "false" in explanation or "no" in explanation[:10]:
                question.status = VerificationStatus.CONTRADICTED
            elif "correct" in explanation or "true" in explanation or "yes" in explanation[:10] or question.confidence >= 0.7:
                question.status = VerificationStatus.VERIFIED
            elif question.confidence <= 0.3:
                question.status = VerificationStatus.CONTRADICTED
            else:
                question.status = VerificationStatus.UNCERTAIN

        except Exception as e:
            logger.warning(f"Verification failed for question: {e}")
            question.status = VerificationStatus.UNCERTAIN
            question.answer = f"Verification error: {e}"

        return question

    async def _verify_parallel(self, questions: list[VerificationQuestion]) -> list[VerificationQuestion]:
        """Verify all questions in parallel for speed.

        Args:
            questions: List of questions to verify

        Returns:
            List of questions with verification results
        """
        tasks = [self._verify_single(q) for q in questions]
        return list(await asyncio.gather(*tasks))

    async def _verify_sequential(self, questions: list[VerificationQuestion]) -> list[VerificationQuestion]:
        """Verify questions sequentially.

        Args:
            questions: List of questions to verify

        Returns:
            List of questions with verification results
        """
        for q in questions:
            await self._verify_single(q)
        return questions

    async def _generate_verified_response(
        self,
        original: str,
        questions: list[VerificationQuestion],
    ) -> str:
        """Generate refined response based on verification results.

        Args:
            original: Original response to refine
            questions: Verification questions with results

        Returns:
            Refined response with corrections
        """
        # Format verification results
        results_lines = []
        for q in questions:
            status_emoji = {
                VerificationStatus.VERIFIED: "✓ VERIFIED",
                VerificationStatus.CONTRADICTED: "✗ CONTRADICTED",
                VerificationStatus.UNCERTAIN: "? UNCERTAIN",
            }.get(q.status, "? UNKNOWN")

            results_lines.append(
                f"Claim: \"{q.claim_being_verified}\"\n"
                f"Status: {status_emoji}\n"
                f"Verification: {q.answer or 'N/A'}\n"
            )

        verification_results = "\n---\n".join(results_lines)

        prompt = FINAL_RESPONSE_PROMPT.format(
            original_response=original,
            verification_results=verification_results,
        )

        try:
            result = await self.llm.ask(
                messages=[{"role": "user", "content": prompt}],
            )
            refined = result.get("content", original)

            # Log the reduction
            original_len = len(original)
            refined_len = len(refined)
            logger.info(f"CoVe refinement: {original_len} -> {refined_len} chars")

            return refined

        except Exception as e:
            logger.warning(f"Failed to generate verified response: {e}")
            return original

    def get_stats(self) -> dict[str, Any]:
        """Get verification statistics.

        Returns:
            Dictionary of verification stats
        """
        total = self._stats["total_verifications"]
        claims_total = (
            self._stats["claims_verified"]
            + self._stats["claims_contradicted"]
            + self._stats["claims_uncertain"]
        )

        return {
            **self._stats,
            "verification_rate": f"{claims_total / max(total, 1):.1f} claims/verification",
            "accuracy_rate": f"{self._stats['claims_verified'] / max(claims_total, 1):.1%}",
        }

    def reset_stats(self) -> None:
        """Reset verification statistics."""
        self._stats = {
            "total_verifications": 0,
            "claims_verified": 0,
            "claims_contradicted": 0,
            "claims_uncertain": 0,
        }


# Convenience function
async def verify_response(
    llm: LLM,
    json_parser: JsonParser,
    response: str,
    query: str = "",
) -> CoVeResult:
    """Convenience function to verify a response.

    Args:
        llm: Language model
        json_parser: JSON parser
        response: Response to verify
        query: Original query (optional)

    Returns:
        CoVeResult with verification details
    """
    cove = ChainOfVerification(llm, json_parser)
    return await cove.verify_and_refine(query=query, response=response)
