"""Tests for canvas API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models.canvas import CanvasPage, CanvasProject
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.main import app

BASE_URL = "http://test"


def _make_test_user(user_id: str = "test-user-id") -> User:
    return User(id=user_id, email=f"{user_id}@example.com", fullname="Test User")


def _make_project(
    *,
    project_id: str = "project-123",
    user_id: str = "test-user-id",
    session_id: str | None = None,
    version: int = 1,
) -> CanvasProject:
    return CanvasProject(
        id=project_id,
        user_id=user_id,
        session_id=session_id,
        name="Studio Draft",
        pages=[
            CanvasPage(
                id="page-1",
                name="Page 1",
                width=1920,
                height=1080,
                background="#FFFFFF",
            )
        ],
        width=1920,
        height=1080,
        background="#FFFFFF",
        version=version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _mock_canvas_service() -> MagicMock:
    service = MagicMock()
    service.create_project = AsyncMock()
    service.get_project_by_session_id = AsyncMock()
    return service


@pytest.fixture()
def _override_user():
    user = _make_test_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_create_project_accepts_and_persists_session_id():
    service = _mock_canvas_service()
    service.create_project.return_value = _make_project(session_id="session-123")

    with patch("app.interfaces.api.canvas_routes.get_canvas_service", return_value=service):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/canvas/projects",
                json={
                    "name": "Studio Draft",
                    "width": 1440,
                    "height": 900,
                    "background": "#111827",
                    "session_id": "session-123",
                },
            )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["session_id"] == "session-123"
    service.create_project.assert_awaited_once_with(
        user_id="test-user-id",
        name="Studio Draft",
        width=1440,
        height=900,
        background="#111827",
        session_id="session-123",
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_get_session_project_returns_active_project_for_owner():
    service = _mock_canvas_service()
    service.get_project_by_session_id.return_value = _make_project(session_id="session-123", version=7)

    with patch("app.interfaces.api.canvas_routes.get_canvas_service", return_value=service):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get("/api/v1/canvas/sessions/session-123/project")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["id"] == "project-123"
    assert payload["session_id"] == "session-123"
    assert payload["version"] == 7
    assert payload["updated_at"]
    service.get_project_by_session_id.assert_awaited_once_with("session-123")


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_user")
async def test_get_session_project_hides_projects_owned_by_other_users():
    service = _mock_canvas_service()
    service.get_project_by_session_id.return_value = _make_project(
        user_id="other-user-id",
        session_id="session-123",
    )

    with patch("app.interfaces.api.canvas_routes.get_canvas_service", return_value=service):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get("/api/v1/canvas/sessions/session-123/project")

    assert response.status_code == 404
    assert response.json()["msg"] == "Project not found"
    service.get_project_by_session_id.assert_awaited_once_with("session-123")
