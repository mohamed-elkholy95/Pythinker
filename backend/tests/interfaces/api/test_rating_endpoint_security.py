"""Unit tests for rating endpoint security (Priority 6)."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.application.services.email_service import EmailService
from app.application.services.rating_service import RatingService
from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User
from app.infrastructure.repositories.mongo_session_repository import (
    MongoSessionRepository,
)
from app.interfaces.api.rating_routes import RatingRequest, submit_rating


@pytest.mark.asyncio
async def test_rating_requires_session_ownership():
    """Test that users can only rate their own sessions."""
    # Setup
    request = RatingRequest(
        session_id="session-123",
        report_id="report-456",
        rating=5,
        feedback="Great!",
    )

    current_user = User(id="user-1", email="user1@example.com", fullname="User One")

    # Mock session owned by different user
    other_user_session = Session(
        id="session-123",
        user_id="user-2",  # Different user
        agent_id="agent-2",
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    # Mock repository
    session_repository = Mock(spec=MongoSessionRepository)
    session_repository.find_by_id = AsyncMock(return_value=other_user_session)

    # Mock services
    rating_service = Mock(spec=RatingService)
    email_service = Mock(spec=EmailService)
    background_tasks = Mock()

    # Should raise 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        await submit_rating(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            email_service=email_service,
            rating_service=rating_service,
            session_repository=session_repository,
        )

    assert exc_info.value.status_code == 403
    assert "own sessions" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_rating_allowed_for_own_session():
    """Test that users can rate their own sessions."""
    # Setup
    request = RatingRequest(
        session_id="session-123",
        report_id="report-456",
        rating=5,
        feedback="Great!",
    )

    current_user = User(id="user-1", email="user1@example.com", fullname="User One")

    # Mock session owned by current user
    own_session = Session(
        id="session-123",
        user_id="user-1",  # Same user
        agent_id="agent-1",
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    # Mock repository
    session_repository = Mock(spec=MongoSessionRepository)
    session_repository.find_by_id = AsyncMock(return_value=own_session)

    # Mock services
    rating_service = Mock(spec=RatingService)
    rating_service.submit_rating = AsyncMock()

    email_service = Mock(spec=EmailService)
    email_service.send_rating_email = AsyncMock()

    background_tasks = Mock()
    background_tasks.add_task = Mock()

    # Should succeed
    response = await submit_rating(
        request=request,
        background_tasks=background_tasks,
        current_user=current_user,
        email_service=email_service,
        rating_service=rating_service,
        session_repository=session_repository,
    )

    assert response.status == "accepted"
    assert "5/5" in response.message

    # Should have called rating service
    rating_service.submit_rating.assert_called_once()


@pytest.mark.asyncio
async def test_rating_nonexistent_session_returns_404():
    """Test that rating a non-existent session returns 404."""
    # Setup
    request = RatingRequest(
        session_id="nonexistent-session",
        report_id="report-456",
        rating=5,
    )

    current_user = User(id="user-1", email="user1@example.com", fullname="User One")

    # Mock repository returning None (session not found)
    session_repository = Mock(spec=MongoSessionRepository)
    session_repository.find_by_id = AsyncMock(return_value=None)

    # Mock services
    rating_service = Mock(spec=RatingService)
    email_service = Mock(spec=EmailService)
    background_tasks = Mock()

    # Should raise 404 Not Found
    with pytest.raises(HTTPException) as exc_info:
        await submit_rating(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            email_service=email_service,
            rating_service=rating_service,
            session_repository=session_repository,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_unauthorized_rating_increments_metric():
    """Test that unauthorized rating attempts increment the metric."""
    from app.infrastructure.observability.prometheus_metrics import rating_unauthorized_attempts_total

    # Setup
    request = RatingRequest(
        session_id="session-123",
        report_id="report-456",
        rating=5,
    )

    current_user = User(id="user-1", email="user1@example.com", fullname="User One")

    # Mock session owned by different user
    other_user_session = Session(
        id="session-123",
        user_id="user-2",
        agent_id="agent-2",
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    session_repository = Mock(spec=MongoSessionRepository)
    session_repository.find_by_id = AsyncMock(return_value=other_user_session)

    rating_service = Mock(spec=RatingService)
    email_service = Mock(spec=EmailService)
    background_tasks = Mock()

    initial_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)

    # Attempt unauthorized rating
    with pytest.raises(HTTPException):
        await submit_rating(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            email_service=email_service,
            rating_service=rating_service,
            session_repository=session_repository,
        )

    final_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)

    # Metric should have incremented
    assert final_count == initial_count + 1


@pytest.mark.asyncio
async def test_validation_error_on_repository_failure():
    """Test that repository failures are handled gracefully."""
    # Setup
    request = RatingRequest(
        session_id="session-123",
        report_id="report-456",
        rating=5,
    )

    current_user = User(id="user-1", email="user1@example.com", fullname="User One")

    # Mock repository raising an error
    session_repository = Mock(spec=MongoSessionRepository)
    session_repository.find_by_id = AsyncMock(side_effect=Exception("Database error"))

    rating_service = Mock(spec=RatingService)
    email_service = Mock(spec=EmailService)
    background_tasks = Mock()

    # Should raise 500 Internal Server Error
    with pytest.raises(HTTPException) as exc_info:
        await submit_rating(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            email_service=email_service,
            rating_service=rating_service,
            session_repository=session_repository,
        )

    assert exc_info.value.status_code == 500
    assert "validate session ownership" in exc_info.value.detail.lower()
