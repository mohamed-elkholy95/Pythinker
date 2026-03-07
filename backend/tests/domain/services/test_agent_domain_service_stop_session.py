"""Tests for AgentDomainService.stop_session teardown behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService


@pytest.mark.asyncio
async def test_stop_session_destroys_sandbox_and_clears_session_references():
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=True,
    )
    task = MagicMock()
    sandbox = AsyncMock()
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()
    session_repo.update_by_id = AsyncMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock(return_value=sandbox)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("session-id")

    task.cancel.assert_called_once()
    sandbox_cls.get.assert_awaited_once_with("sandbox-id")
    sandbox.destroy.assert_awaited_once()
    assert session.sandbox_id is None
    assert session.task_id is None
    assert session.sandbox_owned is False
    # update_by_id() atomically sets task_id+status, save() clears sandbox refs
    session_repo.update_by_id.assert_awaited_once()
    assert session_repo.save.await_count == 1


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_stop_session_skips_destroy_for_unowned_sandbox(mock_get_settings: MagicMock):
    mock_get_settings.return_value = SimpleNamespace(
        sandbox_lifecycle_mode="static",
        max_concurrent_agents=2,
        max_concurrent_executions=4,
    )
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id="shared-sandbox",
        sandbox_owned=False,
    )
    task = MagicMock()
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()
    session_repo.update_by_id = AsyncMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock()

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("session-id")

    task.cancel.assert_called_once()
    sandbox_cls.get.assert_not_awaited()
    assert session.sandbox_id is None
    assert session.task_id is None
    assert session.status == SessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_stop_session_sets_cancelled_status_and_saves_session():
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()
    session_repo.update_by_id = AsyncMock()

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("session-id")

    assert session.status == SessionStatus.CANCELLED
    # Atomic update_by_id replaces save() for task_id+status
    session_repo.update_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_session_handles_missing_task_gracefully():
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="missing-task-id",
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()
    session_repo.update_by_id = AsyncMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=None)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("session-id")

    task_cls.get.assert_called_once_with("missing-task-id")
    assert session.task_id is None
    assert session.status == SessionStatus.CANCELLED
    session_repo.update_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_session_is_idempotent_when_session_missing():
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=None)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("missing-session-id")

    session_repo.find_by_id.assert_awaited_once_with("missing-session-id")


@pytest.mark.asyncio
async def test_stop_session_double_stop_early_exits_second_call():
    """Second stop_session on already-stopped session must early-exit without re-destroying."""
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.COMPLETED,
        sandbox_id=None,
        sandbox_owned=False,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock()

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=sandbox_cls,
        task_cls=MagicMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )

    await service.stop_session("session-id")
    await service.stop_session("session-id")

    sandbox_cls.get.assert_not_awaited()
    session_repo.save.assert_not_awaited()
