"""TaskManagementTool — agent-accessible task CRUD.

Lets the agent create, update, list, retrieve, and stop tracked tasks.
Large outputs are offloaded to ToolResultStore to keep task records compact.

This is distinct from TaskStateManager (which tracks session-level todo
recitation) — TaskManagementTool is an agent-visible tool for managing
discrete units of work.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.tool_result_store import ToolResultStore
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)


# ── Status enum ──────────────────────────────────────────────────────────────


class ManagedTaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


_TERMINAL = {ManagedTaskStatus.COMPLETED, ManagedTaskStatus.FAILED, ManagedTaskStatus.STOPPED}


# ── Task record ──────────────────────────────────────────────────────────────


@dataclass
class ManagedTask:
    """A tracked unit of work."""

    task_id: str
    description: str
    status: ManagedTaskStatus = ManagedTaskStatus.PENDING
    output: str = ""
    output_ref: str | None = None  # ToolResultStore ref when output offloaded
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def summary(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status,
            "has_output": bool(self.output or self.output_ref),
            "output_ref": self.output_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── Tool ─────────────────────────────────────────────────────────────────────


class TaskManagementTool(BaseTool):
    """Agent-accessible task CRUD with ToolResultStore integration for large outputs.

    Usage:
        tool = TaskManagementTool()
        # Agent creates a task
        result = await tool.task_create(description="Research topic X")
        task_id = result.data["task_id"]
        # Agent updates it
        await tool.task_update(task_id=task_id, status="in_progress")
        # When done
        await tool.task_update(task_id=task_id, status="completed", output="findings...")
    """

    name: str = "tasks"

    def __init__(
        self,
        result_store: ToolResultStore | None = None,
    ) -> None:
        super().__init__(
            defaults=ToolDefaults(
                category="system",
                user_facing_name="Task Manager",
            )
        )
        self._store: dict[str, ManagedTask] = {}
        self._result_store = result_store or ToolResultStore()

    def _make_id(self) -> str:
        return f"tsk-{uuid.uuid4().hex[:8]}"

    def _get_task(self, task_id: str) -> ManagedTask | None:
        return self._store.get(task_id)

    def _offload_output(self, task: ManagedTask, output: str) -> str:
        """Store output in ToolResultStore if large; return preview or full string."""
        if not self._result_store.should_offload(output):
            task.output = output
            task.output_ref = None
            return output

        result_id, preview = self._result_store.store(output, "task_output", result_id=task.task_id)
        task.output = preview
        task.output_ref = result_id
        return preview

    # ── Tools ──────────────────────────────────────────────────────────────

    @tool(
        name="task_create",
        description=(
            "Create a new tracked task. Returns a task_id. Use task_update to change status and record output."
        ),
        parameters={
            "description": {"type": "string", "description": "What this task does."},
            "metadata": {
                "type": "object",
                "description": "Optional key-value metadata (tags, priority, etc.).",
            },
        },
        required=["description"],
        is_concurrency_safe=True,
    )
    async def task_create(
        self,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Create a new tracked task."""
        if not description or not description.strip():
            return ToolResult(success=False, message="'description' must not be empty.")

        task_id = self._make_id()
        task = ManagedTask(
            task_id=task_id,
            description=description.strip(),
            metadata=metadata or {},
        )
        self._store[task_id] = task
        logger.debug("task_create: %s %r", task_id, description[:60])

        return ToolResult(
            success=True,
            message=f"Task created: {task_id}",
            data=task.summary(),
        )

    @tool(
        name="task_update",
        description=(
            "Update a task's status and/or output. Valid statuses: pending, in_progress, completed, failed, stopped."
        ),
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by task_create."},
            "status": {
                "type": "string",
                "description": "New status: pending | in_progress | completed | failed | stopped.",
            },
            "output": {
                "type": "string",
                "description": "Task output or result text (stored, large outputs offloaded).",
            },
        },
        required=["task_id"],
        is_destructive=True,
    )
    async def task_update(
        self,
        task_id: str,
        status: str | None = None,
        output: str | None = None,
    ) -> ToolResult:
        """Update status and/or output for an existing task."""
        task = self._get_task(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        if status is not None:
            try:
                new_status = ManagedTaskStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in ManagedTaskStatus)
                return ToolResult(success=False, message=f"Invalid status '{status}'. Valid: {valid}")
            task.status = new_status

        if output is not None:
            self._offload_output(task, output)

        task.touch()
        return ToolResult(
            success=True,
            message=f"Task {task_id} updated.",
            data=task.summary(),
        )

    @tool(
        name="task_list",
        description="List tracked tasks, optionally filtered by status.",
        parameters={
            "status": {
                "type": "string",
                "description": "Filter by status: pending | in_progress | completed | failed | stopped. Omit for all.",
            },
        },
        required=[],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def task_list(self, status: str | None = None) -> ToolResult:
        """Return a list of task summaries, optionally filtered by status."""
        tasks = list(self._store.values())

        if status is not None:
            try:
                filter_status = ManagedTaskStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in ManagedTaskStatus)
                return ToolResult(success=False, message=f"Invalid status '{status}'. Valid: {valid}")
            tasks = [t for t in tasks if t.status == filter_status]

        summaries = [t.summary() for t in tasks]
        return ToolResult(
            success=True,
            message=f"{len(summaries)} task(s).",
            data={"tasks": summaries, "total": len(summaries)},
        )

    @tool(
        name="task_get",
        description="Get details of a specific task including its current output preview.",
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by task_create."},
        },
        required=["task_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def task_get(self, task_id: str) -> ToolResult:
        """Return full details for a single task."""
        task = self._get_task(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        data = task.summary()
        data["output_preview"] = task.output
        return ToolResult(
            success=True,
            message=f"task_id={task_id} status={task.status}",
            data=data,
        )

    @tool(
        name="task_output",
        description=(
            "Retrieve the full output of a task. If the output was offloaded (large), fetches it from the result store."
        ),
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by task_create."},
        },
        required=["task_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def task_output(self, task_id: str) -> ToolResult:
        """Return the full output for a task, fetching from store if offloaded."""
        task = self._get_task(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        # If output was offloaded, retrieve full content
        if task.output_ref is not None:
            full = self._result_store.retrieve(task.output_ref)
            if full is not None:
                return ToolResult(
                    success=True,
                    message=full,
                    data={"task_id": task_id, "output": full, "offloaded": True},
                )
            # Fallback to stored preview if store miss
            return ToolResult(
                success=True,
                message=task.output or "(no output)",
                data={"task_id": task_id, "output": task.output, "offloaded": True, "store_miss": True},
            )

        return ToolResult(
            success=True,
            message=task.output or "(no output)",
            data={"task_id": task_id, "output": task.output, "offloaded": False},
        )

    @tool(
        name="task_stop",
        description="Stop a running or pending task. Terminal tasks (completed/failed/stopped) are unaffected.",
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by task_create."},
        },
        required=["task_id"],
        is_destructive=True,
    )
    async def task_stop(self, task_id: str) -> ToolResult:
        """Mark a task as stopped (idempotent for terminal tasks)."""
        task = self._get_task(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        if task.status in _TERMINAL:
            return ToolResult(
                success=True,
                message=f"Task {task_id} already in terminal state: {task.status}",
                data=task.summary(),
            )

        task.status = ManagedTaskStatus.STOPPED
        task.touch()
        return ToolResult(
            success=True,
            message=f"Task {task_id} stopped.",
            data=task.summary(),
        )
