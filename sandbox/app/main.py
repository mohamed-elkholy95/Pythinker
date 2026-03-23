from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import sys
import asyncio

from app.core.config import settings
from app.core.telemetry import setup_telemetry
from app.api.router import api_router
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from app.core.middleware import SandboxAuthMiddleware, auto_extend_timeout_middleware


# Configure logging
def setup_logging():
    """
    Set up the application logging system

    Configures log level, format, and handlers based on application settings.
    Outputs logs to stdout for container compatibility.
    """
    log_level = getattr(logging, settings.LOG_LEVEL)
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=log_level, format=log_format, handlers=[logging.StreamHandler(sys.stdout)]
    )
    # Get root logger
    root_logger = logging.getLogger()

    # Set root log level
    log_level = getattr(logging, settings.LOG_LEVEL)
    root_logger.setLevel(log_level)

    # Suppress noisy uvicorn access logs for health checks (every 30s)
    class _HealthCheckFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            return '"GET /health ' not in msg

    for _name in ("uvicorn.access", "uvicorn"):
        _logger = logging.getLogger(_name)
        _logger.addFilter(_HealthCheckFilter())

    # Log setup completion
    logging.info(
        "Sandbox logging system initialized with level: %s", settings.LOG_LEVEL
    )


# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize Chrome on-demand lifecycle manager."""
    from app.services.chrome_lifecycle import init_chrome_lifecycle

    lifecycle = None
    if settings.CHROME_ON_DEMAND:
        import xmlrpc.client
        from urllib.parse import quote

        from app.services.supervisor import UnixStreamTransport

        username = quote(settings.SUPERVISOR_RPC_USERNAME, safe="")
        password = quote(settings.SUPERVISOR_RPC_PASSWORD, safe="")

        rpc = xmlrpc.client.ServerProxy(
            f"http://{username}:{password}@localhost",
            transport=UnixStreamTransport("/tmp/supervisor.sock"),
        )

        lifecycle = init_chrome_lifecycle(
            rpc,
            idle_timeout=settings.CHROME_IDLE_TIMEOUT,
            ready_timeout=settings.CHROME_READY_TIMEOUT,
            idle_check_interval=settings.CHROME_IDLE_CHECK_INTERVAL,
            cdp_port=settings.CHROME_CDP_PORT,
        )
        await lifecycle.sync_state_from_supervisor()
        await lifecycle.start_idle_checker()
        logger.info(
            "Chrome on-demand lifecycle enabled (idle_timeout=%ds)",
            settings.CHROME_IDLE_TIMEOUT,
        )
    else:
        logger.info("Chrome on-demand disabled — Chrome is always-on")

    yield

    if lifecycle is not None:
        await lifecycle.stop_idle_checker()
        logger.info("Chrome lifecycle manager shut down")


app = FastAPI(
    version="1.0.0",
    lifespan=lifespan,
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Sandbox API server starting")

# Register middleware — auth middleware runs first (ASGI), then timeout extension (HTTP)
app.add_middleware(SandboxAuthMiddleware)
app.middleware("http")(auto_extend_timeout_middleware)

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Initialize observability (OTEL + Sentry) — lazy, zero overhead when disabled
setup_telemetry(app)

# Register routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/sandbox-context")
async def get_sandbox_context():
    """Serve sandbox context JSON for backend consumption.

    Placed at the top level (not under /api/v1/) so it is accessible without
    the X-Sandbox-Secret header — the context file contains only environment
    metadata (no secrets) and must be reachable by the backend at startup.

    Checks multiple paths because the context generator may fall back to
    ``~/sandbox_context.json`` when ``/app/`` is read-only.  The freshest
    file (by ``generated_at``) wins.
    """
    import json
    import os
    from datetime import datetime

    candidate_paths = [
        "/app/sandbox_context.json",
        os.path.expanduser("~/sandbox_context.json"),
    ]

    best_context = None
    best_ts: datetime | None = None

    for path in candidate_paths:
        try:
            with open(path) as f:
                data = json.load(f)
            generated = data.get("generated_at", "")
            try:
                ts = datetime.fromisoformat(generated)
            except (ValueError, TypeError):
                ts = datetime.min
            if best_ts is None or ts > best_ts:
                best_context = data
                best_ts = ts
        except (FileNotFoundError, OSError):
            continue

    if best_context is not None:
        return best_context

    from fastapi import HTTPException

    raise HTTPException(status_code=503, detail="Context not generated yet")


@app.get("/health")
async def health_check(response: Response):
    """Health check endpoint for container orchestration.

    When Chrome on-demand is enabled, an intentionally stopped Chrome is
    reported as ``"on_demand_stopped"`` (healthy), not as a failure.
    """
    from app.services.chrome_lifecycle import get_chrome_lifecycle

    async def _check_port(host: str, port: int) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    lifecycle = get_chrome_lifecycle()

    checks: dict = {
        "api": True,
        "framework": await _check_port("127.0.0.1", 8082),
    }

    if lifecycle is not None:
        # On-demand mode: Chrome being stopped is healthy
        if lifecycle.is_running:
            checks["cdp"] = await _check_port("127.0.0.1", 9222)
        else:
            checks["cdp"] = "on_demand_stopped"
    else:
        # Always-on mode: CDP must be responsive
        checks["cdp"] = await _check_port("127.0.0.1", 9222)

    # "on_demand_stopped" is healthy — only False is unhealthy
    unhealthy = any(v is False for v in checks.values())
    if unhealthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "service": "sandbox", "checks": checks}

    return {"status": "healthy", "service": "sandbox", "checks": checks}


logger.info("Sandbox API routes registered and server ready")
