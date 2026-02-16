from __future__ import annotations

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

from app.application.services.maintenance_service import MaintenanceService
from app.core.config import get_settings
from app.core.sandbox_pool import start_sandbox_pool, stop_sandbox_pool
from app.infrastructure.models.canvas_documents import (
    CanvasProjectDocument,
    CanvasVersionDocument,
)
from app.infrastructure.models.connector_documents import (
    ConnectorDocument,
    UserConnectorDocument,
)
from app.infrastructure.models.documents import (
    AgentDocument,
    DailyUsageDocument,
    RatingDocument,
    ScreenshotDocument,
    SessionDocument,
    SkillDocument,
    SnapshotDocument,
    UsageDocument,
    UserDocument,
)
from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.storage.qdrant import get_qdrant
from app.infrastructure.storage.redis import get_cache_redis, get_redis
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


async def _run_periodic_session_cleanup(
    maintenance_service: MaintenanceService,
    interval_seconds: float = 300.0,
    stale_threshold_minutes: int = 30,
) -> None:
    """Background task: clean up stale sessions on a fixed interval."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await maintenance_service.cleanup_stale_running_sessions(
                stale_threshold_minutes=stale_threshold_minutes,
                dry_run=False,
            )
            if result.get("sessions_cleaned", 0) > 0:
                logger.info(
                    "Periodic cleanup: %d stale sessions cleaned",
                    result["sessions_cleaned"],
                )
        except Exception as e:
            logger.warning("Periodic session cleanup failed: %s", e)


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

    # Exempt paths: SSE long-poll, health checks, lightweight status polls
    EXEMPT_PATHS: ClassVar[set[str]] = {"/api/v1/auth/status", "/health"}

    # In-memory fallback storage: {key: (count, window_start_time)}
    _fallback_storage: ClassVar[dict] = {}
    _fallback_cleanup_counter: ClassVar[int] = 0
    _fallback_cleanup_interval: ClassVar[int] = 100  # Cleanup every N requests
    _fallback_last_cleanup_time: ClassVar[float] = 0.0  # Last cleanup timestamp
    _fallback_cleanup_time_interval: ClassVar[float] = 60.0  # Cleanup every 60 seconds
    _RATE_LIMIT_WINDOW_SCRIPT: ClassVar[str] = """
    local current = redis.call("INCR", KEYS[1])
    if current == 1 then
        redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
    end
    local ttl = redis.call("TTL", KEYS[1])
    return {current, ttl}
    """

    def __init__(self, app: Callable):
        self.app = app
        self._rate_limit_window_script = None
        # Initialize cleanup timestamp on first instantiation
        if RateLimitMiddleware._fallback_last_cleanup_time == 0.0:
            RateLimitMiddleware._fallback_last_cleanup_time = time.time()

    async def _increment_window_counter(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Atomically increment request counter and return (current_count, ttl_seconds)."""
        redis_client = get_redis()
        await redis_client.initialize()
        if self._rate_limit_window_script is None:
            self._rate_limit_window_script = redis_client.client.register_script(self._RATE_LIMIT_WINDOW_SCRIPT)

        async def _execute_script():
            script = self._rate_limit_window_script
            if script is None:
                raise RuntimeError("Rate limit script not initialized")
            return await script(keys=[key], args=[window_seconds], client=redis_client.client)

        result = await redis_client.execute_with_retry(
            _execute_script,
            operation_name="rate_limit_window_script",
        )
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(f"Unexpected rate limit script result: {result!r}")

        current = int(result[0])
        ttl = int(result[1]) if result[1] is not None else window_seconds
        if ttl <= 0:
            ttl = window_seconds
        return current, ttl

    def _cleanup_fallback_storage(self, window_seconds: int) -> None:
        """Remove expired entries from fallback storage to prevent memory growth."""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, window_start) in self._fallback_storage.items()
            if current_time - window_start > window_seconds
        ]
        for key in expired_keys:
            del self._fallback_storage[key]

    def _fallback_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """In-memory rate limiting fallback when Redis is unavailable.

        Returns:
            tuple of (is_allowed, current_count)
        """
        current_time = time.time()

        # Periodic cleanup to prevent memory growth
        # Triggers on either: 100 requests OR 60 seconds (whichever comes first)
        self._fallback_cleanup_counter += 1
        time_since_last_cleanup = current_time - self._fallback_last_cleanup_time
        should_cleanup = (
            self._fallback_cleanup_counter >= self._fallback_cleanup_interval
            or time_since_last_cleanup >= self._fallback_cleanup_time_interval
        )
        if should_cleanup:
            self._cleanup_fallback_storage(window_seconds)
            self._fallback_cleanup_counter = 0
            self._fallback_last_cleanup_time = current_time

        if key in self._fallback_storage:
            count, window_start = self._fallback_storage[key]

            # Check if window has expired
            if current_time - window_start > window_seconds:
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
        method = scope.get("method", "GET")

        # Exempt health checks and auth status from rate limiting
        if path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Lightweight session status polling (GET /sessions/{id}/status) - high frequency, low payload
        if method == "GET" and path.endswith("/status") and "/sessions/" in path:
            await self.app(scope, receive, send)
            return

        # SSE endpoints (POST /sessions for session list, POST /sessions/{id}/chat)
        # are long-lived streaming connections — exempt from rate limiting
        if method == "POST" and (path == "/api/v1/sessions" or "/chat" in path):
            await self.app(scope, receive, send)
            return

        # Determine rate limit based on path
        if path in self.AUTH_PATHS:
            max_requests = settings.rate_limit_auth_requests_per_minute
        else:
            max_requests = settings.rate_limit_requests_per_minute

        # Get client identifier (IP or user ID from token)
        client_id = request.client.host if request.client else "unknown"
        # Use method + normalized path for granular buckets
        # Strip session IDs to group per-endpoint (e.g., GET /sessions/* → one bucket)
        parts = path.split("/")
        if len(parts) > 4:
            # Normalize: /api/v1/sessions/{id}/action → sessions:action
            bucket = f"{parts[3]}:{parts[-1]}"
        elif len(parts) > 3:
            bucket = parts[3]
        else:
            bucket = "default"
        key = f"rate_limit:{client_id}:{method}:{bucket}"

        rate_limit_exceeded = False
        using_fallback = False
        window_seconds = max(1, settings.rate_limit_window_seconds)
        retry_after_seconds = window_seconds

        try:
            # Atomically increment counter and preserve TTL window.
            # Context7/Redis docs recommend this pattern to avoid INCR/EXPIRE race windows.
            current, ttl = await self._increment_window_counter(key, window_seconds)

            # Check if rate limit exceeded
            if current > max_requests:
                rate_limit_exceeded = True
                retry_after_seconds = max(1, ttl)

        except Exception as e:
            # SECURITY FIX: Fall back to in-memory rate limiting instead of allowing all requests
            logger.warning(f"Redis unavailable for rate limiting, using in-memory fallback: {e}")
            using_fallback = True
            try:
                from app.core.prometheus_metrics import rate_limit_fallback_total

                rate_limit_fallback_total.inc({"reason": "redis_unavailable"})
            except Exception:
                logger.debug("Failed to emit rate-limit fallback metric", exc_info=True)

            is_allowed, current = self._fallback_rate_limit(key, max_requests, window_seconds)
            if not is_allowed:
                rate_limit_exceeded = True
                # In-memory: estimate remaining from window
                if key in self._fallback_storage:
                    _, window_start = self._fallback_storage[key]
                    retry_after_seconds = max(1, int(window_seconds - (time.time() - window_start)))

        if rate_limit_exceeded:
            logger.warning(
                f"Rate limit exceeded for {client_id} on {path}{' (fallback mode)' if using_fallback else ''}"
            )
            response = JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Too many requests. Retry after {retry_after_seconds} seconds.",
                        "retry_after": retry_after_seconds,
                    },
                },
                headers={"Retry-After": str(retry_after_seconds)},
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

        # Wire domain metrics port to Prometheus-backed counters/histograms
        from app.infrastructure.observability.metrics_port_adapter import configure_domain_metrics_adapter

        configure_domain_metrics_adapter()

        logger.info("Observability components initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize observability: {e}")


# Health check state
_health_state = {
    "mongodb": False,
    "redis": False,
    "redis_cache": False,
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

        # Initialize typo correction analytics/feedback store
        from app.infrastructure.observability.typo_correction_analytics import (
            get_typo_correction_analytics,
        )

        get_typo_correction_analytics()

        # Initialize MongoDB and Beanie
        await get_mongodb().initialize()
        _health_state["mongodb"] = True

        # Initialize Beanie
        await init_beanie(
            database=get_mongodb().client[settings.mongodb_database],
            document_models=[
                AgentDocument,
                CanvasProjectDocument,
                CanvasVersionDocument,
                ConnectorDocument,
                RatingDocument,
                ScreenshotDocument,
                SessionDocument,
                SkillDocument,
                SnapshotDocument,
                UserConnectorDocument,
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

        # Seed official connectors
        try:
            from app.infrastructure.seeds.connectors_seed import seed_connectors

            connector_count = await seed_connectors()
            logger.info(f"Seeded {connector_count} official connectors")
        except Exception as e:
            logger.warning(f"Failed to seed connectors (non-critical): {e}")

        # Cleanup stale running sessions from previous crashes/restarts
        periodic_cleanup_task = None
        try:
            from app.application.services.maintenance_service import MaintenanceService

            db = get_mongodb().client[settings.mongodb_database]
            maintenance_service = MaintenanceService(db)
            cleanup_result = await maintenance_service.cleanup_stale_running_sessions(
                stale_threshold_minutes=settings.stale_session_startup_threshold_minutes,
                dry_run=False,
            )
            if cleanup_result["sessions_cleaned"] > 0:
                logger.info(f"Cleaned up {cleanup_result['sessions_cleaned']} stale sessions from previous run")

            periodic_cleanup_task = asyncio.create_task(
                _run_periodic_session_cleanup(
                    maintenance_service,
                    interval_seconds=settings.stale_session_cleanup_interval_seconds,
                    stale_threshold_minutes=settings.stale_session_threshold_minutes,
                ),
            )
            logger.info("Periodic session cleanup background task started")
        except Exception as e:
            logger.warning(f"Stale session cleanup failed (non-critical): {e}")

        # Initialize MinIO (required for screenshot storage + optional file storage)
        try:
            from app.infrastructure.storage.minio_storage import get_minio_storage

            await get_minio_storage().initialize()
            _health_state["minio"] = True
            logger.info("MinIO storage initialized")
        except Exception as e:
            logger.warning("MinIO initialization failed (graceful degradation): %s", e)
            _health_state["minio"] = False

        # Initialize Redis
        await get_redis().initialize()
        _health_state["redis"] = True
        cache_redis = get_cache_redis()
        if cache_redis is not None:
            try:
                await cache_redis.initialize()
                _health_state["redis_cache"] = True
            except Exception as e:
                logger.warning("Cache Redis initialization failed (graceful degradation): %s", e)
                _health_state["redis_cache"] = False
        else:
            _health_state["redis_cache"] = False

        # Initialize Qdrant (optional, graceful degradation if unavailable)
        try:
            await get_qdrant().initialize()
            _health_state["qdrant"] = True

            # Connect Qdrant to domain layer for vector memory operations
            from app.domain.repositories.vector_memory_repository import set_vector_memory_repository
            from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository

            qdrant_repo = QdrantMemoryRepository()
            set_vector_memory_repository(qdrant_repo)

            # Wire task artifact, tool log repos, and embedding provider
            from app.domain.repositories.vector_repos import (
                set_embedding_provider,
                set_task_artifact_repository,
                set_tool_log_repository,
            )
            from app.infrastructure.external.embedding.client import get_embedding_client
            from app.infrastructure.repositories.qdrant_task_repository import QdrantTaskRepository
            from app.infrastructure.repositories.qdrant_tool_log_repository import QdrantToolLogRepository

            set_task_artifact_repository(QdrantTaskRepository())
            set_tool_log_repository(QdrantToolLogRepository())
            try:
                set_embedding_provider(get_embedding_client())
            except RuntimeError:
                logger.warning("No embedding API key — embedding provider not set")
            logger.info("Vector memory repositories connected to Qdrant")
        except Exception as e:
            logger.warning(f"Qdrant initialization failed (graceful degradation): {e}")
            _health_state["qdrant"] = False

        # Initialize BM25 encoder from existing memories (for hybrid search)
        try:
            from app.domain.services.embeddings.bm25_encoder import initialize_bm25_from_memories
            from app.infrastructure.repositories.mongo_memory_repository import MongoMemoryRepository

            db = get_mongodb().client[settings.mongodb_database]
            memory_repo = MongoMemoryRepository(database=db)
            logger.info("Initializing BM25 encoder from stored memories...")
            await initialize_bm25_from_memories(memory_repo)
        except Exception as e:
            logger.warning(f"BM25 encoder initialization failed (non-critical): {e}")

        # Initialize Sandbox Pool (Phase 3: Pre-warming) if enabled.
        # In static dev sandbox mode (SANDBOX_ADDRESS configured), pooling can
        # create contention against shared CDP endpoints across sessions.
        logger.info("Sandbox lifecycle mode: %s", settings.sandbox_lifecycle_mode)
        sandbox_pool_enabled = (
            settings.sandbox_pool_enabled
            and not settings.uses_static_sandbox_addresses
            and settings.sandbox_lifecycle_mode != "ephemeral"
        )
        if sandbox_pool_enabled:
            try:
                from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                await start_sandbox_pool(DockerSandbox)
                _health_state["sandbox_pool"] = True
                logger.info("Sandbox pool initialized and warming")
            except Exception as e:
                logger.warning(f"Sandbox pool initialization failed (graceful degradation): {e}")
                _health_state["sandbox_pool"] = False
        else:
            if settings.sandbox_pool_enabled and settings.uses_static_sandbox_addresses:
                logger.info("Sandbox pool disabled: static SANDBOX_ADDRESS mode uses direct sandbox allocation")
            elif settings.sandbox_pool_enabled and settings.sandbox_lifecycle_mode == "ephemeral":
                logger.info("Sandbox pool disabled: ephemeral sandbox lifecycle requires per-session containers")
            else:
                logger.info("Sandbox pool disabled by configuration")

        # Initialize enhanced system components
        await system_integrator.initialize()
        logger.info("Enhanced system components initialized")

        # Mark as ready
        _health_state["ready"] = True
        logger.info("Application startup complete - all services initialized")

        # Phase 2: Start sync worker for MongoDB → Qdrant outbox processing
        if _health_state["qdrant"]:
            try:
                from app.domain.services.sync_worker import start_sync_worker

                await start_sync_worker()
                logger.info("Sync worker started for MongoDB → Qdrant synchronization")
            except Exception as e:
                logger.warning(f"Sync worker startup failed (non-critical): {e}")

        # Phase 2: Start reconciliation job background task
        reconciliation_task = None
        if _health_state["qdrant"]:

            async def _reconciliation_loop():
                """Periodic reconciliation -- runs every 5 minutes."""
                # Wait 1 minute before first run to let system stabilize
                await asyncio.sleep(60)
                while True:
                    try:
                        from app.domain.services.reconciliation_job import run_reconciliation

                        stats = await run_reconciliation()
                        if stats.get("failed_retried", 0) > 0 or stats.get("missing_vectors_found", 0) > 0:
                            logger.info(f"Reconciliation completed: {stats}")
                        else:
                            logger.debug(f"Reconciliation completed: {stats}")
                    except Exception as e:
                        logger.debug(f"Reconciliation failed (non-critical): {e}")
                    await asyncio.sleep(300)  # Every 5 minutes

            reconciliation_task = asyncio.create_task(_reconciliation_loop())
            logger.info("Reconciliation background task started")

        # Start background memory cleanup task (Phase 7)
        memory_cleanup_task = None
        if _health_state["qdrant"]:

            async def _memory_cleanup_loop():
                """Periodic memory maintenance -- runs every hour."""
                while True:
                    await asyncio.sleep(3600)  # Every hour
                    try:
                        from app.interfaces.dependencies import get_memory_service

                        memory_service = get_memory_service()
                        if memory_service:
                            await memory_service.cleanup(remove_expired=True, consolidate=False)
                            logger.debug("Memory cleanup cycle completed")
                    except Exception as e:
                        logger.debug(f"Memory cleanup failed (non-critical): {e}")

            memory_cleanup_task = asyncio.create_task(_memory_cleanup_loop())
            logger.info("Memory cleanup background task started")

        try:
            yield
        finally:
            # Code executed on shutdown
            logger.info("Application shutdown - Pythinker AI Agent terminating")
            _health_state["ready"] = False

            # Phase 2: Stop sync worker
            if _health_state["qdrant"]:
                try:
                    from app.domain.services.sync_worker import stop_sync_worker

                    await stop_sync_worker()
                    logger.info("Sync worker stopped")
                except Exception as e:
                    logger.debug(f"Sync worker shutdown error: {e}")

            # Cancel reconciliation task
            if reconciliation_task is not None:
                reconciliation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await reconciliation_task

            # Cancel periodic session cleanup task
            if periodic_cleanup_task is not None:
                periodic_cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await periodic_cleanup_task

            # Cancel memory cleanup task
            if memory_cleanup_task is not None:
                memory_cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await memory_cleanup_task

            # Shutdown sandbox pool first (Phase 3)
            sandbox_pool_enabled = (
                settings.sandbox_pool_enabled
                and not settings.uses_static_sandbox_addresses
                and settings.sandbox_lifecycle_mode != "ephemeral"
            )
            if sandbox_pool_enabled:
                try:
                    await asyncio.wait_for(stop_sandbox_pool(), timeout=90.0)
                    _health_state["sandbox_pool"] = False
                    logger.info("Sandbox pool shutdown completed")
                except TimeoutError:
                    logger.warning("Sandbox pool shutdown timed out after 90 seconds")
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

            # --- Application-level cleanup (requires DB connections) ---

            # Only shut down AgentService if it was actually created (lru_cache populated).
            # Without this guard, get_agent_service() creates a brand-new instance
            # (LLM, search, memory) just to immediately shut it down on hot-reload.
            if get_agent_service.cache_info().currsize > 0:
                logger.info("Cleaning up AgentService instance")
                try:
                    await asyncio.wait_for(get_agent_service().shutdown(), timeout=90.0)
                    logger.info("AgentService shutdown completed successfully")
                except TimeoutError:
                    logger.warning(
                        "AgentService shutdown timed out after 90 seconds - some tasks may not have completed gracefully"
                    )
                except Exception as e:
                    logger.error(f"Error during AgentService cleanup: {e!s}")
            else:
                logger.info("AgentService was never created, skipping shutdown")

            # Destroy orphaned sandbox containers from active sessions
            # (catches sandboxes missed by task registry cleanup)
            try:
                from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                db = get_mongodb().client[settings.mongodb_database]
                active_sessions = db.sessions.find(
                    {"sandbox_id": {"$ne": None}, "status": {"$in": ["running", "initializing"]}},
                    {"_id": 1, "sandbox_id": 1},
                )
                destroyed = 0
                async for session in active_sessions:
                    sandbox_id = session.get("sandbox_id")
                    if sandbox_id:
                        try:
                            sandbox = await DockerSandbox.get(sandbox_id)
                            if sandbox:
                                await asyncio.wait_for(sandbox.destroy(), timeout=10.0)
                                destroyed += 1
                        except TimeoutError:
                            logger.warning(f"Orphaned sandbox {sandbox_id} destroy timed out")
                        except Exception as e:
                            logger.debug(f"Orphaned sandbox {sandbox_id} cleanup failed: {e}")
                if destroyed > 0:
                    logger.info(f"Destroyed {destroyed} orphaned sandbox containers on shutdown")
            except Exception as e:
                logger.warning(f"Orphaned sandbox cleanup failed (non-critical): {e}")

            # Close shared HTTP session (browser tool connection pool)
            try:
                from app.domain.services.tools.browser import close_http_session

                await close_http_session()
            except Exception as e:
                logger.debug(f"HTTP session cleanup error: {e}")

            # Close all HTTPClientPool connections (Phase 1: Connection pooling)
            try:
                from app.infrastructure.external.http_pool import HTTPClientPool

                count = await HTTPClientPool.close_all()
                if count > 0:
                    logger.info(f"Closed {count} HTTP client pool connections")
            except Exception as e:
                logger.debug(f"HTTPClientPool cleanup error: {e}")

            # --- Infrastructure disconnection (no more DB queries after this) ---

            # Disconnect from MinIO
            if _health_state.get("minio"):
                try:
                    from app.infrastructure.storage.minio_storage import get_minio_storage

                    await get_minio_storage().shutdown()
                    _health_state.pop("minio", None)
                except Exception as e:
                    logger.debug("MinIO shutdown error: %s", e)

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

            # Disconnect from cache Redis (if enabled)
            cache_redis = get_cache_redis()
            if cache_redis is not None:
                try:
                    await asyncio.wait_for(cache_redis.shutdown(), timeout=10.0)
                    _health_state["redis_cache"] = False
                except TimeoutError:
                    logger.warning("Cache Redis shutdown timed out")
                except Exception as e:
                    logger.error(f"Cache Redis shutdown error: {e}")

            # Disconnect from Qdrant
            try:
                await asyncio.wait_for(get_qdrant().shutdown(), timeout=10.0)
                _health_state["qdrant"] = False
            except TimeoutError:
                logger.warning("Qdrant shutdown timed out")
            except Exception as e:
                logger.debug(f"Qdrant shutdown error (may not have been initialized): {e}")

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

# Add security headers middleware (Context7 best practice - OWASP compliant)
from app.infrastructure.middleware.security_headers import add_security_headers_middleware  # noqa: E402

add_security_headers_middleware(app)

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
            "http://localhost:5174",
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
