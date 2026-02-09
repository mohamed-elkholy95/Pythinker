"""Tests for session route utilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.interfaces.api.session_routes import _safe_exc_text, stop_session


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
