import asyncio
import inspect
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.domain.models.session import Session, SessionStatus


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 100


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in create_session tests")


class FakeSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, object] = {}

    async def save(self, session) -> None:
        self._sessions[session.id] = session

    async def find_by_id(self, session_id: str):
        return self._sessions.get(session_id)

    async def find_by_user_id(self, user_id: str):
        return [s for s in self._sessions.values() if getattr(s, "user_id", None) == user_id]

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.status = status


def _build_service() -> AgentService:
    agent_repo = AsyncMock()
    agent_repo.save = AsyncMock()
    session_repo = FakeSessionRepository()

    return AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=session_repo,
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
async def test_create_session_auto_stops_prior_session_with_bound_sandbox(monkeypatch):
    service = _build_service()
    stop_session_mock = AsyncMock()
    monkeypatch.setattr(service._agent_domain_service, "stop_session", stop_session_mock)

    stale_session = Session(
        id="stale-session",
        user_id="user-1",
        agent_id="agent-1",
        status=SessionStatus.COMPLETED,
        sandbox_id="sandbox-stale",
    )
    await service._session_repository.save(stale_session)

    await service.create_session(user_id="user-1", require_fresh_sandbox=False)

    stop_session_mock.assert_awaited_once_with("stale-session")


@pytest.mark.asyncio
async def test_create_session_returns_initializing_on_timeout(monkeypatch):
    signature = inspect.signature(AgentService.create_session)
    assert "require_fresh_sandbox" in signature.parameters
    assert "sandbox_wait_seconds" in signature.parameters

    service = _build_service()

    warm_started = asyncio.Event()
    warm_done = asyncio.Event()

    async def slow_warm(_session_id: str) -> None:
        warm_started.set()
        await asyncio.sleep(0.2)
        await service._session_repository.update_status(_session_id, SessionStatus.PENDING)
        warm_done.set()

    monkeypatch.setattr(service, "_warm_sandbox_for_session", slow_warm)

    session = await service.create_session(
        user_id="user-1",
        require_fresh_sandbox=True,
        sandbox_wait_seconds=0.05,
    )

    assert session.status == SessionStatus.INITIALIZING
    assert warm_started.is_set()

    await asyncio.wait_for(warm_done.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_create_session_returns_pending_when_warm_completes(monkeypatch):
    signature = inspect.signature(AgentService.create_session)
    assert "require_fresh_sandbox" in signature.parameters
    assert "sandbox_wait_seconds" in signature.parameters

    service = _build_service()

    async def fast_warm(_session_id: str) -> None:
        await service._session_repository.update_status(_session_id, SessionStatus.PENDING)

    monkeypatch.setattr(service, "_warm_sandbox_for_session", fast_warm)

    session = await service.create_session(
        user_id="user-1",
        require_fresh_sandbox=True,
        sandbox_wait_seconds=1.0,
    )

    assert session.status == SessionStatus.PENDING


@pytest.mark.asyncio
async def test_create_session_respects_max_wait_budget_when_request_timeout_is_too_large(monkeypatch):
    service = _build_service()
    service.MAX_CREATE_SESSION_WAIT_SECONDS = 0.05

    async def very_slow_warm(_session_id: str) -> None:
        await asyncio.sleep(0.4)
        await service._session_repository.update_status(_session_id, SessionStatus.PENDING)

    monkeypatch.setattr(service, "_warm_sandbox_for_session", very_slow_warm)

    started_at = time.perf_counter()
    session = await service.create_session(
        user_id="user-1",
        require_fresh_sandbox=True,
        sandbox_wait_seconds=10.0,
    )
    elapsed = time.perf_counter() - started_at

    assert session.status == SessionStatus.INITIALIZING
    assert elapsed < 0.2
