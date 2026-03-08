import asyncio
import contextlib
import hashlib
import json
import logging
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.application.errors.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.application.services.agent_service import AgentService
from app.application.services.screenshot_service import ScreenshotQueryService
from app.application.services.token_service import TokenService
from app.core import prometheus_metrics as pm
from app.core.config import get_settings
from app.domain.external.sandbox import Sandbox
from app.domain.models.event import DoneEvent, ErrorEvent, PlanningPhase, ProgressEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User
from app.domain.services.pdf.models import ReportPdfPayload
from app.domain.services.stream_guard import (
    StreamErrorCategory,
    StreamErrorCode,
    StreamGuard,
    has_active_stream,
    record_stream_metrics,
    record_stream_reconnection,
    register_active_stream,
    unregister_active_stream,
)
from app.domain.utils.cancellation import CancellationToken
from app.interfaces.dependencies import (
    get_agent_service,
    get_current_user,
    get_eventsource_current_user,
    get_file_service,
    get_optional_current_user,
    get_sandbox_cls,
    get_screenshot_query_service,
    get_token_service,
    verify_signature_websocket,
)
from app.interfaces.gateway.pdf_renderer_factory import build_configured_pdf_renderer
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.event import EventMapper
from app.interfaces.schemas.file import FileViewRequest, FileViewResponse
from app.interfaces.schemas.resource import AccessTokenRequest, SignedUrlResponse
from app.interfaces.schemas.screenshot import ScreenshotListResponse, ScreenshotMetadataResponse
from app.interfaces.schemas.session import (
    ActiveSessionResponse,
    BrowseUrlRequest,
    ChatRequest,
    ConfirmActionRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    DeleteSessionResponse,
    GetSessionResponse,
    ListSessionItem,
    ListSessionResponse,
    RenameSessionRequest,
    ReportPdfDownloadRequest,
    ResumeSessionRequest,
    SandboxInfo,
    SessionStatusResponse,
    SharedSessionResponse,
    ShareSessionResponse,
    ShellViewRequest,
    ShellViewResponse,
    TakeoverEndRequest,
    TakeoverNavigationHistoryEntry,
    TakeoverNavigationHistoryResponse,
    TakeoverNavigationResponse,
    TakeoverStartRequest,
    TakeoverStatusResponse,
)
from app.interfaces.schemas.workspace import WorkspaceManifest, WorkspaceManifestResponse

logger = logging.getLogger(__name__)
SESSION_POLL_INTERVAL = 10

# Redis stream IDs have the format "<milliseconds>-<sequence>" (e.g. "1772445693104-0").
# Only these IDs should be emitted as the SSE `id:` field so that browser Last-Event-ID
# is always a valid Redis resume cursor.  UUID-format IDs from synthetic events (gap
# warnings, beacons) must never become the browser's resume cursor.
_REDIS_STREAM_ID_RE = re.compile(r"^\d+-\d+$")
SANDBOX_WS_CONNECT_KWARGS: dict = {
    # RFC 6455 §5.5.2: Ping every 20s to detect dead sandbox connections.
    # Without this, the backend proxy hangs indefinitely when the sandbox
    # container dies or the screencast stream silently stops.
    "ping_interval": 20,
    # If no pong received within 10s of a ping, consider connection dead.
    "ping_timeout": 10,
    "max_size": None,
}


def _sandbox_ws_extra_headers() -> list[tuple[str, str]]:
    """Build extra headers for backend→sandbox WebSocket connections.

    Includes the shared secret so sandbox auth middleware accepts the connection.
    """
    settings = get_settings()
    headers: list[tuple[str, str]] = []
    if settings.sandbox_api_secret:
        headers.append(("x-sandbox-secret", settings.sandbox_api_secret))
    return headers


def _sandbox_http_headers() -> dict[str, str]:
    """Build extra headers for backend→sandbox HTTP requests."""
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.sandbox_api_secret:
        headers["x-sandbox-secret"] = settings.sandbox_api_secret
    return headers


_SENSITIVE_QUERY_KEYS = {"secret", "signature", "uid"}


def _is_websocket_origin_allowed(websocket: WebSocket) -> bool:
    """Return True if the WebSocket Origin header is in the configured CORS allowlist.

    When no origins are configured (empty string), all origins are permitted to
    preserve backward-compatible behaviour in development environments.
    For production deployments, set ``cors_origins`` in settings to a comma-separated
    list of allowed origins (e.g. ``http://localhost:5173,https://app.example.com``).
    """
    settings = get_settings()
    raw_origins: str = getattr(settings, "cors_origins", "") or ""
    if not raw_origins.strip():
        # No allowlist configured — permissive (dev-mode default)
        return True

    allowed: set[str] = {o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()}
    request_origin: str = (websocket.headers.get("origin") or "").rstrip("/")
    return request_origin in allowed


def _redact_query_params(url: str, sensitive_keys: set[str] | None = None) -> str:
    """Redact sensitive query parameter values in URLs before logging."""
    keys = sensitive_keys or _SENSITIVE_QUERY_KEYS
    try:
        split = urlsplit(url)
        if not split.query:
            return url
        redacted_pairs = []
        for key, value in parse_qsl(split.query, keep_blank_values=True):
            if key.lower() in keys:
                redacted_pairs.append((key, "***"))
            else:
                redacted_pairs.append((key, value))
        return urlunsplit(
            (split.scheme, split.netloc, split.path, urlencode(redacted_pairs, doseq=True), split.fragment)
        )
    except Exception:
        return url


SSE_PROTOCOL_VERSION = "2"
SSE_RETRY_MAX_ATTEMPTS = 7
SSE_RETRY_BASE_DELAY_MS = 1000
SSE_RETRY_MAX_DELAY_MS = 45000
SSE_RETRY_JITTER_RATIO = 0.25
SSE_HEARTBEAT_INTERVAL_SECONDS = 30.0
SSE_DISCONNECT_CANCELLATION_GRACE_SECONDS = 45.0
SSE_TERMINAL_STATUS_CLOSE_REASONS: dict[str, str] = {
    "completed": "session_terminal_completed",
    "failed": "session_terminal_failed",
    "cancelled": "session_terminal_cancelled",
}
SSE_NON_TERMINAL_STATUSES = {"pending", "initializing", "running", "waiting"}

router = APIRouter(prefix="/sessions", tags=["sessions"])
_pending_disconnect_cancellations: dict[str, asyncio.Task[None]] = {}


def _cancel_pending_disconnect_cancellation(session_id: str) -> None:
    pending_task = _pending_disconnect_cancellations.pop(session_id, None)
    if pending_task and not pending_task.done():
        pending_task.cancel()


def _schedule_disconnect_cancellation(session_id: str, agent_service: AgentService, grace_seconds: float) -> None:
    _cancel_pending_disconnect_cancellation(session_id)

    async def _deferred_cancel() -> None:
        try:
            await asyncio.sleep(max(0.0, grace_seconds))
            if await has_active_stream(session_id=session_id, endpoint="chat"):
                logger.info(
                    "Skipping deferred cancellation for session %s: active chat stream detected",
                    session_id,
                )
                return
            request_cancellation = getattr(agent_service, "request_cancellation", None)
            if callable(request_cancellation):
                with contextlib.suppress(Exception):
                    request_cancellation(session_id)
        except asyncio.CancelledError:
            logger.debug("Deferred disconnect cancellation cancelled for session %s", session_id)
            raise

    task = asyncio.create_task(_deferred_cancel())
    _pending_disconnect_cancellations[session_id] = task

    def _cleanup(completed_task: asyncio.Task[None]) -> None:
        current = _pending_disconnect_cancellations.get(session_id)
        if current is completed_task:
            _pending_disconnect_cancellations.pop(session_id, None)

    task.add_done_callback(_cleanup)


def _safe_exc_text(exc: BaseException) -> str:
    """Return a stable, bounded exception message for websocket paths."""
    try:
        message = str(exc)
    except Exception:
        message = repr(exc)

    if not message:
        message = exc.__class__.__name__

    for key in _SENSITIVE_QUERY_KEYS:
        message = re.sub(rf"({re.escape(key)}=)[^&\s]+", r"\1***", message, flags=re.IGNORECASE)

    # Keep WebSocket close reasons compact.
    return message[:240]


def _is_truthy_header(value: object | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _event_phase_label(event: object) -> str:
    """Extract a low-cardinality phase label from an event object."""
    phase = getattr(event, "phase", None)
    if phase is None:
        return "none"

    raw_value = str(phase.value) if hasattr(phase, "value") else str(phase)
    normalized = raw_value.strip().lower()
    return normalized or "none"


def _is_heartbeat_progress_event(event: object) -> bool:
    """Return True when the event is a transport heartbeat progress event."""
    return isinstance(event, ProgressEvent) and event.phase == PlanningPhase.HEARTBEAT


def _normalize_session_status(status: object | None) -> str:
    """Normalize session status into a lowercase string value."""
    if status is None:
        return "unknown"
    raw_value = str(status.value) if hasattr(status, "value") else str(status)
    normalized = raw_value.strip().lower()
    return normalized or "unknown"


def _resolve_stream_exhausted_close_reason(status: object | None) -> str:
    """Map stream exhaustion to a bounded close-reason enum using session status."""
    normalized_status = _normalize_session_status(status)
    terminal_reason = SSE_TERMINAL_STATUS_CLOSE_REASONS.get(normalized_status)
    if terminal_reason:
        return terminal_reason
    if normalized_status in SSE_NON_TERMINAL_STATUSES:
        return "stream_exhausted_non_terminal"
    return "stream_exhausted_unknown_state"


def _build_sse_protocol_headers(heartbeat_interval_seconds: float = SSE_HEARTBEAT_INTERVAL_SECONDS) -> dict[str, str]:
    """Build protocol headers so clients can adapt retry and liveness policies."""
    expose_headers = [
        "X-Pythinker-SSE-Protocol-Version",
        "X-Pythinker-SSE-Heartbeat-Interval-Seconds",
        "X-Pythinker-SSE-Retry-Max-Attempts",
        "X-Pythinker-SSE-Retry-Base-Delay-Ms",
        "X-Pythinker-SSE-Retry-Max-Delay-Ms",
        "X-Pythinker-SSE-Retry-Jitter-Ratio",
    ]
    return {
        "X-Pythinker-SSE-Protocol-Version": SSE_PROTOCOL_VERSION,
        "X-Pythinker-SSE-Heartbeat-Interval-Seconds": str(heartbeat_interval_seconds),
        "X-Pythinker-SSE-Retry-Max-Attempts": str(SSE_RETRY_MAX_ATTEMPTS),
        "X-Pythinker-SSE-Retry-Base-Delay-Ms": str(SSE_RETRY_BASE_DELAY_MS),
        "X-Pythinker-SSE-Retry-Max-Delay-Ms": str(SSE_RETRY_MAX_DELAY_MS),
        "X-Pythinker-SSE-Retry-Jitter-Ratio": str(SSE_RETRY_JITTER_RATIO),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
        "Access-Control-Expose-Headers": ", ".join(expose_headers),
    }


def _filter_sessions_for_listing(
    sessions: list[Session],
    *,
    source: str | None = None,
    query_text: str | None = None,
    status: SessionStatus | None = None,
    limit: int = 200,
) -> list[Session]:
    """Apply source/query/status filters to session lists."""
    normalized_source = source.strip().lower() if source else None
    normalized_query = query_text.strip().lower() if query_text else None

    filtered: list[Session] = []
    for session in sessions:
        if normalized_source and str(getattr(session, "source", "web")).lower() != normalized_source:
            continue

        if status and session.status != status:
            continue

        if normalized_query:
            title = (session.title or "").lower()
            latest_message = (session.latest_message or "").lower()
            session_status = session.status.value.lower()
            if (
                normalized_query not in title
                and normalized_query not in latest_message
                and normalized_query not in session_status
            ):
                continue

        filtered.append(session)

    return filtered[:limit]


def _build_safe_pdf_filename(title: str) -> str:
    """Return a stable attachment filename for report PDFs."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").strip().lower()).strip("-")
    if not normalized:
        normalized = "report"
    return f"{normalized[:80]}.pdf"


@router.put("", response_model=APIResponse[CreateSessionResponse])
async def create_session(
    http_request: Request,
    request: CreateSessionRequest = CreateSessionRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> APIResponse[CreateSessionResponse]:
    # Pass the idempotency key (if any) to the application service.
    # The service handles the Redis lookup and storage; the route stays
    # infrastructure-free.
    idempotency_key = http_request.headers.get("x-idempotency-key")

    session = await agent_service.create_session(
        current_user.id,
        mode=request.mode,
        research_mode=request.research_mode,
        initial_message=request.message,  # Phase 4 P0: Pass initial message for intent classification
        require_fresh_sandbox=request.require_fresh_sandbox,
        sandbox_wait_seconds=request.sandbox_wait_seconds,
        idempotency_key=idempotency_key or None,
    )

    # Include sandbox info if available
    sandbox_info = None
    settings = get_settings()
    if session.sandbox_id:
        try:
            sandbox = await sandbox_cls.get(session.sandbox_id)
            if sandbox:
                sandbox_info = SandboxInfo(
                    sandbox_id=sandbox.id,
                    streaming_mode=settings.sandbox_streaming_mode.value,
                    status="initializing",
                )
        except Exception as e:
            logger.debug(f"Could not fetch sandbox info: {e}")

    return APIResponse.success(
        CreateSessionResponse(
            session_id=session.id,
            mode=session.mode,
            research_mode=session.research_mode,
            sandbox=sandbox_info,
            status=session.status,
        )
    )


@router.get("/{session_id}", response_model=APIResponse[GetSessionResponse])
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[GetSessionResponse]:
    session = await agent_service.get_session_full(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    return APIResponse.success(
        GetSessionResponse(
            session_id=session.id,
            title=session.title,
            status=session.status,
            source=getattr(session, "source", "web"),
            research_mode=session.research_mode,
            streaming_mode=get_settings().sandbox_streaming_mode.value,
            events=await EventMapper.events_to_sse_events(session.events),
            is_shared=session.is_shared,
        )
    )


@router.post("/{session_id}/report/pdf")
async def download_session_report_pdf(
    session_id: str,
    request: ReportPdfDownloadRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Generate a report PDF for a session-owned report payload."""
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    markdown_content = request.content.strip()
    if not markdown_content:
        raise BadRequestError("Report content cannot be empty")

    settings = get_settings()
    payload = ReportPdfPayload(
        title=request.title.strip() or "Report",
        markdown_content=markdown_content,
        sources=request.sources,
        author=(request.author or "Pythinker AI Agent").strip() or "Pythinker AI Agent",
        include_toc=settings.telegram_pdf_include_toc,
        toc_min_sections=settings.telegram_pdf_toc_min_sections,
        preferred_font=settings.telegram_pdf_unicode_font,
    )
    renderer = build_configured_pdf_renderer(settings=settings)
    pdf_bytes = await renderer.render(payload)

    filename = _build_safe_pdf_filename(payload.title)
    encoded_filename = quote(filename, safe="")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Cache-Control": "no-store",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.get("/{session_id}/status", response_model=APIResponse[SessionStatusResponse])
async def get_session_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[SessionStatusResponse]:
    """Lightweight session status check for frontend polling."""
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    return APIResponse.success(
        SessionStatusResponse(
            session_id=session.id,
            status=session.status,
            sandbox_id=session.sandbox_id,
            streaming_mode=get_settings().sandbox_streaming_mode.value,
            created_at=session.created_at.timestamp() if session.created_at else None,
        )
    )


@router.get("/active/current", response_model=APIResponse[ActiveSessionResponse])
async def get_active_session(
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[ActiveSessionResponse]:
    """Get the currently active (RUNNING/INITIALIZING) session for the user.

    Returns null session if no active session exists.
    """
    sessions = await agent_service.get_all_sessions(current_user.id)
    active_statuses = {"running", "initializing", "pending"}
    active = next(
        (s for s in sessions if s.status in active_statuses),
        None,
    )
    if not active:
        return APIResponse.success(ActiveSessionResponse(session=None))
    return APIResponse.success(
        ActiveSessionResponse(
            session=SessionStatusResponse(
                session_id=active.id,
                status=active.status,
                sandbox_id=active.sandbox_id,
                streaming_mode=get_settings().sandbox_streaming_mode.value,
                created_at=active.created_at.timestamp() if active.created_at else None,
            )
        )
    )


@router.delete("/{session_id}", response_model=APIResponse[DeleteSessionResponse | None])
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
) -> APIResponse[DeleteSessionResponse | None]:
    await agent_service.delete_session(session_id, current_user.id)
    cleanup_warnings: list[str] = []
    try:
        deleted = await screenshot_query_service.delete_by_session(session_id)
        if deleted:
            logger.info("Deleted %d screenshots for session %s", deleted, session_id)
    except Exception as e:
        warning_msg = f"Screenshot cleanup failed: {e}"
        cleanup_warnings.append(warning_msg)
        logger.warning("Failed to cleanup screenshots for session %s: %s", session_id, e)

    if cleanup_warnings:
        return APIResponse.success(data=DeleteSessionResponse(warnings=cleanup_warnings))
    return APIResponse.success()


@router.post("/{session_id}/stop", response_model=APIResponse[None])
async def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.stop_session(session_id, current_user.id)
    return APIResponse.success()


@router.post("/{session_id}/cancel", status_code=202)
async def cancel_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, str]:
    """Request graceful cancellation of a running session.

    Signals the active AgentTaskRunner to stop between steps via the
    cooperative CancellationToken already used for SSE disconnect.
    Returns 202 Accepted immediately; the flow transitions to
    'cancelled' asynchronously.
    """
    agent_service.request_cancellation(session_id)
    logger.info("Cancellation requested for session %s by user %s", session_id, current_user.id)
    return {"status": "cancelling", "session_id": session_id}


@router.post("/{session_id}/pause", response_model=APIResponse[None])
async def pause_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    """Pause a session for user takeover

    This endpoint pauses the agent execution so the user can take control
    of the browser live preview without conflicts.
    """
    await agent_service.pause_session(session_id, current_user.id)
    return APIResponse.success()


@router.post("/{session_id}/resume", response_model=APIResponse[None])
async def resume_session(
    session_id: str,
    request: ResumeSessionRequest = ResumeSessionRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    """Resume a paused session after user takeover

    This endpoint resumes the agent execution after the user finishes
    their takeover session. Optionally accepts context about changes
    made during takeover and persist_login_state flag.
    """
    await agent_service.resume_session(
        session_id, current_user.id, context=request.context, persist_login_state=request.persist_login_state
    )
    return APIResponse.success()


@router.post("/{session_id}/takeover/start", response_model=APIResponse[TakeoverStatusResponse])
async def start_takeover(
    session_id: str,
    request: TakeoverStartRequest = TakeoverStartRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[TakeoverStatusResponse]:
    """Start browser takeover for a session.

    Pauses the agent first, then transitions to takeover_active state.
    Idempotent: returns current state if takeover already active.
    """
    await agent_service.start_takeover(session_id, current_user.id, reason=request.reason or "manual")
    status = await agent_service.get_takeover_status(session_id, current_user.id)
    return APIResponse.success(
        TakeoverStatusResponse(
            session_id=status["session_id"],
            takeover_state=status["takeover_state"],
            reason=status["reason"],
        )
    )


@router.post("/{session_id}/takeover/end", response_model=APIResponse[TakeoverStatusResponse])
async def end_takeover(
    session_id: str,
    request: TakeoverEndRequest = TakeoverEndRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[TakeoverStatusResponse]:
    """End browser takeover for a session.

    Optionally resumes the agent, injects context, and persists login state.
    Idempotent: returns idle state if takeover already ended.
    """
    await agent_service.end_takeover(
        session_id,
        current_user.id,
        context=request.context,
        persist_login_state=request.persist_login_state,
        resume_agent=request.resume_agent,
    )
    status = await agent_service.get_takeover_status(session_id, current_user.id)
    return APIResponse.success(
        TakeoverStatusResponse(
            session_id=status["session_id"],
            takeover_state=status["takeover_state"],
            reason=status["reason"],
        )
    )


@router.get("/{session_id}/takeover/status", response_model=APIResponse[TakeoverStatusResponse])
async def get_takeover_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[TakeoverStatusResponse]:
    """Get the current takeover state for a session."""
    status = await agent_service.get_takeover_status(session_id, current_user.id)
    return APIResponse.success(
        TakeoverStatusResponse(
            session_id=status["session_id"],
            takeover_state=status["takeover_state"],
            reason=status["reason"],
        )
    )


async def _resolve_user_sandbox_for_session(
    session_id: str,
    user_id: str,
    agent_service: AgentService,
    sandbox_cls: type[Sandbox],
) -> Sandbox:
    session = await agent_service.get_session(session_id, user_id)
    if not session:
        raise NotFoundError("Session not found")
    if not session.sandbox_id:
        raise NotFoundError("Session has no sandbox")
    sandbox = await sandbox_cls.get(session.sandbox_id)
    if not sandbox:
        raise NotFoundError("Sandbox not found")
    return sandbox


@router.post(
    "/{session_id}/takeover/navigation/{action}",
    response_model=APIResponse[TakeoverNavigationResponse],
)
async def takeover_navigation_action(
    session_id: str,
    action: Literal["back", "forward", "reload", "stop"],
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> APIResponse[TakeoverNavigationResponse]:
    """Execute browser navigation action during takeover."""
    sandbox = await _resolve_user_sandbox_for_session(session_id, current_user.id, agent_service, sandbox_cls)
    url = f"{sandbox.base_url}/api/v1/navigation/{action}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=_sandbox_http_headers())
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("Sandbox navigation action failed: %s %s", action, _safe_exc_text(e))
        raise HTTPException(status_code=502, detail=f"Sandbox navigation action failed: {action}") from e
    except httpx.RequestError as e:
        logger.error("Sandbox navigation unavailable for action %s: %s", action, _safe_exc_text(e))
        raise HTTPException(status_code=502, detail="Sandbox navigation unavailable") from e

    response_data = {}
    with contextlib.suppress(Exception):
        response_data = response.json()

    return APIResponse.success(
        TakeoverNavigationResponse(
            ok=bool(response_data.get("ok", True)),
            action=action,
            message=response_data.get("message"),
        )
    )


@router.get(
    "/{session_id}/takeover/navigation/history",
    response_model=APIResponse[TakeoverNavigationHistoryResponse],
)
async def takeover_navigation_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> APIResponse[TakeoverNavigationHistoryResponse]:
    """Fetch browser navigation history for takeover URL-bar sync."""
    sandbox = await _resolve_user_sandbox_for_session(session_id, current_user.id, agent_service, sandbox_cls)
    url = f"{sandbox.base_url}/api/v1/navigation/history"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=_sandbox_http_headers())
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as e:
        logger.error("Sandbox navigation history request failed: %s", _safe_exc_text(e))
        raise HTTPException(status_code=502, detail="Sandbox navigation history failed") from e
    except httpx.RequestError as e:
        logger.error("Sandbox navigation history unavailable: %s", _safe_exc_text(e))
        raise HTTPException(status_code=502, detail="Sandbox navigation history unavailable") from e
    except Exception as e:
        logger.error("Sandbox navigation history parse failure: %s", _safe_exc_text(e))
        raise HTTPException(status_code=502, detail="Invalid sandbox navigation history response") from e

    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    safe_entries: list[TakeoverNavigationHistoryEntry] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            safe_entries.append(
                TakeoverNavigationHistoryEntry(
                    id=int(entry.get("id", -1)),
                    url=str(entry.get("url", "")),
                    title=str(entry.get("title", "")),
                )
            )
        except Exception as _entry_exc:
            logger.debug("Skipping malformed navigation history entry: %s", _entry_exc)
            continue

    return APIResponse.success(
        TakeoverNavigationHistoryResponse(
            current_index=int(payload.get("current_index", 0)) if isinstance(payload, dict) else 0,
            entries=safe_entries,
        )
    )


@router.patch("/{session_id}/rename", response_model=APIResponse[None])
async def rename_session(
    session_id: str,
    request: RenameSessionRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.rename_session(session_id, current_user.id, request.title.strip())
    return APIResponse.success()


@router.post("/{session_id}/clear_unread_message_count", response_model=APIResponse[None])
async def clear_unread_message_count(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.clear_unread_message_count(session_id, current_user.id)
    return APIResponse.success()


@router.get("", response_model=APIResponse[ListSessionResponse])
async def get_all_sessions(
    source: str | None = Query(default=None, description="Filter by session source (e.g. telegram, web)"),
    q: str | None = Query(default=None, description="Case-insensitive search over title/latest message/status"),
    status: SessionStatus | None = Query(default=None, description="Filter by session status"),
    limit: int = Query(default=200, ge=1, le=500, description="Maximum number of sessions to return"),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[ListSessionResponse]:
    sessions = await agent_service.get_all_sessions(current_user.id)
    filtered_sessions = _filter_sessions_for_listing(
        sessions,
        source=source,
        query_text=q,
        status=status,
        limit=limit,
    )
    session_items = [
        ListSessionItem(
            session_id=session.id,
            title=session.title,
            status=session.status,
            unread_message_count=session.unread_message_count,
            latest_message=session.latest_message,
            latest_message_at=int(session.latest_message_at.timestamp()) if session.latest_message_at else None,
            is_shared=session.is_shared,
            source=getattr(session, "source", "web"),
        )
        for session in filtered_sessions
    ]
    return APIResponse.success(ListSessionResponse(sessions=session_items))


@router.post("")
async def stream_sessions(
    source: str | None = Query(default=None, description="Filter by session source (e.g. telegram, web)"),
    q: str | None = Query(default=None, description="Case-insensitive search over title/latest message/status"),
    status: SessionStatus | None = Query(default=None, description="Filter by session status"),
    limit: int = Query(default=200, ge=1, le=500, description="Maximum number of sessions to stream"),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        last_hash: str | None = None
        stream_key = await register_active_stream(
            session_id=f"user:{current_user.id}",
            endpoint="stream_sessions",
        )
        try:
            while True:
                sessions = await agent_service.get_all_sessions(current_user.id)
                filtered_sessions = _filter_sessions_for_listing(
                    sessions,
                    source=source,
                    query_text=q,
                    status=status,
                    limit=limit,
                )
                session_items = [
                    ListSessionItem(
                        session_id=session.id,
                        title=session.title,
                        status=session.status,
                        unread_message_count=session.unread_message_count,
                        latest_message=session.latest_message,
                        latest_message_at=int(session.latest_message_at.timestamp())
                        if session.latest_message_at
                        else None,
                        is_shared=session.is_shared,
                        source=getattr(session, "source", "web"),
                    )
                    for session in filtered_sessions
                ]
                data = ListSessionResponse(sessions=session_items).model_dump_json()
                current_hash = hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()
                # Only send if data actually changed
                if current_hash != last_hash:
                    yield ServerSentEvent(event="sessions", data=data)
                    last_hash = current_hash
                else:
                    # Keep-alive frame so proxies don't time out idle streams.
                    yield ServerSentEvent(comment="heartbeat")
                await asyncio.sleep(SESSION_POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.debug("Session SSE stream cancelled")
            return
        finally:
            await unregister_active_stream(stream_key)

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    request: ChatRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    token_service: TokenService = Depends(get_token_service),
) -> EventSourceResponse:
    """Chat endpoint with SSE streaming.

    Phase 3 Enhancement: Improved disconnect handling and send timeout.
    When feature_sse_v2 is enabled, uses enhanced event streaming with
    disconnect detection and timeouts for better reliability.
    """
    # Validate session exists before starting SSE stream (returns 404 instead of 200 with error)
    # Use full payload for completed/failed sessions so resume_cursor replay has events.
    session = await agent_service.get_session_full(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    # New stream means client is connected again; cancel any pending disconnect teardown.
    _cancel_pending_disconnect_cancellation(session_id)
    heartbeat_interval_seconds = SSE_HEARTBEAT_INTERVAL_SECONDS
    protocol_headers = _build_sse_protocol_headers(heartbeat_interval_seconds=heartbeat_interval_seconds)

    # Short-circuit for completed/failed sessions ONLY when there is no fresh user
    # input (pure reconnect / page-refresh).  When the request carries a message,
    # attachments, skills, or follow-up context the call must reach
    # agent_service.chat() so the domain-level reactivation path can create a
    # new task and re-initialise the sandbox.
    has_fresh_input = bool(
        (request.message and request.message.strip())
        or request.attachments
        or request.skills
        or (request.thinking_mode and request.thinking_mode != "auto")
        or request.follow_up
    )
    if session.status in ("completed", "failed") and not has_fresh_input:
        resume_cursor = request.event_id or http_request.headers.get("Last-Event-ID")
        logger.info(
            "Session %s already %s with no new input (resume_cursor=%s)",
            session_id,
            session.status,
            resume_cursor,
        )

        replay_events: list[ServerSentEvent] = []
        stale_resume_gap_event: ServerSentEvent | None = None
        normalized_terminal_status = _normalize_session_status(session.status)
        if resume_cursor:
            session_events = getattr(session, "events", None) or []
            sse_events = await EventMapper.events_to_sse_events(session_events)
            cursor_index = next(
                (
                    index
                    for index, sse_event in enumerate(sse_events)
                    if sse_event.data and getattr(sse_event.data, "event_id", None) == resume_cursor
                ),
                None,
            )
            if cursor_index is not None:
                pm.record_sse_resume_cursor_state(endpoint="chat", state="found")
                replay_events.extend(
                    ServerSentEvent(
                        event=sse_event.event,
                        data=sse_event.data.model_dump_json() if sse_event.data else None,
                    )
                    for sse_event in sse_events[cursor_index + 1 :]
                )
            else:
                pm.record_sse_resume_cursor_state(endpoint="chat", state="stale")
                pm.record_sse_resume_cursor_fallback(endpoint="chat", reason="stale_cursor")
                logger.info(
                    "Resume cursor %s not found in completed session %s; falling back to done-only response",
                    resume_cursor,
                    session_id,
                )
                stale_gap = ErrorEvent(
                    error="Reconnect gap detected. Resume cursor not found; returning latest session state.",
                    error_type="stream_gap",
                    error_code="stream_gap_detected",
                    error_category="transport",
                    severity="warning",
                    recoverable=True,
                    can_resume=True,
                    retry_hint="Session is terminal; refreshed state includes the latest available output.",
                    details={
                        "session_id": session_id,
                        "resume_cursor": resume_cursor,
                        "reason": "stale_cursor",
                        "status": normalized_terminal_status,
                    },
                )
                sse_gap = await EventMapper.event_to_sse_event(stale_gap)
                if sse_gap:
                    stale_resume_gap_event = ServerSentEvent(
                        event=sse_gap.event,
                        data=sse_gap.data.model_dump_json() if sse_gap.data else None,
                    )
        else:
            pm.record_sse_resume_cursor_state(endpoint="chat", state="absent")

        if replay_events:

            async def completed_generator() -> AsyncGenerator[ServerSentEvent, None]:
                if stale_resume_gap_event:
                    yield stale_resume_gap_event
                for replay_event in replay_events:
                    yield replay_event

            return EventSourceResponse(completed_generator(), headers=protocol_headers)

        done_event = DoneEvent(title=session.title or "Task completed")
        sse_done = await EventMapper.event_to_sse_event(done_event)

        async def completed_generator() -> AsyncGenerator[ServerSentEvent, None]:
            if stale_resume_gap_event:
                yield stale_resume_gap_event
            if sse_done:
                yield ServerSentEvent(
                    event=sse_done.event,
                    data=sse_done.data.model_dump_json() if sse_done.data else None,
                )

        return EventSourceResponse(completed_generator(), headers=protocol_headers)

    # ---------------------------------------------------------------------------
    # Short-circuit for active sessions owned by another process (e.g. gateway).
    #
    # When the gateway runs a Telegram task, the task lives in the gateway's
    # in-memory registry.  The backend's AgentDomainService has no visibility
    # into it — _get_task() returns None — and the "reconnect race" heuristic
    # in process_message() would incorrectly emit DoneEvent and tear down the
    # session while the gateway is still processing.
    #
    # Instead we poll MongoDB for new events written by the gateway and stream
    # them to the frontend until the session reaches a terminal state.
    # ---------------------------------------------------------------------------
    session_source = getattr(session, "source", "web") or "web"
    normalized_session_status = _normalize_session_status(session.status)
    is_remote_active_session = (
        normalized_session_status in SSE_NON_TERMINAL_STATUSES and session_source != "web" and not has_fresh_input
    )
    if is_remote_active_session:
        logger.info(
            "Session %s is %s on remote process (source=%s) — "
            "streaming events via MongoDB polling instead of process_message()",
            session_id,
            normalized_session_status,
            session_source,
        )

        _remote_poll_interval = 3.0  # seconds between MongoDB polls
        _remote_poll_timeout = 600.0  # max 10 minutes before giving up
        _remote_heartbeat_interval = 25.0  # keep SSE alive

        resume_cursor = request.event_id or http_request.headers.get("Last-Event-ID")

        async def remote_session_generator() -> AsyncGenerator[ServerSentEvent, None]:
            """Poll MongoDB for events from a gateway-owned session."""
            sent_event_ids: set[str] = set()
            elapsed = 0.0
            last_heartbeat = 0.0

            # Pre-populate sent set with events the frontend already has
            initial_events = getattr(session, "events", None) or []
            if resume_cursor:
                found_cursor = False
                for ev in initial_events:
                    ev_id = getattr(ev, "id", None) or getattr(ev, "event_id", None)
                    if not ev_id:
                        continue
                    ev_id_str = str(ev_id)
                    sent_event_ids.add(ev_id_str)
                    if ev_id_str == resume_cursor:
                        found_cursor = True
                        break
                if not found_cursor:
                    # Cursor not found — mark all existing events as sent
                    for ev in initial_events:
                        ev_id = getattr(ev, "id", None) or getattr(ev, "event_id", None)
                        if ev_id:
                            sent_event_ids.add(str(ev_id))
            else:
                # No cursor — mark all existing events as already sent
                for ev in initial_events:
                    ev_id = getattr(ev, "id", None) or getattr(ev, "event_id", None)
                    if ev_id:
                        sent_event_ids.add(str(ev_id))

            while elapsed < _remote_poll_timeout:
                if await http_request.is_disconnected():
                    logger.info("Remote session poller: client disconnected for %s", session_id)
                    return

                # Heartbeat to keep SSE alive
                now = asyncio.get_running_loop().time()
                if now - last_heartbeat >= _remote_heartbeat_interval:
                    yield ServerSentEvent(comment="heartbeat")
                    last_heartbeat = now

                await asyncio.sleep(_remote_poll_interval)
                elapsed += _remote_poll_interval

                # Re-fetch session from MongoDB
                fresh_session = await agent_service.get_session_full(session_id, current_user.id)
                if not fresh_session:
                    logger.warning("Remote session poller: session %s disappeared", session_id)
                    return

                # Stream any new events
                fresh_events = getattr(fresh_session, "events", None) or []
                for ev in fresh_events:
                    ev_id = getattr(ev, "id", None) or getattr(ev, "event_id", None)
                    ev_id_str = str(ev_id) if ev_id else None
                    if ev_id_str and ev_id_str in sent_event_ids:
                        continue
                    if ev_id_str:
                        sent_event_ids.add(ev_id_str)

                    sse_event = await EventMapper.event_to_sse_event(ev)
                    if sse_event:
                        yield ServerSentEvent(
                            event=sse_event.event,
                            data=sse_event.data.model_dump_json() if sse_event.data else None,
                        )

                # Check for terminal status
                normalized_status = _normalize_session_status(fresh_session.status)
                if normalized_status in ("completed", "failed", "cancelled"):
                    logger.info(
                        "Remote session poller: session %s reached %s",
                        session_id,
                        normalized_status,
                    )
                    # Emit a final done event if not already in the events
                    done_event = DoneEvent(title=fresh_session.title or "Task completed")
                    sse_done = await EventMapper.event_to_sse_event(done_event)
                    if sse_done:
                        yield ServerSentEvent(
                            event=sse_done.event,
                            data=sse_done.data.model_dump_json() if sse_done.data else None,
                        )
                    return

            # Timeout — don't tear down, just close the stream gracefully
            logger.info(
                "Remote session poller: timeout after %.0fs for session %s (still %s)",
                _remote_poll_timeout,
                session_id,
                session.status,
            )
            done_event = DoneEvent(
                title=session.title or "Session active",
                summary="Session is still being processed. Refresh to see latest results.",
            )
            sse_done = await EventMapper.event_to_sse_event(done_event)
            if sse_done:
                yield ServerSentEvent(
                    event=sse_done.event,
                    data=sse_done.data.model_dump_json() if sse_done.data else None,
                )

        return EventSourceResponse(remote_session_generator(), headers=protocol_headers)

    settings = get_settings()
    use_sse_v2 = settings.feature_sse_v2
    disconnect_cancellation_grace_seconds = SSE_DISCONNECT_CANCELLATION_GRACE_SECONDS
    with contextlib.suppress(Exception):
        disconnect_cancellation_grace_seconds = float(
            getattr(
                settings,
                "sse_disconnect_cancellation_grace_seconds",
                SSE_DISCONNECT_CANCELLATION_GRACE_SECONDS,
            )
        )
    disconnect_cancellation_grace_seconds = max(0.0, disconnect_cancellation_grace_seconds)
    raw_diag_header = None
    with contextlib.suppress(Exception):
        raw_diag_header = http_request.headers.get("X-Pythinker-SSE-Debug")
    sse_diag_enabled = bool(getattr(settings, "debug", False)) or _is_truthy_header(raw_diag_header)

    def log_sse_diag(stage: str, **details: object) -> None:
        if not sse_diag_enabled:
            return
        detail_parts = [f"{key}={details[key]!r}" for key in sorted(details)]
        detail_suffix = f" {' '.join(detail_parts)}" if detail_parts else ""
        logger.info("[SSE-DIAG] stage=%s session_id=%s%s", stage, session_id, detail_suffix)

    # SSE send timeout (Phase 3: prevents hanging on slow clients)
    send_timeout = 60.0 if use_sse_v2 else None  # 60s for slow networks

    # Heartbeat interval: keep connection alive and prevent "stuck" feeling during long ops
    # Set to 30s to prevent SSE timeout during browser recovery (can take >120s)
    heartbeat_interval_seconds = SSE_HEARTBEAT_INTERVAL_SECONDS
    resume_cursor = request.event_id or http_request.headers.get("Last-Event-ID")
    log_sse_diag(
        "stream_config",
        use_sse_v2=use_sse_v2,
        send_timeout=send_timeout,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        resume_event_id=resume_cursor,
        has_message=bool(request.message and request.message.strip()),
    )
    if resume_cursor:
        await record_stream_reconnection(session_id=session_id, endpoint="chat")
        log_sse_diag("resume_cursor_detected", resume_cursor=resume_cursor)

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        stream_started_at = asyncio.get_running_loop().time()
        stream_event_count = 0
        heartbeat_count = 0
        close_reason = "unknown"
        last_emitted_event_id: str | None = None  # Updated to UUID as real events are sent.
        reconnect_first_non_heartbeat_seconds: float | None = None
        disconnect_event = asyncio.Event()
        cancel_token = CancellationToken(event=disconnect_event, session_id=session_id)
        guard = StreamGuard(
            session_id=session_id,
            endpoint="chat",
            cancel_token=cancel_token,
        )
        stream_metrics = guard.get_metrics()
        pm.record_sse_stream_open(endpoint="chat")

        try:
            # INSTANT FEEDBACK: Emit ProgressEvent immediately (<100ms)
            # This gives users visual feedback before any processing begins
            instant_ack = ProgressEvent(
                phase=PlanningPhase.RECEIVED,
                message="Got it! Working on your request...",
                progress_percent=5,
            )
            sse_event = await EventMapper.event_to_sse_event(instant_ack)
            if sse_event:
                payload = ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json() if sse_event.data else None,
                )
                yield payload
                stream_event_count += 1
                stream_metrics.record_event(instant_ack)
                pm.record_sse_stream_event(
                    endpoint="chat",
                    event_type=instant_ack.type,
                    phase=_event_phase_label(instant_ack),
                )
                ack_event_id = getattr(sse_event.data, "event_id", None) if sse_event.data else None
                if ack_event_id:
                    last_emitted_event_id = str(ack_event_id)
                log_sse_diag("instant_ack_sent", event=sse_event.event, event_id=ack_event_id)

            # Convert FollowUpContext to dict for service layer
            follow_up_dict = None
            if request.follow_up:
                follow_up_dict = {
                    "selected_suggestion": request.follow_up.selected_suggestion,
                    "anchor_event_id": request.follow_up.anchor_event_id,
                    "source": request.follow_up.source,
                }

            # Extract token expiry once for heartbeat enrichment (Phase 4: SSE token awareness)
            _token_expires_at: int | None = None
            _auth_header = http_request.headers.get("authorization", "")
            if _auth_header.startswith("Bearer "):
                _token_exp = token_service.get_token_expiration(_auth_header[7:])
                if _token_exp:
                    _token_expires_at = int(_token_exp.timestamp())

            # Heartbeat: send keep-alive events during long agent operations
            # Prevents frontend "stale" detection and proxy/timeout disconnects (SSE best practice)
            heartbeat = ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message="",
                progress_percent=None,
            )
            sse_heartbeat = await EventMapper.event_to_sse_event(heartbeat)
            if sse_heartbeat and sse_heartbeat.data:
                _hb_data = json.loads(sse_heartbeat.data.model_dump_json())
                if _token_expires_at:
                    _hb_data["token_expires_at"] = _token_expires_at
                heartbeat_sse = ServerSentEvent(
                    event=sse_heartbeat.event,
                    data=json.dumps(_hb_data),
                )
            elif sse_heartbeat:
                heartbeat_sse = ServerSentEvent(
                    event=sse_heartbeat.event,
                    data=None,
                )
            else:
                heartbeat_sse = None

            chat_stream = agent_service.chat(
                session_id=session_id,
                user_id=current_user.id,
                message=request.message,
                timestamp=datetime.fromtimestamp(request.timestamp, tz=UTC) if request.timestamp else None,
                event_id=resume_cursor,
                attachments=request.attachments,
                skills=request.skills,
                thinking_mode=request.thinking_mode,
                follow_up=follow_up_dict,
            )
            stream_iter = guard.wrap(chat_stream).__aiter__()
            next_event_task: asyncio.Task | None = asyncio.create_task(stream_iter.__anext__())
            heartbeat_task: asyncio.Task | None = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))
            stream_exhausted = False

            while not stream_exhausted:
                # Phase 3: Check for client disconnect before sending
                if use_sse_v2 and await http_request.is_disconnected():
                    logger.info(f"Client disconnected during chat stream: {session_id}")
                    disconnect_event.set()
                    close_reason = "client_disconnected"
                    log_sse_diag("disconnect_detected", event_count=stream_event_count, heartbeat_count=heartbeat_count)
                    break

                done: set[asyncio.Task] = set()
                pending: set[asyncio.Task] = set()
                done, pending = await asyncio.wait(
                    {t for t in (next_event_task, heartbeat_task) if t is not None},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if heartbeat_task in done:
                    # Heartbeat fired: send keep-alive (SSE comment) to prevent proxy timeouts
                    # Do NOT cancel next_event_task - it is still waiting for the real event
                    heartbeat_task = None
                    if heartbeat_sse:
                        yield heartbeat_sse
                    else:
                        yield ServerSentEvent(comment="heartbeat")
                    heartbeat_count += 1
                    stream_event_count += 1
                    stream_metrics.record_event(heartbeat)
                    pm.record_sse_stream_heartbeat(endpoint="chat")
                    pm.record_sse_stream_event(
                        endpoint="chat",
                        event_type=heartbeat.type,
                        phase=_event_phase_label(heartbeat),
                    )
                    log_sse_diag(
                        "heartbeat_sent",
                        heartbeat_count=heartbeat_count,
                        stream_event_count=stream_event_count,
                        last_event_id=last_emitted_event_id,
                    )
                    heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))
                    # next_event_task unchanged - still waiting for real event
                else:
                    # Real event arrived
                    for t in pending:
                        t.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await t
                    heartbeat_task = None

                    try:
                        event = next_event_task.result()
                    except StopAsyncIteration:
                        stream_exhausted = True
                        close_reason = "stream_exhausted"
                        log_sse_diag(
                            "stream_exhausted",
                            event_count=stream_event_count,
                            heartbeat_count=heartbeat_count,
                        )
                        break
                    except RuntimeError as _rte:
                        # PEP 479: StopAsyncIteration raised inside an async generator
                        # is re-wrapped as RuntimeError("async generator raised
                        # StopAsyncIteration"). Treat it as normal stream exhaustion so
                        # it does not surface as an unhandled ExceptionGroup in sse-starlette.
                        if "StopAsyncIteration" in str(_rte):
                            stream_exhausted = True
                            close_reason = "stream_exhausted"
                            log_sse_diag(
                                "stream_exhausted",
                                event_count=stream_event_count,
                                heartbeat_count=heartbeat_count,
                            )
                            break
                        raise

                    logger.debug(f"Received event from chat: {event}")
                    if (
                        resume_cursor
                        and reconnect_first_non_heartbeat_seconds is None
                        and not _is_heartbeat_progress_event(event)
                    ):
                        reconnect_first_non_heartbeat_seconds = asyncio.get_running_loop().time() - stream_started_at
                        pm.record_sse_reconnect_first_non_heartbeat(
                            endpoint="chat",
                            latency_seconds=reconnect_first_non_heartbeat_seconds,
                        )
                    sse_event = await EventMapper.event_to_sse_event(event)
                    logger.debug(f"Received event: {sse_event}")
                    if sse_event:
                        event_data = sse_event.data.model_dump_json() if sse_event.data else None
                        event_id_val = getattr(sse_event.data, "event_id", None) if sse_event.data else None
                        if event_id_val:
                            last_emitted_event_id = str(event_id_val)
                        log_sse_diag(
                            "event_ready",
                            event=sse_event.event,
                            event_id=event_id_val,
                            send_timeout=send_timeout,
                        )
                        sse_kwargs: dict = {"event": sse_event.event, "data": event_data}
                        # Only expose Redis-format IDs as the SSE `id:` field so the browser's
                        # Last-Event-ID is always a valid Redis stream resume cursor.
                        # UUID-format IDs (synthetic gap warnings, beacons) are tracked
                        # internally via last_emitted_event_id but never sent to the browser.
                        if event_id_val and _REDIS_STREAM_ID_RE.match(str(event_id_val)):
                            sse_kwargs["id"] = str(event_id_val)
                        sse_payload = ServerSentEvent(**sse_kwargs)
                        if send_timeout:
                            try:
                                async with asyncio.timeout(send_timeout):
                                    yield sse_payload
                                stream_event_count += 1
                                pm.record_sse_stream_event(
                                    endpoint="chat",
                                    event_type=getattr(event, "type", "unknown"),
                                    phase=_event_phase_label(event),
                                )
                            except TimeoutError:
                                logger.warning(f"SSE send timeout for session {session_id}")
                                close_reason = "send_timeout"
                                stream_metrics.record_error(
                                    StreamErrorCode.STREAM_TIMEOUT,
                                    StreamErrorCategory.TIMEOUT,
                                    recoverable=True,
                                    message="SSE send timeout",
                                )
                                pm.record_sse_stream_error(endpoint="chat", error_type="send_timeout")
                                pm.record_sse_stream_retry_suggestion(endpoint="chat", reason="send_timeout")
                                log_sse_diag(
                                    "send_timeout",
                                    event=sse_event.event,
                                    event_id=event_id_val,
                                    event_count=stream_event_count,
                                    heartbeat_count=heartbeat_count,
                                )
                                break
                        else:
                            yield sse_payload
                            stream_event_count += 1
                            pm.record_sse_stream_event(
                                endpoint="chat",
                                event_type=getattr(event, "type", "unknown"),
                                phase=_event_phase_label(event),
                            )

                    next_event_task = asyncio.create_task(stream_iter.__anext__())
                    heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))

            # Cleanup stream and pending tasks
            for task in (next_event_task, heartbeat_task):
                if task is not None:
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    # Retrieve result to suppress "Task exception was never retrieved"
                    with contextlib.suppress(Exception, asyncio.CancelledError):
                        task.result()
            try:
                await stream_iter.aclose()
            except Exception as _aclose_exc:
                logger.warning("stream_iter.aclose() raised for session %s: %s", session_id, _aclose_exc)
        except asyncio.CancelledError:
            # Client disconnected - log and gracefully terminate
            # CRITICAL FIX: Close the stream_iter to clean up orphaned agent_service.chat()
            for task in (next_event_task, heartbeat_task):
                if task is not None:
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    with contextlib.suppress(Exception, asyncio.CancelledError):
                        task.result()
            try:
                await stream_iter.aclose()
            except Exception as _aclose_exc:
                logger.warning("stream_iter.aclose() raised for session %s: %s", session_id, _aclose_exc)
            logger.warning(f"Chat stream cancelled for session {session_id} (client disconnected)")
            disconnect_event.set()
            close_reason = "generator_cancelled"
            stream_metrics.record_cancellation()
            stream_metrics.record_error(
                StreamErrorCode.CANCELLED,
                StreamErrorCategory.TRANSPORT,
                recoverable=True,
                message="Chat stream generator cancelled by client disconnect",
            )
            log_sse_diag("generator_cancelled", event_count=stream_event_count, heartbeat_count=heartbeat_count)
            raise
        except Exception as e:
            logger.error(f"Error in chat stream for session {session_id}: {e}")
            disconnect_event.set()
            close_reason = "stream_exception"
            safe_error_text = _safe_exc_text(e)
            normalized_error_type = type(e).__name__.lower()
            stream_metrics.record_error(
                StreamErrorCode.INTERNAL_ERROR,
                StreamErrorCategory.INTERNAL,
                recoverable=True,
                message=safe_error_text,
            )
            pm.record_sse_stream_error(endpoint="chat", error_type=normalized_error_type)
            pm.record_sse_stream_retry_suggestion(endpoint="chat", reason="stream_exception")
            log_sse_diag(
                "stream_exception",
                error_type=type(e).__name__,
                error=str(e),
                event_count=stream_event_count,
                heartbeat_count=heartbeat_count,
            )
            # Yield schema-compliant error event before closing so frontend
            # ErrorEventData handler receives the expected `error` field.
            error_event = ErrorEvent(
                error=f"Stream error: {safe_error_text}",
                error_type=normalized_error_type,
                error_code="stream_exception",
                error_category="transport",
                severity="error",
                recoverable=True,
                retry_hint="Connection interrupted. Reconnecting may resume progress.",
                retry_after_ms=1500,
                can_resume=True,
                checkpoint_event_id=last_emitted_event_id,
                details={"session_id": session_id},
            )
            sse_err = await EventMapper.event_to_sse_event(error_event)
            if sse_err:
                yield ServerSentEvent(
                    event=sse_err.event,
                    data=sse_err.data.model_dump_json() if sse_err.data else None,
                )
                stream_event_count += 1
                stream_metrics.record_event(error_event)
                pm.record_sse_stream_event(
                    endpoint="chat",
                    event_type=error_event.type,
                    phase=_event_phase_label(error_event),
                )
        finally:
            disconnect_event.set()
            elapsed_seconds = asyncio.get_running_loop().time() - stream_started_at
            if close_reason in {"unknown", "stream_exhausted"}:
                final_status: object | None = getattr(session, "status", None)
                with contextlib.suppress(Exception):
                    refreshed_session = await agent_service.get_session(session_id, current_user.id)
                    if refreshed_session is not None:
                        final_status = getattr(refreshed_session, "status", final_status)
                close_reason = _resolve_stream_exhausted_close_reason(final_status)
                if close_reason == "stream_exhausted_non_terminal":
                    logger.debug(
                        "SSE stream exhausted while session is non-terminal (session=%s status=%s)",
                        session_id,
                        _normalize_session_status(final_status),
                    )
            if close_reason in {"client_disconnected", "generator_cancelled"}:
                stream_metrics.record_cancellation()
            with contextlib.suppress(Exception):
                await record_stream_metrics(stream_metrics)
            pm.record_sse_stream_close(
                endpoint="chat",
                reason=close_reason,
                duration_seconds=max(0.0, elapsed_seconds),
            )
            log_sse_diag(
                "stream_closed",
                close_reason=close_reason,
                elapsed_seconds=round(elapsed_seconds, 3),
                event_count=stream_event_count,
                heartbeat_count=heartbeat_count,
                last_event_id=last_emitted_event_id,
            )
            # Signal cancellation so agent service can stop background work.
            # Use the request-scoped dependency instance; tolerate lightweight mocks.
            request_cancellation = getattr(agent_service, "request_cancellation", None)
            if callable(request_cancellation):
                if close_reason == "client_disconnected":
                    # A full page refresh also looks like a disconnect to the server.
                    # Defer cancellation briefly so the browser can reconnect with
                    # Last-Event-ID instead of losing the running session mid-task.
                    _schedule_disconnect_cancellation(
                        session_id=session_id,
                        agent_service=agent_service,
                        grace_seconds=disconnect_cancellation_grace_seconds,
                    )
                elif close_reason == "generator_cancelled":
                    # Short grace period (5s) for legitimate reconnection attempts
                    # Reduced from 45s to prevent orphaned background tasks
                    _schedule_disconnect_cancellation(
                        session_id=session_id,
                        agent_service=agent_service,
                        grace_seconds=5.0,  # Reduced from 45s
                    )
                elif close_reason == "stream_exhausted_non_terminal":
                    # Agent is still running — the SSE stream simply exhausted its
                    # current batch of events.  Schedule a deferred cancellation
                    # so the frontend can reconnect within the grace window.
                    # On reconnect, _cancel_pending_disconnect_cancellation()
                    # (called at line 777) will abort the teardown.
                    _non_terminal_grace = getattr(
                        settings,
                        "sse_disconnect_non_terminal_grace_seconds",
                        120.0,
                    )
                    _schedule_disconnect_cancellation(
                        session_id=session_id,
                        agent_service=agent_service,
                        grace_seconds=max(5.0, float(_non_terminal_grace)),
                    )
                else:
                    # Ensure stale deferred cancellations don't race with a successful completion path.
                    _cancel_pending_disconnect_cancellation(session_id)
                    with contextlib.suppress(Exception):
                        request_cancellation(session_id)

    return EventSourceResponse(event_generator(), headers=protocol_headers)


@router.get("/{session_id}/chat/eventsource")
async def chat_eventsource(
    session_id: str,
    http_request: Request,
    event_id: str | None = Query(default=None),
    current_user: User = Depends(get_eventsource_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """EventSource-compatible chat stream for resume/reconnect flows.

    This route mirrors POST /chat behavior but accepts query parameters so
    native browser EventSource clients can reconnect without custom headers.
    """
    chat_request = ChatRequest(event_id=event_id)
    return await chat(
        session_id=session_id,
        request=chat_request,
        http_request=http_request,
        current_user=current_user,
        agent_service=agent_service,
    )


@router.post("/{session_id}/shell", response_model=APIResponse[ShellViewResponse])
async def view_shell(
    session_id: str,
    request: ShellViewRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[ShellViewResponse]:
    """View shell session output

    If the agent does not exist or fails to get shell output, an appropriate exception will be thrown and handled by the global exception handler

    Args:
        session_id: Session ID
        request: Shell view request containing session ID

    Returns:
        APIResponse with shell output
    """
    result = await agent_service.shell_view(session_id, request.session_id, current_user.id)
    return APIResponse.success(result)


@router.post("/{session_id}/file", response_model=APIResponse[FileViewResponse])
async def view_file(
    session_id: str,
    request: FileViewRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[FileViewResponse]:
    """View file content

    If the agent does not exist or fails to get file content, an appropriate exception will be thrown and handled by the global exception handler

    Args:
        session_id: Session ID
        request: File view request containing file path

    Returns:
        APIResponse with file content
    """
    result = await agent_service.file_view(session_id, request.file, current_user.id)
    return APIResponse.success(result)


@router.post("/{session_id}/browse")
async def browse_url(
    session_id: str,
    request: BrowseUrlRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """Navigate browser directly to a URL from search results.

    This endpoint triggers the browser in the sandbox to navigate to the specified URL.
    It provides a faster workflow than having the agent search again, allowing users
    to click on search results and immediately view them in the browser.

    The navigation is executed via the fast-path router for optimal performance.

    Args:
        session_id: Session ID
        request: Browse URL request containing the target URL

    Returns:
        SSE stream of navigation events
    """

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        disconnect_event = asyncio.Event()
        guard = StreamGuard(
            session_id=session_id,
            endpoint="browse",
            cancel_token=CancellationToken(event=disconnect_event, session_id=session_id),
        )
        try:
            raw_stream = agent_service.browse_url(session_id=session_id, user_id=current_user.id, url=request.url)
            async for event in guard.wrap(raw_stream):
                if await http_request.is_disconnected():
                    disconnect_event.set()
                    logger.info("Browse URL client disconnected for session %s", session_id)
                    break
                logger.debug(f"Received browse event: {event}")
                sse_event = await EventMapper.event_to_sse_event(event)
                if sse_event:
                    yield ServerSentEvent(
                        event=sse_event.event, data=sse_event.data.model_dump_json() if sse_event.data else None
                    )
        except asyncio.CancelledError:
            disconnect_event.set()
            logger.info("Browse URL stream cancelled for session %s", session_id)
            raise
        except Exception as e:
            disconnect_event.set()
            logger.error("Browse URL error for session %s: %s", session_id, e)
            # Yield structured error event before closing
            error_event = ErrorEvent(
                error=f"Navigation failed: {str(e)[:100]}",
                error_type="navigation",
                error_code="browse_url_failed",
                error_category="transport",
                recoverable=True,
                retry_hint="Retry the navigation request.",
            )
            sse_err = await EventMapper.event_to_sse_event(error_event)
            if sse_err:
                yield ServerSentEvent(
                    event=sse_err.event, data=sse_err.data.model_dump_json() if sse_err.data else None
                )
        finally:
            disconnect_event.set()
            with contextlib.suppress(Exception):
                await record_stream_metrics(guard.get_metrics())

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/actions/{action_id}/confirm", response_model=APIResponse[None])
async def confirm_action(
    session_id: str,
    action_id: str,
    request: ConfirmActionRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.confirm_action(
        session_id=session_id,
        action_id=action_id,
        accept=request.accept,
        user_id=current_user.id,
    )
    return APIResponse.success()


@router.get("/{session_id}/files", response_model=APIResponse[list[FileInfo]])
async def get_session_files(
    session_id: str,
    current_user: User | None = Depends(get_optional_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[list[FileInfo]]:
    if not current_user and not await agent_service.is_session_shared(session_id):
        raise UnauthorizedError()
    files = await agent_service.get_session_files(session_id, current_user.id if current_user else None)
    return APIResponse.success(files)


@router.get("/{session_id}/screenshot")
async def get_session_screenshot(
    session_id: str,
    quality: int = Query(default=75, ge=1, le=100, description="JPEG quality (1-100)"),
    scale: float = Query(default=0.5, ge=0.1, le=1.0, description="Scale factor (0.1-1.0)"),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
):
    """Get a screenshot from the session sandbox."""
    from fastapi.responses import Response

    # Check if session exists and belongs to user
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    if not session.sandbox_id:
        raise NotFoundError("Session has no active sandbox")

    # Get sandbox
    sandbox = await sandbox_cls.get(session.sandbox_id)
    if not sandbox:
        raise NotFoundError("Sandbox not found")

    # Fetch screenshot from sandbox with quality and scale parameters
    try:
        response = await sandbox.get_screenshot(quality=quality, scale=scale, format="jpeg")

        content_size = len(response.content)
        logger.info("Fetched screenshot for session %s (%d bytes)", session_id, content_size)

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Screenshot-Size": str(content_size),
            },
        )
    except Exception as e:
        error_text = _safe_exc_text(e)
        logger.error(f"Failed to fetch screenshot: {error_text}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch screenshot: {error_text}") from e


@router.post("/{session_id}/sandbox/signed-url", response_model=APIResponse[SignedUrlResponse])
async def create_sandbox_signed_url(
    session_id: str,
    request_data: AccessTokenRequest,
    target: str = Query(default="screencast"),
    quality: int = Query(default=70, ge=1, le=100),
    max_fps: int = Query(default=15, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    token_service: TokenService = Depends(get_token_service),
) -> APIResponse[SignedUrlResponse]:
    """Generate signed URL for sandbox WebSocket access

    Creates a signed URL for the screencast, input, or vnc WebSocket proxy.
    Target must be 'screencast', 'input', or 'vnc'.
    """
    allowed_targets = {"screencast", "input", "vnc"}
    if target not in allowed_targets:
        raise HTTPException(status_code=400, detail=f"Invalid target: {target}. Must be one of {allowed_targets}")

    expire_minutes = request_data.expire_minutes or 15
    if expire_minutes > 15:
        expire_minutes = 15

    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    ws_base_url = f"/api/v1/sessions/{session_id}/{target}"
    if target == "screencast":
        ws_base_url = f"{ws_base_url}?quality={quality}&max_fps={max_fps}"
    signed_url = token_service.create_signed_url(
        base_url=ws_base_url, expire_minutes=expire_minutes, user_id=current_user.id
    )

    return APIResponse.success(
        SignedUrlResponse(
            signed_url=signed_url,
            expires_in=expire_minutes * 60,
        )
    )


@router.websocket("/{session_id}/screencast")
async def screencast_websocket(
    websocket: WebSocket,
    session_id: str,
    quality: int = Query(default=70, ge=1, le=100),
    max_fps: int = Query(default=15, ge=1, le=30),
    signature: str = Depends(verify_signature_websocket),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> None:
    """CDP screencast WebSocket proxy

    Proxies the sandbox CDP screencast stream to the browser.
    The browser cannot reach sandbox containers directly, so the
    backend acts as a WebSocket relay.
    """
    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.warning(f"Screencast WebSocket accept failed (connection already closed or shutdown in progress): {e}")
        return
    logger.debug(f"Accepted screencast WebSocket for session {session_id}")

    if not _is_websocket_origin_allowed(websocket):
        logger.warning(
            "[SECURITY] Screencast WebSocket rejected: origin %r not in allowlist for session %s",
            websocket.headers.get("origin"),
            session_id,
        )
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    stream_key: str | None = None
    try:
        stream_key = await register_active_stream(session_id=session_id, endpoint="screencast")
        # Extract user_id from signed URL (uid parameter) for authorization
        from app.interfaces.dependencies import extract_user_id_from_signed_url

        user_id = extract_user_id_from_signed_url(websocket=websocket)

        # IDOR protection: user_id is required for session ownership verification
        if not user_id:
            logger.warning(
                f"[SECURITY] Screencast WebSocket rejected: missing user_id in signed URL for session {session_id}"
            )
            await websocket.close(code=1008, reason="Unauthorized")
            return

        # Get session with ownership check (user_id is always passed)
        session = await agent_service.get_session(session_id, user_id)

        if not session or not session.sandbox_id:
            await websocket.close(code=1008, reason="Session or sandbox not found")
            return

        sandbox = await sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            await websocket.close(code=1008, reason="Sandbox not found")
            return

        sandbox_ws_url = sandbox.base_url.replace("http", "ws")
        sandbox_ws_url = f"{sandbox_ws_url}/api/v1/screencast/stream?quality={quality}&max_fps={max_fps}"

        # Add authentication secret as query parameter (fallback for websockets library compatibility)
        settings = get_settings()
        if settings.sandbox_api_secret:
            from urllib.parse import quote

            sandbox_ws_url = f"{sandbox_ws_url}&secret={quote(settings.sandbox_api_secret)}"

        redacted_sandbox_ws_url = _redact_query_params(sandbox_ws_url)
        logger.debug("Connecting to screencast at %s", redacted_sandbox_ws_url)

        async with websockets.connect(
            sandbox_ws_url,
            additional_headers=_sandbox_ws_extra_headers(),
            **SANDBOX_WS_CONNECT_KWARGS,
        ) as sandbox_ws:
            logger.debug("Connected to screencast at %s", redacted_sandbox_ws_url)

            async def forward_from_sandbox():
                """Relay frames from sandbox → browser."""
                try:
                    async for message in sandbox_ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except WebSocketDisconnect:
                    logger.debug("Browser -> screencast connection closed")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        logger.debug("Browser -> screencast connection closed")
                    else:
                        logger.error(f"Error forwarding from screencast: {e}")
                except websockets.exceptions.ConnectionClosed as e:
                    if e.code in (1000, 1001, None):
                        logger.debug("Screencast -> browser connection closed (code=%s)", e.code)
                    else:
                        logger.warning(
                            "Screencast -> browser connection closed abnormally (code=%s, reason=%s)", e.code, e.reason
                        )
                except Exception as e:
                    logger.error(f"Error forwarding from screencast: {e}")

            async def forward_from_browser():
                """Relay browser → sandbox messages (pong, pause/resume, control).

                Also detects browser disconnect immediately instead of waiting
                for the next send failure in ``forward_from_sandbox``.
                """
                try:
                    while True:
                        msg = await websocket.receive()
                        msg_type = msg.get("type")
                        if msg_type == "websocket.disconnect":
                            break
                        # Forward text/binary messages to the sandbox so that
                        # pong responses and control commands (pause/resume)
                        # actually reach the sandbox's receive_control loop.
                        text = msg.get("text")
                        data = msg.get("bytes")
                        try:
                            if text is not None:
                                await sandbox_ws.send(text)
                            elif data is not None:
                                await sandbox_ws.send(data)
                        except websockets.exceptions.ConnectionClosed:
                            break
                except (WebSocketDisconnect, RuntimeError):
                    pass

            # Run both directions concurrently — finish when either side closes.
            tasks = [
                asyncio.create_task(forward_from_sandbox()),
                asyncio.create_task(forward_from_browser()),
            ]
            try:
                _done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                for task in tasks:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    except (ConnectionError, websockets.exceptions.WebSocketException) as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"Screencast: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"Unable to connect to screencast: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Unable to connect to sandbox: {error_text}")
    except Exception as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"Screencast: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"Screencast WebSocket error: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Screencast error: {error_text}")
    finally:
        if stream_key:
            with contextlib.suppress(Exception):
                await unregister_active_stream(stream_key)


@router.websocket("/{session_id}/input")
async def input_websocket(
    websocket: WebSocket,
    session_id: str,
    signature: str = Depends(verify_signature_websocket),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> None:
    """Input stream WebSocket proxy for interactive takeover

    Proxies mouse/keyboard input from the browser to the sandbox.
    """
    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.warning(f"Input WebSocket accept failed (connection already closed or shutdown in progress): {e}")
        return

    if not _is_websocket_origin_allowed(websocket):
        logger.warning(
            "[SECURITY] Input WebSocket rejected: origin %r not in allowlist for session %s",
            websocket.headers.get("origin"),
            session_id,
        )
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    try:
        # Extract user_id from signed URL (uid parameter) for authorization
        from app.interfaces.dependencies import extract_user_id_from_signed_url

        user_id = extract_user_id_from_signed_url(websocket=websocket)

        # IDOR protection: user_id is required for session ownership verification
        if not user_id:
            logger.warning(
                f"[SECURITY] Input WebSocket rejected: missing user_id in signed URL for session {session_id}"
            )
            await websocket.close(code=1008, reason="Unauthorized")
            return

        # Get session with ownership check
        session = await agent_service.get_session(session_id, user_id)
        if not session or not session.sandbox_id:
            await websocket.close(code=1008, reason="Session or sandbox not found")
            return

        sandbox = await sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            await websocket.close(code=1008, reason="Sandbox not found")
            return

        sandbox_ws_url = sandbox.base_url.replace("http", "ws")
        sandbox_ws_url = f"{sandbox_ws_url}/api/v1/input/stream"

        # Add authentication secret as query parameter (fallback for websockets library compatibility)
        settings = get_settings()
        if settings.sandbox_api_secret:
            from urllib.parse import quote

            sandbox_ws_url = f"{sandbox_ws_url}?secret={quote(settings.sandbox_api_secret)}"

        async with websockets.connect(
            sandbox_ws_url,
            additional_headers=_sandbox_ws_extra_headers(),
            **SANDBOX_WS_CONNECT_KWARGS,
        ) as sandbox_ws:

            async def forward_to_sandbox():
                try:
                    while True:
                        data = await websocket.receive()
                        if "text" in data:
                            await sandbox_ws.send(data["text"])
                        elif "bytes" in data:
                            await sandbox_ws.send(data["bytes"])
                except WebSocketDisconnect:
                    logger.info("Browser -> input connection closed")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        logger.info("Browser -> input connection closed")
                    else:
                        logger.error(f"Error forwarding input to sandbox: {e}")
                except Exception as e:
                    logger.error(f"Error forwarding input to sandbox: {e}")

            async def forward_from_sandbox():
                try:
                    async for message in sandbox_ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.error(f"Error forwarding from sandbox input: {e}")

            task1 = asyncio.create_task(forward_to_sandbox())
            task2 = asyncio.create_task(forward_from_sandbox())

            _done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except ConnectionError as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"Input WS: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"Unable to connect to sandbox input: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Unable to connect to sandbox: {error_text}")
    except Exception as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"Input WS: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"Input WebSocket error: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Input error: {error_text}")


@router.websocket("/{session_id}/vnc")
async def vnc_websocket(
    websocket: WebSocket,
    session_id: str,
    signature: str = Depends(verify_signature_websocket),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> None:
    """VNC WebSocket proxy for takeover mode.

    Proxies the sandbox websockify (VNC-over-WebSocket on port 6080) to the
    browser.  Used during takeover to show full browser chrome with tabs.
    The VNC protocol is binary-only — no text messages to handle.
    """
    try:
        # noVNC requires the 'binary' subprotocol (VNC is a binary protocol).
        # If the server doesn't echo the subprotocol, the browser closes with 1006.
        await websocket.accept(subprotocol="binary")
    except RuntimeError as e:
        logger.warning(f"VNC WebSocket accept failed (connection already closed or shutdown in progress): {e}")
        return

    if not _is_websocket_origin_allowed(websocket):
        logger.warning(
            "[SECURITY] VNC WebSocket rejected: origin %r not in allowlist for session %s",
            websocket.headers.get("origin"),
            session_id,
        )
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    try:
        from app.interfaces.dependencies import extract_user_id_from_signed_url

        user_id = extract_user_id_from_signed_url(websocket=websocket)

        if not user_id:
            logger.warning(f"[SECURITY] VNC WebSocket rejected: missing user_id in signed URL for session {session_id}")
            await websocket.close(code=1008, reason="Unauthorized")
            return

        session = await agent_service.get_session(session_id, user_id)
        if not session or not session.sandbox_id:
            await websocket.close(code=1008, reason="Session or sandbox not found")
            return

        sandbox = await sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            await websocket.close(code=1008, reason="Sandbox not found")
            return

        # Websockify runs on port 6080 inside the sandbox container.
        # Replace the API port (typically 8080) with 6080 for VNC.
        sandbox_vnc_url = sandbox.base_url.replace("http", "ws")
        sandbox_vnc_url = sandbox_vnc_url.replace(":8080", ":6080")

        redacted_sandbox_vnc_url = _redact_query_params(sandbox_vnc_url)
        logger.info("Connecting to VNC websockify at %s", redacted_sandbox_vnc_url)

        async with websockets.connect(
            sandbox_vnc_url,
            subprotocols=["binary"],
            **SANDBOX_WS_CONNECT_KWARGS,
        ) as sandbox_ws:
            logger.info("Connected to VNC websockify at %s", redacted_sandbox_vnc_url)

            async def forward_from_sandbox():
                """Relay VNC frames from sandbox → browser."""
                try:
                    async for message in sandbox_ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except WebSocketDisconnect:
                    logger.info("Browser -> VNC connection closed")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        logger.info("Browser -> VNC connection closed")
                    else:
                        logger.error(f"Error forwarding from VNC: {e}")
                except websockets.exceptions.ConnectionClosed:
                    logger.info("VNC -> browser connection closed")
                except Exception as e:
                    logger.error(f"Error forwarding from VNC: {e}")

            async def forward_from_browser():
                """Relay browser → sandbox VNC messages (mouse/keyboard input)."""
                try:
                    while True:
                        msg = await websocket.receive()
                        msg_type = msg.get("type")
                        if msg_type == "websocket.disconnect":
                            break
                        text = msg.get("text")
                        data = msg.get("bytes")
                        try:
                            if data is not None:
                                await sandbox_ws.send(data)
                            elif text is not None:
                                await sandbox_ws.send(text)
                        except websockets.exceptions.ConnectionClosed:
                            break
                except (WebSocketDisconnect, RuntimeError):
                    pass

            tasks = [
                asyncio.create_task(forward_from_sandbox()),
                asyncio.create_task(forward_from_browser()),
            ]
            try:
                _done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                for task in tasks:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    except (ConnectionError, websockets.exceptions.WebSocketException) as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"VNC WS: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"Unable to connect to VNC websockify: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Unable to connect to sandbox VNC: {error_text}")
    except Exception as e:
        error_text = _safe_exc_text(e)
        if "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"VNC WS: sandbox container no longer exists: {error_text}")
        else:
            logger.error(f"VNC WebSocket error: {error_text}")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"VNC error: {error_text}")


# ============================================================================
# Screenshot Replay Endpoints
# ============================================================================


@router.get("/{session_id}/screenshots", response_model=APIResponse[ScreenshotListResponse])
async def list_screenshots(
    session_id: str,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
) -> APIResponse[ScreenshotListResponse]:
    """List screenshot metadata for a session."""
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    screenshots, total = await screenshot_query_service.list_by_session(session_id, limit=limit, offset=offset)

    items = [
        ScreenshotMetadataResponse(
            id=s.id,
            session_id=s.session_id,
            sequence_number=s.sequence_number,
            timestamp=s.timestamp.timestamp(),
            trigger=s.trigger.value if hasattr(s.trigger, "value") else str(s.trigger),
            tool_call_id=s.tool_call_id,
            tool_name=s.tool_name,
            function_name=s.function_name,
            action_type=s.action_type,
            size_bytes=s.size_bytes,
            has_thumbnail=s.thumbnail_storage_key is not None,
        )
        for s in screenshots
    ]

    return APIResponse.success(ScreenshotListResponse(screenshots=items, total=total))


@router.get("/{session_id}/screenshots/{screenshot_id}")
async def get_screenshot_image(
    session_id: str,
    screenshot_id: str,
    thumbnail: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
):
    """Get screenshot image (JPEG bytes)."""
    from fastapi.responses import Response

    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    image_result = await screenshot_query_service.get_image_bytes(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=thumbnail,
    )
    if isinstance(image_result, tuple):
        image_data = image_result[0] if len(image_result) >= 1 else None
        content_type = image_result[1] if len(image_result) >= 2 else "image/jpeg"
    else:
        image_data = image_result
        content_type = "image/jpeg"
    if image_data is None:
        raise NotFoundError("Screenshot not found")

    return Response(
        content=image_data,
        media_type=content_type or "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.get("/shared/{session_id}/screenshots", response_model=APIResponse[ScreenshotListResponse])
async def list_shared_screenshots(
    session_id: str,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
) -> APIResponse[ScreenshotListResponse]:
    """List screenshot metadata for a shared session."""
    session = await agent_service.get_shared_session(session_id)
    if not session:
        raise NotFoundError("Shared session not found")

    screenshots, total = await screenshot_query_service.list_by_session(session_id, limit=limit, offset=offset)

    items = [
        ScreenshotMetadataResponse(
            id=s.id,
            session_id=s.session_id,
            sequence_number=s.sequence_number,
            timestamp=s.timestamp.timestamp(),
            trigger=s.trigger.value if hasattr(s.trigger, "value") else str(s.trigger),
            tool_call_id=s.tool_call_id,
            tool_name=s.tool_name,
            function_name=s.function_name,
            action_type=s.action_type,
            size_bytes=s.size_bytes,
            has_thumbnail=s.thumbnail_storage_key is not None,
        )
        for s in screenshots
    ]

    return APIResponse.success(ScreenshotListResponse(screenshots=items, total=total))


@router.get("/shared/{session_id}/screenshots/{screenshot_id}")
async def get_shared_screenshot_image(
    session_id: str,
    screenshot_id: str,
    thumbnail: bool = Query(default=False),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
):
    """Get screenshot image for a shared session (JPEG bytes)."""
    from fastapi.responses import Response

    session = await agent_service.get_shared_session(session_id)
    if not session:
        raise NotFoundError("Shared session not found")

    image_result = await screenshot_query_service.get_image_bytes(
        session_id=session_id,
        screenshot_id=screenshot_id,
        thumbnail=thumbnail,
    )
    if isinstance(image_result, tuple):
        image_data = image_result[0] if len(image_result) >= 1 else None
        content_type = image_result[1] if len(image_result) >= 2 else "image/jpeg"
    else:
        image_data = image_result
        content_type = "image/jpeg"
    if image_data is None:
        raise NotFoundError("Screenshot not found")

    return Response(
        content=image_data,
        media_type=content_type or "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.post("/{session_id}/workspace/manifest", response_model=APIResponse[WorkspaceManifestResponse])
async def init_workspace_from_manifest(
    session_id: str,
    request: WorkspaceManifest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[WorkspaceManifestResponse]:
    """Initialize workspace from a manifest payload."""
    result = await agent_service.init_workspace_from_manifest(
        session_id=session_id,
        manifest=request,
        user_id=current_user.id,
    )
    return APIResponse.success(result)


@router.post("/{session_id}/share", response_model=APIResponse[ShareSessionResponse])
async def share_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[ShareSessionResponse]:
    """Share a session to make it publicly accessible

    This endpoint marks a session as shared, allowing it to be accessed
    without authentication using the shared session endpoint.
    """
    await agent_service.share_session(session_id, current_user.id)
    return APIResponse.success(ShareSessionResponse(session_id=session_id, is_shared=True))


@router.get("/{session_id}/share/files", response_model=APIResponse[list[FileInfo]])
async def get_shared_session_files(
    session_id: str, agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[list[FileInfo]]:
    files = await agent_service.get_shared_session_files(session_id)
    for file in files:
        await get_file_service().enrich_with_file_url(file)
    return APIResponse.success(files)


@router.delete("/{session_id}/share", response_model=APIResponse[ShareSessionResponse])
async def unshare_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[ShareSessionResponse]:
    """Unshare a session to make it private again

    This endpoint marks a session as not shared, removing public access.
    """
    await agent_service.unshare_session(session_id, current_user.id)
    return APIResponse.success(ShareSessionResponse(session_id=session_id, is_shared=False))


@router.get("/shared/{session_id}", response_model=APIResponse[SharedSessionResponse])
async def get_shared_session(
    session_id: str, agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[SharedSessionResponse]:
    """Get a shared session without authentication

    This endpoint allows public access to sessions that have been marked as shared.
    No authentication is required, but the session must be explicitly shared.
    """
    session = await agent_service.get_shared_session(session_id)
    if not session:
        raise NotFoundError("Shared session not found")

    return APIResponse.success(
        SharedSessionResponse(
            session_id=session.id,
            title=session.title,
            status=session.status,
            events=await EventMapper.events_to_sse_events(session.events),
            is_shared=session.is_shared,
        )
    )
