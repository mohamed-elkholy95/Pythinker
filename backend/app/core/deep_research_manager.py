"""Deep Research Session Manager.

Manages active deep research sessions for approve/skip operations.
Uses in-memory storage with automatic cleanup of completed sessions.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from app.domain.services.flows.deep_research import DeepResearchFlow

logger = logging.getLogger(__name__)

# Session timeout for cleanup
SESSION_TIMEOUT_MINUTES = 30


class DeepResearchManager:
    """Singleton manager for active deep research sessions."""

    _instance: Optional["DeepResearchManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "DeepResearchManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._sessions: dict[str, DeepResearchFlow] = {}
        self._session_times: dict[str, datetime] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def register(self, session_id: str, flow: DeepResearchFlow) -> None:
        """Register a deep research flow for a session.

        Args:
            session_id: Parent session ID
            flow: The deep research flow instance
        """
        async with self._lock:
            self._sessions[session_id] = flow
            self._session_times[session_id] = datetime.now(UTC)
            logger.info(f"Registered deep research for session {session_id}")

            # Start cleanup task if not running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def unregister(self, session_id: str) -> None:
        """Unregister a deep research flow.

        Args:
            session_id: Parent session ID
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                del self._session_times[session_id]
                logger.info(f"Unregistered deep research for session {session_id}")

    def get(self, session_id: str) -> DeepResearchFlow | None:
        """Get the active deep research flow for a session.

        Args:
            session_id: Parent session ID

        Returns:
            DeepResearchFlow if active, None otherwise
        """
        return self._sessions.get(session_id)

    async def approve(self, session_id: str) -> bool:
        """Approve deep research for a session.

        Args:
            session_id: Parent session ID

        Returns:
            True if approved, False if no active research found
        """
        flow = self.get(session_id)
        if flow:
            await flow.approve()
            return True
        return False

    async def skip_query(self, session_id: str, query_id: str | None = None) -> bool:
        """Skip a query or all queries in deep research.

        Args:
            session_id: Parent session ID
            query_id: Specific query ID or None for all

        Returns:
            True if skip signal sent, False if no active research found
        """
        flow = self.get(session_id)
        if flow:
            if query_id:
                return await flow.skip_query(query_id)
            await flow.skip_all()
            return True
        return False

    async def cancel(self, session_id: str) -> bool:
        """Cancel deep research for a session.

        Args:
            session_id: Parent session ID

        Returns:
            True if cancelled, False if no active research found
        """
        flow = self.get(session_id)
        if flow:
            await flow.cancel()
            await self.unregister(session_id)
            return True
        return False

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._cleanup_stale_sessions()

    async def _cleanup_stale_sessions(self) -> None:
        """Remove sessions that have timed out."""
        now = datetime.now(UTC)
        timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        async with self._lock:
            stale_sessions = [sid for sid, t in self._session_times.items() if now - t > timeout]

            for sid in stale_sessions:
                del self._sessions[sid]
                del self._session_times[sid]
                logger.info(f"Cleaned up stale deep research session {sid}")


# Global instance
_manager: DeepResearchManager | None = None


def get_deep_research_manager() -> DeepResearchManager:
    """Get the global deep research manager instance."""
    global _manager
    if _manager is None:
        _manager = DeepResearchManager()
    return _manager
