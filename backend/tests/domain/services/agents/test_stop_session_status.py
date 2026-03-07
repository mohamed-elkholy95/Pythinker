"""Tests that stop_session tears down with CANCELLED, not COMPLETED."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.session import Session, SessionStatus
from app.domain.services.agents.agent_session_lifecycle import AgentSessionLifecycle


@pytest.fixture
def session_repository() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def lifecycle(session_repository: AsyncMock) -> AgentSessionLifecycle:
    sandbox_cls = MagicMock()
    task_cls = MagicMock()
    return AgentSessionLifecycle(
        session_repository=session_repository,
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
    )


@pytest.fixture
def mock_session() -> Session:
    session = MagicMock(spec=Session)
    session.id = "session-123"
    session.sandbox_id = None
    return session


@pytest.mark.asyncio
async def test_stop_session_calls_teardown_with_cancelled_status(
    lifecycle: AgentSessionLifecycle,
    session_repository: AsyncMock,
    mock_session: Session,
) -> None:
    """stop_session must use CANCELLED, not COMPLETED — it is an interruption."""
    session_repository.find_by_id.return_value = mock_session

    teardown_mock = AsyncMock()
    lifecycle._teardown_session_runtime = teardown_mock  # type: ignore[method-assign]

    await lifecycle.stop_session("session-123")

    teardown_mock.assert_awaited_once()
    _, kwargs = teardown_mock.call_args
    assert kwargs["status"] == SessionStatus.CANCELLED, (
        f"Expected CANCELLED but got {kwargs['status']!r}. "
        "stop_session is an interruption, not a natural completion."
    )


@pytest.mark.asyncio
async def test_stop_session_calls_teardown_with_destroy_sandbox_true(
    lifecycle: AgentSessionLifecycle,
    session_repository: AsyncMock,
    mock_session: Session,
) -> None:
    """stop_session must request sandbox destruction to prevent orphaned containers."""
    session_repository.find_by_id.return_value = mock_session

    teardown_mock = AsyncMock()
    lifecycle._teardown_session_runtime = teardown_mock  # type: ignore[method-assign]

    await lifecycle.stop_session("session-123")

    _, kwargs = teardown_mock.call_args
    assert kwargs["destroy_sandbox"] is True


@pytest.mark.asyncio
async def test_stop_session_returns_early_when_session_not_found(
    lifecycle: AgentSessionLifecycle,
    session_repository: AsyncMock,
) -> None:
    """stop_session must silently return when the session does not exist."""
    session_repository.find_by_id.return_value = None

    teardown_mock = AsyncMock()
    lifecycle._teardown_session_runtime = teardown_mock  # type: ignore[method-assign]

    # Should not raise
    await lifecycle.stop_session("nonexistent-session")

    teardown_mock.assert_not_awaited()
