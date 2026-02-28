import asyncio
from types import SimpleNamespace
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
        raise AssertionError("Task creation should not be invoked in file view tests")


class DummyAgentRepository:
    async def save(self, *_args, **_kwargs) -> None:
        return None


def _build_service(*, session: Session, sandbox: object) -> AgentService:
    session_repository = SimpleNamespace(
        find_by_id_and_user_id=AsyncMock(return_value=session),
    )
    sandbox_cls = MagicMock()
    sandbox_cls.get = AsyncMock(return_value=sandbox)
    return AgentService(
        llm=DummyLLM(),
        agent_repository=DummyAgentRepository(),
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


@pytest.mark.asyncio
async def test_file_view_coalesces_concurrent_requests_for_same_file() -> None:
    session = Session(id="s1", user_id="u1", agent_id="a1", sandbox_id="sb-1")

    async def _file_read(_path: str):
        await asyncio.sleep(0.02)
        return SimpleNamespace(success=True, data={"content": "hello", "file": "/workspace/a.txt"}, message=None)

    sandbox = SimpleNamespace(file_read=AsyncMock(side_effect=_file_read))
    service = _build_service(session=session, sandbox=sandbox)

    results = await asyncio.gather(
        service.file_view("s1", "/workspace/a.txt", "u1"),
        service.file_view("s1", "/workspace/a.txt", "u1"),
        service.file_view("s1", "/workspace/a.txt", "u1"),
    )

    assert sandbox.file_read.await_count == 1
    assert [r.content for r in results] == ["hello", "hello", "hello"]
