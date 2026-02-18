"""
Speculative Execution module.

This module provides speculative execution capabilities,
pre-executing predictable next steps while current step completes.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SpeculationSafety(str, Enum):
    """Safety level for speculative execution."""

    SAFE = "safe"  # No side effects, can always speculate
    CONDITIONAL = "conditional"  # Safe under certain conditions
    UNSAFE = "unsafe"  # Has side effects, never speculate


# Safe tools for speculative execution (read-only, no side effects)
SAFE_SPECULATION_TOOLS = {
    # Search operations
    "info_search_web",
    "info_search_news",
    # File read operations
    "file_read",
    "file_search",
    "file_list_directory",
    # Browser read operations
    "browser_get_content",
    "browser_view",
    # Code analysis (read-only)
    "code_analyze",
    "code_list_artifacts",
    # Git read operations
    "git_status",
    "git_diff",
    "git_log",
}


@dataclass
class SpeculativeTask:
    """A speculative task queued for execution."""

    task_id: str
    tool_name: str
    tool_args: dict[str, Any]
    prediction_confidence: float
    depends_on: str | None = None  # Task ID this depends on
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    was_used: bool = False


@dataclass
class SpeculativeResult:
    """Result of speculative execution."""

    task_id: str
    tool_name: str
    result: Any
    prediction_confidence: float
    execution_time_ms: float
    was_accurate: bool = False
    saved_time_ms: float = 0.0


class SpeculativeExecutor:
    """Executor for speculative pre-execution.

    Pre-executes predictable read-only operations while
    the current step is being processed, saving time when
    predictions are accurate.
    """

    # Maximum concurrent speculative tasks
    MAX_CONCURRENT_SPECULATION = 3
    # Minimum confidence to speculate
    MIN_CONFIDENCE_THRESHOLD = 0.6
    # Maximum speculation queue size
    MAX_QUEUE_SIZE = 10

    def __init__(
        self,
        max_concurrent: int | None = None,
        min_confidence: float | None = None,
    ) -> None:
        """Initialize the speculative executor.

        Args:
            max_concurrent: Maximum concurrent speculations
            min_confidence: Minimum confidence threshold
        """
        self._max_concurrent = max_concurrent or self.MAX_CONCURRENT_SPECULATION
        self._min_confidence = min_confidence or self.MIN_CONFIDENCE_THRESHOLD
        self._queue: list[SpeculativeTask] = []
        self._running: dict[str, asyncio.Task] = {}
        self._completed: dict[str, SpeculativeResult] = {}
        self._stats = {
            "total_speculated": 0,
            "hits": 0,
            "misses": 0,
            "time_saved_ms": 0.0,
        }

    def can_speculate(self, tool_name: str) -> bool:
        """Check if a tool is safe for speculation.

        Args:
            tool_name: Name of the tool

        Returns:
            True if safe to speculate
        """
        return tool_name in SAFE_SPECULATION_TOOLS

    def queue_speculation(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        confidence: float,
        depends_on: str | None = None,
    ) -> SpeculativeTask | None:
        """Queue a speculative task for execution.

        Args:
            tool_name: Tool to execute
            tool_args: Tool arguments
            confidence: Prediction confidence
            depends_on: Optional dependency task ID

        Returns:
            Queued task if accepted, None if rejected
        """
        # Check if tool is safe
        if not self.can_speculate(tool_name):
            logger.debug(f"Tool {tool_name} not safe for speculation")
            return None

        # Check confidence threshold
        if confidence < self._min_confidence:
            logger.debug(f"Confidence {confidence:.2f} below threshold {self._min_confidence:.2f}")
            return None

        # Check queue size
        if len(self._queue) >= self.MAX_QUEUE_SIZE:
            logger.debug("Speculation queue full")
            return None

        # Create task
        task = SpeculativeTask(
            task_id=f"spec_{len(self._queue)}_{datetime.now(UTC).timestamp()}",
            tool_name=tool_name,
            tool_args=tool_args,
            prediction_confidence=confidence,
            depends_on=depends_on,
        )

        self._queue.append(task)
        self._stats["total_speculated"] += 1

        logger.debug(f"Queued speculation: {tool_name} with confidence {confidence:.2f}")

        return task

    async def execute_speculations(
        self,
        tool_executor: Any,  # Callable to execute tools
    ) -> list[SpeculativeResult]:
        """Execute queued speculations.

        Args:
            tool_executor: Function to execute tools

        Returns:
            List of completed speculation results
        """
        results = []

        # Sort by confidence (highest first)
        self._queue.sort(key=lambda t: t.prediction_confidence, reverse=True)

        # Execute up to max concurrent
        tasks_to_run = []
        for task in self._queue[: self._max_concurrent]:
            if task.depends_on and task.depends_on not in self._completed:
                continue  # Skip if dependency not ready

            tasks_to_run.append(task)

        # Execute in parallel
        if tasks_to_run:
            async_tasks = [self._execute_single(task, tool_executor) for task in tasks_to_run]
            completed = await asyncio.gather(*async_tasks, return_exceptions=True)

            for task, result in zip(tasks_to_run, completed, strict=True):
                if isinstance(result, Exception):
                    task.error = str(result)
                else:
                    results.append(result)
                    self._completed[task.task_id] = result

                # Remove from queue
                if task in self._queue:
                    self._queue.remove(task)

        return results

    def get_cached_result(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> SpeculativeResult | None:
        """Get a cached speculation result if available.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments

        Returns:
            Cached result if found and matches
        """
        for task_id, result in self._completed.items():
            if result.tool_name != tool_name:
                continue

            # Check if args match (find the task)
            task = self._find_task_by_id(task_id)
            if task and self._args_match(task.tool_args, tool_args):
                result.was_accurate = True
                self._stats["hits"] += 1
                return result

        self._stats["misses"] += 1
        return None

    def mark_result_used(
        self,
        result: SpeculativeResult,
        actual_execution_time_ms: float,
    ) -> None:
        """Mark a speculation result as used.

        Args:
            result: The result that was used
            actual_execution_time_ms: Time that would have been taken
        """
        saved = actual_execution_time_ms - result.execution_time_ms
        result.saved_time_ms = max(0, saved)
        result.was_accurate = True

        self._stats["time_saved_ms"] += result.saved_time_ms

    def clear_speculation(self, task_id: str | None = None) -> None:
        """Clear speculation results.

        Args:
            task_id: Specific task to clear, or None for all
        """
        if task_id:
            if task_id in self._completed:
                del self._completed[task_id]
            self._queue = [t for t in self._queue if t.task_id != task_id]
        else:
            self._completed.clear()
            self._queue.clear()

    def get_statistics(self) -> dict[str, Any]:
        """Get speculation statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0

        return {
            "total_speculated": self._stats["total_speculated"],
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": hit_rate,
            "time_saved_ms": self._stats["time_saved_ms"],
            "queue_size": len(self._queue),
            "cached_results": len(self._completed),
        }

    async def _execute_single(
        self,
        task: SpeculativeTask,
        tool_executor: Any,
    ) -> SpeculativeResult:
        """Execute a single speculative task."""
        task.started_at = datetime.now(UTC)

        try:
            result = await tool_executor(task.tool_name, task.tool_args)
            task.completed_at = datetime.now(UTC)
            task.result = result

            execution_time_ms = (task.completed_at - task.started_at).total_seconds() * 1000

            return SpeculativeResult(
                task_id=task.task_id,
                tool_name=task.tool_name,
                result=result,
                prediction_confidence=task.prediction_confidence,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            raise

    def _find_task_by_id(self, task_id: str) -> SpeculativeTask | None:
        """Find a task by ID."""
        for task in self._queue:
            if task.task_id == task_id:
                return task
        return None

    def _args_match(
        self,
        args1: dict[str, Any],
        args2: dict[str, Any],
    ) -> bool:
        """Check if two argument dicts match."""
        if set(args1.keys()) != set(args2.keys()):
            return False

        return all(args1[key] == args2[key] for key in args1)


# Global speculative executor instance
_executor: SpeculativeExecutor | None = None


def get_speculative_executor() -> SpeculativeExecutor:
    """Get or create the global speculative executor."""
    global _executor
    if _executor is None:
        _executor = SpeculativeExecutor()
    return _executor


def reset_speculative_executor() -> None:
    """Reset the global speculative executor."""
    global _executor
    _executor = None
