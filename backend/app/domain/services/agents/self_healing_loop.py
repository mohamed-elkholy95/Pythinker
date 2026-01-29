"""
Self-healing agent loop with automatic recovery and alternative strategies.

Provides intelligent error recovery, alternative approach generation,
and learning from error patterns to improve resilience. Integrates
with error_handler.py for error classification and pattern analysis.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from app.domain.services.agents.error_handler import (
    ErrorContext,
    ErrorHandler,
    ErrorType,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RecoveryStrategy(str, Enum):
    """Available recovery strategies for different error types."""
    RETRY = "retry"  # Simple retry with backoff
    RETRY_WITH_CONTEXT = "retry_with_context"  # Retry with error context in prompt
    ALTERNATIVE_TOOL = "alternative_tool"  # Try different tool for same goal
    ALTERNATIVE_APPROACH = "alternative_approach"  # Try different approach entirely
    SIMPLIFY = "simplify"  # Simplify the task/request
    DECOMPOSE = "decompose"  # Break into smaller subtasks
    SKIP = "skip"  # Skip this step and continue
    ESCALATE = "escalate"  # Escalate to user
    ROLLBACK = "rollback"  # Rollback and restart from checkpoint


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    strategy: RecoveryStrategy
    error_type: ErrorType
    original_error: str
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = False
    result: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy": self.strategy.value,
            "error_type": self.error_type.value,
            "original_error": self.original_error[:200],
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "result": self.result,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SelfReflectionResult:
    """Result of a self-reflection cycle."""
    iteration: int
    observations: list[str]
    issues_identified: list[str]
    recommendations: list[str]
    should_adjust_strategy: bool = False
    suggested_strategy: RecoveryStrategy | None = None
    timestamp: datetime = field(default_factory=datetime.now)


# Strategy selection based on error type
ERROR_STRATEGY_MAP: dict[ErrorType, list[RecoveryStrategy]] = {
    ErrorType.JSON_PARSE: [
        RecoveryStrategy.RETRY_WITH_CONTEXT,
        RecoveryStrategy.SIMPLIFY,
        RecoveryStrategy.ESCALATE,
    ],
    ErrorType.TOKEN_LIMIT: [
        RecoveryStrategy.SIMPLIFY,
        RecoveryStrategy.DECOMPOSE,
        RecoveryStrategy.SKIP,
    ],
    ErrorType.TOOL_EXECUTION: [
        RecoveryStrategy.RETRY,
        RecoveryStrategy.ALTERNATIVE_TOOL,
        RecoveryStrategy.ALTERNATIVE_APPROACH,
        RecoveryStrategy.ESCALATE,
    ],
    ErrorType.LLM_API: [
        RecoveryStrategy.RETRY,
        RecoveryStrategy.RETRY_WITH_CONTEXT,
        RecoveryStrategy.ESCALATE,
    ],
    ErrorType.LLM_EMPTY_RESPONSE: [
        RecoveryStrategy.RETRY_WITH_CONTEXT,
        RecoveryStrategy.SIMPLIFY,
        RecoveryStrategy.ALTERNATIVE_APPROACH,
    ],
    ErrorType.MCP_CONNECTION: [
        RecoveryStrategy.RETRY,
        RecoveryStrategy.ALTERNATIVE_TOOL,
        RecoveryStrategy.SKIP,
    ],
    ErrorType.TIMEOUT: [
        RecoveryStrategy.RETRY,
        RecoveryStrategy.SIMPLIFY,
        RecoveryStrategy.SKIP,
    ],
    ErrorType.STUCK_LOOP: [
        RecoveryStrategy.ALTERNATIVE_APPROACH,
        RecoveryStrategy.DECOMPOSE,
        RecoveryStrategy.ESCALATE,
    ],
    ErrorType.UNKNOWN: [
        RecoveryStrategy.RETRY,
        RecoveryStrategy.ESCALATE,
    ],
}

# Tool alternatives for common failures
TOOL_ALTERNATIVES: dict[str, list[str]] = {
    "browser_navigate": ["browser_view", "browser_get_content"],
    "browser_click": ["browser_type", "shell_exec"],
    "shell_exec": ["file_write", "browser_navigate"],
    "file_read": ["shell_exec", "browser_get_content"],
    "file_write": ["shell_exec"],
    "info_search_web": ["browser_navigate", "browser_agent"],
}


class SelfHealingLoop:
    """
    Self-healing agent execution loop.

    Provides automatic error recovery with multiple strategies,
    learning from error patterns, and periodic self-reflection.
    """

    def __init__(
        self,
        error_handler: ErrorHandler | None = None,
        max_recovery_attempts: int = 3,
        reflection_interval: int = 5,  # Iterations between reflections
    ):
        """
        Initialize self-healing loop.

        Args:
            error_handler: ErrorHandler instance for error classification
            max_recovery_attempts: Maximum recovery attempts per error
            reflection_interval: Iterations between self-reflection cycles
        """
        self._error_handler = error_handler or ErrorHandler()
        self._max_recovery_attempts = max_recovery_attempts
        self._reflection_interval = reflection_interval

        # Recovery tracking
        self._recovery_attempts: list[RecoveryAttempt] = []
        self._current_attempt_count: int = 0
        self._last_error_type: ErrorType | None = None

        # Strategy tracking
        self._tried_strategies: dict[str, list[RecoveryStrategy]] = {}
        self._successful_strategies: dict[str, RecoveryStrategy] = {}

        # Iteration tracking for reflection
        self._iteration_count: int = 0
        self._reflections: list[SelfReflectionResult] = []

        # Learning from patterns
        self._error_patterns: dict[str, int] = {}  # error_signature -> count
        self._pattern_threshold: int = 3  # Trigger learning after N occurrences

        logger.debug("SelfHealingLoop initialized")

    def _get_error_signature(self, error_context: ErrorContext) -> str:
        """Generate a signature for error pattern tracking."""
        return f"{error_context.error_type.value}:{error_context.message[:50]}"

    def _track_error_pattern(self, error_context: ErrorContext) -> None:
        """Track error pattern for learning."""
        signature = self._get_error_signature(error_context)
        self._error_patterns[signature] = self._error_patterns.get(signature, 0) + 1

        if self._error_patterns[signature] >= self._pattern_threshold:
            logger.info(
                f"Recurring error pattern detected ({self._error_patterns[signature]} occurrences): "
                f"{signature}"
            )

    def select_recovery_strategy(
        self,
        error_context: ErrorContext,
        tool_name: str | None = None,
    ) -> RecoveryStrategy:
        """
        Select the best recovery strategy for an error.

        Args:
            error_context: The error context from classification
            tool_name: Optional name of the failing tool

        Returns:
            Selected RecoveryStrategy
        """
        error_type = error_context.error_type
        error_key = f"{error_type.value}:{tool_name or 'general'}"

        # Check if we have a known successful strategy for this error type
        if error_key in self._successful_strategies:
            return self._successful_strategies[error_key]

        # Get candidate strategies for this error type
        candidates = ERROR_STRATEGY_MAP.get(error_type, [RecoveryStrategy.ESCALATE])

        # Filter out already tried strategies
        tried = self._tried_strategies.get(error_key, [])
        available = [s for s in candidates if s not in tried]

        if not available:
            # All strategies tried, escalate
            logger.warning(f"All strategies exhausted for {error_key}, escalating")
            return RecoveryStrategy.ESCALATE

        # Select first available strategy
        selected = available[0]

        # Track the attempt
        if error_key not in self._tried_strategies:
            self._tried_strategies[error_key] = []
        self._tried_strategies[error_key].append(selected)

        logger.info(f"Selected recovery strategy: {selected.value} for {error_key}")
        return selected

    def get_alternative_tools(self, failing_tool: str) -> list[str]:
        """Get alternative tools for a failing tool."""
        # Check direct alternatives
        if failing_tool in TOOL_ALTERNATIVES:
            return TOOL_ALTERNATIVES[failing_tool]

        # Try partial match
        for tool, alternatives in TOOL_ALTERNATIVES.items():
            if tool in failing_tool or failing_tool in tool:
                return alternatives

        return []

    def generate_recovery_prompt(
        self,
        error_context: ErrorContext,
        strategy: RecoveryStrategy,
        original_task: str,
        tool_name: str | None = None,
    ) -> str:
        """
        Generate a recovery prompt based on strategy.

        Args:
            error_context: The error context
            strategy: Selected recovery strategy
            original_task: The original task description
            tool_name: Optional failing tool name

        Returns:
            Recovery prompt for the agent
        """
        prompts = {
            RecoveryStrategy.RETRY: (
                f"The previous attempt failed with: {error_context.message[:200]}\n"
                f"Please retry the task: {original_task}\n"
                "Try again with the same approach."
            ),
            RecoveryStrategy.RETRY_WITH_CONTEXT: (
                f"Previous attempt failed with error: {error_context.message[:200]}\n"
                f"Error type: {error_context.error_type.value}\n"
                f"Task: {original_task}\n\n"
                "Please try again, taking the error into account. "
                "Adjust your approach to avoid the same error."
            ),
            RecoveryStrategy.ALTERNATIVE_TOOL: (
                f"The tool '{tool_name or 'previous'}' failed with: {error_context.message[:200]}\n"
                f"Task: {original_task}\n\n"
                f"Please try a different tool to accomplish this task. "
                f"Available alternatives: {', '.join(self.get_alternative_tools(tool_name or ''))}"
            ),
            RecoveryStrategy.ALTERNATIVE_APPROACH: (
                f"The previous approach failed with: {error_context.message[:200]}\n"
                f"Task: {original_task}\n\n"
                "Please try a completely different approach to accomplish this task. "
                "Consider:\n"
                "1. Different tools or methods\n"
                "2. Alternative data sources\n"
                "3. Breaking down the task differently"
            ),
            RecoveryStrategy.SIMPLIFY: (
                f"The task appears too complex. Error: {error_context.message[:200]}\n"
                f"Original task: {original_task}\n\n"
                "Please simplify your approach:\n"
                "1. Focus on the core requirement only\n"
                "2. Use simpler tools and methods\n"
                "3. Reduce the scope if needed"
            ),
            RecoveryStrategy.DECOMPOSE: (
                f"The task failed, possibly due to complexity: {error_context.message[:200]}\n"
                f"Original task: {original_task}\n\n"
                "Please break this down into smaller, manageable subtasks:\n"
                "1. Identify the smallest unit of work that can succeed\n"
                "2. Complete that unit before moving on\n"
                "3. Build up to the full task incrementally"
            ),
            RecoveryStrategy.SKIP: (
                f"The current step failed with: {error_context.message[:200]}\n"
                f"Task: {original_task}\n\n"
                "This step will be skipped. Please continue with the next step "
                "or provide a summary of what was accomplished so far."
            ),
            RecoveryStrategy.ROLLBACK: (
                f"Multiple failures encountered: {error_context.message[:200]}\n"
                f"Task: {original_task}\n\n"
                "Rolling back to the last checkpoint. Please review the task "
                "and start fresh with a new approach."
            ),
            RecoveryStrategy.ESCALATE: (
                f"Unable to recover from error: {error_context.message[:200]}\n"
                f"Task: {original_task}\n\n"
                "Please ask the user for guidance on how to proceed."
            ),
        }

        return prompts.get(strategy, prompts[RecoveryStrategy.ESCALATE])

    async def attempt_recovery(
        self,
        error_context: ErrorContext,
        recovery_action: Callable[[], Awaitable[T]],
        tool_name: str | None = None,
    ) -> tuple[bool, T | None, RecoveryAttempt]:
        """
        Attempt to recover from an error.

        Args:
            error_context: The error context
            recovery_action: Async callable to retry
            tool_name: Optional failing tool name

        Returns:
            Tuple of (success, result, attempt_record)
        """
        start_time = datetime.now()

        # Track the error pattern
        self._track_error_pattern(error_context)

        # Select strategy
        strategy = self.select_recovery_strategy(error_context, tool_name)

        # Create attempt record
        attempt = RecoveryAttempt(
            strategy=strategy,
            error_type=error_context.error_type,
            original_error=error_context.message,
        )

        # Check if we should escalate immediately
        if strategy == RecoveryStrategy.ESCALATE:
            attempt.success = False
            attempt.result = "Escalated to user"
            self._recovery_attempts.append(attempt)
            return False, None, attempt

        # Check if we should skip
        if strategy == RecoveryStrategy.SKIP:
            attempt.success = True
            attempt.result = "Step skipped"
            self._recovery_attempts.append(attempt)
            return True, None, attempt

        # Attempt recovery
        try:
            # Apply backoff delay
            delay = error_context.get_retry_delay()
            await asyncio.sleep(delay)

            result = await recovery_action()

            # Record success
            attempt.success = True
            attempt.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Learn from success
            error_key = f"{error_context.error_type.value}:{tool_name or 'general'}"
            self._successful_strategies[error_key] = strategy

            logger.info(
                f"Recovery successful with strategy {strategy.value} "
                f"in {attempt.duration_ms}ms"
            )

            self._recovery_attempts.append(attempt)
            return True, result, attempt

        except Exception as e:
            # Record failure
            attempt.success = False
            attempt.result = str(e)[:200]
            attempt.duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            logger.warning(
                f"Recovery attempt failed with strategy {strategy.value}: {e}"
            )

            self._recovery_attempts.append(attempt)
            return False, None, attempt

    def should_reflect(self) -> bool:
        """Check if it's time for a self-reflection cycle."""
        return (
            self._iteration_count > 0 and
            self._iteration_count % self._reflection_interval == 0
        )

    def perform_reflection(self) -> SelfReflectionResult:
        """
        Perform a self-reflection cycle to assess progress.

        Returns:
            SelfReflectionResult with observations and recommendations
        """
        self._iteration_count += 1

        observations = []
        issues = []
        recommendations = []

        # Analyze recent recovery attempts
        recent_attempts = self._recovery_attempts[-10:]  # Last 10 attempts

        if recent_attempts:
            success_rate = sum(1 for a in recent_attempts if a.success) / len(recent_attempts)
            observations.append(f"Recent recovery success rate: {success_rate:.0%}")

            if success_rate < 0.5:
                issues.append("Recovery success rate is below 50%")
                recommendations.append("Consider simplifying tasks or using different approaches")

        # Analyze error patterns
        recurring_patterns = [
            (sig, count) for sig, count in self._error_patterns.items()
            if count >= self._pattern_threshold
        ]

        if recurring_patterns:
            for sig, count in recurring_patterns:
                observations.append(f"Recurring error pattern ({count}x): {sig}")
                issues.append(f"Pattern '{sig[:30]}...' keeps recurring")

            recommendations.append("Address recurring error patterns before proceeding")

        # Analyze strategy effectiveness
        strategy_success: dict[RecoveryStrategy, tuple[int, int]] = {}
        for attempt in recent_attempts:
            if attempt.strategy not in strategy_success:
                strategy_success[attempt.strategy] = (0, 0)
            success, total = strategy_success[attempt.strategy]
            strategy_success[attempt.strategy] = (
                success + (1 if attempt.success else 0),
                total + 1
            )

        for strategy, (success, total) in strategy_success.items():
            rate = success / total if total > 0 else 0
            observations.append(f"Strategy '{strategy.value}': {rate:.0%} success ({total} attempts)")
            if rate < 0.3 and total >= 2:
                issues.append(f"Strategy '{strategy.value}' has low success rate")

        # Determine if strategy adjustment is needed
        should_adjust = len(issues) > 2 or (recurring_patterns and len(recurring_patterns) > 1)
        suggested = None

        if should_adjust:
            # Suggest the most successful strategy
            best_strategy = None
            best_rate = 0
            for strategy, (success, total) in strategy_success.items():
                rate = success / total if total > 0 else 0
                if rate > best_rate:
                    best_rate = rate
                    best_strategy = strategy

            if best_strategy and best_rate > 0.5:
                suggested = best_strategy
                recommendations.append(f"Consider prioritizing '{best_strategy.value}' strategy")
            else:
                recommendations.append("Consider escalating to user for guidance")

        result = SelfReflectionResult(
            iteration=self._iteration_count,
            observations=observations,
            issues_identified=issues,
            recommendations=recommendations,
            should_adjust_strategy=should_adjust,
            suggested_strategy=suggested,
        )

        self._reflections.append(result)
        logger.info(
            f"Self-reflection complete: {len(observations)} observations, "
            f"{len(issues)} issues, adjust_strategy={should_adjust}"
        )

        return result

    def can_attempt_recovery(self) -> bool:
        """Check if more recovery attempts are allowed."""
        return self._current_attempt_count < self._max_recovery_attempts

    def reset_recovery_counter(self) -> None:
        """Reset the current recovery attempt counter."""
        self._current_attempt_count = 0
        self._tried_strategies.clear()

    def increment_recovery_counter(self) -> None:
        """Increment the current recovery attempt counter."""
        self._current_attempt_count += 1

    def get_recovery_stats(self) -> dict[str, Any]:
        """Get recovery statistics for monitoring."""
        total_attempts = len(self._recovery_attempts)
        successful = sum(1 for a in self._recovery_attempts if a.success)

        strategy_breakdown: dict[str, dict[str, int]] = {}
        for attempt in self._recovery_attempts:
            strategy = attempt.strategy.value
            if strategy not in strategy_breakdown:
                strategy_breakdown[strategy] = {"success": 0, "failure": 0}
            if attempt.success:
                strategy_breakdown[strategy]["success"] += 1
            else:
                strategy_breakdown[strategy]["failure"] += 1

        return {
            "total_attempts": total_attempts,
            "successful_recoveries": successful,
            "success_rate": successful / total_attempts if total_attempts > 0 else 0,
            "current_attempt_count": self._current_attempt_count,
            "max_recovery_attempts": self._max_recovery_attempts,
            "strategy_breakdown": strategy_breakdown,
            "error_patterns": dict(self._error_patterns),
            "reflections_performed": len(self._reflections),
        }

    def clear_history(self) -> None:
        """Clear all recovery history."""
        self._recovery_attempts.clear()
        self._tried_strategies.clear()
        self._successful_strategies.clear()
        self._error_patterns.clear()
        self._reflections.clear()
        self._current_attempt_count = 0
        self._iteration_count = 0


@dataclass
class HealingLoopConfig:
    """Configuration for self-healing loop behavior."""
    max_recovery_attempts: int = 3
    reflection_interval: int = 5
    enable_learning: bool = True
    pattern_threshold: int = 3
    escalation_after_failures: int = 3  # Escalate after N consecutive failures

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_recovery_attempts": self.max_recovery_attempts,
            "reflection_interval": self.reflection_interval,
            "enable_learning": self.enable_learning,
            "pattern_threshold": self.pattern_threshold,
            "escalation_after_failures": self.escalation_after_failures,
        }


# Singleton instance
_self_healing_loop: SelfHealingLoop | None = None


def get_self_healing_loop() -> SelfHealingLoop:
    """Get the global self-healing loop singleton."""
    global _self_healing_loop
    if _self_healing_loop is None:
        _self_healing_loop = SelfHealingLoop()
    return _self_healing_loop


def set_self_healing_loop(loop: SelfHealingLoop) -> None:
    """Set the global self-healing loop singleton."""
    global _self_healing_loop
    _self_healing_loop = loop
