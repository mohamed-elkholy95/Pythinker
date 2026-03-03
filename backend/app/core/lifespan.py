import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

from beanie import init_beanie
from fastapi import FastAPI

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
from app.infrastructure.models.prompt_optimization_documents import (
    OptimizationRunDocument,
    PromptProfileDocument,
)
from app.infrastructure.repositories.event_store_repository import AgentEventDocument
from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.storage.qdrant import get_qdrant
from app.infrastructure.storage.redis import get_cache_redis, get_redis
from app.infrastructure.structured_logging import get_logger
from app.interfaces.dependencies import get_agent_service

logger = get_logger(__name__)
settings = get_settings()

BEANIE_DOCUMENT_MODELS = [
    AgentDocument,
    AgentEventDocument,
    CanvasProjectDocument,
    CanvasVersionDocument,
    ConnectorDocument,
    OptimizationRunDocument,
    PromptProfileDocument,
    RatingDocument,
    ScreenshotDocument,
    SessionDocument,
    SkillDocument,
    SnapshotDocument,
    UserConnectorDocument,
    UserDocument,
    UsageDocument,
    DailyUsageDocument,
]

# Health check state
_health_state = {
    "mongodb": False,
    "redis": False,
    "redis_cache": False,
    "qdrant": False,
    "minio": False,
    "sandbox_pool": False,
    "ready": False,
}
_STARTUP_SINGLETON_TTL_SECONDS = 6 * 60 * 60


def get_health_state() -> dict:
    """Get current health state for health check endpoint"""
    return _health_state.copy()


async def _try_acquire_leader_lock(lock_name: str, ttl_seconds: int) -> bool:
    """Try to acquire a distributed leader lock via Redis SET NX EX.

    With multiple uvicorn workers each running their own lifespan, this
    prevents duplicate execution of periodic background jobs.  The lock
    auto-expires after ``ttl_seconds`` so a crashed worker doesn't hold
    the lock forever.

    Returns True if this worker acquired the lock, False otherwise.
    """
    ttl_seconds = max(ttl_seconds, 5)  # floor at 5s for test/edge cases
    try:
        redis = get_redis()
        if redis.client is None:
            return True  # Redis not initialised yet — allow execution
        result = await redis.call("set", f"leader:{lock_name}", "1", "NX", "EX", ttl_seconds, max_retries=0)
        return result is not None  # SET NX returns None when key already exists
    except Exception:
        # Redis down → allow execution (graceful degradation)
        return True


async def _try_acquire_startup_singleton(task_name: str, ttl_seconds: int = _STARTUP_SINGLETON_TTL_SECONDS) -> bool:
    """Acquire a startup-only singleton lock for long-running background tasks."""
    acquired = await _try_acquire_leader_lock(f"startup:{task_name}", ttl_seconds=ttl_seconds)
    if not acquired:
        logger.info("Skipping startup task '%s' on this worker (already started elsewhere)", task_name)
    return acquired


async def _run_periodic_session_cleanup(
    maintenance_service: MaintenanceService,
    interval_seconds: float = 300.0,
    stale_threshold_minutes: int = 30,
) -> None:
    """Background task: clean up stale sessions on a fixed interval."""
    while True:
        await asyncio.sleep(interval_seconds)
        if not await _try_acquire_leader_lock("session_cleanup", ttl_seconds=int(interval_seconds) - 5):
            continue
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


async def _run_periodic_event_archival(
    interval_seconds: float = 86400.0,  # Daily
) -> None:
    """Background task: archive old agent_events to cold collection."""
    # Wait 5 minutes before first run to let system stabilize
    await asyncio.sleep(300)
    while True:
        if not await _try_acquire_leader_lock("event_archival", ttl_seconds=int(interval_seconds) - 5):
            await asyncio.sleep(interval_seconds)
            continue
        try:
            from app.core.prometheus_metrics import event_store_archival_runs
            from app.infrastructure.repositories.event_store_repository import EventStoreRepository

            db = get_mongodb().client[settings.mongodb_database]
            event_repo = EventStoreRepository(db_client=db)
            cutoff = datetime.now(UTC) - timedelta(days=settings.mongodb_event_retention_days)
            archived = await event_repo.archive_events_before(cutoff)
            event_store_archival_runs.inc(labels={"status": "success"})
            if archived > 0:
                logger.info("Periodic event archival: %d events archived", archived)
        except Exception as e:
            from app.core.prometheus_metrics import event_store_archival_runs

            event_store_archival_runs.inc(labels={"status": "error"})
            error_text = str(e).strip() or repr(e)
            logger.warning(
                "Periodic event archival failed (%s): %s",
                type(e).__name__,
                error_text,
                exc_info=True,
            )
        await asyncio.sleep(interval_seconds)


def _initialize_observability() -> None:
    """Initialize observability components (OTEL, metrics, tracer)."""
    try:
        # Configure OTEL if enabled
        otel_active = False
        if settings.otel_enabled and settings.otel_endpoint:
            from app.infrastructure.observability.otel_exporter import configure_otel

            otel_active = configure_otel(
                endpoint=settings.otel_endpoint,
                service_name=settings.otel_service_name,
                insecure=settings.otel_insecure,
            )

        # Auto-instrument httpx and FastAPI when OTEL is active
        if otel_active:
            _setup_otel_auto_instrumentation()

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


def _setup_otel_auto_instrumentation() -> None:
    """Activate OpenTelemetry auto-instrumentation for httpx and FastAPI.

    Each instrumentor is independently guarded so a missing package
    never blocks the others.
    """
    # httpx — traces all outbound HTTP calls (LLM, search, embeddings)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.info("OTEL auto-instrumented: httpx")
    except Exception as exc:
        logger.debug("OTEL httpx instrumentation skipped: %s", exc)

    # FastAPI — traces all inbound HTTP requests
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
        logger.info("OTEL auto-instrumented: FastAPI")
    except Exception as exc:
        logger.debug("OTEL FastAPI instrumentation skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code executed on startup
    logger.info("Application startup - Pythinker AI Agent initializing")
    logger.info(f"Environment: {settings.environment}")

    # Initialize enhanced error handling and monitoring
    from app.core.system_integrator import get_system_integrator

    system_integrator = get_system_integrator()

    # Declare background task handles before try block to prevent NameError
    # in the finally/shutdown block if startup fails partway through.
    periodic_cleanup_task = None
    reconciliation_task = None
    memory_cleanup_task = None
    event_archival_task = None
    mongo_profiler_task = None
    sync_worker_started = False

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
            document_models=BEANIE_DOCUMENT_MODELS,
        )
        logger.info("Successfully initialized Beanie")

        # Seed official skills
        try:
            from app.infrastructure.seeds.skills_seed import seed_official_skills

            skill_count = await seed_official_skills()
            logger.info(f"Seeded {skill_count} official skills")
        except Exception as e:
            logger.warning(f"Failed to seed skills (non-critical): {e}")

        # Load pip-installed skill plugins (AgentSkills entry-point discovery)
        try:
            from app.infrastructure.plugins.skill_plugin_loader import load_skill_plugins

            plugin_count = await load_skill_plugins()
            if plugin_count > 0:
                logger.info(f"Loaded {plugin_count} skill plugin(s) via entry-points")
        except Exception as e:
            logger.warning(f"Failed to load skill plugins (non-critical): {e}")

        # Seed official connectors
        try:
            from app.infrastructure.seeds.connectors_seed import seed_connectors

            connector_count = await seed_connectors()
            logger.info(f"Seeded {connector_count} official connectors")
        except Exception as e:
            logger.warning(f"Failed to seed connectors (non-critical): {e}")

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

        # Cleanup stale running sessions from previous crashes/restarts.
        # On startup, ANY session still marked RUNNING is orphaned — the backend
        # just (re)started so no in-memory task can be alive.  Use threshold=0
        # to catch sessions from hot-reloads that are only seconds old.
        try:
            from app.application.services.maintenance_service import MaintenanceService

            db = get_mongodb().client[settings.mongodb_database]
            maintenance_service = MaintenanceService(db)

            if await _try_acquire_startup_singleton("stale_session_cleanup", ttl_seconds=600):
                cleanup_result = await maintenance_service.cleanup_stale_running_sessions(
                    stale_threshold_minutes=0,
                    dry_run=False,
                )
                if cleanup_result["sessions_cleaned"] > 0:
                    logger.info(
                        "Startup: cleaned %d orphaned RUNNING sessions (threshold=0 min)",
                        cleanup_result["sessions_cleaned"],
                    )

            if await _try_acquire_startup_singleton("periodic_session_cleanup_loop"):
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

        # Eagerly create memory indexes to avoid first-request latency spike.
        # Without this, ensure_indexes() fires lazily on the first memory write
        # (create/search), adding ~50-200ms to the initial session's processing.
        try:
            from app.infrastructure.repositories.mongo_memory_repository import MongoMemoryRepository

            db = get_mongodb().client[settings.mongodb_database]
            memory_repo = MongoMemoryRepository(database=db)
            await memory_repo.ensure_indexes()
            logger.info("Memory repository indexes pre-created at startup")
        except Exception as e:
            logger.warning(f"Memory index pre-creation failed (will retry on first use): {e}")

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

        # Initialize knowledge base storage directory
        if settings.knowledge_base_enabled:
            import os as _os

            _os.makedirs(settings.knowledge_base_storage_dir, exist_ok=True)
            logger.info("Knowledge base storage ready: %s", settings.knowledge_base_storage_dir)

        # Mark as ready
        _health_state["ready"] = True
        logger.info("Application startup complete - all services initialized")

        # Wire domain-layer agent metrics to Prometheus infrastructure
        try:
            from app.infrastructure.observability.agent_metrics_adapter import configure_agent_metrics

            configure_agent_metrics()
        except Exception as e:
            logger.warning(f"Agent metrics adapter configuration failed (non-critical): {e}")

        # Phase 2: Start sync worker for MongoDB → Qdrant outbox processing
        if _health_state["qdrant"] and await _try_acquire_startup_singleton("sync_worker"):
            try:
                from app.domain.services.sync_worker import SyncWorker, set_sync_worker, start_sync_worker
                from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
                from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository

                set_sync_worker(
                    SyncWorker(
                        outbox_repo=SyncOutboxRepository(),
                        qdrant_repo=QdrantMemoryRepository(),
                    )
                )
                await start_sync_worker()
                sync_worker_started = True
                logger.info("Sync worker started for MongoDB → Qdrant synchronization")
            except Exception as e:
                logger.warning(f"Sync worker startup failed (non-critical): {e}")

        # Phase 2: Start reconciliation job background task
        if _health_state["qdrant"]:
            try:
                from app.domain.services.reconciliation_job import ReconciliationJob, set_reconciliation_job
                from app.infrastructure.repositories.mongo_memories_collection import MongoMemoriesCollection
                from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
                from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository

                set_reconciliation_job(
                    ReconciliationJob(
                        outbox_repo=SyncOutboxRepository(),
                        qdrant_repo=QdrantMemoryRepository(),
                        memories_collection=MongoMemoriesCollection(),
                    )
                )
            except Exception as e:
                logger.warning(f"Reconciliation job initialization failed (non-critical): {e}")

            async def _reconciliation_loop():
                """Periodic reconciliation -- runs every 5 minutes."""
                # Wait 1 minute before first run to let system stabilize
                await asyncio.sleep(60)
                while True:
                    if not await _try_acquire_leader_lock("reconciliation", ttl_seconds=295):
                        await asyncio.sleep(300)
                        continue
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

            if await _try_acquire_startup_singleton("reconciliation_loop"):
                reconciliation_task = asyncio.create_task(_reconciliation_loop())
                logger.info("Reconciliation background task started")

        # Start background memory cleanup task (Phase 7 + Phase 6F context cleanup)
        if _health_state["qdrant"]:

            async def _memory_cleanup_loop():
                """Periodic memory maintenance -- runs every hour."""
                while True:
                    await asyncio.sleep(3600)  # Every hour
                    if not await _try_acquire_leader_lock("memory_cleanup", ttl_seconds=3595):
                        continue
                    try:
                        from app.interfaces.dependencies import get_memory_service

                        memory_service = get_memory_service()
                        if memory_service:
                            await memory_service.cleanup(remove_expired=True, consolidate=False)
                            logger.debug("Memory cleanup cycle completed")
                    except Exception as e:
                        logger.debug(f"Memory cleanup failed (non-critical): {e}")

                    # Phase 6F: Clean up old conversation context points
                    try:
                        from qdrant_client import models as qdrant_models

                        max_age_days = settings.qdrant_conversation_context_max_age_days
                        collection = settings.qdrant_conversation_context_collection
                        cutoff_ts = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
                        qdrant_client = get_qdrant().client
                        if qdrant_client:
                            result = await qdrant_client.delete(
                                collection_name=collection,
                                points_selector=qdrant_models.FilterSelector(
                                    filter=qdrant_models.Filter(
                                        must=[
                                            qdrant_models.FieldCondition(
                                                key="created_at",
                                                range=qdrant_models.Range(lt=cutoff_ts),
                                            ),
                                        ],
                                    ),
                                ),
                            )
                            logger.debug("Conversation context cleanup: %s", result)
                    except Exception as e:
                        logger.debug(f"Conversation context cleanup failed (non-critical): {e}")

            if await _try_acquire_startup_singleton("memory_cleanup_loop"):
                memory_cleanup_task = asyncio.create_task(_memory_cleanup_loop())
                logger.info("Memory cleanup background task started")

        # Start MongoDB slow query profiler (Phase 4B)
        if _health_state["mongodb"] and settings.mongodb_profiler_enabled:
            try:
                from app.infrastructure.middleware.mongo_profiler import start_mongo_profiler

                db = get_mongodb().client[settings.mongodb_database]
                mongo_profiler_task = await start_mongo_profiler(
                    db, threshold_ms=settings.mongodb_slow_query_threshold_ms
                )
            except Exception as e:
                logger.warning("MongoDB profiler startup failed (non-critical): %s", e)

        # Start event archival background task (Phase 1A: unbounded growth prevention)
        if _health_state["mongodb"] and await _try_acquire_startup_singleton("event_archival_loop"):
            event_archival_task = asyncio.create_task(_run_periodic_event_archival())
            logger.info(
                "Event archival background task started (retention: %d days)",
                settings.mongodb_event_retention_days,
            )

        try:
            yield
        finally:
            # Code executed on shutdown
            logger.info("Application shutdown - Pythinker AI Agent terminating")
            _health_state["ready"] = False

            # Phase 1.5: Drain active SSE streams before tearing down services
            try:
                from app.domain.services.stream_guard import drain_active_streams

                drained = await drain_active_streams(drain_timeout=5.0)
                if drained:
                    logger.info("Drained %d active SSE streams before shutdown", drained)
            except Exception as e:
                logger.warning("SSE stream drain failed (non-critical): %s", e)

            # Phase 2: Stop sync worker
            if _health_state["qdrant"] and sync_worker_started:
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

            # Cancel event archival task
            if event_archival_task is not None:
                event_archival_task.cancel()
                with suppress(asyncio.CancelledError):
                    await event_archival_task

            # Stop MongoDB profiler
            if mongo_profiler_task is not None:
                mongo_profiler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await mongo_profiler_task

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
