import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.domain.models.event import ErrorEvent


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 100


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in latency guard tests")


class FakeSessionRepository:
    async def save(self, _session) -> None:
        return None

    async def find_by_id(self, _session_id: str):
        return None

    async def find_by_user_id(self, _user_id: str):
        return []


def _build_service() -> AgentService:
    agent_repo = AsyncMock()
    agent_repo.save = AsyncMock()

    return AgentService(
        llm=DummyLLM(),
        agent_repository=agent_repo,
        session_repository=FakeSessionRepository(),
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


async def _collect_events(generator):
    return [event async for event in generator]


@pytest.mark.asyncio
async def test_chat_timeout_path_emits_controlled_status_not_hang(monkeypatch):
    service = _build_service()
    service.CHAT_EVENT_TIMEOUT_SECONDS = 0.05

    async def _hanging_chat(*_args, **_kwargs):
        await asyncio.sleep(3600)
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_hanging_chat)

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )

    events = await asyncio.wait_for(
        _collect_events(
            service.chat(
                session_id="session-1",
                user_id="user-1",
                message="hello",
            )
        ),
        timeout=0.5,
    )

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].error_type == "timeout"
