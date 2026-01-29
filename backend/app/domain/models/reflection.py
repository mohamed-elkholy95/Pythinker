"""Reflection models for intermediate progress assessment.

These models support the Enhanced Self-Reflection pattern (Phase 2),
enabling course correction during execution rather than only at the end.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReflectionTriggerType(str, Enum):
    """Types of events that can trigger reflection."""
    STEP_INTERVAL = "step_interval"    # Every N steps
    AFTER_ERROR = "after_error"         # After a tool error
    LOW_CONFIDENCE = "low_confidence"   # Confidence dropped below threshold
    PROGRESS_STALL = "progress_stall"   # No meaningful progress
    HIGH_ERROR_RATE = "high_error_rate" # Too many errors
    EXPLICIT = "explicit"               # Explicitly requested


class ReflectionDecision(str, Enum):
    """Possible decisions from reflection."""
    CONTINUE = "continue"       # Proceed as planned
    ADJUST_STRATEGY = "adjust"  # Minor tactical change
    REPLAN = "replan"           # Major replanning needed
    ESCALATE = "escalate"       # Need user input
    ABORT = "abort"             # Cannot complete


@dataclass
class ReflectionTrigger:
    """Configuration for when to trigger reflection."""
    # Step-based triggers
    step_interval: int = 2              # Reflect every N steps
    min_steps_before_first: int = 1     # Don't reflect until this many steps done

    # Error-based triggers
    reflect_after_error: bool = True    # Reflect after any error
    error_rate_threshold: float = 0.5   # Reflect when error rate exceeds this

    # Confidence-based triggers
    confidence_threshold: float = 0.6   # Reflect when confidence drops below

    # Stall detection
    stall_detection: bool = True        # Enable stall detection
    stall_threshold: int = 3            # Actions with no progress before stall

    def should_trigger(
        self,
        steps_completed: int,
        error_count: int,
        total_attempts: int,
        confidence: float = 1.0,
        is_stalled: bool = False,
        last_had_error: bool = False
    ) -> ReflectionTriggerType | None:
        """Determine if reflection should be triggered.

        Args:
            steps_completed: Number of steps completed
            error_count: Total errors encountered
            total_attempts: Total tool invocations
            confidence: Current confidence level
            is_stalled: Whether progress appears stalled
            last_had_error: Whether the last action had an error

        Returns:
            ReflectionTriggerType if triggered, None otherwise
        """
        # Check step interval
        if (steps_completed >= self.min_steps_before_first and
            steps_completed > 0 and
            steps_completed % self.step_interval == 0):
            return ReflectionTriggerType.STEP_INTERVAL

        # Check after error
        if self.reflect_after_error and last_had_error:
            return ReflectionTriggerType.AFTER_ERROR

        # Check error rate
        if total_attempts > 0:
            error_rate = error_count / total_attempts
            if error_rate > self.error_rate_threshold:
                return ReflectionTriggerType.HIGH_ERROR_RATE

        # Check confidence
        if confidence < self.confidence_threshold:
            return ReflectionTriggerType.LOW_CONFIDENCE

        # Check stall
        if self.stall_detection and is_stalled:
            return ReflectionTriggerType.PROGRESS_STALL

        return None


@dataclass
class ProgressMetrics:
    """Metrics tracking execution progress."""
    steps_completed: int = 0
    steps_remaining: int = 0
    total_steps: int = 0

    # Success tracking
    successful_actions: int = 0
    failed_actions: int = 0

    # Time tracking
    started_at: datetime | None = None
    last_progress_at: datetime | None = None

    # Stall detection
    actions_since_progress: int = 0

    # Error details
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate of actions."""
        total = self.successful_actions + self.failed_actions
        if total == 0:
            return 1.0
        return self.successful_actions / total

    @property
    def estimated_progress(self) -> float:
        """Estimate overall progress."""
        if self.total_steps == 0:
            return 0.0
        return self.steps_completed / self.total_steps

    @property
    def error_count(self) -> int:
        """Total error count."""
        return len(self.errors)

    @property
    def is_stalled(self) -> bool:
        """Check if progress appears stalled."""
        return self.actions_since_progress >= 3

    def record_success(self) -> None:
        """Record a successful action."""
        self.successful_actions += 1
        self.actions_since_progress = 0
        self.last_progress_at = datetime.now()

    def record_failure(self, error: str) -> None:
        """Record a failed action."""
        self.failed_actions += 1
        self.errors.append(error)
        # Limit error history
        if len(self.errors) > 20:
            self.errors = self.errors[-10:]

    def record_step_completed(self) -> None:
        """Record a step completion."""
        self.steps_completed += 1
        if self.steps_remaining > 0:
            self.steps_remaining -= 1
        self.actions_since_progress = 0
        self.last_progress_at = datetime.now()

    def record_no_progress(self) -> None:
        """Record an action that made no progress."""
        self.actions_since_progress += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for prompt formatting."""
        return {
            "steps_completed": self.steps_completed,
            "steps_remaining": self.steps_remaining,
            "total_steps": self.total_steps,
            "success_rate": round(self.success_rate * 100, 1),
            "error_count": self.error_count,
            "is_stalled": self.is_stalled,
            "estimated_progress": round(self.estimated_progress * 100, 1),
        }


class ReflectionResult(BaseModel):
    """Result of a reflection assessment."""
    decision: ReflectionDecision = Field(description="The reflection decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in decision")
    progress_assessment: str = Field(description="Assessment of progress")
    issues_identified: list[str] = Field(
        default_factory=list,
        description="Issues identified during reflection"
    )
    strategy_adjustment: str | None = Field(
        default=None,
        description="Strategy adjustment guidance (if decision is ADJUST)"
    )
    replan_reason: str | None = Field(
        default=None,
        description="Reason for replanning (if decision is REPLAN)"
    )
    user_question: str | None = Field(
        default=None,
        description="Question for user (if decision is ESCALATE)"
    )
    summary: str = Field(description="Brief summary of reflection")
    trigger_type: ReflectionTriggerType | None = Field(
        default=None,
        description="What triggered this reflection"
    )


@dataclass
class ReflectionConfig:
    """Configuration for reflection behavior."""
    enabled: bool = True
    trigger: ReflectionTrigger = field(default_factory=ReflectionTrigger)
    max_reflections_per_task: int = 10  # Prevent infinite reflection loops
    min_steps_between_reflections: int = 1  # Minimum steps between reflections
