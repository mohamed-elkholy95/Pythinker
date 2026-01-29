"""Parallel Step Executor for Pythinker

Enables parallel execution of independent plan steps using DAG-based scheduling.
Steps with no dependencies or all dependencies satisfied can execute concurrently.

Features:
- Semaphore-based concurrency control
- Dependency-aware scheduling
- Error propagation and cascade blocking
- Progress tracking and metrics

Usage:
    executor = ParallelExecutor(max_concurrency=3)
    async for event in executor.execute_plan(plan, execute_step_func):
        yield event
"""
import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
)

from app.domain.models.event import BaseEvent, PlanEvent, PlanStatus
from app.domain.models.plan import ExecutionStatus, Plan, Step

logger = logging.getLogger(__name__)


class ParallelExecutionMode(str, Enum):
    """Execution mode for the parallel executor."""
    SEQUENTIAL = "sequential"  # Execute one step at a time (default)
    PARALLEL = "parallel"  # Execute independent steps in parallel
    ADAPTIVE = "adaptive"  # Switch between modes based on step characteristics


@dataclass
class ExecutionStats:
    """Statistics for parallel execution."""
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    blocked_steps: int = 0
    skipped_steps: int = 0
    parallel_batches: int = 0
    max_parallel_achieved: int = 0
    total_wait_time_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "blocked_steps": self.blocked_steps,
            "skipped_steps": self.skipped_steps,
            "parallel_batches": self.parallel_batches,
            "max_parallel_achieved": self.max_parallel_achieved,
            "total_wait_time_ms": self.total_wait_time_ms,
        }


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    success: bool
    result: str | None = None
    error: str | None = None
    events: list[BaseEvent] = field(default_factory=list)


class ParallelExecutor:
    """Executes plan steps in parallel based on dependency graph.

    The executor analyzes step dependencies and executes independent
    steps concurrently while respecting the dependency DAG.

    Args:
        max_concurrency: Maximum number of concurrent step executions
        mode: Execution mode (sequential, parallel, adaptive)
    """

    def __init__(
        self,
        max_concurrency: int = 3,
        mode: ParallelExecutionMode = ParallelExecutionMode.PARALLEL,
    ):
        self.max_concurrency = max_concurrency
        self.mode = mode
        self._semaphore: asyncio.Semaphore | None = None
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._stats = ExecutionStats()

    def reset(self) -> None:
        """Reset executor state for a new plan."""
        self._completed = set()
        self._failed = set()
        self._stats = ExecutionStats()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

    def get_stats(self) -> ExecutionStats:
        """Get execution statistics."""
        return self._stats

    def _get_ready_steps(self, plan: Plan) -> list[Step]:
        """Get steps that are ready to execute (dependencies satisfied).

        Args:
            plan: The plan to analyze

        Returns:
            List of steps ready for execution
        """
        ready = []
        for step in plan.steps:
            if step.status != ExecutionStatus.PENDING:
                continue

            # Check if all dependencies are completed
            deps_satisfied = all(
                dep_id in self._completed
                for dep_id in step.dependencies
            )

            # Check if any dependency failed (should block this step)
            deps_failed = any(
                dep_id in self._failed
                for dep_id in step.dependencies
            )

            if deps_failed:
                # Mark as blocked
                failed_dep = next(
                    dep_id for dep_id in step.dependencies
                    if dep_id in self._failed
                )
                step.mark_blocked(
                    reason=f"Dependency {failed_dep} failed",
                    blocked_by=failed_dep
                )
                self._stats.blocked_steps += 1
                continue

            if deps_satisfied:
                ready.append(step)

        return ready

    async def _execute_step_with_limit(
        self,
        step: Step,
        execute_func: Callable[[Step], Awaitable[StepResult]],
    ) -> StepResult:
        """Execute a step with concurrency limiting.

        Args:
            step: Step to execute
            execute_func: Function that executes the step

        Returns:
            StepResult with execution outcome
        """
        async with self._semaphore:
            logger.debug(f"Executing step {step.id}: {step.description[:50]}")
            try:
                result = await execute_func(step)
                return result
            except Exception as e:
                logger.error(f"Step {step.id} failed with exception: {e}")
                return StepResult(
                    step_id=step.id,
                    success=False,
                    error=str(e),
                )

    async def execute_plan(
        self,
        plan: Plan,
        execute_func: Callable[[Step], Awaitable[StepResult]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute plan steps respecting dependencies.

        This generator executes steps in parallel where possible,
        yielding events as progress is made.

        Args:
            plan: Plan to execute
            execute_func: Async function that executes a single step

        Yields:
            Events from step execution
        """
        self.reset()
        self._stats.total_steps = len(plan.steps)

        # Ensure dependencies are inferred if not set
        if not any(step.dependencies for step in plan.steps):
            if self.mode == ParallelExecutionMode.PARALLEL:
                # For parallel mode, try smart dependency inference
                plan.infer_smart_dependencies()
            else:
                # For sequential mode, use simple sequential dependencies
                plan.infer_sequential_dependencies()

        # Execute in batches until all steps are done
        while True:
            # Get steps ready to execute
            ready_steps = self._get_ready_steps(plan)

            if not ready_steps:
                # No more steps to execute
                break

            self._stats.parallel_batches += 1
            self._stats.max_parallel_achieved = max(
                self._stats.max_parallel_achieved,
                len(ready_steps)
            )

            logger.info(f"Executing batch of {len(ready_steps)} steps in parallel")

            # Execute steps based on mode
            if self.mode == ParallelExecutionMode.SEQUENTIAL or len(ready_steps) == 1:
                # Sequential execution
                for step in ready_steps:
                    step.status = ExecutionStatus.RUNNING

                    yield PlanEvent(
                        status=PlanStatus.RUNNING,
                        plan=plan,
                    )

                    result = await self._execute_step_with_limit(step, execute_func)
                    async for event in self._process_result(plan, step, result):
                        yield event

            else:
                # Parallel execution
                for step in ready_steps:
                    step.status = ExecutionStatus.RUNNING

                yield PlanEvent(
                    status=PlanStatus.RUNNING,
                    plan=plan,
                )

                # Create tasks for parallel execution
                tasks = [
                    asyncio.create_task(
                        self._execute_step_with_limit(step, execute_func)
                    )
                    for step in ready_steps
                ]

                # Wait for all tasks to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for step, result in zip(ready_steps, results):
                    if isinstance(result, Exception):
                        result = StepResult(
                            step_id=step.id,
                            success=False,
                            error=str(result),
                        )
                    async for event in self._process_result(plan, step, result):
                        yield event

        # Final status event
        progress = plan.get_progress()
        if progress["failed"] > 0 or progress["blocked"] > 0:
            plan.status = ExecutionStatus.FAILED
        elif progress["completed"] + progress["skipped"] == progress["total"]:
            plan.status = ExecutionStatus.COMPLETED
        else:
            plan.status = ExecutionStatus.PENDING

        yield PlanEvent(
            status=PlanStatus.FINISHED if plan.status == ExecutionStatus.COMPLETED else PlanStatus.RUNNING,
            plan=plan,
        )

    async def _process_result(
        self,
        plan: Plan,
        step: Step,
        result: StepResult,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Process the result of a step execution.

        Args:
            plan: The plan being executed
            step: The step that was executed
            result: The result of execution

        Yields:
            Events for the step result
        """
        # Yield any events from the step execution
        for event in result.events:
            yield event

        # Update step status
        if result.success:
            step.status = ExecutionStatus.COMPLETED
            step.result = result.result
            step.success = True
            self._completed.add(step.id)
            self._stats.completed_steps += 1
            logger.info(f"Step {step.id} completed successfully")
        else:
            step.status = ExecutionStatus.FAILED
            step.error = result.error
            step.success = False
            self._failed.add(step.id)
            self._stats.failed_steps += 1
            logger.warning(f"Step {step.id} failed: {result.error}")

            # Cascade block dependent steps
            blocked_ids = plan.mark_blocked_cascade(
                step.id,
                f"Dependency failed: {result.error[:100] if result.error else 'Unknown error'}"
            )
            self._stats.blocked_steps += len(blocked_ids)

        # Emit plan update
        yield PlanEvent(
            status=PlanStatus.RUNNING,
            plan=plan,
        )

    def can_parallelize(self, plan: Plan) -> bool:
        """Check if a plan has opportunities for parallelization.

        Args:
            plan: Plan to analyze

        Returns:
            True if plan has independent steps that can run in parallel
        """
        if len(plan.steps) < 2:
            return False

        # Build dependency graph
        step_ids = {step.id for step in plan.steps}
        has_independent = False

        for i, step in enumerate(plan.steps):
            # Check if step has no dependencies or only external dependencies
            internal_deps = [d for d in step.dependencies if d in step_ids]

            if not internal_deps and i > 0:
                # This step could potentially run in parallel with others
                has_independent = True
                break

        return has_independent

    def estimate_parallelism(self, plan: Plan) -> dict[str, Any]:
        """Estimate the parallelism potential of a plan.

        Args:
            plan: Plan to analyze

        Returns:
            Dictionary with parallelism metrics
        """
        if len(plan.steps) == 0:
            return {"max_parallel": 0, "critical_path_length": 0, "speedup_factor": 1.0}

        # Build dependency graph
        deps_graph: dict[str, set[str]] = {}
        for step in plan.steps:
            deps_graph[step.id] = set(step.dependencies)

        # Calculate critical path length (longest chain)
        def get_depth(step_id: str, memo: dict[str, int]) -> int:
            if step_id in memo:
                return memo[step_id]
            step = plan.get_step_by_id(step_id)
            if not step or not step.dependencies:
                memo[step_id] = 1
                return 1
            max_dep_depth = max(
                get_depth(dep_id, memo)
                for dep_id in step.dependencies
                if plan.get_step_by_id(dep_id)
            ) if step.dependencies else 0
            memo[step_id] = max_dep_depth + 1
            return memo[step_id]

        memo: dict[str, int] = {}
        critical_path = max(get_depth(step.id, memo) for step in plan.steps)

        # Calculate max parallel steps at any level
        levels: dict[int, int] = {}
        for step in plan.steps:
            depth = memo.get(step.id, 1)
            levels[depth] = levels.get(depth, 0) + 1

        max_parallel = max(levels.values()) if levels else 1

        # Speedup factor (assuming perfect parallelism)
        speedup = len(plan.steps) / critical_path if critical_path > 0 else 1.0

        return {
            "max_parallel": max_parallel,
            "critical_path_length": critical_path,
            "speedup_factor": round(speedup, 2),
            "total_steps": len(plan.steps),
        }
