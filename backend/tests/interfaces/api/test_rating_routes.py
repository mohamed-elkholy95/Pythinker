"""Tests for rating API endpoints."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User
from app.interfaces.dependencies import (
    get_current_user,
    get_email_service,
    get_rating_service,
    get_session_repository,
)
from app.main import app


def _make_test_user() -> User:
    return User(id="test-user-id", email="test@example.com", fullname="Test User")


def _mock_email_service() -> AsyncMock:
    svc = AsyncMock()
    svc.send_rating_email = AsyncMock()
    return svc


def _mock_rating_service() -> AsyncMock:
    svc = AsyncMock()
    svc.submit_rating = AsyncMock()
    return svc


def _mock_session_repository(user_id: str) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(
        return_value=Session(
            id="test-session-123",
            user_id=user_id,
            agent_id="agent-test",
            status=SessionStatus.COMPLETED,
        )
    )
    return repo


@pytest.fixture()
def _override_deps():
    """Override auth and email deps for rating tests."""
    user = _make_test_user()
    email_svc = _mock_email_service()
    rating_svc = _mock_rating_service()
    session_repo = _mock_session_repository(user.id)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_email_service] = lambda: email_svc
    app.dependency_overrides[get_rating_service] = lambda: rating_svc
    app.dependency_overrides[get_session_repository] = lambda: session_repo
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_email_service, None)
    app.dependency_overrides.pop(get_rating_service, None)
    app.dependency_overrides.pop(get_session_repository, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_submit_rating_success():
    """Should accept valid rating submission."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 4,
            },
        )
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_submit_rating_with_feedback():
    """Should accept rating with optional feedback."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great report!",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    assert "5/5" in data["message"]


@pytest.mark.asyncio
async def test_submit_rating_invalid_value_too_high():
    """Should reject rating values above 5."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 6,  # Invalid: must be 1-5
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_invalid_value_too_low():
    """Should reject rating values below 1."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 0,  # Invalid: must be 1-5
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_missing_session_id():
    """Should reject request without session_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "report_id": "report-456",
                "rating": 4,
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_missing_report_id():
    """Should reject request without report_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "rating": 4,
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_submit_rating_boundary_values():
    """Should accept boundary rating values (1 and 5)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test rating = 1
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 1,
            },
        )
        assert response.status_code == 201
        assert "1/5" in response.json()["message"]

        # Test rating = 5
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 5,
            },
        )
        assert response.status_code == 201
        assert "5/5" in response.json()["message"]
