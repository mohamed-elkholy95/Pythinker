"""
CDP Screencast Service - Low-latency browser streaming via Chrome DevTools Protocol.

This service provides real-time browser view streaming with 10-50ms latency,
significantly faster than VNC-based approaches (50-200ms).

Features:
- Direct CDP connection to Chrome
- JPEG frame streaming for low bandwidth
- Configurable quality and frame rate
- WebSocket-based delivery for real-time updates
- Persistent connection with auto-reconnect
- Health checks to detect stale connections
"""

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable

import aiohttp

logger = logging.getLogger(__name__)

# CDP connection settings
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
CDP_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}"

# Connection management
_WS_URL_CACHE_TTL = 60.0  # Cache the WebSocket URL for 60 seconds
_HEALTH_CHECK_TIMEOUT = 2.0  # Quick health check timeout
_CAPTURE_COMMAND_TIMEOUT = 6.0  # P1.2: Increased from 4.0s to allow more time for heavy pages
_CONNECT_TIMEOUT = 3.0  # Timeout for WebSocket connection establishment


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

    Supports persistent connections with auto-reconnect for low-latency
    repeated captures (e.g., periodic screenshot service).
    """

    def __init__(self, config: ScreencastConfig | None = None):
        self.config = config or ScreencastConfig()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._streaming = False
        self._frame_callback: Callable[[ScreencastFrame], None] | None = None
        self._msg_counter: int = 0

        # Connection caching
        self._cached_ws_url: str | None = None
        self._ws_url_cached_at: float = 0.0
        self._last_successful_capture: float = 0.0

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket connection is alive."""
        return (
            self._ws is not None
            and not self._ws.closed
            and self._session is not None
            and not self._session.closed
        )

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
        """Get the WebSocket debugger URL for the first browser page."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CDP_ENDPOINT}/json",
                    timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        pages = await resp.json()
                        if pages:
                            # Find first page (not extension or devtools)
                            for page in pages:
                                if page.get("type") == "page":
                                    return page.get("webSocketDebuggerUrl")
                            # Fallback to first item
                            return pages[0].get("webSocketDebuggerUrl")
        except Exception as e:
            logger.debug(f"Failed to get CDP WebSocket URL: {e}")
        return None

    async def ensure_connected(self) -> bool:
        """Ensure connection is alive, reconnecting if needed.

        This is the primary entry point for persistent connection usage.
        Avoids full connect/disconnect overhead on every call.
        """
        if self.is_connected:
            return True

        # Connection is dead or doesn't exist, try to reconnect
        await self._cleanup_stale_connection()
        return await self.connect()

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

    async def connect(self) -> bool:
        """Connect to Chrome via CDP WebSocket."""
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

    async def _send_command(
        self, method: str, params: dict | None = None, timeout: float = _CAPTURE_COMMAND_TIMEOUT
    ) -> dict | None:
        """Send a CDP command and wait for response with timeout."""
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
                    msg = await asyncio.wait_for(self._ws.receive(), timeout=remaining)
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
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
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

    async def start_screencast(self) -> bool:
        """Start the screencast stream."""
        if not self._ws:
            if not await self.connect():
                return False

        params = {
            "format": self.config.format,
            "quality": self.config.quality,
            "maxWidth": self.config.max_width,
            "maxHeight": self.config.max_height,
            "everyNthFrame": self.config.every_nth_frame,
        }

        result = await self._send_command("Page.startScreencast", params)
        if result and "error" not in result:
            self._running = True
            logger.info(f"CDP screencast started with config: {self.config}")
            return True

        logger.error(f"Failed to start screencast: {result}")
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

    async def stream_frames(self) -> AsyncGenerator[ScreencastFrame, None]:
        """
        Stream screencast frames as an async generator.

        Yields ScreencastFrame objects with decoded image data.
        Automatically acknowledges frames to keep the stream flowing.
        """
        if not self._running:
            if not await self.start_screencast():
                return

        self._streaming = True
        try:
            async for msg in self._ws:
                if not self._running:
                    break

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

        except asyncio.CancelledError:
            logger.info("Screencast stream cancelled")
        except Exception as e:
            logger.error(f"Screencast stream error: {e}")
        finally:
            self._streaming = False

    async def capture_single_frame(self) -> bytes | None:
        """
        Capture a single frame from the browser.

        Uses persistent connection via ensure_connected() for low overhead.
        Useful for one-off screenshots with lower latency than xwd approach.

        P1.2: Enhanced with timeout detection and automatic reconnect.
        """
        if not await self.ensure_connected():
            return None

        try:
            result = await self._send_command(
                "Page.captureScreenshot",
                {"format": self.config.format, "quality": self.config.quality},
            )

            # P1.2: Detect timeout (result is None) and force reconnect
            if result is None:
                logger.warning("CDP capture timed out, forcing reconnect")
                await self._cleanup_stale_connection()
                return None

            if "result" in result:
                data = result["result"].get("data")
                if data:
                    self._last_successful_capture = time.monotonic()
                    return base64.b64decode(data)

            # Command succeeded but no data - connection may be stale
            if "error" in result:
                logger.warning(f"CDP capture error response: {result['error']}")
                # Force reconnect on next attempt
                await self._cleanup_stale_connection()

        except Exception as e:
            logger.warning(f"Failed to capture single frame: {e}")
            # Force reconnect on next attempt
            await self._cleanup_stale_connection()

        return None


# Singleton instance for reuse across requests
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
