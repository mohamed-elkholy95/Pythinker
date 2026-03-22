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

from app.core.config import settings as sandbox_settings
from app.services.cdp_screencast import (
    CDPScreencastService,
    ScreencastConfig,
    get_screencast_service,
)
from app.services.x11_screencast import (
    drain_x11_event_queue,
    is_x11_available,
    stream_x11_frames,
)

# Active service for the running WebSocket stream (distinct from the singleton
# used by /frame). Tracked so preemption can close its CDP socket immediately,
# waking any blocked receive() call instead of waiting the full frame timeout.
_active_stream_service: CDPScreencastService | None = None

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
# Serialize access to the preemption globals so two simultaneous WebSocket
# connections don't race to overwrite each other's events.
_slot_lock: asyncio.Lock = asyncio.Lock()
# Must exceed CDP_COMMAND_TIMEOUT (6s) because stop_screencast() sends a CDP
# command that may block for the full command timeout when Chrome is hung.
_PREEMPT_WAIT_TIMEOUT = sandbox_settings.CDP_PREEMPT_WAIT_TIMEOUT


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

    service = get_screencast_service()

    try:
        if not await service.ensure_connected():
            raise HTTPException(
                status_code=503, detail="Failed to connect to Chrome CDP"
            )

        image_data = await service.capture_single_frame(
            quality=quality, image_format=format
        )

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
    global _active_stop_event, _active_done_event, _active_stream_service

    await websocket.accept()
    logger.info(
        f"[CDP Stream] WebSocket connected: quality={quality}, max_fps={max_fps}"
    )

    # ── Preempt any existing stream (under lock) ─────────────────────
    async with _slot_lock:
        if _active_stop_event is not None:
            logger.info("[CDP Stream] Preempting existing stream for new connection")
            _active_stop_event.set()
            # Close the old stream's CDP WebSocket immediately so its blocked
            # receive() call raises instead of waiting the full frame timeout.
            # This makes cleanup instantaneous rather than waiting up to
            # _STREAM_FRAME_TIMEOUT (10s) for the next frame to arrive.
            if _active_stream_service is not None:
                asyncio.create_task(_active_stream_service.disconnect())
            if _active_done_event is not None:
                try:
                    await asyncio.wait_for(
                        _active_done_event.wait(), timeout=_PREEMPT_WAIT_TIMEOUT
                    )
                except TimeoutError:
                    logger.warning(
                        "[CDP Stream] Previous stream cleanup timed out after "
                        f"{_PREEMPT_WAIT_TIMEOUT}s — force-clearing slot. "
                        "Old stream may have a hung CDP command."
                    )
                    # Force-clear the slot so the new stream can proceed.
                    # The old stream's finally block will still run eventually
                    # and call done_event.set(), but we don't wait for it.
                    _active_stop_event = None
                    _active_done_event = None
                    _active_stream_service = None

        # ── Register this stream ─────────────────────────────────────
        stop_event = asyncio.Event()
        done_event = asyncio.Event()
        _active_stop_event = stop_event
        _active_done_event = done_event

    # ── X11 display capture mode ───────────────────────────────────
    # When SCREENCAST_MODE=x11, capture the full Xvfb display (including
    # Chrome's tab bar, address bar, and window decorations) using xwd.
    # This matches the VNC takeover view appearance.
    use_x11 = (
        sandbox_settings.SCREENCAST_MODE == "x11" and is_x11_available()
    )

    if use_x11:
        logger.info("[X11 Stream] Using X11 display capture mode")
        frame_count = 0
        paused = False
        disconnected = asyncio.Event()
        _PING_INTERVAL = 5.0

        async def _x11_receive_control():
            nonlocal paused
            try:
                while True:
                    msg = await websocket.receive_text()
                    if msg == "pause":
                        paused = True
                    elif msg == "resume":
                        paused = False
                    elif msg == "pong":
                        pass
            except WebSocketDisconnect:
                disconnected.set()

        async def _x11_send_pings():
            try:
                while not disconnected.is_set() and not stop_event.is_set():
                    await asyncio.sleep(_PING_INTERVAL)
                    if disconnected.is_set() or stop_event.is_set():
                        break
                    try:
                        await websocket.send_text("ping")
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        disconnected.set()
                        break
            except asyncio.CancelledError:
                pass

        recv_task = asyncio.create_task(_x11_receive_control())
        ping_task = asyncio.create_task(_x11_send_pings())
        x11_exited_cleanly = True  # Assume clean until proven otherwise

        try:
            stream_cancel = asyncio.Event()

            async def _x11_stop_monitor():
                try:
                    await stop_event.wait()
                    stream_cancel.set()
                except asyncio.CancelledError:
                    pass

            stop_task = asyncio.create_task(_x11_stop_monitor())

            try:
                async for frame in stream_x11_frames(
                    quality=quality,
                    max_fps=max_fps,
                    cancel_event=stream_cancel,
                ):
                    if disconnected.is_set() or stop_event.is_set():
                        break
                    if paused:
                        await asyncio.sleep(0.1)
                        continue
                    try:
                        await websocket.send_bytes(frame.data)
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        disconnected.set()
                        break
                    frame_count += 1
                    if frame_count % 100 == 0:
                        logger.debug("[X11 Stream] Sent %d frames", frame_count)
            finally:
                stop_task.cancel()
                try:
                    await stop_task
                except asyncio.CancelledError:
                    pass
        except WebSocketDisconnect:
            x11_exited_cleanly = True
        except Exception as e:
            logger.error("[X11 Stream] Error: %s", e, exc_info=True)
        else:
            # X11 stream exited normally (consecutive failures or cancel).
            # If the client is still connected and not preempted, fall
            # through to the CDP path below as a runtime fallback.
            x11_exited_cleanly = disconnected.is_set() or stop_event.is_set()
        finally:
            recv_task.cancel()
            ping_task.cancel()
            for t in (recv_task, ping_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        if x11_exited_cleanly:
            # Drain queued X11 events to prevent "event leak: N queued"
            # warnings from x11vnc during rapid session cycling.
            await drain_x11_event_queue()
            done_event.set()
            async with _slot_lock:
                if _active_stop_event is stop_event:
                    _active_stop_event = None
                    _active_done_event = None
                    _active_stream_service = None
            logger.info("[X11 Stream] Session ended, sent %d frames", frame_count)
            return

        # X11 capture failed — fall through to CDP screencast below
        logger.warning(
            "[X11 Stream] Falling back to CDP screencast after %d frames",
            frame_count,
        )

    # ── CDP screencast mode (original) ──────────────────────────────
    # Create a fresh service instance per stream so streams never share a CDP
    # WebSocket. The singleton (_service_instance) is reserved for the /frame
    # endpoint's short-lived captures; streaming gets its own independent session.
    service = CDPScreencastService(
        ScreencastConfig(
            format="jpeg",
            quality=quality,
            max_height=sandbox_settings.SCREENCAST_MAX_HEIGHT,
        )
    )
    # Register this stream's service so preemption can disconnect it if needed.
    async with _slot_lock:
        _active_stream_service = service
    min_frame_interval = 1.0 / max_fps
    paused = False
    frame_count = 0
    _MAX_START_RETRIES = 3
    _RETRY_DELAY = 0.5  # seconds between retries
    _MAX_STREAM_RECOVERIES = 2  # Max times to restart stream after Chrome hang
    _PING_INTERVAL = 5.0  # Server-side ping interval (seconds)

    async def _start_screencast_with_retries() -> bool:
        """Attempt to connect and start screencast with retries.

        Returns True if screencast is running, False if all attempts failed.
        Handles page navigation/crash by invalidating cache between retries.
        """
        for attempt in range(_MAX_START_RETRIES):
            if stop_event.is_set():
                return False

            if not await service.connect():
                if attempt < _MAX_START_RETRIES - 1:
                    logger.warning(
                        f"[CDP Stream] Connect failed (attempt {attempt + 1}/{_MAX_START_RETRIES}), "
                        f"retrying in {_RETRY_DELAY}s..."
                    )
                    service.invalidate_cache()
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                return False

            if await service.start_screencast():
                return True

            # start_screencast failed - page may be detached
            logger.warning(
                f"[CDP Stream] Screencast start failed (attempt {attempt + 1}/{_MAX_START_RETRIES})"
            )
            await service.disconnect()
            if attempt < _MAX_START_RETRIES - 1:
                service.invalidate_cache()
                await asyncio.sleep(_RETRY_DELAY)

        return False

    try:
        # Initial screencast start
        if not await _start_screencast_with_retries():
            if stop_event.is_set():
                await websocket.close(code=1001, reason="Preempted by newer connection")
            else:
                await websocket.send_json(
                    {"error": "Failed to start screencast after retries"}
                )
                await websocket.close()
            return

        last_frame_time = 0

        # Shared event to signal the frame loop when the client disconnects
        disconnected = asyncio.Event()

        # Combined cancel event propagated into stream_frames() for fast exit.
        # Set when either the client disconnects OR preemption is signalled.
        stream_cancel = asyncio.Event()

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
                stream_cancel.set()  # Propagate to stream_frames() immediately

        async def send_pings():
            """Server-side ping to detect dead client connections.

            Sends a JSON "ping" message every _PING_INTERVAL seconds. The client
            should respond with "pong" (handled by receive_control). If the send
            fails, the client has disconnected.
            """
            try:
                while not disconnected.is_set() and not stop_event.is_set():
                    await asyncio.sleep(_PING_INTERVAL)
                    if disconnected.is_set() or stop_event.is_set():
                        break
                    try:
                        await websocket.send_text("ping")
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        # AssertionError: websockets legacy protocol race during teardown
                        disconnected.set()
                        stream_cancel.set()
                        break
            except asyncio.CancelledError:
                pass

        receive_task = asyncio.create_task(receive_control())
        ping_task = asyncio.create_task(send_pings())

        # Monitor preemption and propagate to stream_cancel for fast exit
        async def monitor_stop():
            """Watch stop_event and propagate to stream_cancel."""
            try:
                await stop_event.wait()
                stream_cancel.set()
            except asyncio.CancelledError:
                pass

        stop_monitor_task = asyncio.create_task(monitor_stop())

        try:
            # Stream loop with auto-recovery
            # When Chrome hangs, stream_frames() breaks out (via frame timeout
            # watchdog in CDPScreencastService). We attempt recovery by
            # reconnecting to CDP and restarting the screencast.
            recovery_count = 0

            while not disconnected.is_set() and not stop_event.is_set():
                stream_yielded_frames = False

                async for frame in service.stream_frames(cancel_event=stream_cancel):
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
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        disconnected.set()
                        stream_cancel.set()
                        break
                    frame_count += 1
                    stream_yielded_frames = True

                    if frame_count % 100 == 0:
                        logger.debug(f"[CDP Stream] Sent {frame_count} frames")

                # stream_frames() exited — check if we should recover or exit
                if disconnected.is_set() or stop_event.is_set():
                    break

                # If stream exited without yielding frames and Chrome is
                # healthy, the page is likely static or a transient WS
                # hiccup occurred.  Send a fallback screenshot and retry
                # without counting it as a recovery failure.
                if not stream_yielded_frames and await service.health_check():
                    logger.info(
                        "[CDP Stream] Stream exited with 0 frames but Chrome "
                        "is healthy — sending fallback screenshot before retry"
                    )
                    try:
                        fallback = await service.capture_single_frame()
                        if fallback:
                            await websocket.send_bytes(fallback)
                            frame_count += 1
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        disconnected.set()
                        stream_cancel.set()
                        break
                    except Exception as e:
                        logger.debug(f"[CDP Stream] Fallback screenshot failed: {e}")
                    await asyncio.sleep(2.0)
                    continue

                # Stream exited without client disconnect — Chrome may be hung
                recovery_count += 1
                if recovery_count > _MAX_STREAM_RECOVERIES:
                    logger.error(
                        f"[CDP Stream] Exhausted {_MAX_STREAM_RECOVERIES} recovery attempts. "
                        "Closing stream."
                    )
                    try:
                        await websocket.send_json(
                            {
                                "error": "Chrome became unresponsive after multiple recovery attempts"
                            }
                        )
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        pass
                    break

                logger.warning(
                    f"[CDP Stream] Frame stream exited (recovery {recovery_count}/{_MAX_STREAM_RECOVERIES}). "
                    f"Frames so far: {frame_count}. Attempting CDP reconnect..."
                )

                # Recovery: disconnect, invalidate cache, reconnect
                await service.stop_screencast()
                await service.disconnect()
                service.invalidate_cache()
                await asyncio.sleep(_RETRY_DELAY)

                if not await _start_screencast_with_retries():
                    logger.error(
                        "[CDP Stream] Recovery failed — cannot restart screencast"
                    )
                    try:
                        await websocket.send_json(
                            {"error": "Failed to recover screencast after Chrome hang"}
                        )
                    except (RuntimeError, WebSocketDisconnect, AssertionError):
                        pass
                    break

                logger.info(
                    f"[CDP Stream] Recovery {recovery_count} successful — resuming frame stream"
                )

        finally:
            receive_task.cancel()
            ping_task.cancel()
            stop_monitor_task.cancel()
            for task in (receive_task, ping_task, stop_monitor_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except WebSocketDisconnect:
        logger.info("[CDP Stream] Client disconnected")
    except AssertionError:
        # websockets legacy protocol race condition during connection teardown
        logger.info(
            "[CDP Stream] Connection closed during teardown (websockets assertion)"
        )
    except Exception as e:
        logger.error(f"[CDP Stream] Error: {e}", exc_info=True)
    finally:
        await service.stop_screencast()
        await service.disconnect()
        # Signal that cleanup is complete so a waiting newcomer can proceed
        done_event.set()
        async with _slot_lock:
            if _active_stop_event is stop_event:
                _active_stop_event = None
                _active_done_event = None
                _active_stream_service = None
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
        service = CDPScreencastService(
            ScreencastConfig(
                format="jpeg",
                quality=quality,
                max_height=sandbox_settings.SCREENCAST_MAX_HEIGHT,
            )
        )
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
        }

    return {"available": False, "message": "Chrome CDP not available"}
