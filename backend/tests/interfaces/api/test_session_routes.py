"""Tests for session route utilities."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent, PlanningPhase, ProgressEvent
from app.interfaces.api.session_routes import (
    _cancel_pending_disconnect_cancellation,
    _safe_exc_text,
    _schedule_disconnect_cancellation,
    chat,
    get_screenshot_image,
    get_shared_screenshot_image,
    stop_session,
)
from app.interfaces.schemas.session import ChatRequest, FollowUpContext


class _UnprintableError(Exception):
    def __str__(self) -> str:  # pragma: no cover - exercised via _safe_exc_text
        raise RuntimeError("stringification failed")


def test_safe_exc_text_returns_message():
    error = RuntimeError("connection dropped")
    assert _safe_exc_text(error) == "connection dropped"


def test_safe_exc_text_handles_unprintable_exception():
    message = _safe_exc_text(_UnprintableError())
    assert "_UnprintableError" in message


def test_safe_exc_text_truncates_long_messages():
    error = RuntimeError("x" * 400)
    assert len(_safe_exc_text(error)) == 240


@pytest.mark.asyncio
async def test_stop_session_calls_agent_service_with_user_id_and_returns_success():
    session_id = "session-123"
    current_user = SimpleNamespace(id="user-123")
    agent_service = SimpleNamespace(stop_session=AsyncMock())

    response = await stop_session(
        session_id=session_id,
        current_user=current_user,
        agent_service=agent_service,
    )

    agent_service.stop_session.assert_awaited_once_with(session_id, current_user.id)
    assert response.code == 0
    assert response.msg == "success"
    assert response.data is None


@pytest.mark.asyncio
async def test_get_screenshot_image_sets_immutable_cache_header():
    session_id = "session-1"
    screenshot_id = "screenshot-1"
    current_user = SimpleNamespace(id="user-1")
    agent_service = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    screenshot_query_service = SimpleNamespace(get_image_bytes=AsyncMock(return_value=b"jpeg-bytes"))

    response = await get_screenshot_image(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=False,
        current_user=current_user,
        agent_service=agent_service,
        screenshot_query_service=screenshot_query_service,
    )

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    screenshot_query_service.get_image_bytes.assert_awaited_once_with(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=False,
    )


@pytest.mark.asyncio
async def test_get_shared_screenshot_image_sets_immutable_cache_header():
    session_id = "shared-session-1"
    screenshot_id = "screenshot-2"
    agent_service = SimpleNamespace(get_shared_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    screenshot_query_service = SimpleNamespace(get_image_bytes=AsyncMock(return_value=b"jpeg-bytes"))

    response = await get_shared_screenshot_image(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=True,
        agent_service=agent_service,
        screenshot_query_service=screenshot_query_service,
    )

    assert response.status_code == 200
    assert response.media_type == "image/jpeg"
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    screenshot_query_service.get_image_bytes.assert_awaited_once_with(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=True,
    )


# ---------------------------------------------------------------------------
# chat() endpoint tests - completed-session reentry & SSE payload schemas
# ---------------------------------------------------------------------------


def _make_completed_session(session_id: str = "sess-1", title: str = "My Task") -> SimpleNamespace:
    """Return a minimal session object that looks completed."""
    return SimpleNamespace(id=session_id, status="completed", title=title)


def _make_http_request() -> MagicMock:
    """Return a mock starlette Request with is_disconnected."""
    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)
    return req


async def _collect_sse_events(response) -> list[dict]:
    """Drain an EventSourceResponse and return parsed SSE frames.

    EventSourceResponse wraps an async generator.  We iterate the
    generator attribute directly to collect ServerSentEvent objects.
    """
    events: list[dict] = []
    # The response body_iterator is the async generator
    async for sse in response.body_iterator:
        # sse is a ServerSentEvent — extract event name + data
        data = None
        if sse.data:
            data = json.loads(sse.data) if isinstance(sse.data, str) else sse.data
        events.append({"event": sse.event, "data": data})
    return events


@pytest.mark.asyncio
async def test_chat_completed_session_no_input_returns_done_event():
    """Completed session + empty request → schema-compliant 'done' SSE event."""
    session_id = "sess-done"
    session = _make_completed_session(session_id, title="Finished task")
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        chat=AsyncMock(),  # Should NOT be called
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest()  # No message, no attachments, no follow_up

    response = await chat(
        session_id=session_id,
        request=request,
        http_request=_make_http_request(),
        current_user=current_user,
        agent_service=agent_service,
    )

    assert response.headers["X-Pythinker-SSE-Protocol-Version"] == "2"
    assert response.headers["X-Pythinker-SSE-Retry-Max-Attempts"] == "7"
    assert response.headers["X-Pythinker-SSE-Retry-Base-Delay-Ms"] == "1000"
    assert response.headers["X-Pythinker-SSE-Retry-Max-Delay-Ms"] == "45000"
    assert response.headers["X-Pythinker-SSE-Retry-Jitter-Ratio"] == "0.25"

    events = await _collect_sse_events(response)

    # Must emit exactly one 'done' event
    assert len(events) == 1
    assert events[0]["event"] == "done"
    # Payload must include standard SSE data fields (event_id, timestamp)
    assert "event_id" in events[0]["data"]
    assert "timestamp" in events[0]["data"]

    # agent_service.chat must NOT have been invoked
    agent_service.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_completed_session_with_message_proceeds_to_agent_chat():
    """Completed session + fresh message → passes through to agent_service.chat()."""
    session_id = "sess-reactivate"
    session = _make_completed_session(session_id)

    # Simulate agent_service.chat yielding a DoneEvent
    async def fake_chat(**_kwargs):
        yield DoneEvent(title="Reactivated")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="Follow-up question")

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(feature_sse_v2=False)
        response = await chat(
            session_id=session_id,
            request=request,
            http_request=_make_http_request(),
            current_user=current_user,
            agent_service=agent_service,
        )

    events = await _collect_sse_events(response)

    # Should have at least the instant ack ProgressEvent + the DoneEvent from agent
    event_names = [e["event"] for e in events]
    assert "progress" in event_names, "Expected instant-ack progress event"
    assert "done" in event_names, "Expected done event from agent_service.chat()"


@pytest.mark.asyncio
async def test_chat_completed_session_with_follow_up_proceeds_to_agent_chat():
    """Completed session + follow_up context → passes through to agent_service.chat()."""
    session_id = "sess-followup"
    session = _make_completed_session(session_id)

    async def fake_chat(**_kwargs):
        yield DoneEvent(title="Follow-up done")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    follow_up = FollowUpContext(
        selected_suggestion="Tell me more about X",
        anchor_event_id="evt-123",
        source="suggestion_click",
    )
    request = ChatRequest(follow_up=follow_up)

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(feature_sse_v2=False)
        response = await chat(
            session_id=session_id,
            request=request,
            http_request=_make_http_request(),
            current_user=current_user,
            agent_service=agent_service,
        )

    events = await _collect_sse_events(response)
    event_names = [e["event"] for e in events]
    assert "done" in event_names, "Follow-up should reach agent_service.chat()"


@pytest.mark.asyncio
async def test_chat_stream_error_emits_schema_compliant_error_event():
    """Exception in agent_service.chat() → SSE error event with 'error' field."""
    session_id = "sess-error"
    session = SimpleNamespace(id=session_id, status="running", title="Active task")

    async def exploding_chat(**_kwargs):
        # Yield one valid event so the generator is iterable, then crash
        yield ProgressEvent(phase=PlanningPhase.RECEIVED, message="Starting...", progress_percent=5)
        raise RuntimeError("Sandbox crashed")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        chat=exploding_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="Do something")

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(feature_sse_v2=False)
        response = await chat(
            session_id=session_id,
            request=request,
            http_request=_make_http_request(),
            current_user=current_user,
            agent_service=agent_service,
        )

    events = await _collect_sse_events(response)

    # Find the error event
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1, "Expected at least one error SSE event"
    # Payload MUST have 'error' field (matches frontend ErrorEventData schema)
    assert "error" in error_events[0]["data"]
    assert "Sandbox crashed" in error_events[0]["data"]["error"]
    assert error_events[0]["data"]["error_code"] in {"stream_exception", "sandbox_failure"}
    assert error_events[0]["data"]["error_category"] in {"transport", "internal"}
    assert error_events[0]["data"]["recoverable"] is True
    assert error_events[0]["data"]["can_resume"] is True


@pytest.mark.asyncio
async def test_chat_failed_session_no_input_returns_done_event():
    """Failed session + no input → done event (same as completed)."""
    session_id = "sess-failed"
    session = SimpleNamespace(id=session_id, status="failed", title="Failed task")
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        chat=AsyncMock(),
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest()

    response = await chat(
        session_id=session_id,
        request=request,
        http_request=_make_http_request(),
        current_user=current_user,
        agent_service=agent_service,
    )

    events = await _collect_sse_events(response)
    assert len(events) == 1
    assert events[0]["event"] == "done"
    agent_service.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_deferred_disconnect_cancellation_triggers_after_grace(monkeypatch: pytest.MonkeyPatch):
    """Disconnect cancellation should be delayed and then executed."""
    service = SimpleNamespace(request_cancellation=MagicMock())

    async def _no_active_stream(*_args, **_kwargs):
        return False

    monkeypatch.setattr("app.interfaces.api.session_routes.has_active_stream", _no_active_stream)

    _schedule_disconnect_cancellation("sess-grace", service, grace_seconds=0.01)
    await asyncio.sleep(0.03)

    service.request_cancellation.assert_called_once_with("sess-grace")


@pytest.mark.asyncio
async def test_deferred_disconnect_cancellation_skips_when_stream_reconnected(monkeypatch: pytest.MonkeyPatch):
    """Cancellation should be skipped when stream is active again within grace window."""
    service = SimpleNamespace(request_cancellation=MagicMock())

    async def _active_stream(*_args, **_kwargs):
        return True

    monkeypatch.setattr("app.interfaces.api.session_routes.has_active_stream", _active_stream)

    _schedule_disconnect_cancellation("sess-reconnected", service, grace_seconds=0.01)
    await asyncio.sleep(0.03)

    service.request_cancellation.assert_not_called()


@pytest.mark.asyncio
async def test_reconnect_cancels_pending_disconnect_cancellation(monkeypatch: pytest.MonkeyPatch):
    """A reconnect should cancel previously scheduled disconnect teardown."""
    service = SimpleNamespace(request_cancellation=MagicMock())

    async def _no_active_stream(*_args, **_kwargs):
        return False

    monkeypatch.setattr("app.interfaces.api.session_routes.has_active_stream", _no_active_stream)

    _schedule_disconnect_cancellation("sess-reconnect-cancel", service, grace_seconds=0.05)
    _cancel_pending_disconnect_cancellation("sess-reconnect-cancel")
    await asyncio.sleep(0.08)

    service.request_cancellation.assert_not_called()
