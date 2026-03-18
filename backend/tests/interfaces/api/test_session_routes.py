"""Tests for session route utilities."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.core.prometheus_metrics import (
    reset_all_metrics,
    sse_reconnect_first_non_heartbeat_seconds,
    sse_resume_cursor_fallback_total,
    sse_resume_cursor_state_total,
    sse_stream_close_total,
    sse_stream_events_total,
)
from app.domain.models.event import DoneEvent, PlanningPhase, ProgressEvent, ReportEvent
from app.domain.models.session import ResearchMode, SessionStatus
from app.domain.models.source_citation import SourceCitation
from app.interfaces.api.session_routes import (
    _cancel_pending_disconnect_cancellation,
    _event_phase_label,
    _is_websocket_origin_allowed,
    _normalize_session_status,
    _resolve_stream_exhausted_close_reason,
    _safe_exc_text,
    _schedule_disconnect_cancellation,
    chat,
    download_session_report_pdf,
    end_takeover,
    get_screenshot_image,
    get_session,
    get_shared_screenshot_image,
    get_takeover_status,
    input_websocket,
    screencast_websocket,
    start_takeover,
    stop_session,
    takeover_navigation_action,
    takeover_navigation_history,
)
from app.interfaces.schemas.session import ChatRequest, FollowUpContext, ReportPdfDownloadRequest


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


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


def test_safe_exc_text_redacts_sensitive_query_values():
    error = RuntimeError("connect failed: ws://sandbox.local/stream?secret=abc123&signature=sig123&uid=user42")
    message = _safe_exc_text(error)
    assert "secret=***" in message
    assert "signature=***" in message
    assert "uid=***" in message
    assert "abc123" not in message
    assert "sig123" not in message
    assert "user42" not in message


def test_event_phase_label_handles_enum_and_missing_phase():
    assert (
        _event_phase_label(ProgressEvent(phase=PlanningPhase.ANALYZING, message="a", progress_percent=10))
        == "analyzing"
    )
    assert _event_phase_label(DoneEvent(title="Done")) == "none"


def test_normalize_session_status_handles_enum_strings_and_unknown():
    assert _normalize_session_status(PlanningPhase.ANALYZING) == "analyzing"
    assert _normalize_session_status("RUNNING") == "running"
    assert _normalize_session_status(None) == "unknown"


def test_resolve_stream_exhausted_close_reason_maps_terminal_and_non_terminal_statuses():
    assert _resolve_stream_exhausted_close_reason("completed") == "session_terminal_completed"
    assert _resolve_stream_exhausted_close_reason("failed") == "session_terminal_failed"
    assert _resolve_stream_exhausted_close_reason("cancelled") == "session_terminal_cancelled"
    assert _resolve_stream_exhausted_close_reason("running") == "stream_exhausted_non_terminal"
    assert _resolve_stream_exhausted_close_reason("mystery") == "stream_exhausted_unknown_state"


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
async def test_get_session_includes_source_field_in_response():
    session_id = "session-123"
    current_user = SimpleNamespace(id="user-123")
    session = SimpleNamespace(
        id=session_id,
        title="Telegram thread",
        status=SessionStatus.COMPLETED,
        source="telegram",
        research_mode=ResearchMode.DEEP_RESEARCH,
        events=[],
        is_shared=False,
    )
    agent_service = SimpleNamespace(get_session_full=AsyncMock(return_value=session))

    response = await get_session(
        session_id=session_id,
        current_user=current_user,
        agent_service=agent_service,
    )

    assert response.code == 0
    assert response.data is not None
    assert response.data.session_id == session_id
    assert response.data.source == "telegram"


@pytest.mark.asyncio
async def test_download_session_report_pdf_returns_pdf_attachment():
    session_id = "session-pdf-1"
    current_user = SimpleNamespace(id="user-123")
    agent_service = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    renderer = SimpleNamespace(render=AsyncMock(return_value=b"%PDF-1.4"))
    request = ReportPdfDownloadRequest(
        title="Q1 Revenue Report",
        content="# Summary\n\nSee findings [1].",
        sources=[
            SourceCitation(
                url="https://example.com/source",
                title="Example Source",
                snippet=None,
                access_time=datetime.now(UTC),
                source_type="search",
            )
        ],
        author="Analyst",
    )

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(
            telegram_pdf_include_toc=True,
            telegram_pdf_toc_min_sections=3,
            telegram_pdf_unicode_font="DejaVuSans",
        )
        with patch("app.interfaces.api.session_routes.build_configured_pdf_renderer", return_value=renderer):
            response = await download_session_report_pdf(
                session_id=session_id,
                request=request,
                current_user=current_user,
                agent_service=agent_service,
            )

    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4"
    assert response.headers["content-disposition"].startswith("attachment; filename*=UTF-8''q1-revenue-report.pdf")
    agent_service.get_session.assert_awaited_once_with(session_id, current_user.id)
    renderer.render.assert_awaited_once()


@pytest.mark.asyncio
async def test_download_session_report_pdf_rejects_empty_content():
    session_id = "session-pdf-2"
    current_user = SimpleNamespace(id="user-123")
    agent_service = SimpleNamespace(get_session=AsyncMock(return_value=SimpleNamespace(id=session_id)))
    request = ReportPdfDownloadRequest(title="Report", content="   ", sources=[])

    with pytest.raises(BadRequestError, match="Report content cannot be empty"):
        await download_session_report_pdf(
            session_id=session_id,
            request=request,
            current_user=current_user,
            agent_service=agent_service,
        )


@pytest.mark.asyncio
async def test_download_session_report_pdf_raises_not_found_for_missing_session():
    session_id = "session-pdf-404"
    current_user = SimpleNamespace(id="user-123")
    agent_service = SimpleNamespace(get_session=AsyncMock(return_value=None))
    request = ReportPdfDownloadRequest(title="Report", content="# Body", sources=[])

    with pytest.raises(NotFoundError, match="Session not found"):
        await download_session_report_pdf(
            session_id=session_id,
            request=request,
            current_user=current_user,
            agent_service=agent_service,
        )


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


@pytest.mark.asyncio
async def test_takeover_navigation_action_proxies_to_sandbox():
    session_id = "session-nav-1"
    current_user = SimpleNamespace(id="user-1")
    sandbox = SimpleNamespace(base_url="http://sandbox.local")
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=SimpleNamespace(id=session_id, sandbox_id="sandbox-1"))
    )
    sandbox_cls = SimpleNamespace(get=AsyncMock(return_value=sandbox))

    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()
    response_mock.json = MagicMock(return_value={"ok": True, "message": "Navigated back"})

    client = AsyncMock()
    client.post = AsyncMock(return_value=response_mock)

    with patch("app.interfaces.api.session_routes.get_sandbox_navigation_http_client", AsyncMock(return_value=client)):
        response = await takeover_navigation_action(
            session_id=session_id,
            action="back",
            current_user=current_user,
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

    assert response.code == 0
    assert response.data.action == "back"
    assert response.data.ok is True
    assert response.data.message == "Navigated back"


@pytest.mark.asyncio
async def test_takeover_navigation_history_returns_sanitized_payload():
    session_id = "session-nav-2"
    current_user = SimpleNamespace(id="user-2")
    sandbox = SimpleNamespace(base_url="http://sandbox.local")
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=SimpleNamespace(id=session_id, sandbox_id="sandbox-2"))
    )
    sandbox_cls = SimpleNamespace(get=AsyncMock(return_value=sandbox))

    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()
    response_mock.json = MagicMock(
        return_value={
            "current_index": 1,
            "entries": [
                {"id": 101, "url": "https://example.com/login", "title": "Login"},
                {"id": 102, "url": "https://example.com/app", "title": "App"},
            ],
        }
    )

    client = AsyncMock()
    client.get = AsyncMock(return_value=response_mock)

    with patch("app.interfaces.api.session_routes.get_sandbox_navigation_http_client", AsyncMock(return_value=client)):
        response = await takeover_navigation_history(
            session_id=session_id,
            current_user=current_user,
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

    assert response.code == 0
    assert response.data.current_index == 1
    assert len(response.data.entries) == 2
    assert response.data.entries[0].url == "https://example.com/login"


# ---------------------------------------------------------------------------
# chat() endpoint tests - completed-session reentry & SSE payload schemas
# ---------------------------------------------------------------------------


def _make_completed_session(
    session_id: str = "sess-1",
    title: str = "My Task",
    events: list | None = None,
) -> SimpleNamespace:
    """Return a minimal session object that looks completed."""
    return SimpleNamespace(id=session_id, status="completed", title=title, events=events or [])


def _make_http_request() -> MagicMock:
    """Return a mock starlette Request with is_disconnected."""
    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)
    req.headers = {"Last-Event-ID": None}
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
        get_session_full=AsyncMock(return_value=session),
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
async def test_chat_completed_session_with_resume_cursor_replays_tail_events():
    """Completed session + resume cursor should replay missing report tail instead of done-only."""
    session_id = "sess-resume-tail"
    progress_event = ProgressEvent(
        id="evt-progress",
        phase=PlanningPhase.FINALIZING,
        message="Wrapping up",
        progress_percent=90,
    )
    report_event = ReportEvent(
        id="evt-report",
        title="Final Report",
        content="# Final Report\n\nAll done.",
    )
    done_event = DoneEvent(id="evt-done", title="Task completed")
    session = _make_completed_session(
        session_id=session_id,
        title="Finished task",
        events=[progress_event, report_event, done_event],
    )
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        get_session_full=AsyncMock(return_value=session),
        chat=AsyncMock(),  # Should NOT be called
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(event_id="evt-progress")

    response = await chat(
        session_id=session_id,
        request=request,
        http_request=_make_http_request(),
        current_user=current_user,
        agent_service=agent_service,
    )

    events = await _collect_sse_events(response)

    assert [event["event"] for event in events] == ["report", "done"]
    assert events[0]["data"]["event_id"] == "evt-report"
    assert events[0]["data"]["title"] == "Final Report"
    assert events[1]["data"]["event_id"] == "evt-done"
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "found"}) == 1.0
    agent_service.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_completed_session_with_stale_resume_cursor_emits_gap_then_done():
    """Completed session + stale cursor should emit explicit gap diagnostics before done."""
    session_id = "sess-stale-cursor"
    done_event = DoneEvent(id="evt-done", title="Task completed")
    session = _make_completed_session(
        session_id=session_id,
        title="Finished task",
        events=[done_event],
    )
    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        get_session_full=AsyncMock(return_value=session),
        chat=AsyncMock(),  # Should NOT be called
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(event_id="evt-missing")

    response = await chat(
        session_id=session_id,
        request=request,
        http_request=_make_http_request(),
        current_user=current_user,
        agent_service=agent_service,
    )

    events = await _collect_sse_events(response)

    assert [event["event"] for event in events] == ["error", "done"]
    assert events[0]["data"]["error_code"] == "stream_gap_detected"
    assert events[0]["data"]["details"]["reason"] == "stale_cursor"
    assert "event_id" in events[1]["data"]
    assert sse_resume_cursor_state_total.get({"endpoint": "chat", "state": "stale"}) == 1.0
    assert sse_resume_cursor_fallback_total.get({"endpoint": "chat", "reason": "stale_cursor"}) == 1.0
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
        get_session_full=AsyncMock(return_value=session),
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
        get_session_full=AsyncMock(return_value=session),
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
async def test_chat_forwards_last_event_id_header_when_request_event_id_missing():
    """Running session + Last-Event-ID header should propagate cursor to agent_service.chat()."""
    session_id = "sess-header-resume"
    session = SimpleNamespace(id=session_id, status="running", title="Active task")
    captured_kwargs: dict[str, object] = {}

    async def fake_chat(**kwargs):
        captured_kwargs.update(kwargs)
        yield DoneEvent(title="done")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        get_session_full=AsyncMock(return_value=session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="continue")
    http_request = _make_http_request()
    http_request.headers = {"Last-Event-ID": "evt-header-123"}

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(feature_sse_v2=False)
        response = await chat(
            session_id=session_id,
            request=request,
            http_request=http_request,
            current_user=current_user,
            agent_service=agent_service,
        )

    events = await _collect_sse_events(response)
    event_names = [e["event"] for e in events]
    assert "done" in event_names
    assert captured_kwargs["event_id"] == "evt-header-123"


@pytest.mark.asyncio
async def test_chat_remote_pending_session_streams_persisted_events_without_calling_agent_chat():
    """Gateway-owned non-terminal sessions should be observed, not resumed locally."""
    session_id = "sess-remote-pending"
    initial_progress = ProgressEvent(
        id="evt-1",
        phase=PlanningPhase.RECEIVED,
        message="Queued from Telegram",
        progress_percent=5,
    )
    report_event = ReportEvent(
        id="evt-2",
        title="Final Report",
        content="# Final Report\n\nDelivered from gateway.",
    )
    pending_session = SimpleNamespace(
        id=session_id,
        status="pending",
        title="Telegram task",
        source="telegram",
        events=[initial_progress],
    )
    completed_session = SimpleNamespace(
        id=session_id,
        status="completed",
        title="Telegram task",
        source="telegram",
        events=[initial_progress, report_event],
    )
    chat_called = False

    async def _unexpected_chat(**_kwargs):
        nonlocal chat_called
        chat_called = True
        raise AssertionError("agent_service.chat should not run for gateway-owned pending sessions")
        yield  # pragma: no cover

    agent_service = SimpleNamespace(
        get_session_full=AsyncMock(side_effect=[pending_session, completed_session]),
        chat=_unexpected_chat,
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

    events = [event for event in await _collect_sse_events(response) if event["event"]]

    assert [event["event"] for event in events] == ["report", "done"]
    assert events[0]["data"]["event_id"] == "evt-2"
    assert chat_called is False


@pytest.mark.asyncio
async def test_chat_remote_running_session_replays_events_after_resume_cursor():
    """Remote session replay should emit only events after the supplied cursor."""
    session_id = "sess-remote-running"
    first_progress = ProgressEvent(
        id="evt-1",
        phase=PlanningPhase.RECEIVED,
        message="Gateway accepted request",
        progress_percent=5,
    )
    second_progress = ProgressEvent(
        id="evt-2",
        phase=PlanningPhase.ANALYZING,
        message="Collecting evidence",
        progress_percent=45,
    )
    report_event = ReportEvent(
        id="evt-3",
        title="Final Report",
        content="# Final Report\n\nAll findings included.",
    )
    running_session = SimpleNamespace(
        id=session_id,
        status="running",
        title="Telegram task",
        source="telegram",
        events=[first_progress, second_progress],
    )
    completed_session = SimpleNamespace(
        id=session_id,
        status="completed",
        title="Telegram task",
        source="telegram",
        events=[first_progress, second_progress, report_event],
    )
    chat_called = False

    async def _unexpected_chat(**_kwargs):
        nonlocal chat_called
        chat_called = True
        raise AssertionError("agent_service.chat should not run for gateway-owned running sessions")
        yield  # pragma: no cover

    agent_service = SimpleNamespace(
        get_session_full=AsyncMock(side_effect=[running_session, completed_session]),
        chat=_unexpected_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(event_id="evt-1")

    response = await chat(
        session_id=session_id,
        request=request,
        http_request=_make_http_request(),
        current_user=current_user,
        agent_service=agent_service,
    )

    events = [event for event in await _collect_sse_events(response) if event["event"]]

    assert [event["event"] for event in events] == ["progress", "report", "done"]
    assert events[0]["data"]["event_id"] == "evt-2"
    assert events[1]["data"]["event_id"] == "evt-3"
    assert chat_called is False


@pytest.mark.asyncio
async def test_chat_reconnect_records_latency_and_phase_metrics():
    """Reconnect streams should record first real-event latency and phase-tagged event counts."""
    session_id = "sess-metrics"
    session = SimpleNamespace(id=session_id, status="running", title="Active task")

    async def fake_chat(**_kwargs):
        yield ProgressEvent(
            phase=PlanningPhase.ANALYZING,
            message="Analyzing",
            progress_percent=15,
        )
        yield DoneEvent(title="done")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        get_session_full=AsyncMock(return_value=session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="continue", event_id="evt-prev")

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
    assert "done" in event_names

    reconnect_latency_observations = sse_reconnect_first_non_heartbeat_seconds.collect()
    reconnect_latency_chat = next(
        observation for observation in reconnect_latency_observations if observation["labels"].get("endpoint") == "chat"
    )
    assert reconnect_latency_chat["count"] == 1
    assert reconnect_latency_chat["sum"] >= 0.0

    assert sse_stream_events_total.get({"endpoint": "chat", "event_type": "progress", "phase": "received"}) >= 1.0
    assert sse_stream_events_total.get({"endpoint": "chat", "event_type": "progress", "phase": "analyzing"}) >= 1.0
    assert sse_stream_events_total.get({"endpoint": "chat", "event_type": "done", "phase": "none"}) >= 1.0


@pytest.mark.asyncio
async def test_chat_stream_exhausted_uses_terminal_close_reason_when_session_completed():
    """Active stream exhaustion should map to terminal close reason when session is completed."""
    session_id = "sess-close-terminal"
    initial_session = SimpleNamespace(id=session_id, status="running", title="Active task")
    terminal_session = SimpleNamespace(id=session_id, status="completed", title="Active task")

    async def fake_chat(**_kwargs):
        yield DoneEvent(title="done")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=terminal_session),
        get_session_full=AsyncMock(return_value=initial_session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="continue")

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
    assert any(event["event"] == "done" for event in events)
    assert sse_stream_close_total.get({"endpoint": "chat", "reason": "session_terminal_completed"}) == 1.0


@pytest.mark.asyncio
async def test_chat_stream_exhausted_uses_non_terminal_close_reason_when_session_running():
    """Stream exhaustion without terminal session state should not be reported as completed."""
    session_id = "sess-close-nonterminal"
    running_session = SimpleNamespace(id=session_id, status="running", title="Active task")

    async def fake_chat(**_kwargs):
        yield DoneEvent(title="done")

    agent_service = SimpleNamespace(
        get_session=AsyncMock(return_value=running_session),
        get_session_full=AsyncMock(return_value=running_session),
        chat=fake_chat,
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="continue")

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
    assert any(event["event"] == "done" for event in events)
    assert sse_stream_close_total.get({"endpoint": "chat", "reason": "stream_exhausted_non_terminal"}) == 1.0


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
        get_session_full=AsyncMock(return_value=session),
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
        get_session_full=AsyncMock(return_value=session),
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
async def test_chat_client_disconnect_defers_cancellation_for_reconnect_window():
    """Refresh-like disconnects should schedule deferred teardown instead of cancelling immediately."""
    session_id = "sess-refresh"
    session = SimpleNamespace(id=session_id, status="running", title="Active task")

    async def hanging_chat(**_kwargs):
        await asyncio.sleep(60)
        yield DoneEvent(title="never reached")

    agent_service = SimpleNamespace(
        get_session_full=AsyncMock(return_value=session),
        chat=hanging_chat,
        request_cancellation=MagicMock(),
    )
    current_user = SimpleNamespace(id="user-1")
    request = ChatRequest(message="continue")
    http_request = _make_http_request()
    http_request.is_disconnected = AsyncMock(side_effect=[True])

    with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(
            feature_sse_v2=True,
            debug=False,
            sse_disconnect_cancellation_grace_seconds=7.5,
        )
        with patch("app.interfaces.api.session_routes._schedule_disconnect_cancellation") as schedule_disconnect:
            response = await chat(
                session_id=session_id,
                request=request,
                http_request=http_request,
                current_user=current_user,
                agent_service=agent_service,
            )

            events = await _collect_sse_events(response)

    assert any(event["event"] == "progress" for event in events)
    agent_service.request_cancellation.assert_not_called()
    schedule_disconnect.assert_called_once_with(
        session_id=session_id,
        agent_service=agent_service,
        grace_seconds=7.5,
    )


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


# ---------------------------------------------------------------------------
# WebSocket IDOR Protection Tests
# ---------------------------------------------------------------------------


def _make_websocket(
    url: str = "ws://localhost/sessions/sess-1/input?signature=abc&uid=user-1",
    origin: str = "http://localhost",
) -> MagicMock:
    """Create a mock WebSocket with a configurable URL.

    ``ws.headers`` is a plain dict so that origin-allowlist logic
    (``_is_websocket_origin_allowed``) receives a real string rather than an
    auto-created MagicMock.  The default origin ``http://localhost`` passes the
    allowlist check when ``cors_origins`` is empty (dev-permissive default) or
    when ``http://localhost`` is explicitly listed.
    """
    ws = MagicMock()
    ws.url = url
    ws.headers = {"origin": origin}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.receive = AsyncMock(side_effect=Exception("should not be called"))
    return ws


def _make_session(
    session_id: str = "sess-1",
    user_id: str = "user-1",
    sandbox_id: str = "sandbox-1",
) -> SimpleNamespace:
    """Create a minimal session object."""
    return SimpleNamespace(id=session_id, user_id=user_id, sandbox_id=sandbox_id)


@pytest.fixture(autouse=False)
def _permit_all_ws_origins(monkeypatch):
    """Patch get_settings to clear cors_origins so origin check is permissive.

    IDOR tests focus on uid/signature auth, not origin enforcement.
    Origin-enforcement tests control their own settings via explicit patching.
    """
    monkeypatch.setattr(
        "app.interfaces.api.session_routes.get_settings",
        lambda: SimpleNamespace(cors_origins="", sandbox_api_secret=None),
    )


class TestInputWebSocketIDOR:
    """Tests for IDOR protection on the input_websocket endpoint."""

    @pytest.fixture(autouse=True)
    def _allow_origins(self, _permit_all_ws_origins):
        """Ensure origin allowlist is not enforced for IDOR tests."""

    @pytest.mark.asyncio
    async def test_rejects_missing_user_id_in_signed_url(self):
        """Input WebSocket must reject connections without uid in signed URL."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/input?signature=abc")
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        await input_websocket(
            websocket=ws,
            session_id="sess-1",
            signature="abc",
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

        ws.close.assert_awaited_once_with(code=1008, reason="Unauthorized")
        agent_service.get_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_session_belonging_to_different_user(self):
        """Input WebSocket must reject when session belongs to a different user."""
        # Attacker (user-attacker) tries to access session owned by user-1
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/input?signature=abc&uid=user-attacker")
        # get_session with (session_id, user_id) returns None when user doesn't own it
        agent_service = SimpleNamespace(get_session=AsyncMock(return_value=None))
        sandbox_cls = MagicMock()

        await input_websocket(
            websocket=ws,
            session_id="sess-1",
            signature="abc",
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

        agent_service.get_session.assert_awaited_once_with("sess-1", "user-attacker")
        ws.close.assert_awaited_once_with(code=1008, reason="Session or sandbox not found")

    @pytest.mark.asyncio
    async def test_rejects_session_without_sandbox_id(self):
        """Input WebSocket must reject when session has no sandbox assigned."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/input?signature=abc&uid=user-1")
        session = _make_session(sandbox_id=None)
        agent_service = SimpleNamespace(get_session=AsyncMock(return_value=session))
        sandbox_cls = MagicMock()

        await input_websocket(
            websocket=ws,
            session_id="sess-1",
            signature="abc",
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

        ws.close.assert_awaited_once_with(code=1008, reason="Session or sandbox not found")

    @pytest.mark.asyncio
    async def test_passes_user_id_to_get_session(self):
        """Input WebSocket must always pass user_id for ownership verification."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/input?signature=abc&uid=user-1")
        session = _make_session()
        agent_service = SimpleNamespace(get_session=AsyncMock(return_value=session))
        sandbox = SimpleNamespace(base_url="http://sandbox:8083")
        sandbox_cls = MagicMock()
        sandbox_cls.get = AsyncMock(return_value=sandbox)

        # Patch websockets.connect to avoid actual connection
        with patch("app.interfaces.api.session_routes.websockets") as mock_ws_lib:
            mock_ws_lib.connect.side_effect = ConnectionError("test abort")
            mock_ws_lib.exceptions = SimpleNamespace(WebSocketException=Exception)

            await input_websocket(
                websocket=ws,
                session_id="sess-1",
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        agent_service.get_session.assert_awaited_once_with("sess-1", "user-1")

    @pytest.mark.asyncio
    async def test_logs_security_warning_for_missing_uid(self, caplog: pytest.LogCaptureFixture):
        """Input WebSocket must log a security warning when uid is missing."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-target/input?signature=abc")
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        with caplog.at_level(logging.WARNING):
            await input_websocket(
                websocket=ws,
                session_id="sess-target",
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        assert any("[SECURITY]" in record.message for record in caplog.records)
        assert any("sess-target" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# WebSocket Origin Allowlist Tests
# ---------------------------------------------------------------------------


def _make_ws_with_origin(origin: str | None, url: str = "ws://localhost/sessions/s/screencast") -> MagicMock:
    ws = MagicMock()
    ws.url = url
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    headers: dict[str, str] = {}
    if origin is not None:
        headers["origin"] = origin
    ws.headers = headers
    return ws


class TestWebSocketOriginAllowlist:
    """Tests for _is_websocket_origin_allowed helper and WebSocket handler enforcement."""

    def test_allows_all_when_no_cors_origins_configured(self):
        ws = _make_ws_with_origin("https://evil.example.com")
        with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(cors_origins="")
            assert _is_websocket_origin_allowed(ws) is True

    def test_allows_matching_origin(self):
        ws = _make_ws_with_origin("http://localhost:5173")
        with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(cors_origins="http://localhost:5173,https://app.example.com")
            assert _is_websocket_origin_allowed(ws) is True

    def test_rejects_unknown_origin(self):
        ws = _make_ws_with_origin("https://evil.example.com")
        with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(cors_origins="http://localhost:5173")
            assert _is_websocket_origin_allowed(ws) is False

    def test_rejects_missing_origin_when_allowlist_set(self):
        ws = _make_ws_with_origin(None)
        with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(cors_origins="http://localhost:5173")
            assert _is_websocket_origin_allowed(ws) is False

    def test_ignores_trailing_slash_in_origin(self):
        ws = _make_ws_with_origin("http://localhost:5173/")
        with patch("app.interfaces.api.session_routes.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(cors_origins="http://localhost:5173")
            assert _is_websocket_origin_allowed(ws) is True

    @pytest.mark.asyncio
    async def test_screencast_websocket_rejects_disallowed_origin(self, caplog: pytest.LogCaptureFixture):
        ws = _make_ws_with_origin("https://evil.example.com")
        ws.url = "ws://localhost/sessions/sess-1/screencast?signature=abc&uid=user-1"
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        with (
            patch("app.interfaces.api.session_routes.get_settings") as mock_settings,
            caplog.at_level(logging.WARNING),
        ):
            mock_settings.return_value = SimpleNamespace(
                cors_origins="http://localhost:5173",
                sandbox_api_secret=None,
            )
            await screencast_websocket(
                websocket=ws,
                session_id="sess-1",
                quality=70,
                max_fps=15,
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        # accept() must be called before close() so the WS handshake completes
        # and the client receives the 1008 close frame rather than an HTTP 403.
        ws.accept.assert_awaited_once()
        ws.close.assert_awaited_once_with(code=1008, reason="Origin not allowed")
        assert any("[SECURITY]" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_input_websocket_rejects_disallowed_origin(self, caplog: pytest.LogCaptureFixture):
        ws = _make_ws_with_origin("https://evil.example.com")
        ws.url = "ws://localhost/sessions/sess-1/input?signature=abc&uid=user-1"
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        with (
            patch("app.interfaces.api.session_routes.get_settings") as mock_settings,
            caplog.at_level(logging.WARNING),
        ):
            mock_settings.return_value = SimpleNamespace(
                cors_origins="http://localhost:5173",
                sandbox_api_secret=None,
            )
            await input_websocket(
                websocket=ws,
                session_id="sess-1",
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        # accept() must be called before close() so the WS handshake completes
        # and the client receives the 1008 close frame rather than an HTTP 403.
        ws.accept.assert_awaited_once()
        ws.close.assert_awaited_once_with(code=1008, reason="Origin not allowed")
        assert any("[SECURITY]" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Takeover Lifecycle Route Tests
# ---------------------------------------------------------------------------


def _make_takeover_status_response(
    session_id: str = "sess-1",
    state: str = "takeover_active",
    reason: str = "manual",
) -> dict:
    return {"session_id": session_id, "takeover_state": state, "reason": reason}


class TestTakeoverLifecycleRoutes:
    """Tests for start_takeover, end_takeover, and get_takeover_status routes."""

    @pytest.mark.asyncio
    async def test_start_takeover_calls_service_and_returns_status(self):
        from app.interfaces.schemas.session import TakeoverStartRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="takeover_active")
        agent_service = SimpleNamespace(
            start_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        response = await start_takeover(
            session_id="sess-1",
            request=TakeoverStartRequest(reason="manual"),
            current_user=current_user,
            agent_service=agent_service,
        )

        agent_service.start_takeover.assert_awaited_once_with("sess-1", "user-1", reason="manual")
        agent_service.get_takeover_status.assert_awaited_once_with("sess-1", "user-1")
        assert response.code == 0
        assert response.data.takeover_state == "takeover_active"
        assert response.data.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_start_takeover_uses_manual_reason_as_default(self):
        from app.interfaces.schemas.session import TakeoverStartRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response()
        agent_service = SimpleNamespace(
            start_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        await start_takeover(
            session_id="sess-1",
            request=TakeoverStartRequest(reason=None),
            current_user=current_user,
            agent_service=agent_service,
        )

        agent_service.start_takeover.assert_awaited_once_with("sess-1", "user-1", reason="manual")

    @pytest.mark.asyncio
    async def test_end_takeover_forwards_all_options_to_service(self):
        from app.interfaces.schemas.session import TakeoverEndRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="idle")
        agent_service = SimpleNamespace(
            end_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        response = await end_takeover(
            session_id="sess-1",
            request=TakeoverEndRequest(
                context="user finished captcha",
                persist_login_state=True,
                resume_agent=True,
            ),
            current_user=current_user,
            agent_service=agent_service,
        )

        agent_service.end_takeover.assert_awaited_once_with(
            "sess-1",
            "user-1",
            context="user finished captcha",
            persist_login_state=True,
            resume_agent=True,
        )
        assert response.code == 0
        assert response.data.takeover_state == "idle"

    @pytest.mark.asyncio
    async def test_end_takeover_resume_agent_false_is_forwarded(self):
        """Ensure resume_agent=False is forwarded so the agent must not resume."""
        from app.interfaces.schemas.session import TakeoverEndRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="takeover_active")
        agent_service = SimpleNamespace(
            end_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        await end_takeover(
            session_id="sess-1",
            request=TakeoverEndRequest(resume_agent=False),
            current_user=current_user,
            agent_service=agent_service,
        )

        _, kwargs = agent_service.end_takeover.call_args
        assert kwargs.get("resume_agent") is False

    @pytest.mark.asyncio
    async def test_get_takeover_status_returns_current_state(self):
        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="idle")
        agent_service = SimpleNamespace(
            get_takeover_status=AsyncMock(return_value=status),
        )

        response = await get_takeover_status(
            session_id="sess-1",
            current_user=current_user,
            agent_service=agent_service,
        )

        agent_service.get_takeover_status.assert_awaited_once_with("sess-1", "user-1")
        assert response.code == 0
        assert response.data.takeover_state == "idle"
        assert response.data.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_start_takeover_is_idempotent_when_already_active(self):
        """Calling start_takeover when already active returns current state without error."""
        from app.interfaces.schemas.session import TakeoverStartRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="takeover_active")
        agent_service = SimpleNamespace(
            start_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        response = await start_takeover(
            session_id="sess-1",
            request=TakeoverStartRequest(reason="captcha"),
            current_user=current_user,
            agent_service=agent_service,
        )

        assert response.data.takeover_state == "takeover_active"

    @pytest.mark.asyncio
    async def test_end_takeover_is_idempotent_when_already_idle(self):
        """Calling end_takeover when already idle returns current state without error."""
        from app.interfaces.schemas.session import TakeoverEndRequest

        current_user = SimpleNamespace(id="user-1")
        status = _make_takeover_status_response(state="idle")
        agent_service = SimpleNamespace(
            end_takeover=AsyncMock(),
            get_takeover_status=AsyncMock(return_value=status),
        )

        response = await end_takeover(
            session_id="sess-1",
            request=TakeoverEndRequest(),
            current_user=current_user,
            agent_service=agent_service,
        )

        assert response.data.takeover_state == "idle"


class TestScreencastWebSocketIDOR:
    """Tests for IDOR protection on the screencast_websocket endpoint."""

    @pytest.fixture(autouse=True)
    def _allow_origins(self, _permit_all_ws_origins):
        """Ensure origin allowlist is not enforced for IDOR tests."""

    @pytest.mark.asyncio
    async def test_rejects_missing_user_id_in_signed_url(self):
        """Screencast WebSocket must reject connections without uid in signed URL."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/screencast?signature=abc")
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        await screencast_websocket(
            websocket=ws,
            session_id="sess-1",
            quality=70,
            max_fps=15,
            signature="abc",
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

        ws.close.assert_awaited_once_with(code=1008, reason="Unauthorized")
        agent_service.get_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_session_belonging_to_different_user(self):
        """Screencast WebSocket must reject when session belongs to a different user."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/screencast?signature=abc&uid=user-attacker")
        agent_service = SimpleNamespace(get_session=AsyncMock(return_value=None))
        sandbox_cls = MagicMock()

        await screencast_websocket(
            websocket=ws,
            session_id="sess-1",
            quality=70,
            max_fps=15,
            signature="abc",
            agent_service=agent_service,
            sandbox_cls=sandbox_cls,
        )

        agent_service.get_session.assert_awaited_once_with("sess-1", "user-attacker")
        ws.close.assert_awaited_once_with(code=1008, reason="Session or sandbox not found")

    @pytest.mark.asyncio
    async def test_passes_user_id_to_get_session(self):
        """Screencast WebSocket must always pass user_id for ownership verification."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-1/screencast?signature=abc&uid=user-1")
        session = _make_session()
        agent_service = SimpleNamespace(get_session=AsyncMock(return_value=session))
        sandbox = SimpleNamespace(base_url="http://sandbox:8083")
        sandbox_cls = MagicMock()
        sandbox_cls.get = AsyncMock(return_value=sandbox)

        with patch("app.interfaces.api.session_routes.websockets") as mock_ws_lib:
            mock_ws_lib.connect.side_effect = ConnectionError("test abort")
            mock_ws_lib.exceptions = SimpleNamespace(WebSocketException=Exception)

            await screencast_websocket(
                websocket=ws,
                session_id="sess-1",
                quality=70,
                max_fps=15,
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        agent_service.get_session.assert_awaited_once_with("sess-1", "user-1")

    @pytest.mark.asyncio
    async def test_logs_security_warning_for_missing_uid(self, caplog: pytest.LogCaptureFixture):
        """Screencast WebSocket must log a security warning when uid is missing."""
        ws = _make_websocket(url="ws://localhost/sessions/sess-target/screencast?signature=abc")
        agent_service = SimpleNamespace(get_session=AsyncMock())
        sandbox_cls = MagicMock()

        with caplog.at_level(logging.WARNING):
            await screencast_websocket(
                websocket=ws,
                session_id="sess-target",
                quality=70,
                max_fps=15,
                signature="abc",
                agent_service=agent_service,
                sandbox_cls=sandbox_cls,
            )

        assert any("[SECURITY]" in record.message for record in caplog.records)
        assert any("sess-target" in record.message for record in caplog.records)
