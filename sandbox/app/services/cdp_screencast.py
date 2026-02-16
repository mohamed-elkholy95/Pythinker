"""
CDP Screencast Service - Low-latency browser streaming via Chrome DevTools Protocol.

Provides real-time browser view streaming with 10-50ms latency, significantly
faster than traditional screenshot polling (50-200ms).

Features:
- Direct CDP connection to Chrome with automatic page target discovery
- JPEG frame streaming for low bandwidth
- Configurable quality and frame rate
- Persistent connection with smart auto-reconnect on page navigation/crash
- Cache invalidation on stale page targets (handles browser navigation/crash)
- Health checks to detect stale connections
- Exponential backoff for retry attempts

Architecture:
    Frontend → Backend proxy → Sandbox screencast API → CDP Service → Chrome
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CDP connection settings
# ---------------------------------------------------------------------------
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
CDP_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}"

# Connection management
_WS_URL_CACHE_TTL = 60.0  # Cache the WebSocket URL for 60 seconds
_HEALTH_CHECK_TIMEOUT = 2.0  # Quick health check timeout
_CAPTURE_COMMAND_TIMEOUT = (
    6.0  # P1.2: Increased from 4.0s to allow more time for heavy pages
)
_CONNECT_TIMEOUT = 3.0  # Timeout for WebSocket connection establishment
_PAGE_REDISCOVERY_DELAY = 0.3  # Brief pause for Chrome to register new page target
_MAX_RETRY_ATTEMPTS = 2  # Initial attempt + 1 retry after page re-discovery
_STREAM_FRAME_TIMEOUT = 10.0  # Max seconds to wait for next frame before declaring stream dead
_STREAM_HEALTH_CHECK_INTERVAL = 30.0  # Periodic health check during streaming


@dataclass
class ScreencastConfig:
    """Configuration for CDP screencast streaming."""

    format: str = "jpeg"  # jpeg is faster than png
    quality: int = 80  # 80% is good balance of quality/bandwidth
    max_width: int = 1280
    max_height: int = 1024
    every_nth_frame: int = 1  # Capture every frame


@dataclass
class ScreencastFrame:
    """A single screencast frame from CDP."""

    data: bytes  # Raw image bytes (decoded from base64)
    session_id: int
    timestamp: float
    metadata: dict


class CDPScreencastService:
    """
    Service for streaming browser content via Chrome DevTools Protocol.

    Uses Page.startScreencast for low-latency frame streaming directly
    from Chrome's rendering pipeline.

    Key resilience features:
    - Automatic page target re-discovery when CDP pages become detached
      (e.g., after browser navigation, tab close, or page crash)
    - Cache invalidation ensures stale WebSocket URLs are never reused
    - Retry-once pattern: on detached errors, invalidate + re-discover + retry
    - Persistent connections with auto-reconnect for low-latency repeated captures

    Error Recovery Flow:
        CDP command → "Not attached to active page" error
            → invalidate_cache() (clears stale WS URL)
            → _cleanup_stale_connection() (closes dead WS)
            → sleep(0.3s) (let Chrome register new target)
            → get_ws_debugger_url() (fresh /json lookup)
            → connect to new page target
            → retry command (succeeds)
    """

    # CDP error messages that indicate the page target is stale/detached.
    # When any of these appear in an error response, we invalidate the cached
    # WebSocket URL and re-discover the active page target.
    _PAGE_DETACHED_INDICATORS = frozenset({
        "Not attached to an active page",
        "Internal error",
        "Target closed",
        "Session with given id not found",
    })

    def __init__(self, config: ScreencastConfig | None = None):
        self.config = config or ScreencastConfig()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._streaming = False
        self._frame_callback: Callable[[ScreencastFrame], None] | None = None
        self._msg_counter: int = 0

        # Serialize all CDP command send/receive cycles on the shared WebSocket
        # to prevent "Concurrent call to receive() is not allowed" errors.
        self._command_lock: asyncio.Lock = asyncio.Lock()

        # Connection caching
        self._cached_ws_url: str | None = None
        self._ws_url_cached_at: float = 0.0
        self._last_successful_capture: float = 0.0

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket connection is alive."""
        return (
            self._ws is not None
            and not self._ws.closed
            and self._session is not None
            and not self._session.closed
        )

    # ------------------------------------------------------------------
    # Page target discovery & cache management
    # ------------------------------------------------------------------

    def _is_page_detached_error(self, result: dict) -> bool:
        """Check if a CDP error response indicates the page target is stale/detached.

        These errors occur when Chrome navigates to a new page, the tab is closed,
        or the renderer process crashes. The old page UUID becomes invalid but may
        still be returned by /json briefly.
        """
        error = result.get("error", {})
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        return any(indicator in message for indicator in self._PAGE_DETACHED_INDICATORS)

    def invalidate_cache(self) -> None:
        """Invalidate the cached WebSocket URL to force fresh page discovery.

        Call this when CDP commands fail with page-detached errors so the next
        connection attempt discovers the current active page target via /json.
        """
        if self._cached_ws_url:
            logger.info(
                f"Invalidating cached CDP URL (was: ...{self._cached_ws_url[-20:]})"
            )
        self._cached_ws_url = None
        self._ws_url_cached_at = 0.0

    async def _get_cached_ws_url(self) -> str | None:
        """Get WebSocket URL with caching to avoid repeated /json lookups."""
        now = time.monotonic()
        if self._cached_ws_url and (now - self._ws_url_cached_at) < _WS_URL_CACHE_TTL:
            return self._cached_ws_url

        url = await self.get_ws_debugger_url()
        if url:
            self._cached_ws_url = url
            self._ws_url_cached_at = now
        return url

    async def get_ws_debugger_url(self) -> str | None:
        """Get the WebSocket debugger URL for the active browser page.

        Queries Chrome's /json introspection endpoint to discover page targets.
        Filters for type="page" targets, preferring non-blank pages when multiple
        targets exist (e.g., after a crash creates a new blank tab).
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json",
                    timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        targets = await resp.json()
                        if not targets:
                            return None

                        # Collect all page-type targets
                        pages = [t for t in targets if t.get("type") == "page"]
                        if not pages:
                            # Fallback: use first target regardless of type
                            return targets[0].get("webSocketDebuggerUrl")

                        # Prefer non-blank pages (after crash, Chrome may have
                        # both a crashed target and a new blank tab)
                        for page in pages:
                            url = page.get("url", "")
                            if url and url not in ("about:blank", "chrome://newtab/"):
                                return page.get("webSocketDebuggerUrl")

                        # All pages are blank - return the first one
                        return pages[0].get("webSocketDebuggerUrl")
        except Exception as e:
            logger.debug(f"Failed to get CDP WebSocket URL: {e}")
        return None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def ensure_connected(self) -> bool:
        """Ensure connection is alive, reconnecting if needed.

        This is the primary entry point for persistent connection usage.
        Avoids full connect/disconnect overhead on every call.
        Serialized via _command_lock to prevent multiple callers from
        racing to reconnect (which causes unclosed client sessions).
        """
        if self.is_connected:
            return True

        async with self._command_lock:
            # Double-check after acquiring lock
            if self.is_connected:
                return True
            # Connection is dead or doesn't exist, try to reconnect
            await self._cleanup_stale_connection()
            return await self._connect_unlocked()

    async def _connect_unlocked(self) -> bool:
        """Connect to Chrome via CDP WebSocket (caller must hold _command_lock)."""
        ws_url = await self._get_cached_ws_url()
        if not ws_url:
            logger.debug("No CDP WebSocket URL available")
            return False

        try:
            self._session = aiohttp.ClientSession()
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(ws_url),
                timeout=_CONNECT_TIMEOUT,
            )
            logger.info(f"Connected to CDP at {ws_url}")
            return True
        except asyncio.TimeoutError:
            logger.warning("CDP WebSocket connection timed out")
            await self._cleanup_stale_connection()
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to CDP: {e}")
            await self._cleanup_stale_connection()
            return False

    async def _cleanup_stale_connection(self) -> None:
        """Clean up any stale connection state without logging disconnect."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    async def _handle_page_detached(self, context: str) -> None:
        """Common handler for page-detached errors.

        Cleans up the stale connection and invalidates the URL cache so the
        next connection attempt discovers the current active page target.

        Args:
            context: Description of where the error occurred (for logging)
        """
        async with self._command_lock:
            await self._cleanup_stale_connection()
        self.invalidate_cache()
        logger.info(
            f"Page detached during {context} - invalidated cache, "
            f"will retry with fresh page discovery"
        )
        # Brief delay for Chrome to register the new page target
        await asyncio.sleep(_PAGE_REDISCOVERY_DELAY)

    async def connect(self) -> bool:
        """Connect to Chrome via CDP WebSocket."""
        async with self._command_lock:
            return await self._connect_unlocked()

    async def disconnect(self):
        """Disconnect from CDP."""
        self._running = False
        await self._cleanup_stale_connection()
        logger.debug("Disconnected from CDP")

    async def health_check(self) -> bool:
        """Quick health check - verify Chrome is responsive via the /json endpoint.

        This is cheaper than a full WebSocket roundtrip and detects
        Chrome crashes or restarts without disturbing the WS connection.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json/version",
                    timeout=aiohttp.ClientTimeout(total=_HEALTH_CHECK_TIMEOUT),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # CDP command transport
    # ------------------------------------------------------------------

    async def _send_command(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = _CAPTURE_COMMAND_TIMEOUT,
    ) -> dict | None:
        """Send a CDP command and wait for response with timeout.

        Serialized via _command_lock to prevent concurrent receive() calls
        on the shared WebSocket (aiohttp forbids this).
        """
        if not self._ws or self._ws.closed:
            return None

        async with self._command_lock:
            # Re-check after acquiring lock (connection may have been cleaned up)
            if not self._ws or self._ws.closed:
                return None

            self._msg_counter += 1
            msg_id = self._msg_counter

            message = {"id": msg_id, "method": method}
            if params:
                message["params"] = params

            try:
                await self._ws.send_json(message)
                logger.debug(f"Sent CDP command: {method} (id={msg_id})")

                # Wait for response with timeout
                start_time = asyncio.get_event_loop().time()
                while True:
                    remaining = timeout - (asyncio.get_event_loop().time() - start_time)
                    if remaining <= 0:
                        logger.warning(f"CDP command timed out: {method}")
                        return None

                    try:
                        msg = await asyncio.wait_for(
                            self._ws.receive(), timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"CDP command timed out waiting for response: {method}"
                        )
                        return None

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        # Check if this is our response
                        if data.get("id") == msg_id:
                            logger.debug(f"Got CDP response for {method}")
                            return data
                        # Otherwise it might be an event, continue waiting
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.warning(f"CDP WebSocket error: {msg.data}")
                        return None
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        logger.warning("CDP WebSocket closed unexpectedly")
                        return None

            except RuntimeError as e:
                # Transport can close during rapid restarts/teardown.
                if "closing transport" in str(e).lower():
                    logger.debug(f"CDP command skipped on closing transport: {method}")
                else:
                    logger.warning(f"CDP command error: {e}")
            except Exception as e:
                logger.warning(f"CDP command error: {e}")
            return None

    # ------------------------------------------------------------------
    # Screencast streaming
    # ------------------------------------------------------------------

    async def start_screencast(self) -> bool:
        """Start the screencast stream.

        On page-detached errors, invalidates the cache and retries once
        with fresh page discovery so the screencast recovers from navigation/crashes.
        """
        params = {
            "format": self.config.format,
            "quality": self.config.quality,
            "maxWidth": self.config.max_width,
            "maxHeight": self.config.max_height,
            "everyNthFrame": self.config.every_nth_frame,
        }

        for attempt in range(_MAX_RETRY_ATTEMPTS):
            if not self._ws:
                if not await self.connect():
                    if attempt == 0:
                        self.invalidate_cache()
                        continue
                    return False

            result = await self._send_command("Page.startScreencast", params)
            if result and "error" not in result:
                self._running = True
                logger.info(f"CDP screencast started with config: {self.config}")
                return True

            # Check for page-detached error and retry
            if result and self._is_page_detached_error(result) and attempt == 0:
                logger.warning(
                    f"Screencast start failed (page detached): {result.get('error')}"
                )
                await self._handle_page_detached("start_screencast")
                continue

            logger.error(f"Failed to start screencast: {result}")
            return False

        return False

    async def stop_screencast(self):
        """Stop the screencast stream."""
        self._running = False
        # Do not send a CDP command while the stream reader is active; that causes
        # concurrent receive() calls on the same websocket connection.
        if self._ws and not self._streaming and not self._ws.closed:
            await self._send_command("Page.stopScreencast")
        logger.info("CDP screencast stopped")

    async def ack_frame(self, session_id: int):
        """Acknowledge receipt of a frame to continue receiving frames."""
        if self._ws:
            await self._ws.send_json(
                {
                    "id": id(session_id),
                    "method": "Page.screencastFrameAck",
                    "params": {"sessionId": session_id},
                }
            )

    async def stream_frames(
        self,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[ScreencastFrame, None]:
        """
        Stream screencast frames as an async generator.

        Yields ScreencastFrame objects with decoded image data.
        Automatically acknowledges frames to keep the stream flowing.

        Args:
            cancel_event: Optional event that, when set, causes the stream to
                exit promptly. Used to propagate client disconnects so the
                stream doesn't linger for the full frame timeout cycle.

        Frame Timeout Watchdog:
            If no frame is received within _STREAM_FRAME_TIMEOUT seconds and
            Chrome's health check fails, the stream exits to trigger recovery.
            When the health check passes (page is simply static), the timeout
            counter resets and the stream continues waiting.

        Health Check:
            Every _STREAM_HEALTH_CHECK_INTERVAL seconds, a lightweight /json
            health check verifies Chrome is still responsive. If Chrome is dead,
            the stream exits early rather than waiting for the full frame timeout.
        """
        if not self._running:
            if not await self.start_screencast():
                return

        self._streaming = True
        last_health_check = time.monotonic()
        consecutive_timeouts = 0
        _MAX_CONSECUTIVE_TIMEOUTS = 2  # Exit after 2 consecutive failed health checks

        try:
            while self._running:
                # Check cancel signal at the top of each iteration
                if cancel_event and cancel_event.is_set():
                    logger.info("Stream cancelled by caller (client disconnect)")
                    break
                try:
                    # Wait for next message with timeout — prevents indefinite hang
                    # when Chrome stops producing frames
                    msg = await asyncio.wait_for(
                        self._ws.receive(), timeout=_STREAM_FRAME_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    # Check cancel before doing any timeout processing
                    if cancel_event and cancel_event.is_set():
                        logger.info("Stream cancelled during timeout wait")
                        break

                    consecutive_timeouts += 1
                    logger.warning(
                        f"No CDP frame received in {_STREAM_FRAME_TIMEOUT}s "
                        f"(timeout {consecutive_timeouts}/{_MAX_CONSECUTIVE_TIMEOUTS})"
                    )

                    if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                        logger.error(
                            "CDP stream appears dead — Chrome renderer may be hung. "
                            "Breaking stream to trigger recovery."
                        )
                        break

                    # Verify Chrome is still alive before escalating
                    if not await self.health_check():
                        logger.error(
                            "Chrome health check failed during stream timeout. "
                            "Breaking stream to trigger recovery."
                        )
                        break

                    # Chrome is alive — page is likely static (no visual changes
                    # means no compositor updates, so no screencast frames).
                    # Reset the counter: a passing health check is proof of life,
                    # so we should not escalate toward killing the stream.
                    consecutive_timeouts = 0
                    logger.info(
                        "Chrome health check passed — page likely static, "
                        "resetting timeout counter"
                    )
                    continue

                # Reset timeout counter on any received message
                consecutive_timeouts = 0

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()

                    # Check for screencast frame event
                    if data.get("method") == "Page.screencastFrame":
                        params = data.get("params", {})
                        session_id = params.get("sessionId")
                        frame_data = params.get("data")
                        metadata = params.get("metadata", {})

                        if frame_data and session_id is not None:
                            # Decode base64 image data
                            image_bytes = base64.b64decode(frame_data)

                            frame = ScreencastFrame(
                                data=image_bytes,
                                session_id=session_id,
                                timestamp=metadata.get("timestamp", 0),
                                metadata=metadata,
                            )

                            # Acknowledge immediately to receive next frame ASAP
                            await self.ack_frame(session_id)

                            yield frame

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"CDP WebSocket error during stream: {msg.data}")
                    break

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    logger.info("CDP WebSocket closed during stream")
                    break

                # Periodic health check (lightweight, doesn't block frame flow)
                now = time.monotonic()
                if now - last_health_check >= _STREAM_HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    if not await self.health_check():
                        logger.warning(
                            "Chrome health check failed during active stream. "
                            "Breaking stream to trigger recovery."
                        )
                        break

        except asyncio.CancelledError:
            logger.info("Screencast stream cancelled")
        except Exception as e:
            logger.error(f"Screencast stream error: {e}")
        finally:
            self._streaming = False

    # ------------------------------------------------------------------
    # Single-frame capture
    # ------------------------------------------------------------------

    async def capture_single_frame(
        self, quality: int | None = None, image_format: str | None = None
    ) -> bytes | None:
        """
        Capture a single frame from the browser.

        Uses persistent connection via ensure_connected() for low overhead.
        On page-detached errors, invalidates the cached URL and retries once
        with fresh page discovery so navigation/crashes recover automatically.

        Args:
            quality: Override quality setting for this capture (default: use config)
            image_format: Override format for this capture (default: use config)

        P1.2: Enhanced with timeout detection and automatic reconnect.
        P2.8: Added per-request config parameters to fix singleton race condition.
        """
        capture_quality = quality if quality is not None else self.config.quality
        capture_format = image_format if image_format is not None else self.config.format

        # Try up to 2 times: initial attempt + 1 retry after page re-discovery
        for attempt in range(_MAX_RETRY_ATTEMPTS):
            if not await self.ensure_connected():
                if attempt == 0:
                    self.invalidate_cache()
                    continue
                return None

            try:
                result = await self._send_command(
                    "Page.captureScreenshot",
                    {"format": capture_format, "quality": capture_quality},
                )

                # Detect timeout (result is None) and force reconnect
                if result is None:
                    logger.warning("CDP capture timed out, forcing reconnect")
                    await self._handle_page_detached("capture_screenshot_timeout")
                    if attempt == 0:
                        continue
                    return None

                if "result" in result:
                    data = result["result"].get("data")
                    if data:
                        self._last_successful_capture = time.monotonic()
                        return base64.b64decode(data)

                # Command returned error - check if page is detached
                if "error" in result:
                    logger.warning(f"CDP capture error response: {result['error']}")

                    if self._is_page_detached_error(result) and attempt == 0:
                        await self._handle_page_detached("capture_screenshot")
                        continue

                    # Non-retryable error
                    async with self._command_lock:
                        await self._cleanup_stale_connection()

            except Exception as e:
                logger.warning(f"Failed to capture single frame: {e}")
                if attempt == 0:
                    await self._handle_page_detached("capture_screenshot_exception")
                    continue
                async with self._command_lock:
                    await self._cleanup_stale_connection()

        return None


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_service_instance: CDPScreencastService | None = None
_service_lock = asyncio.Lock()


async def get_or_create_screencast_service(
    config: ScreencastConfig | None = None,
) -> CDPScreencastService:
    """Get or create the singleton CDP screencast service (async-safe)."""
    global _service_instance
    if _service_instance is None:
        async with _service_lock:
            # Double-check after acquiring lock
            if _service_instance is None:
                _service_instance = CDPScreencastService(config)
    return _service_instance


def get_screencast_service(
    config: ScreencastConfig | None = None,
) -> CDPScreencastService:
    """Get or create the singleton CDP screencast service (sync version)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CDPScreencastService(config)
    return _service_instance
