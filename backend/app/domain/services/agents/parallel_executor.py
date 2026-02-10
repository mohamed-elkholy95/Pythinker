"""Parallel Tool Executor

Enables parallel execution of independent tool calls to reduce latency.
Research shows this can reduce execution time by 54% in agent workflows.

Key features:
- Batch independent tool calls with asyncio.gather
- Automatic dependency detection
- Fallback to sequential for dependent calls
- Timeout handling per tool call
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Tool execution modes."""

    SEQUENTIAL = "sequential"  # One at a time
    PARALLEL = "parallel"  # All at once
    BATCHED = "batched"  # Groups of parallel calls


@dataclass
class ToolCall:
    """Represents a pending tool call."""

    id: str
    tool_name: str
    arguments: dict[str, Any]
    depends_on: set[str] = field(default_factory=set)  # IDs of dependent calls
    priority: int = 0  # Higher = execute first


@dataclass
class ToolResult:
    """Result of a tool call execution."""

    call_id: str
    tool_name: str
    success: bool
    result: Any
    error: str | None = None
    execution_time_ms: float = 0


class ParallelToolExecutor:
    """Executes tool calls in parallel when safe.

    Usage:
        executor = ParallelToolExecutor()

        # Add tool calls
        executor.add_call(ToolCall(id="1", tool_name="file_read", arguments={"path": "a.txt"}))
        executor.add_call(ToolCall(id="2", tool_name="file_read", arguments={"path": "b.txt"}))
        executor.add_call(ToolCall(id="3", tool_name="shell_exec", arguments={"cmd": "ls"}))

        # Execute all in parallel (no dependencies)
        results = await executor.execute_all(tool_executor_func)
    """

    # Tools that are safe to run in parallel (no side effects on each other)
    PARALLELIZABLE_TOOLS: ClassVar[set[str]] = {
        # Read operations (no side effects)
        "file_read",
        "file_list",
        "file_exists",
        # Shell commands that don't modify state
        "shell_exec",  # Context-dependent, but usually safe
    }

    # Tools that should never run in parallel (use shared browser or modify state)
    SEQUENTIAL_ONLY_TOOLS: ClassVar[set[str]] = {
        "file_write",
        "file_delete",
        "file_append",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_get_content",
        "search",  # Now navigates browser for VNC display
        "info_search_web",
    }

    def __init__(
        self,
        max_concurrent: int = 5,
        timeout_per_call: float = 60.0,
        enable_parallel: bool = True,
    ):
        """Initialize the parallel executor.

        Args:
            max_concurrent: Maximum concurrent tool calls
            timeout_per_call: Timeout per tool call in seconds
            enable_parallel: If False, execute all sequentially
        """
        self.max_concurrent = max_concurrent
        self.timeout_per_call = timeout_per_call
        self.enable_parallel = enable_parallel
        self._pending_calls: list[ToolCall] = []
        self._results: dict[str, ToolResult] = {}

        # Execution statistics
        self._stats = {
            "total_calls": 0,
            "parallel_batches": 0,
            "sequential_calls": 0,
            "time_saved_ms": 0,
        }

    def add_call(self, call: ToolCall) -> None:
        """Add a tool call to the pending queue.

        Args:
            call: ToolCall to add
        """
        self._pending_calls.append(call)

    def add_calls(self, calls: list[ToolCall]) -> None:
        """Add multiple tool calls.

        Args:
            calls: List of ToolCalls to add
        """
        self._pending_calls.extend(calls)

    def clear(self) -> None:
        """Clear pending calls and results."""
        self._pending_calls.clear()
        self._results.clear()

    def can_parallelize(self, call: ToolCall) -> bool:
        """Check if a tool call can be parallelized.

        Args:
            call: ToolCall to check

        Returns:
            True if the call can run in parallel
        """
        if not self.enable_parallel:
            return False

        if call.tool_name in self.SEQUENTIAL_ONLY_TOOLS:
            return False

        # Check for dependencies
        if call.depends_on:
            return False

        return call.tool_name in self.PARALLELIZABLE_TOOLS

    def detect_dependencies(self) -> None:
        """Automatically detect dependencies between pending calls.

        For example:
        - file_write to path X depends on any prior file_read of X
        - browser_click depends on prior browser_navigate
        """
        for i, call in enumerate(self._pending_calls):
            for _j, prior_call in enumerate(self._pending_calls[:i]):
                if self._has_dependency(call, prior_call):
                    call.depends_on.add(prior_call.id)

    def _has_dependency(self, call: ToolCall, prior: ToolCall) -> bool:
        """Check if call depends on prior call.

        Args:
            call: The later call
            prior: The earlier call

        Returns:
            True if call depends on prior
        """
        # File operations on same path (tools use "file" parameter, not "path")
        write_tools = {"file_write", "file_append", "file_delete", "file_str_replace"}
        if "file_" in call.tool_name and "file_" in prior.tool_name:
            call_path = call.arguments.get("file", "") or call.arguments.get("path", "")
            prior_path = prior.arguments.get("file", "") or prior.arguments.get("path", "")
            if call_path and prior_path and call_path == prior_path:
                # Write/modify after any file op on same path is dependent
                if call.tool_name in write_tools:
                    return True
                # Read after write on same path is also dependent
                if prior.tool_name in write_tools:
                    return True

        # Shell operations: sequential by default (shared state: cwd, env vars)
        if "shell_" in call.tool_name and "shell_" in prior.tool_name:
            call_id = call.arguments.get("id", "")
            prior_id = prior.arguments.get("id", "")
            if call_id and prior_id and call_id == prior_id:
                return True

        # Browser operations
        # Most browser operations depend on navigation
        return "browser_" in call.tool_name and "browser_" in prior.tool_name and prior.tool_name == "browser_navigate"

    def create_execution_batches(self) -> list[list[ToolCall]]:
        """Group pending calls into parallel-safe batches.

        Returns:
            List of batches, where calls within a batch can run in parallel
        """
        if not self._pending_calls:
            return []

        # Detect dependencies first
        self.detect_dependencies()

        batches: list[list[ToolCall]] = []
        remaining = list(self._pending_calls)
        completed_ids: set[str] = set()

        while remaining:
            # Find calls with no unmet dependencies
            ready = [call for call in remaining if call.depends_on.issubset(completed_ids)]

            if not ready:
                # Circular dependency or bug - fall back to sequential (one at a time)
                logger.warning("Circular dependency detected, executing remaining calls one-by-one")
                for call in remaining:
                    batches.append([call])
                remaining.clear()
                break

            # Group parallelizable calls
            parallel_batch: list[ToolCall] = []
            sequential_batch: list[ToolCall] = []

            for call in ready:
                if self.can_parallelize(call) and len(parallel_batch) < self.max_concurrent:
                    parallel_batch.append(call)
                else:
                    sequential_batch.append(call)

            # Add parallel batch
            if parallel_batch:
                batches.append(parallel_batch)
                for call in parallel_batch:
                    completed_ids.add(call.id)
                    remaining.remove(call)

            # Add sequential calls as single-item batches
            for call in sequential_batch:
                batches.append([call])
                completed_ids.add(call.id)
                remaining.remove(call)

        return batches

    async def execute_all(
        self,
        executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> list[ToolResult]:
        """Execute all pending calls optimally.

        Args:
            executor: Async function that executes a tool call
                     Signature: (tool_name, arguments) -> result

        Returns:
            List of ToolResults for all calls
        """
        if not self._pending_calls:
            return []

        batches = self.create_execution_batches()
        all_results: list[ToolResult] = []
        total_sequential_time = 0
        actual_time = 0

        for batch in batches:
            batch_start = datetime.now()

            if len(batch) == 1:
                # Sequential execution
                call = batch[0]
                result = await self._execute_single(call, executor)
                all_results.append(result)
                self._stats["sequential_calls"] += 1
            else:
                # Parallel execution
                results = await self._execute_batch(batch, executor)
                all_results.extend(results)
                self._stats["parallel_batches"] += 1

                # Calculate time saved
                max_time = max(r.execution_time_ms for r in results)
                sum_time = sum(r.execution_time_ms for r in results)
                total_sequential_time += sum_time
                actual_time += max_time

            batch_time = (datetime.now() - batch_start).total_seconds() * 1000
            logger.debug(f"Batch executed: {len(batch)} calls in {batch_time:.0f}ms")

        # Store results
        for result in all_results:
            self._results[result.call_id] = result

        self._stats["total_calls"] += len(all_results)
        self._stats["time_saved_ms"] += max(0, total_sequential_time - actual_time)

        # Clear pending calls
        self._pending_calls.clear()

        return all_results

    async def _execute_single(
        self,
        call: ToolCall,
        executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> ToolResult:
        """Execute a single tool call.

        Args:
            call: The tool call to execute
            executor: The executor function

        Returns:
            ToolResult
        """
        start = datetime.now()

        try:
            result = await asyncio.wait_for(executor(call.tool_name, call.arguments), timeout=self.timeout_per_call)
            execution_time = (datetime.now() - start).total_seconds() * 1000

            return ToolResult(
                call_id=call.id,
                tool_name=call.tool_name,
                success=True,
                result=result,
                execution_time_ms=execution_time,
            )

        except TimeoutError:
            execution_time = (datetime.now() - start).total_seconds() * 1000
            logger.warning(f"Tool call timed out: {call.tool_name}")
            return ToolResult(
                call_id=call.id,
                tool_name=call.tool_name,
                success=False,
                result=None,
                error=f"Timeout after {self.timeout_per_call}s",
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"Tool call failed: {call.tool_name} - {e}")
            return ToolResult(
                call_id=call.id,
                tool_name=call.tool_name,
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time,
            )

    async def _execute_batch(
        self,
        batch: list[ToolCall],
        executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> list[ToolResult]:
        """Execute a batch of tool calls in parallel.

        Args:
            batch: List of tool calls to execute
            executor: The executor function

        Returns:
            List of ToolResults
        """
        tasks = [self._execute_single(call, executor) for call in batch]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert any exceptions to ToolResults, re-raise CancelledError
        processed_results: list[ToolResult] = []
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                # Re-raise CancelledError — don't treat cancellation as a tool result
                raise result
            if isinstance(result, Exception):
                processed_results.append(
                    ToolResult(
                        call_id=batch[i].id,
                        tool_name=batch[i].tool_name,
                        success=False,
                        result=None,
                        error=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        return {
            **self._stats,
            "parallel_enabled": self.enable_parallel,
            "max_concurrent": self.max_concurrent,
            "estimated_speedup": f"{(self._stats['time_saved_ms'] / max(1, self._stats['total_calls'])):.0f}ms/call",
        }


# Convenience function for quick parallel execution
async def execute_tools_parallel(
    tool_calls: list[dict[str, Any]],
    executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    max_concurrent: int = 5,
) -> list[ToolResult]:
    """Execute tool calls in parallel where safe.

    Args:
        tool_calls: List of dicts with 'name' and 'arguments' keys
        executor: Async function (tool_name, arguments) -> result
        max_concurrent: Max parallel calls

    Returns:
        List of ToolResults
    """
    parallel_executor = ParallelToolExecutor(max_concurrent=max_concurrent)

    for i, call in enumerate(tool_calls):
        parallel_executor.add_call(
            ToolCall(
                id=str(i),
                tool_name=call.get("name", ""),
                arguments=call.get("arguments", {}),
            )
        )

    return await parallel_executor.execute_all(executor)
