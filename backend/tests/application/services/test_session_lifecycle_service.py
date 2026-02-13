"""Tests for SessionLifecycleService - extracted session management from AgentService"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.application.services.session_lifecycle_service import SessionLifecycleService
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.application.errors.exceptions import NotFoundError


@pytest.fixture
def session_repository():
    """Mock session repository"""
    repo = AsyncMock()
    repo.save = AsyncMock()
    repo.find_by_id = AsyncMock()
    repo.find_by_id_and_user_id = AsyncMock()
    repo.find_by_user_id = AsyncMock()
    repo.delete = AsyncMock()
    repo.update_title = AsyncMock()
    repo.update_unread_message_count = AsyncMock()
    return repo


@pytest.fixture
def agent_domain_service():
    """Mock agent domain service"""
    service = AsyncMock()
    service.stop_session = AsyncMock()
    service.pause_session = AsyncMock(return_value=True)
    service.resume_session = AsyncMock(return_value=True)
    return service


@pytest.fixture
def service(session_repository, agent_domain_service):
    """Create SessionLifecycleService instance"""
    return SessionLifecycleService(
        session_repository=session_repository,
        agent_domain_service=agent_domain_service,
    )


class TestSessionLifecycleServiceInit:
    """Test SessionLifecycleService initialization"""

    def test_initializes_with_required_dependencies(self, session_repository, agent_domain_service):
        """Service initializes with session_repository and agent_domain_service"""
        service = SessionLifecycleService(
            session_repository=session_repository,
            agent_domain_service=agent_domain_service,
        )

        assert service._session_repository == session_repository
        assert service._agent_domain_service == agent_domain_service
        assert isinstance(service._session_cancel_events, dict)
        assert len(service._session_cancel_events) == 0


class TestRequestCancellation:
    """Test request_cancellation method"""

    def test_sets_cancel_event_when_exists(self, service):
        """Sets cancellation event for session when event exists"""
        import asyncio

        # Create and register a cancel event
        session_id = "test-session-123"
        event = asyncio.Event()
        service._session_cancel_events[session_id] = event

        # Request cancellation
        service.request_cancellation(session_id)

        # Verify event is set
        assert event.is_set()

    def test_does_nothing_when_no_event(self, service):
        """Does nothing gracefully when no cancel event exists"""
        # Should not raise exception
        service.request_cancellation("nonexistent-session")


class TestDeleteSession:
    """Test delete_session method"""

    @pytest.mark.asyncio
    async def test_deletes_session_for_valid_user(self, service, session_repository, agent_domain_service):
        """Deletes session when it belongs to the user"""
        session_id = "test-session-123"
        user_id = "user-456"
        session = Session(agent_id="agent-1", user_id=user_id, mode=AgentMode.AGENT)
        session.id = session_id

        session_repository.find_by_id_and_user_id.return_value = session

        await service.delete_session(session_id, user_id)

        # Verify session was looked up
        session_repository.find_by_id_and_user_id.assert_called_once_with(session_id, user_id)

        # Verify session was stopped
        agent_domain_service.stop_session.assert_called_once_with(session_id)

        # Verify session was deleted
        session_repository.delete.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_raises_not_found_when_session_missing(self, service, session_repository):
        """Raises NotFoundError when session doesn't exist"""
        session_repository.find_by_id_and_user_id.return_value = None

        with pytest.raises(NotFoundError, match="Session not found"):
            await service.delete_session("missing-session", "user-123")


class TestStopSession:
    """Test stop_session method"""

    @pytest.mark.asyncio
    async def test_stops_session_for_valid_user(self, service, session_repository, agent_domain_service):
        """Stops session when it belongs to the user"""
        session_id = "test-session-123"
        user_id = "user-456"
        session = Session(agent_id="agent-1", user_id=user_id, mode=AgentMode.AGENT)
        session.id = session_id
        session.status = SessionStatus.RUNNING

        session_repository.find_by_id_and_user_id.return_value = session

        await service.stop_session(session_id, user_id)

        # Verify session was looked up
        session_repository.find_by_id_and_user_id.assert_called_once_with(session_id, user_id)

        # Verify session was stopped
        agent_domain_service.stop_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_raises_not_found_when_session_missing(self, service, session_repository):
        """Raises NotFoundError when session doesn't exist"""
        session_repository.find_by_id_and_user_id.return_value = None

        with pytest.raises(NotFoundError, match="Session not found"):
            await service.stop_session("missing-session", "user-123")
