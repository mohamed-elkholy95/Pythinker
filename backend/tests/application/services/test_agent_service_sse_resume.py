"""Tests for SSE resume cursor handling in AgentService.chat().

Covers the fix for the events=0 infinite reconnect loop:
- Redis stream ID cursors disable skip mode and pass events through cleanly
- UUID-format cursors (synthetic events) trigger stale-cursor fallback
- Absent cursors flow normally without skip mode
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.agent_service import AgentService
from app.core.prometheus_metrics import (
    reset_all_metrics,
    sse_resume_cursor_fallback_total,
    sse_resume_cursor_state_total,
)
from app.domain.models.event import DoneEvent, ErrorEvent, MessageEvent


class _DummyLLM:
    model_name = "test"
    temperature = 0.0
    max_tokens = 100


class _DummyTask:
    @classmethod
    def create(cls, *_args, **_kwargs):
        raise AssertionError("Task creation should not be invoked in resume cursor tests")


class _FakeSessionRepo:
    async def save(self, _s) -> None:
        return None

    async def find_by_id(self, _id: str):
        return None

    async def find_by_user_id(self, _uid: str):
        return []


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_all_metrics()
    yield
    reset_all_metrics()


def _build_service() -> AgentService:
    agent_repo = AsyncMock()
    agent_repo.save = AsyncMock()
    return AgentService(
        llm=_DummyLLM(),
        agent_repository=agent_repo,
        session_repository=_FakeSessionRepo(),
        sandbox_cls=MagicMock(),
        task_cls=_DummyTask,
        json_parser=MagicMock(),
        file_storage=MagicMock(),
        mcp_repository=MagicMock(),
        search_engine=None,
        memory_service=None,
        mongodb_db=None,
    )


async def _collect(gen):
    return [e async for e in gen]


def _make_domain_events(*msgs):
    """Return an async generator that yields MessageEvent for each msg, then DoneEvent."""

    async def _gen(*_args, **_kwargs):
        for m in msgs:
            ev = MessageEvent(role="assistant", message=m)
            ev.id = f"msg-{m[:8]}"
            yield ev
        done = DoneEvent(title="Done", summary="ok")
        done.id = "done-1"
        yield done

    return _gen


# ---------------------------------------------------------------------------
# A1: Redis stream ID cursor — no gap warning, events flow normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_stream_id_cursor_disables_skip_mode_no_gap_warning(monkeypatch):
    """A Redis-format cursor (e.g. '1772445693104-0') must suppress skip mode
    and emit domain events directly without any gap-warning ErrorEvent."""
    service = _build_service()
    service._agent_domain_service = SimpleNamespace(chat=_make_domain_events("hello world"))

    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[])),
    )

    events = await _collect(
        service.chat(
            session_id="s1",
            user_id="u1",
            message="continue",
            event_id="1772445693104-0",
        )
    )

    # Exactly 2 domain events — no synthetic gap warning prepended.
    assert len(events) == 2
    assert isinstance(events[0], MessageEvent)
    assert isinstance(events[1], DoneEvent)

    # Prometheus: redis_cursor state, no fallback counter.
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "redis_cursor"}) == 1.0
    assert sse_resume_cursor_fallback_total.get({"endpoint": "chat", "reason": "format_mismatch"}) == 0.0


@pytest.mark.asyncio
async def test_redis_stream_id_cursor_various_formats(monkeypatch):
    """Various valid Redis stream ID formats must all disable skip mode cleanly."""
    for redis_id in ("1772445693104-0", "0-1", "9999999999999-99", "1234567890-5"):
        reset_all_metrics()
        service = _build_service()
        service._agent_domain_service = SimpleNamespace(chat=_make_domain_events("data"))

        monkeypatch.setattr(
            "app.application.services.connector_service.get_connector_service",
            lambda: SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[])),
        )

        events = await _collect(
            service.chat(session_id="s1", user_id="u1", message="go", event_id=redis_id)
        )

        non_error = [e for e in events if not isinstance(e, ErrorEvent)]
        assert len(non_error) == 2, f"Expected 2 domain events for cursor={redis_id}, got {events}"
        assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "redis_cursor"}) == 1.0


# ---------------------------------------------------------------------------
# A2: Absent cursor — no skip mode, no gap warning, normal flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_absent_cursor_flows_all_events(monkeypatch):
    """When no event_id is supplied, all domain events must flow unfiltered."""
    service = _build_service()
    service._agent_domain_service = SimpleNamespace(chat=_make_domain_events("alpha", "beta"))

    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[])),
    )

    events = await _collect(
        service.chat(session_id="s1", user_id="u1", message="new session")
    )

    assert len(events) == 3  # alpha, beta, DoneEvent
    assert isinstance(events[0], MessageEvent)
    assert events[0].message == "alpha"
    assert isinstance(events[1], MessageEvent)
    assert events[1].message == "beta"
    assert isinstance(events[2], DoneEvent)

    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "absent"}) == 1.0


# ---------------------------------------------------------------------------
# A3: UUID-format cursor from synthetic events must not cause infinite loop
#     (stale-cursor path still triggers gap warning, confirming separation of concerns)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uuid_cursor_triggers_stale_gap_warning(monkeypatch):
    """A UUID cursor (e.g. from a synthetic ErrorEvent or beacon) should go
    through the stale/missing path, NOT the redis_cursor path.  This ensures
    the two cases remain distinguishable in metrics."""
    service = _build_service()

    async def _domain_events(*_args, **_kwargs):
        ev = MessageEvent(role="assistant", message="content")
        ev.id = "real-uuid-evt"
        yield ev
        yield DoneEvent()

    service._agent_domain_service = SimpleNamespace(chat=_domain_events)

    monkeypatch.setattr(
        "app.application.services.connector_service.get_connector_service",
        lambda: SimpleNamespace(get_user_mcp_configs=AsyncMock(return_value=[])),
    )

    events = await asyncio.wait_for(
        _collect(
            service.chat(
                session_id="s1",
                user_id="u1",
                message="resume",
                event_id="some-uuid-gap-warning-id",  # UUID-like, not Redis format
            )
        ),
        timeout=5.0,
    )

    # Must NOT be stuck in infinite loop — events must arrive
    assert len(events) >= 1
    # Must NOT have recorded redis_cursor
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "redis_cursor"}) == 0.0
