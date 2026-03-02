"""
Tool Execution Profiler - Performance monitoring for agent tools.

Tracks execution metrics (duration, success/failure rates, errors) per tool
to enable performance optimization and reliability monitoring.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from app.domain.exceptions.base import ToolConfigurationException
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ToolExecutionMetrics:
    """Metrics for a single tool's executions."""

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    last_used: datetime | None = None
    last_error: str | None = None
    last_error_time: datetime | None = None
    consecutive_failures: int = 0

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average execution duration."""
        if self.call_count == 0:
            return 0.0
        return self.total_duration_ms / self.call_count

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.call_count == 0:
            return 0.0
        return (self.success_count / self.call_count) * 100

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.call_count == 0:
            return 0.0
        return (self.failure_count / self.call_count) * 100

    def record_execution(self, duration_ms: float, success: bool, error: str | None = None) -> None:
        """Record a single execution.

        Args:
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
            error: Optional error message if failed
        """
        self.call_count += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.last_used = datetime.now(UTC)

        if success:
            self.success_count += 1
            self.consecutive_failures = 0
        else:
            self.failure_count += 1
            self.consecutive_failures += 1
            self.last_error = error
            self.last_error_time = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 2),
            "failure_rate": round(self.failure_rate, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float("inf") else None,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class ExecutionRecord:
    """Record of a single tool execution for history tracking."""

    tool_name: str
    timestamp: datetime
    duration_ms: float
    success: bool
    error: str | None = None
    args_summary: str | None = None


class ToolExecutionProfiler:
    """
    Profiles tool executions for performance monitoring and optimization.

    Tracks metrics per tool including:
    - Call counts and success/failure rates
    - Execution duration (min/max/avg)
    - Recent errors and consecutive failures
    - Execution history for trend analysis

    Usage:
        profiler = ToolExecutionProfiler()
        result = await profiler.profile_execution(tool, arg1=value1)

        # Or use as decorator
        @profiler.profile
        async def my_tool_function(...):
            ...
    """

    def __init__(self, history_limit: int = 100, slow_threshold_ms: float = 15000.0, unreliable_threshold: float = 0.2):
        """Initialize the profiler.

        Args:
            history_limit: Maximum execution records to keep
            slow_threshold_ms: Duration threshold for slow tool detection
            unreliable_threshold: Failure rate threshold for unreliable tools
        """
        self._metrics: dict[str, ToolExecutionMetrics] = {}
        self._history: list[ExecutionRecord] = []
        self._history_limit = history_limit
        self._slow_threshold_ms = slow_threshold_ms
        self._unreliable_threshold = unreliable_threshold

    async def profile_execution(self, tool, function_name: str | None = None, **kwargs) -> ToolResult:
        """Execute and profile a tool call.

        Args:
            tool: Tool instance with invoke_function method
            function_name: Function name to invoke (if using BaseTool)
            **kwargs: Arguments for the tool function

        Returns:
            ToolResult from the tool execution
        """
        tool_name = function_name or getattr(tool, "name", type(tool).__name__)

        # Ensure metrics exist for this tool
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolExecutionMetrics(tool_name=tool_name)

        metrics = self._metrics[tool_name]
        start_time = time.perf_counter()
        error_msg = None

        try:
            if function_name and hasattr(tool, "invoke_function"):
                result = await tool.invoke_function(function_name, **kwargs)
            elif hasattr(tool, "execute"):
                result = await tool.execute(**kwargs)
            else:
                raise ToolConfigurationException(f"Tool {tool_name} has no execute or invoke_function method")

            duration_ms = (time.perf_counter() - start_time) * 1000
            success = result.success if hasattr(result, "success") else True

            if not success:
                error_msg = str(result.message)[:200] if hasattr(result, "message") else "Unknown error"

            metrics.record_execution(duration_ms, success, error_msg)
            self._record_history(tool_name, duration_ms, success, error_msg, kwargs)

            # Log slow executions
            if duration_ms > self._slow_threshold_ms:
                logger.warning(
                    f"Slow tool execution: {tool_name} took {duration_ms:.0f}ms "
                    f"(threshold: {self._slow_threshold_ms:.0f}ms)"
                )

            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = str(e)[:200]

            metrics.record_execution(duration_ms, success=False, error=error_msg)
            self._record_history(tool_name, duration_ms, False, error_msg, kwargs)

            logger.error(f"Tool execution failed: {tool_name} - {error_msg}")
            raise

    def record_execution(self, tool_name: str, duration_ms: float, success: bool, error: str | None = None) -> None:
        """Record a tool execution directly without wrapping the call.

        Use this when you need to record execution metrics but the call
        is managed externally (e.g., with retry logic).

        Args:
            tool_name: Name of the tool function
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
            error: Optional error message if failed
        """
        # Ensure metrics exist for this tool
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolExecutionMetrics(tool_name=tool_name)

        metrics = self._metrics[tool_name]
        metrics.record_execution(duration_ms, success, error)
        self._record_history(tool_name, duration_ms, success, error, {})

        # Log slow executions
        if duration_ms > self._slow_threshold_ms:
            logger.warning(
                f"Slow tool execution: {tool_name} took {duration_ms:.0f}ms "
                f"(threshold: {self._slow_threshold_ms:.0f}ms)"
            )

    def _record_history(
        self, tool_name: str, duration_ms: float, success: bool, error: str | None, kwargs: dict[str, Any]
    ) -> None:
        """Record execution in history."""
        # Create brief summary of args
        args_summary = None
        if kwargs:
            try:
                args_str = ", ".join(f"{k}={str(v)[:50]}" for k, v in list(kwargs.items())[:3])
                args_summary = args_str[:100]
            except Exception as e:
                logger.debug(f"Failed to create args summary: {e}")

        record = ExecutionRecord(
            tool_name=tool_name,
            timestamp=datetime.now(UTC),
            duration_ms=duration_ms,
            success=success,
            error=error,
            args_summary=args_summary,
        )

        self._history.append(record)

        # Trim history if needed
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]

    def profile(self, func: Callable) -> Callable:
        """Decorator for profiling async tool functions.

        Usage:
            @profiler.profile
            async def my_tool_function(arg1, arg2):
                ...
        """

        @wraps(func)
        async def wrapper(*args, **kwargs):
            tool_name = func.__name__

            if tool_name not in self._metrics:
                self._metrics[tool_name] = ToolExecutionMetrics(tool_name=tool_name)

            metrics = self._metrics[tool_name]
            start_time = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                success = result.success if hasattr(result, "success") else True
                error = None
                if not success and hasattr(result, "message"):
                    error = str(result.message)[:200]

                metrics.record_execution(duration_ms, success, error)
                self._record_history(tool_name, duration_ms, success, error, kwargs)

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                metrics.record_execution(duration_ms, False, str(e)[:200])
                self._record_history(tool_name, duration_ms, False, str(e)[:200], kwargs)
                raise

        return wrapper

    def get_metrics(self, tool_name: str) -> ToolExecutionMetrics | None:
        """Get metrics for a specific tool."""
        return self._metrics.get(tool_name)

    def get_all_metrics(self) -> dict[str, ToolExecutionMetrics]:
        """Get metrics for all tools."""
        return self._metrics.copy()

    def get_slow_tools(self) -> list[ToolExecutionMetrics]:
        """Get tools with average execution time above threshold.

        Returns:
            List of metrics for slow tools, sorted by avg duration
        """
        slow_tools = [
            m for m in self._metrics.values() if m.avg_duration_ms > self._slow_threshold_ms and m.call_count > 0
        ]
        return sorted(slow_tools, key=lambda m: m.avg_duration_ms, reverse=True)

    def get_unreliable_tools(self) -> list[ToolExecutionMetrics]:
        """Get tools with failure rate above threshold.

        Returns:
            List of metrics for unreliable tools, sorted by failure rate
        """
        unreliable = [
            m
            for m in self._metrics.values()
            if m.call_count > 0 and m.failure_rate > (self._unreliable_threshold * 100)
        ]
        return sorted(unreliable, key=lambda m: m.failure_rate, reverse=True)

    def get_tools_with_consecutive_failures(self, min_failures: int = 3) -> list[ToolExecutionMetrics]:
        """Get tools with recent consecutive failures.

        Args:
            min_failures: Minimum consecutive failures to include

        Returns:
            List of metrics for tools with consecutive failures
        """
        return [m for m in self._metrics.values() if m.consecutive_failures >= min_failures]

    def get_recent_history(self, limit: int = 20, tool_name: str | None = None) -> list[ExecutionRecord]:
        """Get recent execution history.

        Args:
            limit: Maximum records to return
            tool_name: Optional filter by tool name

        Returns:
            List of recent execution records
        """
        history = self._history
        if tool_name:
            history = [r for r in history if r.tool_name == tool_name]
        return history[-limit:]

    def get_execution_summary(self) -> dict[str, Any]:
        """Get summary of all tool executions.

        Returns:
            Summary dictionary with aggregate statistics
        """
        if not self._metrics:
            return {
                "total_calls": 0,
                "total_failures": 0,
                "overall_success_rate": 0.0,
                "slowest_tool": None,
                "most_used_tool": None,
                "most_unreliable_tool": None,
                "tools": {},
            }

        total_calls = sum(m.call_count for m in self._metrics.values())
        total_failures = sum(m.failure_count for m in self._metrics.values())
        overall_success_rate = ((total_calls - total_failures) / total_calls * 100) if total_calls > 0 else 0.0

        slowest = max(self._metrics.values(), key=lambda m: m.avg_duration_ms) if self._metrics else None
        most_used = max(self._metrics.values(), key=lambda m: m.call_count) if self._metrics else None
        most_unreliable = max(self._metrics.values(), key=lambda m: m.failure_rate) if self._metrics else None

        return {
            "total_calls": total_calls,
            "total_failures": total_failures,
            "overall_success_rate": round(overall_success_rate, 2),
            "slowest_tool": slowest.tool_name if slowest and slowest.call_count > 0 else None,
            "slowest_avg_ms": round(slowest.avg_duration_ms, 2) if slowest and slowest.call_count > 0 else None,
            "most_used_tool": most_used.tool_name if most_used else None,
            "most_used_count": most_used.call_count if most_used else 0,
            "most_unreliable_tool": most_unreliable.tool_name
            if most_unreliable and most_unreliable.failure_rate > 0
            else None,
            "most_unreliable_rate": round(most_unreliable.failure_rate, 2)
            if most_unreliable and most_unreliable.failure_rate > 0
            else None,
            "slow_tools_count": len(self.get_slow_tools()),
            "unreliable_tools_count": len(self.get_unreliable_tools()),
            "tools": {name: m.to_dict() for name, m in self._metrics.items()},
        }

    def reset(self, tool_name: str | None = None) -> None:
        """Reset metrics and history.

        Args:
            tool_name: Optional tool name to reset (None = reset all)
        """
        if tool_name:
            if tool_name in self._metrics:
                self._metrics[tool_name] = ToolExecutionMetrics(tool_name=tool_name)
            self._history = [r for r in self._history if r.tool_name != tool_name]
        else:
            self._metrics.clear()
            self._history.clear()

    def set_thresholds(self, slow_threshold_ms: float | None = None, unreliable_threshold: float | None = None) -> None:
        """Update profiler thresholds.

        Args:
            slow_threshold_ms: New slow tool threshold in ms
            unreliable_threshold: New unreliable tool threshold (0-1)
        """
        if slow_threshold_ms is not None:
            self._slow_threshold_ms = slow_threshold_ms
        if unreliable_threshold is not None:
            self._unreliable_threshold = unreliable_threshold


# Global profiler instance for convenience
_global_profiler: ToolExecutionProfiler | None = None


def get_tool_profiler() -> ToolExecutionProfiler:
    """Get or create the global tool profiler instance."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = ToolExecutionProfiler()
    return _global_profiler


def reset_tool_profiler() -> None:
    """Reset the global tool profiler."""
    global _global_profiler
    if _global_profiler:
        _global_profiler.reset()
