"""CronBridge — infrastructure adapter that wraps the vendored CronService.

Satisfies ``CronServiceProtocol`` from the domain layer so the ``CronTool``
can schedule/list/cancel recurring jobs without depending on channel transport directly.

The bridge:
  1. Creates a dedicated ``CronService`` backed by a Pythinker-specific workspace.
  2. Translates the synchronous CronService API into the async protocol the domain expects.
  3. Filters jobs by ``user_id`` (stored as a prefix in the job name) since the
     CronService has no built-in per-user isolation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nanobot.cron.service import CronService as VendoredCronService
from nanobot.cron.types import CronJob, CronSchedule

logger = logging.getLogger(__name__)

# Separator between user_id and job name stored in CronJob.name
_USER_PREFIX_SEP = "::"


def _user_prefix(user_id: str) -> str:
    """Build the prefix stored in ``CronJob.name`` for per-user filtering."""
    return f"{user_id}{_USER_PREFIX_SEP}"


def _strip_user_prefix(name: str) -> str:
    """Strip the ``user_id::`` prefix from a job name, returning the human part."""
    if _USER_PREFIX_SEP in name:
        return name.split(_USER_PREFIX_SEP, 1)[1]
    return name


def _job_to_dict(job: CronJob) -> dict[str, Any]:
    """Serialize a CronJob into the dict format expected by the domain."""
    next_run: str | datetime | None = None
    if job.state.next_run_at_ms:
        next_run = datetime.fromtimestamp(
            job.state.next_run_at_ms / 1000,
            tz=UTC,
        )

    return {
        "id": job.id,
        "name": _strip_user_prefix(job.name),
        "cron_expr": job.schedule.expr or "",
        "timezone": job.schedule.tz or "UTC",
        "next_run": next_run,
        "enabled": job.enabled,
        "last_status": job.state.last_status,
        "last_error": job.state.last_error,
    }


class CronBridge:
    """Infrastructure adapter wrapping the vendored ``CronService``.

    Usage::

        bridge = CronBridge(workspace_dir="~/.pythinker/cron")
        await bridge.start()
        job_id = await bridge.add_job(user_id, "Daily report", "0 9 * * *", "UTC")
        jobs = await bridge.list_jobs(user_id)
        await bridge.remove_job(job_id)
        bridge.stop()
    """

    def __init__(self, workspace_dir: str = "~/.pythinker/cron") -> None:
        store_path = Path(workspace_dir).expanduser() / "jobs.json"
        self._service = VendoredCronService(store_path=store_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the underlying CronService (arms the timer loop)."""
        await self._service.start()
        logger.info("CronBridge: started (store=%s)", self._service.store_path)

    def stop(self) -> None:
        """Stop the underlying CronService."""
        self._service.stop()
        logger.info("CronBridge: stopped")

    # ------------------------------------------------------------------
    # CronServiceProtocol implementation
    # ------------------------------------------------------------------

    async def add_job(
        self,
        user_id: str,
        description: str,
        cron_expr: str,
        timezone: str,
    ) -> str:
        """Schedule a recurring job.

        Wraps ``CronService.add_job`` (sync) in ``asyncio.to_thread``
        to avoid blocking the event loop on file I/O.
        """
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=timezone)
        prefixed_name = f"{_user_prefix(user_id)}{description}"

        job: CronJob = await asyncio.to_thread(
            self._service.add_job,
            name=prefixed_name,
            schedule=schedule,
            message=description,
        )

        logger.info("CronBridge: added job %s for user %s", job.id, user_id)
        return job.id

    async def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        """List all active jobs for a given user.

        Filters by the ``user_id::`` prefix in the job name.
        """
        all_jobs: list[CronJob] = await asyncio.to_thread(self._service.list_jobs)
        prefix = _user_prefix(user_id)
        user_jobs = [j for j in all_jobs if j.name.startswith(prefix)]
        return [_job_to_dict(j) for j in user_jobs]

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        removed: bool = await asyncio.to_thread(self._service.remove_job, job_id)
        if removed:
            logger.info("CronBridge: removed job %s", job_id)
        return removed
