"""Cancellation utilities for graceful task termination.

Provides a simple cancellation token that can be checked throughout
the domain layer to detect when clients disconnect (SSE timeout, etc.).
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CancellationToken:
    """A simple cancellation token that wraps an asyncio.Event.

    Allows checking if cancellation was requested without needing to
    thread the event object through every function call.
    """

    def __init__(self, event: Optional[asyncio.Event] = None, session_id: str = ""):
        """Create a cancellation token.

        Args:
            event: Optional asyncio.Event that signals cancellation
            session_id: Session ID for logging purposes
        """
        self._event = event
        self._session_id = session_id
        self._checked_count = 0

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
                logger.info(
                    "Cancellation detected for session %s (client disconnected)",
                    self._session_id
                )
        return cancelled

    async def check_cancelled(self) -> None:
        """Check if cancelled and raise CancelledError if so.

        Raises:
            asyncio.CancelledError: If cancellation was requested
        """
        if self.is_cancelled():
            logger.info(
                "Raising CancelledError for session %s",
                self._session_id
            )
            raise asyncio.CancelledError(f"Session {self._session_id} cancelled")

    def __bool__(self) -> bool:
        """Allow using token in boolean context: if cancel_token: ..."""
        return not self.is_cancelled()

    @staticmethod
    def null() -> "CancellationToken":
        """Create a null token that never cancels (for tests, etc.)."""
        return CancellationToken(event=None, session_id="null")
