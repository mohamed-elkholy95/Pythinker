from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import DoneEvent, WaitEvent
from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService


def _build_service(session: Session, task: SimpleNamespace) -> tuple[AgentDomainService, AsyncMock]:
    session_repo = AsyncMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=session)
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    session_repo.update_mode = AsyncMock()
    session_repo.update_unread_message_count = AsyncMock()

    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=task)

    service = AgentDomainService(
        agent_repository=AsyncMock(),
        session_repository=session_repo,
        llm=MagicMock(),
        sandbox_cls=MagicMock(),
        task_cls=task_cls,
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=AsyncMock(),
    )
    teardown = AsyncMock()
    service._teardown_session_runtime = teardown
    return service, teardown


@pytest.mark.asyncio
async def test_chat_done_event_triggers_runtime_teardown() -> None:
    done_event = DoneEvent()
    task = SimpleNamespace(
        id="task-id",
        output_stream=SimpleNamespace(get=AsyncMock(return_value=("1-0", done_event.model_dump_json()))),
        done=False,
    )
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=True,
    )

    service, teardown = _build_service(session, task)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
async def test_chat_wait_event_does_not_trigger_runtime_teardown() -> None:
    wait_event = WaitEvent()
    task = SimpleNamespace(
        id="task-id",
        output_stream=SimpleNamespace(get=AsyncMock(return_value=("1-0", wait_event.model_dump_json()))),
        done=False,
    )
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id="task-id",
        sandbox_id="sandbox-id",
        sandbox_owned=True,
    )

    service, teardown = _build_service(session, task)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 1
    assert isinstance(events[0], WaitEvent)
    teardown.assert_not_awaited()
