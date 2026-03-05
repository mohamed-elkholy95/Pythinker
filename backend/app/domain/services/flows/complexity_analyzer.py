"""Task complexity analyzer for Tree-of-Thoughts branching decisions.

Analyzes incoming tasks to determine:
- Complexity level (simple, moderate, complex, research)
- Whether multi-path exploration would be beneficial
- Suggested alternative strategies if branching

This enables intelligent routing between linear execution and ToT exploration.
"""

import logging
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.path_state import (
    BranchingDecision,
    ComplexityAnalysis,
    TaskComplexity,
    TreeOfThoughtsConfig,
)
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


COMPLEXITY_ANALYSIS_PROMPT = """Analyze this task for complexity and determine the best execution approach.

## Task:
{task_description}

## Context:
{context}

## Available Tools:
{tools_summary}

---

Analyze and respond with JSON:
{{
    "complexity": "simple" | "moderate" | "complex" | "research",
    "confidence": 0.0-1.0,
    "branching_decision": "linear" | "branch_strategies" | "branch_parameters" | "branch_verification",
    "suggested_strategies": ["strategy 1", "strategy 2", ...],
    "reasoning": "brief explanation",
    "estimated_steps": number
}}

## Complexity Guidelines:
- SIMPLE: Direct action, 1-2 steps, obvious approach (e.g., "read this file")
- MODERATE: Clear task, 3-5 steps, single approach (e.g., "create a simple script")
- COMPLEX: Multi-faceted, 5+ steps, multiple approaches (e.g., "build a web scraper")
- RESEARCH: Information gathering, verification needed (e.g., "compare 3 products")

## Branching Guidelines:
- LINEAR: Simple/moderate tasks with clear single approach
- BRANCH_STRATEGIES: Complex tasks where 2-3 different approaches exist
- BRANCH_PARAMETERS: Same approach but different parameter choices
- BRANCH_VERIFICATION: Main approach + alternative for verification

For "branch_strategies", provide 2-3 distinct approach descriptions.
"""


# Heuristic patterns for quick complexity detection
SIMPLE_PATTERNS = [
    "read ",
    "show ",
    "display ",
    "print ",
    "list ",
    "get ",
    "what is",
    "tell me ",
    "explain ",
    "define ",
    "describe ",
]

MODERATE_PATTERNS = [
    "create ",
    "write ",
    "make ",
    "build a simple",
    "add ",
    "update ",
    "change ",
    "modify ",
    "fix ",
    "edit ",
]

COMPLEX_PATTERNS = [
    "compare ",
    "analyze ",
    "investigate ",
    "research ",
    "evaluate ",
    "design ",
    "architect ",
    "optimize ",
    "refactor ",
    "implement complex",
    "build a system",
    "create a framework",
]

RESEARCH_PATTERNS = [
    "find the best",
    "compare options",
    "research ",
    "which is better",
    "investigate ",
    "explore alternatives",
    "survey ",
    "review ",
]


class TaskComplexityAnalyzer:
    """Analyzes task complexity to determine execution strategy.

    Uses a combination of:
    1. Fast heuristic pattern matching for obvious cases
    2. LLM-based analysis for ambiguous cases

    This enables intelligent routing between linear and multi-path execution.
    """

    def __init__(self, llm: LLM, json_parser: JsonParser, config: TreeOfThoughtsConfig | None = None):
        """Initialize the analyzer.

        Args:
            llm: Language model for complex analysis
            json_parser: Parser for structured responses
            config: Optional configuration
        """
        self.llm = llm
        self.json_parser = json_parser
        self.config = config or TreeOfThoughtsConfig()

    def quick_analyze(self, task: str) -> ComplexityAnalysis | None:
        """Quick heuristic analysis without LLM call.

        Args:
            task: Task description

        Returns:
            ComplexityAnalysis if heuristics are confident, None if LLM needed
        """
        task_lower = task.lower()

        # Check for simple patterns
        if any(pattern in task_lower for pattern in SIMPLE_PATTERNS) and len(task.split()) < 15:
            return ComplexityAnalysis(
                complexity=TaskComplexity.SIMPLE,
                confidence=0.9,
                branching_decision=BranchingDecision.LINEAR,
                reasoning="Simple task detected via pattern matching",
                estimated_steps=2,
            )

        # Check for research patterns
        if any(pattern in task_lower for pattern in RESEARCH_PATTERNS):
            return ComplexityAnalysis(
                complexity=TaskComplexity.RESEARCH,
                confidence=0.85,
                branching_decision=BranchingDecision.BRANCH_STRATEGIES,
                suggested_strategies=[
                    "Web search + official sources",
                    "Multiple search engines comparison",
                    "User reviews + expert opinions",
                ],
                reasoning="Research task detected, multiple sources recommended",
                estimated_steps=5,
            )

        # Check for complex patterns
        if any(pattern in task_lower for pattern in COMPLEX_PATTERNS):
            return ComplexityAnalysis(
                complexity=TaskComplexity.COMPLEX,
                confidence=0.75,
                branching_decision=BranchingDecision.BRANCH_STRATEGIES,
                reasoning="Complex task detected, may benefit from multiple approaches",
                estimated_steps=7,
            )

        # Check for moderate patterns
        if any(pattern in task_lower for pattern in MODERATE_PATTERNS):
            return ComplexityAnalysis(
                complexity=TaskComplexity.MODERATE,
                confidence=0.8,
                branching_decision=BranchingDecision.LINEAR,
                reasoning="Moderate task with clear approach",
                estimated_steps=4,
            )

        # Can't determine with heuristics
        return None

    async def analyze(self, task: str, context: str = "", tools_summary: str = "") -> ComplexityAnalysis:
        """Analyze task complexity using LLM when heuristics insufficient.

        Args:
            task: Task description
            context: Additional context
            tools_summary: Summary of available tools

        Returns:
            ComplexityAnalysis with complexity level and branching decision
        """
        # Try quick analysis first
        quick_result = self.quick_analyze(task)
        if quick_result and quick_result.confidence >= 0.85:
            logger.debug(
                f"Quick complexity analysis: {quick_result.complexity.value} (confidence: {quick_result.confidence})"
            )
            return quick_result

        # Use LLM for detailed analysis
        logger.info("Using LLM for complexity analysis")

        try:
            prompt = COMPLEXITY_ANALYSIS_PROMPT.format(
                task_description=task,
                context=context or "No additional context",
                tools_summary=tools_summary or "Standard web, file, and browser tools",
            )

            messages = [{"role": "user", "content": prompt}]

            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content, tier="C")

            # Parse complexity
            complexity_str = parsed.get("complexity", "moderate").lower()
            try:
                complexity = TaskComplexity(complexity_str)
            except ValueError:
                complexity = TaskComplexity.MODERATE

            # Parse branching decision
            branching_str = parsed.get("branching_decision", "linear").lower()
            try:
                branching = BranchingDecision(branching_str)
            except ValueError:
                branching = BranchingDecision.LINEAR

            return ComplexityAnalysis(
                complexity=complexity,
                confidence=float(parsed.get("confidence", 0.8)),
                branching_decision=branching,
                suggested_strategies=parsed.get("suggested_strategies", []),
                reasoning=parsed.get("reasoning", ""),
                estimated_steps=int(parsed.get("estimated_steps", 5)),
            )

        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}")
            # Default to moderate/linear on error
            return ComplexityAnalysis(
                complexity=TaskComplexity.MODERATE,
                confidence=0.5,
                branching_decision=BranchingDecision.LINEAR,
                reasoning=f"Analysis error, defaulting to linear: {str(e)[:50]}",
            )

    def should_use_tot(self, analysis: ComplexityAnalysis) -> bool:
        """Determine if Tree-of-Thoughts should be used based on analysis.

        Args:
            analysis: Complexity analysis result

        Returns:
            True if ToT should be used
        """
        if not self.config.enabled:
            return False

        # Check complexity threshold
        complexity_order = {
            TaskComplexity.SIMPLE: 0,
            TaskComplexity.MODERATE: 1,
            TaskComplexity.COMPLEX: 2,
            TaskComplexity.RESEARCH: 3,
        }

        task_level = complexity_order.get(analysis.complexity, 0)
        threshold_level = complexity_order.get(self.config.complexity_threshold, 2)

        if task_level < threshold_level:
            return False

        # Check if branching is recommended
        return analysis.should_branch()

    def get_strategy_plans(
        self, analysis: ComplexityAnalysis, max_strategies: int | None = None
    ) -> list[dict[str, Any]]:
        """Generate plan templates for each suggested strategy.

        Args:
            analysis: Complexity analysis with strategies
            max_strategies: Maximum number of strategies to return

        Returns:
            List of strategy plan templates
        """
        max_strats = max_strategies or self.config.max_paths
        strategies = analysis.suggested_strategies[:max_strats]

        if not strategies:
            # Generate default strategies based on complexity
            if analysis.complexity == TaskComplexity.RESEARCH:
                strategies = [
                    "Comprehensive web search with multiple sources",
                    "Focus on official documentation and authoritative sources",
                ]
            elif analysis.complexity == TaskComplexity.COMPLEX:
                strategies = [
                    "Systematic step-by-step approach",
                    "Iterative prototyping approach",
                ]
            else:
                strategies = ["Standard linear execution"]

        return [
            {
                "strategy_id": i + 1,
                "description": strategy,
                "estimated_steps": analysis.estimated_steps,
            }
            for i, strategy in enumerate(strategies)
        ]
