"""VNC-related API endpoints for desktop screenshot capture and control."""

import asyncio
import logging
import shlex
import shutil
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app.services.cdp_screencast import CDPScreencastService, ScreencastConfig

router = APIRouter()
logger = logging.getLogger(__name__)

_SCREENSHOT_TIMEOUT_SECONDS = 5.0
_DISPLAY_NAME = ":1"


def _xwd_pipeline_available() -> bool:
    """Return True when xwd+convert binaries are available."""
    return shutil.which("xwd") is not None and shutil.which("convert") is not None


async def _capture_with_cdp(quality: int, image_format: Literal["jpeg", "png"]) -> bytes | None:
    """Capture a single frame via Chrome DevTools Protocol."""
    service = CDPScreencastService(ScreencastConfig(format=image_format, quality=quality))
    try:
        async def _capture_once() -> bytes | None:
            if not await service.connect():
                return None
            return await service.capture_single_frame()

        image_data = await asyncio.wait_for(_capture_once(), timeout=_SCREENSHOT_TIMEOUT_SECONDS)
        if not image_data:
            logger.warning("[Screenshot] CDP capture returned empty frame")
            return None
        return image_data
    except asyncio.TimeoutError:
        logger.warning("[Screenshot] CDP capture timed out after %.1fs", _SCREENSHOT_TIMEOUT_SECONDS)
        return None
    except Exception as e:
        logger.warning(f"[Screenshot] CDP capture failed: {e}")
        return None
    finally:
        await service.disconnect()


async def _capture_with_xwd_pipeline(
    quality: int,
    scale: float,
    image_format: Literal["jpeg", "png"],
) -> bytes:
    """Capture screenshot using xwd piped into ImageMagick convert."""
    scale_percent = int(scale * 100)
    convert_parts = ["convert", "xwd:-", "-scale", f"{scale_percent}%"]
    if image_format == "jpeg":
        convert_parts.extend(["-quality", str(quality), "jpg:-"])
    else:
        convert_parts.append("png:-")

    convert_cmd = " ".join(shlex.quote(part) for part in convert_parts)
    shell_cmd = f"DISPLAY={_DISPLAY_NAME} xwd -root | {convert_cmd}"
    logger.info(f"[Screenshot] Executing fallback pipeline: {shell_cmd}")

    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        shell_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_SCREENSHOT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(status_code=504, detail="Screenshot capture timed out after 5 seconds")

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        logger.error(f"[Screenshot] xwd pipeline failed: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Screenshot capture failed: {error_msg}")

    return stdout


def _build_screenshot_response(
    image_data: bytes,
    *,
    quality: int,
    scale: float,
    image_format: Literal["jpeg", "png"],
    backend: Literal["cdp", "xwd"],
    elapsed_seconds: float,
) -> Response:
    """Build the screenshot HTTP response with common metadata headers."""
    return Response(
        content=image_data,
        media_type=f"image/{image_format}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Screenshot-Backend": backend,
            "X-Screenshot-Size": str(len(image_data)),
            "X-Screenshot-Scale": str(scale),
            "X-Screenshot-Quality": str(quality) if image_format == "jpeg" else "N/A",
            "X-Screenshot-Timestamp": str(int(time.time() * 1000)),
            "X-Screenshot-Elapsed-Ms": str(int(elapsed_seconds * 1000)),
        },
    )


@router.get("/screenshot")
async def capture_screenshot(
    quality: int = Query(default=75, ge=1, le=100, description="JPEG quality (1-100)"),
    scale: float = Query(default=0.5, ge=0.1, le=1.0, description="Scale factor (0.1-1.0)"),
    format: Literal["jpeg", "png"] = Query(default="jpeg", description="Image format"),
    _t: int = Query(default=0, description="Cache-busting timestamp"),
) -> Response:
    """
    Capture desktop screenshot optimized for thumbnails.

    Backend selection order:
    1. CDP single-frame capture (works in minimal sandbox profile)
    2. Legacy xwd + convert pipeline (when binaries are installed)
    """
    start_time = time.time()
    logger.info(f"[Screenshot] Request received: quality={quality}, scale={scale}, format={format}, _t={_t}")

    try:
        # Prefer CDP because it does not depend on optional X11 add-ons.
        cdp_image = await _capture_with_cdp(quality, format)
        if cdp_image:
            elapsed = time.time() - start_time
            logger.info(f"[Screenshot] Captured {len(cdp_image)} bytes via CDP in {elapsed:.3f}s")
            return _build_screenshot_response(
                cdp_image,
                quality=quality,
                scale=scale,
                image_format=format,
                backend="cdp",
                elapsed_seconds=elapsed,
            )

        # Fallback to xwd pipeline only when required binaries exist.
        if _xwd_pipeline_available():
            xwd_image = await _capture_with_xwd_pipeline(quality, scale, format)
            elapsed = time.time() - start_time
            logger.info(f"[Screenshot] Captured {len(xwd_image)} bytes via xwd pipeline in {elapsed:.3f}s")
            return _build_screenshot_response(
                xwd_image,
                quality=quality,
                scale=scale,
                image_format=format,
                backend="xwd",
                elapsed_seconds=elapsed,
            )

        raise HTTPException(
            status_code=503,
            detail="Screenshot capture unavailable: CDP capture failed and xwd/convert are not installed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Screenshot] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Screenshot capture error: {e}") from e


@router.get("/screenshot/test")
async def test_screenshot_availability():
    """
    Report screenshot backend availability.

    Preferred backend is CDP. xwd/convert is treated as a legacy fallback.
    """
    try:
        cdp_service = CDPScreencastService()
        cdp_ws_url = await cdp_service.get_ws_debugger_url()
        cdp_available = cdp_ws_url is not None

        xwd_available = shutil.which("xwd") is not None
        convert_available = shutil.which("convert") is not None

        display_check = await asyncio.create_subprocess_exec(
            "sh",
            "-c",
            f"DISPLAY={_DISPLAY_NAME} xdpyinfo > /dev/null 2>&1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await display_check.communicate()
        display_available = display_check.returncode == 0

        xwd_pipeline_ready = xwd_available and convert_available and display_available
        available = cdp_available or xwd_pipeline_ready
        preferred_backend = "cdp" if cdp_available else ("xwd" if xwd_pipeline_ready else "none")

        return {
            "available": available,
            "preferred_backend": preferred_backend,
            "backends": {
                "cdp": cdp_available,
                "xwd_pipeline": xwd_pipeline_ready,
            },
            "tools": {
                "xwd": xwd_available,
                "convert": convert_available,
                "display_1": display_available,
            },
            "message": "Screenshot system ready" if available else "No screenshot backend available",
        }

    except Exception as e:
        logger.error(f"Error testing screenshot availability: {e}", exc_info=True)
        return {"available": False, "error": str(e)}
