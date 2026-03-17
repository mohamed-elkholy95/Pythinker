"""CronTool — agent tool for scheduling, listing, and cancelling recurring tasks.

Delegates to a CronServiceProtocol (implemented by CronBridge in infrastructure).
The domain layer never imports infrastructure; the bridge is injected at composition time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class CronServiceProtocol(Protocol):
    """Abstraction over any cron scheduling backend.

    The CronBridge (infrastructure layer) implements this protocol to wrap
    the vendored CronService without the domain depending on infrastructure.
    """

    async def add_job(
        self,
        user_id: str,
        description: str,
        cron_expr: str,
        timezone: str,
    ) -> str:
        """Schedule a recurring job.

        Args:
            user_id: Owner of the job.
            description: Human-readable task description (doubles as the job name
                and the message payload that will be sent when the job fires).
            cron_expr: Standard 5-field cron expression, e.g. ``'0 9 * * *'``.
            timezone: IANA timezone string, e.g. ``'America/New_York'``.

        Returns:
            The newly created job ID.
        """
        ...

    async def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        """List all active jobs for a user.

        Args:
            user_id: Owner whose jobs to list.

        Returns:
            List of dicts with at minimum ``id``, ``name``, ``cron_expr``,
            ``timezone``, ``next_run``, ``enabled``.
        """
        ...

    async def remove_job(self, job_id: str) -> bool:
        """Cancel / remove a job by ID.

        Args:
            job_id: The job to remove.

        Returns:
            ``True`` if the job existed and was removed, ``False`` otherwise.
        """
        ...


class CronTool(BaseTool):
    """Agent tool for scheduling, listing, and cancelling recurring tasks.

    Actions:
        * ``schedule`` — create a new recurring task from a cron expression.
        * ``list`` — show all active tasks for the current user.
        * ``cancel`` — remove a task by its job ID.
    """

    name: str = "schedule_task"

    def __init__(
        self,
        cron_service: CronServiceProtocol,
        user_id: str,
    ) -> None:
        super().__init__()
        self._cron_service = cron_service
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Tool definition
    # ------------------------------------------------------------------

    @tool(
        name="schedule_task",
        description=(
            "Schedule, list, or cancel recurring tasks.\n\n"
            "Actions:\n"
            "  - 'schedule': Create a recurring task. Requires 'description' and 'cron_expr'. "
            "Optionally set 'timezone' (default UTC).\n"
            "  - 'list': List all active scheduled tasks for the current user.\n"
            "  - 'cancel': Cancel a scheduled task. Requires 'job_id'."
        ),
        parameters={
            "action": {
                "type": "string",
                "enum": ["schedule", "list", "cancel"],
                "description": "The action to perform.",
            },
            "description": {
                "type": "string",
                "description": "Task description (required for 'schedule').",
            },
            "cron_expr": {
                "type": "string",
                "description": "Cron expression, e.g. '0 9 * * *' (required for 'schedule').",
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone, e.g. 'America/New_York' (default: 'UTC').",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID to cancel (required for 'cancel').",
            },
        },
        required=["action"],
    )
    async def execute(
        self,
        action: str,
        description: str | None = None,
        cron_expr: str | None = None,
        timezone: str | None = None,
        job_id: str | None = None,
    ) -> ToolResult:
        """Dispatch to the appropriate action handler."""
        if action == "schedule":
            return await self._handle_schedule(description, cron_expr, timezone)
        if action == "list":
            return await self._handle_list()
        if action == "cancel":
            return await self._handle_cancel(job_id)

        return ToolResult.error(
            message=f"Unknown action '{action}'. Must be one of: schedule, list, cancel.",
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_schedule(
        self,
        description: str | None,
        cron_expr: str | None,
        tz: str | None,
    ) -> ToolResult:
        if not description:
            return ToolResult.error(message="'description' is required for the 'schedule' action.")
        if not cron_expr:
            return ToolResult.error(message="'cron_expr' is required for the 'schedule' action.")

        effective_tz = tz or "UTC"

        try:
            job_id = await self._cron_service.add_job(
                user_id=self._user_id,
                description=description,
                cron_expr=cron_expr,
                timezone=effective_tz,
            )
        except Exception as exc:
            logger.warning("CronTool: failed to schedule job: %s", exc)
            return ToolResult.error(message=f"Failed to schedule task: {exc}")

        return ToolResult.ok(
            message=(
                f"Scheduled task '{description}' with cron '{cron_expr}' (timezone: {effective_tz}). Job ID: {job_id}"
            ),
            data={
                "job_id": job_id,
                "description": description,
                "cron_expr": cron_expr,
                "timezone": effective_tz,
            },
        )

    async def _handle_list(self) -> ToolResult:
        try:
            jobs = await self._cron_service.list_jobs(user_id=self._user_id)
        except Exception as exc:
            logger.warning("CronTool: failed to list jobs: %s", exc)
            return ToolResult.error(message=f"Failed to list tasks: {exc}")

        if not jobs:
            return ToolResult.ok(message="No scheduled tasks found.", data={"jobs": []})

        lines: list[str] = []
        for job in jobs:
            next_run = job.get("next_run", "N/A")
            if isinstance(next_run, datetime):
                next_run = next_run.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
            lines.append(
                f"- [{job.get('id', '?')}] {job.get('name', 'Untitled')} "
                f"| cron: {job.get('cron_expr', '?')} "
                f"| tz: {job.get('timezone', 'UTC')} "
                f"| next: {next_run} "
                f"| enabled: {job.get('enabled', True)}"
            )

        return ToolResult.ok(
            message=f"Scheduled tasks ({len(jobs)}):\n" + "\n".join(lines),
            data={"jobs": jobs},
        )

    async def _handle_cancel(self, job_id: str | None) -> ToolResult:
        if not job_id:
            return ToolResult.error(message="'job_id' is required for the 'cancel' action.")

        try:
            removed = await self._cron_service.remove_job(job_id=job_id)
        except Exception as exc:
            logger.warning("CronTool: failed to cancel job %s: %s", job_id, exc)
            return ToolResult.error(message=f"Failed to cancel task: {exc}")

        if removed:
            return ToolResult.ok(
                message=f"Task {job_id} cancelled successfully.",
                data={"job_id": job_id, "cancelled": True},
            )

        return ToolResult.error(
            message=f"Task {job_id} not found.",
            data={"job_id": job_id, "cancelled": False},
        )
