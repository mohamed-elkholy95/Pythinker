"""Tests for AgentDomainService.stop_session teardown behavior."""

from unittest.mock import AsyncMock, MagicMock

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
    session_repo.save.assert_awaited_once_with(session)


@pytest.mark.asyncio
async def test_stop_session_skips_destroy_for_unowned_sandbox():
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
    assert session.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_stop_session_sets_completed_status_and_saves_session():
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

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

    assert session.status == SessionStatus.COMPLETED
    session_repo.save.assert_awaited_once_with(session)


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
    assert session.status == SessionStatus.COMPLETED
    session_repo.save.assert_awaited_once_with(session)
