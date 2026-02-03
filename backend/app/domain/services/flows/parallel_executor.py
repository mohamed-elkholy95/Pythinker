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

from app.core.async_utils import gather_compat
from app.core.config import get_settings
from app.domain.models.event import BaseEvent, PlanEvent, PlanStatus
from app.domain.models.plan import ExecutionStatus, Plan, Step

logger = logging.getLogger(__name__)


class ParallelExecutionMode(str, Enum):
    """Execution mode for the parallel executor."""

    SEQUENTIAL = "sequential"  # Execute one step at a time (default)
    PARALLEL = "parallel"  # Execute independent steps in parallel
    ADAPTIVE = "adaptive"  # Switch between modes based on step characteristics


class ResourceThrottleLevel(str, Enum):
    """Resource throttling levels for adaptive concurrency."""

    NONE = "none"  # No throttling
    LIGHT = "light"  # Reduce concurrency by 25%
    MODERATE = "moderate"  # Reduce concurrency by 50%
    HEAVY = "heavy"  # Reduce concurrency by 75%


@dataclass
class ParallelExecutorConfig:
    """Configuration for parallel executor.

    Inspired by Manus AI's parallel processing capability.
    """

    max_concurrency: int = 5  # Increased from 3 for wider research
    min_concurrency: int = 1
    mode: ParallelExecutionMode = ParallelExecutionMode.PARALLEL
    throttle_level: ResourceThrottleLevel = ResourceThrottleLevel.NONE
    enable_step_parallel_flag: bool = True  # Honor step.parallel_processing flag
    resource_aware: bool = True  # Enable resource-aware throttling
    batch_timeout_seconds: int = 300  # Timeout for each parallel batch

    def get_effective_concurrency(self) -> int:
        """Get effective concurrency based on throttle level."""
        multipliers = {
            ResourceThrottleLevel.NONE: 1.0,
            ResourceThrottleLevel.LIGHT: 0.75,
            ResourceThrottleLevel.MODERATE: 0.5,
            ResourceThrottleLevel.HEAVY: 0.25,
        }
        multiplier = multipliers.get(self.throttle_level, 1.0)
        return max(self.min_concurrency, int(self.max_concurrency * multiplier))


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

    Inspired by Manus AI's parallel processing (Map) capability for
    dividing tasks into homogeneous subtasks.

    Args:
        max_concurrency: Maximum number of concurrent step executions
        mode: Execution mode (sequential, parallel, adaptive)
        config: Optional ParallelExecutorConfig for advanced settings
    """

    def __init__(
        self,
        max_concurrency: int = 5,  # Increased default for wider research
        mode: ParallelExecutionMode = ParallelExecutionMode.PARALLEL,
        config: ParallelExecutorConfig | None = None,
    ):
        if config:
            self.config = config
            self.max_concurrency = config.get_effective_concurrency()
            self.mode = config.mode
        else:
            self.config = ParallelExecutorConfig(
                max_concurrency=max_concurrency,
                mode=mode,
            )
            self.max_concurrency = max_concurrency
            self.mode = mode

        self._semaphore: asyncio.Semaphore | None = None
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._stats = ExecutionStats()
        self._resource_pressure: float = 0.0  # 0-1 scale

    def reset(self) -> None:
        """Reset executor state for a new plan."""
        self._completed = set()
        self._failed = set()
        self._stats = ExecutionStats()
        self._resource_pressure = 0.0
        effective_concurrency = self.config.get_effective_concurrency()
        self._semaphore = asyncio.Semaphore(effective_concurrency)
        logger.debug(f"ParallelExecutor reset with concurrency={effective_concurrency}")

    def set_throttle_level(self, level: ResourceThrottleLevel) -> None:
        """Dynamically adjust throttle level.

        Args:
            level: New throttle level
        """
        old_concurrency = self.config.get_effective_concurrency()
        self.config.throttle_level = level
        new_concurrency = self.config.get_effective_concurrency()

        if old_concurrency != new_concurrency:
            self._semaphore = asyncio.Semaphore(new_concurrency)
            logger.info(f"Throttle level changed to {level.value}, concurrency: {old_concurrency} -> {new_concurrency}")

    def update_resource_pressure(self, pressure: float) -> None:
        """Update resource pressure for adaptive throttling.

        Args:
            pressure: Resource pressure from 0 (low) to 1 (high)
        """
        self._resource_pressure = max(0.0, min(1.0, pressure))

        if self.config.resource_aware:
            # Auto-adjust throttle based on pressure
            if pressure > 0.9:
                self.set_throttle_level(ResourceThrottleLevel.HEAVY)
            elif pressure > 0.7:
                self.set_throttle_level(ResourceThrottleLevel.MODERATE)
            elif pressure > 0.5:
                self.set_throttle_level(ResourceThrottleLevel.LIGHT)
            else:
                self.set_throttle_level(ResourceThrottleLevel.NONE)

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
            deps_satisfied = all(dep_id in self._completed for dep_id in step.dependencies)

            # Check if any dependency failed (should block this step)
            deps_failed = any(dep_id in self._failed for dep_id in step.dependencies)

            if deps_failed:
                # Mark as blocked
                failed_dep = next(dep_id for dep_id in step.dependencies if dep_id in self._failed)
                step.mark_blocked(reason=f"Dependency {failed_dep} failed", blocked_by=failed_dep)
                self._stats.blocked_steps += 1
                continue

            if deps_satisfied:
                ready.append(step)

        return ready

    def _filter_parallelizable_steps(self, ready_steps: list[Step]) -> tuple[list[Step], list[Step]]:
        """Separate steps into parallelizable and sequential groups.

        Honors the step.parallel_processing flag if enable_step_parallel_flag is True.
        Inspired by Manus's parallel_processing capability flag.

        Args:
            ready_steps: Steps ready for execution

        Returns:
            Tuple of (parallel_steps, sequential_steps)
        """
        if not self.config.enable_step_parallel_flag:
            # All steps are parallelizable if flag checking is disabled
            return ready_steps, []

        parallel_steps = []
        sequential_steps = []

        for step in ready_steps:
            # Check for explicit parallel_processing flag on step
            parallel_flag = getattr(step, "parallel_processing", None)

            if parallel_flag is False:
                # Explicitly marked as sequential
                sequential_steps.append(step)
            elif parallel_flag is True:
                # Explicitly marked as parallel
                parallel_steps.append(step)
            else:
                # Default: check if step appears safe to parallelize
                if self._is_step_safe_for_parallel(step):
                    parallel_steps.append(step)
                else:
                    sequential_steps.append(step)

        return parallel_steps, sequential_steps

    def _is_step_safe_for_parallel(self, step: Step) -> bool:
        """Check if a step is safe for parallel execution.

        Args:
            step: Step to check

        Returns:
            True if step appears safe for parallel execution
        """
        # Heuristics for safe parallel execution
        description_lower = step.description.lower()

        # Steps that should run sequentially (state-modifying)
        sequential_keywords = [
            "delete",
            "remove",
            "modify",
            "update",
            "write",
            "install",
            "uninstall",
            "configure",
            "setup",
            "create directory",
            "mkdir",
            "move",
            "rename",
        ]

        for keyword in sequential_keywords:
            if keyword in description_lower:
                return False

        # Steps that are safe to parallelize (read-only)
        parallel_keywords = [
            "search",
            "read",
            "fetch",
            "get",
            "find",
            "analyze",
            "research",
            "browse",
            "view",
            "list",
            "check",
        ]

        for keyword in parallel_keywords:
            if keyword in description_lower:
                return True

        # Default: allow parallel for unknown
        return True

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
                return await execute_func(step)
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
            self._stats.max_parallel_achieved = max(self._stats.max_parallel_achieved, len(ready_steps))

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
                tasks = [asyncio.create_task(self._execute_step_with_limit(step, execute_func)) for step in ready_steps]

                # Use TaskGroup-based gather if feature flag enabled (Phase 1 enhancement)
                # This provides better cancellation and exception handling
                settings = get_settings()
                use_taskgroup = settings.feature_taskgroup_enabled

                # Wait for all tasks to complete using appropriate method
                results = await gather_compat(*tasks, return_exceptions=True, use_taskgroup=use_taskgroup)

                # Process results
                for step, result in zip(ready_steps, results, strict=False):
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
                step.id, f"Dependency failed: {result.error[:100] if result.error else 'Unknown error'}"
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
            max_dep_depth = (
                max(get_depth(dep_id, memo) for dep_id in step.dependencies if plan.get_step_by_id(dep_id))
                if step.dependencies
                else 0
            )
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

    @staticmethod
    def aggregate_results(results: list[StepResult], strategy: str = "merge") -> dict[str, Any]:
        """Aggregate results from parallel step execution.

        Utility for combining results from concurrent operations,
        inspired by Manus's result aggregation patterns.

        Args:
            results: List of step results to aggregate
            strategy: Aggregation strategy (merge, best, all)

        Returns:
            Aggregated result dictionary
        """
        if not results:
            return {"success": False, "message": "No results to aggregate"}

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if strategy == "merge":
            # Merge all successful results
            merged_data = []
            for r in successful:
                if r.result:
                    merged_data.append(
                        {
                            "step_id": r.step_id,
                            "result": r.result,
                        }
                    )

            return {
                "success": len(failed) == 0,
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "merged_results": merged_data,
                "errors": [{"step_id": r.step_id, "error": r.error} for r in failed],
            }

        if strategy == "best":
            # Return best result (first successful or least error)
            if successful:
                return {
                    "success": True,
                    "best_result": successful[0].result,
                    "step_id": successful[0].step_id,
                }
            return {
                "success": False,
                "error": failed[0].error if failed else "No results",
            }

        # all
        # Return all results as-is
        return {
            "success": len(failed) == 0,
            "results": [
                {
                    "step_id": r.step_id,
                    "success": r.success,
                    "result": r.result,
                    "error": r.error,
                }
                for r in results
            ],
        }

    def get_parallelism_report(self) -> dict[str, Any]:
        """Get a report on parallelism performance.

        Returns:
            Dictionary with parallelism metrics
        """
        stats = self._stats
        efficiency = 0.0
        if stats.total_steps > 0:
            efficiency = stats.completed_steps / stats.total_steps

        parallel_efficiency = 0.0
        if stats.parallel_batches > 0 and stats.max_parallel_achieved > 0:
            # How well we utilized parallel capacity
            actual_parallel = stats.completed_steps / max(stats.parallel_batches, 1)
            parallel_efficiency = min(1.0, actual_parallel / self.max_concurrency)

        return {
            "stats": stats.to_dict(),
            "config": {
                "max_concurrency": self.config.max_concurrency,
                "effective_concurrency": self.config.get_effective_concurrency(),
                "mode": self.mode.value,
                "throttle_level": self.config.throttle_level.value,
            },
            "metrics": {
                "completion_efficiency": round(efficiency, 2),
                "parallel_efficiency": round(parallel_efficiency, 2),
                "resource_pressure": round(self._resource_pressure, 2),
            },
        }
