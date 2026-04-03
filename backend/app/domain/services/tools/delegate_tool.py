"""DelegateTool — unified delegation with typed roles and concurrency caps.

Routes subtasks to the appropriate execution backend based on ``DelegateRole``:
- RESEARCHER → research flow factory (streaming events)
- All others → subagent manager (fire-and-forget spawn)

All infrastructure dependencies are injected at construction time so the
domain layer stays free of concrete I/O concerns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.domain.models.delegation import (
    DelegateRequest,
    DelegateResult,
    DelegateRole,
    DelegateStatus,
)
from app.domain.utils.task_ids import generate_agent_task_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DelegateTool
# ---------------------------------------------------------------------------


class DelegateTool:
    """Unified tool that delegates subtasks to typed execution backends.

    Args:
        subagent_manager: Backend that spawns background subtasks.  Must
            satisfy the duck-typed interface::

                async def spawn(task, label) -> str
                async def get_running_count() -> int

        research_flow_factory: Optional callable that, given a task string,
            returns an async iterable of streaming events.  Required only
            when RESEARCHER tasks are expected.
        max_concurrent: Maximum number of concurrently running subtasks.
            Requests that would exceed this cap are immediately rejected.
        event_sink: Optional callable ``(event_name: str, payload: dict) -> None``
            for emitting lifecycle events to an external observer (e.g. SSE bus).
    """

    def __init__(
        self,
        subagent_manager: Any,
        research_flow_factory: Callable[..., Any] | None = None,
        max_concurrent: int = 3,
        event_sink: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._manager = subagent_manager
        self._research_flow_factory = research_flow_factory
        self._max_concurrent = max_concurrent
        self._event_sink = event_sink

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(self, request: DelegateRequest) -> DelegateResult:
        """Execute a delegation request.

        Guards (evaluated in order):
        1. Empty task description → REJECTED immediately.
        2. Running subtask count >= cap → REJECTED immediately.

        Then routes to ``_execute_research`` (RESEARCHER role with a factory)
        or ``_execute_subagent`` (all other roles).

        Args:
            request: Validated delegation request.

        Returns:
            DelegateResult describing the outcome.
        """
        # --- Guard: empty task --------------------------------------------------
        if not request.task or not request.task.strip():
            return DelegateResult(
                status=DelegateStatus.REJECTED,
                error="Empty task description",
            )

        # --- Guard: concurrency cap ---------------------------------------------
        running = await self._manager.get_running_count()
        if running >= self._max_concurrent:
            return DelegateResult(
                status=DelegateStatus.REJECTED,
                error=(
                    f"Concurrency cap reached ({running}/{self._max_concurrent} "
                    f"subtasks running). Wait for a subtask to finish before "
                    f"delegating another."
                ),
            )

        # --- Generate task id ---------------------------------------------------
        task_id = generate_agent_task_id()

        # --- Emit started event -------------------------------------------------
        if self._event_sink is not None:
            try:
                self._event_sink(
                    "delegate_started",
                    {
                        "task_id": task_id,
                        "role": request.role.value,
                        "label": request.label,
                    },
                )
            except Exception:
                logger.exception("event_sink raised during delegate_started emission")

        # --- Route to appropriate backend ---------------------------------------
        if request.role is DelegateRole.RESEARCHER and self._research_flow_factory is not None:
            return await self._execute_research(task_id, request)

        return await self._execute_subagent(task_id, request)

    # ------------------------------------------------------------------
    # Private routing methods
    # ------------------------------------------------------------------

    async def _execute_research(
        self,
        task_id: str,
        request: DelegateRequest,
    ) -> DelegateResult:
        """Run the research flow, collecting streamed events into a result.

        Args:
            task_id: Pre-generated short task identifier.
            request: Delegation request (role == RESEARCHER).

        Returns:
            COMPLETED with concatenated result text, or FAILED with error.
        """
        if self._research_flow_factory is None:
            # Should not occur — caller guards this.
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.FAILED,
                error="No research flow factory configured",
            )

        try:
            flow = self._research_flow_factory(request.task)
            collected: list[str] = []
            async for event in flow:
                # Events may be strings or objects with a ``text`` attribute.
                if isinstance(event, str):
                    collected.append(event)
                elif hasattr(event, "text"):
                    collected.append(event.text)

            logger.info(
                "Research delegate completed (task_id=%s, chunks=%d)",
                task_id,
                len(collected),
            )
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.COMPLETED,
                result="\n".join(collected) if collected else None,
            )

        except Exception as exc:
            logger.exception("Research delegate failed (task_id=%s)", task_id)
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.FAILED,
                error=str(exc),
            )

    async def _execute_subagent(
        self,
        task_id: str,
        request: DelegateRequest,
    ) -> DelegateResult:
        """Spawn a background subagent for non-research roles.

        Args:
            task_id: Pre-generated short task identifier.
            request: Delegation request.

        Returns:
            STARTED on successful spawn, or FAILED with error message.
        """
        try:
            await self._manager.spawn(
                task=request.task.strip(),
                label=request.label.strip() if request.label else None,
            )
            logger.info(
                "Subagent delegate started (task_id=%s, role=%s)",
                task_id,
                request.role.value,
            )
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.STARTED,
            )

        except Exception as exc:
            logger.exception("Subagent delegate failed (task_id=%s)", task_id)
            return DelegateResult(
                task_id=task_id,
                status=DelegateStatus.FAILED,
                error=str(exc),
            )
