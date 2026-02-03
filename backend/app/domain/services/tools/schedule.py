"""
Schedule Tool
Provides functionality to schedule tasks for deferred or recurring execution.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.domain.models.scheduled_task import (
    ScheduledTask,
    ScheduleType,
)
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class ScheduleTool(BaseTool):
    """
    Tool for scheduling agent tasks.

    Constraints:
    - One active scheduled task per user
    - Minimum interval for recurring tasks is 5 minutes
    """

    name: str = "schedule"

    # Callback for scheduling service integration
    _schedule_callback: Callable[[ScheduledTask], Awaitable[ToolResult]] | None = None
    _cancel_callback: Callable[[str], Awaitable[ToolResult]] | None = None
    _list_callback: Callable[[str], Awaitable[ToolResult]] | None = None

    def __init__(
        self,
        user_id: str,
        schedule_callback: Callable[[ScheduledTask], Awaitable[ToolResult]] | None = None,
        cancel_callback: Callable[[str], Awaitable[ToolResult]] | None = None,
        list_callback: Callable[[str], Awaitable[ToolResult]] | None = None,
    ):
        """
        Initialize schedule tool.

        Args:
            user_id: ID of the user for this tool instance
            schedule_callback: Async callback to schedule a task
            cancel_callback: Async callback to cancel a task
            list_callback: Async callback to list tasks for a user
        """
        super().__init__()
        self._user_id = user_id
        self._schedule_callback = schedule_callback
        self._cancel_callback = cancel_callback
        self._list_callback = list_callback

    @tool(
        name="agent_schedule_task",
        description="""Schedule a task for later execution or recurring execution.

Use this tool to:
- Schedule a reminder or task for a specific time
- Set up recurring tasks (minimum 5-minute interval)
- Defer complex tasks to run at a better time

Constraints:
- Only ONE active scheduled task per user at a time
- Recurring tasks must have at least 5-minute intervals
- Tasks execute in a new or specified session""",
        parameters={
            "task": {"type": "string", "description": "Description of the task to execute"},
            "scheduled_at": {
                "type": "string",
                "description": "When to execute (ISO 8601 format, e.g., '2024-01-15T14:30:00Z'). Use 'now+Xm' for relative time (e.g., 'now+30m' for 30 minutes from now)",
            },
            "recurring": {"type": "boolean", "description": "Whether this is a recurring task (default: false)"},
            "interval_minutes": {
                "type": "integer",
                "description": "Interval in minutes for recurring tasks (minimum 5 minutes)",
            },
            "max_executions": {
                "type": "integer",
                "description": "Maximum number of executions for recurring tasks (optional)",
            },
        },
        required=["task", "scheduled_at"],
    )
    async def agent_schedule_task(
        self,
        task: str,
        scheduled_at: str,
        recurring: bool = False,
        interval_minutes: int | None = None,
        max_executions: int | None = None,
    ) -> ToolResult:
        """
        Schedule a task for later or recurring execution.

        Args:
            task: Description of the task to execute
            scheduled_at: When to execute (ISO 8601 or 'now+Xm' format)
            recurring: Whether this is a recurring task
            interval_minutes: Interval for recurring tasks (minimum 5)
            max_executions: Max executions for recurring tasks

        Returns:
            ToolResult with scheduling confirmation or error
        """
        # Parse scheduled_at
        try:
            if scheduled_at.startswith("now+"):
                # Parse relative time (e.g., "now+30m")
                time_part = scheduled_at[4:]
                if time_part.endswith("m"):
                    minutes = int(time_part[:-1])
                    execute_at = datetime.now(UTC) + timedelta(minutes=minutes)
                elif time_part.endswith("h"):
                    hours = int(time_part[:-1])
                    execute_at = datetime.now(UTC) + timedelta(hours=hours)
                elif time_part.endswith("d"):
                    days = int(time_part[:-1])
                    execute_at = datetime.now(UTC) + timedelta(days=days)
                else:
                    return ToolResult(
                        success=False, message="Invalid relative time format. Use 'now+Xm', 'now+Xh', or 'now+Xd'"
                    )
            else:
                # Parse ISO 8601 format
                execute_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            return ToolResult(success=False, message=f"Invalid scheduled_at format: {e}")

        # Validate recurring task interval
        schedule_type = ScheduleType.RECURRING if recurring else ScheduleType.ONCE
        interval_seconds = None

        if recurring:
            if not interval_minutes or interval_minutes < 5:
                return ToolResult(success=False, message="Recurring tasks require an interval of at least 5 minutes")
            interval_seconds = interval_minutes * 60

        # Create scheduled task
        scheduled_task = ScheduledTask(
            user_id=self._user_id,
            task_description=task,
            schedule_type=schedule_type,
            scheduled_at=execute_at,
            interval_seconds=interval_seconds,
            max_executions=max_executions,
            next_execution_at=execute_at,
        )

        # Use callback if available, otherwise return success
        if self._schedule_callback:
            return await self._schedule_callback(scheduled_task)

        # Default response (when no scheduler service is connected)
        return ToolResult(
            success=True,
            message=f"Task scheduled for {execute_at.isoformat()}",
            data={
                "task_id": scheduled_task.id,
                "task": task,
                "scheduled_at": execute_at.isoformat(),
                "recurring": recurring,
                "interval_minutes": interval_minutes,
            },
        )

    @tool(
        name="agent_cancel_scheduled_task",
        description="""Cancel a scheduled task.

Use this to cancel a pending scheduled task.""",
        parameters={"task_id": {"type": "string", "description": "ID of the scheduled task to cancel"}},
        required=["task_id"],
    )
    async def agent_cancel_scheduled_task(
        self,
        task_id: str,
    ) -> ToolResult:
        """
        Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            ToolResult with cancellation confirmation or error
        """
        if self._cancel_callback:
            return await self._cancel_callback(task_id)

        return ToolResult(success=True, message=f"Task {task_id} cancellation requested")

    @tool(
        name="agent_list_scheduled_tasks",
        description="""List all scheduled tasks for the current user.

Shows pending, running, and recently completed tasks.""",
        parameters={},
        required=[],
    )
    async def agent_list_scheduled_tasks(self) -> ToolResult:
        """
        List all scheduled tasks for the current user.

        Returns:
            ToolResult with list of scheduled tasks
        """
        if self._list_callback:
            return await self._list_callback(self._user_id)

        return ToolResult(success=True, message="No scheduled tasks found", data={"tasks": []})
