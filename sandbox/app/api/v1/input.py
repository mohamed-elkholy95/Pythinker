"""
CDP Input API - Real-time input forwarding via Chrome DevTools Protocol.

Provides WebSocket endpoint for forwarding mouse, keyboard, and scroll events
to the browser with <10ms latency.
"""

import logging
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.services.cdp_input import (
    CDPInputService,
    KeyEventType,
    KeyboardEvent,
    MouseButton,
    MouseEvent,
    MouseEventType,
    WheelEvent,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class InputMouseMessage(BaseModel):
    """Mouse input message schema."""

    type: Literal["mouse"]
    event_type: MouseEventType
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    button: MouseButton = MouseButton.NONE
    click_count: int = Field(default=0, ge=0, le=3)
    modifiers: int = Field(default=0, ge=0, le=15)


class InputKeyboardMessage(BaseModel):
    """Keyboard input message schema."""

    type: Literal["keyboard"]
    event_type: KeyEventType
    key: str
    code: str | None = None
    text: str | None = None
    modifiers: int = Field(default=0, ge=0, le=15)


class InputWheelMessage(BaseModel):
    """Wheel input message schema."""

    type: Literal["wheel"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    delta_x: float = 0.0
    delta_y: float = 0.0


class InputPingMessage(BaseModel):
    """Ping message for keep-alive."""

    type: Literal["ping"]


# Union type for all input messages
InputMessage = (
    InputMouseMessage | InputKeyboardMessage | InputWheelMessage | InputPingMessage
)


@router.websocket("/stream")
async def stream_input(websocket: WebSocket):
    """
    WebSocket endpoint for real-time input forwarding to Chrome via CDP.

    The client sends JSON messages describing input events (mouse, keyboard, wheel).
    The server translates these into CDP Input.dispatch* commands.

    Message format:
    ```json
    // Mouse event
    {
        "type": "mouse",
        "event_type": "mousePressed",  // "mousePressed" | "mouseReleased" | "mouseMoved"
        "x": 100,
        "y": 200,
        "button": "left",  // "left" | "middle" | "right" | "none"
        "click_count": 1,
        "modifiers": 0  // Bitfield: 1=Alt, 2=Ctrl, 4=Meta, 8=Shift
    }

    // Keyboard event
    {
        "type": "keyboard",
        "event_type": "keyDown",  // "keyDown" | "keyUp" | "char"
        "key": "a",
        "code": "KeyA",
        "text": "a",
        "modifiers": 0
    }

    // Wheel event
    {
        "type": "wheel",
        "x": 100,
        "y": 200,
        "delta_x": 0.0,
        "delta_y": -120.0
    }

    // Ping (keep-alive)
    {
        "type": "ping"
    }
    ```

    The server responds with:
    - `{"type": "pong"}` for ping messages
    - `{"type": "ack", "count": N}` every 100 events
    - `{"type": "error", "message": "..."}` on errors
    """
    await websocket.accept()
    logger.info("[CDP Input] WebSocket connected")

    service = CDPInputService()
    event_count = 0

    try:
        # Connect to CDP
        if not await service.connect():
            await websocket.send_json(
                {"type": "error", "message": "Failed to connect to Chrome CDP"}
            )
            await websocket.close()
            return

        await websocket.send_json(
            {"type": "ready", "message": "CDP input service ready"}
        )

        # Process input events
        while True:
            raw_msg = await websocket.receive_json()

            # Handle ping
            if raw_msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                # Dispatch based on message type
                msg_type = raw_msg.get("type")

                if msg_type == "mouse":
                    msg = InputMouseMessage.model_validate(raw_msg)
                    event = MouseEvent(
                        type=msg.event_type,
                        x=msg.x,
                        y=msg.y,
                        button=msg.button,
                        click_count=msg.click_count,
                        modifiers=msg.modifiers,
                    )
                    await service.dispatch_mouse_event(event)

                elif msg_type == "keyboard":
                    msg = InputKeyboardMessage.model_validate(raw_msg)
                    event = KeyboardEvent(
                        type=msg.event_type,
                        key=msg.key,
                        code=msg.code,
                        text=msg.text,
                        modifiers=msg.modifiers,
                    )
                    await service.dispatch_keyboard_event(event)

                elif msg_type == "wheel":
                    msg = InputWheelMessage.model_validate(raw_msg)
                    event = WheelEvent(
                        x=msg.x,
                        y=msg.y,
                        delta_x=msg.delta_x,
                        delta_y=msg.delta_y,
                    )
                    await service.dispatch_wheel_event(event)

                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {msg_type}",
                        }
                    )
                    continue

                event_count += 1

                # Send periodic ack
                if event_count % 100 == 0:
                    await websocket.send_json({"type": "ack", "count": event_count})
                    logger.debug(f"[CDP Input] Processed {event_count} events")

            except Exception as e:
                logger.error(f"[CDP Input] Failed to process event: {e}", exc_info=True)
                await websocket.send_json(
                    {"type": "error", "message": f"Failed to process event: {str(e)}"}
                )

    except WebSocketDisconnect:
        logger.info(f"[CDP Input] Client disconnected after {event_count} events")
    except Exception as e:
        logger.error(f"[CDP Input] Unexpected error: {e}", exc_info=True)
    finally:
        await service.disconnect()
        logger.info(f"[CDP Input] Session ended, processed {event_count} events")


@router.get("/status")
async def input_status():
    """
    Check CDP input availability.

    Returns:
        Status dict with CDP availability information
    """
    service = CDPInputService()
    try:
        connected = await service.connect()
        await service.disconnect()

        if connected:
            return {
                "available": True,
                "message": "CDP input service ready",
                "cdp_url": service.cdp_url,
            }
        else:
            return {
                "available": False,
                "message": "Failed to connect to Chrome CDP",
            }
    except Exception as e:
        logger.error(f"CDP input status check failed: {e}")
        return {
            "available": False,
            "message": "CDP input service unavailable",
            "error": str(e),
        }
