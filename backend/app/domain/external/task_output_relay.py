"""Protocol for relaying background task output to reconnecting clients.

Abstracts the liveness check and output stream polling so the domain layer
does not depend on any specific infrastructure (Redis, etc.).
"""

from __future__ import annotations

from typing import Any, Protocol


class TaskOutputRelay(Protocol):
    """Relay interface for background task liveness and output streaming."""

    async def get_live_task_id(self, session_id: str) -> str | None:
        """Check whether a background task is alive for *session_id*.

        Returns:
            The task_id string if the task is still running, ``None`` otherwise.
        """
        ...

    async def get_task_output(
        self,
        task_id: str,
        start_id: str | None = None,
        block_ms: int | None = None,
    ) -> tuple[str | None, Any]:
        """Read the next output message from the task's output stream.

        Args:
            task_id: Identifier of the background task.
            start_id: Stream cursor to resume from (implementation-specific).
            block_ms: How long to block waiting for a message, in milliseconds.

        Returns:
            ``(message_id, data)`` on success, ``(None, None)`` when nothing is
            available within the blocking window.
        """
        ...
