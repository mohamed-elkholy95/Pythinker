"""Contract tests for liveness-based reconnect logic in AgentDomainService.chat().

Verifies the three reconnect paths:
1. get_liveness returns task_id → RedisStreamQueue polls task:output:<id>
2. No liveness + recent session (<180s) → ProgressEvent + 15s bounded poll
3. No liveness + stale session (>=180s) → ErrorEvent + CANCELLED
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent, ErrorEvent, PlanningPhase, ProgressEvent
from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_domain_service import AgentDomainService

_LIVENESS_PATCH = "app.domain.services.agent_domain_service.RedisStreamTask.get_liveness"
_QUEUE_PATCH = "app.domain.services.agent_domain_service.RedisStreamQueue"
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


def _build_service(session: Session) -> tuple[AgentDomainService, AsyncMock]:
    """Build an AgentDomainService with mocked dependencies and no active task."""
    session_repo = AsyncMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=session)
    session_repo.find_by_id = AsyncMock(return_value=session)
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    session_repo.update_mode = AsyncMock()
    session_repo.update_unread_message_count = AsyncMock()
    session_repo.update_status = AsyncMock()

    # task_cls.get returns None → no active task (triggers orphan/reconnect path)
    task_cls = MagicMock()
    task_cls.get = MagicMock(return_value=None)

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


def _running_session(*, updated_seconds_ago: float = 0) -> Session:
    """Create a RUNNING session with no task_id (reconnect scenario)."""
    return Session(
        id="session-id",
        user_id="user-id",
        agent_id="agent-id",
        status=SessionStatus.RUNNING,
        task_id=None,
        sandbox_id="sandbox-id",
        sandbox_owned=True,
        updated_at=datetime.now(UTC) - timedelta(seconds=updated_seconds_ago),
    )


# -------------------------------------------------------------------
# Path 1: Liveness key exists → poll RedisStreamQueue(task:output:<id>)
# -------------------------------------------------------------------


@pytest.mark.asyncio
@patch(_QUEUE_PATCH)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
@patch(_LIVENESS_PATCH, new_callable=AsyncMock)
async def test_liveness_found_constructs_correct_stream(
    mock_liveness: AsyncMock,
    mock_loop: MagicMock,
    mock_queue_cls: MagicMock,
) -> None:
    """When get_liveness returns a task_id, RedisStreamQueue is constructed
    with 'task:output:<task_id>' and polled for events."""
    mock_liveness.return_value = "live-task-42"

    # Simulate stream returning a DoneEvent on first poll
    done_json = DoneEvent().model_dump_json()
    mock_stream = AsyncMock()
    mock_stream.get = AsyncMock(return_value=("1-0", done_json))
    mock_queue_cls.return_value = mock_stream

    session = _running_session()
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    # Verify correct stream name
    mock_queue_cls.assert_called_with("task:output:live-task-42")
    # Verify DoneEvent was yielded
    assert any(isinstance(e, DoneEvent) for e in events)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_QUEUE_PATCH)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
@patch(_LIVENESS_PATCH, new_callable=AsyncMock)
async def test_liveness_found_error_event_marks_failed(
    mock_liveness: AsyncMock,
    mock_loop: MagicMock,
    mock_queue_cls: MagicMock,
) -> None:
    """When the live stream yields an ErrorEvent, terminal_status is FAILED."""
    mock_liveness.return_value = "live-task-err"

    error_json = ErrorEvent(error="something broke").model_dump_json()
    mock_stream = AsyncMock()
    mock_stream.get = AsyncMock(return_value=("1-0", error_json))
    mock_queue_cls.return_value = mock_stream

    session = _running_session()
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert any(isinstance(e, ErrorEvent) for e in events)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.FAILED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_QUEUE_PATCH)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
@patch(_LIVENESS_PATCH, new_callable=AsyncMock)
async def test_liveness_expires_mid_poll_emits_done(
    mock_liveness: AsyncMock,
    mock_loop: MagicMock,
    mock_queue_cls: MagicMock,
) -> None:
    """When the liveness key expires during polling (no events, get_liveness returns None),
    a DoneEvent is emitted and terminal_status is COMPLETED."""
    # First call: liveness exists; subsequent calls (re-check): gone
    mock_liveness.side_effect = ["live-task-exp", None]

    mock_stream = AsyncMock()
    # No event data (empty poll)
    mock_stream.get = AsyncMock(return_value=(None, None))
    mock_queue_cls.return_value = mock_stream

    session = _running_session()
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert any(isinstance(e, DoneEvent) for e in events)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


# -------------------------------------------------------------------
# Path 2: No liveness + recent session → ProgressEvent + bounded poll
# -------------------------------------------------------------------


@pytest.mark.asyncio
@patch(_SLEEP_PATCH, new_callable=AsyncMock)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
@patch(_LIVENESS_PATCH, new_callable=AsyncMock, return_value=None)
async def test_no_liveness_recent_session_emits_progress_then_done(
    mock_liveness: AsyncMock,
    mock_loop: MagicMock,
    mock_sleep: AsyncMock,
) -> None:
    """When no liveness key and session <180s, first event should be ProgressEvent
    (EXECUTING_SETUP) and last event should be DoneEvent after bounded polling."""
    session = _running_session(updated_seconds_ago=10)
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 2
    assert isinstance(events[0], ProgressEvent)
    assert events[0].phase == PlanningPhase.EXECUTING_SETUP
    assert isinstance(events[1], DoneEvent)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


@pytest.mark.asyncio
@patch(_QUEUE_PATCH)
@patch(_SLEEP_PATCH, new_callable=AsyncMock)
@patch(_LOOP_TIME_PATCH, side_effect=_fast_loop_time())
@patch(_LIVENESS_PATCH, new_callable=AsyncMock)
async def test_no_liveness_then_late_liveness_switches_to_stream(
    mock_liveness: AsyncMock,
    mock_loop: MagicMock,
    mock_sleep: AsyncMock,
    mock_queue_cls: MagicMock,
) -> None:
    """When no liveness initially but appears during bounded polling,
    the code switches to stream polling."""
    # First call (initial check) returns None, second call (bounded poll) returns task_id
    mock_liveness.side_effect = [None, "late-task-99", None]

    done_json = DoneEvent().model_dump_json()
    mock_stream = AsyncMock()
    mock_stream.get = AsyncMock(return_value=("1-0", done_json))
    mock_queue_cls.return_value = mock_stream

    session = _running_session(updated_seconds_ago=5)
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    # First event: ProgressEvent from bounded polling entry
    assert isinstance(events[0], ProgressEvent)
    # Stream constructed with late task ID
    mock_queue_cls.assert_called_with("task:output:late-task-99")
    # DoneEvent from stream
    assert any(isinstance(e, DoneEvent) for e in events)
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.COMPLETED, destroy_sandbox=False)


# -------------------------------------------------------------------
# Path 3: No liveness + stale session (>=180s) → ErrorEvent + CANCELLED
# -------------------------------------------------------------------


@pytest.mark.asyncio
@patch(_LIVENESS_PATCH, new_callable=AsyncMock, return_value=None)
async def test_no_liveness_stale_session_emits_error_cancelled(
    mock_liveness: AsyncMock,
) -> None:
    """Stale orphan (>180s, no liveness) should emit ErrorEvent and cancel."""
    session = _running_session(updated_seconds_ago=300)
    service, teardown = _build_service(session)
    events = [event async for event in service.chat(session_id=session.id, user_id=session.user_id, message=None)]

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "interrupted" in events[0].error.lower()
    teardown.assert_awaited_once_with(session.id, status=SessionStatus.CANCELLED, destroy_sandbox=False)
