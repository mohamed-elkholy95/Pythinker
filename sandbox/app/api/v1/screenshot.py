"""Screenshot API endpoints for desktop capture via CDP-first fallback tiers.

Implements a multi-tier screenshot capture system with in-memory caching
to ensure maximum reliability and eliminate 503 errors:

Tier 1: CDP (persistent connection, ~20ms) - Chrome DevTools Protocol
Tier 2: xwd + Pillow (no ImageMagick, ~100ms) - X11 screenshot with Python image processing
Tier 3: xwd + ImageMagick (~100ms) - X11 screenshot with convert binary
Tier 4: Stale cache (0ms) - Return last successful screenshot with stale indicator
"""

from __future__ import annotations

import asyncio
import io
import logging
import shlex
import shutil
import struct
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from PIL import Image

from fastapi import APIRouter, HTTPException, Query, Response

from app.services.cdp_screencast import (
    CDPScreencastService,
    ScreencastConfig,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_SCREENSHOT_TIMEOUT_SECONDS = 5.0
_DISPLAY_NAME = ":1"
_CACHE_TTL_SECONDS = 30.0  # Return stale cache up to 30s old
_CACHE_MAX_ENTRIES = 3  # Keep last few frames (different quality/scale combos)


# ---------------------------------------------------------------------------
# In-memory screenshot cache
# ---------------------------------------------------------------------------


@dataclass
class _CachedScreenshot:
    """A cached screenshot with metadata."""

    image_data: bytes
    captured_at: float  # time.monotonic()
    backend: str
    quality: int
    scale: float
    image_format: str

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.captured_at

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds < _CACHE_TTL_SECONDS


@dataclass
class _ScreenshotCache:
    """Thread-safe in-memory cache for recent screenshots.

    Keeps the last few successful captures so that when all backends fail,
    we can return a stale-but-usable frame instead of a 503 error.
    """

    _entries: list[_CachedScreenshot] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Stats
    hits: int = 0
    misses: int = 0

    async def put(
        self,
        image_data: bytes,
        backend: str,
        quality: int,
        scale: float,
        image_format: str,
    ) -> None:
        """Cache a successful screenshot."""
        async with self._lock:
            entry = _CachedScreenshot(
                image_data=image_data,
                captured_at=time.monotonic(),
                backend=backend,
                quality=quality,
                scale=scale,
                image_format=image_format,
            )
            self._entries.append(entry)
            # Keep only the most recent entries
            if len(self._entries) > _CACHE_MAX_ENTRIES:
                self._entries = self._entries[-_CACHE_MAX_ENTRIES:]

    async def get(self, image_format: str = "jpeg") -> _CachedScreenshot | None:
        """Get the most recent cached screenshot that matches the format.

        Returns None if cache is empty or all entries are expired.
        """
        async with self._lock:
            # Search backwards (most recent first)
            for entry in reversed(self._entries):
                if entry.is_fresh and entry.image_format == image_format:
                    self.hits += 1
                    return entry
            # Fallback: return any fresh entry regardless of format
            for entry in reversed(self._entries):
                if entry.is_fresh:
                    self.hits += 1
                    return entry
            self.misses += 1
            return None

    async def get_any(self) -> _CachedScreenshot | None:
        """Get any cached screenshot, even if expired (last resort)."""
        async with self._lock:
            if self._entries:
                return self._entries[-1]
            return None

    @property
    def size(self) -> int:
        return len(self._entries)


# Module-level singleton cache
_screenshot_cache = _ScreenshotCache()


# ---------------------------------------------------------------------------
# CDP capture (Tier 1) - persistent connection, lowest latency
# ---------------------------------------------------------------------------

# Dedicated CDP service for screenshot capture.
# This is intentionally SEPARATE from the screencast singleton to avoid:
# 1. _command_lock contention between polling screenshots and streaming frames
# 2. _cleanup_stale_connection() in screenshot killing the screencast WebSocket
# 3. Shared connection state causing race conditions on error recovery
_screenshot_cdp_service: CDPScreencastService | None = None

# P1.3: CDP failure tracking to skip tier after consecutive failures
_cdp_consecutive_failures: int = 0
_CDP_FAILURE_THRESHOLD: int = 3  # Skip after 3 consecutive failures
_cdp_skip_until: float = 0.0
_CDP_SKIP_DURATION: float = 5.0  # Skip for 5s after threshold (reduced from 30s)


def _get_cdp_service() -> CDPScreencastService:
    """Get or create dedicated CDP service for screenshot capture.

    IMPORTANT: This returns a SEPARATE instance from the screencast service.
    Screenshot capture (Page.captureScreenshot) and screencast streaming
    (Page.startScreencast/Page.screencastFrame) use different CDP commands
    and have different lifecycle requirements. Sharing a single WebSocket
    connection causes command interleaving and lock contention.

    P2.8 FIX: Quality and format are passed as parameters to
    capture_single_frame() instead of mutating config.
    """
    global _screenshot_cdp_service
    if _screenshot_cdp_service is None:
        _screenshot_cdp_service = CDPScreencastService(
            ScreencastConfig(format="jpeg", quality=70)
        )
    return _screenshot_cdp_service


async def _capture_with_cdp(
    quality: int, image_format: Literal["jpeg", "png"]
) -> bytes | None:
    """Capture via CDP using a persistent WebSocket connection.

    The singleton service maintains the WebSocket across requests,
    eliminating ~150ms of connection overhead per capture.

    P1.3: Tracks consecutive failures and skips CDP tier during cooldown.
    On cooldown expiry, invalidates the CDP URL cache so the next attempt
    discovers the current active page (handles navigation/crash recovery).
    """
    global _cdp_consecutive_failures, _cdp_skip_until

    # P1.3: Skip CDP if in cooldown period
    now = time.monotonic()
    if _cdp_consecutive_failures >= _CDP_FAILURE_THRESHOLD and now < _cdp_skip_until:
        logger.debug(
            f"[Screenshot] Skipping CDP tier (in cooldown, {_cdp_consecutive_failures} failures)"
        )
        return None

    # When cooldown expires, invalidate cache so we re-discover the active page
    service = _get_cdp_service()
    if _cdp_consecutive_failures >= _CDP_FAILURE_THRESHOLD and now >= _cdp_skip_until:
        logger.info(
            "[Screenshot] CDP cooldown expired, invalidating cache for fresh page discovery"
        )
        _cdp_consecutive_failures = 0
        service.invalidate_cache()

    try:
        # P2.8 FIX: Pass quality and format per-request to avoid singleton config race
        image_data = await asyncio.wait_for(
            service.capture_single_frame(quality=quality, image_format=image_format),
            timeout=_SCREENSHOT_TIMEOUT_SECONDS,
        )
        if not image_data:
            logger.debug("[Screenshot] CDP capture returned empty frame")
            # P1.3: Track failure
            _cdp_consecutive_failures += 1
            if _cdp_consecutive_failures >= _CDP_FAILURE_THRESHOLD:
                _cdp_skip_until = now + _CDP_SKIP_DURATION
                logger.warning(
                    f"[Screenshot] CDP failed {_cdp_consecutive_failures}x, "
                    f"skipping for {_CDP_SKIP_DURATION}s"
                )
            return None
        # P1.3: Reset on success
        _cdp_consecutive_failures = 0
        return image_data
    except asyncio.TimeoutError:
        logger.warning(
            "[Screenshot] CDP capture timed out after %.1fs",
            _SCREENSHOT_TIMEOUT_SECONDS,
        )
        # P1.3: Track failure
        _cdp_consecutive_failures += 1
        if _cdp_consecutive_failures >= _CDP_FAILURE_THRESHOLD:
            _cdp_skip_until = now + _CDP_SKIP_DURATION
            logger.warning(
                f"[Screenshot] CDP failed {_cdp_consecutive_failures}x, "
                f"skipping for {_CDP_SKIP_DURATION}s"
            )
        return None
    except Exception as e:
        logger.warning(f"[Screenshot] CDP capture failed: {e}")
        # P1.3: Track failure
        _cdp_consecutive_failures += 1
        if _cdp_consecutive_failures >= _CDP_FAILURE_THRESHOLD:
            _cdp_skip_until = now + _CDP_SKIP_DURATION
            logger.warning(
                f"[Screenshot] CDP failed {_cdp_consecutive_failures}x, "
                f"skipping for {_CDP_SKIP_DURATION}s"
            )
        return None


# ---------------------------------------------------------------------------
# XWD + Pillow capture (Tier 2) - no ImageMagick dependency
# ---------------------------------------------------------------------------


def _parse_xwd(data: bytes) -> "Image.Image | None":
    """Parse XWD (X Window Dump) format into a PIL Image.

    XWD is the native X11 screenshot format produced by the xwd utility.
    This parser handles the common ZPixmap format with 24 or 32 bits per pixel,
    eliminating the need for ImageMagick convert binary.

    XWD format reference: https://www.x.org/releases/current/doc/libXmu/xwd-format.html
    """
    from PIL import Image

    try:
        if len(data) < 100:
            return None

        # XWD header fields (all big-endian uint32)
        header_size = struct.unpack(">I", data[0:4])[0]
        file_version = struct.unpack(">I", data[4:8])[0]

        if file_version != 7:
            logger.warning(f"[XWD] Unsupported file version: {file_version}")
            return None

        pixmap_width = struct.unpack(">I", data[16:20])[0]
        pixmap_height = struct.unpack(">I", data[20:24])[0]
        bits_per_pixel = struct.unpack(">I", data[44:48])[0]
        bytes_per_line = struct.unpack(">I", data[48:52])[0]
        ncolors = struct.unpack(">I", data[76:80])[0]

        # Pixel data starts after header + colormap (each XWDColor is 12 bytes)
        pixel_offset = header_size + ncolors * 12
        pixel_data = data[pixel_offset:]

        expected_size = bytes_per_line * pixmap_height
        if len(pixel_data) < expected_size:
            logger.warning(
                f"[XWD] Pixel data too short: {len(pixel_data)} < {expected_size}"
            )
            return None

        if bits_per_pixel == 32:
            # BGRX format (most common for 32-bit X11 on little-endian systems)
            img = Image.frombytes(
                "RGB",
                (pixmap_width, pixmap_height),
                pixel_data,
                "raw",
                "BGRX",
                bytes_per_line,
            )
            return img
        elif bits_per_pixel == 24:
            img = Image.frombytes(
                "RGB",
                (pixmap_width, pixmap_height),
                pixel_data,
                "raw",
                "BGR",
                bytes_per_line,
            )
            return img
        else:
            logger.warning(f"[XWD] Unsupported bits_per_pixel: {bits_per_pixel}")
            return None
    except Exception as e:
        logger.warning(f"[XWD] Failed to parse XWD data: {e}")
        return None


async def _capture_with_xwd_pillow(
    quality: int,
    scale: float,
    image_format: Literal["jpeg", "png"],
) -> bytes | None:
    """Capture screenshot using xwd + Pillow (no ImageMagick required).

    This fallback only needs the xwd binary (part of x11-utils, always installed)
    and Pillow (always available in the sandbox Python environment).
    """
    if not shutil.which("xwd"):
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            "xwd",
            "-root",
            "-display",
            _DISPLAY_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SCREENSHOT_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("[Screenshot] xwd capture timed out")
            return None

        if proc.returncode != 0 or not stdout:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.warning(f"[Screenshot] xwd failed: {error_msg}")
            return None

        # Parse XWD format with Pillow
        img = _parse_xwd(stdout)
        if img is None:
            return None

        # Scale if needed
        if scale < 1.0:
            from PIL import Image

            new_w = max(1, int(img.width * scale))
            new_h = max(1, int(img.height * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # Encode to desired format
        buf = io.BytesIO()
        if image_format == "jpeg":
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buf, format="PNG", optimize=True)

        return buf.getvalue()

    except ImportError:
        logger.warning("[Screenshot] Pillow not available for xwd fallback")
        return None
    except Exception as e:
        logger.warning(f"[Screenshot] xwd+Pillow capture failed: {e}")
        return None


# ---------------------------------------------------------------------------
# XWD + ImageMagick capture (Tier 3) fallback
# ---------------------------------------------------------------------------


def _xwd_pipeline_available() -> bool:
    """Return True when xwd+convert binaries are available."""
    return shutil.which("xwd") is not None and shutil.which("convert") is not None


async def _capture_with_xwd_pipeline(
    quality: int,
    scale: float,
    image_format: Literal["jpeg", "png"],
) -> bytes | None:
    """Capture screenshot using xwd piped into ImageMagick convert.

    Legacy fallback that requires both xwd and ImageMagick convert binary.
    Only used when ENABLE_SANDBOX_ADDONS=1 installs ImageMagick.
    """
    scale_percent = int(scale * 100)
    convert_parts = ["convert", "xwd:-", "-scale", f"{scale_percent}%"]
    if image_format == "jpeg":
        convert_parts.extend(["-quality", str(quality), "jpg:-"])
    else:
        convert_parts.append("png:-")

    convert_cmd = " ".join(shlex.quote(part) for part in convert_parts)
    shell_cmd = f"DISPLAY={_DISPLAY_NAME} xwd -root | {convert_cmd}"

    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        shell_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_SCREENSHOT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("[Screenshot] xwd+convert pipeline timed out")
        return None

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        logger.warning(f"[Screenshot] xwd pipeline failed: {error_msg}")
        return None

    return stdout if stdout else None


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _build_screenshot_response(
    image_data: bytes,
    *,
    quality: int,
    scale: float,
    image_format: Literal["jpeg", "png"],
    backend: str,
    elapsed_seconds: float,
    is_stale: bool = False,
    stale_age_seconds: float = 0.0,
) -> Response:
    """Build the screenshot HTTP response with common metadata headers."""
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Screenshot-Backend": backend,
        "X-Screenshot-Size": str(len(image_data)),
        "X-Screenshot-Scale": str(scale),
        "X-Screenshot-Quality": str(quality) if image_format == "jpeg" else "N/A",
        "X-Screenshot-Timestamp": str(int(time.time() * 1000)),
        "X-Screenshot-Elapsed-Ms": str(int(elapsed_seconds * 1000)),
    }
    if is_stale:
        headers["X-Screenshot-Stale"] = "true"
        headers["X-Screenshot-Stale-Age-Ms"] = str(int(stale_age_seconds * 1000))

    return Response(
        content=image_data,
        media_type=f"image/{image_format}",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Main screenshot endpoint
# ---------------------------------------------------------------------------


@router.get("")
async def capture_screenshot(
    quality: int = Query(default=75, ge=1, le=100, description="JPEG quality (1-100)"),
    scale: float = Query(
        default=0.5, ge=0.1, le=1.0, description="Scale factor (0.1-1.0)"
    ),
    format: Literal["jpeg", "png"] = Query(default="jpeg", description="Image format"),
    _t: int = Query(default=0, description="Cache-busting timestamp"),
) -> Response:
    """
    Capture desktop screenshot with multi-tier fallback.

    Backend selection order (automatic failover):
    1. CDP - persistent connection, lowest latency (~20ms)
    2. xwd + Pillow - no external deps beyond xwd binary (~100ms)
    3. xwd + ImageMagick convert pipeline (~100ms)
    4. Stale cache - return last successful capture with stale indicator

    Never returns 503 if any screenshot has been captured recently.
    """
    start_time = time.time()

    # --- Tier 1: CDP (persistent connection) ---
    try:
        cdp_image = await _capture_with_cdp(quality, format)
        if cdp_image:
            elapsed = time.time() - start_time
            logger.info(
                f"[Screenshot] Captured {len(cdp_image)} bytes via CDP in {elapsed:.3f}s"
            )
            # Cache for fallback
            await _screenshot_cache.put(cdp_image, "cdp", quality, scale, format)
            return _build_screenshot_response(
                cdp_image,
                quality=quality,
                scale=scale,
                image_format=format,
                backend="cdp",
                elapsed_seconds=elapsed,
            )
    except Exception as e:
        logger.debug(f"[Screenshot] CDP tier failed: {e}")

    # --- Tier 2: xwd + Pillow (no ImageMagick needed) ---
    try:
        pillow_image = await _capture_with_xwd_pillow(quality, scale, format)
        if pillow_image:
            elapsed = time.time() - start_time
            logger.info(
                f"[Screenshot] Captured {len(pillow_image)} bytes via xwd+Pillow in {elapsed:.3f}s"
            )
            await _screenshot_cache.put(
                pillow_image, "xwd_pillow", quality, scale, format
            )
            return _build_screenshot_response(
                pillow_image,
                quality=quality,
                scale=scale,
                image_format=format,
                backend="xwd_pillow",
                elapsed_seconds=elapsed,
            )
    except Exception as e:
        logger.debug(f"[Screenshot] xwd+Pillow tier failed: {e}")

    # --- Tier 3: xwd + ImageMagick ---
    if _xwd_pipeline_available():
        try:
            xwd_image = await _capture_with_xwd_pipeline(quality, scale, format)
            if xwd_image:
                elapsed = time.time() - start_time
                logger.info(
                    f"[Screenshot] Captured {len(xwd_image)} bytes via xwd+convert in {elapsed:.3f}s"
                )
                await _screenshot_cache.put(xwd_image, "xwd", quality, scale, format)
                return _build_screenshot_response(
                    xwd_image,
                    quality=quality,
                    scale=scale,
                    image_format=format,
                    backend="xwd",
                    elapsed_seconds=elapsed,
                )
        except Exception as e:
            logger.debug(f"[Screenshot] xwd+convert tier failed: {e}")

    # --- Tier 4: Return stale cached screenshot ---
    cached = await _screenshot_cache.get(format)
    if cached:
        elapsed = time.time() - start_time
        logger.info(
            f"[Screenshot] Returning cached screenshot ({cached.age_seconds:.1f}s old, "
            f"backend={cached.backend})"
        )
        return _build_screenshot_response(
            cached.image_data,
            quality=cached.quality,
            scale=cached.scale,
            image_format=cached.image_format,
            backend=f"cache:{cached.backend}",
            elapsed_seconds=elapsed,
            is_stale=True,
            stale_age_seconds=cached.age_seconds,
        )

    # Last resort: try any cached entry even if expired
    any_cached = await _screenshot_cache.get_any()
    if any_cached:
        elapsed = time.time() - start_time
        logger.warning(
            f"[Screenshot] Returning expired cached screenshot ({any_cached.age_seconds:.1f}s old)"
        )
        return _build_screenshot_response(
            any_cached.image_data,
            quality=any_cached.quality,
            scale=any_cached.scale,
            image_format=any_cached.image_format,
            backend=f"cache_expired:{any_cached.backend}",
            elapsed_seconds=elapsed,
            is_stale=True,
            stale_age_seconds=any_cached.age_seconds,
        )

    # Truly no screenshot available (first-ever request and all backends failed)
    raise HTTPException(
        status_code=503,
        detail=(
            "Screenshot capture unavailable: all backends failed and no cached frame available. "
            "This typically resolves after the first successful capture."
        ),
    )


# ---------------------------------------------------------------------------
# Diagnostic endpoint
# ---------------------------------------------------------------------------


@router.get("/test")
async def test_screenshot_availability():
    """
    Report screenshot backend availability and cache status.

    Tests all four tiers and reports which backends are operational.
    """
    try:
        # Check CDP availability (uses screenshot's dedicated service)
        cdp_service = _get_cdp_service()
        cdp_ws_url = await cdp_service.get_ws_debugger_url()
        cdp_available = cdp_ws_url is not None
        cdp_connected = cdp_service.is_connected

        # Check xwd availability (Tier 2)
        xwd_available = shutil.which("xwd") is not None

        # Check Pillow availability (Tier 2)
        pillow_available = False
        try:
            from PIL import Image  # noqa: F401

            pillow_available = True
        except ImportError:
            pass

        # Check ImageMagick (Tier 3)
        convert_available = shutil.which("convert") is not None

        # Check X11 display
        display_check = await asyncio.create_subprocess_exec(
            "sh",
            "-c",
            f"DISPLAY={_DISPLAY_NAME} xdpyinfo > /dev/null 2>&1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await display_check.communicate()
        display_available = display_check.returncode == 0

        # Cache status
        cache_entry = await _screenshot_cache.get_any()
        cache_info = {
            "entries": _screenshot_cache.size,
            "hits": _screenshot_cache.hits,
            "misses": _screenshot_cache.misses,
            "latest_age_seconds": round(cache_entry.age_seconds, 1)
            if cache_entry
            else None,
            "latest_backend": cache_entry.backend if cache_entry else None,
        }

        # Determine availability per tier
        tier1_ready = cdp_available
        tier2_ready = xwd_available and pillow_available and display_available
        tier3_ready = xwd_available and convert_available and display_available
        tier4_ready = cache_entry is not None

        available = tier1_ready or tier2_ready or tier3_ready or tier4_ready
        preferred = (
            "cdp"
            if tier1_ready
            else "xwd_pillow"
            if tier2_ready
            else "xwd"
            if tier3_ready
            else "cache"
            if tier4_ready
            else "none"
        )

        return {
            "available": available,
            "preferred_backend": preferred,
            "tiers": {
                "tier1_cdp": {
                    "ready": tier1_ready,
                    "ws_url_available": cdp_available,
                    "persistent_connection": cdp_connected,
                },
                "tier2_xwd_pillow": {
                    "ready": tier2_ready,
                    "xwd": xwd_available,
                    "pillow": pillow_available,
                    "display": display_available,
                },
                "tier3_xwd_convert": {
                    "ready": tier3_ready,
                    "xwd": xwd_available,
                    "convert": convert_available,
                    "display": display_available,
                },
                "tier4_cache": {
                    "ready": tier4_ready,
                    **cache_info,
                },
            },
            # Backward-compatible fields
            "backends": {
                "cdp": cdp_available,
                "xwd_pipeline": tier3_ready,
                "xwd_pillow": tier2_ready,
            },
            "tools": {
                "xwd": xwd_available,
                "convert": convert_available,
                "pillow": pillow_available,
                "display_1": display_available,
            },
            "cache": cache_info,
            "message": "Screenshot system ready"
            if available
            else "No screenshot backend available",
        }

    except Exception as e:
        logger.error(f"Error testing screenshot availability: {e}", exc_info=True)
        return {"available": False, "error": str(e)}
