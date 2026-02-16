from unittest.mock import MagicMock

import pytest

from app.application.errors.exceptions import NotFoundError
from app.application.services.agent_service import AgentService


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 128


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in not-found tests")


class MissingSessionRepository:
    async def find_by_id_and_user_id(self, _session_id: str, _user_id: str):
        return None


class DummyAgentRepository:
    async def save(self, *_args, **_kwargs) -> None:
        return None


def _build_service() -> AgentService:
    return AgentService(
        llm=DummyLLM(),
        agent_repository=DummyAgentRepository(),
        session_repository=MissingSessionRepository(),
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
async def test_delete_session_raises_not_found_for_missing_session() -> None:
    service = _build_service()

    with pytest.raises(NotFoundError, match="Session not found"):
        await service.delete_session("missing-session", "user-1")


@pytest.mark.asyncio
async def test_stop_session_raises_not_found_for_missing_session() -> None:
    service = _build_service()

    with pytest.raises(NotFoundError, match="Session not found"):
        await service.stop_session("missing-session", "user-1")
