"""Cancellation utilities for graceful task termination.

Provides a simple cancellation token that can be checked throughout
the domain layer to detect when clients disconnect (SSE timeout, etc.).
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CancellationToken:
    """A simple cancellation token that wraps an asyncio.Event.

    Allows checking if cancellation was requested without needing to
    thread the event object through every function call.

    Enhanced with:
    - Cooperative waiting
    - Coroutine wrapping with cancellation races
    - Cleanup callback registration
    """

    def __init__(self, event: asyncio.Event | None = None, session_id: str = ""):
        """Create a cancellation token.

        Args:
            event: Optional asyncio.Event that signals cancellation
            session_id: Session ID for logging purposes
        """
        self._event = event
        self._session_id = session_id
        self._checked_count = 0
        self._cleanup_callbacks: list[Callable[[], Coroutine[Any, Any, None]]] = []

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested.

        Returns:
            True if cancellation requested, False otherwise
        """
        if self._event is None:
            return False

        cancelled = self._event.is_set()
        if cancelled:
            self._checked_count += 1
            if self._checked_count == 1:  # Log only once
                logger.info("Cancellation detected for session %s (client disconnected)", self._session_id)
        return cancelled

    async def check_cancelled(self) -> None:
        """Check if cancelled and raise CancelledError if so.

        Raises:
            asyncio.CancelledError: If cancellation was requested
        """
        if self.is_cancelled():
            logger.info("Raising CancelledError for session %s", self._session_id)
            raise asyncio.CancelledError(f"Session {self._session_id} cancelled")

    async def wait_for_cancellation(self, wait_seconds: float | None = None) -> bool:
        """Cooperatively wait for cancellation with optional timeout.

        This allows yielding control while waiting for cancellation,
        preventing busy-waiting in loops.

        Args:
            wait_seconds: Optional wait duration in seconds. None means wait indefinitely.

        Returns:
            True if cancellation occurred, False if timeout reached
        """
        if self._event is None:
            if wait_seconds:
                await asyncio.sleep(wait_seconds)
            return False

        try:
            if wait_seconds:
                await asyncio.wait_for(self._event.wait(), timeout=wait_seconds)
            else:
                await self._event.wait()
            return True
        except TimeoutError:
            return False

    async def wrap_awaitable(self, coro: Coroutine[Any, Any, T]) -> T:
        """Wrap a coroutine to race it against cancellation.

        If cancellation is requested while the coroutine is running,
        the coroutine is cancelled and CancelledError is raised.

        Args:
            coro: The coroutine to wrap

        Returns:
            The result of the coroutine if it completes before cancellation

        Raises:
            asyncio.CancelledError: If cancellation was requested
        """
        if self.is_cancelled():
            # Caller may pass an already-created coroutine object; close it to
            # avoid "coroutine was never awaited" warnings on early cancellation.
            with contextlib.suppress(Exception):
                coro.close()
            raise asyncio.CancelledError(f"Session {self._session_id} already cancelled")

        task = asyncio.create_task(coro)
        cancel_wait_task: asyncio.Task[bool] | None = None

        if self._event is not None:
            cancel_wait_task = asyncio.create_task(self._event.wait())

        try:
            if cancel_wait_task:
                done, _pending = await asyncio.wait(
                    {task, cancel_wait_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # If cancellation event fired first
                if cancel_wait_task in done:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                    raise asyncio.CancelledError(f"Session {self._session_id} cancelled during operation")

                # Task completed first
                return task.result()
            return await task
        finally:
            if cancel_wait_task and not cancel_wait_task.done():
                cancel_wait_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await cancel_wait_task

    def register_cleanup(self, callback: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Register a cleanup callback to be called on cancellation.

        Callbacks are called in reverse order of registration (LIFO).
        They are executed when run_cleanup() is called.

        Args:
            callback: Async cleanup function to register
        """
        self._cleanup_callbacks.append(callback)

    async def run_cleanup(self) -> None:
        """Run all registered cleanup callbacks.

        This should be called when handling cancellation to ensure
        resources are properly released. Callbacks are run in LIFO order.

        Note: This does not automatically raise CancelledError after cleanup.
        """
        if not self._cleanup_callbacks:
            return

        logger.info(
            "Running %d cleanup callbacks for session %s",
            len(self._cleanup_callbacks),
            self._session_id,
        )

        # Run callbacks in reverse order (LIFO)
        for callback in reversed(self._cleanup_callbacks):
            try:
                await callback()
            except Exception as e:
                logger.warning(
                    "Cleanup callback failed for session %s: %s",
                    self._session_id,
                    e,
                )

        self._cleanup_callbacks.clear()

    def clear(self) -> None:
        """Clear cancellation state (e.g., when client reconnects).

        Resets the internal event so that ``is_cancelled()`` returns False
        and ``check_cancelled()`` no longer raises.
        """
        if self._event is not None:
            self._event.clear()
            self._checked_count = 0

    def __bool__(self) -> bool:
        """Allow using token in boolean context: if cancel_token: ..."""
        return not self.is_cancelled()

    @staticmethod
    def null() -> "CancellationToken":
        """Create a null token that never cancels (for tests, etc.)."""
        return CancellationToken(event=None, session_id="null")
