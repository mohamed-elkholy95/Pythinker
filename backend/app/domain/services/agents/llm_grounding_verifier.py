"""LLM-based grounding verification.

Replaces LettuceDetect with a zero-ML-dependency approach: uses the existing
LLM provider to fact-check response claims against source context.

Architecture:
    LLMGroundingVerifier calls the FAST_MODEL tier via the injected LLM
    interface to extract claims from a response and classify each as
    supported/unsupported/unverifiable. Returns a VerificationResult
    with a hallucination_score (ratio of unsupported claims).

Usage:
    from app.application.providers.grounding_verifier import get_llm_grounding_verifier

    verifier = get_llm_grounding_verifier()
    result = await verifier.verify(
        response_text="The population of France is 69 million.",
        source_context=["France has 67 million people."],
    )
    if result.hallucination_score > 0.4:
        # flag or append disclaimer
        ...
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)

_VERIFICATION_SYSTEM_PROMPT = """\
You are a fact-checking assistant. Given a RESPONSE and SOURCE CONTEXT, extract \
the key factual claims from the response and check each against the source context.

Return a JSON object with a single key "claims" containing an array. Each element:
{
  "claim": "<the factual claim from the response>",
  "verdict": "supported" | "unsupported" | "unverifiable"
}

Rules:
- "supported": the claim is directly backed by the source context
- "unsupported": the claim contradicts the source context or makes specific \
assertions (numbers, dates, names) not found in the source context
- "unverifiable": the claim is subjective, a general statement, or cannot be \
checked against the provided context (e.g., opinions, formatting instructions)
- Only extract factual claims (numbers, dates, names, comparisons, statistics)
- Skip stylistic or structural text (headings, transitions, disclaimers)
- Return ONLY the JSON object, no other text
"""


@dataclass(frozen=True, slots=True)
class FlaggedClaim:
    """A claim flagged during verification."""

    claim_text: str
    verdict: str  # "supported", "unsupported", "unverifiable"
    source_snippet: str | None = None


@dataclass(slots=True)
class VerificationResult:
    """Result of LLM-based grounding verification."""

    hallucination_score: float  # 0.0 (fully supported) to 1.0 (fully unsupported)
    flagged_claims: list[FlaggedClaim] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class LLMGroundingVerifier:
    """LLM-based grounding verifier.

    Uses an existing LLM provider to extract and classify factual claims
    from a response against provided source context. Zero ML dependencies.
    """

    def __init__(
        self,
        llm: LLM,
        min_response_length: int = 200,
        max_claims: int = 20,
    ) -> None:
        self._llm = llm
        self._min_response_length = min_response_length
        self._max_claims = max_claims

    async def verify(
        self,
        response_text: str,
        source_context: list[str],
    ) -> VerificationResult:
        """Verify a response against source context for hallucinations.

        Args:
            response_text: The generated response to verify.
            source_context: List of source text chunks for grounding.

        Returns:
            VerificationResult with hallucination score and flagged claims.
        """
        # Skip short responses
        if len(response_text) < self._min_response_length:
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"Response too short ({len(response_text)} chars < {self._min_response_length})",
            )

        # Skip if no context
        total_context_len = sum(len(c.strip()) for c in source_context)
        if not source_context or total_context_len < 50:
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason="Insufficient source context for grounding",
            )

        try:
            messages = self._build_verification_prompt(response_text, source_context)
            llm_response = await self._llm.ask(messages, tools=None, tool_choice=None)
            content = llm_response.get("content", "")
            return self._parse_verdict(content)
        except Exception as e:
            logger.warning("LLM grounding verification failed: %s", e)
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"Verification error: {type(e).__name__}: {e}",
            )

    def _build_verification_prompt(self, response_text: str, source_context: list[str]) -> list[dict[str, str]]:
        """Build the verification prompt for the LLM."""
        combined_context = "\n\n---\n\n".join(source_context)
        user_message = f"SOURCE CONTEXT:\n{combined_context}\n\nRESPONSE TO VERIFY:\n{response_text}"
        return [
            {"role": "system", "content": _VERIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

    def _parse_verdict(self, llm_content: str) -> VerificationResult:
        """Parse the LLM's JSON verdict into a VerificationResult."""
        try:
            # Strip markdown code fences if present
            content = llm_content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            data = json.loads(content)
            claims_raw = data.get("claims", [])
            if not isinstance(claims_raw, list):
                claims_raw = []

            # Cap claims
            claims_raw = claims_raw[: self._max_claims]

            flagged: list[FlaggedClaim] = []
            total = 0
            unsupported = 0

            for claim in claims_raw:
                if not isinstance(claim, dict):
                    continue
                claim_text = claim.get("claim", "")
                verdict = claim.get("verdict", "unverifiable").lower()
                if verdict not in ("supported", "unsupported", "unverifiable"):
                    verdict = "unverifiable"

                total += 1
                if verdict == "unsupported":
                    unsupported += 1
                    flagged.append(
                        FlaggedClaim(
                            claim_text=claim_text,
                            verdict=verdict,
                            source_snippet=claim.get("source_snippet"),
                        )
                    )

            if total == 0:
                return VerificationResult(hallucination_score=0.0, skipped=True, skip_reason="No claims extracted")

            score = unsupported / total
            logger.info(
                "LLM grounding: %d/%d claims unsupported (score=%.2f)",
                unsupported,
                total,
                score,
            )
            return VerificationResult(hallucination_score=score, flagged_claims=flagged)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse LLM verification response: %s", e)
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"JSON parse error: {e}",
            )
