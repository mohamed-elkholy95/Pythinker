"""End-to-end integration tests for rating endpoint security (Priority 6)."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User
from app.interfaces.dependencies import (
    get_current_user,
    get_email_service,
    get_rating_service,
    get_session_repository,
)


def _build_session(owner_user_id: str) -> Session:
    return Session(
        id="session-123",
        user_id=owner_user_id,
        agent_id="agent-123",
        status=SessionStatus.COMPLETED,
    )


@pytest.mark.asyncio
async def test_unauthorized_rating_blocked_e2e():
    """Test that unauthorized users cannot rate other users' sessions (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user2_session = _build_session(owner_user_id="user-2")

    session_repo = AsyncMock(spec=MongoSessionRepository)
    session_repo.find_by_id = AsyncMock(return_value=user2_session)

    rating_service = AsyncMock()
    rating_service.submit_rating = AsyncMock()
    email_service = AsyncMock()
    email_service.send_rating_email = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user1
    app.dependency_overrides[get_session_repository] = lambda: session_repo
    app.dependency_overrides[get_rating_service] = lambda: rating_service
    app.dependency_overrides[get_email_service] = lambda: email_service

    try:
        response = client.post(
            "/api/v1/ratings",
            json={
                "session_id": "session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great!",
            },
        )
        assert response.status_code == 403
        assert "own sessions" in response.json()["msg"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorized_rating_succeeds_e2e():
    """Test that users can successfully rate their own sessions (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user1_session = _build_session(owner_user_id="user-1")

    session_repo = AsyncMock(spec=MongoSessionRepository)
    session_repo.find_by_id = AsyncMock(return_value=user1_session)

    rating_service = AsyncMock()
    rating_service.submit_rating = AsyncMock()
    email_service = AsyncMock()
    email_service.send_rating_email = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user1
    app.dependency_overrides[get_session_repository] = lambda: session_repo
    app.dependency_overrides[get_rating_service] = lambda: rating_service
    app.dependency_overrides[get_email_service] = lambda: email_service

    try:
        response = client.post(
            "/api/v1/ratings",
            json={
                "session_id": "session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great!",
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "accepted"
        assert "5/5" in response.json()["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rating_nonexistent_session_blocked_e2e():
    """Test that rating a non-existent session returns 404 (E2E)."""
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")

    session_repo = AsyncMock(spec=MongoSessionRepository)
    session_repo.find_by_id = AsyncMock(return_value=None)

    rating_service = AsyncMock()
    rating_service.submit_rating = AsyncMock()
    email_service = AsyncMock()
    email_service.send_rating_email = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user1
    app.dependency_overrides[get_session_repository] = lambda: session_repo
    app.dependency_overrides[get_rating_service] = lambda: rating_service
    app.dependency_overrides[get_email_service] = lambda: email_service

    try:
        response = client.post(
            "/api/v1/ratings",
            json={
                "session_id": "nonexistent-session",
                "report_id": "report-456",
                "rating": 5,
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["msg"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_multiple_unauthorized_attempts_tracked():
    """Test that multiple unauthorized attempts are tracked in metrics."""
    from app.core.prometheus_metrics import (
        rating_unauthorized_attempts_total,
    )
    from app.infrastructure.repositories.mongo_session_repository import (
        MongoSessionRepository,
    )
    from app.main import app

    client = TestClient(app)

    user1 = User(id="user-1", email="user1@example.com", fullname="User One")
    user2_session = _build_session(owner_user_id="user-2")

    initial_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)

    session_repo = AsyncMock(spec=MongoSessionRepository)
    session_repo.find_by_id = AsyncMock(return_value=user2_session)

    rating_service = AsyncMock()
    rating_service.submit_rating = AsyncMock()
    email_service = AsyncMock()
    email_service.send_rating_email = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user1
    app.dependency_overrides[get_session_repository] = lambda: session_repo
    app.dependency_overrides[get_rating_service] = lambda: rating_service
    app.dependency_overrides[get_email_service] = lambda: email_service

    try:
        for _ in range(5):
            response = client.post(
                "/api/v1/ratings",
                json={
                    "session_id": "session-123",
                    "report_id": "report-456",
                    "rating": 5,
                },
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()

    final_count = rating_unauthorized_attempts_total._value.get(frozenset(), 0)
    assert final_count == initial_count + 5
