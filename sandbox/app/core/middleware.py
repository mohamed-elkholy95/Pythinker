import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTH_HEADER = "x-sandbox-secret"
# Paths exempt from auth (health checks used by Docker/k8s probes)
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json"})


class SandboxAuthMiddleware:
    """ASGI middleware that validates a shared secret on every API request.

    When SANDBOX_API_SECRET is set, requests to /api/* must include
    a matching X-Sandbox-Secret header. Health endpoints are exempt so
    container orchestrators can probe without credentials.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._secret = settings.SANDBOX_API_SECRET
        if self._secret:
            logger.info("Sandbox API secret authentication enabled")
        else:
            logger.warning(
                "SANDBOX_API_SECRET not set — sandbox API is unauthenticated. "
                "Set SANDBOX_API_SECRET in production."
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._secret:
            await self.app(scope, receive, send)
            return

        scope_type = scope["type"]

        # Only gate http and websocket scopes
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Allow health/docs endpoints without auth
        if path in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # Check auth header for all /api/* routes (covers both HTTP and WebSocket)
        # WebSocket clients pass the secret via query param ?secret= or header
        if path.startswith("/api/"):
            headers = dict(scope.get("headers", []))
            token = headers.get(_AUTH_HEADER.encode(), b"").decode()

            # Fallback: check query string for WebSocket clients that can't set headers
            if not token and scope_type == "websocket":
                from urllib.parse import parse_qs

                qs = parse_qs(scope.get("query_string", b"").decode())
                token = qs.get("secret", [""])[0]

            if token != self._secret:
                # Log the source IP and path for diagnostics. Requests from the
                # Docker gateway IP (e.g. 172.x.x.1 / 192.168.x.1) typically come
                # from host-side tools hitting the exposed sandbox port without auth.
                client = scope.get("client")
                client_ip = client[0] if client else "unknown"
                logger.warning(
                    "Sandbox auth rejected: %s %s from %s (missing or invalid secret)",
                    scope_type.upper(),
                    path,
                    client_ip,
                )
                if scope_type == "http":
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "Invalid or missing sandbox API secret"},
                    )
                    await response(scope, receive, send)
                else:
                    # For WebSocket: must accept then close (ASGI spec)
                    await send({"type": "websocket.close", "code": 4003})
                return

        await self.app(scope, receive, send)


async def auto_extend_timeout_middleware(request: Request, call_next):
    """
    Middleware to automatically extend timeout on every API request
    Only auto-extends when auto-expand is enabled (disabled when user explicitly manages timeout)
    """
    from app.services.supervisor import supervisor_service

    # Only extend timeout if timeout is currently active, it's an API request,
    # and not a timeout management API call, and auto-expand is enabled
    if (
        settings.SERVICE_TIMEOUT_MINUTES is not None
        and supervisor_service.timeout_active
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/v1/supervisor/timeout/")
        and supervisor_service.auto_expand_enabled
    ):
        try:
            await supervisor_service.extend_timeout()
            logger.debug(
                "Timeout automatically extended due to API request: %s",
                request.url.path,
            )
        except Exception as e:
            logger.warning("Failed to auto-extend timeout: %s", str(e))

    response = await call_next(request)
    return response
