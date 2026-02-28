from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.domain.models.file import FileInfo
from app.domain.models.session import Session


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 128


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in session file tests")


class DummyAgentRepository:
    async def save(self, *_args, **_kwargs) -> None:
        return None


def _build_service(session_repository: object) -> AgentService:
    return AgentService(
        llm=DummyLLM(),
        agent_repository=DummyAgentRepository(),
        session_repository=session_repository,
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


def _make_session(*, session_id: str, user_id: str, is_shared: bool, files: list[FileInfo]) -> Session:
    return Session(
        id=session_id,
        user_id=user_id,
        agent_id="agent-1",
        is_shared=is_shared,
        files=files,
    )


@pytest.mark.asyncio
async def test_get_session_files_returns_persisted_files() -> None:
    file_info = FileInfo(
        file_id="local_admin/report.md",
        filename="report.md",
        file_path="/workspace/s1/report.md",
        content_type="text/markdown",
        size=1234,
        user_id="user-1",
    )

    light_session = _make_session(session_id="s1", user_id="user-1", is_shared=False, files=[])
    full_session = _make_session(session_id="s1", user_id="user-1", is_shared=False, files=[file_info])

    session_repository = SimpleNamespace(
        find_by_id_and_user_id=AsyncMock(return_value=light_session),
        find_by_id_and_user_id_full=AsyncMock(return_value=full_session),
    )
    service = _build_service(session_repository)

    files = await service.get_session_files("s1", "user-1")

    assert [f.file_id for f in files] == ["local_admin/report.md"]


@pytest.mark.asyncio
async def test_get_shared_session_files_returns_persisted_files() -> None:
    file_info = FileInfo(
        file_id="local_admin/report.md",
        filename="report.md",
        file_path="/workspace/s1/report.md",
        content_type="text/markdown",
        size=1234,
        user_id="user-1",
    )

    light_shared_session = _make_session(session_id="s1", user_id="user-1", is_shared=True, files=[])
    full_shared_session = _make_session(session_id="s1", user_id="user-1", is_shared=True, files=[file_info])

    session_repository = SimpleNamespace(
        find_by_id=AsyncMock(return_value=light_shared_session),
        find_by_id_full=AsyncMock(return_value=full_shared_session),
    )
    service = _build_service(session_repository)

    files = await service.get_shared_session_files("s1")

    assert [f.file_id for f in files] == ["local_admin/report.md"]
