"""Reflection models for intermediate progress assessment.

These models support the Enhanced Self-Reflection pattern (Phase 2),
enabling course correction during execution rather than only at the end.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReflectionTriggerType(str, Enum):
    """Types of events that can trigger reflection."""

    STEP_INTERVAL = "step_interval"  # Every N steps
    AFTER_ERROR = "after_error"  # After a tool error
    LOW_CONFIDENCE = "low_confidence"  # Confidence dropped below threshold
    PROGRESS_STALL = "progress_stall"  # No meaningful progress
    HIGH_ERROR_RATE = "high_error_rate"  # Too many errors
    EXPLICIT = "explicit"  # Explicitly requested

    # Enhanced triggers (Phase 2.5)
    PLAN_DIVERGENCE = "plan_divergence"  # Execution diverged from plan
    PATTERN_CHANGE = "pattern_change"  # Execution pattern changed significantly
    CONFIDENCE_DECAY = "confidence_decay"  # Confidence dropping over time
    USER_REQUESTED = "user_requested"  # User explicitly requested reflection
    QUALITY_DEGRADATION = "quality_degradation"  # Output quality declining


class ReflectionDecision(str, Enum):
    """Possible decisions from reflection."""

    CONTINUE = "continue"  # Proceed as planned
    ADJUST_STRATEGY = "adjust"  # Minor tactical change
    REPLAN = "replan"  # Major replanning needed
    ESCALATE = "escalate"  # Need user input
    ABORT = "abort"  # Cannot complete


@dataclass
class ReflectionTrigger:
    """Configuration for when to trigger reflection."""

    # Step-based triggers
    step_interval: int = 2  # Reflect every N steps
    min_steps_before_first: int = 1  # Don't reflect until this many steps done

    # Error-based triggers
    reflect_after_error: bool = True  # Reflect after any error
    error_rate_threshold: float = 0.5  # Reflect when error rate exceeds this

    # Confidence-based triggers
    confidence_threshold: float = 0.6  # Reflect when confidence drops below

    # Stall detection
    stall_detection: bool = True  # Enable stall detection
    stall_threshold: int = 3  # Actions with no progress before stall

    # Enhanced triggers
    detect_plan_divergence: bool = True  # Detect execution diverging from plan
    detect_pattern_change: bool = True  # Detect execution pattern changes
    detect_confidence_decay: bool = True  # Detect confidence declining over time
    confidence_decay_threshold: float = 0.15  # Min confidence drop to trigger

    # Confidence history for decay detection
    _confidence_history: list[float] = field(default_factory=list)

    def record_confidence(self, confidence: float) -> None:
        """Record a confidence value for decay detection."""
        self._confidence_history.append(confidence)
        # Keep last 10 values
        if len(self._confidence_history) > 10:
            self._confidence_history.pop(0)

    def should_trigger(
        self,
        steps_completed: int,
        error_count: int,
        total_attempts: int,
        confidence: float = 1.0,
        is_stalled: bool = False,
        last_had_error: bool = False,
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
        # Record confidence for decay detection
        self.record_confidence(confidence)

        # Check step interval
        if (
            steps_completed >= self.min_steps_before_first
            and steps_completed > 0
            and steps_completed % self.step_interval == 0
        ):
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

        # Check confidence decay (new)
        if self.detect_confidence_decay:
            decay = self._detect_confidence_decay()
            if decay:
                return ReflectionTriggerType.CONFIDENCE_DECAY

        return None

    def _detect_confidence_decay(self) -> bool:
        """Detect if confidence is declining over time.

        Returns:
            True if significant decay detected
        """
        if len(self._confidence_history) < 3:
            return False

        # Compare recent average to earlier average
        midpoint = len(self._confidence_history) // 2
        early_avg = sum(self._confidence_history[:midpoint]) / midpoint
        recent_avg = sum(self._confidence_history[midpoint:]) / (len(self._confidence_history) - midpoint)

        decay = early_avg - recent_avg
        return decay >= self.confidence_decay_threshold

    def should_trigger_enhanced(
        self,
        steps_completed: int,
        error_count: int,
        total_attempts: int,
        confidence: float = 1.0,
        is_stalled: bool = False,
        last_had_error: bool = False,
        plan_divergence: float = 0.0,
        pattern_change_detected: bool = False,
        user_requested: bool = False,
    ) -> ReflectionTriggerType | None:
        """Enhanced trigger check with additional signals.

        Args:
            steps_completed: Number of steps completed
            error_count: Total errors encountered
            total_attempts: Total tool invocations
            confidence: Current confidence level
            is_stalled: Whether progress appears stalled
            last_had_error: Whether the last action had an error
            plan_divergence: How much execution diverged from plan (0.0-1.0)
            pattern_change_detected: Whether execution pattern changed
            user_requested: Whether user explicitly requested reflection

        Returns:
            ReflectionTriggerType if triggered, None otherwise
        """
        # Check user request first (highest priority)
        if user_requested:
            return ReflectionTriggerType.USER_REQUESTED

        # Check plan divergence
        if self.detect_plan_divergence and plan_divergence > 0.3:
            return ReflectionTriggerType.PLAN_DIVERGENCE

        # Check pattern change
        if self.detect_pattern_change and pattern_change_detected:
            return ReflectionTriggerType.PATTERN_CHANGE

        # Fall back to basic triggers
        return self.should_trigger(
            steps_completed=steps_completed,
            error_count=error_count,
            total_attempts=total_attempts,
            confidence=confidence,
            is_stalled=is_stalled,
            last_had_error=last_had_error,
        )


def calculate_plan_divergence(
    planned_steps: list[str],
    executed_tools: list[str],
) -> float:
    """Calculate how much execution has diverged from the plan.

    Args:
        planned_steps: Step descriptions from the plan
        executed_tools: Tool names that were actually executed

    Returns:
        Divergence score from 0.0 (following plan) to 1.0 (completely diverged)
    """
    if not planned_steps or not executed_tools:
        return 0.0

    # Map tool types mentioned in plan
    plan_tool_patterns = {
        "search": ["search", "find", "look up", "query"],
        "browser": ["browse", "navigate", "visit", "click"],
        "shell": ["run", "execute", "command", "install"],
        "file": ["read", "write", "create file", "edit"],
        "code": ["implement", "code", "function", "class"],
    }

    # Count expected tool types from plan
    expected_types: dict[str, int] = {}
    for step in planned_steps:
        step_lower = step.lower()
        for tool_type, patterns in plan_tool_patterns.items():
            if any(p in step_lower for p in patterns):
                expected_types[tool_type] = expected_types.get(tool_type, 0) + 1

    if not expected_types:
        return 0.0

    # Count actual tool types used
    actual_types: dict[str, int] = {}
    for tool in executed_tools:
        tool_lower = tool.lower()
        for tool_type in plan_tool_patterns:
            if tool_type in tool_lower:
                actual_types[tool_type] = actual_types.get(tool_type, 0) + 1
                break

    # Calculate divergence as difference in distribution
    all_types = set(expected_types.keys()) | set(actual_types.keys())
    total_diff = 0
    total_expected = sum(expected_types.values())

    for tool_type in all_types:
        expected = expected_types.get(tool_type, 0)
        actual = actual_types.get(tool_type, 0)
        total_diff += abs(expected - actual)

    if total_expected == 0:
        return 0.0

    return min(1.0, total_diff / (total_expected * 2))


def detect_pattern_change(
    tool_history: list[str],
    window_size: int = 5,
) -> bool:
    """Detect if execution pattern has changed significantly.

    Looks for sudden shifts in tool usage patterns, which may indicate
    the agent is struggling or has changed approach.

    Args:
        tool_history: List of tool names executed in order
        window_size: Size of comparison windows

    Returns:
        True if significant pattern change detected
    """
    if len(tool_history) < window_size * 2:
        return False

    # Get tool distribution in early vs recent windows
    early_window = tool_history[-window_size * 2 : -window_size]
    recent_window = tool_history[-window_size:]

    early_set = set(early_window)
    recent_set = set(recent_window)

    # Check for significant change in tool diversity
    early_diversity = len(early_set)
    recent_diversity = len(recent_set)

    if early_diversity > 0:
        diversity_change = abs(recent_diversity - early_diversity) / early_diversity
        if diversity_change > 0.5:  # 50% change in diversity
            return True

    # Check for completely new tools
    new_tools = recent_set - early_set
    if len(new_tools) >= 2:  # Multiple new tools
        return True

    # Check for tool repetition (potential loop)
    return recent_diversity == 1 and early_diversity > 1


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

    # Runtime issues (exceptions, missing artifacts) surfaced during execution
    runtime_issues: list[str] = field(default_factory=list)

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
        self.last_progress_at = datetime.now(UTC)

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
        self.last_progress_at = datetime.now(UTC)

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
            "runtime_issue_count": len(self.runtime_issues),
        }


class ReflectionResult(BaseModel):
    """Result of a reflection assessment."""

    decision: ReflectionDecision = Field(description="The reflection decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in decision")
    progress_assessment: str = Field(description="Assessment of progress")
    issues_identified: list[str] = Field(default_factory=list, description="Issues identified during reflection")
    strategy_adjustment: str | None = Field(
        default=None, description="Strategy adjustment guidance (if decision is ADJUST)"
    )
    replan_reason: str | None = Field(default=None, description="Reason for replanning (if decision is REPLAN)")
    user_question: str | None = Field(default=None, description="Question for user (if decision is ESCALATE)")
    summary: str = Field(description="Brief summary of reflection")
    trigger_type: ReflectionTriggerType | None = Field(default=None, description="What triggered this reflection")

    # Enhanced decision tracking
    decision_factors: list[str] = Field(default_factory=list, description="Factors that influenced the decision")
    alternative_decisions: list[str] = Field(default_factory=list, description="Other decisions considered")
    recommended_actions: list[str] = Field(default_factory=list, description="Specific actions recommended")

    @property
    def is_high_confidence(self) -> bool:
        """Check if decision has high confidence (>0.8)."""
        return self.confidence >= 0.8

    @property
    def is_low_confidence(self) -> bool:
        """Check if decision has low confidence (<0.5)."""
        return self.confidence < 0.5

    @property
    def requires_action(self) -> bool:
        """Check if decision requires action (not CONTINUE)."""
        return self.decision != ReflectionDecision.CONTINUE

    def should_override(self, user_confidence_threshold: float = 0.3) -> bool:
        """Check if user should be asked to override low-confidence decisions.

        Args:
            user_confidence_threshold: Threshold below which to ask user

        Returns:
            True if user should be consulted
        """
        return (
            self.decision in (ReflectionDecision.REPLAN, ReflectionDecision.ESCALATE, ReflectionDecision.ABORT)
            and self.confidence < user_confidence_threshold
        )


@dataclass
class ReflectionConfig:
    """Configuration for reflection behavior."""

    enabled: bool = True
    trigger: ReflectionTrigger = field(default_factory=ReflectionTrigger)
    max_reflections_per_task: int = 10  # Prevent infinite reflection loops
    min_steps_between_reflections: int = 1  # Minimum steps between reflections
