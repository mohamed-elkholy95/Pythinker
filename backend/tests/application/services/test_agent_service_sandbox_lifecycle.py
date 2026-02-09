from types import SimpleNamespace
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
        raise AssertionError("Task creation should not be invoked in sandbox lifecycle tests")


class FakeSessionRepository:
    def __init__(self, sessions: list[Session] | None = None) -> None:
        self._sessions: dict[str, Session] = {session.id: session for session in sessions or []}
        self.save_calls = 0
        self.status_updates: list[tuple[str, SessionStatus]] = []

    async def save(self, session: Session) -> None:
        self.save_calls += 1
        self._sessions[session.id] = session

    async def find_by_id(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        return [s for s in self._sessions.values() if s.user_id == user_id]

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.status_updates.append((session_id, status))
        session = self._sessions.get(session_id)
        if session:
            session.status = status


class MissingSessionRepository(FakeSessionRepository):
    async def find_by_id(self, session_id: str) -> Session | None:
        return None


def _build_service(session_repository: FakeSessionRepository, sandbox_cls: MagicMock) -> AgentService:
    agent_repo = AsyncMock()
    agent_repo.save = AsyncMock()

    return AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=session_repository,
        sandbox_cls=sandbox_cls,
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


def _build_sandbox(sandbox_id: str) -> MagicMock:
    sandbox = MagicMock()
    sandbox.id = sandbox_id
    sandbox.ensure_sandbox = AsyncMock()
    sandbox.destroy = AsyncMock(return_value=True)
    return sandbox


@pytest.mark.asyncio
async def test_warm_sandbox_destroys_new_sandbox_when_session_already_bound(monkeypatch):
    session = Session(
        id="session-already-bound",
        user_id="user-1",
        agent_id="agent-1",
        sandbox_id="existing-sandbox",
    )
    session_repository = FakeSessionRepository([session])

    created_sandbox = _build_sandbox("new-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    service = _build_service(session_repository, sandbox_cls)
    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=False),
    )
    prewarm_browser = AsyncMock()
    monkeypatch.setattr(service, "_prewarm_browser", prewarm_browser)

    await service._warm_sandbox_for_session(session.id)

    assert session.sandbox_id == "existing-sandbox"
    created_sandbox.destroy.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_not_awaited()
    prewarm_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_warm_sandbox_destroys_new_sandbox_when_session_missing(monkeypatch):
    session_repository = MissingSessionRepository()

    created_sandbox = _build_sandbox("orphaned-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    service = _build_service(session_repository, sandbox_cls)
    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=False),
    )
    prewarm_browser = AsyncMock()
    monkeypatch.setattr(service, "_prewarm_browser", prewarm_browser)

    await service._warm_sandbox_for_session("missing-session")

    created_sandbox.destroy.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_not_awaited()
    prewarm_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_warm_sandbox_saves_sandbox_id_when_binding_succeeds(monkeypatch):
    session = Session(
        id="session-bind-success",
        user_id="user-1",
        agent_id="agent-1",
    )
    session_repository = FakeSessionRepository([session])

    created_sandbox = _build_sandbox("bound-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    service = _build_service(session_repository, sandbox_cls)
    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=False),
    )
    prewarm_browser = AsyncMock()
    monkeypatch.setattr(service, "_prewarm_browser", prewarm_browser)

    await service._warm_sandbox_for_session(session.id)

    assert session_repository._sessions[session.id].sandbox_id == "bound-sandbox"
    assert session_repository.save_calls == 1
    created_sandbox.destroy.assert_not_awaited()
    created_sandbox.ensure_sandbox.assert_awaited_once()
    prewarm_browser.assert_awaited_once_with(created_sandbox, session.id)
    assert session_repository.status_updates[-1] == (session.id, SessionStatus.PENDING)
