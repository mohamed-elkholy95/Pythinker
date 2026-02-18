"""
Task Pattern Learning module.

This module enables learning from task outcomes to improve
future performance through pattern recognition.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskOutcome:
    """Outcome of a completed task for learning."""

    task_id: str
    task_description: str
    task_type: str
    success: bool
    duration_ms: float
    tool_sequence: list[str] = field(default_factory=list)
    error_types: list[str] = field(default_factory=list)
    user_satisfaction: float | None = None  # 0-1 if provided
    context_factors: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TaskPattern:
    """A learned pattern from task outcomes."""

    pattern_id: str
    pattern_type: str  # tool_sequence, error_recovery, success_factor
    description: str
    confidence: float = 0.5
    occurrence_count: int = 0
    success_rate: float = 0.0
    average_duration_ms: float = 0.0
    tool_sequence: list[str] = field(default_factory=list)
    context_factors: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))

    def update_with_outcome(self, outcome: TaskOutcome) -> None:
        """Update pattern with a new outcome."""
        alpha = 0.2  # Learning rate
        self.occurrence_count += 1
        self.last_seen = datetime.now(UTC)

        # Update success rate
        self.success_rate = alpha * (1.0 if outcome.success else 0.0) + (1 - alpha) * self.success_rate

        # Update duration
        self.average_duration_ms = alpha * outcome.duration_ms + (1 - alpha) * self.average_duration_ms

        # Update confidence based on consistency
        self.confidence = min(0.95, self.confidence + 0.05)


@dataclass
class LearnedRecommendation:
    """A recommendation based on learned patterns."""

    recommendation_type: str  # approach, tools, warning
    content: str
    confidence: float
    source_patterns: list[str] = field(default_factory=list)
    priority: int = 1  # 1 = highest


class PatternLearner:
    """Learner for task patterns and outcomes.

    Analyzes completed tasks to identify patterns that
    can improve future task execution.
    """

    # Minimum occurrences before a pattern is considered reliable
    MIN_OCCURRENCES = 3
    # Confidence threshold for making recommendations
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self) -> None:
        """Initialize the pattern learner."""
        self._patterns: dict[str, TaskPattern] = {}
        self._outcomes: list[TaskOutcome] = []
        self._tool_sequence_patterns: dict[str, TaskPattern] = {}
        self._error_patterns: dict[str, TaskPattern] = {}
        self._success_factors: dict[str, TaskPattern] = {}

    def record_outcome(self, outcome: TaskOutcome) -> list[TaskPattern]:
        """Record a task outcome and update patterns.

        Args:
            outcome: The task outcome to record

        Returns:
            List of patterns that were updated or created
        """
        self._outcomes.append(outcome)
        updated_patterns = []

        # Extract and update tool sequence patterns
        if outcome.tool_sequence:
            sequence_key = self._get_sequence_key(outcome.tool_sequence)
            pattern = self._update_tool_sequence_pattern(sequence_key, outcome)
            updated_patterns.append(pattern)

        # Extract and update error patterns
        for error_type in outcome.error_types:
            pattern = self._update_error_pattern(error_type, outcome)
            updated_patterns.append(pattern)

        # Identify success factors
        if outcome.success:
            factors = self._extract_success_factors(outcome)
            for factor in factors:
                pattern = self._update_success_factor(factor, outcome)
                updated_patterns.append(pattern)

        logger.debug(f"Recorded outcome for {outcome.task_id}, updated {len(updated_patterns)} patterns")

        return updated_patterns

    def get_recommendations(
        self,
        task_description: str,
        task_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[LearnedRecommendation]:
        """Get recommendations based on learned patterns.

        Args:
            task_description: Description of the task
            task_type: Optional task type
            context: Optional context factors

        Returns:
            List of recommendations sorted by priority
        """
        recommendations = []

        # Find matching tool sequence patterns
        for pattern in self._tool_sequence_patterns.values():
            if (
                self._pattern_matches_task(pattern, task_description, task_type)
                and pattern.confidence >= self.CONFIDENCE_THRESHOLD
            ):
                rec = LearnedRecommendation(
                    recommendation_type="tools",
                    content=f"Consider using: {', '.join(pattern.tool_sequence)}",
                    confidence=pattern.confidence,
                    source_patterns=[pattern.pattern_id],
                    priority=2,
                )
                recommendations.append(rec)

        # Find matching error patterns for warnings
        for pattern in self._error_patterns.values():
            if (
                self._pattern_matches_task(pattern, task_description, task_type)
                and pattern.occurrence_count >= self.MIN_OCCURRENCES
            ):
                rec = LearnedRecommendation(
                    recommendation_type="warning",
                    content=f"Watch out for: {pattern.description}",
                    confidence=pattern.confidence,
                    source_patterns=[pattern.pattern_id],
                    priority=1,  # Warnings are high priority
                )
                recommendations.append(rec)

        # Find success factors to apply
        for pattern in self._success_factors.values():
            if pattern.success_rate >= 0.7 and pattern.occurrence_count >= self.MIN_OCCURRENCES:
                rec = LearnedRecommendation(
                    recommendation_type="approach",
                    content=f"Apply success factor: {pattern.description}",
                    confidence=pattern.success_rate,
                    source_patterns=[pattern.pattern_id],
                    priority=3,
                )
                recommendations.append(rec)

        # Sort by priority
        recommendations.sort(key=lambda r: r.priority)

        return recommendations

    def get_tool_sequence_for_task(
        self,
        task_type: str,
        min_success_rate: float = 0.6,
    ) -> list[str] | None:
        """Get recommended tool sequence for a task type.

        Args:
            task_type: Type of task
            min_success_rate: Minimum success rate threshold

        Returns:
            Recommended tool sequence if found
        """
        best_pattern = None
        best_score = 0.0

        for pattern in self._tool_sequence_patterns.values():
            if task_type.lower() in pattern.description.lower():
                score = pattern.success_rate * pattern.confidence
                if score > best_score and pattern.success_rate >= min_success_rate:
                    best_score = score
                    best_pattern = pattern

        return best_pattern.tool_sequence if best_pattern else None

    def get_common_errors(
        self,
        task_type: str | None = None,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Get common error patterns.

        Args:
            task_type: Optional task type filter
            limit: Maximum number of errors to return

        Returns:
            List of (error_description, occurrence_rate) tuples
        """
        errors = []

        for pattern in self._error_patterns.values():
            if task_type and task_type.lower() not in pattern.description.lower():
                continue
            errors.append((pattern.description, pattern.occurrence_count))

        # Sort by occurrence count
        errors.sort(key=lambda x: x[1], reverse=True)

        return errors[:limit]

    def get_success_factors(
        self,
        min_success_rate: float = 0.7,
    ) -> list[TaskPattern]:
        """Get identified success factors.

        Args:
            min_success_rate: Minimum success rate threshold

        Returns:
            List of success factor patterns
        """
        factors = [
            p
            for p in self._success_factors.values()
            if p.success_rate >= min_success_rate and p.occurrence_count >= self.MIN_OCCURRENCES
        ]
        factors.sort(key=lambda p: p.success_rate, reverse=True)
        return factors

    def get_statistics(self) -> dict[str, Any]:
        """Get learning statistics."""
        total_outcomes = len(self._outcomes)
        success_count = sum(1 for o in self._outcomes if o.success)

        return {
            "total_outcomes": total_outcomes,
            "success_rate": success_count / total_outcomes if total_outcomes > 0 else 0,
            "tool_sequence_patterns": len(self._tool_sequence_patterns),
            "error_patterns": len(self._error_patterns),
            "success_factors": len(self._success_factors),
            "high_confidence_patterns": sum(
                1 for p in self._patterns.values() if p.confidence >= self.CONFIDENCE_THRESHOLD
            ),
        }

    def _get_sequence_key(self, sequence: list[str]) -> str:
        """Generate a key for a tool sequence."""
        return "->".join(sequence[:5])  # Limit to first 5 tools

    def _update_tool_sequence_pattern(
        self,
        sequence_key: str,
        outcome: TaskOutcome,
    ) -> TaskPattern:
        """Update or create a tool sequence pattern."""
        if sequence_key not in self._tool_sequence_patterns:
            pattern = TaskPattern(
                pattern_id=f"seq_{len(self._tool_sequence_patterns)}",
                pattern_type="tool_sequence",
                description=f"Tool sequence for {outcome.task_type}",
                tool_sequence=outcome.tool_sequence[:5],
            )
            self._tool_sequence_patterns[sequence_key] = pattern
            self._patterns[pattern.pattern_id] = pattern
        else:
            pattern = self._tool_sequence_patterns[sequence_key]

        pattern.update_with_outcome(outcome)
        return pattern

    def _update_error_pattern(
        self,
        error_type: str,
        outcome: TaskOutcome,
    ) -> TaskPattern:
        """Update or create an error pattern."""
        if error_type not in self._error_patterns:
            pattern = TaskPattern(
                pattern_id=f"err_{len(self._error_patterns)}",
                pattern_type="error",
                description=error_type,
            )
            self._error_patterns[error_type] = pattern
            self._patterns[pattern.pattern_id] = pattern
        else:
            pattern = self._error_patterns[error_type]

        pattern.update_with_outcome(outcome)
        return pattern

    def _update_success_factor(
        self,
        factor: str,
        outcome: TaskOutcome,
    ) -> TaskPattern:
        """Update or create a success factor pattern."""
        if factor not in self._success_factors:
            pattern = TaskPattern(
                pattern_id=f"success_{len(self._success_factors)}",
                pattern_type="success_factor",
                description=factor,
            )
            self._success_factors[factor] = pattern
            self._patterns[pattern.pattern_id] = pattern
        else:
            pattern = self._success_factors[factor]

        pattern.update_with_outcome(outcome)
        return pattern

    def _extract_success_factors(self, outcome: TaskOutcome) -> list[str]:
        """Extract success factors from a successful outcome."""
        factors = []

        # Tool combination factors
        if len(outcome.tool_sequence) >= 2:
            factors.append(f"Tool combo: {outcome.tool_sequence[0]}->{outcome.tool_sequence[1]}")

        # Duration factors
        if outcome.duration_ms < 5000:
            factors.append("Fast completion")
        elif outcome.duration_ms < 30000:
            factors.append("Moderate completion time")

        # Context factors
        for key, value in outcome.context_factors.items():
            if isinstance(value, bool) and value:
                factors.append(f"Context: {key}")

        return factors

    def _pattern_matches_task(
        self,
        pattern: TaskPattern,
        task_description: str,
        task_type: str | None,
    ) -> bool:
        """Check if a pattern matches a task."""
        desc_lower = task_description.lower()
        pattern_desc_lower = pattern.description.lower()

        # Check task type match
        if task_type and task_type.lower() in pattern_desc_lower:
            return True

        # Check keyword overlap
        task_words = set(desc_lower.split())
        pattern_words = set(pattern_desc_lower.split())
        overlap = len(task_words & pattern_words)

        return overlap >= 2


# Global pattern learner instance
_learner: PatternLearner | None = None


def get_pattern_learner() -> PatternLearner:
    """Get or create the global pattern learner."""
    global _learner
    if _learner is None:
        _learner = PatternLearner()
    return _learner


def reset_pattern_learner() -> None:
    """Reset the global pattern learner."""
    global _learner
    _learner = None
