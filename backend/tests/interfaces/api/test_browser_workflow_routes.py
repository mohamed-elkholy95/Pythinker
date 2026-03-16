"""Tests for browser workflow API routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.models.user import User
from app.interfaces.dependencies import get_browser_workflow_service, get_current_user
from app.main import app

BASE_URL = "http://test"


def _make_test_user(user_id: str = "browser-workflow-user") -> User:
    return User(id=user_id, email=f"{user_id}@example.com", fullname="Browser Workflow User")


async def _progress_events() -> AsyncGenerator[dict[str, object], None]:
    yield {
        "event_id": "100-0",
        "phase": "completed",
        "url": "https://example.com/article",
        "mode": "dynamic",
    }


@pytest.fixture()
def _override_browser_workflow_dependencies():
    user = _make_test_user()
    service = MagicMock()
    service.fetch_with_progress = MagicMock(return_value=_progress_events())
    service.invalidate_cache = AsyncMock(return_value=2)
    service.get_capabilities = AsyncMock(return_value={"available_modes": ["http", "dynamic", "stealth"]})

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_browser_workflow_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_browser_workflow_service, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_browser_workflow_dependencies")
async def test_fetch_stream_rejects_ssrf_targets(_override_browser_workflow_dependencies: MagicMock) -> None:
    service = _override_browser_workflow_dependencies

    with patch(
        "app.interfaces.api.browser_workflow_routes.is_ssrf_target",
        return_value="Blocked internal hostname: sandbox",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.get(
                "/api/v1/browser-workflow/fetch/stream",
                params={"url": "http://sandbox/internal", "mode": "dynamic"},
            )

    assert response.status_code == 400
    assert response.json()["msg"] == "Blocked internal hostname: sandbox"
    service.fetch_with_progress.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_browser_workflow_dependencies")
async def test_invalidate_cache_rejects_ssrf_targets(_override_browser_workflow_dependencies: MagicMock) -> None:
    service = _override_browser_workflow_dependencies

    with patch(
        "app.interfaces.api.browser_workflow_routes.is_ssrf_target",
        return_value="Blocked internal hostname: sandbox",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            response = await client.delete(
                "/api/v1/browser-workflow/cache",
                params={"url": "http://sandbox/internal"},
            )

    assert response.status_code == 400
    assert response.json()["msg"] == "Blocked internal hostname: sandbox"
    service.invalidate_cache.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_override_browser_workflow_dependencies")
async def test_fetch_stream_rejects_unknown_mode(_override_browser_workflow_dependencies: MagicMock) -> None:
    service = _override_browser_workflow_dependencies

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v1/browser-workflow/fetch/stream",
            params={"url": "https://example.com/article", "mode": "bogus"},
        )

    assert response.status_code == 422
    assert response.json()["msg"] == "Validation error"
    service.fetch_with_progress.assert_not_called()
