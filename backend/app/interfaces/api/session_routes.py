import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.application.errors.exceptions import NotFoundError, UnauthorizedError
from app.application.services.agent_service import AgentService
from app.application.services.token_service import TokenService
from app.core.deep_research_manager import get_deep_research_manager
from app.domain.external.sandbox import Sandbox
from app.domain.models.file import FileInfo
from app.domain.models.user import User
from app.interfaces.dependencies import (
    get_agent_service,
    get_current_user,
    get_file_service,
    get_optional_current_user,
    get_sandbox_cls,
    get_token_service,
    verify_signature_websocket,
)
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.event import EventMapper
from app.interfaces.schemas.file import FileViewRequest, FileViewResponse
from app.interfaces.schemas.resource import AccessTokenRequest, SignedUrlResponse
from app.interfaces.schemas.session import (
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
    SharedSessionResponse,
    ShareSessionResponse,
    ShellViewRequest,
    ShellViewResponse,
)
from app.interfaces.schemas.workspace import WorkspaceManifest, WorkspaceManifestResponse

logger = logging.getLogger(__name__)
SESSION_POLL_INTERVAL = 10

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.put("", response_model=APIResponse[CreateSessionResponse])
async def create_session(
    request: CreateSessionRequest = CreateSessionRequest(),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    sandbox_cls: type[Sandbox] = Depends(get_sandbox_cls),
) -> APIResponse[CreateSessionResponse]:
    session = await agent_service.create_session(current_user.id, mode=request.mode)

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


@router.delete("/{session_id}", response_model=APIResponse[None])
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[None]:
    await agent_service.delete_session(session_id, current_user.id)
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
        while True:
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
            yield ServerSentEvent(event="sessions", data=ListSessionResponse(sessions=session_items).model_dump_json())
            await asyncio.sleep(SESSION_POLL_INTERVAL)

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.chat(
            session_id=session_id,
            user_id=current_user.id,
            message=request.message,
            timestamp=datetime.fromtimestamp(request.timestamp) if request.timestamp else None,
            event_id=request.event_id,
            attachments=request.attachments,
        ):
            logger.debug(f"Received event from chat: {event}")
            sse_event = await EventMapper.event_to_sse_event(event)
            logger.debug(f"Received event: {sse_event}")
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event, data=sse_event.data.model_dump_json() if sse_event.data else None
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
        async with websockets.connect(sandbox_ws_url) as sandbox_ws:
            logger.info(f"Connected to VNC WebSocket at {sandbox_ws_url}")

            # Create two tasks to forward data bidirectionally
            async def forward_to_sandbox():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await sandbox_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web -> VNC connection closed")
                    pass
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
            done, pending = await asyncio.wait([forward_task1, forward_task2], return_when=asyncio.FIRST_COMPLETED)

            logger.info("WebSocket connection closed")

            # Cancel pending tasks
            for task in pending:
                task.cancel()

    except ConnectionError as e:
        logger.error(f"Unable to connect to sandbox environment: {e!s}")
        await websocket.close(code=1011, reason=f"Unable to connect to sandbox environment: {e!s}")
    except Exception as e:
        logger.error(f"WebSocket error: {e!s}")
        await websocket.close(code=1011, reason=f"WebSocket error: {e!s}")


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
    import httpx
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
        import time

        timestamp = int(time.time() * 1000)
        logger.info(f"[VNC Screenshot] Fetching from sandbox {sandbox.base_url}, session={session_id}, ts={timestamp}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            sandbox_url = f"{sandbox.base_url}/api/v1/vnc/screenshot"
            response = await client.get(
                sandbox_url,
                params={"quality": quality, "scale": scale, "format": "jpeg", "_t": timestamp},
                headers={"Cache-Control": "no-cache, no-store"},
            )
            response.raise_for_status()

            content_size = len(response.content)
            logger.info(f"[VNC Screenshot] Received {content_size} bytes from sandbox")

            return Response(
                content=response.content,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "X-Screenshot-Timestamp": str(timestamp),
                    "X-Screenshot-Size": str(content_size),
                },
            )
    except Exception as e:
        logger.error(f"Failed to fetch VNC screenshot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch screenshot: {e!s}")


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
