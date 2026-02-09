"""
CDP Screencast API - Low-latency browser streaming endpoints.

Provides WebSocket and SSE endpoints for real-time browser view streaming
with 10-50ms latency via Chrome DevTools Protocol.
"""

import asyncio
import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.services.cdp_screencast import CDPScreencastService, ScreencastConfig

router = APIRouter()
logger = logging.getLogger(__name__)
_MAX_STREAM_CLIENTS = 1
_STREAM_CLIENT_SEMAPHORE = asyncio.Semaphore(_MAX_STREAM_CLIENTS)


@router.get("/frame")
async def capture_frame(
    quality: int = Query(default=80, ge=1, le=100, description="JPEG quality (1-100)"),
    format: Literal["jpeg", "png"] = Query(default="jpeg", description="Image format"),
):
    """
    Capture a single frame from the browser via CDP.

    This is faster than the VNC/xwd approach for one-off screenshots.
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
            raise HTTPException(status_code=503, detail="Failed to connect to Chrome CDP")

        image_data = await service.capture_single_frame()
        await service.disconnect()

        if not image_data:
            raise HTTPException(status_code=500, detail="Failed to capture frame")

        elapsed = time.time() - start_time
        logger.info(f"[CDP Screenshot] Captured {len(image_data)} bytes in {elapsed*1000:.1f}ms")

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

    Args:
        quality: JPEG quality (1-100, default 70 for streaming)
        max_fps: Maximum frames per second (1-30, default 15)

    Protocol:
        - Server sends binary JPEG frames
        - Client can send "pause" to pause, "resume" to resume
        - Server sends "ping" every 5 seconds, client should respond "pong"
    """
    await websocket.accept()
    logger.info(f"[CDP Stream] WebSocket connected: quality={quality}, max_fps={max_fps}")

    slot_acquired = False
    try:
        await asyncio.wait_for(_STREAM_CLIENT_SEMAPHORE.acquire(), timeout=0.5)
        slot_acquired = True
    except TimeoutError:
        await websocket.send_json({"error": "Screencast is busy. Please retry."})
        await websocket.close(code=1013, reason="Screencast is busy")
        logger.warning("[CDP Stream] Rejected connection because screencast slot is busy")
        return

    config = ScreencastConfig(format="jpeg", quality=quality)
    service = CDPScreencastService(config)
    min_frame_interval = 1.0 / max_fps
    paused = False
    frame_count = 0

    try:
        if not await service.connect():
            await websocket.send_json({"error": "Failed to connect to Chrome CDP"})
            await websocket.close()
            return

        if not await service.start_screencast():
            await websocket.send_json({"error": "Failed to start screencast"})
            await websocket.close()
            return

        last_frame_time = 0

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
                pass

        receive_task = asyncio.create_task(receive_control())

        try:
            async for frame in service.stream_frames():
                if paused:
                    await asyncio.sleep(0.1)
                    continue

                # Rate limiting
                now = time.time()
                if now - last_frame_time < min_frame_interval:
                    continue
                last_frame_time = now

                # Send frame as binary
                await websocket.send_bytes(frame.data)
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
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        await service.stop_screencast()
        await service.disconnect()
        if slot_acquired:
            _STREAM_CLIENT_SEMAPHORE.release()
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
            async with session.get("http://127.0.0.1:9222/json/version", timeout=aiohttp.ClientTimeout(total=2)) as resp:
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
        return {"available": False, "message": "Chrome CDP not available", "error": str(e)}

    return {"available": False, "message": "Chrome CDP not available"}
