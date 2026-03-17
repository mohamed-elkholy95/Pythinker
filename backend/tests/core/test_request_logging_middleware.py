import pytest

from app.core.middleware import RequestLoggingMiddleware
from app.infrastructure.structured_logging import request_id_var


@pytest.mark.asyncio
async def test_request_logging_middleware_clears_request_id_for_excluded_paths() -> None:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 405, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = RequestLoggingMiddleware(app)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    # Simulate stale context from another request/task.
    request_id_var.set("stale-request-id")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/health",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }

    await middleware(scope, receive, send)

    assert request_id_var.get() is None
