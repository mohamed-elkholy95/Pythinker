import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.core.prometheus_metrics import (
    reset_all_metrics,
    sse_resume_cursor_fallback_total,
    sse_resume_cursor_state_total,
)
from app.domain.models.event import DoneEvent, ErrorEvent, MessageEvent, PlanningPhase, ProgressEvent


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


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


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
    service.CHAT_EVENT_HARD_TIMEOUT_SECONDS = 0.15

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
                message="please summarize the architecture choices",
            )
        ),
        timeout=0.5,
    )

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].error_type == "timeout"


@pytest.mark.asyncio
async def test_chat_soft_timeout_does_not_abort_slow_stream(monkeypatch):
    service = _build_service()
    service.CHAT_EVENT_TIMEOUT_SECONDS = 0.05
    service.CHAT_EVENT_HARD_TIMEOUT_SECONDS = 0.5

    async def _slow_then_done_chat(*_args, **_kwargs):
        await asyncio.sleep(0.12)
        yield DoneEvent()

    service._agent_domain_service = SimpleNamespace(chat=_slow_then_done_chat)

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
                message="run a long operation and report back",
            )
        ),
        timeout=1.0,
    )

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)


@pytest.mark.asyncio
async def test_chat_emits_waiting_progress_beacon_during_long_idle(monkeypatch):
    service = _build_service()
    service.CHAT_EVENT_TIMEOUT_SECONDS = 2.0
    service.CHAT_EVENT_HARD_TIMEOUT_SECONDS = 3.0
    service.CHAT_WAIT_BEACON_INTERVAL_SECONDS = 0.05

    async def _slow_then_done_chat(*_args, **_kwargs):
        await asyncio.sleep(1.2)
        yield DoneEvent()

    service._agent_domain_service = SimpleNamespace(chat=_slow_then_done_chat)

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
                message="run a long operation and report back",
            )
        ),
        timeout=3.0,
    )

    waiting_events = [event for event in events if isinstance(event, ProgressEvent)]
    assert waiting_events, "expected at least one waiting progress beacon before completion"
    assert all(event.phase == PlanningPhase.WAITING for event in waiting_events)
    assert all(event.wait_stage == "execution_wait" for event in waiting_events)
    assert all(event.wait_elapsed_seconds is not None for event in waiting_events)
    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_chat_waits_for_active_sandbox_warmup_lock(monkeypatch):
    service = _build_service()
    service.CHAT_WARMUP_WAIT_SECONDS = 0.2

    call_times: list[float] = []

    async def _chat_impl(*_args, **_kwargs):
        call_times.append(time.perf_counter())
        yield ErrorEvent(error="ok", error_type="test")

    service._agent_domain_service = SimpleNamespace(chat=_chat_impl)

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )

    lock = asyncio.Lock()
    await lock.acquire()
    service._sandbox_warm_locks["session-1"] = lock

    start = time.perf_counter()

    async def _release_lock() -> None:
        await asyncio.sleep(0.05)
        lock.release()

    releaser = asyncio.create_task(_release_lock())
    try:
        events = await asyncio.wait_for(
            _collect_events(
                service.chat(
                    session_id="session-1",
                    user_id="user-1",
                    message="please explain token budget behavior",
                )
            ),
            timeout=1.0,
        )
    finally:
        await releaser

    assert len(events) == 1
    assert call_times, "domain chat was not called"
    assert call_times[0] - start >= 0.045


@pytest.mark.asyncio
async def test_chat_forwards_user_skill_auto_trigger_policy(monkeypatch):
    service = _build_service()
    captured_kwargs: dict[str, object] = {}

    async def _chat_impl(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        yield ErrorEvent(error="ok", error_type="test")

    service._agent_domain_service = SimpleNamespace(chat=_chat_impl)
    service._settings_service = SimpleNamespace(get_skill_auto_trigger_enabled=AsyncMock(return_value=True))

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )
    monkeypatch.setattr(
        "app.application.services.agent_service.get_settings",
        lambda: SimpleNamespace(skill_auto_trigger_enabled=False),
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message="please explain this design",
        )
    )

    assert len(events) == 1
    assert captured_kwargs["auto_trigger_enabled"] is True


@pytest.mark.asyncio
async def test_chat_bypasses_full_initialization_for_greeting(monkeypatch):
    service = _build_service()

    session_repo = MagicMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=SimpleNamespace(id="session-1"))
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    service._session_repository = session_repo

    service._wait_for_sandbox_warmup_if_needed = AsyncMock()

    async def _domain_chat_should_not_run(*_args, **_kwargs):
        raise AssertionError("domain chat should not be called for greeting bypass")
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_domain_chat_should_not_run)

    def _connector_should_not_be_called():
        raise AssertionError("connector service should not be called for greeting bypass")

    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        _connector_should_not_be_called,
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message="hello",
        )
    )

    assert len(events) == 3
    assert isinstance(events[0], MessageEvent)
    assert events[0].role == "user"
    assert events[0].message == "hello"
    assert isinstance(events[1], MessageEvent)
    assert events[1].role == "assistant"
    assert isinstance(events[2], DoneEvent)

    service._wait_for_sandbox_warmup_if_needed.assert_not_awaited()
    session_repo.update_latest_message.assert_awaited_once()
    assert session_repo.add_event.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_fragment"),
    [
        ("who created you?", "Pythinker Team and Mohamed Elkholy"),
        ("what model are you?", "exact backend model can vary by configuration"),
    ],
)
async def test_chat_bypasses_full_initialization_for_identity_queries(
    monkeypatch,
    message: str,
    expected_fragment: str,
):
    service = _build_service()

    session_repo = MagicMock()
    session_repo.find_by_id_and_user_id = AsyncMock(return_value=SimpleNamespace(id="session-1"))
    session_repo.update_latest_message = AsyncMock()
    session_repo.add_event = AsyncMock()
    service._session_repository = session_repo

    service._wait_for_sandbox_warmup_if_needed = AsyncMock()

    async def _domain_chat_should_not_run(*_args, **_kwargs):
        raise AssertionError("domain chat should not be called for direct identity bypass")
        if False:  # pragma: no cover
            yield None

    service._agent_domain_service = SimpleNamespace(chat=_domain_chat_should_not_run)

    def _connector_should_not_be_called():
        raise AssertionError("connector service should not be called for direct identity bypass")

    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        _connector_should_not_be_called,
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message=message,
        )
    )

    assert len(events) == 3
    assert isinstance(events[0], MessageEvent)
    assert events[0].role == "user"
    assert events[0].message == message
    assert isinstance(events[1], MessageEvent)
    assert events[1].role == "assistant"
    assert expected_fragment in events[1].message
    assert isinstance(events[2], DoneEvent)

    service._wait_for_sandbox_warmup_if_needed.assert_not_awaited()
    session_repo.update_latest_message.assert_awaited_once()
    assert session_repo.add_event.await_count == 3


@pytest.mark.asyncio
async def test_chat_resumption_emits_idless_events_instead_of_skipping_forever(monkeypatch):
    service = _build_service()

    async def _domain_chat_idless(*_args, **_kwargs):
        message_event = MessageEvent(role="assistant", message="quick response")
        message_event.id = ""
        done_event = DoneEvent(title="Done", summary="Completed")
        done_event.id = ""
        yield message_event
        yield done_event

    service._agent_domain_service = SimpleNamespace(chat=_domain_chat_idless)

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message="please explain architecture summary",
            event_id="already-seen-event-id",
        )
    )

    assert len(events) == 3
    assert isinstance(events[0], ErrorEvent)
    assert events[0].error_code == "stream_gap_detected"
    assert events[0].details and events[0].details.get("reason") == "missing_event_id"
    assert isinstance(events[1], MessageEvent)
    assert events[1].message == "quick response"
    assert isinstance(events[2], DoneEvent)
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "stale"}) == 1.0
    assert sse_resume_cursor_fallback_total.get({"endpoint": "chat", "reason": "missing_event_id"}) == 1.0


@pytest.mark.asyncio
async def test_chat_resumption_disables_skip_mode_when_cursor_is_stale(monkeypatch):
    service = _build_service()
    service.CHAT_RESUME_MAX_SKIPPED_EVENTS = 2
    service.CHAT_RESUME_MAX_SKIP_SECONDS = 60.0

    async def _domain_chat_with_newer_events(*_args, **_kwargs):
        first = MessageEvent(role="assistant", message="first event")
        first.id = "evt-new-1"
        second = MessageEvent(role="assistant", message="second event")
        second.id = "evt-new-2"
        third = MessageEvent(role="assistant", message="third event")
        third.id = "evt-new-3"
        done = DoneEvent(title="Done", summary="Completed")
        done.id = "evt-new-4"
        yield first
        yield second
        yield third
        yield done

    service._agent_domain_service = SimpleNamespace(chat=_domain_chat_with_newer_events)

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message="continue with latest events",
            event_id="stale-resume-cursor",
        )
    )

    # First event is skipped while searching for stale cursor. Once threshold is hit,
    # service emits a gap warning and resumes from the current event.
    assert len(events) == 4
    assert isinstance(events[0], ErrorEvent)
    assert events[0].error_code == "stream_gap_detected"
    assert events[0].details and events[0].details.get("reason") == "stale_cursor"
    assert isinstance(events[1], MessageEvent)
    assert events[1].message == "second event"
    assert isinstance(events[2], MessageEvent)
    assert events[2].message == "third event"
    assert isinstance(events[3], DoneEvent)
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "stale"}) == 1.0
    assert sse_resume_cursor_fallback_total.get({"endpoint": "chat", "reason": "stale_cursor"}) == 1.0


@pytest.mark.asyncio
async def test_chat_resumption_emits_gap_when_cursor_format_mismatches(monkeypatch):
    service = _build_service()

    async def _domain_chat_with_events(*_args, **_kwargs):
        first = MessageEvent(role="assistant", message="first event")
        first.id = "evt-1"
        done = DoneEvent(title="Done", summary="Completed")
        done.id = "evt-2"
        yield first
        yield done

    service._agent_domain_service = SimpleNamespace(chat=_domain_chat_with_events)

    fake_connector_service = SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: fake_connector_service,
    )

    events = await _collect_events(
        service.chat(
            session_id="session-1",
            user_id="user-1",
            message="resume from header cursor",
            event_id="1771867510458-0",
        )
    )

    assert len(events) == 3
    assert isinstance(events[0], ErrorEvent)
    assert events[0].error_code == "stream_gap_detected"
    assert events[0].details and events[0].details.get("reason") == "format_mismatch"
    assert isinstance(events[1], MessageEvent)
    assert events[1].message == "first event"
    assert isinstance(events[2], DoneEvent)
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "format_mismatch"}) == 1.0
    assert sse_resume_cursor_fallback_total.get({"endpoint": "chat", "reason": "format_mismatch"}) == 1.0
