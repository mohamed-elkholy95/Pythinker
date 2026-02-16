"""
CDP Screencast API - Low-latency browser streaming endpoints.

Provides WebSocket and SSE endpoints for real-time browser view streaming
with 10-50ms latency via Chrome DevTools Protocol.

Connection Model:
    Only one screencast stream is active at a time. New connections preempt
    (gracefully evict) the current stream instead of being rejected, ensuring
    the latest viewer always succeeds even during rapid reconnect cycles.
"""

import asyncio
import logging
import time
from typing import Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse

from app.services.cdp_screencast import CDPScreencastService, ScreencastConfig

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stream slot management — preemption model (replaces semaphore)
#
# Only one screencast stream runs at a time.  When a new WebSocket arrives
# the existing stream is signalled to stop via _active_stop_event, and the
# newcomer waits for _active_done_event before starting its own CDP session.
# This eliminates the race condition where the old stream's cleanup slightly
# outlasts the fixed semaphore timeout, causing the new connection to be
# rejected even though the slot is about to free up.
# ---------------------------------------------------------------------------
_active_stop_event: asyncio.Event | None = None
_active_done_event: asyncio.Event | None = None
_PREEMPT_WAIT_TIMEOUT = 3.0  # max seconds to wait for old stream cleanup


@router.get("/frame")
async def capture_frame(
    quality: int = Query(default=80, ge=1, le=100, description="JPEG quality (1-100)"),
    format: Literal["jpeg", "png"] = Query(default="jpeg", description="Image format"),
):
    """
    Capture a single frame from the browser via CDP.

    This is faster than the xwd fallback approach for one-off screenshots.
    Typical latency: 10-30ms vs 50-100ms for xwd.

    Args:
        quality: JPEG quality (1-100, default 80)
        format: Output format (jpeg or png, default jpeg)

    Returns:
        Image bytes in specified format
    """
    start_time = time.time()
    logger.info(f"[CDP Screenshot] Request: quality={quality}, format={format}")

    config = ScreencastConfig(format=format, quality=quality)
    service = CDPScreencastService(config)

    try:
        if not await service.connect():
            raise HTTPException(
                status_code=503, detail="Failed to connect to Chrome CDP"
            )

        image_data = await service.capture_single_frame()
        await service.disconnect()

        if not image_data:
            raise HTTPException(status_code=500, detail="Failed to capture frame")

        elapsed = time.time() - start_time
        logger.info(
            f"[CDP Screenshot] Captured {len(image_data)} bytes in {elapsed * 1000:.1f}ms"
        )

        return Response(
            content=image_data,
            media_type=f"image/{format}",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Capture-Method": "cdp",
                "X-Capture-Elapsed-Ms": str(int(elapsed * 1000)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CDP Screenshot] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/stream")
async def stream_frames_ws(
    websocket: WebSocket,
    quality: int = Query(default=70, ge=1, le=100),
    max_fps: int = Query(default=15, ge=1, le=30),
):
    """
    WebSocket endpoint for real-time browser frame streaming.

    Streams JPEG frames at up to max_fps. Each message is a binary JPEG image.
    Client should display frames as they arrive for lowest latency.

    Only one stream is active at a time.  A new connection **preempts** any
    existing stream (signals it to stop and waits for cleanup) instead of
    being rejected, so rapid reconnects always succeed.

    Args:
        quality: JPEG quality (1-100, default 70 for streaming)
        max_fps: Maximum frames per second (1-30, default 15)

    Protocol:
        - Server sends binary JPEG frames
        - Client can send "pause" to pause, "resume" to resume
        - Server sends "ping" every 5 seconds, client should respond "pong"
    """
    global _active_stop_event, _active_done_event

    await websocket.accept()
    logger.info(
        f"[CDP Stream] WebSocket connected: quality={quality}, max_fps={max_fps}"
    )

    # ── Preempt any existing stream ──────────────────────────────────
    if _active_stop_event is not None:
        logger.info("[CDP Stream] Preempting existing stream for new connection")
        _active_stop_event.set()
        if _active_done_event is not None:
            try:
                await asyncio.wait_for(
                    _active_done_event.wait(), timeout=_PREEMPT_WAIT_TIMEOUT
                )
            except TimeoutError:
                logger.warning("[CDP Stream] Previous stream cleanup timed out")

    # ── Register this stream ─────────────────────────────────────────
    stop_event = asyncio.Event()
    done_event = asyncio.Event()
    _active_stop_event = stop_event
    _active_done_event = done_event

    config = ScreencastConfig(format="jpeg", quality=quality)
    service = CDPScreencastService(config)
    min_frame_interval = 1.0 / max_fps
    paused = False
    frame_count = 0
    _MAX_START_RETRIES = 3
    _RETRY_DELAY = 0.5  # seconds between retries

    try:
        # Retry connection + screencast start to recover from page navigation/crash.
        # When Chrome navigates, the old page target becomes detached. Retrying
        # gives Chrome time to register the new page target.
        started = False
        for attempt in range(_MAX_START_RETRIES):
            if stop_event.is_set():
                # We were preempted before we even started
                await websocket.close(code=1001, reason="Preempted by newer connection")
                return

            if not await service.connect():
                if attempt < _MAX_START_RETRIES - 1:
                    logger.warning(
                        f"[CDP Stream] Connect failed (attempt {attempt + 1}/{_MAX_START_RETRIES}), "
                        f"retrying in {_RETRY_DELAY}s..."
                    )
                    service.invalidate_cache()
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                await websocket.send_json({"error": "Failed to connect to Chrome CDP"})
                await websocket.close()
                return

            if await service.start_screencast():
                started = True
                break

            # start_screencast failed - page may be detached
            logger.warning(
                f"[CDP Stream] Screencast start failed (attempt {attempt + 1}/{_MAX_START_RETRIES})"
            )
            await service.disconnect()
            if attempt < _MAX_START_RETRIES - 1:
                service.invalidate_cache()
                await asyncio.sleep(_RETRY_DELAY)

        if not started:
            await websocket.send_json({"error": "Failed to start screencast after retries"})
            await websocket.close()
            return

        last_frame_time = 0

        # Shared event to signal the frame loop when the client disconnects
        disconnected = asyncio.Event()

        # Create tasks for sending frames and receiving control messages
        async def receive_control():
            nonlocal paused
            try:
                while True:
                    msg = await websocket.receive_text()
                    if msg == "pause":
                        paused = True
                        logger.debug("[CDP Stream] Paused")
                    elif msg == "resume":
                        paused = False
                        logger.debug("[CDP Stream] Resumed")
                    elif msg == "pong":
                        pass  # Keep-alive response
            except WebSocketDisconnect:
                disconnected.set()

        receive_task = asyncio.create_task(receive_control())

        try:
            async for frame in service.stream_frames():
                if disconnected.is_set() or stop_event.is_set():
                    break

                if paused:
                    await asyncio.sleep(0.1)
                    continue

                # Rate limiting
                now = time.time()
                if now - last_frame_time < min_frame_interval:
                    continue
                last_frame_time = now

                # Send frame as binary
                try:
                    await websocket.send_bytes(frame.data)
                except (RuntimeError, WebSocketDisconnect):
                    # Client already disconnected
                    break
                frame_count += 1

                if frame_count % 100 == 0:
                    logger.debug(f"[CDP Stream] Sent {frame_count} frames")

        finally:
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info("[CDP Stream] Client disconnected")
    except Exception as e:
        logger.error(f"[CDP Stream] Error: {e}", exc_info=True)
    finally:
        await service.stop_screencast()
        await service.disconnect()
        # Signal that cleanup is complete so a waiting newcomer can proceed
        done_event.set()
        if _active_stop_event is stop_event:
            _active_stop_event = None
            _active_done_event = None
        logger.info(f"[CDP Stream] Session ended, sent {frame_count} frames")


@router.get("/stream/mjpeg")
async def stream_frames_mjpeg(
    quality: int = Query(default=70, ge=1, le=100),
    max_fps: int = Query(default=10, ge=1, le=30),
):
    """
    MJPEG stream endpoint for browser frame streaming.

    Compatible with <img> tags and simple clients that support MJPEG.
    Lower performance than WebSocket but simpler to consume.

    Args:
        quality: JPEG quality (1-100, default 70)
        max_fps: Maximum frames per second (1-30, default 10)

    Returns:
        MJPEG stream (multipart/x-mixed-replace)
    """
    logger.info(f"[CDP MJPEG] Stream started: quality={quality}, max_fps={max_fps}")

    async def generate_mjpeg():
        config = ScreencastConfig(format="jpeg", quality=quality)
        service = CDPScreencastService(config)
        min_frame_interval = 1.0 / max_fps
        last_frame_time = 0

        try:
            if not await service.connect():
                return

            if not await service.start_screencast():
                return

            async for frame in service.stream_frames():
                now = time.time()
                if now - last_frame_time < min_frame_interval:
                    continue
                last_frame_time = now

                # MJPEG frame format
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame.data)).encode() + b"\r\n"
                    b"\r\n" + frame.data + b"\r\n"
                )

        except asyncio.CancelledError:
            pass
        finally:
            await service.stop_screencast()
            await service.disconnect()
            logger.info("[CDP MJPEG] Stream ended")

    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/status")
async def screencast_status():
    """
    Check CDP screencast availability and Chrome connection status.

    Returns:
        Status dict with CDP availability information
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:9222/json/version",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                if resp.status == 200:
                    version_info = await resp.json()
                    return {
                        "available": True,
                        "cdp_version": version_info.get("Protocol-Version"),
                        "browser": version_info.get("Browser"),
                        "user_agent": version_info.get("User-Agent"),
                        "message": "CDP screencast ready",
                    }
    except Exception as e:
        logger.warning(f"CDP status check failed: {e}")
        return {
            "available": False,
            "message": "Chrome CDP not available",
            "error": str(e),
        }

    return {"available": False, "message": "Chrome CDP not available"}
