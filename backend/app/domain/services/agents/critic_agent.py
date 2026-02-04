"""Critic agent for quality gate pattern.

This module implements a lightweight CriticAgent for self-correction loops.
The critic reviews outputs against tasks and criteria, providing
approval/rejection decisions with structured feedback.

Usage:
    critic = CriticAgent(session_id="session_123", llm=llm_instance)

    # Review a single output
    result = await critic.review(
        output="The capital of France is Paris.",
        task="What is the capital of France?",
        criteria=["accuracy", "completeness"]
    )

    if result.approved:
        # Output is good, proceed
        pass
    else:
        # Use result.feedback, result.issues, result.suggestions to improve
        pass
"""

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CriticResult(BaseModel):
    """Result of a critic review.

    Attributes:
        approved: Whether the output meets all criteria and should be accepted.
        feedback: Overall assessment or explanation of the decision.
        issues: List of specific problems found in the output.
        suggestions: List of actionable improvements.
        score: Optional quality score (0.0 to 1.0).
    """

    approved: bool
    feedback: str
    issues: list[str] = []
    suggestions: list[str] = []
    score: float | None = None


class CriticAgent:
    """Critic agent for self-correction loop.

    The CriticAgent reviews generated outputs against the original task
    and optional criteria. It provides structured feedback that can be
    used to improve outputs in an iterative refinement process.

    This implements the "Quality Gate Pattern" where outputs are validated
    before being delivered to the user.

    Attributes:
        session_id: The session identifier for tracking.
        llm: Language model for review operations.
        SYSTEM_PROMPT: Class attribute with critic instructions.
    """

    SYSTEM_PROMPT = """You are a quality critic. Review the given output against the task and criteria.

Return a JSON object with:
- "approved": boolean (true if output meets all criteria)
- "feedback": string (overall assessment)
- "issues": array of strings (specific problems found)
- "suggestions": array of strings (how to improve)

Be strict but fair. Focus on accuracy, completeness, and relevance.

IMPORTANT: Return ONLY valid JSON, no additional text or explanation."""

    def __init__(self, session_id: str, llm: Any) -> None:
        """Initialize the CriticAgent.

        Args:
            session_id: The session identifier for this critic.
            llm: Language model instance that implements chat() method.
        """
        self.session_id = session_id
        self.llm = llm

    async def review(
        self,
        output: str,
        task: str,
        criteria: list[str] | None = None,
    ) -> CriticResult:
        """Review an output against a task and criteria.

        Args:
            output: The generated output to review.
            task: The original task/question the output should address.
            criteria: Optional list of criteria to evaluate against.

        Returns:
            CriticResult with approval status and feedback.
        """
        logger.debug(
            "Critic reviewing output for session %s, task: %s",
            self.session_id,
            task[:50] if task else "empty",
        )

        # Build the user message
        user_content = self._build_user_prompt(output, task, criteria)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # Call the LLM
        response = await self.llm.chat(messages)

        # Extract content from response
        content = self._extract_content(response)

        # Parse the response
        result = self._parse_response(content)

        logger.debug(
            "Critic review complete: approved=%s, issues=%d",
            result.approved,
            len(result.issues),
        )

        return result

    async def review_batch(
        self,
        outputs: list[dict[str, str]],
        criteria: list[str] | None = None,
    ) -> list[CriticResult]:
        """Review multiple outputs in batch.

        Each item in the outputs list should be a dictionary with
        'output' and 'task' keys.

        Args:
            outputs: List of dicts with 'output' and 'task' keys.
            criteria: Optional criteria to apply to all reviews.

        Returns:
            List of CriticResult objects, one per input.
        """
        results = []
        for item in outputs:
            result = await self.review(
                output=item["output"],
                task=item["task"],
                criteria=criteria,
            )
            results.append(result)
        return results

    def _build_user_prompt(
        self,
        output: str,
        task: str,
        criteria: list[str] | None,
    ) -> str:
        """Build the user prompt for review.

        Args:
            output: The output to review.
            task: The original task.
            criteria: Optional criteria list.

        Returns:
            Formatted prompt string.
        """
        parts = [
            f"## Task\n{task}",
            f"## Output to Review\n{output}",
        ]

        if criteria:
            criteria_text = "\n".join(f"- {c}" for c in criteria)
            parts.append(f"## Criteria\n{criteria_text}")

        return "\n\n".join(parts)

    def _extract_content(self, response: Any) -> str:
        """Extract content string from LLM response.

        Handles both object with content attribute and plain string responses.

        Args:
            response: The LLM response (object or string).

        Returns:
            Content string.
        """
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _parse_response(self, content: str) -> CriticResult:
        """Parse LLM response into CriticResult.

        Handles:
        - Plain JSON
        - JSON wrapped in markdown code blocks
        - Non-JSON fallback

        Args:
            content: Raw response content from LLM.

        Returns:
            Parsed CriticResult.
        """
        # Try to extract JSON from markdown code blocks
        cleaned_content = self._strip_markdown_code_blocks(content)

        try:
            parsed = json.loads(cleaned_content)
            return CriticResult(
                approved=parsed.get("approved", False),
                feedback=parsed.get("feedback", ""),
                issues=parsed.get("issues", []),
                suggestions=parsed.get("suggestions", []),
                score=parsed.get("score"),
            )
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse critic response as JSON, using fallback"
            )
            return self._fallback_parse(content)

    def _strip_markdown_code_blocks(self, content: str) -> str:
        """Strip markdown code blocks from content.

        Handles:
        - ```json ... ```
        - ``` ... ```
        - Content without code blocks

        Args:
            content: Raw content possibly with code blocks.

        Returns:
            Content with code blocks stripped.
        """
        # Pattern for code blocks with or without language tag
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(code_block_pattern, content)

        if match:
            return match.group(1).strip()

        return content.strip()

    def _fallback_parse(self, content: str) -> CriticResult:
        """Fallback parsing for non-JSON responses.

        Attempts to infer approval from language sentiment.

        Args:
            content: Non-JSON response content.

        Returns:
            CriticResult with inferred values.
        """
        content_lower = content.lower()

        # Look for approval indicators
        positive_indicators = [
            "good",
            "correct",
            "accurate",
            "complete",
            "approved",
            "pass",
            "valid",
            "well done",
            "looks good",
        ]
        negative_indicators = [
            "bad",
            "incorrect",
            "inaccurate",
            "incomplete",
            "rejected",
            "fail",
            "invalid",
            "needs improvement",
            "issue",
            "problem",
        ]

        positive_count = sum(1 for p in positive_indicators if p in content_lower)
        negative_count = sum(1 for n in negative_indicators if n in content_lower)

        # Default to approved if more positive than negative
        approved = positive_count >= negative_count

        return CriticResult(
            approved=approved,
            feedback=content[:500] if content else "Unable to parse review response",
            issues=[],
            suggestions=[],
            score=None,
        )
