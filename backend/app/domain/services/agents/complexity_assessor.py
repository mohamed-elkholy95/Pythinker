"""Task complexity assessment for dynamic iteration limits.

Includes adaptive model selection support for routing steps to
appropriate model tiers based on complexity.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, computed_field

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """LLM model tier for cost-optimized routing.

    Maps to actual model identifiers in Settings.
    Context7 validated: Enum pattern for configuration selection.
    """

    FAST = "fast"  # Haiku-class: summaries, simple transforms, status checks
    BALANCED = "balanced"  # Sonnet-class: planning, standard execution
    POWERFUL = "powerful"  # Opus-class: complex reasoning, architecture


class StepModelRecommendation(BaseModel):
    """Model recommendation for a specific step.

    Context7 validated: Pydantic v2 computed_field pattern.
    """

    step_description: str
    complexity: str  # "simple", "medium", "complex", "very_complex"
    tier: ModelTier

    @computed_field  # Context7: Pydantic v2 @computed_field (not @property)
    @property
    def model_key(self) -> str:
        """Settings key for the recommended model.

        Returns:
            The Settings attribute name (e.g., "fast_model", "balanced_model")
        """
        return f"{self.tier.value}_model"


@dataclass
class ComplexityAssessment:
    """Result of complexity assessment"""

    score: float  # 0.0 (simple) to 1.0 (very complex)
    category: str  # "simple", "medium", "complex", "very_complex"
    recommended_iterations: int
    estimated_tool_calls: int
    reasoning: str
    recommended_phases: list[str] | None = None  # PhaseType values to activate


class ComplexityAssessor:
    """Assesses task complexity to set appropriate iteration limits.

    Analyzes:
    - Task description keywords
    - Plan complexity (number of steps, dependencies)
    - Estimated tool usage
    - Multi-task indicators
    """

    # Complexity indicators
    SIMPLE_KEYWORDS: ClassVar[list[str]] = [
        "read",
        "check",
        "verify",
        "show",
        "display",
        "list",
        "find",
    ]

    MEDIUM_KEYWORDS: ClassVar[list[str]] = [
        "create",
        "write",
        "modify",
        "update",
        "search",
        "analyze",
    ]

    COMPLEX_KEYWORDS: ClassVar[list[str]] = [
        "build",
        "develop",
        "implement",
        "design",
        "refactor",
        "research",
        "investigate",
        "comprehensive",
    ]

    VERY_COMPLEX_KEYWORDS: ClassVar[list[str]] = [
        "multi-task",
        "pipeline",
        "system",
        "architecture",
        "full-stack",
        "end-to-end",
        "comprehensive",
        "production-grade",
    ]

    def assess_task_complexity(
        self,
        task_description: str,
        plan_steps: int | None = None,
        is_multi_task: bool = False,
    ) -> ComplexityAssessment:
        """Assess task complexity.

        Args:
            task_description: User's task description
            plan_steps: Number of steps in plan (if available)
            is_multi_task: Whether this is a multi-task challenge

        Returns:
            ComplexityAssessment with recommendations
        """
        logger.info("Assessing task complexity...")

        task_lower = task_description.lower()

        # Base score from keywords
        score = 0.0
        reasoning_parts = []

        # Check keyword categories
        simple_matches = sum(1 for kw in self.SIMPLE_KEYWORDS if kw in task_lower)
        medium_matches = sum(1 for kw in self.MEDIUM_KEYWORDS if kw in task_lower)
        complex_matches = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in task_lower)
        very_complex_matches = sum(1 for kw in self.VERY_COMPLEX_KEYWORDS if kw in task_lower)

        # Weight keyword matches
        score += simple_matches * 0.1
        score += medium_matches * 0.3
        score += complex_matches * 0.5
        score += very_complex_matches * 0.8

        if simple_matches > 0:
            reasoning_parts.append(f"{simple_matches} simple operation(s)")
        if medium_matches > 0:
            reasoning_parts.append(f"{medium_matches} medium operation(s)")
        if complex_matches > 0:
            reasoning_parts.append(f"{complex_matches} complex operation(s)")
        if very_complex_matches > 0:
            reasoning_parts.append(f"{very_complex_matches} very complex operation(s)")

        # Adjust for plan steps
        if plan_steps:
            if plan_steps <= 3:
                score += 0.1
                reasoning_parts.append(f"{plan_steps} steps (simple)")
            elif plan_steps <= 7:
                score += 0.3
                reasoning_parts.append(f"{plan_steps} steps (medium)")
            elif plan_steps <= 15:
                score += 0.5
                reasoning_parts.append(f"{plan_steps} steps (complex)")
            else:
                score += 0.8
                reasoning_parts.append(f"{plan_steps} steps (very complex)")

        # Multi-task bonus
        if is_multi_task:
            score += 0.3
            reasoning_parts.append("multi-task challenge")

        # Task length indicator
        word_count = len(task_description.split())
        if word_count > 100:
            score += 0.2
            reasoning_parts.append("detailed description")

        # Normalize to 0.0-1.0
        score = min(1.0, score)

        # Categorize
        if score < 0.25:
            category = "simple"
            recommended_iterations = 50
            estimated_tool_calls = 10
        elif score < 0.5:
            category = "medium"
            recommended_iterations = 100
            estimated_tool_calls = 25
        elif score < 0.75:
            category = "complex"
            recommended_iterations = 200
            estimated_tool_calls = 50
        else:
            category = "very_complex"
            recommended_iterations = 300
            estimated_tool_calls = 100

        # Build reasoning
        reasoning = f"Complexity: {category} ({score:.2f}). " + ", ".join(reasoning_parts)

        # Select recommended phases based on complexity
        from app.domain.services.flows.phase_registry import select_phases_for_complexity

        recommended_phases = [p.value for p in select_phases_for_complexity(score)]

        assessment = ComplexityAssessment(
            score=score,
            category=category,
            recommended_iterations=recommended_iterations,
            estimated_tool_calls=estimated_tool_calls,
            reasoning=reasoning,
            recommended_phases=recommended_phases,
        )

        logger.info(f"Complexity assessment: {assessment.reasoning}")

        return assessment

    def recommend_model_tier(self, step_description: str, complexity_category: str | None = None) -> ModelTier:
        """Recommend model tier for a specific step.

        Args:
            step_description: The step description to analyze
            complexity_category: Optional pre-computed complexity ("simple", "medium", etc.)

        Returns:
            Recommended ModelTier (FAST, BALANCED, or POWERFUL)

        Context7: Uses Pydantic v2 StepModelRecommendation internally.
        """
        step_lower = step_description.lower()

        # Fast tier: summaries, lists, simple data transforms, status checks
        fast_keywords = {
            "summarize",
            "summary",
            "list",
            "format",
            "status",
            "count",
            "show",
            "display",
            "get",
            "fetch",
        }
        if any(kw in step_lower for kw in fast_keywords):
            return ModelTier.FAST

        # Powerful tier: architecture, refactoring, debugging, design
        powerful_keywords = {
            "architect",
            "architecture",
            "refactor",
            "debug",
            "design",
            "optimize",
            "analyze deeply",
            "research",
            "investigate",
            "complex analysis",
        }
        if any(kw in step_lower for kw in powerful_keywords):
            return ModelTier.POWERFUL

        # Use complexity category if provided
        if complexity_category:
            if complexity_category in ("simple", "medium"):
                return ModelTier.BALANCED  # Default for most cases
            if complexity_category in ("complex", "very_complex"):
                return ModelTier.POWERFUL

        # Default: balanced tier for standard execution
        return ModelTier.BALANCED
