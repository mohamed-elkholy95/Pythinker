"""
VNC-related API endpoints for desktop screenshot capture and control.
"""

from fastapi import APIRouter, HTTPException, Response, Query
import logging
import asyncio
from typing import Literal

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/screenshot")
async def capture_screenshot(
    quality: int = Query(default=75, ge=1, le=100, description="JPEG quality (1-100)"),
    scale: float = Query(default=0.5, ge=0.1, le=1.0, description="Scale factor (0.1-1.0)"),
    format: Literal["jpeg", "png"] = Query(default="jpeg", description="Image format"),
    _t: int = Query(default=0, description="Cache-busting timestamp")
):
    """
    Capture desktop screenshot optimized for thumbnails.

    Uses xwd to capture the X11 display and ImageMagick convert for processing.
    Scaled down and compressed for efficient transmission.

    Args:
        quality: JPEG quality (1-100, default 75)
        scale: Scale factor (0.1-1.0, default 0.5 for 50% size)
        format: Output format (jpeg or png, default jpeg)

    Returns:
        Image bytes in specified format
    """
    import time
    start_time = time.time()
    logger.info(f"[Screenshot] Request received: quality={quality}, scale={scale}, format={format}, _t={_t}")

    try:
        # Build ImageMagick convert command
        # xwd captures raw X11 display, convert processes it
        if format == "jpeg":
            convert_cmd = f"convert xwd:- -scale {int(scale*100)}% -quality {quality} jpg:-"
        else:
            convert_cmd = f"convert xwd:- -scale {int(scale*100)}% png:-"

        cmd = [
            "sh", "-c",
            f"DISPLAY=:1 xwd -root | {convert_cmd}"
        ]

        logger.info(f"[Screenshot] Executing: DISPLAY=:1 xwd -root | {convert_cmd}")

        # Execute with timeout
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("[Screenshot] Capture timed out after 5 seconds")
            raise HTTPException(
                status_code=504,
                detail="Screenshot capture timed out after 5 seconds"
            )

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"[Screenshot] Command failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Screenshot capture failed: {error_msg}"
            )

        elapsed = time.time() - start_time
        logger.info(f"[Screenshot] Captured {len(stdout)} bytes in {elapsed:.3f}s")

        # Return image with appropriate headers
        media_type = f"image/{format}"
        return Response(
            content=stdout,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Screenshot-Size": str(len(stdout)),
                "X-Screenshot-Scale": str(scale),
                "X-Screenshot-Quality": str(quality) if format == "jpeg" else "N/A",
                "X-Screenshot-Timestamp": str(int(time.time() * 1000)),
                "X-Screenshot-Elapsed-Ms": str(int(elapsed * 1000))
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Screenshot] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Screenshot capture error: {str(e)}"
        )


@router.get("/screenshot/test")
async def test_screenshot_availability():
    """
    Test if screenshot capabilities are available.

    Checks for required X11 tools (xwd, convert).

    Returns:
        Status dict with availability information
    """
    try:
        # Check if xwd is available
        xwd_check = await asyncio.create_subprocess_exec(
            "which", "xwd",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await xwd_check.communicate()
        xwd_available = xwd_check.returncode == 0

        # Check if convert (ImageMagick) is available
        convert_check = await asyncio.create_subprocess_exec(
            "which", "convert",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await convert_check.communicate()
        convert_available = convert_check.returncode == 0

        # Check if DISPLAY :1 is accessible
        display_check = await asyncio.create_subprocess_exec(
            "sh", "-c", "DISPLAY=:1 xdpyinfo > /dev/null 2>&1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await display_check.communicate()
        display_available = display_check.returncode == 0

        all_available = xwd_available and convert_available and display_available

        return {
            "available": all_available,
            "tools": {
                "xwd": xwd_available,
                "convert": convert_available,
                "display_1": display_available
            },
            "message": "Screenshot system ready" if all_available else "Screenshot system not fully configured"
        }

    except Exception as e:
        logger.error(f"Error testing screenshot availability: {e}")
        return {
            "available": False,
            "error": str(e)
        }
