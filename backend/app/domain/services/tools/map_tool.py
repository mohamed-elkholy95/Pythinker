"""MapTool - Generic Parallel Batch Execution.

Provides a reusable pattern for executing batches of tasks in parallel
with configurable concurrency, error handling, and progress tracking.

Example usage:
    class SearchWorker:
        async def execute(self, task: MapTask) -> Any:
            return await search_engine.query(task.input)

    worker = SearchWorker()
    map_tool = MapTool(worker=worker, max_concurrency=5)
    tasks = [MapTask(id=str(i), input=query) for i, query in enumerate(queries)]
    results = await map_tool.execute(tasks)
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MapTask(BaseModel):
    """A task to be executed by the MapTool.

    Attributes:
        id: Unique identifier for the task
        input: The input data to be processed by the worker
        metadata: Optional metadata for tracking or filtering
    """

    id: str
    input: Any
    metadata: dict[str, Any] = Field(default_factory=dict)


class MapResult(BaseModel):
    """Result of a MapTask execution.

    Attributes:
        id: The task ID (matches MapTask.id)
        success: Whether the task completed successfully
        output: The worker's output (if successful)
        error: Error message (if failed)
        duration_ms: Execution duration in milliseconds
    """

    id: str
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0


class WorkerProtocol(Protocol):
    """Protocol for workers that can execute MapTasks.

    Workers must implement an async execute method that takes a MapTask
    and returns Any output.
    """

    async def execute(self, task: MapTask) -> Any:
        """Execute a single task and return the result.

        Args:
            task: The MapTask to execute

        Returns:
            The execution result (any type)

        Raises:
            Any exception if the task fails
        """
        ...


# Type alias for progress callback
ProgressCallback = Callable[
    [str, str, int, int, MapResult | None],  # task_id, status, completed, total, result
    None,
]


class MapTool:
    """Generic parallel batch execution tool.

    Executes a list of MapTasks using a worker with configurable concurrency,
    error handling, and optional retry logic.

    Attributes:
        worker: The worker that executes individual tasks
        max_concurrency: Maximum number of concurrent task executions
        on_progress: Optional callback for progress updates
    """

    def __init__(
        self,
        worker: WorkerProtocol,
        max_concurrency: int = 10,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Initialize the MapTool.

        Args:
            worker: Worker implementing WorkerProtocol
            max_concurrency: Maximum concurrent executions (default: 10)
            on_progress: Optional callback for progress updates
        """
        self.worker = worker
        self.max_concurrency = max_concurrency
        self.on_progress = on_progress

    async def execute(
        self,
        tasks: list[MapTask],
        timeout_per_task: float | None = None,
    ) -> list[MapResult]:
        """Execute tasks in parallel with concurrency control.

        Args:
            tasks: List of MapTasks to execute
            timeout_per_task: Optional timeout per task in seconds

        Returns:
            List of MapResults in the same order as input tasks
        """
        if not tasks:
            logger.debug("No tasks to execute")
            return []

        total_tasks = len(tasks)
        logger.info(f"Starting parallel execution of {total_tasks} tasks with max_concurrency={self.max_concurrency}")

        # Use semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrency)

        # Track completion for progress
        completed_count = 0
        completed_lock = asyncio.Lock()

        async def execute_with_semaphore(task: MapTask) -> MapResult:
            """Execute a single task with semaphore control."""
            nonlocal completed_count

            async with semaphore:
                start_time = time.perf_counter()

                try:
                    # Notify progress: started
                    if self.on_progress:
                        self.on_progress(task.id, "started", completed_count, total_tasks, None)

                    # Execute with optional timeout
                    if timeout_per_task is not None:
                        try:
                            output = await asyncio.wait_for(
                                self.worker.execute(task),
                                timeout=timeout_per_task,
                            )
                        except TimeoutError:
                            duration_ms = (time.perf_counter() - start_time) * 1000
                            logger.warning(f"Task {task.id} timed out after {timeout_per_task}s")
                            result = MapResult(
                                id=task.id,
                                success=False,
                                error=f"Task timeout after {timeout_per_task}s",
                                duration_ms=duration_ms,
                            )
                            async with completed_lock:
                                completed_count += 1
                            if self.on_progress:
                                self.on_progress(task.id, "completed", completed_count, total_tasks, result)
                            return result
                    else:
                        output = await self.worker.execute(task)

                    duration_ms = (time.perf_counter() - start_time) * 1000
                    result = MapResult(
                        id=task.id,
                        success=True,
                        output=output,
                        duration_ms=duration_ms,
                    )

                    async with completed_lock:
                        completed_count += 1

                    if self.on_progress:
                        self.on_progress(task.id, "completed", completed_count, total_tasks, result)

                    logger.debug(f"Task {task.id} completed in {duration_ms:.2f}ms")
                    return result

                except Exception as e:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    error_msg = str(e)
                    logger.warning(f"Task {task.id} failed: {error_msg}")

                    result = MapResult(
                        id=task.id,
                        success=False,
                        error=error_msg,
                        duration_ms=duration_ms,
                    )

                    async with completed_lock:
                        completed_count += 1

                    if self.on_progress:
                        self.on_progress(task.id, "completed", completed_count, total_tasks, result)

                    return result

        # Create tasks preserving order
        coroutines = [execute_with_semaphore(task) for task in tasks]

        # Execute all tasks and gather results
        results = await asyncio.gather(*coroutines)

        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        logger.info(f"Completed {len(results)} tasks: {successful} successful, {failed} failed")

        return list(results)

    async def execute_with_retry(
        self,
        tasks: list[MapTask],
        max_retries: int = 2,
        retry_delay: float = 1.0,
        timeout_per_task: float | None = None,
    ) -> list[MapResult]:
        """Execute tasks with automatic retry for failures.

        Args:
            tasks: List of MapTasks to execute
            max_retries: Maximum number of retry attempts per task
            retry_delay: Delay between retries in seconds
            timeout_per_task: Optional timeout per task in seconds

        Returns:
            List of MapResults in the same order as input tasks
        """
        if not tasks:
            return []

        logger.info(
            f"Starting execution with retry of {len(tasks)} tasks "
            f"(max_retries={max_retries}, retry_delay={retry_delay}s)"
        )

        # First attempt
        results = await self.execute(tasks, timeout_per_task=timeout_per_task)

        # Track which tasks need retry
        pending_retries: list[tuple[int, MapTask]] = []  # (original_index, task)
        for i, result in enumerate(results):
            if not result.success:
                pending_retries.append((i, tasks[i]))

        # Retry loop
        for attempt in range(max_retries):
            if not pending_retries:
                break

            logger.info(f"Retry attempt {attempt + 1}/{max_retries} for {len(pending_retries)} failed tasks")

            # Wait before retry
            await asyncio.sleep(retry_delay)

            # Execute retry batch
            retry_tasks = [task for _, task in pending_retries]
            retry_results = await self.execute(retry_tasks, timeout_per_task=timeout_per_task)

            # Update results and collect still-failing tasks
            new_pending: list[tuple[int, MapTask]] = []
            for (original_idx, task), result in zip(pending_retries, retry_results, strict=True):
                results[original_idx] = result
                if not result.success:
                    new_pending.append((original_idx, task))

            pending_retries = new_pending

        # Log final summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        logger.info(
            f"Execute with retry completed: {successful} successful, {failed} failed (after {max_retries} max retries)"
        )

        return results
