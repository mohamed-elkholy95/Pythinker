from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.services.agents.agent_task_factory import AgentTaskFactory


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
    session_repo.update_by_id = AsyncMock()

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
    # Atomic update_by_id replaces the old save() for task_id+status
    session_repo.update_by_id.assert_awaited_once_with(session.id, {"task_id": None})


@pytest.mark.asyncio
async def test_teardown_completed_session_does_not_cancel_task() -> None:
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        task_id="task-id",
        sandbox_id=None,
    )
    session_repo = AsyncMock()
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_by_id = AsyncMock()

    task = MagicMock()
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)

    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock()

    service = _build_service(session_repo, sandbox_cls, task_cls)

    await service._teardown_session_runtime(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)

    task.cancel.assert_not_called()


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
        "app.core.config.get_settings",
        return_value=SimpleNamespace(sandbox_lifecycle_mode="ephemeral"),
    ):
        await service._teardown_session_runtime(session.id)

    sandbox.destroy.assert_awaited_once()


@pytest.mark.asyncio
async def test_teardown_uses_force_destroy_when_sandbox_destroy_times_out() -> None:
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
    sandbox.destroy = AsyncMock(side_effect=TimeoutError)
    sandbox.force_destroy = AsyncMock(return_value=True)
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock(return_value=sandbox)

    service = _build_service(session_repo, sandbox_cls, task_cls)
    service._register_background_task = MagicMock()

    await service._teardown_session_runtime(session.id)

    sandbox.destroy.assert_awaited_once()
    sandbox.force_destroy.assert_awaited_once()
    service._register_background_task.assert_not_called()
    assert session.sandbox_id is None


# ---------------------------------------------------------------------------
# Task 3: Ownership contract for static on-demand sandboxes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_factory_static_no_pool_sets_sandbox_owned_true() -> None:
    """In static mode with pool disabled, ad-hoc created containers are session-owned."""
    session = Session(
        id="session-static-no-pool",
        user_id="user-1",
        agent_id="agent-1",
    )

    mock_sandbox = AsyncMock()
    mock_sandbox.id = "adhoc-sandbox-1"
    mock_sandbox.verify_browser_ready = AsyncMock(return_value=True)

    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=mock_sandbox)
    sandbox_cls.get = AsyncMock(return_value=None)  # No existing sandbox

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    mock_task = MagicMock()
    task_cls = MagicMock()
    task_cls.create = MagicMock(return_value=mock_task)

    factory = AgentTaskFactory(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
    )

    from app.core.config import get_settings

    real_settings = get_settings()
    real_settings.sandbox_lifecycle_mode = "static"
    real_settings.sandbox_pool_enabled = False
    real_settings.sandbox_address = None

    with patch("app.core.config.get_settings", return_value=real_settings):
        await factory.create_task(session)

    # Ad-hoc container in static mode with pool disabled → session-owned
    assert session.sandbox_owned is True
    assert session.sandbox_created_at is not None


@pytest.mark.asyncio
async def test_task_factory_static_address_sets_sandbox_unowned() -> None:
    """Static-address sandboxes (dev mode) are external/shared — never owned."""
    session = Session(
        id="session-static-addr",
        user_id="user-1",
        agent_id="agent-1",
    )

    mock_sandbox = AsyncMock()
    mock_sandbox.id = "dev-sandbox-localhost"
    mock_sandbox.verify_browser_ready = AsyncMock(return_value=True)

    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=mock_sandbox)
    sandbox_cls.get = AsyncMock(return_value=None)

    session_repo = AsyncMock()
    session_repo.save = AsyncMock()

    mock_task = MagicMock()
    task_cls = MagicMock()
    task_cls.create = MagicMock(return_value=mock_task)

    factory = AgentTaskFactory(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
    )

    from app.core.config import get_settings

    real_settings = get_settings()
    real_settings.sandbox_lifecycle_mode = "static"
    real_settings.sandbox_pool_enabled = False
    real_settings.sandbox_address = "sandbox:8082"

    with patch("app.core.config.get_settings", return_value=real_settings):
        await factory.create_task(session)

    # Static-address sandbox → external/shared, NOT session-owned
    assert session.sandbox_owned is False
    assert session.sandbox_created_at is None
