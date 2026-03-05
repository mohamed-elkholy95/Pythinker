"""Periodic heartbeat emitter for long-running LLM calls.

Emits ProgressEvent at a configurable interval so the SSE stream
stays alive and the frontend shows continuous activity.
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress

from app.domain.models.event import PlanningPhase, ProgressEvent


class LLMHeartbeat:
    """Produces ProgressEvent heartbeats on a background task."""

    def __init__(
        self,
        phase: PlanningPhase,
        message: str,
        interval_seconds: float = 2.5,
    ) -> None:
        self._phase = phase
        self._message = message
        self._interval = interval_seconds
        self._events: deque[ProgressEvent] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    def start(self) -> None:
        self._stopped = False
        self._task = asyncio.create_task(self._emit_loop())

    def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()

    def drain(self) -> list[ProgressEvent]:
        """Return and clear all buffered events."""
        events = list(self._events)
        self._events.clear()
        return events

    async def __aenter__(self) -> LLMHeartbeat:
        self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.stop()
        if self._task:
            with suppress(asyncio.CancelledError):
                await self._task

    async def _emit_loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._interval)
                if not self._stopped:
                    self._events.append(
                        ProgressEvent(
                            phase=self._phase,
                            message=self._message,
                        )
                    )
        except asyncio.CancelledError:
            return
