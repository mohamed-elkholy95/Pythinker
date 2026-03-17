"""Cooperative cancellation signal for agent flows.

Used to request graceful shutdown of a running PlanActFlow.
The flow checks this signal between steps and during tool execution.
"""

from __future__ import annotations

import asyncio


class CancellationSignal:
    """Thread-safe cancellation flag checked between flow steps.

    Usage:
        signal = CancellationSignal()
        # In the flow loop:
        if signal.is_cancelled:
            break
        # From the API endpoint:
        signal.cancel()
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        """Request cancellation. Safe to call multiple times."""
        self._event.set()

    def reset(self) -> None:
        """Clear cancellation flag for reuse."""
        self._event.clear()

    async def wait(self, deadline: float | None = None) -> bool:
        """Wait for cancellation. Returns True if cancelled, False on timeout.

        Args:
            deadline: Optional timeout in seconds. Pass None to wait forever.
        """
        try:
            async with asyncio.timeout(deadline):
                await self._event.wait()
            return True
        except TimeoutError:
            return False
