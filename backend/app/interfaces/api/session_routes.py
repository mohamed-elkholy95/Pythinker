import asyncio
import contextlib
import hashlib
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.application.errors.exceptions import NotFoundError, UnauthorizedError
from app.application.services.agent_service import AgentService
from app.application.services.screenshot_service import ScreenshotQueryService
from app.application.services.token_service import TokenService
from app.core.config import get_settings
from app.core.deep_research_manager import get_deep_research_manager
from app.domain.external.sandbox import Sandbox
from app.domain.models.event import DoneEvent, ErrorEvent, PlanningPhase, ProgressEvent
from app.domain.models.file import FileInfo
from app.domain.models.user import User
from app.interfaces.dependencies import (
    get_agent_service,
    get_current_user,
    get_file_service,
    get_optional_current_user,
    get_sandbox_cls,
    get_screenshot_query_service,
    get_token_service,
    verify_signature_websocket,
)
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
    DeepResearchSkipRequest,
    DeepResearchStatusResponse,
    GetSessionResponse,
    ListSessionItem,
    ListSessionResponse,
    ResumeSessionRequest,
    SandboxInfo,
    SessionStatusResponse,
    SharedSessionResponse,
    ShareSessionResponse,
    ShellViewRequest,
    ShellViewResponse,
)
from app.interfaces.schemas.workspace import WorkspaceManifest, WorkspaceManifestResponse

logger = logging.getLogger(__name__)
SESSION_POLL_INTERVAL = 10
SANDBOX_WS_CONNECT_KWARGS = {
    "ping_interval": None,
    "max_size": None,
}

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _safe_exc_text(exc: BaseException) -> str:
    """Return a stable, bounded exception message for websocket paths."""
    try:
        message = str(exc)
    except Exception:
        message = repr(exc)

    if not message:
        message = exc.__class__.__name__

    # Keep WebSocket close reasons compact.
    return message[:240]


async def _safe_ws_close(websocket: WebSocket, code: int, reason: str) -> None:
    """Best-effort websocket close to avoid raising on already-closed channels."""
    with contextlib.suppress(Exception):
        await websocket.close(code=code, reason=reason[:240])


@router.put("", response_model=APIResponse[CreateSessionResponse])
async def create_session(
    request: CreateSessionRequest = CreateSessionRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> APIResponse[CreateSessionResponse]:
    session = await agent_service.create_session(
        current_user.id,
        mode=request.mode,
        initial_message=request.message,  # Phase 4 P0: Pass initial message for intent classification
        require_fresh_sandbox=request.require_fresh_sandbox,
        sandbox_wait_seconds=request.sandbox_wait_seconds,
    )

    # Phase 4: Include sandbox info if available for optimistic VNC connection
    sandbox_info = None
    if session.sandbox_id:
        try:
            sandbox = await sandbox_cls.get(session.sandbox_id)
            if sandbox:
                sandbox_info = SandboxInfo(sandbox_id=sandbox.id, vnc_url=sandbox.vnc_url, status="initializing")
        except Exception as e:
            logger.debug(f"Could not fetch sandbox info for optimistic VNC: {e}")

    return APIResponse.success(
        CreateSessionResponse(session_id=session.id, mode=session.mode, sandbox=sandbox_info, status=session.status)
    )


@router.get("/{session_id}", response_model=APIResponse[GetSessionResponse])
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[GetSessionResponse]:
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    return APIResponse.success(
        GetSessionResponse(
            session_id=session.id,
            title=session.title,
            status=session.status,
            events=await EventMapper.events_to_sse_events(session.events),
            is_shared=session.is_shared,
        )
    )


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
                created_at=active.created_at.timestamp() if active.created_at else None,
            )
        )
    )


@router.delete("/{session_id}", response_model=APIResponse[None])
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    screenshot_query_service: ScreenshotQueryService = Depends(get_screenshot_query_service),
) -> APIResponse[None]:
    await agent_service.delete_session(session_id, current_user.id)
    # Clean up screenshots for the deleted session (fire-and-forget)
    try:
        deleted = await screenshot_query_service.delete_by_session(session_id)
        if deleted:
            logger.info("Deleted %d screenshots for session %s", deleted, session_id)
    except Exception as e:
        logger.warning("Failed to cleanup screenshots for session %s: %s", session_id, e)
    return APIResponse.success()


@router.post("/{session_id}/stop", response_model=APIResponse[None])
async def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.stop_session(session_id, current_user.id)
    return APIResponse.success()


@router.post("/{session_id}/pause", response_model=APIResponse[None])
async def pause_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    """Pause a session for user takeover

    This endpoint pauses the agent execution so the user can take control
    of the browser via VNC without conflicts.
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


@router.patch("/{session_id}/rename", response_model=APIResponse[None])
async def rename_session(
    session_id: str,
    request: dict,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    title = request.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    await agent_service.rename_session(session_id, current_user.id, title)
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
    current_user: User = Depends(get_current_user), agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[ListSessionResponse]:
    sessions = await agent_service.get_all_sessions(current_user.id)
    session_items = [
        ListSessionItem(
            session_id=session.id,
            title=session.title,
            status=session.status,
            unread_message_count=session.unread_message_count,
            latest_message=session.latest_message,
            latest_message_at=int(session.latest_message_at.timestamp()) if session.latest_message_at else None,
            is_shared=session.is_shared,
        )
        for session in sessions
    ]
    return APIResponse.success(ListSessionResponse(sessions=session_items))


@router.post("")
async def stream_sessions(
    current_user: User = Depends(get_current_user), agent_service: AgentService = Depends(get_agent_service)
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        last_hash: str | None = None
        try:
            while True:
                sessions = await agent_service.get_all_sessions(current_user.id)
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
                    )
                    for session in sessions
                ]
                data = ListSessionResponse(sessions=session_items).model_dump_json()
                current_hash = hashlib.md5(data.encode(), usedforsecurity=False).hexdigest()
                # Only send if data actually changed
                if current_hash != last_hash:
                    yield ServerSentEvent(event="sessions", data=data)
                    last_hash = current_hash
                await asyncio.sleep(SESSION_POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.debug("Session SSE stream cancelled")
            return

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    request: ChatRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """Chat endpoint with SSE streaming.

    Phase 3 Enhancement: Improved disconnect handling and send timeout.
    When feature_sse_v2 is enabled, uses enhanced event streaming with
    disconnect detection and timeouts for better reliability.
    """
    # Validate session exists before starting SSE stream (returns 404 instead of 200 with error)
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    # Short-circuit for completed/failed sessions ONLY when there is no fresh user
    # input (pure reconnect / page-refresh).  When the request carries a message,
    # attachments, skills, follow-up context, or deep-research flag the call must
    # reach agent_service.chat() so the domain-level reactivation path can create a
    # new task and re-initialise the sandbox.
    has_fresh_input = bool(
        (request.message and request.message.strip())
        or request.attachments
        or request.skills
        or request.deep_research
        or request.follow_up
    )
    if session.status in ("completed", "failed") and not has_fresh_input:
        logger.info(f"Session {session_id} already {session.status} with no new input, emitting done event")

        done_event = DoneEvent(title=session.title or "Task completed")
        sse_done = await EventMapper.event_to_sse_event(done_event)

        async def completed_generator() -> AsyncGenerator[ServerSentEvent, None]:
            if sse_done:
                yield ServerSentEvent(
                    event=sse_done.event,
                    data=sse_done.data.model_dump_json() if sse_done.data else None,
                )

        return EventSourceResponse(completed_generator())

    settings = get_settings()
    use_sse_v2 = settings.feature_sse_v2

    # SSE send timeout (Phase 3: prevents hanging on slow clients)
    send_timeout = 60.0 if use_sse_v2 else None  # 60s for slow networks

    # Heartbeat interval: keep connection alive and prevent "stuck" feeling during long ops
    heartbeat_interval_seconds = 15.0

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
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
                yield ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json() if sse_event.data else None,
                )

            # Convert FollowUpContext to dict for service layer
            follow_up_dict = None
            if request.follow_up:
                follow_up_dict = {
                    "selected_suggestion": request.follow_up.selected_suggestion,
                    "anchor_event_id": request.follow_up.anchor_event_id,
                    "source": request.follow_up.source,
                }

            # Heartbeat: send keep-alive events during long agent operations
            # Prevents frontend "stale" detection and proxy/timeout disconnects (SSE best practice)
            heartbeat = ProgressEvent(
                phase=PlanningPhase.HEARTBEAT,
                message="",
                progress_percent=None,
            )
            sse_heartbeat = await EventMapper.event_to_sse_event(heartbeat)
            if sse_heartbeat:
                heartbeat_sse = ServerSentEvent(
                    event=sse_heartbeat.event,
                    data=sse_heartbeat.data.model_dump_json() if sse_heartbeat.data else None,
                )
            else:
                heartbeat_sse = None

            chat_stream = agent_service.chat(
                session_id=session_id,
                user_id=current_user.id,
                message=request.message,
                timestamp=datetime.fromtimestamp(request.timestamp) if request.timestamp else None,
                event_id=request.event_id,
                attachments=request.attachments,
                skills=request.skills,
                deep_research=request.deep_research,
                follow_up=follow_up_dict,
            )
            stream_iter = chat_stream.__aiter__()
            next_event_task: asyncio.Task | None = asyncio.create_task(stream_iter.__anext__())
            heartbeat_task: asyncio.Task | None = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))
            stream_exhausted = False

            while not stream_exhausted:
                # Phase 3: Check for client disconnect before sending
                if use_sse_v2 and await http_request.is_disconnected():
                    logger.info(f"Client disconnected during chat stream: {session_id}")
                    break

                done: set[asyncio.Task] = set()
                pending: set[asyncio.Task] = set()
                done, pending = await asyncio.wait(
                    {t for t in (next_event_task, heartbeat_task) if t is not None},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if heartbeat_task in done:
                    # Heartbeat fired: send keep-alive, reset heartbeat timer
                    # Do NOT cancel next_event_task - it is still waiting for the real event
                    heartbeat_task = None
                    if heartbeat_sse:
                        yield heartbeat_sse
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
                        break

                    logger.debug(f"Received event from chat: {event}")
                    sse_event = await EventMapper.event_to_sse_event(event)
                    logger.debug(f"Received event: {sse_event}")
                    if sse_event:
                        event_data = sse_event.data.model_dump_json() if sse_event.data else None
                        event_id_val = getattr(sse_event.data, "event_id", None) if sse_event.data else None
                        sse_kwargs: dict = {"event": sse_event.event, "data": event_data}
                        if event_id_val:
                            sse_kwargs["id"] = str(event_id_val)
                        sse_payload = ServerSentEvent(**sse_kwargs)
                        if send_timeout:
                            try:
                                async with asyncio.timeout(send_timeout):
                                    yield sse_payload
                            except TimeoutError:
                                logger.warning(f"SSE send timeout for session {session_id}")
                                break
                        else:
                            yield sse_payload

                    next_event_task = asyncio.create_task(stream_iter.__anext__())
                    heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_interval_seconds))

            # Cleanup stream
            with contextlib.suppress(Exception):
                await stream_iter.aclose()
        except asyncio.CancelledError:
            # Client disconnected - log and gracefully terminate
            logger.warning(f"Chat stream cancelled for session {session_id} (client disconnected)")
            raise
        except Exception as e:
            logger.error(f"Error in chat stream for session {session_id}: {e}")
            # Yield schema-compliant error event before closing so frontend
            # ErrorEventData handler receives the expected `error` field.
            error_event = ErrorEvent(error=f"Stream error: {str(e)[:100]}")
            sse_err = await EventMapper.event_to_sse_event(error_event)
            if sse_err:
                yield ServerSentEvent(
                    event=sse_err.event,
                    data=sse_err.data.model_dump_json() if sse_err.data else None,
                )

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/shell")
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


@router.post("/{session_id}/file")
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
        async for event in agent_service.browse_url(session_id=session_id, user_id=current_user.id, url=request.url):
            logger.debug(f"Received browse event: {event}")
            sse_event = await EventMapper.event_to_sse_event(event)
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event, data=sse_event.data.model_dump_json() if sse_event.data else None
                )

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


@router.websocket("/{session_id}/vnc")
async def vnc_websocket(
    websocket: WebSocket,
    session_id: str,
    signature: str = Depends(verify_signature_websocket),
    agent_service: AgentService = Depends(get_agent_service),
) -> None:
    """VNC WebSocket endpoint (binary mode)

    Establishes a connection with the VNC WebSocket service in the sandbox environment and forwards data bidirectionally
    Supports authentication via signed URL with signature verification

    Args:
        websocket: WebSocket connection
        session_id: Session ID
        signature: Verified signature from dependency injection
    """

    await websocket.accept(subprotocol="binary")
    logger.info(f"Accepted WebSocket connection for session {session_id}")

    try:
        # Get sandbox environment address with user validation
        sandbox_ws_url = await agent_service.get_vnc_url(session_id)

        logger.info(f"Connecting to VNC WebSocket at {sandbox_ws_url}")

        # Connect to sandbox WebSocket (standard RFB protocol)
        async with websockets.connect(sandbox_ws_url, **SANDBOX_WS_CONNECT_KWARGS) as sandbox_ws:
            logger.info(f"Connected to VNC WebSocket at {sandbox_ws_url}")

            # Create two tasks to forward data bidirectionally
            async def forward_to_sandbox():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await sandbox_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web -> VNC connection closed")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        logger.info("Web -> VNC connection closed")
                    else:
                        logger.error(f"Error forwarding data to sandbox: {e}")
                except Exception as e:
                    logger.error(f"Error forwarding data to sandbox: {e}")

            async def forward_from_sandbox():
                try:
                    while True:
                        data = await sandbox_ws.recv()
                        await websocket.send_bytes(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("VNC -> Web connection closed")
                    pass
                except Exception as e:
                    logger.error(f"Error forwarding data from sandbox: {e}")

            # Run two forwarding tasks concurrently
            forward_task1 = asyncio.create_task(forward_to_sandbox())
            forward_task2 = asyncio.create_task(forward_from_sandbox())

            # Wait for either task to complete (meaning connection has closed)
            _done, pending = await asyncio.wait([forward_task1, forward_task2], return_when=asyncio.FIRST_COMPLETED)

            logger.info("WebSocket connection closed")

            # Cancel pending tasks
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    except ConnectionError as e:
        error_text = _safe_exc_text(e)
        logger.error(f"Unable to connect to sandbox environment: {error_text}")
        await _safe_ws_close(websocket, code=1011, reason=f"Unable to connect to sandbox environment: {error_text}")
    except NotFoundError as e:
        error_text = _safe_exc_text(e)
        logger.info(f"VNC WebSocket rejected: {error_text}")
        await _safe_ws_close(websocket, code=1008, reason=error_text)
    except Exception as e:
        error_text = _safe_exc_text(e)
        if "Session has no sandbox environment" in error_text:
            logger.info(f"VNC WebSocket rejected: {error_text}")
            await _safe_ws_close(websocket, code=1008, reason=error_text)
        elif "No such container" in error_text or "404 Client Error" in error_text:
            logger.warning(f"VNC WebSocket: sandbox container no longer exists: {error_text}")
            await _safe_ws_close(websocket, code=1001, reason="Sandbox container terminated")
        else:
            logger.error(f"WebSocket error: {error_text}")
            await _safe_ws_close(websocket, code=1011, reason=f"WebSocket error: {error_text}")


@router.get("/{session_id}/files")
async def get_session_files(
    session_id: str,
    current_user: User | None = Depends(get_optional_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[list[FileInfo]]:
    if not current_user and not await agent_service.is_session_shared(session_id):
        raise UnauthorizedError()
    files = await agent_service.get_session_files(session_id, current_user.id if current_user else None)
    return APIResponse.success(files)


@router.post("/{session_id}/vnc/signed-url", response_model=APIResponse[SignedUrlResponse])
async def create_vnc_signed_url(
    session_id: str,
    request_data: AccessTokenRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    token_service: TokenService = Depends(get_token_service),
) -> APIResponse[SignedUrlResponse]:
    """Generate signed URL for VNC WebSocket access

    This endpoint creates a signed URL that allows temporary access to the VNC
    WebSocket for a specific session without requiring authentication headers.
    """

    # Validate expiration time (max 15 minutes)
    expire_minutes = request_data.expire_minutes
    if expire_minutes > 15:
        expire_minutes = 15

    # Check if session exists and belongs to user
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    # Create signed URL for VNC WebSocket
    ws_base_url = f"/api/v1/sessions/{session_id}/vnc"
    signed_url = token_service.create_signed_url(base_url=ws_base_url, expire_minutes=expire_minutes)

    logger.info(f"Created signed URL for VNC access for user {current_user.id}, session {session_id}")

    return APIResponse.success(
        SignedUrlResponse(
            signed_url=signed_url,
            expires_in=expire_minutes * 60,
        )
    )


@router.get("/{session_id}/vnc/screenshot")
async def get_vnc_screenshot(
    session_id: str,
    quality: int = Query(default=75, ge=1, le=100, description="JPEG quality (1-100)"),
    scale: float = Query(default=0.5, ge=0.1, le=1.0, description="Scale factor (0.1-1.0)"),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
):
    """Get VNC screenshot from sandbox"""
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
        logger.info("Fetched VNC screenshot for session %s (%d bytes)", session_id, content_size)

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
        logger.error(f"Failed to fetch VNC screenshot: {error_text}")
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

    Creates a signed URL for the screencast or input WebSocket proxy.
    Target must be 'screencast' or 'input'.
    """
    allowed_targets = {"screencast", "input"}
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
    signed_url = token_service.create_signed_url(base_url=ws_base_url, expire_minutes=expire_minutes)

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
    await websocket.accept()
    logger.info(f"Accepted screencast WebSocket for session {session_id}")

    try:
        session = await agent_service.get_session(session_id)
        if not session or not session.sandbox_id:
            await websocket.close(code=1008, reason="Session or sandbox not found")
            return

        sandbox = await sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            await websocket.close(code=1008, reason="Sandbox not found")
            return

        sandbox_ws_url = sandbox.base_url.replace("http", "ws")
        sandbox_ws_url = f"{sandbox_ws_url}/api/v1/screencast/stream?quality={quality}&max_fps={max_fps}"

        logger.info(f"Connecting to screencast at {sandbox_ws_url}")

        async with websockets.connect(sandbox_ws_url, **SANDBOX_WS_CONNECT_KWARGS) as sandbox_ws:
            logger.info(f"Connected to screencast at {sandbox_ws_url}")

            async def forward_from_sandbox():
                try:
                    async for message in sandbox_ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except WebSocketDisconnect:
                    logger.info("Browser -> screencast connection closed")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        logger.info("Browser -> screencast connection closed")
                    else:
                        logger.error(f"Error forwarding from screencast: {e}")
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Screencast -> browser connection closed")
                except Exception as e:
                    logger.error(f"Error forwarding from screencast: {e}")

            await forward_from_sandbox()

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
    await websocket.accept()

    try:
        session = await agent_service.get_session(session_id)
        if not session or not session.sandbox_id:
            await websocket.close(code=1008, reason="Session or sandbox not found")
            return

        sandbox = await sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            await websocket.close(code=1008, reason="Sandbox not found")
            return

        sandbox_ws_url = sandbox.base_url.replace("http", "ws")
        sandbox_ws_url = f"{sandbox_ws_url}/api/v1/input/stream"

        async with websockets.connect(sandbox_ws_url, **SANDBOX_WS_CONNECT_KWARGS) as sandbox_ws:

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


@router.get("/{session_id}/share/files")
async def get_shared_session_files(
    session_id: str, agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[list[FileInfo]]:
    files = await agent_service.get_shared_session_files(session_id)
    for file in files:
        await get_file_service().enrich_with_file_url(file)
    return APIResponse.success(files)


@router.post("/{session_id}/deep-research/approve", response_model=APIResponse[None])
async def approve_deep_research(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    """Approve a pending deep research session to start execution.

    This endpoint signals the deep research flow to begin executing
    queries that were waiting for user approval.
    """
    # Verify session ownership
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    # Approve the research
    manager = get_deep_research_manager()
    if await manager.approve(session_id):
        logger.info(f"Deep research approved for session {session_id}")
        return APIResponse.success()
    raise HTTPException(status_code=404, detail="No active deep research found for this session")


@router.post("/{session_id}/deep-research/skip", response_model=APIResponse[None])
async def skip_deep_research_query(
    session_id: str,
    request: DeepResearchSkipRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    """Skip a specific query or all pending queries in deep research.

    If query_id is provided, skips only that query.
    If query_id is None, skips all pending/searching queries.
    """
    # Verify session ownership
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    # Skip the query(s)
    manager = get_deep_research_manager()
    if await manager.skip_query(session_id, request.query_id):
        logger.info(f"Deep research query skipped for session {session_id}: {request.query_id or 'all'}")
        return APIResponse.success()
    raise HTTPException(status_code=404, detail="No active deep research found for this session")


@router.get("/{session_id}/deep-research/status", response_model=APIResponse[DeepResearchStatusResponse])
async def get_deep_research_status(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[DeepResearchStatusResponse]:
    """Get the current status of deep research for a session."""
    # Verify session ownership
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")

    manager = get_deep_research_manager()
    flow = manager.get(session_id)

    if not flow or not flow.get_session():
        raise HTTPException(status_code=404, detail="No active deep research found for this session")

    research_session = flow.get_session()
    return APIResponse.success(
        DeepResearchStatusResponse(
            research_id=research_session.research_id,
            status=research_session.status,
            total_queries=research_session.total_count,
            completed_queries=research_session.completed_count,
        )
    )


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
