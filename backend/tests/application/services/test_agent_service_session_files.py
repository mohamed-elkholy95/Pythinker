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


@pytest.mark.asyncio
async def test_persist_generated_artifact_uploads_and_tracks_file(tmp_path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    uploaded = FileInfo(
        file_id="local_admin/report.pdf",
        filename="report.pdf",
        file_path="",
        content_type="application/pdf",
        size=0,
        user_id="user-1",
    )
    session_repository = SimpleNamespace(
        find_by_id_and_user_id=AsyncMock(
            return_value=_make_session(session_id="s1", user_id="user-1", is_shared=False, files=[])
        ),
        get_file_by_path=AsyncMock(return_value=None),
        add_file=AsyncMock(),
        remove_file=AsyncMock(),
    )
    file_storage = MagicMock(upload_file=AsyncMock(return_value=uploaded), delete_file=AsyncMock(return_value=True))
    service = AgentService(
        llm=DummyLLM(),
        agent_repository=DummyAgentRepository(),
        session_repository=session_repository,
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=file_storage,
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )

    result = await service.persist_generated_artifact(
        session_id="s1",
        user_id="user-1",
        local_path=str(pdf_path),
        filename="report.pdf",
        content_type="application/pdf",
        virtual_path="/channel-deliveries/s1/report.pdf",
        metadata={"delivery_channel": "telegram"},
    )

    assert result is not None
    assert result.file_path == "/channel-deliveries/s1/report.pdf"
    file_storage.upload_file.assert_awaited_once()
    session_repository.add_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_generated_artifact_skips_unchanged_duplicate(tmp_path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_bytes = b"%PDF-1.4 test"
    pdf_path.write_bytes(pdf_bytes)
    existing = FileInfo(
        file_id="local_admin/report.pdf",
        filename="report.pdf",
        file_path="/channel-deliveries/s1/report.pdf",
        content_type="application/pdf",
        size=len(pdf_bytes),
        user_id="user-1",
        metadata={"content_md5": "30fc778fbe570b29a54647c6c18d9f55"},
    )

    session_repository = SimpleNamespace(
        find_by_id_and_user_id=AsyncMock(
            return_value=_make_session(session_id="s1", user_id="user-1", is_shared=False, files=[existing])
        ),
        get_file_by_path=AsyncMock(return_value=existing),
        add_file=AsyncMock(),
        remove_file=AsyncMock(),
    )
    file_storage = MagicMock(upload_file=AsyncMock(), delete_file=AsyncMock())
    service = AgentService(
        llm=DummyLLM(),
        agent_repository=DummyAgentRepository(),
        session_repository=session_repository,
        sandbox_cls=MagicMock(),
        task_cls=DummyTask,
        json_parser=MagicMock(),
        file_storage=file_storage,
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )

    result = await service.persist_generated_artifact(
        session_id="s1",
        user_id="user-1",
        local_path=str(pdf_path),
        filename="report.pdf",
        content_type="application/pdf",
        virtual_path="/channel-deliveries/s1/report.pdf",
    )

    assert result == existing
    file_storage.upload_file.assert_not_awaited()
    session_repository.add_file.assert_not_awaited()
