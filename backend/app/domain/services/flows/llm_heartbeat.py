"""Periodic heartbeat emitter for long-running LLM calls.

Emits ProgressEvent at a configurable interval so the SSE stream
stays alive and the frontend shows continuous activity.

Also provides ``interleave_heartbeat`` — a concurrent wrapper that
yields heartbeat events even when the inner async generator is stalled
on a long-running LLM call.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TypeVar

from app.domain.models.event import BaseEvent, PlanningPhase, ProgressEvent

_T = TypeVar("_T", bound=BaseEvent)


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


async def interleave_heartbeat(
    inner: AsyncGenerator[_T, None],
    heartbeat: LLMHeartbeat,
) -> AsyncGenerator[_T | ProgressEvent, None]:
    """Wrap *inner* so heartbeat events are yielded even when *inner* stalls.

    When the inner generator blocks on a long LLM call (e.g. 75s report
    generation), this helper periodically yields buffered heartbeat events
    so the SSE stream stays alive and the frontend shows activity.

    Uses ``asyncio.wait`` with a timeout equal to the heartbeat interval
    to poll for the next inner event while draining heartbeats in between.
    """
    inner_iter = inner.__aiter__()
    pending_next: asyncio.Task[_T] | None = None

    try:
        while True:
            if pending_next is None:
                pending_next = asyncio.create_task(inner_iter.__anext__())  # type: ignore[arg-type]

            done, _ = await asyncio.wait({pending_next}, timeout=heartbeat._interval)

            if done:
                task = done.pop()
                pending_next = None
                try:
                    event = task.result()
                except StopAsyncIteration:
                    # Inner generator exhausted — drain final heartbeats
                    for hb_event in heartbeat.drain():
                        yield hb_event
                    break
                # Yield accumulated heartbeats first, then the real event
                for hb_event in heartbeat.drain():
                    yield hb_event
                yield event
            else:
                # Timeout — inner generator stalled, emit heartbeats
                for hb_event in heartbeat.drain():
                    yield hb_event
    finally:
        # Clean up pending task if the outer consumer stops iterating
        if pending_next is not None and not pending_next.done():
            pending_next.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending_next
