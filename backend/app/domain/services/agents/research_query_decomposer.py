"""LLM-driven research query decomposer.

Decomposes complex research questions into independent, focused sub-questions
suitable for parallel search execution.  Inspired by MindSearch's graph-based
decomposition but uses structured LLM output (Pydantic) instead of arbitrary
code generation (security risk in MindSearch).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, field_validator

from app.domain.external.llm import LLM
from app.domain.services.prompts.research import DECOMPOSITION_PROMPT

logger = logging.getLogger(__name__)

# ── Validation constants ─────────────────────────────────────────────────
MIN_SUBQUESTION_WORDS = 3
MAX_SUBQUESTION_WORDS = 50
MIN_SUBQUESTIONS = 2
MAX_SUBQUESTIONS = 6

# Patterns indicating compound questions that should be split further
_COMPOUND_PATTERNS = re.compile(
    r"\b(?:and also|as well as|in addition to|along with)\b",
    re.IGNORECASE,
)


# ── Pydantic response model for structured LLM output ────────────────────
class DecomposedQueries(BaseModel):
    """Structured response from LLM decomposition."""

    sub_questions: list[str]

    @field_validator("sub_questions")
    @classmethod
    def validate_sub_questions(cls, v: list[str]) -> list[str]:
        """Ensure each sub-question meets quality criteria."""
        validated: list[str] = []
        for q in v:
            q = q.strip().rstrip("?").strip() + "?"  # Normalize trailing punctuation
            q = re.sub(r"^\d+[\.\)]\s*", "", q)  # Strip leading numbering

            word_count = len(q.split())
            if word_count < MIN_SUBQUESTION_WORDS:
                continue  # Too short — drop silently
            if word_count > MAX_SUBQUESTION_WORDS:
                # Truncate to max words while keeping the question mark
                words = q.split()[:MAX_SUBQUESTION_WORDS]
                q = " ".join(words).rstrip("?") + "?"

            validated.append(q)

        return validated


class ResearchQueryDecomposer:
    """Decomposes a complex research question into independent sub-questions.

    Uses structured LLM output to produce 2-6 focused, independently-searchable
    sub-questions from a single complex query.

    Usage::

        decomposer = ResearchQueryDecomposer()
        subs = await decomposer.decompose("Compare GPT-4, Claude, and Gemini", llm)
        # ["What are GPT-4's key features and pricing?",
        #  "What are Claude's key features and pricing?",
        #  "What are Gemini's key features and pricing?"]
    """

    async def decompose(
        self,
        question: str,
        llm: LLM,
        *,
        context: str | None = None,
    ) -> list[str]:
        """Decompose *question* into independent sub-questions.

        Args:
            question: The complex research question to decompose.
            llm: LLM instance for structured output generation.
            context: Optional extra context (e.g. prior conversation) to
                help the LLM produce more targeted sub-questions.

        Returns:
            A list of 2-6 focused, validated sub-questions.
            Falls back to ``[question]`` if decomposition fails.
        """
        prompt = DECOMPOSITION_PROMPT.format(question=question)
        if context:
            prompt += f"\n\nAdditional context:\n{context}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are a research planning assistant."},
            {"role": "user", "content": prompt},
        ]

        try:
            policy_method = getattr(llm, "ask_structured_with_policy", None)
            if callable(policy_method):
                result = await policy_method(
                    messages=messages,
                    response_model=DecomposedQueries,
                    tier="B",
                )
            else:
                result = await llm.ask_structured(
                    messages=messages,
                    response_model=DecomposedQueries,
                    temperature=0.3,
                    max_tokens=1024,
                )
            sub_questions = result.sub_questions
        except Exception:
            logger.warning(
                "LLM decomposition failed, falling back to original question",
                exc_info=True,
            )
            return [question]

        # Post-validation: enforce cardinality bounds
        if len(sub_questions) < MIN_SUBQUESTIONS:
            logger.info(
                f"Decomposition produced {len(sub_questions)} sub-questions "
                f"(min {MIN_SUBQUESTIONS}), using original question"
            )
            return [question]

        if len(sub_questions) > MAX_SUBQUESTIONS:
            sub_questions = sub_questions[:MAX_SUBQUESTIONS]

        # Drop compound questions that slipped through
        sub_questions = [q for q in sub_questions if not _COMPOUND_PATTERNS.search(q)]

        if len(sub_questions) < MIN_SUBQUESTIONS:
            return [question]

        logger.info(f"Decomposed research question into {len(sub_questions)} sub-questions")
        return sub_questions
