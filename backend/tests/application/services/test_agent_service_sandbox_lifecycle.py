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

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Session | None:
        s = self._sessions.get(session_id)
        return s if s and s.user_id == user_id else None

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

    await service._warm_sandbox_for_session(session.id)

    assert session.sandbox_id == "existing-sandbox"
    created_sandbox.destroy.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_not_awaited()


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

    await service._warm_sandbox_for_session("missing-session")

    created_sandbox.destroy.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_not_awaited()


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

    await service._warm_sandbox_for_session(session.id)

    assert session_repository._sessions[session.id].sandbox_id == "bound-sandbox"
    assert session_repository.save_calls == 1
    created_sandbox.destroy.assert_not_awaited()
    created_sandbox.ensure_sandbox.assert_awaited_once()
    prewarm_browser.assert_awaited_once_with(created_sandbox, session.id)
    assert session_repository.status_updates[-1] == (session.id, SessionStatus.PENDING)


@pytest.mark.asyncio
async def test_warm_sandbox_skips_redundant_prewarm_for_pooled_sandbox(monkeypatch):
    session = Session(
        id="session-pooled-skip-prewarm",
        user_id="user-1",
        agent_id="agent-1",
    )
    session_repository = FakeSessionRepository([session])

    pooled_sandbox = _build_sandbox("pooled-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock()  # Should not be used when pool acquire succeeds

    service = _build_service(session_repository, sandbox_cls)

    fake_pool = SimpleNamespace(
        is_started=True,
        size=1,
        acquire=AsyncMock(return_value=pooled_sandbox),
    )

    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=True),
    )
    monkeypatch.setattr(
        "app.application.services.agent_service.get_sandbox_pool",
        AsyncMock(return_value=fake_pool),
    )

    await service._warm_sandbox_for_session(session.id)

    fake_pool.acquire.assert_awaited_once()
    sandbox_cls.create.assert_not_awaited()
    pooled_sandbox.ensure_sandbox.assert_awaited_once()
    assert session_repository.status_updates[-1] == (session.id, SessionStatus.PENDING)


@pytest.mark.asyncio
async def test_warm_sandbox_bypasses_pool_for_static_sandbox_addresses(monkeypatch):
    session = Session(
        id="session-static-addresses",
        user_id="user-1",
        agent_id="agent-1",
    )
    session_repository = FakeSessionRepository([session])

    created_sandbox = _build_sandbox("static-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    service = _build_service(session_repository, sandbox_cls)

    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=True, sandbox_address="sandbox,sandbox2"),
    )
    get_pool_mock = AsyncMock(side_effect=AssertionError("pool should be bypassed in static sandbox mode"))
    monkeypatch.setattr(
        "app.application.services.agent_service.get_sandbox_pool",
        get_pool_mock,
    )

    await service._warm_sandbox_for_session(session.id)

    get_pool_mock.assert_not_awaited()
    sandbox_cls.create.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_awaited_once()


@pytest.mark.asyncio
async def test_warm_sandbox_bypasses_pool_for_ephemeral_lifecycle_mode(monkeypatch):
    session = Session(
        id="session-ephemeral-lifecycle",
        user_id="user-1",
        agent_id="agent-1",
    )
    session_repository = FakeSessionRepository([session])

    created_sandbox = _build_sandbox("ephemeral-sandbox")
    sandbox_cls = MagicMock()
    sandbox_cls.create = AsyncMock(return_value=created_sandbox)

    service = _build_service(session_repository, sandbox_cls)

    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(sandbox_pool_enabled=True, sandbox_lifecycle_mode="ephemeral", sandbox_address=None),
    )
    get_pool_mock = AsyncMock(side_effect=AssertionError("pool should be bypassed for ephemeral lifecycle mode"))
    monkeypatch.setattr(
        "app.application.services.agent_service.get_sandbox_pool",
        get_pool_mock,
    )

    await service._warm_sandbox_for_session(session.id)

    get_pool_mock.assert_not_awaited()
    sandbox_cls.create.assert_awaited_once()
    created_sandbox.ensure_sandbox.assert_awaited_once()
    prewarm_browser.assert_awaited_once_with(created_sandbox, session.id)


@pytest.mark.asyncio
async def test_stop_session_double_stop_does_not_raise():
    """Double-stop on same session must complete without raising."""
    session = Session(
        id="session-double-stop",
        user_id="user-1",
        agent_id="agent-1",
        status=SessionStatus.RUNNING,
        sandbox_id="sb-1",
        sandbox_owned=True,
    )
    session_repository = FakeSessionRepository([session])
    sandbox_cls = MagicMock()

    service = _build_service(session_repository, sandbox_cls)
    service._cancel_sandbox_warmup_task = AsyncMock()
    service._agent_domain_service.stop_session = AsyncMock()

    await service.stop_session("session-double-stop", "user-1")
    await service.stop_session("session-double-stop", "user-1")

    # Second stop must not raise; idempotent at application layer
    assert service._agent_domain_service.stop_session.await_count == 2
