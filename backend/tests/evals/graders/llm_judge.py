"""
LLM-based graders for agent evaluation.

Uses LLM-as-judge for subjective quality assessment of responses,
plans, and other outputs that require nuanced evaluation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class LLMJudgeResult:
    """Result of LLM-based grading."""

    passed: bool
    score: float  # 0.0 to 1.0
    reasoning: str
    criteria_scores: dict[str, float] = field(default_factory=dict)
    raw_response: str = ""


class LLMJudge:
    """LLM-based grading for subjective quality assessment."""

    DEFAULT_CRITERIA: ClassVar[list[str]] = [
        "relevance",
        "accuracy",
        "completeness",
        "coherence",
    ]

    PLAN_CRITERIA: ClassVar[list[str]] = [
        "feasibility",
        "efficiency",
        "completeness",
        "tool_usage",
    ]

    def __init__(
        self,
        llm,
        criteria: list[str] | None = None,
        passing_threshold: float = 7.0,
    ):
        """Initialize the LLM judge.

        Args:
            llm: LLM client for generating judgments
            criteria: List of criteria to evaluate (default: relevance, accuracy, etc.)
            passing_threshold: Minimum score (out of 10) to pass
        """
        self.llm = llm
        self.criteria = criteria or self.DEFAULT_CRITERIA
        self.passing_threshold = passing_threshold

    async def grade_response(
        self,
        query: str,
        response: str,
        context: str = "",
        reference: str = "",
    ) -> LLMJudgeResult:
        """Grade a response for quality.

        Args:
            query: The original user query
            response: The agent's response to evaluate
            context: Optional context that was available
            reference: Optional reference answer for comparison

        Returns:
            LLMJudgeResult with scores and reasoning
        """
        prompt = self._build_response_grading_prompt(
            query=query,
            response=response,
            context=context,
            reference=reference,
        )

        try:
            result = await self.llm.ask(
                [
                    {"role": "system", "content": "You are an expert evaluator. Be strict but fair."},
                    {"role": "user", "content": prompt},
                ]
            )

            content = result.get("content", "")
            scores = self._parse_scores(content)

            return LLMJudgeResult(
                passed=scores.get("overall", 0) >= self.passing_threshold,
                score=scores.get("overall", 0) / 10.0,
                reasoning=scores.get("reasoning", "No reasoning provided"),
                criteria_scores=scores,
                raw_response=content,
            )

        except Exception as e:
            logger.error(f"LLM judge failed: {e}")
            return LLMJudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Grading failed: {e}",
                criteria_scores={},
            )

    async def grade_plan_quality(
        self,
        task: str,
        plan: dict[str, Any],
        available_tools: list[str] | None = None,
    ) -> LLMJudgeResult:
        """Grade a plan for quality and feasibility.

        Args:
            task: The task the plan is meant to accomplish
            plan: The plan to evaluate
            available_tools: List of available tool names

        Returns:
            LLMJudgeResult with scores and reasoning
        """
        prompt = self._build_plan_grading_prompt(
            task=task,
            plan=plan,
            available_tools=available_tools,
        )

        try:
            result = await self.llm.ask(
                [
                    {
                        "role": "system",
                        "content": "You are an expert plan evaluator. Assess feasibility and efficiency.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            content = result.get("content", "")
            scores = self._parse_scores(content)

            return LLMJudgeResult(
                passed=scores.get("overall", 0) >= self.passing_threshold,
                score=scores.get("overall", 0) / 10.0,
                reasoning=scores.get("reasoning", "No reasoning provided"),
                criteria_scores=scores,
                raw_response=content,
            )

        except Exception as e:
            logger.error(f"LLM judge failed for plan: {e}")
            return LLMJudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Grading failed: {e}",
                criteria_scores={},
            )

    async def grade_tool_selection(
        self,
        task: str,
        selected_tools: list[str],
        available_tools: list[str],
    ) -> LLMJudgeResult:
        """Grade tool selection for appropriateness.

        Args:
            task: The task to accomplish
            selected_tools: Tools that were selected
            available_tools: All available tools

        Returns:
            LLMJudgeResult with scores and reasoning
        """
        prompt = f"""
Evaluate the tool selection for this task.

Task: {task}
Selected Tools: {", ".join(selected_tools)}
Available Tools: {", ".join(available_tools)}

Grade each criterion from 0-10:
- Appropriateness: Are the selected tools suitable for the task?
- Completeness: Are all necessary tools included?
- Efficiency: Is the selection minimal without redundancy?
- Feasibility: Can these tools actually accomplish the task?

Output JSON:
{{
    "appropriateness": <score>,
    "completeness": <score>,
    "efficiency": <score>,
    "feasibility": <score>,
    "overall": <average>,
    "reasoning": "<explanation>"
}}
"""

        try:
            result = await self.llm.ask(
                [
                    {"role": "system", "content": "You are an expert tool selection evaluator."},
                    {"role": "user", "content": prompt},
                ]
            )

            content = result.get("content", "")
            scores = self._parse_scores(content)

            return LLMJudgeResult(
                passed=scores.get("overall", 0) >= self.passing_threshold,
                score=scores.get("overall", 0) / 10.0,
                reasoning=scores.get("reasoning", "No reasoning provided"),
                criteria_scores=scores,
                raw_response=content,
            )

        except Exception as e:
            logger.error(f"LLM judge failed for tool selection: {e}")
            return LLMJudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Grading failed: {e}",
                criteria_scores={},
            )

    async def detect_hallucination(
        self,
        response: str,
        sources: list[str],
    ) -> LLMJudgeResult:
        """Detect potential hallucinations in a response.

        Args:
            response: The response to check
            sources: Source texts that the response should be based on

        Returns:
            LLMJudgeResult where higher score = less hallucination
        """
        prompt = f"""
Check this response for hallucinations (claims not supported by sources).

Response:
{response}

Sources:
{chr(10).join(f"[{i + 1}] {s}" for i, s in enumerate(sources))}

Evaluate:
- Factual_Accuracy: Are all claims supported by the sources?
- Source_Attribution: Are sources properly referenced?
- No_Fabrication: Is there any made-up information?

Output JSON:
{{
    "factual_accuracy": <0-10>,
    "source_attribution": <0-10>,
    "no_fabrication": <0-10>,
    "overall": <average>,
    "hallucinations_found": ["<specific hallucination 1>", ...],
    "reasoning": "<explanation>"
}}
"""

        try:
            result = await self.llm.ask(
                [
                    {"role": "system", "content": "You are a fact-checker. Be strict about unsupported claims."},
                    {"role": "user", "content": prompt},
                ]
            )

            content = result.get("content", "")
            scores = self._parse_scores(content)

            return LLMJudgeResult(
                passed=scores.get("overall", 0) >= self.passing_threshold,
                score=scores.get("overall", 0) / 10.0,
                reasoning=scores.get("reasoning", "No reasoning provided"),
                criteria_scores=scores,
                raw_response=content,
            )

        except Exception as e:
            logger.error(f"Hallucination detection failed: {e}")
            return LLMJudgeResult(
                passed=False,
                score=0.0,
                reasoning=f"Detection failed: {e}",
                criteria_scores={},
            )

    def _build_response_grading_prompt(
        self,
        query: str,
        response: str,
        context: str = "",
        reference: str = "",
    ) -> str:
        """Build the prompt for response grading."""
        context_section = f"\nContext: {context}" if context else ""
        reference_section = f"\nReference Answer: {reference}" if reference else ""

        return f"""
You are an expert evaluator. Grade the following response.

Query: {query}{context_section}
Response: {response}{reference_section}

Grade each criterion from 0-10:
- Relevance: Does the response address the query?
- Accuracy: Is the information correct?
- Completeness: Is the response thorough?
- Coherence: Is the response well-organized?

Output JSON:
{{
    "relevance": <score>,
    "accuracy": <score>,
    "completeness": <score>,
    "coherence": <score>,
    "overall": <average>,
    "reasoning": "<explanation>"
}}
"""

    def _build_plan_grading_prompt(
        self,
        task: str,
        plan: dict[str, Any],
        available_tools: list[str] | None = None,
    ) -> str:
        """Build the prompt for plan grading."""
        tools_section = f"\nAvailable Tools: {', '.join(available_tools)}" if available_tools else ""

        plan_str = json.dumps(plan, indent=2) if isinstance(plan, dict) else str(plan)

        return f"""
You are an expert plan evaluator. Grade this execution plan.

Task: {task}{tools_section}

Plan:
{plan_str}

Grade each criterion from 0-10:
- Feasibility: Can this plan realistically complete the task?
- Efficiency: Is the plan optimally structured?
- Completeness: Does the plan cover all aspects?
- Tool_Usage: Are the right tools selected?

Output JSON:
{{
    "feasibility": <score>,
    "efficiency": <score>,
    "completeness": <score>,
    "tool_usage": <score>,
    "overall": <average>,
    "reasoning": "<explanation>"
}}
"""

    def _parse_scores(self, content: str) -> dict[str, Any]:
        """Parse scores from LLM response.

        Args:
            content: Raw LLM response content

        Returns:
            Dict with parsed scores
        """
        # Try to extract JSON from the response
        try:
            # Look for JSON in the content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Fallback: return empty scores with the reasoning
        return {
            "overall": 0,
            "reasoning": content,
        }


class PairwiseJudge:
    """Compare two responses and determine which is better."""

    def __init__(self, llm):
        """Initialize the pairwise judge.

        Args:
            llm: LLM client for generating judgments
        """
        self.llm = llm

    async def compare(
        self,
        query: str,
        response_a: str,
        response_b: str,
    ) -> dict[str, Any]:
        """Compare two responses and determine the winner.

        Args:
            query: The original query
            response_a: First response
            response_b: Second response

        Returns:
            Dict with winner ('A', 'B', or 'TIE') and reasoning
        """
        prompt = f"""
Compare these two responses to the query.

Query: {query}

Response A:
{response_a}

Response B:
{response_b}

Which response is better? Consider relevance, accuracy, and helpfulness.

Output JSON:
{{
    "winner": "A" or "B" or "TIE",
    "a_score": <0-10>,
    "b_score": <0-10>,
    "reasoning": "<explanation>"
}}
"""

        try:
            result = await self.llm.ask(
                [
                    {"role": "system", "content": "You are a fair judge. Evaluate both responses objectively."},
                    {"role": "user", "content": prompt},
                ]
            )

            content = result.get("content", "")

            # Parse result
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])

        except Exception as e:
            logger.error(f"Pairwise comparison failed: {e}")

        return {
            "winner": "TIE",
            "a_score": 5,
            "b_score": 5,
            "reasoning": "Comparison failed",
        }
