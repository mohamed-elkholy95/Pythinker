"""CoordinatorFlow — parallel subagent task coordination.

Decomposes a top-level task into subtasks, dispatches them to background
subagents via AgentTool, polls for completion, and synthesizes results.

Architecture
------------
- CoordinatorFlow is a pure domain service: no infrastructure imports.
- AgentTool is injected at construction time (AgentRunnerProtocol inside it
  handles actual execution).
- CommunicationProtocol is optional; when provided, broadcast notifications
  are sent at key lifecycle points (start, worker completion, finish).
- Synthesis is left as a pluggable hook so callers can inject an LLM-backed
  synthesizer without coupling this module to any LLM provider.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.services.agents.communication.protocol import CommunicationProtocol
from app.domain.services.tools.agent_tool import AgentTaskStatus, AgentTool

logger = logging.getLogger(__name__)

# Type alias for the optional async synthesizer hook
SynthesizerFn = Callable[[str, list["SubtaskResult"]], Coroutine[Any, Any, str]]


# ── Data classes ─────────────────────────────────────────────────────────────


class CoordinatorStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"  # some subtasks failed
    FAILED = "failed"


@dataclass
class SubtaskResult:
    """Result for a single dispatched subtask."""

    subtask_id: str
    subtask: str
    agent_task_id: str
    success: bool
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class CoordinatorResult:
    """Aggregated result from a CoordinatorFlow run."""

    run_id: str
    task: str
    status: CoordinatorStatus
    subtask_results: list[SubtaskResult] = field(default_factory=list)
    synthesis: str = ""
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.subtask_results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.subtask_results if not r.success)


# ── Default synthesizer ───────────────────────────────────────────────────────


async def _default_synthesizer(task: str, results: list[SubtaskResult]) -> str:
    """Simple concatenation synthesizer — replace with an LLM-backed one."""
    parts = [f"Task: {task}", ""]
    for r in results:
        status = "OK" if r.success else "FAILED"
        parts.append(f"[{status}] {r.subtask}")
        if r.output:
            parts.append(r.output)
        if r.error:
            parts.append(f"Error: {r.error}")
        parts.append("")
    return "\n".join(parts).strip()


# ── CoordinatorFlow ───────────────────────────────────────────────────────────


class CoordinatorFlow:
    """Coordinates parallel subagent execution and synthesizes results.

    Usage::

        agent_tool = AgentTool(runner=my_runner)
        coordinator = CoordinatorFlow(agent_tool=agent_tool)

        result = await coordinator.run(
            task="Analyse the codebase and produce a report",
            subtasks=[
                "List all Python files and count lines of code",
                "Find all TODO comments",
                "Identify the top-level modules",
            ],
        )
        print(result.synthesis)
    """

    def __init__(
        self,
        agent_tool: AgentTool,
        protocol: CommunicationProtocol | None = None,
        coordinator_id: str = "coordinator",
        coordinator_type: str = "coordinator",
        synthesizer: SynthesizerFn | None = None,
    ) -> None:
        self._agent_tool = agent_tool
        self._protocol = protocol
        self._coordinator_id = coordinator_id
        self._coordinator_type = coordinator_type
        self._synthesizer: SynthesizerFn = synthesizer or _default_synthesizer

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        task: str,
        subtasks: list[str],
        context: str = "",
        isolation: str = "shared",
        poll_interval: float = 0.5,
        deadline_seconds: float = 300.0,
    ) -> CoordinatorResult:
        """Decompose *task* into *subtasks*, run them in parallel, and synthesize.

        Args:
            task: Top-level task description (for synthesis context).
            subtasks: List of subtask descriptions to dispatch in parallel.
            context: Optional shared context string passed to every subagent.
            isolation: AgentTool isolation mode ('shared' or 'workspace').
            poll_interval: Seconds between status polls.
            deadline_seconds: Hard deadline in seconds for ALL subtasks to finish.

        Returns:
            CoordinatorResult with per-subtask results and synthesized output.
        """
        run_id = f"coord-{uuid.uuid4().hex[:8]}"
        wall_start = time.monotonic()

        if not subtasks:
            return CoordinatorResult(
                run_id=run_id,
                task=task,
                status=CoordinatorStatus.FAILED,
                synthesis="No subtasks provided.",
            )

        logger.info("CoordinatorFlow %s starting: %d subtasks for '%s'", run_id, len(subtasks), task[:60])

        # Optional: broadcast start notification
        if self._protocol:
            self._protocol.broadcast(
                sender_id=self._coordinator_id,
                sender_type=self._coordinator_type,
                subject=f"[{run_id}] Coordinator started",
                content=f"Dispatching {len(subtasks)} subtask(s) for: {task}",
            )

        # --- Dispatch all subtasks as background agent tasks ---
        dispatched: list[tuple[str, str, str]] = []  # (subtask_id, subtask, agent_task_id)
        for subtask in subtasks:
            subtask_id = f"st-{uuid.uuid4().hex[:6]}"
            sub_context = f"{context}\n\nParent task: {task}" if context else f"Parent task: {task}"
            result = await self._agent_tool.agent_run_background(
                task=subtask,
                context=sub_context,
                isolation=isolation,
            )
            if result.success:
                agent_task_id = result.data["task_id"]
                dispatched.append((subtask_id, subtask, agent_task_id))
                logger.debug("Dispatched subtask %s → agent task %s", subtask_id, agent_task_id)
            else:
                # Dispatch failed immediately — record as failed subtask
                dispatched.append((subtask_id, subtask, ""))
                logger.warning("Failed to dispatch subtask '%s': %s", subtask[:40], result.message)

        # --- Poll until all tasks finish or deadline ---
        subtask_results = await self._await_all(dispatched, subtasks, poll_interval, deadline_seconds)

        # Optional: broadcast finish notification
        if self._protocol:
            succeeded = sum(1 for r in subtask_results if r.success)
            self._protocol.broadcast(
                sender_id=self._coordinator_id,
                sender_type=self._coordinator_type,
                subject=f"[{run_id}] Coordinator finished",
                content=f"{succeeded}/{len(subtask_results)} subtasks succeeded.",
            )

        # --- Synthesize ---
        try:
            synthesis = await self._synthesizer(task, subtask_results)
        except Exception as exc:
            logger.exception("Synthesizer failed for run %s", run_id)
            synthesis = f"Synthesis failed: {exc}"

        # --- Determine overall status ---
        n_ok = sum(1 for r in subtask_results if r.success)
        n_total = len(subtask_results)
        if n_ok == n_total:
            status = CoordinatorStatus.COMPLETED
        elif n_ok == 0:
            status = CoordinatorStatus.FAILED
        else:
            status = CoordinatorStatus.PARTIAL

        duration = time.monotonic() - wall_start
        logger.info(
            "CoordinatorFlow %s done in %.1fs: %d/%d succeeded, status=%s",
            run_id,
            duration,
            n_ok,
            n_total,
            status,
        )

        return CoordinatorResult(
            run_id=run_id,
            task=task,
            status=status,
            subtask_results=subtask_results,
            synthesis=synthesis,
            duration_seconds=duration,
            metadata={"isolation": isolation, "subtask_count": n_total},
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _await_all(
        self,
        dispatched: list[tuple[str, str, str]],
        original_subtasks: list[str],
        poll_interval: float,
        deadline_seconds: float,
    ) -> list[SubtaskResult]:
        """Poll agent task statuses until all finish or deadline expires."""
        deadline = time.monotonic() + deadline_seconds
        # Track which agent_task_ids are still pending
        pending: set[str] = {agt_id for _, _, agt_id in dispatched if agt_id}
        results: dict[str, SubtaskResult] = {}

        # Pre-populate dispatch failures (empty agent_task_id)
        for subtask_id, subtask, agent_task_id in dispatched:
            if not agent_task_id:
                results[subtask_id] = SubtaskResult(
                    subtask_id=subtask_id,
                    subtask=subtask,
                    agent_task_id="",
                    success=False,
                    error="Dispatch failed",
                )

        while pending and time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            still_pending: set[str] = set()

            for subtask_id, subtask, agent_task_id in dispatched:
                if agent_task_id not in pending:
                    continue

                status_result = await self._agent_tool.agent_status(task_id=agent_task_id)
                if not status_result.success:
                    # Unknown task — treat as failed
                    results[subtask_id] = SubtaskResult(
                        subtask_id=subtask_id,
                        subtask=subtask,
                        agent_task_id=agent_task_id,
                        success=False,
                        error=status_result.message,
                    )
                    pending.discard(agent_task_id)
                    continue

                agent_status = status_result.data.get("status", "")
                agent_status_value = (
                    agent_status.value if isinstance(agent_status, AgentTaskStatus) else str(agent_status)
                )
                if agent_status_value in {"completed", "failed", "cancelled"}:
                    output_result = await self._agent_tool.agent_output(task_id=agent_task_id)
                    success = agent_status_value == "completed"
                    results[subtask_id] = SubtaskResult(
                        subtask_id=subtask_id,
                        subtask=subtask,
                        agent_task_id=agent_task_id,
                        success=success,
                        output=output_result.data.get("output") or "" if output_result.success else "",
                        error="" if success else (output_result.message or agent_status_value),
                    )
                    pending.discard(agent_task_id)
                    logger.debug("Subtask %s finished: %s", subtask_id, agent_status_value)
                else:
                    still_pending.add(agent_task_id)

        # Deadline exceeded: mark remaining as failed
        if pending:
            logger.warning("CoordinatorFlow deadline exceeded: %d subtask(s) still running", len(pending))
            for subtask_id, subtask, agent_task_id in dispatched:
                if subtask_id not in results:
                    results[subtask_id] = SubtaskResult(
                        subtask_id=subtask_id,
                        subtask=subtask,
                        agent_task_id=agent_task_id,
                        success=False,
                        error="Timeout",
                    )

        # Return in original dispatch order
        ordered: list[SubtaskResult] = []
        for subtask_id, _, _ in dispatched:
            if subtask_id in results:
                ordered.append(results[subtask_id])
        return ordered
