"""Shielded tool execution with progress heartbeats.

Wraps tool calls with LLMHeartbeat + interleave_heartbeat so that
long-running tools emit ProgressEvent every N seconds, keeping the
idle timeout alive in StreamExecutor.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.domain.models.event import BaseEvent, PlanningPhase
from app.domain.services.flows.llm_heartbeat import LLMHeartbeat, interleave_heartbeat

logger = logging.getLogger(__name__)


class ToolExecutorWithHeartbeat:
    """Execute tool calls with heartbeat emission for long-running operations."""

    def __init__(self, interval_seconds: float = 5.0) -> None:
        self._interval = interval_seconds

    async def execute(
        self,
        tool_name: str,
        execute_fn: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[BaseEvent | Any]:
        """Execute a tool call, yielding heartbeats during execution.

        Args:
            tool_name: Name of the tool (for heartbeat message)
            execute_fn: Async callable that executes the tool
            *args, **kwargs: Passed to execute_fn
        """
        heartbeat = LLMHeartbeat(
            phase=PlanningPhase.TOOL_EXECUTING,
            message=f"Running {tool_name}...",
            interval_seconds=self._interval,
        )

        async def _tool_gen():
            result = await execute_fn(*args, **kwargs)
            yield result

        async with heartbeat:
            async for event in interleave_heartbeat(_tool_gen(), heartbeat):
                yield event
