"""
Error pattern detection and analysis.

Mines error history to detect recurring patterns and provide
proactive guidance to help the agent avoid repeated failures.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from app.domain.services.agents.error_handler import ErrorContext, ErrorType

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    """Types of detectable error patterns"""
    TIMEOUT_REPEATED = "timeout_repeated"
    JSON_PARSE_LOOP = "json_parse_loop"
    TOOL_FAILURE_STREAK = "tool_failure_streak"
    RATE_LIMIT_BURST = "rate_limit_burst"
    STUCK_ON_TOOL = "stuck_on_tool"
    SAME_ERROR_REPEATED = "same_error_repeated"


@dataclass
class DetectedPattern:
    """A detected error pattern with suggestions"""
    pattern_type: PatternType
    confidence: float  # 0-1 confidence score
    occurrences: int
    time_window: timedelta
    affected_tools: list[str]
    suggestion: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_context_signal(self) -> str:
        """Generate context signal for prompt injection"""
        return (
            f"PATTERN DETECTED: {self.pattern_type.value} "
            f"({self.occurrences} occurrences in {self.time_window.seconds}s)\n"
            f"SUGGESTION: {self.suggestion}"
        )


@dataclass
class ToolErrorRecord:
    """Record of tool execution error"""
    tool_name: str
    error_type: ErrorType
    error_message: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class ErrorPatternAnalyzer:
    """
    Analyzes error history to detect patterns and provide guidance.

    Patterns detected:
    - Repeated timeouts on similar commands
    - JSON parsing failure loops
    - Tool failure streaks (3+ consecutive failures)
    - Rate limit bursts
    - Getting stuck on specific tools
    """

    # Pattern detection thresholds
    TIMEOUT_THRESHOLD = 3  # Number of timeouts to trigger pattern
    JSON_PARSE_THRESHOLD = 2  # Number of JSON errors
    TOOL_FAILURE_THRESHOLD = 3  # Consecutive failures
    RATE_LIMIT_THRESHOLD = 2  # Rate limits in window
    SAME_ERROR_THRESHOLD = 3  # Same error message

    # Time windows for pattern detection
    PATTERN_WINDOW = timedelta(minutes=5)  # Look back window

    def __init__(self, max_history: int = 100):
        """
        Initialize the pattern analyzer.

        Args:
            max_history: Maximum error records to keep
        """
        self._max_history = max_history
        self._error_history: list[ToolErrorRecord] = []
        self._tool_error_counts: dict[str, int] = defaultdict(int)
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._last_success_time: dict[str, datetime] = {}

    def record_error(
        self,
        tool_name: str,
        error_context: ErrorContext,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Record a tool execution error.

        Args:
            tool_name: Name of the tool that failed
            error_context: Error context from error handler
            metadata: Optional additional metadata
        """
        record = ToolErrorRecord(
            tool_name=tool_name,
            error_type=error_context.error_type,
            error_message=error_context.message[:500],
            timestamp=datetime.now(),
            metadata=metadata or {}
        )

        self._error_history.append(record)
        self._tool_error_counts[tool_name] += 1
        self._consecutive_failures[tool_name] += 1

        # Trim history if needed
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]

        logger.debug(f"Recorded error for {tool_name}: {error_context.error_type.value}")

    def record_success(self, tool_name: str) -> None:
        """Record a successful tool execution to break failure streaks"""
        self._consecutive_failures[tool_name] = 0
        self._last_success_time[tool_name] = datetime.now()

    def analyze_patterns(self) -> list[DetectedPattern]:
        """
        Analyze error history for patterns.

        Returns:
            List of detected patterns with suggestions
        """
        if not self._error_history:
            return []

        patterns = []
        now = datetime.now()
        window_start = now - self.PATTERN_WINDOW

        # Get recent errors within window
        recent_errors = [
            e for e in self._error_history
            if e.timestamp >= window_start
        ]

        if not recent_errors:
            return []

        # Check for timeout pattern
        timeout_pattern = self._check_timeout_pattern(recent_errors)
        if timeout_pattern:
            patterns.append(timeout_pattern)

        # Check for JSON parse loop
        json_pattern = self._check_json_parse_pattern(recent_errors)
        if json_pattern:
            patterns.append(json_pattern)

        # Check for tool failure streak
        streak_pattern = self._check_failure_streak_pattern(recent_errors)
        if streak_pattern:
            patterns.append(streak_pattern)

        # Check for rate limit burst
        rate_pattern = self._check_rate_limit_pattern(recent_errors)
        if rate_pattern:
            patterns.append(rate_pattern)

        # Check for repeated same error
        repeat_pattern = self._check_same_error_pattern(recent_errors)
        if repeat_pattern:
            patterns.append(repeat_pattern)

        return patterns

    def _check_timeout_pattern(
        self,
        recent_errors: list[ToolErrorRecord]
    ) -> DetectedPattern | None:
        """Check for repeated timeout pattern"""
        timeout_errors = [
            e for e in recent_errors
            if e.error_type == ErrorType.TIMEOUT
        ]

        if len(timeout_errors) >= self.TIMEOUT_THRESHOLD:
            # Group by tool
            tool_counts = defaultdict(int)
            for e in timeout_errors:
                tool_counts[e.tool_name] += 1

            most_affected = max(tool_counts.keys(), key=lambda k: tool_counts[k])

            return DetectedPattern(
                pattern_type=PatternType.TIMEOUT_REPEATED,
                confidence=min(len(timeout_errors) / 5, 1.0),
                occurrences=len(timeout_errors),
                time_window=self.PATTERN_WINDOW,
                affected_tools=[most_affected],
                suggestion=(
                    f"Tool '{most_affected}' has timed out {tool_counts[most_affected]} times. "
                    "Consider: 1) Breaking the operation into smaller parts, "
                    "2) Using --timeout flag if supported, "
                    "3) Trying an alternative approach."
                ),
                details={"timeout_counts": dict(tool_counts)}
            )

        return None

    def _check_json_parse_pattern(
        self,
        recent_errors: list[ToolErrorRecord]
    ) -> DetectedPattern | None:
        """Check for JSON parsing failure loop"""
        json_errors = [
            e for e in recent_errors
            if e.error_type == ErrorType.JSON_PARSE
        ]

        if len(json_errors) >= self.JSON_PARSE_THRESHOLD:
            return DetectedPattern(
                pattern_type=PatternType.JSON_PARSE_LOOP,
                confidence=min(len(json_errors) / 4, 1.0),
                occurrences=len(json_errors),
                time_window=self.PATTERN_WINDOW,
                affected_tools=list(set(e.tool_name for e in json_errors)),
                suggestion=(
                    "Multiple JSON parsing failures detected. "
                    "Ensure: 1) Proper JSON escaping of strings, "
                    "2) No trailing commas, "
                    "3) All keys and strings use double quotes, "
                    "4) Response matches expected schema exactly."
                ),
                details={"error_samples": [e.error_message[:100] for e in json_errors[:3]]}
            )

        return None

    def _check_failure_streak_pattern(
        self,
        recent_errors: list[ToolErrorRecord]
    ) -> DetectedPattern | None:
        """Check for consecutive tool failure streak"""
        for tool_name, count in self._consecutive_failures.items():
            if count >= self.TOOL_FAILURE_THRESHOLD:
                tool_errors = [
                    e for e in recent_errors
                    if e.tool_name == tool_name
                ]

                return DetectedPattern(
                    pattern_type=PatternType.TOOL_FAILURE_STREAK,
                    confidence=min(count / 5, 1.0),
                    occurrences=count,
                    time_window=self.PATTERN_WINDOW,
                    affected_tools=[tool_name],
                    suggestion=(
                        f"Tool '{tool_name}' has failed {count} times consecutively. "
                        "Try: 1) Using a different tool for this task, "
                        "2) Verifying input parameters, "
                        "3) Checking if the operation is even possible."
                    ),
                    details={
                        "error_types": list(set(e.error_type.value for e in tool_errors)),
                        "last_error": tool_errors[-1].error_message[:200] if tool_errors else ""
                    }
                )

        return None

    def _check_rate_limit_pattern(
        self,
        recent_errors: list[ToolErrorRecord]
    ) -> DetectedPattern | None:
        """Check for rate limit burst"""
        rate_errors = [
            e for e in recent_errors
            if e.error_type == ErrorType.LLM_API and 'rate' in e.error_message.lower()
        ]

        if len(rate_errors) >= self.RATE_LIMIT_THRESHOLD:
            return DetectedPattern(
                pattern_type=PatternType.RATE_LIMIT_BURST,
                confidence=min(len(rate_errors) / 4, 1.0),
                occurrences=len(rate_errors),
                time_window=self.PATTERN_WINDOW,
                affected_tools=[],
                suggestion=(
                    "Multiple rate limit errors detected. "
                    "Wait before making additional requests. "
                    "Consider batching operations where possible."
                ),
                details={"rate_limit_count": len(rate_errors)}
            )

        return None

    def _check_same_error_pattern(
        self,
        recent_errors: list[ToolErrorRecord]
    ) -> DetectedPattern | None:
        """Check for repeated identical error messages"""
        error_msg_counts: dict[str, int] = defaultdict(int)
        error_msg_tools: dict[str, str] = {}

        for e in recent_errors:
            # Normalize error message for comparison
            normalized = e.error_message[:100].lower().strip()
            error_msg_counts[normalized] += 1
            error_msg_tools[normalized] = e.tool_name

        for msg, count in error_msg_counts.items():
            if count >= self.SAME_ERROR_THRESHOLD:
                return DetectedPattern(
                    pattern_type=PatternType.SAME_ERROR_REPEATED,
                    confidence=min(count / 5, 1.0),
                    occurrences=count,
                    time_window=self.PATTERN_WINDOW,
                    affected_tools=[error_msg_tools[msg]],
                    suggestion=(
                        f"The same error has occurred {count} times. "
                        "This approach is not working - try a completely "
                        "different strategy to accomplish the task."
                    ),
                    details={"repeated_error": msg[:200]}
                )

        return None

    def get_guidance_for_tool(self, tool_name: str) -> str | None:
        """
        Get specific guidance for a tool based on its error history.

        Args:
            tool_name: Name of the tool

        Returns:
            Guidance string if patterns detected, None otherwise
        """
        patterns = self.analyze_patterns()

        for pattern in patterns:
            if tool_name in pattern.affected_tools:
                return pattern.suggestion

        return None

    def get_all_pattern_signals(self) -> list[str]:
        """Get context signals for all detected patterns"""
        patterns = self.analyze_patterns()
        return [p.to_context_signal() for p in patterns]

    def get_proactive_signals(
        self,
        likely_tools: list[str] | None = None
    ) -> str | None:
        """Get proactive warning signals for likely tool usage.

        Analyzes error history to generate warnings BEFORE execution,
        helping the agent avoid repeated failures.

        Args:
            likely_tools: List of tool names likely to be used in the next step

        Returns:
            Warning message if patterns detected, None otherwise
        """
        if not likely_tools:
            return None

        warnings = []
        patterns = self.analyze_patterns()

        for pattern in patterns:
            # Check if any likely tools are affected by detected patterns
            affected_overlap = set(likely_tools) & set(pattern.affected_tools)
            if affected_overlap:
                warnings.append(
                    f"CAUTION ({pattern.pattern_type.value}): {pattern.suggestion}"
                )

        # Also check for general patterns that apply to all tools
        for pattern in patterns:
            if not pattern.affected_tools:  # Patterns like rate limits
                if pattern.confidence >= 0.5:
                    warnings.append(
                        f"WARNING: {pattern.suggestion}"
                    )

        if warnings:
            return "\n".join(warnings)
        return None

    def infer_tools_from_description(self, step_description: str) -> list[str]:
        """Infer likely tools from a step description.

        Args:
            step_description: The step description text

        Returns:
            List of likely tool names
        """
        desc_lower = step_description.lower()
        tools = []

        # Map keywords to tool names
        tool_keywords = {
            "shell": ["run", "execute", "command", "terminal", "bash", "install"],
            "browser": ["browse", "navigate", "click", "website", "page", "url"],
            "file": ["read", "write", "save", "file", "create file", "edit"],
            "search": ["search", "find", "lookup", "google", "query"],
            "message": ["ask", "tell", "inform", "message", "user"],
        }

        for tool, keywords in tool_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                tools.append(tool)

        return tools

    def clear_history(self) -> None:
        """Clear error history"""
        self._error_history.clear()
        self._tool_error_counts.clear()
        self._consecutive_failures.clear()
        self._last_success_time.clear()
        logger.debug("Error pattern analyzer history cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "total_errors": len(self._error_history),
            "tool_error_counts": dict(self._tool_error_counts),
            "consecutive_failures": dict(self._consecutive_failures),
            "active_patterns": len(self.analyze_patterns())
        }


# Singleton for global access
_pattern_analyzer: ErrorPatternAnalyzer | None = None


def get_error_pattern_analyzer() -> ErrorPatternAnalyzer:
    """Get or create the global error pattern analyzer"""
    global _pattern_analyzer
    if _pattern_analyzer is None:
        _pattern_analyzer = ErrorPatternAnalyzer()
    return _pattern_analyzer
