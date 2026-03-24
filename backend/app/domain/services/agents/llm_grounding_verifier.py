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

import asyncio
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
  "verdict": "supported" | "unsupported" | "unverifiable" | "common_knowledge"
}

Rules:
- "supported": the claim is directly backed by the source context
- "unsupported": the claim contradicts the source context or makes specific \
assertions (numbers, dates, names) not found in the source context AND is not \
widely known
- "common_knowledge": the claim states a widely known, well-established fact \
that does not need source backing (e.g., historical dates like "World War II \
ended in 1945", famous events like "AlphaGo beat Lee Sedol in 2016", scientific \
consensus like "DNA is a double helix", well-known product launches, established \
company facts). Use this verdict when a reasonable educated person would accept \
the claim without a citation.
- "unverifiable": the claim is subjective, a general statement, or cannot be \
checked against the provided context (e.g., opinions, formatting instructions)
- Only extract factual claims (numbers, dates, names, comparisons, statistics)
- Skip stylistic or structural text (headings, transitions, disclaimers)
- Return ONLY the JSON object, no other text
"""


class ClaimVerdict:
    """Verdict constants for grounding verification claims."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIABLE = "unverifiable"
    COMMON_KNOWLEDGE = "common_knowledge"

    # All recognised verdicts — used for input normalisation.
    _ALL: frozenset[str] = frozenset({SUPPORTED, UNSUPPORTED, UNVERIFIABLE, COMMON_KNOWLEDGE})


@dataclass(frozen=True, slots=True)
class FlaggedClaim:
    """A claim flagged during verification."""

    claim_text: str
    verdict: str  # See ClaimVerdict constants
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
        timeout: float = 30.0,
    ) -> None:
        self._llm = llm
        self._min_response_length = min_response_length
        self._max_claims = max_claims
        self._timeout = timeout

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
            # Use a dedicated timeout shorter than the main LLM timeout — grounding
            # is a validation side-task and should not consume the full 90s budget.
            llm_response = await asyncio.wait_for(
                self._llm.ask(messages, tools=None, tool_choice=None),
                timeout=self._timeout,
            )
            content = llm_response.get("content", "")
            return self._parse_verdict(content)
        except TimeoutError:
            logger.warning("LLM grounding verification timed out after %.0fs", self._timeout)
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"Verification timed out after {self._timeout:.0f}s",
            )
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

    @staticmethod
    def _is_self_referential_claim(claim_text: str) -> bool:
        """Detect claims about the agent's own actions rather than external facts.

        Self-referential claims like "I compiled a 3,196-word report" or
        "The report includes citations from 10 sources" are meta-statements
        about the agent's output, not factual claims that can be grounded
        against source context. Scoring them as "unsupported" inflates the
        hallucination score with false positives.
        """
        if not claim_text:
            return False
        lower = claim_text.lower()
        # Agent self-reference patterns (first-person actions)
        _self_action_prefixes = (
            "i have ",
            "i've ",
            "i compiled",
            "i created",
            "i wrote",
            "i generated",
            "i produced",
            "i prepared",
            "i delivered",
            "i completed",
            "i analyzed",
            "i researched",
            "i included",
            "i provided",
            "i summarized",
            "i found",
        )
        if any(lower.startswith(p) for p in _self_action_prefixes):
            return True
        # Meta-statements about "the report" / "this report" as subject
        _meta_subjects = (
            "the report ",
            "this report ",
            "the analysis ",
            "this analysis ",
            "the document ",
            "the comparison ",
            "the summary ",
        )
        _meta_verbs = (
            "includes",
            "contains",
            "covers",
            "provides",
            "presents",
            "compares",
            "was compiled",
            "was created",
            "was generated",
            "has been",
            "is a ",
            "is based",
        )
        for subj in _meta_subjects:
            if lower.startswith(subj):
                rest = lower[len(subj) :]
                if any(rest.startswith(v) for v in _meta_verbs):
                    return True
        # "compiled a X-word report" anywhere
        return bool("compiled" in lower and "report" in lower)

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
            self_referential_skipped = 0
            common_knowledge_skipped = 0

            for claim in claims_raw:
                if not isinstance(claim, dict):
                    continue
                claim_text = claim.get("claim", "")
                verdict = claim.get("verdict", ClaimVerdict.UNVERIFIABLE).lower()
                if verdict not in ClaimVerdict._ALL:
                    verdict = ClaimVerdict.UNVERIFIABLE

                # Skip self-referential claims — they are meta-statements about
                # the agent's own output, not verifiable external facts.
                if self._is_self_referential_claim(claim_text):
                    self_referential_skipped += 1
                    continue

                # Skip common knowledge claims — well-established facts that
                # don't need source backing (e.g., historical dates, famous events).
                # Counting these as "unsupported" inflates the hallucination score
                # with false positives and causes alert fatigue.
                if verdict == ClaimVerdict.COMMON_KNOWLEDGE:
                    common_knowledge_skipped += 1
                    continue

                total += 1
                if verdict == ClaimVerdict.UNSUPPORTED:
                    unsupported += 1
                    flagged.append(
                        FlaggedClaim(
                            claim_text=claim_text,
                            verdict=verdict,
                            source_snippet=claim.get("source_snippet"),
                        )
                    )

            if self_referential_skipped > 0 or common_knowledge_skipped > 0:
                logger.info(
                    "LLM grounding: skipped %d self-referential and %d common-knowledge claim(s)",
                    self_referential_skipped,
                    common_knowledge_skipped,
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
