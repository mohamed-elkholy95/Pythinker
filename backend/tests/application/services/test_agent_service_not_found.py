from unittest.mock import AsyncMock as MockAsyncMock
from unittest.mock import MagicMock

import pytest

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
async def test_delete_session_is_idempotent_for_missing_session() -> None:
    """AgentService delegates delete_session to SessionLifecycleService."""
    service = _build_service()
    service._session_lifecycle_service.delete_session = MockAsyncMock()

    await service.delete_session("missing-session", "user-1")

    service._session_lifecycle_service.delete_session.assert_awaited_once_with("missing-session", "user-1")


@pytest.mark.asyncio
async def test_stop_session_is_idempotent_for_missing_session() -> None:
    """AgentService delegates stop_session to SessionLifecycleService."""
    service = _build_service()
    service._session_lifecycle_service.stop_session = MockAsyncMock()

    await service.stop_session("missing-session", "user-1")

    service._session_lifecycle_service.stop_session.assert_awaited_once_with("missing-session", "user-1")
