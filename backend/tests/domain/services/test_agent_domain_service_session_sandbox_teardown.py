from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import Session
from app.domain.services.agent_domain_service import AgentDomainService


def _build_service(session_repo: AsyncMock, sandbox_cls: MagicMock, task_cls: MagicMock) -> AgentDomainService:
    return AgentDomainService(
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


@pytest.mark.asyncio
async def test_teardown_session_runtime_is_idempotent_and_clears_references() -> None:
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=True,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

    task = MagicMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)

    sandbox = AsyncMock()
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock(return_value=sandbox)

    service = _build_service(session_repo, sandbox_cls, task_cls)

    await service._teardown_session_runtime(session.id)
    await service._teardown_session_runtime(session.id)

    sandbox.destroy.assert_awaited_once()
    task.cancel.assert_called_once()
    assert session.sandbox_id is None
    assert session.task_id is None
    assert session.sandbox_owned is False


@pytest.mark.asyncio
async def test_teardown_without_destroy_keeps_sandbox_reference() -> None:
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=True,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

    task = MagicMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)

    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock()

    service = _build_service(session_repo, sandbox_cls, task_cls)

    await service._teardown_session_runtime(session.id, destroy_sandbox=False)

    task.cancel.assert_called_once()
    sandbox_cls.get.assert_not_awaited()
    assert session.task_id is None
    assert session.sandbox_id == "sandbox-id"
    assert session.sandbox_owned is True
    session_repo.save.assert_awaited_once_with(session)


@pytest.mark.asyncio
async def test_teardown_legacy_session_destroys_sandbox_when_global_mode_is_ephemeral() -> None:
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=False,
        sandbox_lifecycle_mode=None,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.save = AsyncMock()

    task = MagicMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)

    sandbox = AsyncMock()
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock(return_value=sandbox)

    service = _build_service(session_repo, sandbox_cls, task_cls)

    with patch(
        "app.domain.services.agent_domain_service.get_settings",
        return_value=SimpleNamespace(sandbox_lifecycle_mode="ephemeral"),
    ):
        await service._teardown_session_runtime(session.id)

    sandbox.destroy.assert_awaited_once()
