"""Tests for sandbox auth middleware logic.

Since the SandboxAuthMiddleware lives in the sandbox package (not backend),
these tests validate the security contract via a standalone ASGI middleware
that mirrors the same logic.
"""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket


class _TestAuthMiddleware:
    """Mirror of SandboxAuthMiddleware for testing the auth contract."""

    AUTH_HEADER = b"x-sandbox-secret"
    PUBLIC_PATHS = frozenset({"/health"})

    def __init__(self, app: ASGIApp, secret: str | None) -> None:
        self.app = app
        self._secret = secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._secret or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in self.PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        if path.startswith("/api/"):
            headers = dict(scope.get("headers", []))
            token = headers.get(self.AUTH_HEADER, b"").decode()

            if not token and scope["type"] == "websocket":
                from urllib.parse import parse_qs

                qs = parse_qs(scope.get("query_string", b"").decode())
                token = qs.get("secret", [""])[0]

            if token != self._secret:
                if scope["type"] == "http":
                    resp = JSONResponse(status_code=403, content={"detail": "forbidden"})
                    await resp(scope, receive, send)
                else:
                    await send({"type": "websocket.close", "code": 4003})
                return

        await self.app(scope, receive, send)


def _make_app(secret: str | None) -> Starlette:
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def api_test(request: Request) -> JSONResponse:
        return JSONResponse({"data": "secret"})

    async def ws_test(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"connected": True})
        await websocket.close()

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/api/v1/test", api_test),
            WebSocketRoute("/api/v1/ws", ws_test),
        ],
    )
    app.add_middleware(_TestAuthMiddleware, secret=secret)
    return app


class TestHTTPAuth:
    def test_health_no_auth(self) -> None:
        client = TestClient(_make_app("s3cret"))
        assert client.get("/health").status_code == 200

    def test_api_blocked_no_header(self) -> None:
        client = TestClient(_make_app("s3cret"))
        assert client.get("/api/v1/test").status_code == 403

    def test_api_blocked_wrong_header(self) -> None:
        client = TestClient(_make_app("s3cret"))
        resp = client.get("/api/v1/test", headers={"x-sandbox-secret": "wrong"})
        assert resp.status_code == 403

    def test_api_allowed_correct_header(self) -> None:
        client = TestClient(_make_app("s3cret"))
        resp = client.get("/api/v1/test", headers={"x-sandbox-secret": "s3cret"})
        assert resp.status_code == 200
        assert resp.json() == {"data": "secret"}

    def test_no_secret_allows_all(self) -> None:
        client = TestClient(_make_app(None))
        assert client.get("/api/v1/test").status_code == 200


class TestWebSocketAuth:
    def test_ws_blocked_no_secret(self) -> None:
        client = TestClient(_make_app("s3cret"))
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws"):
                pass

    def test_ws_allowed_query_param(self) -> None:
        client = TestClient(_make_app("s3cret"))
        with client.websocket_connect("/api/v1/ws?secret=s3cret") as ws:
            data = ws.receive_json()
            assert data == {"connected": True}

    def test_ws_no_secret_configured_allows(self) -> None:
        client = TestClient(_make_app(None))
        with client.websocket_connect("/api/v1/ws") as ws:
            data = ws.receive_json()
            assert data == {"connected": True}
