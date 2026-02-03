import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from typing import ClassVar

from beanie import init_beanie
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.sandbox_pool import start_sandbox_pool, stop_sandbox_pool
from app.infrastructure.models.documents import (
    AgentDocument,
    DailyUsageDocument,
    SessionDocument,
    SkillDocument,
    SnapshotDocument,
    UsageDocument,
    UserDocument,
)
from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.storage.qdrant import get_qdrant
from app.infrastructure.storage.redis import get_redis
from app.infrastructure.structured_logging import (
    get_logger,
    set_request_id,
    setup_structured_logging,
)
from app.interfaces.api.routes import router
from app.interfaces.dependencies import get_agent_service
from app.interfaces.errors.exception_handlers import register_exception_handlers

# Initialize structured logging system
setup_structured_logging()
logger = get_logger(__name__)

# Load configuration
settings = get_settings()


# ============================================================================
# MIDDLEWARE COMPONENTS
# ============================================================================


class RequestLoggingMiddleware:
    """Middleware to log HTTP requests and add correlation IDs"""

    # Paths to exclude from logging (health checks, static files)
    EXCLUDED_PATHS: ClassVar[set[str]] = {"/health", "/api/v1/health", "/favicon.ico"}
    # Sensitive headers to redact
    SENSITIVE_HEADERS: ClassVar[set[str]] = {"authorization", "cookie", "x-api-key"}

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip logging for excluded paths
        if path in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        # Generate request ID
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        start_time = time.time()

        # Store request_id in state for access in handlers
        scope["state"] = scope.get("state", {})
        scope["state"]["request_id"] = request_id

        # Propagate request_id to structlog for correlation
        set_request_id(request_id)

        # Log request (sanitized)
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"[{request_id}] {request.method} {path} - Client: {client_ip}")

        # Capture response status
        response_status = 500

        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                # Add request ID to response headers
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            logger.error(f"[{request_id}] Request failed with exception: {e}")
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            log_level = logging.INFO if response_status < 400 else logging.WARNING
            logger.log(log_level, f"[{request_id}] {request.method} {path} - {response_status} ({duration_ms:.2f}ms)")


class RateLimitMiddleware:
    """Middleware to implement rate limiting using Redis with in-memory fallback.

    Security: If Redis is unavailable, falls back to in-memory rate limiting
    to prevent authentication bypass attacks.
    """

    # Auth endpoints have stricter limits
    AUTH_PATHS: ClassVar[set[str]] = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}

    # In-memory fallback storage: {key: (count, window_start_time)}
    _fallback_storage: ClassVar[dict] = {}
    _fallback_window_seconds: ClassVar[int] = 60
    _fallback_cleanup_counter: ClassVar[int] = 0
    _fallback_cleanup_interval: ClassVar[int] = 100  # Cleanup every N requests

    def __init__(self, app: Callable):
        self.app = app

    def _cleanup_fallback_storage(self) -> None:
        """Remove expired entries from fallback storage to prevent memory growth."""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, window_start) in self._fallback_storage.items()
            if current_time - window_start > self._fallback_window_seconds
        ]
        for key in expired_keys:
            del self._fallback_storage[key]

    def _fallback_rate_limit(self, key: str, max_requests: int) -> tuple[bool, int]:
        """In-memory rate limiting fallback when Redis is unavailable.

        Returns:
            tuple of (is_allowed, current_count)
        """
        current_time = time.time()

        # Periodic cleanup to prevent memory growth
        self._fallback_cleanup_counter += 1
        if self._fallback_cleanup_counter >= self._fallback_cleanup_interval:
            self._cleanup_fallback_storage()
            self._fallback_cleanup_counter = 0

        if key in self._fallback_storage:
            count, window_start = self._fallback_storage[key]

            # Check if window has expired
            if current_time - window_start > self._fallback_window_seconds:
                # Start new window
                self._fallback_storage[key] = (1, current_time)
                return True, 1
            # Increment count in current window
            new_count = count + 1
            self._fallback_storage[key] = (new_count, window_start)
            return new_count <= max_requests, new_count
        # New key, start window
        self._fallback_storage[key] = (1, current_time)
        return True, 1

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Determine rate limit based on path
        if path in self.AUTH_PATHS:
            max_requests = settings.rate_limit_auth_requests_per_minute
        else:
            max_requests = settings.rate_limit_requests_per_minute

        # Get client identifier (IP or user ID from token)
        client_id = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_id}:{path.split('/')[3] if len(path.split('/')) > 3 else 'default'}"

        rate_limit_exceeded = False
        using_fallback = False

        try:
            redis = get_redis().client

            # Increment request count
            current = await redis.incr(key)

            # Set expiry on first request
            if current == 1:
                await redis.expire(key, 60)  # 1 minute window

            # Check if rate limit exceeded
            if current > max_requests:
                rate_limit_exceeded = True

        except Exception as e:
            # SECURITY FIX: Fall back to in-memory rate limiting instead of allowing all requests
            logger.warning(f"Redis unavailable for rate limiting, using in-memory fallback: {e}")
            using_fallback = True

            is_allowed, current = self._fallback_rate_limit(key, max_requests)
            if not is_allowed:
                rate_limit_exceeded = True

        if rate_limit_exceeded:
            logger.warning(
                f"Rate limit exceeded for {client_id} on {path}{' (fallback mode)' if using_fallback else ''}"
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please try again later."},
                },
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _initialize_observability() -> None:
    """Initialize observability components (OTEL, metrics, tracer)."""
    try:
        # Configure OTEL if enabled
        if settings.otel_enabled and settings.otel_endpoint:
            from app.infrastructure.observability.otel_exporter import configure_otel

            configure_otel(
                endpoint=settings.otel_endpoint,
                service_name=settings.otel_service_name,
                insecure=settings.otel_insecure,
            )

        # Configure tracer with OTEL export
        from app.infrastructure.observability.tracer import configure_tracer

        configure_tracer(
            service_name=settings.otel_service_name,
            export_to_log=True,
            export_to_otel=settings.otel_enabled,
        )

        logger.info("Observability components initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize observability: {e}")


# Health check state
_health_state = {
    "mongodb": False,
    "redis": False,
    "qdrant": False,
    "sandbox_pool": False,
    "ready": False,
}


def get_health_state() -> dict:
    """Get current health state for health check endpoint"""
    return _health_state.copy()


# Create lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code executed on startup
    logger.info("Application startup - Pythinker AI Agent initializing")
    logger.info(f"Environment: {settings.environment}")

    # Initialize enhanced error handling and monitoring
    from app.core.system_integrator import get_system_integrator

    system_integrator = get_system_integrator()

    try:
        # Initialize observability (OTEL, metrics)
        _initialize_observability()

        # Initialize MongoDB and Beanie
        await get_mongodb().initialize()
        _health_state["mongodb"] = True

        # Initialize Beanie
        await init_beanie(
            database=get_mongodb().client[settings.mongodb_database],
            document_models=[
                AgentDocument,
                SessionDocument,
                SkillDocument,
                SnapshotDocument,
                UserDocument,
                UsageDocument,
                DailyUsageDocument,
            ],
        )
        logger.info("Successfully initialized Beanie")

        # Seed official skills
        try:
            from app.infrastructure.seeds.skills_seed import seed_official_skills

            skill_count = await seed_official_skills()
            logger.info(f"Seeded {skill_count} official skills")
        except Exception as e:
            logger.warning(f"Failed to seed skills (non-critical): {e}")

        # Initialize Redis
        await get_redis().initialize()
        _health_state["redis"] = True

        # Initialize Qdrant (optional, graceful degradation if unavailable)
        try:
            await get_qdrant().initialize()
            _health_state["qdrant"] = True
        except Exception as e:
            logger.warning(f"Qdrant initialization failed (graceful degradation): {e}")
            _health_state["qdrant"] = False

        # Initialize Sandbox Pool (Phase 3: Pre-warming) if enabled
        if settings.sandbox_pool_enabled:
            try:
                from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                await start_sandbox_pool(DockerSandbox)
                _health_state["sandbox_pool"] = True
                logger.info("Sandbox pool initialized and warming")
            except Exception as e:
                logger.warning(f"Sandbox pool initialization failed (graceful degradation): {e}")
                _health_state["sandbox_pool"] = False
        else:
            logger.info("Sandbox pool disabled by configuration")

        # Initialize enhanced system components
        await system_integrator.initialize()
        logger.info("Enhanced system components initialized")

        # Mark as ready
        _health_state["ready"] = True
        logger.info("Application startup complete - all services initialized")

        try:
            yield
        finally:
            # Code executed on shutdown
            logger.info("Application shutdown - Pythinker AI Agent terminating")
            _health_state["ready"] = False

            # Shutdown sandbox pool first (Phase 3)
            if settings.sandbox_pool_enabled:
                try:
                    await asyncio.wait_for(stop_sandbox_pool(), timeout=30.0)
                    _health_state["sandbox_pool"] = False
                    logger.info("Sandbox pool shutdown completed")
                except TimeoutError:
                    logger.warning("Sandbox pool shutdown timed out")
                except Exception as e:
                    logger.error(f"Sandbox pool shutdown error: {e}")

            # Shutdown enhanced components
            try:
                await asyncio.wait_for(system_integrator.shutdown(), timeout=15.0)
                logger.info("Enhanced components shutdown completed")
            except TimeoutError:
                logger.warning("Enhanced components shutdown timed out")
            except Exception as e:
                logger.error(f"Enhanced components shutdown error: {e}")

            # Disconnect from MongoDB
            try:
                await asyncio.wait_for(get_mongodb().shutdown(), timeout=10.0)
                _health_state["mongodb"] = False
            except TimeoutError:
                logger.warning("MongoDB shutdown timed out")
            except Exception as e:
                logger.error(f"MongoDB shutdown error: {e}")

            # Disconnect from Redis
            try:
                await asyncio.wait_for(get_redis().shutdown(), timeout=10.0)
                _health_state["redis"] = False
            except TimeoutError:
                logger.warning("Redis shutdown timed out")
            except Exception as e:
                logger.error(f"Redis shutdown error: {e}")

            # Disconnect from Qdrant
            try:
                await asyncio.wait_for(get_qdrant().shutdown(), timeout=10.0)
                _health_state["qdrant"] = False
            except TimeoutError:
                logger.warning("Qdrant shutdown timed out")
            except Exception:
                pass  # Already logged or never initialized

            logger.info("Cleaning up AgentService instance")
            try:
                await asyncio.wait_for(get_agent_service().shutdown(), timeout=30.0)
                logger.info("AgentService shutdown completed successfully")
            except TimeoutError:
                logger.warning("AgentService shutdown timed out after 30 seconds")
            except Exception as e:
                logger.error(f"Error during AgentService cleanup: {e!s}")

            logger.info("Application shutdown complete")

    except Exception as e:
        logger.critical(f"Critical error during application startup: {e}")
        # Attempt graceful shutdown even on startup failure
        with suppress(Exception):
            await system_integrator.shutdown()
        raise


app = FastAPI(
    title="Pythinker AI Agent",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,  # Disable docs in production
    redoc_url="/redoc" if settings.is_development else None,
)

# Add request logging middleware (outermost - runs first)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Configure CORS with proper security settings
cors_origins = settings.cors_origins_list
if not cors_origins:
    # In development without explicit config, allow common dev origins
    if settings.is_development:
        cors_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]
        logger.warning(f"[SECURITY] CORS using development defaults: {cors_origins}")
    else:
        logger.error("[SECURITY] No CORS origins configured for production!")
        cors_origins = []  # Block all cross-origin requests

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


# Register routes
app.include_router(router, prefix="/api/v1")
