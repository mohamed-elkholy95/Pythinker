import asyncio
import json
import logging
import time

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from app.schemas.shell import (
    ShellExecRequest,
    ShellViewRequest,
    ShellWaitRequest,
    ShellWriteToProcessRequest,
    ShellKillProcessRequest,
)
from app.schemas.response import Response
from app.services.shell import shell_service
from app.core.exceptions import BadRequestException

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/exec", response_model=Response)
async def exec_command(request: ShellExecRequest):
    """
    Execute command in the specified shell session
    """
    # If no session ID is provided, automatically create one
    if not request.id or request.id == "":
        request.id = shell_service.create_session_id()

    result = await shell_service.exec_command(
        session_id=request.id, exec_dir=request.exec_dir, command=request.command
    )

    # Construct response
    return Response(success=True, message="Command executed", data=result.model_dump())


@router.post("/view", response_model=Response)
async def view_shell(request: ShellViewRequest):
    """
    View output of the specified shell session
    """
    if not request.id or request.id == "":
        raise BadRequestException("Session ID not provided")

    result = await shell_service.view_shell(
        session_id=request.id, console=request.console
    )

    # Construct response
    return Response(
        success=True,
        message="Session content retrieved successfully",
        data=result.model_dump(),
    )


@router.post("/wait", response_model=Response)
async def wait_for_process(request: ShellWaitRequest):
    """
    Wait for the process in the specified shell session to return
    """
    result = await shell_service.wait_for_process(
        session_id=request.id, seconds=request.seconds
    )

    # Construct response
    return Response(
        success=True,
        message=f"Process completed, return code: {result.returncode}",
        data=result.model_dump(),
    )


@router.post("/write", response_model=Response)
async def write_to_process(request: ShellWriteToProcessRequest):
    """
    Write input to the process in the specified shell session
    """
    if not request.id or request.id == "":
        raise BadRequestException("Session ID not provided")

    result = await shell_service.write_to_process(
        session_id=request.id, input_text=request.input, press_enter=request.press_enter
    )

    # Construct response
    return Response(success=True, message="Input written", data=result.model_dump())


@router.post("/kill", response_model=Response)
async def kill_process(request: ShellKillProcessRequest):
    """
    Terminate the process in the specified shell session
    """
    result = await shell_service.kill_process(session_id=request.id)

    # Construct response
    message = "Process terminated" if result.status == "terminated" else "Process ended"
    return Response(success=True, message=message, data=result.model_dump())


@router.get("/stream/{session_id}")
async def stream_shell_output(session_id: str):
    """Push-based SSE stream for real-time shell output.

    Streams delta output from the shell session as Server-Sent Events.
    Emits three event types:
      - ``output``: new stdout content (delta since last emission)
      - ``complete``: process has exited (includes returncode)
      - ``heartbeat``: keep-alive sent every ~5 s to prevent proxy timeouts

    The connection closes automatically when the process exits or the
    session is not found.
    """

    async def _event_generator():
        # Validate session exists
        if session_id not in shell_service.active_shells:
            yield _sse_event("error", {"message": f"Session {session_id} not found"})
            return

        last_output_len = 0
        last_heartbeat = time.monotonic()
        poll_interval = 0.2  # 200 ms — 5× faster than HTTP polling

        while session_id in shell_service.active_shells:
            shell = shell_service.active_shells[session_id]
            raw_output = shell["output"]
            process = shell["process"]

            # Compute delta
            current_len = len(raw_output)
            if current_len > last_output_len:
                # Remove ANSI codes from the delta only
                delta_raw = raw_output[last_output_len:]
                delta = shell_service._remove_ansi_escape_codes(delta_raw)
                last_output_len = current_len
                yield _sse_event("output", {"content": delta})
                last_heartbeat = time.monotonic()
            elif raw_output != "" and current_len < last_output_len:
                # Output was truncated/reset — send full cleaned output
                delta = shell_service._remove_ansi_escape_codes(raw_output)
                last_output_len = current_len
                yield _sse_event("output", {"content": delta, "reset": True})
                last_heartbeat = time.monotonic()

            # Check if process has exited
            if process.returncode is not None:
                # Drain any final output after a brief delay
                await asyncio.sleep(0.05)
                shell_after = shell_service.active_shells.get(session_id)
                if shell_after:
                    final_output = shell_after["output"]
                    if len(final_output) > last_output_len:
                        delta_raw = final_output[last_output_len:]
                        delta = shell_service._remove_ansi_escape_codes(delta_raw)
                        yield _sse_event("output", {"content": delta})

                yield _sse_event(
                    "complete",
                    {"returncode": process.returncode},
                )
                return

            # Heartbeat every 5 s
            now = time.monotonic()
            if now - last_heartbeat >= 5.0:
                yield _sse_event("heartbeat", {})
                last_heartbeat = now

            await asyncio.sleep(poll_interval)

        # Session disappeared (cleaned up externally)
        yield _sse_event("error", {"message": "Session ended"})

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
