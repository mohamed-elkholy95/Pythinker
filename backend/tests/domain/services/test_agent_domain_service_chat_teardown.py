import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent, ErrorEvent, PlanningPhase, ProgressEvent, WaitEvent
from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService

_LOOP_TIME_PATCH = "app.domain.services.agent_domain_service.asyncio.get_event_loop"
_SLEEP_PATCH = "asyncio.sleep"


def _fast_loop_time():
    """Return a mock event loop whose .time() advances 20s per call,
    causing time-based polling loops to exit after one iteration."""
    _counter = {"t": 0.0}

    def _get_loop():
        loop = MagicMock()
        loop.time.side_effect = lambda: _counter.__setitem__("t", _counter["t"] + 2.0) or _counter["t"]
        return loop

    return _get_loop


def _build_service(
    session: Session, task: SimpleNamespace, *, relay: AsyncMock | None = None
) -> tuple[AgentDomainService, AsyncMock]:
    session_repo = AsyncMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=session)
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    session_repo.update_mode = AsyncMock()
    session_repo.update_unread_message_count = AsyncMock()
    session_repo.update_status = AsyncMock()

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
        task_output_relay=relay,
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


@pytest.mark.asyncio
async def test_chat_no_active_task_and_running_session_emits_error_and_tears_down() -> None:
    """An orphaned RUNNING session (stale > 180s) with no active task should emit
    an ErrorEvent and be torn down as CANCELLED."""
    relay = AsyncMock()
    relay.get_live_task_id = AsyncMock(return_value=None)

    task = None
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        # Stale session: updated > 180s ago → genuine orphan
        updated_at=datetime.now(UTC) - timedelta(seconds=240),
    )

    service, teardown = _build_service(session, task, relay=relay)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "interrupted" in events[0].error.lower()
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.CANCELLED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_SLEEP_PATCH, new_callable=AsyncMock)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
async def test_chat_no_active_task_recent_running_session_emits_done_not_cancel(
    mock_loop: MagicMock, mock_sleep: AsyncMock
) -> None:
    """A RUNNING session with no task but updated < 180s ago is likely a reconnect
    race — should emit ProgressEvent then DoneEvent instead of cancelling the session."""
    relay = AsyncMock()
    relay.get_live_task_id = AsyncMock(return_value=None)

    task = None
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        # Recent session: updated just now → reconnect race
        updated_at=datetime.now(UTC),
    )

    service, teardown = _build_service(session, task, relay=relay)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent)
    assert isinstance(events[1], DoneEvent)
    # Should tear down as COMPLETED (graceful), not CANCELLED
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_SLEEP_PATCH, new_callable=AsyncMock)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
async def test_chat_no_active_task_within_grace_period_emits_done_not_cancel(
    mock_loop: MagicMock, mock_sleep: AsyncMock
) -> None:
    """A RUNNING session at 150s (within 180s grace window, past old 30s threshold)
    should emit ProgressEvent then DoneEvent — the SSE reconnection grace period protects it."""
    relay = AsyncMock()
    relay.get_live_task_id = AsyncMock(return_value=None)

    task = None
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        # 150s: within 180s grace window — should NOT be treated as orphan
        updated_at=datetime.now(UTC) - timedelta(seconds=150),
    )

    service, teardown = _build_service(session, task, relay=relay)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent)
    assert isinstance(events[1], DoneEvent)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_SLEEP_PATCH, new_callable=AsyncMock)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
async def test_chat_no_active_task_recent_running_session_with_naive_updated_at_emits_done(
    mock_loop: MagicMock, mock_sleep: AsyncMock
) -> None:
    """Naive updated_at timestamps must not crash age arithmetic in reconnect races."""
    relay = AsyncMock()
    relay.get_live_task_id = AsyncMock(return_value=None)

    task = None
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        # Emulate legacy Mongo records serialized without timezone info
        updated_at=datetime.now(UTC).replace(tzinfo=None, microsecond=0),
    )

    service, teardown = _build_service(session, task, relay=relay)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent)
    assert isinstance(events[1], DoneEvent)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
async def test_chat_no_active_task_running_with_persisted_done_event_emits_done() -> None:
    """When status is stale RUNNING but a DoneEvent is already persisted, recover as COMPLETED."""
    task = None
    session = Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        events=[DoneEvent()],
    )

    service, teardown = _build_service(session, task)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
async def test_chat_cancellation_marks_session_cancelled() -> None:
    task = SimpleNamespace(
        id="task-id",
        output_stream=SimpleNamespace(get=AsyncMock()),
        done=False,
        cancel=MagicMock(),
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
    cancel_event = asyncio.Event()
    cancel_event.set()

    service, teardown = _build_service(session, task)
    events = [
        event
        async for event in service.chat(
            session_id=session.id,
            user_id=session.user_id,
            message=None,
            cancel_event=cancel_event,
        )
    ]

    assert events == []
    task.cancel.assert_called_once()
    teardown.assert_awaited_once_with(
        session.id,
        session=session,
        status=SessionStatus.CANCELLED,
        destroy_sandbox=False,
    )


@pytest.mark.asyncio
async def test_chat_done_emitted_when_task_completes_without_events() -> None:
    task = SimpleNamespace(
        id="task-id",
        output_stream=SimpleNamespace(get=AsyncMock(return_value=(None, None))),
        done=True,
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
async def test_chat_marks_cancelled_when_task_finishes_without_terminal_event_after_partial_events() -> None:
    progress_event = ProgressEvent(phase=PlanningPhase.ANALYZING, message="Working...", progress_percent=50)

    task = SimpleNamespace(
        id="task-id",
        done=False,
    )

    _call_count = 0

    async def _get_event(*args, **kwargs):
        nonlocal _call_count
        _call_count += 1
        if _call_count == 1:
            task.done = True
            return ("1-0", progress_event.model_dump_json())
        # Subsequent calls return None — stream exhausted (matches real Redis XREAD behavior)
        return (None, None)

    task.output_stream = SimpleNamespace(get=AsyncMock(side_effect=_get_event))

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

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent)
    assert isinstance(events[1], ErrorEvent)
    assert "interrupted" in events[1].error
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.CANCELLED, destroy_sandbox=False)
