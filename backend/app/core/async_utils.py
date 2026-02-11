"""Python 3.11+ TaskGroup Utilities for Pythinker

Provides safer async task management with proper cancellation and exception handling.
Uses Python 3.11+ TaskGroup and except* syntax for structured concurrency.

Key Features:
- TaskGroup-based gather with proper exception handling
- Graceful cancellation propagation
- Optional return_exceptions mode for fault-tolerant execution
- Compatible with existing asyncio.gather patterns

Usage:
    # Basic usage (raises on first exception)
    results = await gather_with_taskgroup(coro1(), coro2(), coro3())

    # Return exceptions instead of raising
    results = await gather_with_taskgroup(coro1(), coro2(), return_exceptions=True)

    # With timeout
    async with asyncio.timeout(30):
        results = await gather_with_taskgroup(*coroutines)
"""

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TaskGroupResult:
    """Result container for TaskGroup execution.

    Provides detailed information about task execution including
    timing, success/failure counts, and individual results.
    """

    results: list[Any]
    errors: list[Exception]
    successful_count: int
    failed_count: int
    total_count: int
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    execution_time_ms: float = 0.0

    @property
    def all_successful(self) -> bool:
        """Check if all tasks completed successfully."""
        return self.failed_count == 0

    @property
    def any_successful(self) -> bool:
        """Check if at least one task succeeded."""
        return self.successful_count > 0

    def get_successful_results(self) -> list[Any]:
        """Get only successful results (filter out exceptions)."""
        return [r for r in self.results if not isinstance(r, Exception)]


async def gather_with_taskgroup(
    *coros: Coroutine[Any, Any, T],
    return_exceptions: bool = False,
) -> list[T | Exception]:
    """Execute coroutines concurrently using Python 3.11+ TaskGroup.

    This is a drop-in replacement for asyncio.gather that provides:
    - Proper cancellation semantics (all tasks cancelled on failure)
    - Structured concurrency via TaskGroup context manager
    - Better exception handling with except* syntax

    Args:
        *coros: Coroutines to execute concurrently
        return_exceptions: If True, exceptions are returned in results list
                          instead of being raised. Default False.

    Returns:
        List of results in the same order as input coroutines.
        If return_exceptions=True, exceptions appear as items in the list.

    Raises:
        ExceptionGroup: If return_exceptions=False and any task fails,
                       containing all exceptions from failed tasks.

    Example:
        # Raises if any task fails
        results = await gather_with_taskgroup(
            fetch_data("url1"),
            fetch_data("url2"),
            fetch_data("url3"),
        )

        # Returns exceptions in results list
        results = await gather_with_taskgroup(
            fetch_data("url1"),
            fetch_data("url2"),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Task {i} failed: {result}")
    """
    if not coros:
        return []

    # Results container: (index, result_or_exception)
    results: list[tuple[int, Any]] = []
    exceptions_occurred: list[Exception] = []

    async def capture_result(coro: Coroutine[Any, Any, T], idx: int) -> None:
        """Wrapper that captures both results and exceptions."""
        try:
            result = await coro
            results.append((idx, result))
        except asyncio.CancelledError:
            # Re-raise cancellation to propagate properly
            raise
        except Exception as e:
            if return_exceptions:
                results.append((idx, e))
            else:
                exceptions_occurred.append(e)
                raise

    try:
        async with asyncio.TaskGroup() as tg:
            for i, coro in enumerate(coros):
                tg.create_task(capture_result(coro, i))
    except* Exception as eg:
        if not return_exceptions:
            # Log the exception group for debugging
            logger.debug(f"TaskGroup caught {len(eg.exceptions)} exceptions")
            # Re-raise the group - caller handles it
            raise

    # Sort by original index and extract values
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


async def gather_with_taskgroup_detailed(
    *coros: Coroutine[Any, Any, T],
    return_exceptions: bool = True,
) -> TaskGroupResult:
    """Execute coroutines with detailed result tracking.

    Similar to gather_with_taskgroup but returns a TaskGroupResult
    with execution metadata.

    Args:
        *coros: Coroutines to execute
        return_exceptions: If True (default), continues on failure

    Returns:
        TaskGroupResult with detailed execution information
    """
    start_time = datetime.now()
    results: list[Any] = []
    errors: list[Exception] = []

    if not coros:
        return TaskGroupResult(
            results=[],
            errors=[],
            successful_count=0,
            failed_count=0,
            total_count=0,
            start_time=start_time,
            end_time=datetime.now(),
        )

    try:
        results = await gather_with_taskgroup(*coros, return_exceptions=return_exceptions)
    except* Exception as eg:
        # If we're not returning exceptions, collect them
        errors.extend(eg.exceptions)

    end_time = datetime.now()

    # Separate successes from failures
    errors.extend(r for r in results if isinstance(r, Exception))

    successful_count = len(results) - len([r for r in results if isinstance(r, Exception)])
    failed_count = len([r for r in results if isinstance(r, Exception)])

    return TaskGroupResult(
        results=results,
        errors=errors,
        successful_count=successful_count,
        failed_count=failed_count,
        total_count=len(coros),
        start_time=start_time,
        end_time=end_time,
        execution_time_ms=(end_time - start_time).total_seconds() * 1000,
    )


async def gather_with_timeout(
    *coros: Coroutine[Any, Any, T],
    timeout: float,  # noqa: ASYNC109
    return_exceptions: bool = False,
) -> list[T | Exception | asyncio.TimeoutError]:
    """Execute coroutines with a global timeout using TaskGroup.

    All tasks share a single timeout. If the timeout is reached,
    all pending tasks are cancelled.

    Args:
        *coros: Coroutines to execute
        timeout: Maximum seconds to wait for all tasks
        return_exceptions: If True, return exceptions in results

    Returns:
        List of results (may include TimeoutError if timed out)

    Raises:
        asyncio.TimeoutError: If timeout reached and return_exceptions=False
    """
    try:
        async with asyncio.timeout(timeout):
            return await gather_with_taskgroup(*coros, return_exceptions=return_exceptions)
    except TimeoutError:
        if return_exceptions:
            # Return timeout errors for all coroutines
            return [TimeoutError(f"Global timeout of {timeout}s exceeded")] * len(coros)
        raise


async def map_with_taskgroup(
    func: Any,
    items: list[Any],
    *,
    return_exceptions: bool = False,
    max_concurrency: int | None = None,
) -> list[Any]:
    """Map a coroutine function over items using TaskGroup.

    Similar to asyncio.gather but with a functional interface and
    optional concurrency limiting via semaphore.

    Args:
        func: Async function to apply to each item
        items: List of items to process
        return_exceptions: If True, return exceptions in results
        max_concurrency: Maximum concurrent executions (None = unlimited)

    Returns:
        List of results in same order as items

    Example:
        async def fetch(url):
            async with aiohttp.ClientSession() as session:
                return await session.get(url)

        results = await map_with_taskgroup(fetch, urls, max_concurrency=5)
    """
    if not items:
        return []

    if max_concurrency is not None and max_concurrency > 0:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def limited_call(item: Any) -> Any:
            async with semaphore:
                return await func(item)

        coros = [limited_call(item) for item in items]
    else:
        coros = [func(item) for item in items]

    return await gather_with_taskgroup(*coros, return_exceptions=return_exceptions)


class TaskGroupExecutor:
    """Reusable executor for TaskGroup-based concurrent execution.

    Provides a class-based interface with configuration and statistics.
    Useful for repeated batch operations with consistent settings.

    Usage:
        executor = TaskGroupExecutor(max_concurrency=5, return_exceptions=True)
        results = await executor.run(coro1(), coro2(), coro3())
        print(executor.stats)
    """

    def __init__(
        self,
        max_concurrency: int | None = None,
        return_exceptions: bool = False,
        timeout: float | None = None,
    ):
        """Initialize the executor.

        Args:
            max_concurrency: Maximum concurrent tasks (None = unlimited)
            return_exceptions: Whether to return exceptions vs raise
            timeout: Optional global timeout for all tasks
        """
        self.max_concurrency = max_concurrency
        self.return_exceptions = return_exceptions
        self.timeout = timeout

        # Statistics
        self._total_runs = 0
        self._total_tasks = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_time_ms = 0.0

    @property
    def stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        return {
            "total_runs": self._total_runs,
            "total_tasks": self._total_tasks,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "total_time_ms": self._total_time_ms,
            "success_rate": self._total_successes / max(self._total_tasks, 1),
            "avg_time_per_run_ms": self._total_time_ms / max(self._total_runs, 1),
        }

    async def run(self, *coros: Coroutine[Any, Any, T]) -> list[T | Exception]:
        """Execute coroutines with configured settings.

        Args:
            *coros: Coroutines to execute

        Returns:
            List of results
        """
        start_time = datetime.now()
        self._total_runs += 1
        self._total_tasks += len(coros)

        try:
            if self.max_concurrency:
                # Use semaphore for concurrency limiting
                semaphore = asyncio.Semaphore(self.max_concurrency)

                async def limited(coro: Coroutine[Any, Any, T]) -> T:
                    async with semaphore:
                        return await coro

                limited_coros = [limited(c) for c in coros]

                if self.timeout:
                    results = await gather_with_timeout(
                        *limited_coros,
                        timeout=self.timeout,
                        return_exceptions=self.return_exceptions,
                    )
                else:
                    results = await gather_with_taskgroup(*limited_coros, return_exceptions=self.return_exceptions)
            elif self.timeout:
                results = await gather_with_timeout(
                    *coros,
                    timeout=self.timeout,
                    return_exceptions=self.return_exceptions,
                )
            else:
                results = await gather_with_taskgroup(*coros, return_exceptions=self.return_exceptions)

            # Update statistics
            for result in results:
                if isinstance(result, Exception):
                    self._total_failures += 1
                else:
                    self._total_successes += 1

            return results

        finally:
            end_time = datetime.now()
            self._total_time_ms += (end_time - start_time).total_seconds() * 1000

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._total_runs = 0
        self._total_tasks = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_time_ms = 0.0


# Convenience function for feature-flag controlled migration
async def gather_compat(
    *coros: Coroutine[Any, Any, T],
    return_exceptions: bool = False,
    use_taskgroup: bool = False,
) -> list[T | Exception]:
    """Compatibility wrapper for gradual migration from asyncio.gather.

    Allows switching between asyncio.gather and TaskGroup based on
    feature flag, enabling A/B testing and gradual rollout.

    Args:
        *coros: Coroutines to execute
        return_exceptions: If True, return exceptions in results
        use_taskgroup: If True, use TaskGroup; otherwise use asyncio.gather

    Returns:
        List of results
    """
    if use_taskgroup:
        return await gather_with_taskgroup(*coros, return_exceptions=return_exceptions)
    # Use traditional asyncio.gather
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)


__all__ = [
    "TaskGroupExecutor",
    "TaskGroupResult",
    "gather_compat",
    "gather_with_taskgroup",
    "gather_with_taskgroup_detailed",
    "gather_with_timeout",
    "map_with_taskgroup",
]
