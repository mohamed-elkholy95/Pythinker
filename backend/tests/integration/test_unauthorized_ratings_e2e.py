"""End-to-end integration tests for rating endpoint security (Priority 6)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User


@pytest.mark.asyncio
async def test_unauthorized_rating_blocked_e2e():
    """Test that unauthorized users cannot rate other users' sessions (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    # Mock authentication
    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user2_session = Session(
        id="session-123",
        user_id="user-2",  # Different user
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    # Mock repository
    with (
        patch("app.interfaces.dependencies.get_current_user", return_value=user1),
        patch("app.interfaces.dependencies.get_session_repository") as mock_repo,
    ):
        mock_repo_instance = Mock(spec=MongoSessionRepository)
        mock_repo_instance.get_by_id = AsyncMock(return_value=user2_session)
        mock_repo.return_value = mock_repo_instance

        # Attempt to rate another user's session
        response = client.post(
            "/ratings",
            json={
                "session_id": "session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great!",
            },
        )

        # Should be forbidden
        assert response.status_code == 403
        assert "own sessions" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_authorized_rating_succeeds_e2e():
    """Test that users can successfully rate their own sessions (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    # Mock authentication
    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user1_session = Session(
        id="session-123",
        user_id="user-1",  # Same user
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    # Mock dependencies
    with (
        patch("app.interfaces.dependencies.get_current_user", return_value=user1),
        patch("app.interfaces.dependencies.get_session_repository") as mock_repo,
        patch("app.interfaces.dependencies.get_rating_service") as mock_rating,
        patch("app.interfaces.dependencies.get_email_service") as mock_email,
    ):
        # Setup mocks
        mock_repo_instance = Mock(spec=MongoSessionRepository)
        mock_repo_instance.get_by_id = AsyncMock(return_value=user1_session)
        mock_repo.return_value = mock_repo_instance

        mock_rating_instance = Mock()
        mock_rating_instance.submit_rating = AsyncMock()
        mock_rating.return_value = mock_rating_instance

        mock_email_instance = Mock()
        mock_email_instance.send_rating_email = AsyncMock()
        mock_email.return_value = mock_email_instance

        # Rate own session
        response = client.post(
            "/ratings",
            json={
                "session_id": "session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great!",
            },
        )

        # Should succeed
        assert response.status_code == 201
        assert response.json()["status"] == "accepted"
        assert "5/5" in response.json()["message"]


@pytest.mark.asyncio
async def test_rating_nonexistent_session_blocked_e2e():
    """Test that rating a non-existent session returns 404 (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")

    with (
        patch("app.interfaces.dependencies.get_current_user", return_value=user1),
        patch("app.interfaces.dependencies.get_session_repository") as mock_repo,
    ):
        # Session not found
        mock_repo_instance = Mock(spec=MongoSessionRepository)
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        response = client.post(
            "/ratings",
            json={
                "session_id": "nonexistent-session",
                "report_id": "report-456",
                "rating": 5,
            },
        )

        # Should return 404
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_multiple_unauthorized_attempts_tracked():
    """Test that multiple unauthorized attempts are tracked in metrics."""
    from app.infrastructure.observability.prometheus_metrics import (
        rating_unauthorized_attempts_total,
    )
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user2_session = Session(
        id="session-123",
        user_id="user-2",
        prompt="test",
        status=SessionStatus.COMPLETED,
    )

    initial_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)

    with (
        patch("app.interfaces.dependencies.get_current_user", return_value=user1),
        patch("app.interfaces.dependencies.get_session_repository") as mock_repo,
    ):
        mock_repo_instance = Mock(spec=MongoSessionRepository)
        mock_repo_instance.get_by_id = AsyncMock(return_value=user2_session)
        mock_repo.return_value = mock_repo_instance

        # Attempt 5 unauthorized ratings
        for _ in range(5):
            client.post(
                "/ratings",
                json={
                    "session_id": "session-123",
                    "report_id": "report-456",
                    "rating": 5,
                },
            )

    final_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)

    # Metric should have incremented by 5
    assert final_count == initial_count + 5
