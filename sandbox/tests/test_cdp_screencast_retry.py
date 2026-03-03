"""Tests for CDP screencast single-frame retry behavior."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest

from app.services.cdp_screencast import CDPScreencastService


@pytest.mark.asyncio
async def test_capture_single_frame_retries_after_exception() -> None:
    service = CDPScreencastService()
    encoded = base64.b64encode(b"frame").decode()

    service.ensure_connected = AsyncMock(return_value=True)
    service._ensure_viewport = AsyncMock()
    service._send_command = AsyncMock(
        side_effect=[
            Exception("socket closed"),
            {"result": {"data": encoded}},
        ]
    )
    service._handle_page_detached = AsyncMock()
    service._maybe_escalate = AsyncMock(return_value=False)
    service._cached_ws_url = "ws://broken-target"

    frame = await service.capture_single_frame()

    assert frame == b"frame"
    assert service.ensure_connected.await_count == 2
    service._handle_page_detached.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_single_frame_retries_after_non_detached_error() -> None:
    service = CDPScreencastService()
    encoded = base64.b64encode(b"frame").decode()

    service.ensure_connected = AsyncMock(return_value=True)
    service._ensure_viewport = AsyncMock()
    service._send_command = AsyncMock(
        side_effect=[
            {"error": {"code": -32000, "message": "temporary renderer error"}},
            {"result": {"data": encoded}},
        ]
    )
    service._maybe_escalate = AsyncMock(return_value=False)
    service._cached_ws_url = "ws://broken-target"

    with patch("app.services.cdp_screencast.asyncio.sleep", new=AsyncMock()):
        frame = await service.capture_single_frame()

    assert frame == b"frame"
    assert service.ensure_connected.await_count == 2
