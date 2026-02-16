"""Tests for VNC websocket lifecycle handling."""

import asyncio
from types import SimpleNamespace
from typing import Never
from unittest.mock import patch

import pytest
from fastapi import WebSocketDisconnect

from app.core.config import StreamingMode
from app.interfaces.api import session_routes
from app.interfaces.api.session_routes import vnc_websocket


class _FakeClientWebSocket:
    def __init__(self, receive_error: BaseException | None = None) -> None:
        self.accept_calls: list[str | None] = []
        self.close_calls: list[tuple[int, str]] = []
        self.sent_binary: list[bytes] = []
        self._receive_error = receive_error

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accept_calls.append(subprotocol)

    async def receive_bytes(self) -> bytes:
        if self._receive_error is not None:
            raise self._receive_error
        await asyncio.sleep(0)
        return b""

    async def send_bytes(self, data: bytes) -> None:
        self.sent_binary.append(data)

    async def close(self, code: int, reason: str) -> None:
        self.close_calls.append((code, reason))


class _FakeSandboxWebSocket:
    def __init__(self) -> None:
        self.sent_data: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent_data.append(data)

    async def recv(self) -> Never:
        # Simulate a long-running read until cancellation by the route cleanup path.
        await asyncio.sleep(999)
        raise AssertionError("unreachable")


class _FakeSandboxConnectCtx:
    def __init__(self, sandbox_ws: _FakeSandboxWebSocket) -> None:
        self.sandbox_ws = sandbox_ws

    async def __aenter__(self) -> _FakeSandboxWebSocket:
        return self.sandbox_ws

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


_DUAL_MODE_SETTINGS = SimpleNamespace(
    is_vnc_enabled=True,
    sandbox_streaming_mode=StreamingMode.DUAL,
)


@pytest.mark.asyncio
async def test_vnc_websocket_rejects_in_cdp_only_mode():
    """VNC WebSocket should close with 1008 when streaming mode is cdp_only."""
    websocket = _FakeClientWebSocket()
    agent_service = SimpleNamespace(get_vnc_url=_return_vnc_url)

    mock_settings = SimpleNamespace(
        is_vnc_enabled=False,
        sandbox_streaming_mode=StreamingMode.CDP_ONLY,
    )
    with patch("app.interfaces.api.session_routes.get_settings", return_value=mock_settings):
        await vnc_websocket(
            websocket=websocket,
            session_id="session-1",
            signature="sig",
            agent_service=agent_service,
        )

    assert websocket.accept_calls == ["binary"]
    assert websocket.close_calls == [(1008, "VNC disabled (cdp_only mode)")]


@pytest.mark.asyncio
async def test_vnc_websocket_returns_policy_violation_for_missing_sandbox_runtime_error():
    websocket = _FakeClientWebSocket()
    agent_service = SimpleNamespace(get_vnc_url=_raise_no_sandbox_runtime_error)

    with patch("app.interfaces.api.session_routes.get_settings", return_value=_DUAL_MODE_SETTINGS):
        await vnc_websocket(
            websocket=websocket,
            session_id="session-1",
            signature="sig",
            agent_service=agent_service,
        )

    assert websocket.accept_calls == ["binary"]
    assert websocket.close_calls == [(1008, "Session has no sandbox environment")]


@pytest.mark.asyncio
async def test_vnc_websocket_closes_gracefully_when_client_disconnects(monkeypatch: pytest.MonkeyPatch):
    sandbox_ws = _FakeSandboxWebSocket()
    websocket = _FakeClientWebSocket(receive_error=WebSocketDisconnect())
    agent_service = SimpleNamespace(get_vnc_url=_return_vnc_url)

    def _fake_connect(*args, **kwargs):
        return _FakeSandboxConnectCtx(sandbox_ws)

    monkeypatch.setattr(session_routes.websockets, "connect", _fake_connect)

    with patch("app.interfaces.api.session_routes.get_settings", return_value=_DUAL_MODE_SETTINGS):
        await vnc_websocket(
            websocket=websocket,
            session_id="session-1",
            signature="sig",
            agent_service=agent_service,
        )

    assert websocket.accept_calls == ["binary"]
    assert websocket.close_calls == []
    assert sandbox_ws.sent_data == []


async def _raise_no_sandbox_runtime_error(_session_id: str) -> str:
    raise RuntimeError("Session has no sandbox environment")


async def _return_vnc_url(_session_id: str) -> str:
    return "ws://sandbox/vnc"
