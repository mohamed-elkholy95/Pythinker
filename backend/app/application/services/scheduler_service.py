"""
Scheduler Service
Manages scheduled tasks using Redis persistence and APScheduler execution.
"""

import logging

from app.domain.models.scheduled_task import (
    ScheduledTask,
    ScheduledTaskStatus,
)
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Service for managing scheduled tasks.

    Constraints:
    - One active scheduled task per user
    - Minimum 5-minute interval for recurring tasks
    - Uses Redis for persistence

    Note: Full APScheduler integration requires additional setup.
    This implementation provides the core task management logic.
    """

    # Redis key prefix for scheduled tasks
    REDIS_PREFIX = "pythinker:scheduled_task:"
    USER_TASK_PREFIX = "pythinker:user_tasks:"

    def __init__(self, redis_client=None):
        """
        Initialize scheduler service.

        Args:
            redis_client: Redis client for persistence (optional)
        """
        self._redis = redis_client
        self._in_memory_tasks: dict[str, ScheduledTask] = {}
        self._user_active_tasks: dict[str, str] = {}  # user_id -> task_id
        logger.info("SchedulerService initialized")

    async def schedule_task(self, task: ScheduledTask) -> ToolResult:
        """
        Schedule a new task.

        Enforces one active task per user constraint.

        Args:
            task: The scheduled task to create

        Returns:
            ToolResult with success status and task info
        """
        # Validate interval for recurring tasks
        if not task.validate_interval():
            return ToolResult(
                success=False,
                message=f"Recurring tasks require minimum {task.MIN_INTERVAL_SECONDS // 60} minute interval",
            )

        # Check for existing active task
        existing_task_id = self._user_active_tasks.get(task.user_id)
        if existing_task_id:
            existing_task = self._in_memory_tasks.get(existing_task_id)
            if existing_task and existing_task.is_active():
                return ToolResult(
                    success=False,
                    message=f"User already has an active scheduled task (ID: {existing_task_id}). Cancel it first to create a new one.",
                    data={"existing_task_id": existing_task_id},
                )

        # Store task
        self._in_memory_tasks[task.id] = task
        self._user_active_tasks[task.user_id] = task.id

        # Persist to Redis if available
        if self._redis:
            try:
                await self._persist_task(task)
            except Exception as e:
                logger.warning(f"Failed to persist task to Redis: {e}")

        logger.info(f"Scheduled task {task.id} for user {task.user_id}")

        return ToolResult(
            success=True,
            message=f"Task scheduled successfully for {task.scheduled_at.isoformat()}",
            data={
                "task_id": task.id,
                "task": task.task_description,
                "scheduled_at": task.scheduled_at.isoformat(),
                "schedule_type": task.schedule_type.value,
                "interval_minutes": task.interval_seconds // 60 if task.interval_seconds else None,
            },
        )

    async def cancel_task(self, task_id: str) -> ToolResult:
        """
        Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            ToolResult with cancellation status
        """
        task = self._in_memory_tasks.get(task_id)
        if not task:
            return ToolResult(success=False, message=f"Task {task_id} not found")

        if not task.is_active():
            return ToolResult(success=False, message=f"Task {task_id} is not active (status: {task.status.value})")

        task.cancel()

        # Update user's active task
        if self._user_active_tasks.get(task.user_id) == task_id:
            del self._user_active_tasks[task.user_id]

        # Persist to Redis if available
        if self._redis:
            try:
                await self._persist_task(task)
            except Exception as e:
                logger.warning(f"Failed to persist task cancellation to Redis: {e}")

        logger.info(f"Cancelled task {task_id}")

        return ToolResult(success=True, message=f"Task {task_id} cancelled successfully")

    async def list_user_tasks(self, user_id: str) -> ToolResult:
        """
        List all tasks for a user.

        Args:
            user_id: ID of the user

        Returns:
            ToolResult with list of tasks
        """
        user_tasks = [task for task in self._in_memory_tasks.values() if task.user_id == user_id]

        # Sort by scheduled_at (most recent first)
        user_tasks.sort(key=lambda t: t.scheduled_at, reverse=True)

        tasks_data = [
            {
                "id": task.id,
                "task": task.task_description,
                "scheduled_at": task.scheduled_at.isoformat(),
                "status": task.status.value,
                "schedule_type": task.schedule_type.value,
                "execution_count": task.execution_count,
                "next_execution_at": task.next_execution_at.isoformat() if task.next_execution_at else None,
            }
            for task in user_tasks[:10]  # Limit to 10 most recent
        ]

        return ToolResult(success=True, message=f"Found {len(tasks_data)} scheduled tasks", data={"tasks": tasks_data})

    async def get_pending_tasks(self) -> list[ScheduledTask]:
        """
        Get all tasks ready for execution.

        Returns:
            List of tasks that can be executed now
        """
        return [task for task in self._in_memory_tasks.values() if task.can_execute()]

    async def mark_task_executed(self, task_id: str) -> None:
        """
        Mark a task as executed and update its state.

        Args:
            task_id: ID of the executed task
        """
        task = self._in_memory_tasks.get(task_id)
        if task:
            task.mark_executed()

            # Remove from active tasks if completed
            if task.status == ScheduledTaskStatus.COMPLETED and self._user_active_tasks.get(task.user_id) == task_id:
                del self._user_active_tasks[task.user_id]

            # Persist to Redis if available
            if self._redis:
                try:
                    await self._persist_task(task)
                except Exception as e:
                    logger.warning(f"Failed to persist task execution to Redis: {e}")

    async def mark_task_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_id: ID of the failed task
            error: Error message
        """
        task = self._in_memory_tasks.get(task_id)
        if task:
            task.mark_failed(error)

            # Remove from active tasks
            if self._user_active_tasks.get(task.user_id) == task_id:
                del self._user_active_tasks[task.user_id]

            # Persist to Redis if available
            if self._redis:
                try:
                    await self._persist_task(task)
                except Exception as e:
                    logger.warning(f"Failed to persist task failure to Redis: {e}")

    async def _persist_task(self, task: ScheduledTask) -> None:
        """
        Persist task to Redis.

        Args:
            task: Task to persist
        """
        if not self._redis:
            return

        key = f"{self.REDIS_PREFIX}{task.id}"
        await self._redis.set(key, task.model_dump_json())

        # Update user's task index
        user_key = f"{self.USER_TASK_PREFIX}{task.user_id}"
        if task.is_active():
            await self._redis.set(user_key, task.id)
        else:
            await self._redis.delete(user_key)

    async def load_from_redis(self) -> None:
        """
        Load tasks from Redis on startup.
        """
        if not self._redis:
            logger.warning("No Redis client available, tasks will not persist")
            return

        try:
            # Scan for all task keys
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=f"{self.REDIS_PREFIX}*", count=100)
                for key in keys:
                    data = await self._redis.get(key)
                    if data:
                        task = ScheduledTask.model_validate_json(data)
                        self._in_memory_tasks[task.id] = task
                        if task.is_active():
                            self._user_active_tasks[task.user_id] = task.id

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._in_memory_tasks)} scheduled tasks from Redis")
        except Exception as e:
            logger.error(f"Failed to load tasks from Redis: {e}")
