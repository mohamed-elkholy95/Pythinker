import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.domain.models.session import Session


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 128


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in warmup cancellation tests")


class FakeSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def find_by_id_and_user_id(self, _session_id: str, _user_id: str):
        return self._session


def _build_service(session: Session) -> AgentService:
    return AgentService(
        llm=DummyLLM(),
        agent_repository=AsyncMock(),
        session_repository=FakeSessionRepository(session),
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


@pytest.mark.asyncio
async def test_cancel_sandbox_warmup_task_removes_and_cancels_task():
    session = Session(id="session-1", user_id="user-1", agent_id="agent-1")
    service = _build_service(session)

    task = asyncio.create_task(asyncio.sleep(60))
    service._register_sandbox_warmup_task(session.id, task)

    await service._cancel_sandbox_warmup_task(session.id)
    await asyncio.sleep(0)

    assert session.id not in service._sandbox_warm_tasks
    assert task.cancelled()


@pytest.mark.asyncio
async def test_stop_session_cancels_warmup_before_domain_stop():
    session = Session(id="session-2", user_id="user-2", agent_id="agent-2")
    service = _build_service(session)
    service._cancel_sandbox_warmup_task = AsyncMock()
    service._agent_domain_service.stop_session = AsyncMock()

    await service.stop_session("session-2", "user-2")

    service._cancel_sandbox_warmup_task.assert_awaited_once_with("session-2")
    service._agent_domain_service.stop_session.assert_awaited_once_with("session-2")


@pytest.mark.asyncio
async def test_warmup_cancelled_cleanly_when_stop_before_complete():
    """Stopping session while warmup in progress must cancel warmup and not orphan connections."""
    session = Session(id="session-warmup-cancel", user_id="user-1", agent_id="agent-1")
    service = _build_service(session)
    service._agent_domain_service.stop_session = AsyncMock()

    # Start a long-running warmup
    warmup_task = asyncio.create_task(asyncio.sleep(60))
    service._register_sandbox_warmup_task(session.id, warmup_task)

    # Stop before warmup completes
    await service.stop_session(session.id, "user-1")

    # Warmup must be cancelled
    assert warmup_task.cancelled()
    assert session.id not in service._sandbox_warm_tasks
