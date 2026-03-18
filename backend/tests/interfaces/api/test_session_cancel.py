"""Tests for the POST /sessions/{id}/cancel endpoint.

Verifies that the cancel endpoint delegates to AgentService.request_cancellation()
which sets the cooperative CancellationToken event, causing PlanActFlow._check_cancelled()
to raise CancelledError between steps.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.user import UserRole
from app.domain.services.flows.cancellation import CancellationSignal


def test_cancellation_signal_basic_lifecycle() -> None:
    """CancellationSignal cancel/reset round-trip."""
    signal = CancellationSignal()
    assert not signal.is_cancelled

    signal.cancel()
    assert signal.is_cancelled

    signal.reset()
    assert not signal.is_cancelled


def test_cancellation_signal_is_idempotent() -> None:
    """Calling cancel() multiple times is safe."""
    signal = CancellationSignal()
    signal.cancel()
    signal.cancel()
    assert signal.is_cancelled


@pytest.mark.asyncio
async def test_cancel_endpoint_calls_request_cancellation() -> None:
    """POST /sessions/{id}/cancel delegates to agent_service.request_cancellation()."""
    from app.interfaces.api.session_routes import cancel_session

    mock_user = MagicMock()
    mock_user.id = "test-user"
    mock_user.role = UserRole.USER

    mock_agent_service = MagicMock()
    mock_session_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(user_id="test-user")))

    result = await cancel_session(
        session_id="test-session-123",
        current_user=mock_user,
        agent_service=mock_agent_service,
        session_repo=mock_session_repo,
    )

    mock_agent_service.request_cancellation.assert_called_once_with("test-session-123")
    assert result["status"] == "cancelling"
    assert result["session_id"] == "test-session-123"


@pytest.mark.asyncio
async def test_cancel_endpoint_is_idempotent() -> None:
    """Calling cancel twice does not raise — request_cancellation is idempotent."""
    from app.interfaces.api.session_routes import cancel_session

    mock_user = MagicMock()
    mock_user.id = "test-user"
    mock_user.role = UserRole.USER
    mock_agent_service = MagicMock()
    mock_session_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(user_id="test-user")))

    await cancel_session("s1", current_user=mock_user, agent_service=mock_agent_service, session_repo=mock_session_repo)
    await cancel_session("s1", current_user=mock_user, agent_service=mock_agent_service, session_repo=mock_session_repo)

    assert mock_agent_service.request_cancellation.call_count == 2


@pytest.mark.asyncio
async def test_cancel_endpoint_returns_202_shape() -> None:
    """Response body has 'status' and 'session_id' fields."""
    from app.interfaces.api.session_routes import cancel_session

    mock_user = MagicMock()
    mock_user.id = "test-user"
    mock_user.role = UserRole.USER
    mock_agent_service = MagicMock()
    mock_session_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(user_id="test-user")))

    result = await cancel_session(
        "abc-123",
        current_user=mock_user,
        agent_service=mock_agent_service,
        session_repo=mock_session_repo,
    )

    assert isinstance(result, dict)
    assert "status" in result
    assert "session_id" in result
