"""
X11 Display Screencast Service - Full desktop capture including browser chrome.

Unlike CDP Page.startScreencast which captures only the page viewport,
this service captures the entire X11 display (Xvfb :99) including Chrome's
tab bar, address bar, and window decorations — matching VNC takeover view.

Uses xwd (X Window Dump) + Pillow for frame capture, streaming JPEG frames
through the same WebSocket protocol as the CDP screencast.

Architecture:
    Frontend -> Backend proxy -> Sandbox screencast API -> X11 Service -> Xvfb display
"""

import asyncio
import io
import logging
import shutil
import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)

_DISPLAY = ":99"
_CAPTURE_TIMEOUT = 5.0  # seconds per xwd capture
_XDOTOOL_SYNC_TIMEOUT = 2.0  # seconds for XSync drain


@dataclass
class X11ScreencastFrame:
    """A single frame captured from the X11 display."""

    data: bytes  # Raw JPEG image bytes
    timestamp: float
    width: int
    height: int


def _parse_xwd_to_pil(data: bytes) -> "PILImage.Image | None":
    """Parse XWD (X Window Dump) format into a PIL Image.

    Handles the common ZPixmap format with 24 or 32 bits per pixel.
    """
    from PIL import Image

    try:
        if len(data) < 100:
            return None

        header_size = struct.unpack(">I", data[0:4])[0]
        file_version = struct.unpack(">I", data[4:8])[0]

        if file_version != 7:
            return None

        pixmap_width = struct.unpack(">I", data[16:20])[0]
        pixmap_height = struct.unpack(">I", data[20:24])[0]
        bits_per_pixel = struct.unpack(">I", data[44:48])[0]
        bytes_per_line = struct.unpack(">I", data[48:52])[0]
        ncolors = struct.unpack(">I", data[76:80])[0]

        pixel_offset = header_size + ncolors * 12
        pixel_data = data[pixel_offset:]

        expected_size = bytes_per_line * pixmap_height
        if len(pixel_data) < expected_size:
            return None

        if bits_per_pixel == 32:
            return Image.frombytes(
                "RGB",
                (pixmap_width, pixmap_height),
                pixel_data,
                "raw",
                "BGRX",
                bytes_per_line,
            )
        elif bits_per_pixel == 24:
            return Image.frombytes(
                "RGB",
                (pixmap_width, pixmap_height),
                pixel_data,
                "raw",
                "BGR",
                bytes_per_line,
            )
        return None
    except Exception as e:
        logger.debug("XWD parse failed: %s", e)
        return None


def _pil_to_jpeg(img: "PILImage.Image", quality: int = 70) -> bytes:
    """Convert PIL Image to JPEG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=False)
    return buf.getvalue()


async def _capture_x11_frame(quality: int = 70) -> X11ScreencastFrame | None:
    """Capture a single frame from the X11 display.

    Uses xwd -root to capture the full display including window decorations.
    All arguments to create_subprocess_exec are hardcoded constants (safe).
    """
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "xwd", "-root", "-display", _DISPLAY,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_CAPTURE_TIMEOUT
        )

        if proc.returncode != 0 or not stdout:
            logger.debug(
                "xwd capture failed: %s",
                stderr.decode().strip() if stderr else "",
            )
            return None

        img = _parse_xwd_to_pil(stdout)
        if img is None:
            return None

        jpeg_data = _pil_to_jpeg(img, quality)

        return X11ScreencastFrame(
            data=jpeg_data,
            timestamp=time.monotonic(),
            width=img.width,
            height=img.height,
        )
    except asyncio.TimeoutError:
        logger.warning("X11 frame capture timed out")
        if proc is not None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # Process already exited between timeout and kill
            await proc.wait()
        return None
    except Exception as e:
        logger.warning("X11 frame capture failed: %s", e)
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # Process already exited
            await proc.wait()
        return None


async def drain_x11_event_queue() -> None:
    """Drain queued X11 events to prevent event leak accumulation.

    When screencast sessions are rapidly cycled (teardown → reconnect), X11
    events queue up with no consumer between sessions.  Running ``xdpyinfo``
    forces a round-trip ``XSync`` that flushes the event queue, preventing the
    ``event leak: N queued`` warnings from x11vnc and reducing memory pressure.
    """
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdpyinfo", "-display", _DISPLAY,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=_XDOTOOL_SYNC_TIMEOUT)
        logger.debug("X11 event queue drained via xdpyinfo sync")
    except asyncio.TimeoutError:
        logger.debug("X11 event drain timed out — skipping")
        if proc is not None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # Process already exited between timeout and kill
            await proc.wait()
    except Exception as e:
        logger.debug("X11 event drain failed (non-critical): %s", e)


def is_x11_available() -> bool:
    """Check if X11 capture is available (xwd binary + Pillow)."""
    if not shutil.which("xwd"):
        return False
    try:
        from PIL import Image  # noqa: F401

        return True
    except ImportError:
        return False


_X11_CONSECUTIVE_FAILURE_LIMIT = 10  # Fall back to CDP after this many failures


async def stream_x11_frames(
    quality: int = 70,
    max_fps: int = 15,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[X11ScreencastFrame, None]:
    """Stream frames from the X11 display as an async generator.

    Captures the full Xvfb display including Chrome's browser chrome
    (tabs, address bar, window decorations).

    If X11 capture fails consecutively (_X11_CONSECUTIVE_FAILURE_LIMIT times),
    the generator exits so the caller can fall back to CDP screencast.

    Args:
        quality: JPEG quality (1-100)
        max_fps: Maximum frames per second
        cancel_event: Optional event to signal stream cancellation
    """
    min_interval = 1.0 / max_fps
    consecutive_failures = 0
    logger.info(
        "X11 screencast started (quality=%d, max_fps=%d)", quality, max_fps
    )

    while True:
        if cancel_event and cancel_event.is_set():
            break

        start = time.monotonic()

        frame = await _capture_x11_frame(quality)
        if frame:
            consecutive_failures = 0
            yield frame
        else:
            consecutive_failures += 1
            if consecutive_failures >= _X11_CONSECUTIVE_FAILURE_LIMIT:
                logger.error(
                    "X11 capture failed %d consecutive times — "
                    "exiting stream for CDP fallback",
                    consecutive_failures,
                )
                break

        # Rate limiting - account for capture time
        elapsed = time.monotonic() - start
        sleep_time = min_interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
