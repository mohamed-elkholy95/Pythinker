from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.errors.exceptions import NotFoundError
from app.application.schemas.session import ShellViewResponse
from app.application.services.agent_service import AgentService
from app.domain.exceptions.base import InvalidStateException
from app.domain.models.session import Session
from app.domain.models.tool_result import ToolResult


class DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 128


class DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in shell_view tests")


class DummyAgentRepository:
    async def save(self, *_args, **_kwargs) -> None:
        return None


def _build_service(*, sandbox_result: ToolResult) -> AgentService:
    session = Session(id="s1", user_id="u1", agent_id="a1", sandbox_id="sb-1")
    session_repository = SimpleNamespace(
        find_by_id_and_user_id=AsyncMock(return_value=session),
    )
    sandbox = SimpleNamespace(view_shell=AsyncMock(return_value=sandbox_result))
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
async def test_shell_view_returns_empty_output_when_shell_session_missing() -> None:
    service = _build_service(
        sandbox_result=ToolResult.error(
            "Sandbox API error (HTTP 404): Session ID does not exist: 550e8400-e29b-41d4-a716-446655440000"
        ),
    )

    response = await service.shell_view("s1", "550e8400-e29b-41d4-a716-446655440000", "u1")

    assert response == ShellViewResponse(
        output="",
        session_id="550e8400-e29b-41d4-a716-446655440000",
        console=[],
    )


@pytest.mark.asyncio
async def test_shell_view_maps_other_sandbox_404_to_not_found() -> None:
    service = _build_service(
        sandbox_result=ToolResult.error("Sandbox API error (HTTP 404): endpoint not found"),
    )

    with pytest.raises(NotFoundError):
        await service.shell_view("s1", "550e8400-e29b-41d4-a716-446655440000", "u1")


@pytest.mark.asyncio
async def test_shell_view_maps_sandbox_409_to_invalid_state() -> None:
    service = _build_service(
        sandbox_result=ToolResult.error("Sandbox API error (HTTP 409): Session is not running"),
    )

    with pytest.raises(InvalidStateException):
        await service.shell_view("s1", "550e8400-e29b-41d4-a716-446655440000", "u1")
