"""Streaming executor with cancellation grace and idle timeout management.

Extracted from plan_act.py:2042-2108 to provide a reusable, testable
streaming loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator

from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    ToolEvent,
    ToolStatus,
)
from app.domain.utils.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class StreamExecutor:
    """Execute an async event generator with timeout and cancellation."""

    def __init__(
        self,
        cancel_token: CancellationToken,
        session_id: str,
        agent_id: str,
        wall_clock_timeout: int,
        idle_timeout: int,
        grace_period: int = 5,
    ) -> None:
        self._cancel_token = cancel_token
        self._session_id = session_id
        self._agent_id = agent_id
        self._wall_clock_timeout = wall_clock_timeout
        self._idle_timeout = idle_timeout
        self._grace_period = grace_period

    async def execute(
        self,
        inner: AsyncGenerator[BaseEvent, None],
    ) -> AsyncIterator[BaseEvent]:
        """Stream events with timeout, cancellation, and tool-aware grace."""
        try:
            # Initial cancellation check before starting
            await self._check_cancelled(tool_active=False)

            async with asyncio.timeout(self._wall_clock_timeout):
                inner_iter = inner.__aiter__()
                tool_active = False

                while True:
                    await self._check_cancelled(tool_active=tool_active)

                    try:
                        async with asyncio.timeout(self._idle_timeout):
                            event = await inner_iter.__anext__()
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        idle_mins = self._idle_timeout // 60
                        logger.warning(
                            "Agent %s idle timeout after %ds for session %s",
                            self._agent_id,
                            self._idle_timeout,
                            self._session_id,
                        )
                        async for ev in self._timeout_cleanup(
                            inner_iter,
                            f"The agent hasn't produced output for {idle_mins} minutes and may be stuck.",
                            "workflow_idle_timeout",
                        ):
                            yield ev
                        return

                    # Track tool execution state for grace period
                    if isinstance(event, ToolEvent):
                        if event.status == ToolStatus.CALLING:
                            tool_active = True
                        elif event.status == ToolStatus.CALLED:
                            tool_active = False

                    yield event

        except asyncio.CancelledError:
            logger.info(
                "StreamExecutor: workflow cancelled for session %s",
                self._session_id,
            )
            raise
        except TimeoutError:
            wall_mins = self._wall_clock_timeout // 60
            logger.error(
                "Agent %s wall-clock timeout after %ds for session %s",
                self._agent_id,
                self._wall_clock_timeout,
                self._session_id,
            )
            async for ev in self._timeout_cleanup(
                inner,
                f"The task reached the {wall_mins}-minute time limit.",
                "workflow_wall_clock_timeout",
            ):
                yield ev

    async def _timeout_cleanup(
        self,
        inner_iter: AsyncIterator[BaseEvent],
        error_message: str,
        error_code: str,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Close inner generator (so its finally-blocks run) then emit timeout events."""
        try:
            await inner_iter.aclose()
        except Exception as e:
            logger.debug(
                "StreamExecutor: inner generator close error for session %s: %s",
                self._session_id,
                e,
            )
        yield ErrorEvent(
            error=error_message,
            error_type="timeout",
            recoverable=True,
            can_resume=True,
            error_code=error_code,
        )
        yield DoneEvent()

    async def _check_cancelled(self, tool_active: bool = False) -> None:
        """Check cancellation with grace period during tool execution."""
        if not self._cancel_token.is_cancelled():
            return
        if tool_active and self._grace_period > 0:
            logger.info(
                "StreamExecutor: disconnect detected during tool execution, waiting %ds grace period for session %s",
                self._grace_period,
                self._session_id,
            )
            await asyncio.sleep(self._grace_period)
            if not self._cancel_token.is_cancelled():
                logger.info(
                    "StreamExecutor: client reconnected during grace for %s",
                    self._session_id,
                )
                return
        raise asyncio.CancelledError(f"Session {self._session_id} cancelled")
