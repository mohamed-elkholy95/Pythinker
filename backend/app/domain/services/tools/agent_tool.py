"""AgentTool — unified subagent lifecycle management.

Provides five agent-accessible operations:
  - agent_run            synchronous subtask (waits for result)
  - agent_run_background fire-and-forget subtask (returns task_id)
  - agent_status         query status of a background task
  - agent_stop           cancel a background task
  - agent_output         retrieve full output of a task

Isolation modes
---------------
shared     The subagent shares the caller's sandbox / working directory.
workspace  The subagent gets its own working directory (/workspace/agent_<id>/).

Tool allowlists enforce what the subagent may call per isolation mode.
The concrete execution backend is injected via AgentRunnerProtocol so the
domain layer stays free of infrastructure concerns.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)


# ── Isolation modes ─────────────────────────────────────────────────────────


class IsolationMode(StrEnum):
    SHARED = "shared"
    WORKSPACE = "workspace"


# Tool allowlists per isolation mode
# SHARED: no restrictions — subagent may call any tool the parent has
SHARED_ALLOWED_TOOLS: frozenset[str] = frozenset()  # empty = no filter

# WORKSPACE: file + shell + search only (no browser, no spawning)
WORKSPACE_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "file_read",
        "file_write",
        "file_list",
        "file_find",
        "file_replace",
        "file_search",
        "file_delete",
        "shell_exec",
        "shell_view",
        "shell_wait",
        "shell_write_to_process",
        "shell_kill_process",
        "shell_exec_background",
        "shell_poll_background",
        "web_search",
        "web_fetch",
        "tool_search",
    }
)


def _allowed_tools_for(isolation: IsolationMode) -> frozenset[str]:
    if isolation == IsolationMode.WORKSPACE:
        return WORKSPACE_ALLOWED_TOOLS
    return SHARED_ALLOWED_TOOLS


# ── Task state ───────────────────────────────────────────────────────────────


class AgentTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentTask:
    """In-memory record for a background agent task."""

    task_id: str
    description: str
    isolation: IsolationMode
    context: str
    allowed_tools: frozenset[str]
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    output: str = ""
    error: str = ""
    _asyncio_task: Any = field(default=None, repr=False)  # asyncio.Task | None


# ── Runner protocol ──────────────────────────────────────────────────────────


class AgentRunnerProtocol(Protocol):
    """Domain-level interface for executing subtasks.

    The infrastructure layer provides a concrete implementation that
    wires up the actual agent execution pipeline.
    """

    async def run(
        self,
        task_id: str,
        description: str,
        context: str,
        allowed_tools: frozenset[str],
        workspace_path: str | None,
    ) -> str:
        """Run a task and return its output string."""
        ...


# ── AgentTool ────────────────────────────────────────────────────────────────


class AgentTool(BaseTool):
    """Unified subagent lifecycle tool.

    Inject an AgentRunnerProtocol at construction time.
    All five tool functions are safe to call from the agent loop.
    """

    name: str = "agent"

    def __init__(
        self,
        runner: AgentRunnerProtocol | None = None,
        workspace_root: str = "/workspace",
    ) -> None:
        super().__init__(
            defaults=ToolDefaults(
                category="agent",
                user_facing_name="Agent",
            )
        )
        self._runner = runner
        self._workspace_root = workspace_root
        self._tasks: dict[str, AgentTask] = {}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_task_id(self) -> str:
        return f"agt-{uuid.uuid4().hex[:8]}"

    def _workspace_path(self, task_id: str, isolation: IsolationMode) -> str | None:
        if isolation == IsolationMode.WORKSPACE:
            return f"{self._workspace_root}/agent_{task_id}"
        return None

    async def _run_task(self, task: AgentTask) -> None:
        """Coroutine that drives a background AgentTask to completion."""
        task.status = AgentTaskStatus.RUNNING
        try:
            if self._runner is None:
                raise RuntimeError("No AgentRunnerProtocol injected into AgentTool.")
            output = await self._runner.run(
                task_id=task.task_id,
                description=task.description,
                context=task.context,
                allowed_tools=task.allowed_tools,
                workspace_path=self._workspace_path(task.task_id, task.isolation),
            )
            task.output = output
            task.status = AgentTaskStatus.COMPLETED
        except asyncio.CancelledError:
            task.status = AgentTaskStatus.CANCELLED
            raise
        except Exception as exc:
            task.error = str(exc)
            task.status = AgentTaskStatus.FAILED
            logger.exception("AgentTask %s failed", task.task_id)

    # ── Tools ─────────────────────────────────────────────────────────────────

    @tool(
        name="agent_run",
        description=(
            "Run a subtask synchronously and wait for the result. "
            "Use for short subtasks (< 2 minutes). "
            "For long tasks use agent_run_background instead."
        ),
        parameters={
            "task": {"type": "string", "description": "Task description for the subagent."},
            "context": {"type": "string", "description": "Optional context or data to pass to the subagent."},
            "isolation": {
                "type": "string",
                "description": "Isolation mode: 'shared' (default) or 'workspace' (own directory, restricted tools).",
            },
        },
        required=["task"],
    )
    async def agent_run(
        self,
        task: str,
        context: str = "",
        isolation: str = "shared",
    ) -> ToolResult:
        """Run a subtask and wait for its result."""
        if not task or not task.strip():
            return ToolResult(success=False, message="'task' must not be empty.")

        if self._runner is None:
            return ToolResult(success=False, message="AgentTool has no runner configured.")

        try:
            iso = IsolationMode(isolation)
        except ValueError:
            iso = IsolationMode.SHARED

        task_id = self._make_task_id()
        agent_task = AgentTask(
            task_id=task_id,
            description=task.strip(),
            isolation=iso,
            context=context,
            allowed_tools=_allowed_tools_for(iso),
        )
        self._tasks[task_id] = agent_task

        try:
            await self._run_task(agent_task)
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Subtask failed: {exc}",
                data={"task_id": task_id, "status": agent_task.status},
            )

        if agent_task.status == AgentTaskStatus.COMPLETED:
            return ToolResult(
                success=True,
                message=agent_task.output,
                data={"task_id": task_id, "status": agent_task.status},
            )
        return ToolResult(
            success=False,
            message=agent_task.error or "Subtask did not complete successfully.",
            data={"task_id": task_id, "status": agent_task.status},
        )

    @tool(
        name="agent_run_background",
        description=(
            "Start a subtask in the background and return a task_id immediately. "
            "Use agent_status to check progress and agent_output to retrieve results."
        ),
        parameters={
            "task": {"type": "string", "description": "Task description for the subagent."},
            "context": {"type": "string", "description": "Optional context or data to pass to the subagent."},
            "isolation": {
                "type": "string",
                "description": "Isolation mode: 'shared' (default) or 'workspace'.",
            },
        },
        required=["task"],
        is_destructive=True,
    )
    async def agent_run_background(
        self,
        task: str,
        context: str = "",
        isolation: str = "shared",
    ) -> ToolResult:
        """Fire-and-forget: start a subtask and return its task_id."""
        if not task or not task.strip():
            return ToolResult(success=False, message="'task' must not be empty.")

        if self._runner is None:
            return ToolResult(success=False, message="AgentTool has no runner configured.")

        try:
            iso = IsolationMode(isolation)
        except ValueError:
            iso = IsolationMode.SHARED

        task_id = self._make_task_id()
        agent_task = AgentTask(
            task_id=task_id,
            description=task.strip(),
            isolation=iso,
            context=context,
            allowed_tools=_allowed_tools_for(iso),
        )
        self._tasks[task_id] = agent_task

        asyncio_task = asyncio.create_task(self._run_task(agent_task))
        agent_task._asyncio_task = asyncio_task

        logger.info("Started background agent task %s: %s", task_id, task[:60])
        return ToolResult(
            success=True,
            message=f"Background task started. task_id={task_id}",
            data={"task_id": task_id, "status": AgentTaskStatus.PENDING},
        )

    @tool(
        name="agent_status",
        description="Check the status of a background agent task.",
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by agent_run_background."},
        },
        required=["task_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def agent_status(self, task_id: str) -> ToolResult:
        """Return the current status of a background task."""
        task = self._tasks.get(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        return ToolResult(
            success=True,
            message=f"task_id={task_id} status={task.status}",
            data={
                "task_id": task_id,
                "status": task.status,
                "has_output": bool(task.output),
                "error": task.error or None,
            },
        )

    @tool(
        name="agent_stop",
        description="Cancel a running background agent task.",
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by agent_run_background."},
        },
        required=["task_id"],
        is_destructive=True,
    )
    async def agent_stop(self, task_id: str) -> ToolResult:
        """Cancel a background task."""
        task = self._tasks.get(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        if task.status in {AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED}:
            return ToolResult(
                success=True,
                message=f"Task {task_id} already in terminal state: {task.status}",
                data={"task_id": task_id, "status": task.status},
            )

        asyncio_task = task._asyncio_task
        if asyncio_task is not None and not asyncio_task.done():
            asyncio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio_task

        task.status = AgentTaskStatus.CANCELLED
        return ToolResult(
            success=True,
            message=f"Task {task_id} cancelled.",
            data={"task_id": task_id, "status": AgentTaskStatus.CANCELLED},
        )

    @tool(
        name="agent_output",
        description="Retrieve the full output of a completed background agent task.",
        parameters={
            "task_id": {"type": "string", "description": "task_id returned by agent_run_background."},
        },
        required=["task_id"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def agent_output(self, task_id: str) -> ToolResult:
        """Return the output (or error) of a task."""
        task = self._tasks.get(task_id)
        if task is None:
            return ToolResult(success=False, message=f"Unknown task_id '{task_id}'.")

        if task.status == AgentTaskStatus.RUNNING:
            return ToolResult(
                success=True,
                message=f"Task {task_id} is still running. Use agent_status to check progress.",
                data={"task_id": task_id, "status": task.status, "output": None},
            )

        if task.status == AgentTaskStatus.FAILED:
            return ToolResult(
                success=False,
                message=f"Task {task_id} failed: {task.error}",
                data={"task_id": task_id, "status": task.status, "output": None},
            )

        return ToolResult(
            success=True,
            message=task.output or f"Task {task_id} completed with no output.",
            data={"task_id": task_id, "status": task.status, "output": task.output},
        )
