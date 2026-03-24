"""Session Lifecycle Service - Extracted from AgentService

Handles session CRUD operations, state management, and cleanup.
Follows Single Responsibility Principle - one service for session lifecycle.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from app.application.errors.exceptions import NotFoundError
from app.domain.models.session import SessionStatus, TakeoverReason
from app.domain.repositories.session_repository import SessionRepository

if TYPE_CHECKING:
    from app.domain.services.agent_domain_service import AgentDomainService

logger = logging.getLogger(__name__)


class SessionLifecycleService:
    """Manages session lifecycle: creation, deletion, state transitions, cleanup"""

    def __init__(
        self,
        session_repository: SessionRepository,
        agent_domain_service: "AgentDomainService",
    ):
        """Initialize SessionLifecycleService

        Args:
            session_repository: Repository for session persistence
            agent_domain_service: Domain service for agent operations
        """
        self._session_repository = session_repository
        self._agent_domain_service = agent_domain_service
        self._session_cancel_events: dict[str, asyncio.Event] = {}

    def request_cancellation(self, session_id: str) -> None:
        """Signal that a session's processing should stop (e.g. SSE disconnect).

        Args:
            session_id: ID of session to cancel
        """
        event = self._session_cancel_events.get(session_id)
        if event:
            event.set()
            logger.info("Cancellation requested for session %s", session_id)

    def register_cancel_event(self, session_id: str) -> asyncio.Event:
        """Register a cancellation event for a session.

        Args:
            session_id: ID of session

        Returns:
            Asyncio Event that will be set when cancellation is requested
        """
        event = asyncio.Event()
        self._session_cancel_events[session_id] = event
        return event

    def unregister_cancel_event(self, session_id: str) -> None:
        """Unregister cancellation event for a session.

        Args:
            session_id: ID of session
        """
        self._session_cancel_events.pop(session_id, None)

    async def delete_session(self, session_id: str, user_id: str) -> None:
        """Delete a session, ensuring it belongs to the user.

        Destroys the associated sandbox container before deleting the session
        record to prevent orphaned Docker containers.

        Args:
            session_id: ID of session to delete
            user_id: User ID for ownership verification

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Deleting session {session_id} for user {user_id}")

        # Verify session belongs to user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        # Stop session first
        try:
            await self._agent_domain_service.stop_session(session_id)
        except Exception as e:
            logger.warning(f"Failed to stop session {session_id} before deletion: {e}")

        # Clean up cancel event
        self.unregister_cancel_event(session_id)

        await self._session_repository.delete(session_id)
        logger.info(f"Session {session_id} deleted successfully")

    async def stop_session(self, session_id: str, user_id: str) -> None:
        """Stop a session, ensuring it belongs to the user.

        Args:
            session_id: ID of session to stop
            user_id: User ID for ownership verification

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Stopping session {session_id} for user {user_id}")

        # Verify session belongs to user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        # Record metric if stopping active session
        if session.status in (SessionStatus.RUNNING, SessionStatus.INITIALIZING):
            try:
                from app.domain.external.observability import get_metrics

                get_metrics().record_counter("user_stop_before_done_total")
            except Exception as e:
                logger.debug("Could not record user_stop_before_done metric: %s", e)

        await self._agent_domain_service.stop_session(session_id)

        # Clean up cancel event to prevent memory leak
        self.unregister_cancel_event(session_id)

        logger.info(f"Session {session_id} stopped successfully")

    async def pause_session(self, session_id: str, user_id: str) -> bool:
        """Pause a session for user takeover, ensuring it belongs to the user.

        Args:
            session_id: ID of session to pause
            user_id: User ID for ownership verification

        Returns:
            True if session was paused successfully

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Pausing session {session_id} for user {user_id}")

        # Verify session belongs to user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        result = await self._agent_domain_service.pause_session(session_id)
        if result:
            logger.info(f"Session {session_id} paused successfully")
        return result

    async def resume_session(
        self, session_id: str, user_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session after user takeover, ensuring it belongs to the user.

        Args:
            session_id: Session ID to resume
            user_id: User ID for ownership verification
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state

        Returns:
            True if session was resumed successfully

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Resuming session {session_id} for user {user_id}")

        # Verify session belongs to user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        result = await self._agent_domain_service.resume_session(
            session_id, context=context, persist_login_state=persist_login_state
        )
        if result:
            logger.info(f"Session {session_id} resumed successfully")
        return result

    async def start_takeover(
        self, session_id: str, user_id: str, reason: str | TakeoverReason = TakeoverReason.MANUAL
    ) -> bool:
        """Start browser takeover, ensuring session belongs to the user.

        Args:
            session_id: Session ID to take over
            user_id: User ID for ownership verification
            reason: Reason for takeover

        Returns:
            True if takeover started successfully

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Starting takeover for session {session_id} for user {user_id} (reason={reason})")
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        result = await self._agent_domain_service.start_takeover(session_id, reason=reason)
        if result:
            logger.info(f"Session {session_id} takeover started successfully")
        return result

    async def end_takeover(
        self,
        session_id: str,
        user_id: str,
        context: str | None = None,
        persist_login_state: bool | None = None,
        resume_agent: bool = True,
    ) -> bool:
        """End browser takeover, ensuring session belongs to the user.

        Args:
            session_id: Session ID to end takeover for
            user_id: User ID for ownership verification
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state
            resume_agent: Whether to resume the agent

        Returns:
            True if takeover ended successfully

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Ending takeover for session {session_id} for user {user_id}")
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        result = await self._agent_domain_service.end_takeover(
            session_id,
            context=context,
            persist_login_state=persist_login_state,
            resume_agent=resume_agent,
        )
        if result:
            logger.info(f"Session {session_id} takeover ended successfully")
        return result

    async def get_takeover_status(self, session_id: str, user_id: str) -> dict:
        """Get takeover status for a session, ensuring it belongs to the user.

        Returns:
            Dict with session_id, takeover_state, and reason

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            raise NotFoundError("Session not found")

        return {
            "session_id": session_id,
            "takeover_state": session.takeover_state.value
            if hasattr(session.takeover_state, "value")
            else str(session.takeover_state),
            "reason": session.takeover_reason,
        }

    async def rename_session(self, session_id: str, user_id: str, title: str) -> None:
        """Rename a session, ensuring it belongs to the user.

        Args:
            session_id: ID of session to rename
            user_id: User ID for ownership verification
            title: New title for the session

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Renaming session {session_id} for user {user_id} to '{title}'")

        # Verify session belongs to user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        await self._session_repository.update_title(session_id, title)
        logger.info(f"Session {session_id} renamed successfully")

    async def clear_unread_message_count(self, session_id: str, user_id: str) -> None:
        """Clear the unread message count for a session, ensuring it belongs to the user.

        Args:
            session_id: ID of session
            user_id: User ID for ownership verification

        Raises:
            NotFoundError: If session not found or doesn't belong to user
        """
        logger.info(f"Clearing unread message count for session {session_id} for user {user_id}")

        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        await self._session_repository.update_unread_message_count(session_id, 0)
        logger.info(f"Unread message count cleared for session {session_id}")
