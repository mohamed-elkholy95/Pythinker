from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.lifespan import get_health_state, lifespan
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from app.infrastructure.middleware.security_headers import add_security_headers_middleware
from app.infrastructure.structured_logging import get_logger, setup_structured_logging
from app.interfaces.api.routes import router
from app.interfaces.errors.exception_handlers import register_exception_handlers

# Initialize structured logging system
setup_structured_logging()
logger = get_logger(__name__)

# Load configuration
settings = get_settings()

app = FastAPI(
    title="Pythinker AI Agent",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Add security headers middleware (Context7 best practice - OWASP compliant)
add_security_headers_middleware(app)

# Add request logging middleware (outermost - runs first)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Configure CORS with proper security settings
cors_origins = settings.cors_origins_list
if not cors_origins:
    if settings.is_development:
        cors_origins = [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]
        logger.warning(f"[SECURITY] CORS using development defaults: {cors_origins}")
    else:
        logger.error("[SECURITY] No CORS origins configured for production!")
        cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods.split(","),
    allow_headers=settings.cors_allow_headers.split(","),
    expose_headers=["X-Request-ID"],
)

logger.info(f"CORS configured with origins: {cors_origins}")

# Register exception handlers
register_exception_handlers(app)


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic health check endpoint for load balancers.
    Returns 200 if the service is running.
    """
    return {"status": "ok", "service": "pythinker-agent"}


@app.get("/api/health", tags=["Health"], include_in_schema=False)
async def health_check_api_alias():
    """Backward-compatible alias for clients probing /api/health."""
    return await health_check()


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check endpoint.
    Returns 200 only if all required services are connected.
    """
    state = get_health_state()

    if not state["ready"]:
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "services": state, "message": "Service is starting up"}
        )

    # Check required services
    if not state["mongodb"] or not state["redis"]:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "services": state, "message": "Required services unavailable"},
        )

    return {"status": "ready", "services": state, "environment": settings.environment}


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check endpoint.
    Returns 200 if the service is alive (can accept requests).
    """
    return {"status": "alive"}


@app.get("/metrics", tags=["Metrics"], include_in_schema=False)
async def root_metrics():
    """Prometheus scrape endpoint at root path (no auth — for internal network only).

    Standard Prometheus convention is GET /metrics. The authenticated endpoint
    at /api/v1/metrics remains available for external access.
    """
    from fastapi.responses import PlainTextResponse

    from app.core.prometheus_metrics import format_prometheus

    return PlainTextResponse(format_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")


# Register routes
app.include_router(router, prefix="/api/v1")
