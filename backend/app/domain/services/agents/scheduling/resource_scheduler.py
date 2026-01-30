"""
Resource-Aware Scheduling module.

This module provides scheduling based on available resources
including tokens, rate limits, and time budgets.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """Types of resources to track."""

    TOKENS = "tokens"
    API_CALLS = "api_calls"
    TIME = "time"
    MEMORY = "memory"
    CONCURRENT_TASKS = "concurrent_tasks"


class SchedulePriority(str, Enum):
    """Priority levels for scheduled tasks."""

    CRITICAL = "critical"  # Must execute immediately
    HIGH = "high"  # Execute soon
    NORMAL = "normal"  # Standard scheduling
    LOW = "low"  # Can wait
    BACKGROUND = "background"  # Execute when resources available


@dataclass
class ResourceBudget:
    """Budget for a specific resource."""

    resource_type: ResourceType
    total: float
    used: float = 0.0
    reserved: float = 0.0
    reset_at: datetime | None = None

    @property
    def available(self) -> float:
        """Get available resource amount."""
        return max(0, self.total - self.used - self.reserved)

    @property
    def usage_percent(self) -> float:
        """Get usage percentage."""
        if self.total == 0:
            return 0.0
        return (self.used + self.reserved) / self.total * 100

    def can_allocate(self, amount: float) -> bool:
        """Check if amount can be allocated."""
        return amount <= self.available

    def allocate(self, amount: float) -> bool:
        """Allocate resource amount.

        Returns:
            True if successful, False if insufficient resources
        """
        if not self.can_allocate(amount):
            return False
        self.used += amount
        return True

    def reserve(self, amount: float) -> bool:
        """Reserve resource amount for future use.

        Returns:
            True if successful, False if insufficient resources
        """
        if amount > self.available:
            return False
        self.reserved += amount
        return True

    def release(self, amount: float) -> None:
        """Release allocated resources."""
        self.used = max(0, self.used - amount)

    def release_reservation(self, amount: float) -> None:
        """Release reserved resources."""
        self.reserved = max(0, self.reserved - amount)

    def should_reset(self) -> bool:
        """Check if resources should be reset."""
        if self.reset_at:
            return datetime.now() >= self.reset_at
        return False


@dataclass
class ScheduledTask:
    """A task scheduled for execution."""

    task_id: str
    description: str
    priority: SchedulePriority = SchedulePriority.NORMAL
    resource_requirements: dict[ResourceType, float] = field(default_factory=dict)
    scheduled_at: datetime = field(default_factory=datetime.now)
    execute_after: datetime | None = None
    deadline: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_ready(self) -> bool:
        """Check if task is ready to execute."""
        if self.execute_after:
            return datetime.now() >= self.execute_after
        return True

    def is_overdue(self) -> bool:
        """Check if task is past deadline."""
        if self.deadline:
            return datetime.now() > self.deadline
        return False

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries


@dataclass
class SchedulerMetrics:
    """Metrics for the scheduler."""

    tasks_scheduled: int = 0
    tasks_executed: int = 0
    tasks_delayed: int = 0
    tasks_dropped: int = 0
    average_wait_ms: float = 0.0
    resource_exhaustion_count: int = 0


class ResourceScheduler:
    """Scheduler for resource-aware task execution.

    Manages task scheduling based on:
    - Available token budget
    - API rate limits
    - Time constraints
    - System resources
    """

    # Default rate limits per minute
    DEFAULT_RATE_LIMITS: ClassVar[dict[ResourceType, int]] = {
        ResourceType.API_CALLS: 60,  # 60 calls per minute
        ResourceType.TOKENS: 100000,  # 100k tokens per minute
    }

    # Priority to delay mapping (seconds)
    PRIORITY_DELAYS: ClassVar[dict[SchedulePriority, int]] = {
        SchedulePriority.CRITICAL: 0,
        SchedulePriority.HIGH: 1,
        SchedulePriority.NORMAL: 5,
        SchedulePriority.LOW: 30,
        SchedulePriority.BACKGROUND: 60,
    }

    def __init__(
        self,
        token_budget: int = 100000,
        api_call_limit: int = 60,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize the resource scheduler.

        Args:
            token_budget: Token budget per minute
            api_call_limit: API calls per minute
            max_concurrent: Maximum concurrent tasks
        """
        self._budgets: dict[ResourceType, ResourceBudget] = {
            ResourceType.TOKENS: ResourceBudget(
                resource_type=ResourceType.TOKENS,
                total=token_budget,
                reset_at=datetime.now() + timedelta(minutes=1),
            ),
            ResourceType.API_CALLS: ResourceBudget(
                resource_type=ResourceType.API_CALLS,
                total=api_call_limit,
                reset_at=datetime.now() + timedelta(minutes=1),
            ),
            ResourceType.CONCURRENT_TASKS: ResourceBudget(
                resource_type=ResourceType.CONCURRENT_TASKS,
                total=max_concurrent,
            ),
        }

        self._queue: list[ScheduledTask] = []
        self._running: dict[str, ScheduledTask] = {}
        self._metrics = SchedulerMetrics()
        self._lock = asyncio.Lock()

    async def schedule(
        self,
        task_id: str,
        description: str,
        priority: SchedulePriority = SchedulePriority.NORMAL,
        token_requirement: int = 0,
        deadline: datetime | None = None,
    ) -> ScheduledTask:
        """Schedule a task for execution.

        Args:
            task_id: Unique task identifier
            description: Task description
            priority: Task priority
            token_requirement: Estimated token requirement
            deadline: Optional deadline

        Returns:
            The scheduled task
        """
        async with self._lock:
            # Build resource requirements
            requirements = {}
            if token_requirement > 0:
                requirements[ResourceType.TOKENS] = token_requirement
            requirements[ResourceType.CONCURRENT_TASKS] = 1
            requirements[ResourceType.API_CALLS] = 1

            task = ScheduledTask(
                task_id=task_id,
                description=description,
                priority=priority,
                resource_requirements=requirements,
                deadline=deadline,
            )

            # Insert by priority
            inserted = False
            for i, existing in enumerate(self._queue):
                if self._compare_priority(task, existing) > 0:
                    self._queue.insert(i, task)
                    inserted = True
                    break

            if not inserted:
                self._queue.append(task)

            self._metrics.tasks_scheduled += 1
            logger.debug(f"Scheduled task {task_id} with priority {priority.value}")

            return task

    async def get_next_task(self) -> ScheduledTask | None:
        """Get the next task to execute.

        Returns:
            Next ready task with available resources, or None
        """
        async with self._lock:
            self._reset_budgets_if_needed()

            for i, task in enumerate(self._queue):
                if not task.is_ready():
                    continue

                if self._can_execute(task):
                    # Remove from queue
                    self._queue.pop(i)

                    # Allocate resources
                    self._allocate_resources(task)

                    # Track as running
                    self._running[task.task_id] = task
                    return task

            return None

    async def complete_task(
        self,
        task_id: str,
        success: bool,
        actual_tokens_used: int = 0,
    ) -> None:
        """Mark a task as complete and release resources.

        Args:
            task_id: Task ID
            success: Whether task succeeded
            actual_tokens_used: Actual tokens used
        """
        async with self._lock:
            if task_id not in self._running:
                return

            task = self._running.pop(task_id)

            # Release resources
            self._release_resources(task, actual_tokens_used)

            self._metrics.tasks_executed += 1

            # Update wait time metric
            wait_ms = (datetime.now() - task.scheduled_at).total_seconds() * 1000
            alpha = 0.2
            self._metrics.average_wait_ms = alpha * wait_ms + (1 - alpha) * self._metrics.average_wait_ms

    async def retry_task(self, task_id: str) -> bool:
        """Retry a failed task.

        Args:
            task_id: Task ID to retry

        Returns:
            True if task was requeued, False if max retries exceeded
        """
        async with self._lock:
            if task_id not in self._running:
                return False

            task = self._running.pop(task_id)

            # Release resources
            self._release_resources(task, 0)

            if not task.can_retry():
                self._metrics.tasks_dropped += 1
                return False

            # Requeue with exponential backoff
            task.retry_count += 1
            delay_seconds = min(300, 10 * (2**task.retry_count))
            task.execute_after = datetime.now() + timedelta(seconds=delay_seconds)

            self._queue.append(task)
            return True

    def check_budget(self, resource_type: ResourceType) -> ResourceBudget:
        """Check the budget for a resource type.

        Args:
            resource_type: Type of resource

        Returns:
            The resource budget
        """
        return self._budgets.get(resource_type)

    def get_queue_status(self) -> dict[str, Any]:
        """Get current queue status."""
        by_priority: dict[str, int] = {}
        for task in self._queue:
            priority = task.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1

        return {
            "queue_length": len(self._queue),
            "running_tasks": len(self._running),
            "by_priority": by_priority,
            "budgets": {
                rt.value: {
                    "total": b.total,
                    "used": b.used,
                    "available": b.available,
                    "usage_percent": b.usage_percent,
                }
                for rt, b in self._budgets.items()
            },
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get scheduler metrics."""
        return {
            "tasks_scheduled": self._metrics.tasks_scheduled,
            "tasks_executed": self._metrics.tasks_executed,
            "tasks_delayed": self._metrics.tasks_delayed,
            "tasks_dropped": self._metrics.tasks_dropped,
            "average_wait_ms": self._metrics.average_wait_ms,
            "resource_exhaustion_count": self._metrics.resource_exhaustion_count,
        }

    def _can_execute(self, task: ScheduledTask) -> bool:
        """Check if resources are available for a task."""
        for resource_type, amount in task.resource_requirements.items():
            budget = self._budgets.get(resource_type)
            if not budget or not budget.can_allocate(amount):
                return False
        return True

    def _allocate_resources(self, task: ScheduledTask) -> None:
        """Allocate resources for a task."""
        for resource_type, amount in task.resource_requirements.items():
            budget = self._budgets.get(resource_type)
            if budget:
                budget.allocate(amount)

    def _release_resources(
        self,
        task: ScheduledTask,
        actual_tokens: int = 0,
    ) -> None:
        """Release resources after task completion."""
        for resource_type, amount in task.resource_requirements.items():
            budget = self._budgets.get(resource_type)
            if budget:
                # For tokens, use actual if provided
                if resource_type == ResourceType.TOKENS and actual_tokens > 0:
                    # Release the difference if we overallocated
                    budget.release(amount - actual_tokens)
                else:
                    budget.release(amount)

    def _compare_priority(self, task1: ScheduledTask, task2: ScheduledTask) -> int:
        """Compare two tasks by priority.

        Returns:
            Positive if task1 > task2, negative if task1 < task2, 0 if equal
        """
        priority_order = [
            SchedulePriority.BACKGROUND,
            SchedulePriority.LOW,
            SchedulePriority.NORMAL,
            SchedulePriority.HIGH,
            SchedulePriority.CRITICAL,
        ]

        idx1 = priority_order.index(task1.priority)
        idx2 = priority_order.index(task2.priority)

        if idx1 != idx2:
            return idx1 - idx2

        # Same priority - check deadline
        if task1.deadline and task2.deadline:
            if task1.deadline < task2.deadline:
                return 1
            if task1.deadline > task2.deadline:
                return -1

        # Same priority and no deadline difference - FIFO
        if task1.scheduled_at < task2.scheduled_at:
            return 1
        return -1

    def _reset_budgets_if_needed(self) -> None:
        """Reset budgets that are due for reset."""
        now = datetime.now()

        for budget in self._budgets.values():
            if budget.should_reset():
                budget.used = 0
                budget.reserved = 0
                budget.reset_at = now + timedelta(minutes=1)


# Global scheduler instance
_scheduler: ResourceScheduler | None = None


def get_resource_scheduler(
    token_budget: int = 100000,
    api_call_limit: int = 60,
    max_concurrent: int = 5,
) -> ResourceScheduler:
    """Get or create the global resource scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ResourceScheduler(
            token_budget=token_budget,
            api_call_limit=api_call_limit,
            max_concurrent=max_concurrent,
        )
    return _scheduler


def reset_resource_scheduler() -> None:
    """Reset the global resource scheduler."""
    global _scheduler
    _scheduler = None
