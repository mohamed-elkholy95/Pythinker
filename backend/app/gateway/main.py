"""
API Gateway - Lightweight gateway for service routing.

WARNING: This module is a development placeholder and is NOT wired into
the production compose stack. Do NOT deploy without implementing real
authentication and actual proxy routing.

Features (planned):
- Service routing (agent, sandbox, session services)
- Authentication/authorization
- Rate limiting
- Request/response logging
"""

import logging
import os
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create gateway app
app = FastAPI(
    title="Pythinker API Gateway",
    description="Unified API gateway for Pythinker services",
    version=os.environ.get("GIT_VERSION", "dev"),
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Middleware: Request logging
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable) -> Response:
    """Log all requests with timing."""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} ({duration * 1000:.0f}ms)")

    return response


@app.middleware("http")
async def authenticate(request: Request, call_next: Callable) -> Response:
    """
    Authenticate requests.

    TODO: Implement actual authentication (JWT, API keys, etc.)
    TODO: Validate auth token from Authorization header
    """
    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)

    return await call_next(request)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Gateway health check."""
    return {"status": "healthy", "service": "gateway"}


# Service routing
@app.api_route("/agent/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@limiter.limit("100/minute")
async def route_to_agent_service(request: Request, path: str):
    """
    Route requests to Agent Service.

    Rate limit: 100 requests per minute
    """
    # TODO: Proxy request to agent service
    # This would use httpx to forward the request
    return {"message": f"Agent service: {path}", "method": request.method}


@app.api_route("/sandbox/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@limiter.limit("200/minute")
async def route_to_sandbox_service(request: Request, path: str):
    """
    Route requests to Sandbox Service.

    Rate limit: 200 requests per minute (higher for sandbox operations)
    """
    # TODO: Proxy request to sandbox service
    return {"message": f"Sandbox service: {path}", "method": request.method}


@app.api_route("/session/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@limiter.limit("100/minute")
async def route_to_session_service(request: Request, path: str):
    """
    Route requests to Session Service.

    Rate limit: 100 requests per minute
    """
    # TODO: Proxy request to session service
    return {"message": f"Session service: {path}", "method": request.method}


# Gateway metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """
    Gateway metrics.

    Returns Prometheus-compatible metrics.
    """
    # TODO: Implement actual metrics collection
    return Response(
        content="# HELP gateway_requests_total Total requests\n"
        "# TYPE gateway_requests_total counter\n"
        "gateway_requests_total 0\n",
        media_type="text/plain",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)  # noqa: S104
