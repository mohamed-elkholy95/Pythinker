"""Tests for rating API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user, get_email_service
from app.main import app


def _make_test_user() -> User:
    return User(id="test-user-id", email="test@example.com", fullname="Test User")


def _mock_email_service() -> AsyncMock:
    svc = AsyncMock()
    svc.send_rating_email = AsyncMock()
    return svc


@pytest.fixture()
def _override_deps():
    """Override auth and email deps for rating tests."""
    user = _make_test_user()
    email_svc = _mock_email_service()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_email_service] = lambda: email_svc
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_email_service, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_submit_rating_success():
    """Should accept valid rating submission."""
    with patch("app.interfaces.api.rating_routes.RatingDocument") as mock_doc_cls:
        mock_instance = AsyncMock()
        mock_doc_cls.return_value = mock_instance
        mock_instance.insert = AsyncMock()

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
        mock_instance.insert.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_deps")
async def test_submit_rating_with_feedback():
    """Should accept rating with optional feedback."""
    with patch("app.interfaces.api.rating_routes.RatingDocument") as mock_doc_cls:
        mock_instance = AsyncMock()
        mock_doc_cls.return_value = mock_instance
        mock_instance.insert = AsyncMock()

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
        # Verify feedback was passed to document
        call_kwargs = mock_doc_cls.call_args
        assert call_kwargs.kwargs.get("feedback") == "Great report!"


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
    with patch("app.interfaces.api.rating_routes.RatingDocument") as mock_doc_cls:
        mock_instance = AsyncMock()
        mock_doc_cls.return_value = mock_instance
        mock_instance.insert = AsyncMock()

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
