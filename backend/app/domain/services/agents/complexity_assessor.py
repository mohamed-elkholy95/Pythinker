"""Task complexity assessment for dynamic iteration limits."""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ComplexityAssessment:
    """Result of complexity assessment"""
    score: float  # 0.0 (simple) to 1.0 (very complex)
    category: str  # "simple", "medium", "complex", "very_complex"
    recommended_iterations: int
    estimated_tool_calls: int
    reasoning: str


class ComplexityAssessor:
    """Assesses task complexity to set appropriate iteration limits.

    Analyzes:
    - Task description keywords
    - Plan complexity (number of steps, dependencies)
    - Estimated tool usage
    - Multi-task indicators
    """

    # Complexity indicators
    SIMPLE_KEYWORDS = [
        "read", "check", "verify", "show", "display", "list", "find",
    ]

    MEDIUM_KEYWORDS = [
        "create", "write", "modify", "update", "search", "analyze",
    ]

    COMPLEX_KEYWORDS = [
        "build", "develop", "implement", "design", "refactor",
        "research", "investigate", "comprehensive",
    ]

    VERY_COMPLEX_KEYWORDS = [
        "multi-task", "pipeline", "system", "architecture", "full-stack",
        "end-to-end", "comprehensive", "production-grade",
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

        assessment = ComplexityAssessment(
            score=score,
            category=category,
            recommended_iterations=recommended_iterations,
            estimated_tool_calls=estimated_tool_calls,
            reasoning=reasoning,
        )

        logger.info(f"Complexity assessment: {assessment.reasoning}")

        return assessment
