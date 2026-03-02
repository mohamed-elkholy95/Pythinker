"""
SpawnTool — allows the agent to spawn background subtasks with concurrency limits.

The tool delegates to a SubagentManagerProtocol, keeping the domain layer
free of infrastructure concerns (the concrete nanobot SubagentManager is
injected at composition-root time).
"""

import logging
from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol — domain-level contract for subagent management
# ---------------------------------------------------------------------------


class SubagentManagerProtocol(Protocol):
    """Minimal interface that the infrastructure layer must satisfy."""

    async def spawn(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """Spawn a background task and return a human-readable confirmation string."""
        ...

    def get_running_count(self) -> int:
        """Return the number of currently running background tasks."""
        ...


# ---------------------------------------------------------------------------
# SpawnTool
# ---------------------------------------------------------------------------


class SpawnTool(BaseTool):
    """Tool that lets the agent spawn independent background subtasks.

    Each subtask runs to completion and announces its result back to the
    main conversation.  A configurable concurrency cap prevents runaway
    spawning.
    """

    name: str = "spawn"

    def __init__(
        self,
        subagent_manager: SubagentManagerProtocol,
        max_concurrent: int = 3,
    ) -> None:
        """Initialise the spawn tool.

        Args:
            subagent_manager: Backend that actually runs the subtask.
            max_concurrent: Maximum number of background tasks allowed at once.
        """
        super().__init__()
        self._manager = subagent_manager
        self._max_concurrent = max_concurrent

    @tool(
        name="spawn_background_task",
        description=(
            "Spawn a background task that runs independently and reports "
            "results when complete. Use this when the user's request can "
            "benefit from parallel work (e.g. research one topic while "
            "working on another)."
        ),
        parameters={
            "task": {
                "type": "string",
                "description": "Task description for the background agent",
            },
            "label": {
                "type": "string",
                "description": "Optional short label for tracking the task",
            },
        },
        required=["task"],
    )
    async def spawn_background_task(
        self,
        task: str,
        label: str | None = None,
    ) -> ToolResult:
        """Spawn a background subtask via the subagent manager.

        Guards:
            1. ``task`` must be a non-empty string.
            2. Running task count must be below ``max_concurrent``.

        Returns:
            ToolResult with the confirmation / task-id string on success,
            or a descriptive error on failure.
        """
        # --- Guard: empty / whitespace-only task description ----------------
        if not task or not task.strip():
            return ToolResult.error(
                message="Task description cannot be empty.",
            )

        # --- Guard: concurrency cap -----------------------------------------
        running = self._manager.get_running_count()
        if running >= self._max_concurrent:
            return ToolResult.error(
                message=(
                    f"Concurrency limit reached ({running}/{self._max_concurrent} "
                    f"background tasks running). Wait for a task to finish before "
                    f"spawning another."
                ),
            )

        # --- Spawn -----------------------------------------------------------
        try:
            confirmation = await self._manager.spawn(
                task=task.strip(),
                label=label.strip() if label else None,
            )
            logger.info(
                "Spawned background task (running=%d/%d): %s",
                running + 1,
                self._max_concurrent,
                label or task[:40],
            )
            return ToolResult.ok(
                message=confirmation,
                data={"running_count": running + 1, "max_concurrent": self._max_concurrent},
            )
        except Exception as exc:
            logger.exception("Failed to spawn background task")
            return ToolResult.error(
                message=f"Failed to spawn background task: {exc}",
            )
