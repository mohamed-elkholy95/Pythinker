"""
CDP Input Service - Real-time input forwarding via Chrome DevTools Protocol.

Translates mouse, keyboard, and scroll events into CDP Input.dispatch* commands
for interactive browser control.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

import aiohttp

logger = logging.getLogger(__name__)


class MouseButton(StrEnum):
    """CDP mouse button types."""

    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"
    BACK = "back"
    FORWARD = "forward"
    NONE = "none"


class MouseEventType(StrEnum):
    """CDP mouse event types."""

    PRESSED = "mousePressed"
    RELEASED = "mouseReleased"
    MOVED = "mouseMoved"
    WHEEL = "mouseWheel"


class KeyEventType(StrEnum):
    """CDP keyboard event types."""

    KEY_DOWN = "keyDown"
    KEY_UP = "keyUp"
    RAW_KEY_DOWN = "rawKeyDown"
    CHAR = "char"


@dataclass
class MouseEvent:
    """Mouse event data."""

    type: MouseEventType
    x: int
    y: int
    button: MouseButton = MouseButton.NONE
    click_count: int = 0
    modifiers: int = 0  # Bitfield: 1=Alt, 2=Ctrl, 4=Meta, 8=Shift


@dataclass
class KeyboardEvent:
    """Keyboard event data."""

    type: KeyEventType
    key: str
    code: str | None = None
    text: str | None = None
    modifiers: int = 0  # Bitfield: 1=Alt, 2=Ctrl, 4=Meta, 8=Shift


@dataclass
class WheelEvent:
    """Mouse wheel event data."""

    x: int
    y: int
    delta_x: float
    delta_y: float


class CDPInputService:
    """
    Service for forwarding input events to Chrome via CDP.

    Connects to Chrome's CDP endpoint and translates high-level input events
    into CDP Input.dispatch* protocol commands.
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.msg_id = 0
        self._connected = False

    async def connect(self) -> bool:
        """
        Connect to Chrome CDP page-level WebSocket.

        Input.dispatch* commands require a page-level connection, not browser-level.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()

            # Get page-level WebSocket URL (Input domain requires page target)
            async with self.session.get(
                f"{self.cdp_url}/json",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"CDP /json endpoint returned {resp.status}")
                    return False

                pages = await resp.json()

            # Find first page target
            ws_url = None
            for target in pages:
                if target.get("type") == "page":
                    ws_url = target.get("webSocketDebuggerUrl")
                    break

            if not ws_url:
                # Fallback: try browser-level (limited CDP support)
                logger.warning("No page target found, falling back to browser WS")
                async with self.session.get(
                    f"{self.cdp_url}/json/version",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    version_info = await resp.json()
                    ws_url = version_info.get("webSocketDebuggerUrl")

            if not ws_url:
                logger.error("No webSocketDebuggerUrl found in CDP targets")
                return False

            # Connect to WebSocket
            self.ws = await self.session.ws_connect(
                ws_url, timeout=aiohttp.ClientTimeout(total=10)
            )

            self._connected = True
            logger.info(f"Connected to CDP page: {ws_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to CDP: {e}", exc_info=True)
            return False

    async def disconnect(self) -> None:
        """Disconnect from CDP and cleanup resources."""
        self._connected = False

        if self.ws:
            await self.ws.close()
            self.ws = None

        if self.session:
            await self.session.close()
            self.session = None

        logger.info("Disconnected from CDP")

    async def _send_command(self, method: str, params: dict | None = None) -> dict:
        """
        Send CDP command and wait for response.

        Args:
            method: CDP method name (e.g., "Input.dispatchMouseEvent")
            params: Method parameters

        Returns:
            Response dict

        Raises:
            RuntimeError: If not connected or command fails
        """
        if not self._connected or not self.ws:
            raise RuntimeError("Not connected to CDP")

        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params

        await self.ws.send_json(msg)

        # Wait for response
        async for ws_msg in self.ws:
            if ws_msg.type == aiohttp.WSMsgType.TEXT:
                data = ws_msg.json()
                if data.get("id") == self.msg_id:
                    if "error" in data:
                        raise RuntimeError(f"CDP command failed: {data['error']}")
                    return data.get("result", {})

        raise RuntimeError("WebSocket closed before response received")

    async def dispatch_mouse_event(self, event: MouseEvent) -> None:
        """
        Dispatch mouse event to Chrome.

        Args:
            event: Mouse event data
        """
        params = {
            "type": event.type.value,
            "x": event.x,
            "y": event.y,
            "modifiers": event.modifiers,
        }

        if event.button != MouseButton.NONE:
            params["button"] = event.button.value

        if event.click_count > 0:
            params["clickCount"] = event.click_count

        await self._send_command("Input.dispatchMouseEvent", params)
        logger.debug(f"Dispatched mouse event: {event.type} at ({event.x}, {event.y})")

    async def dispatch_keyboard_event(self, event: KeyboardEvent) -> None:
        """
        Dispatch keyboard event to Chrome.

        Args:
            event: Keyboard event data
        """
        params = {
            "type": event.type.value,
            "modifiers": event.modifiers,
        }

        if event.key:
            params["key"] = event.key

        if event.code:
            params["code"] = event.code

        if event.text:
            params["text"] = event.text

        await self._send_command("Input.dispatchKeyEvent", params)
        logger.debug(f"Dispatched keyboard event: {event.type} key={event.key}")

    async def dispatch_wheel_event(self, event: WheelEvent) -> None:
        """
        Dispatch mouse wheel event to Chrome.

        Args:
            event: Wheel event data
        """
        params = {
            "type": "mouseWheel",
            "x": event.x,
            "y": event.y,
            "deltaX": event.delta_x,
            "deltaY": event.delta_y,
        }

        await self._send_command("Input.dispatchMouseEvent", params)
        logger.debug(
            f"Dispatched wheel event: delta=({event.delta_x}, {event.delta_y})"
        )
