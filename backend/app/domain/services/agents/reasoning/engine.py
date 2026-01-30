"""
Chain-of-Thought Reasoning Engine.

This module provides explicit structured reasoning before agent decisions,
enabling better traceability, decision quality, and debugging.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.domain.external.llm import LLM
from app.domain.models.thought import (
    Decision,
    ThoughtChain,
    ThoughtQuality,
    ThoughtType,
    ValidationResult,
)
from app.domain.services.agents.reasoning.thought_chain import ThoughtChainBuilder

logger = logging.getLogger(__name__)

# Reasoning prompts for structured thinking
REASONING_SYSTEM_PROMPT = """You are a careful reasoner who thinks through problems step by step.

When reasoning, follow this structure:
1. **Observation**: Note relevant facts from the context
2. **Analysis**: Break down the problem into components
3. **Hypothesis**: Form tentative conclusions
4. **Evaluation**: Assess different options
5. **Decision**: State your final decision with confidence

Format your thinking explicitly with these markers:
- [OBSERVATION] for facts you notice
- [ANALYSIS] for breaking down the problem
- [HYPOTHESIS] for tentative conclusions
- [EVALUATION] for comparing options
- [DECISION] for final decisions
- [UNCERTAINTY] for things you're unsure about

Be explicit about your confidence levels (high, medium, low) and cite evidence for your claims."""

TOOL_SELECTION_REASONING_PROMPT = """Given the task and available tools, reason through the best tool selection:

Task: {task}

Available Tools:
{tools}

Current Context:
{context}

Think through:
1. What is the core objective of this task?
2. What information or actions are needed?
3. Which tools can provide the needed capabilities?
4. What are the pros/cons of each relevant tool?
5. What is the most efficient tool choice?

Provide structured reasoning with [OBSERVATION], [ANALYSIS], [EVALUATION], and [DECISION] markers."""

PLAN_REASONING_PROMPT = """Reason through the best approach for this task:

Task: {task}

Context: {context}

Consider:
1. What are the key requirements?
2. What are the main challenges or risks?
3. What approaches are available?
4. What is the optimal sequence of steps?

Provide structured reasoning with explicit markers."""


class ReasoningEngine:
    """Engine for structured Chain-of-Thought reasoning.

    Provides explicit reasoning before decisions for:
    - Tool selection
    - Plan creation
    - Action execution
    - Error recovery
    """

    def __init__(self, llm: LLM, enable_streaming: bool = True) -> None:
        """Initialize the reasoning engine.

        Args:
            llm: The LLM to use for reasoning
            enable_streaming: Whether to enable streaming reasoning output
        """
        self.llm = llm
        self.enable_streaming = enable_streaming
        self._chain_builder = ThoughtChainBuilder()
        self._reasoning_cache: dict[str, ThoughtChain] = {}

    async def think_step_by_step(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        max_steps: int = 5,
    ) -> ThoughtChain:
        """Perform step-by-step reasoning on a problem.

        Args:
            problem: The problem to reason about
            context: Optional context information
            max_steps: Maximum reasoning steps

        Returns:
            Complete thought chain with reasoning
        """
        logger.debug(f"Starting step-by-step reasoning for: {problem[:100]}...")

        # Check cache for similar problems
        cache_key = self._get_cache_key(problem, context)
        if cache_key in self._reasoning_cache:
            logger.debug("Returning cached reasoning chain")
            return self._reasoning_cache[cache_key]

        # Build reasoning prompt
        messages = [
            {"role": "system", "content": REASONING_SYSTEM_PROMPT},
            {"role": "user", "content": self._format_problem_prompt(problem, context)},
        ]

        try:
            # Get reasoning from LLM
            response = await self.llm.ask(messages, tools=None, response_format=None)
            reasoning_text = response.get("content", "")

            # Parse into structured chain
            chain = self._chain_builder.parse_reasoning_text(
                reasoning_text,
                problem,
                context,
            )

            # Cache the result
            self._reasoning_cache[cache_key] = chain

            logger.info(f"Completed reasoning: {len(chain.steps)} steps, confidence: {chain.overall_confidence:.2f}")

            return chain

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            # Return minimal chain on error
            return self._create_fallback_chain(problem, str(e))

    async def think_step_by_step_streaming(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[tuple[str, ThoughtChain | None], None]:
        """Perform streaming step-by-step reasoning.

        Yields chunks of reasoning text as they're generated,
        with the final thought chain at the end.

        Args:
            problem: The problem to reason about
            context: Optional context information

        Yields:
            Tuples of (chunk, chain) where chain is None until final
        """
        if not self.enable_streaming or not hasattr(self.llm, "ask_stream"):
            # Fall back to non-streaming
            chain = await self.think_step_by_step(problem, context)
            yield (chain.get_summary(), chain)
            return

        messages = [
            {"role": "system", "content": REASONING_SYSTEM_PROMPT},
            {"role": "user", "content": self._format_problem_prompt(problem, context)},
        ]

        full_text = ""
        try:
            async for chunk in self.llm.ask_stream(messages, tools=None, response_format=None):
                full_text += chunk
                yield (chunk, None)

            # Parse final chain
            chain = self._chain_builder.parse_reasoning_text(full_text, problem, context)
            yield ("", chain)

        except Exception as e:
            logger.error(f"Streaming reasoning failed: {e}")
            chain = self._create_fallback_chain(problem, str(e))
            yield (f"Error: {e}", chain)

    async def reason_about_tool_selection(
        self,
        task: str,
        available_tools: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[ThoughtChain, Decision]:
        """Reason about which tool to select for a task.

        Args:
            task: The task description
            available_tools: List of available tool schemas
            context: Optional execution context

        Returns:
            Tuple of (reasoning chain, decision)
        """
        # Format tools for prompt
        tools_text = self._format_tools_for_prompt(available_tools[:10])  # Limit tools

        prompt = TOOL_SELECTION_REASONING_PROMPT.format(
            task=task,
            tools=tools_text,
            context=self._format_context(context) if context else "No additional context",
        )

        chain = await self.think_step_by_step(prompt, context)
        decision = self._chain_builder.extract_decision(chain)

        # Validate tool name in decision
        decision = self._validate_tool_decision(decision, available_tools)

        return chain, decision

    async def reason_about_plan(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[ThoughtChain, Decision]:
        """Reason about the best plan for a task.

        Args:
            task: The task description
            context: Optional context

        Returns:
            Tuple of (reasoning chain, decision about approach)
        """
        prompt = PLAN_REASONING_PROMPT.format(
            task=task,
            context=self._format_context(context) if context else "No additional context",
        )

        chain = await self.think_step_by_step(prompt, context)
        decision = self._chain_builder.extract_decision(chain)

        return chain, decision

    def validate_reasoning(self, chain: ThoughtChain) -> ValidationResult:
        """Validate a reasoning chain for quality and completeness.

        Checks for:
        - Logical consistency
        - Evidence support
        - Completeness
        - Decision clarity

        Args:
            chain: The thought chain to validate

        Returns:
            Validation result with issues and suggestions
        """
        issues: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        # Check for empty chain
        if not chain.steps:
            issues.append("Reasoning chain has no steps")
            return ValidationResult(
                is_valid=False,
                issues=issues,
                confidence_score=0.0,
            )

        # Check for observations
        observations = chain.get_thoughts_by_type(ThoughtType.OBSERVATION)
        if not observations:
            warnings.append("No explicit observations noted")
            suggestions.append("Start reasoning with concrete observations from context")

        # Check for analysis
        analyses = chain.get_thoughts_by_type(ThoughtType.ANALYSIS)
        if not analyses:
            warnings.append("No explicit analysis performed")
            suggestions.append("Break down the problem into components")

        # Check for decisions
        decisions = chain.get_thoughts_by_type(ThoughtType.DECISION)
        if not decisions and not chain.final_decision:
            issues.append("No decision reached in reasoning")

        # Check for high uncertainty
        uncertainties = chain.get_uncertainties()
        if len(uncertainties) > len(chain.steps):
            warnings.append("High number of uncertainties relative to reasoning steps")
            suggestions.append("Gather more information to reduce uncertainty")

        # Check thought quality distribution
        all_thoughts = chain.get_all_thoughts()
        low_quality_count = sum(1 for t in all_thoughts if t.quality == ThoughtQuality.LOW)
        if low_quality_count > len(all_thoughts) / 2:
            warnings.append("Majority of thoughts are low quality")
            suggestions.append("Strengthen reasoning with more evidence")

        # Check for circular reasoning
        if self._has_circular_reasoning(chain):
            issues.append("Possible circular reasoning detected")

        # Calculate confidence score
        confidence_score = self._calculate_validation_confidence(chain, issues, warnings)

        is_valid = len(issues) == 0 and confidence_score >= 0.3

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions,
            confidence_score=confidence_score,
        )

    def extract_decision(self, chain: ThoughtChain) -> Decision:
        """Extract the decision from a thought chain.

        Args:
            chain: The thought chain

        Returns:
            Extracted decision
        """
        return self._chain_builder.extract_decision(chain)

    def clear_cache(self) -> None:
        """Clear the reasoning cache."""
        self._reasoning_cache.clear()
        logger.debug("Reasoning cache cleared")

    def _format_problem_prompt(self, problem: str, context: dict[str, Any] | None) -> str:
        """Format a problem for reasoning."""
        prompt = f"Problem: {problem}"
        if context:
            prompt += f"\n\nContext:\n{self._format_context(context)}"
        prompt += "\n\nThink through this step by step, using explicit markers for each type of thought."
        return prompt

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format context dictionary as readable text."""
        lines = []
        for key, value in context.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {', '.join(str(v) for v in value[:5])}")
            elif isinstance(value, dict):
                lines.append(f"- {key}: {{{', '.join(f'{k}: {v}' for k, v in list(value.items())[:3])}}}")
            else:
                lines.append(f"- {key}: {str(value)[:100]}")
        return "\n".join(lines)

    def _format_tools_for_prompt(self, tools: list[dict[str, Any]]) -> str:
        """Format tools for inclusion in prompts."""
        lines = []
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")[:100]
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def _get_cache_key(self, problem: str, context: dict[str, Any] | None) -> str:
        """Generate a cache key for a problem + context."""
        context_str = str(sorted(context.items())) if context else ""
        return f"{problem[:200]}|{context_str[:100]}"

    def _create_fallback_chain(self, problem: str, error: str) -> ThoughtChain:
        """Create a minimal chain when reasoning fails."""
        self._chain_builder.start_chain(problem)
        self._chain_builder.start_step("Error Recovery")
        self._chain_builder.add_thought(
            f"Reasoning failed: {error}",
            ThoughtType.UNCERTAINTY,
            confidence=0.2,
        )
        self._chain_builder.complete_step("Unable to complete reasoning")
        return self._chain_builder.complete_chain("Proceed with default behavior")

    def _validate_tool_decision(
        self,
        decision: Decision,
        available_tools: list[dict[str, Any]],
    ) -> Decision:
        """Validate and correct tool name in decision."""
        tool_names = {t.get("function", {}).get("name", "") for t in available_tools}

        # Check if decision mentions a valid tool
        for name in tool_names:
            if name in decision.action.lower():
                decision.metadata["validated_tool"] = name
                return decision

        # Tool not found - add warning
        decision.risks.append("Tool name not clearly identified in decision")
        decision.confidence *= 0.8  # Reduce confidence

        return decision

    def _has_circular_reasoning(self, chain: ThoughtChain) -> bool:
        """Check for potential circular reasoning patterns."""
        thoughts = chain.get_all_thoughts()
        if len(thoughts) < 4:
            return False

        # Simple check: look for very similar thoughts
        contents = [t.content.lower()[:50] for t in thoughts]
        unique_contents = set(contents)

        return len(unique_contents) < len(contents) * 0.7

    def _calculate_validation_confidence(
        self,
        chain: ThoughtChain,
        issues: list[str],
        warnings: list[str],
    ) -> float:
        """Calculate validation confidence score."""
        score = chain.overall_confidence

        # Penalize for issues
        score -= len(issues) * 0.2

        # Slight penalty for warnings
        score -= len(warnings) * 0.05

        # Bonus for evidence
        thoughts_with_evidence = sum(1 for t in chain.get_all_thoughts() if t.has_evidence())
        score += thoughts_with_evidence * 0.05

        return max(0.0, min(1.0, score))


# Singleton instance for global access
_reasoning_engine: ReasoningEngine | None = None


def get_reasoning_engine(llm: LLM | None = None) -> ReasoningEngine:
    """Get or create the global reasoning engine.

    Args:
        llm: LLM instance (required on first call)

    Returns:
        The reasoning engine instance
    """
    global _reasoning_engine
    if _reasoning_engine is None:
        if llm is None:
            raise ValueError("LLM required to initialize reasoning engine")
        _reasoning_engine = ReasoningEngine(llm)
    return _reasoning_engine


def reset_reasoning_engine() -> None:
    """Reset the global reasoning engine."""
    global _reasoning_engine
    _reasoning_engine = None
