"""Tests for session route utilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.interfaces.api.session_routes import (
    _safe_exc_text,
    get_screenshot_image,
    get_shared_screenshot_image,
    stop_session,
)


class _UnprintableError(Exception):
    def __str__(self) -> str:  # pragma: no cover - exercised via _safe_exc_text
        raise RuntimeError("stringification failed")


def test_safe_exc_text_returns_message():
    error = RuntimeError("connection dropped")
    assert _safe_exc_text(error) == "connection dropped"


def test_safe_exc_text_handles_unprintable_exception():
    message = _safe_exc_text(_UnprintableError())
    assert "_UnprintableError" in message


def test_safe_exc_text_truncates_long_messages():
    error = RuntimeError("x" * 400)
    assert len(_safe_exc_text(error)) == 240


@pytest.mark.asyncio
async def test_stop_session_calls_agent_service_with_user_id_and_returns_success():
    session_id = "session-123"
    current_user = SimpleNamespace(id="user-123")
    agent_service = SimpleNamespace(stop_session=AsyncMock())

    response = await stop_session(
        session_id=session_id,
        current_user=current_user,
        agent_service=agent_service,
    )

    agent_service.stop_session.assert_awaited_once_with(session_id, current_user.id)
    assert response.code == 0
    assert response.msg == "success"
    assert response.data is None


@pytest.mark.asyncio
async def test_get_screenshot_image_sets_immutable_cache_header():
    session_id = "session-1"
    screenshot_id = "screenshot-1"
    current_user = SimpleNamespace(id="user-1")
    agent_service = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    screenshot_query_service = SimpleNamespace(get_image_bytes=AsyncMock(return_value=b"jpeg-bytes"))

    response = await get_screenshot_image(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=False,
        current_user=current_user,
        agent_service=agent_service,
        screenshot_query_service=screenshot_query_service,
    )

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    screenshot_query_service.get_image_bytes.assert_awaited_once_with(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=False,
    )


@pytest.mark.asyncio
async def test_get_shared_screenshot_image_sets_immutable_cache_header():
    session_id = "shared-session-1"
    screenshot_id = "screenshot-2"
    agent_service = SimpleNamespace(get_shared_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    screenshot_query_service = SimpleNamespace(get_image_bytes=AsyncMock(return_value=b"jpeg-bytes"))

    response = await get_shared_screenshot_image(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=True,
        agent_service=agent_service,
        screenshot_query_service=screenshot_query_service,
    )

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    screenshot_query_service.get_image_bytes.assert_awaited_once_with(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=True,
    )
