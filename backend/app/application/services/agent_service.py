import asyncio
import contextlib
import hashlib
import logging
import posixpath
import re
import shlex
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Optional

from app.application.errors.exceptions import NotFoundError
from app.application.schemas.file import FileViewResponse
from app.application.schemas.session import ShellViewResponse
from app.application.schemas.workspace import (
    GitRemoteSpec,
    WorkspaceManifest,
    WorkspaceManifestResponse,
    WorkspaceWriteError,
)
from app.application.services.session_lifecycle_service import SessionLifecycleService
from app.application.services.settings_service import get_settings_service
from app.application.services.usage_service import get_usage_service
from app.core import prometheus_metrics as pm
from app.core.config import get_settings
from app.core.sandbox_pool import get_sandbox_pool
from app.domain.exceptions.base import InvalidStateException, SecurityViolation
from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task
from app.domain.models.agent import Agent
from app.domain.models.event import AgentEvent, DoneEvent, ErrorEvent, MessageEvent, PlanningPhase, ProgressEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, ResearchMode, Session, SessionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agent_domain_service import AgentDomainService
from app.domain.services.browser_login_state_store import BrowserLoginStateStore
from app.domain.services.stream_guard import has_active_stream
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

# Set up logger
logger = logging.getLogger(__name__)


class AgentService:
    MAX_CREATE_SESSION_WAIT_SECONDS = 5.0
    CHAT_EVENT_TIMEOUT_SECONDS = 300.0  # Soft idle warning threshold between domain events.
    CHAT_EVENT_HARD_TIMEOUT_SECONDS = 1800.0  # Hard idle cutoff to prevent infinite hangs.
    CHAT_RESUME_MAX_SKIPPED_EVENTS = 1000  # Disable skip mode if resume cursor appears stale.
    CHAT_RESUME_MAX_SKIP_SECONDS = 60.0  # Balance stale-cursor fallback with slower backlog streams.
    CHAT_WARMUP_WAIT_SECONDS = 10.0
    CHAT_WAIT_BEACON_INTERVAL_SECONDS = 20.0  # Emit non-heartbeat wait progress during long-running operations.
    FILE_VIEW_CACHE_TTL_SECONDS = 2.0
    FILE_VIEW_CACHE_MAX_ENTRIES = 256

    def __init__(
        self,
        llm: LLM,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        sandbox_cls: type[Sandbox],
        task_cls: type[Task],
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        memory_service: Optional["MemoryService"] = None,
        mongodb_db: Any | None = None,  # MongoDB database for LangGraph checkpointing
    ):
        logger.info("Initializing AgentService")
        self._agent_repository = agent_repository
        self._session_repository = session_repository
        self._file_storage = file_storage
        self._agent_domain_service = AgentDomainService(
            self._agent_repository,
            self._session_repository,
            llm,
            sandbox_cls,
            task_cls,
            json_parser,
            file_storage,
            mcp_repository,
            search_engine,
            memory_service,
            mongodb_db,
            usage_recorder=self._record_usage,
        )
        self._session_lifecycle_service = SessionLifecycleService(
            self._session_repository,
            self._agent_domain_service,
        )
        self._llm = llm
        self._search_engine = search_engine
        self._sandbox_cls = sandbox_cls
        self._settings_service = get_settings_service()
        self._background_tasks: set[asyncio.Task] = set()
        self._sandbox_warm_locks: dict[str, asyncio.Lock] = {}
        self._sandbox_warm_tasks: dict[str, asyncio.Task] = {}
        self._session_cancel_events: dict[str, asyncio.Event] = {}
        self._file_view_cache: dict[str, tuple[float, FileViewResponse]] = {}
        self._file_view_inflight: dict[str, asyncio.Task[FileViewResponse]] = {}
        self._file_view_lock = asyncio.Lock()

    @staticmethod
    def _file_view_cache_key(session_id: str, user_id: str, file_path: str) -> str:
        return f"{session_id}:{user_id}:{file_path}"

    def _prune_file_view_cache_locked(self, now: float) -> None:
        expired_keys = [key for key, (expires_at, _) in self._file_view_cache.items() if expires_at <= now]
        for key in expired_keys:
            self._file_view_cache.pop(key, None)

        if len(self._file_view_cache) <= self.FILE_VIEW_CACHE_MAX_ENTRIES:
            return

        # Keep cache bounded by dropping the oldest-expiring entries first.
        overflow = len(self._file_view_cache) - self.FILE_VIEW_CACHE_MAX_ENTRIES
        for key, _entry in sorted(self._file_view_cache.items(), key=lambda item: item[1][0])[:overflow]:
            self._file_view_cache.pop(key, None)

    async def is_task_active(self, session_id: str) -> bool:
        """Check if session has an actively-running task via Redis liveness key.

        Returns True when the task runner is still heartbeating, which means
        the session is mid-execution (e.g. in summarization phase) even though
        session.status may already read 'completed' from the execution phase.
        """
        from app.infrastructure.external.task.redis_task import RedisStreamTask

        try:
            liveness = await RedisStreamTask.get_liveness(session_id)
            return liveness is not None
        except Exception:
            return False

    def request_cancellation(self, session_id: str) -> None:
        """Signal that a session's processing should stop (e.g. SSE disconnect)."""
        event = self._session_cancel_events.get(session_id)
        if event:
            event.set()
            logger.info("Cancellation requested for session %s", session_id)

    def _register_sandbox_warmup_task(self, session_id: str, task: asyncio.Task) -> None:
        """Track a warm-up task so it can be cancelled on stop/delete."""
        existing = self._sandbox_warm_tasks.get(session_id)
        if existing and not existing.done():
            existing.cancel()
        self._sandbox_warm_tasks[session_id] = task

        def _cleanup(_task: asyncio.Task) -> None:
            current = self._sandbox_warm_tasks.get(session_id)
            if current is _task:
                self._sandbox_warm_tasks.pop(session_id, None)

        task.add_done_callback(_cleanup)

    async def _cancel_sandbox_warmup_task(self, session_id: str) -> None:
        """Cancel any in-flight sandbox warm-up task for a session."""
        task = self._sandbox_warm_tasks.pop(session_id, None)
        if not task or task.done():
            return

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _clamp_create_session_wait_seconds(self, requested_seconds: float) -> float:
        """Clamp user-provided warm-up wait to a bounded latency budget."""
        wait_seconds = max(0.0, requested_seconds)
        bounded_seconds = min(wait_seconds, self.MAX_CREATE_SESSION_WAIT_SECONDS)
        if bounded_seconds != wait_seconds:
            logger.info(
                "Clamped sandbox wait budget from %.2fs to %.2fs",
                wait_seconds,
                bounded_seconds,
            )
        return bounded_seconds

    async def _record_usage(self, user_id: str, session_id: str) -> None:
        """Record tool call usage via the application usage service."""
        usage_service = get_usage_service()
        await usage_service.record_tool_call(user_id=user_id, session_id=session_id)

    async def create_session(
        self,
        user_id: str,
        source: str = "web",
        mode: AgentMode = AgentMode.AGENT,
        research_mode: ResearchMode | None = None,
        initial_message: str | None = None,
        require_fresh_sandbox: bool = True,
        sandbox_wait_seconds: float = 3.0,
        idempotency_key: str | None = None,
    ) -> Session:
        # Idempotency guard — if a key is provided, check for a prior session.
        # Stored in Redis with a 60-second TTL; callers should pass the
        # X-Idempotency-Key header value here.
        if idempotency_key:
            from app.infrastructure.external.cache import get_cache

            _cache = get_cache()
            _cache_key = f"idempotency:session:{user_id}:{idempotency_key}"
            existing_session_id = await _cache.get(_cache_key)
            if existing_session_id:
                logger.info(f"Idempotency hit: returning existing session {existing_session_id}")
                existing = await self._session_repository.find_by_id(existing_session_id)
                if existing:
                    return existing

        started_at = time.perf_counter()
        logger.info(f"Creating new session for user: {user_id} with mode: {mode}")

        # Auto-stop any stale running sessions to release sandbox/browser resources
        await self._cleanup_stale_sessions(user_id)

        # Phase 4 P0: Intent classification for simple queries
        if initial_message and mode == AgentMode.AGENT:
            from app.core.prometheus_metrics import intent_classification_total
            from app.domain.services.agents.intent_classifier import get_intent_classifier

            classifier = get_intent_classifier()
            intent, recommended_mode, confidence = classifier.classify(initial_message)

            logger.info(
                "Intent classification",
                extra={
                    "message_preview": initial_message[:50],
                    "detected_intent": intent,
                    "recommended_mode": recommended_mode.value,
                    "confidence": confidence,
                    "original_mode": mode.value,
                },
            )

            # Record metric
            intent_classification_total.inc(
                labels={
                    "detected_intent": intent,
                    "selected_mode": recommended_mode.value,
                }
            )

            # Override mode if classification confidence is high enough
            if confidence >= 0.75:
                mode = recommended_mode
                logger.info(f"Mode overridden by intent classification: {mode.value}")

        agent = await self._create_agent()
        effective_research_mode = research_mode or ResearchMode.DEEP_RESEARCH
        session = Session(
            agent_id=agent.id,
            user_id=user_id,
            source=source,
            mode=mode,
            research_mode=effective_research_mode,
        )
        settings = get_settings()
        session.sandbox_lifecycle_mode = getattr(settings, "sandbox_lifecycle_mode", "static")
        if require_fresh_sandbox:
            session.status = SessionStatus.INITIALIZING
        logger.info(f"Created new Session with ID: {session.id} for user: {user_id} with mode: {mode}")
        await self._session_repository.save(session)

        # Phase 2: Start sandbox creation in background for faster first chat
        if require_fresh_sandbox:
            task = asyncio.create_task(self._warm_sandbox_for_session(session.id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            self._register_sandbox_warmup_task(session.id, task)
            logger.info(f"Started background sandbox warm-up for session {session.id}")
            wait_budget_seconds = self._clamp_create_session_wait_seconds(sandbox_wait_seconds)
            try:
                if wait_budget_seconds > 0:
                    await asyncio.wait_for(asyncio.shield(task), timeout=wait_budget_seconds)
            except TimeoutError:
                logger.info(f"Sandbox warm-up still in progress for session {session.id}")
            except Exception as e:
                logger.warning(f"Sandbox warm-up failed for session {session.id}: {e}")
            updated = await self._session_repository.find_by_id(session.id)
            session_result = updated or session
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "create_session completed in %.2fms (session=%s status=%s require_fresh=%s wait_budget=%.2fs)",
                elapsed_ms,
                session_result.id,
                session_result.status,
                require_fresh_sandbox,
                wait_budget_seconds,
            )
            if idempotency_key:
                from app.infrastructure.external.cache import get_cache

                _cache = get_cache()
                await _cache.set(f"idempotency:session:{user_id}:{idempotency_key}", session_result.id, ttl=60)
            return session_result

        if settings.sandbox_eager_init:
            task = asyncio.create_task(self._warm_sandbox_for_session(session.id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            self._register_sandbox_warmup_task(session.id, task)
            logger.info(f"Started background sandbox warm-up for session {session.id}")

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "create_session completed in %.2fms (session=%s status=%s require_fresh=%s)",
            elapsed_ms,
            session.id,
            session.status,
            require_fresh_sandbox,
        )
        if idempotency_key:
            from app.infrastructure.external.cache import get_cache

            _cache = get_cache()
            await _cache.set(f"idempotency:session:{user_id}:{idempotency_key}", session.id, ttl=60)
        return session

    async def _cleanup_stale_sessions(self, user_id: str) -> None:
        """Stop any stale sessions with active runtime state for this user.

        When a user starts a new task, any previously running sessions should be
        stopped to release sandbox and browser resources, preventing connection
        pool exhaustion (BROWSER_1004).

        Also closes browser connections for the sandbox CDP URL and unregisters
        sandbox ownership to ensure the browser is clean for the next session.
        """
        active_statuses = {SessionStatus.RUNNING, SessionStatus.INITIALIZING, SessionStatus.PENDING}
        try:
            stale_age_seconds = max(
                0.0,
                float(getattr(get_settings(), "stale_session_autostop_min_age_seconds", 30.0)),
            )
            stale_cutoff = datetime.now(UTC) - timedelta(seconds=stale_age_seconds)
            sessions = await self._session_repository.find_by_user_id(user_id)
            stale: list[Session] = []
            for session in sessions:
                if session.status not in active_statuses:
                    continue

                # Do not stop actively streaming sessions while user is still connected.
                if await has_active_stream(session_id=session.id, endpoint="chat"):
                    logger.info(
                        "Skipping auto-stop for session %s (status=%s): active chat stream detected",
                        session.id,
                        session.status,
                    )
                    continue

                # Avoid racing against newly-created/running sessions that are not stale yet.
                updated_at = session.updated_at
                if updated_at is not None:
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=UTC)
                    if updated_at >= stale_cutoff:
                        logger.debug(
                            "Skipping auto-stop for recent session %s (status=%s, updated_at=%s)",
                            session.id,
                            session.status,
                            updated_at.isoformat(),
                        )
                        continue

                stale.append(session)

            async def _stop_one(s: Session) -> None:
                """Stop a single stale session with a hard per-session cap."""
                try:
                    async with asyncio.timeout(10.0):
                        logger.info(
                            "Auto-stopping stale session %s (status=%s) for user %s",
                            s.id,
                            s.status,
                            user_id,
                        )
                        if s.sandbox_id:
                            await self._close_browser_for_sandbox(s.sandbox_id)
                        await self._agent_domain_service.stop_session(s.id)
                except TimeoutError:
                    logger.warning("Auto-stop of stale session %s timed out after 10s", s.id)
                except Exception as e:
                    logger.warning("Failed to auto-stop stale session %s: %s", s.id, e)

            # Stop all stale sessions in parallel with a total cap of 12 seconds
            # so that create_session never blocks on an unbounded cleanup phase.
            if stale:
                try:
                    async with asyncio.timeout(12.0):
                        await asyncio.gather(*[_stop_one(s) for s in stale])
                except TimeoutError:
                    logger.warning(
                        "Stale session cleanup exceeded 12s cap; %d session(s) may not have been fully stopped",
                        len(stale),
                    )
                logger.info("Cleaned up %d stale session(s) for user %s", len(stale), user_id)
        except Exception as e:
            logger.warning(f"Stale session cleanup failed for user {user_id}: {e}")

    async def _close_browser_for_sandbox(self, sandbox_id: str) -> None:
        """Close all browser connections for a sandbox to free the browser for reuse."""
        try:
            sandbox = await self._sandbox_cls.get(sandbox_id)
            if sandbox:
                cdp_url = f"http://{sandbox.ip}:9222"
                from app.infrastructure.external.browser.connection_pool import BrowserConnectionPool

                pool = BrowserConnectionPool.get_instance()
                closed = await pool.close_all_for_url(cdp_url)
                if closed:
                    logger.info(f"Closed {closed} browser connection(s) for sandbox {sandbox_id}")

                # Unregister sandbox ownership
                from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                # Extract address from sandbox_id (format: dev-sandbox-{address})
                if sandbox_id.startswith("dev-sandbox-"):
                    address = sandbox_id[len("dev-sandbox-") :]
                    await DockerSandbox.unregister_session(address)
        except Exception as e:
            logger.debug(f"Browser cleanup for sandbox {sandbox_id} failed (non-critical): {e}")

    async def _warm_sandbox_for_session(self, session_id: str) -> None:
        """Background task to pre-warm sandbox for session.

        Phase 2 optimization: Creates sandbox in background so it's ready
        when the user sends their first chat message.

        Phase 0 enhancement: Uses sandbox pool for instant allocation when enabled.
        Phase 1 enhancement: Pre-warms browser context for immediate use.
        """
        settings = get_settings()
        sandbox_lifecycle_mode = getattr(settings, "sandbox_lifecycle_mode", "static")
        ephemeral_lifecycle = sandbox_lifecycle_mode == "ephemeral"
        lock = self._sandbox_warm_locks.setdefault(session_id, asyncio.Lock())
        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )
        pool_enabled = (
            bool(getattr(settings, "sandbox_pool_enabled", False))
            and not uses_static_sandboxes
            and not ephemeral_lifecycle
        )

        async with lock:
            try:
                # Update session status to INITIALIZING
                await self._session_repository.update_status(session_id, SessionStatus.INITIALIZING)

                # Try to acquire from pool first (Phase 0: instant allocation)
                sandbox = None
                acquired_from_pool = False
                if pool_enabled:
                    try:
                        pool = await get_sandbox_pool(self._sandbox_cls)
                        if pool.is_started and pool.size > 0:
                            sandbox = await pool.acquire(timeout=5.0)
                            acquired_from_pool = True
                            logger.info(f"Acquired sandbox {sandbox.id} from pool for session {session_id}")
                    except Exception as e:
                        logger.warning(f"Pool acquisition failed, creating on-demand: {e}")
                elif uses_static_sandboxes and bool(getattr(settings, "sandbox_pool_enabled", False)):
                    logger.debug(
                        "Skipping sandbox pool for session %s because SANDBOX_ADDRESS is configured",
                        session_id,
                    )

                # Fall back to on-demand creation
                if not sandbox:
                    sandbox = await self._sandbox_cls.create()
                    logger.info(f"Created sandbox {sandbox.id} on-demand for session {session_id}")

                # Set up browser progress callback for retry event emission
                if hasattr(sandbox, "set_browser_progress_callback"):

                    async def browser_progress_callback(message: str) -> None:
                        """Emit browser connection retry progress as MessageEvent."""
                        from app.domain.models.event import MessageEvent

                        try:
                            event = MessageEvent(
                                session_id=session_id,
                                role="assistant",
                                message=message,
                            )
                            await self._session_repository.add_event(session_id, event)
                            logger.debug(f"Emitted browser progress event: {message}")
                        except Exception as e:
                            logger.warning(f"Failed to emit browser progress event: {e}")

                    sandbox.set_browser_progress_callback(browser_progress_callback)

                # Bind sandbox only if session still exists and is still unbound (or already points to this sandbox)
                session = await self._session_repository.find_by_id(session_id)
                if not session:
                    await self._destroy_unbound_sandbox(
                        sandbox,
                        session_id=session_id,
                        reason="session not found during sandbox warm-up",
                    )
                elif session.sandbox_id and session.sandbox_id != sandbox.id:
                    await self._destroy_unbound_sandbox(
                        sandbox,
                        session_id=session_id,
                        reason=f"session already bound to sandbox {session.sandbox_id}",
                    )
                else:
                    owns_sandbox = sandbox_lifecycle_mode == "ephemeral"
                    metadata_changed = False

                    if session.sandbox_id != sandbox.id:
                        session.sandbox_id = sandbox.id
                        metadata_changed = True

                    if session.sandbox_owned != owns_sandbox:
                        session.sandbox_owned = owns_sandbox
                        metadata_changed = True

                    if session.sandbox_lifecycle_mode != sandbox_lifecycle_mode:
                        session.sandbox_lifecycle_mode = sandbox_lifecycle_mode
                        metadata_changed = True

                    if owns_sandbox and session.sandbox_created_at is None:
                        session.sandbox_created_at = datetime.now(UTC)
                        metadata_changed = True
                    elif not owns_sandbox and session.sandbox_created_at is not None:
                        session.sandbox_created_at = None
                        metadata_changed = True

                    if metadata_changed:
                        await self._session_repository.save(session)

                    # Register sandbox ownership for contention prevention
                    if uses_static_sandboxes and sandbox.id.startswith("dev-sandbox-"):
                        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                        address = sandbox.id[len("dev-sandbox-") :]
                        previous_session = await DockerSandbox.register_session(address, session_id)
                        if previous_session is None:
                            # Could be first-time assignment (success) or blocked
                            is_owned = DockerSandbox._active_sessions.get(address) == session_id
                            if not is_owned:
                                # Fix 6: Wait for previous owner to release
                                wait_timeout = get_settings().sandbox_ownership_wait_timeout
                                logger.info(
                                    "Sandbox %s ownership blocked — waiting up to %.0fs",
                                    address,
                                    wait_timeout,
                                )
                                acquired = await DockerSandbox.wait_for_ownership(
                                    address, session_id, max_wait=wait_timeout
                                )
                                if not acquired:
                                    logger.warning(
                                        "Sandbox %s still owned after %.0fs — operating without sandbox",
                                        address,
                                        wait_timeout,
                                    )
                        elif previous_session:
                            logger.info(
                                f"Sandbox {address} was owned by session {previous_session}, "
                                f"now reassigned to {session_id}"
                            )

                    # Run ensure_sandbox for full health check (includes browser verification)
                    if hasattr(sandbox, "ensure_sandbox"):
                        await sandbox.ensure_sandbox()

                    # Pool sandboxes are already browser-prewarmed by the pool manager.
                    # Re-running prewarm here can race with first chat on the same CDP endpoint.
                    if acquired_from_pool:
                        logger.info(
                            f"Skipping redundant browser pre-warm for pooled sandbox {sandbox.id} "
                            f"(session {session_id})"
                        )
                    else:
                        # Non-pooled sandboxes: browser will be lazily initialized on first use
                        # Prewarming removed to eliminate redundancy - sandbox_pool handles prewarming for pooled sandboxes
                        logger.info(
                            f"Browser will be initialized on first use for non-pooled sandbox {sandbox.id} "
                            f"(session {session_id})"
                        )

                    logger.info(f"Sandbox {sandbox.id} fully ready with browser for session {session_id}")

                # Reset status to PENDING (ready for first chat)
                await self._session_repository.update_status(session_id, SessionStatus.PENDING)

            except Exception as e:
                logger.warning(f"Failed to pre-warm sandbox for session {session_id}: {e}")
                # Reset status to PENDING even on failure - first chat will create sandbox
                with contextlib.suppress(Exception):
                    await self._session_repository.update_status(session_id, SessionStatus.PENDING)

    async def _destroy_unbound_sandbox(self, sandbox: Sandbox, session_id: str, reason: str) -> None:
        """Destroy a sandbox that could not be bound to the session."""
        destroy = getattr(sandbox, "destroy", None)
        if not callable(destroy):
            logger.warning(f"Sandbox {getattr(sandbox, 'id', '<unknown>')} has no destroy() during cleanup")
            return

        try:
            result = destroy()
            if asyncio.iscoroutine(result):
                await result
            logger.info(
                f"Destroyed unbound sandbox {getattr(sandbox, 'id', '<unknown>')} for session {session_id}: {reason}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to destroy unbound sandbox {getattr(sandbox, 'id', '<unknown>')} "
                f"for session {session_id}: {reason}; error={e}"
            )

    async def _wait_for_sandbox_warmup_if_needed(self, session_id: str) -> None:
        """Wait briefly for background warm-up to finish to avoid CDP init races."""
        warm_lock = self._sandbox_warm_locks.get(session_id)
        if not warm_lock or not warm_lock.locked():
            return

        try:
            logger.info(
                "Waiting up to %.1fs for sandbox warm-up lock before chat (session %s)",
                self.CHAT_WARMUP_WAIT_SECONDS,
                session_id,
            )
            async with asyncio.timeout(self.CHAT_WARMUP_WAIT_SECONDS):
                async with warm_lock:
                    pass
            logger.info("Sandbox warm-up completed before chat (session %s)", session_id)
        except TimeoutError:
            # Do not fail chat; proceed and let downstream retries handle startup.
            logger.warning(
                "Sandbox warm-up still in progress after %.1fs; proceeding with chat (session %s)",
                self.CHAT_WARMUP_WAIT_SECONDS,
                session_id,
            )

    async def _create_agent(self) -> Agent:
        logger.info("Creating new agent")

        # Create Agent instance
        agent = Agent(
            model_name=self._llm.model_name,
            temperature=self._llm.temperature,
            max_tokens=self._llm.max_tokens,
        )
        logger.info(f"Created new Agent with ID: {agent.id}")

        # Save agent to repository
        await self._agent_repository.save(agent)
        logger.info(f"Saved agent {agent.id} to repository")

        logger.info(f"Agent created successfully with ID: {agent.id}")
        return agent

    async def chat(
        self,
        session_id: str,
        user_id: str,
        message: str | None = None,
        timestamp: datetime | None = None,
        event_id: str | None = None,
        attachments: list[dict] | None = None,
        skills: list[str] | None = None,
        thinking_mode: str | None = None,
        follow_up: dict | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        started_at = time.perf_counter()
        emitted_events = 0
        logger.info(f"Starting chat with session {session_id}: {(message or '')[:50]}...")

        # Extract follow_up fields early so they can be included in fast-path user events.
        follow_up_selected_suggestion: str | None = None
        follow_up_anchor_event_id: str | None = None
        follow_up_source: str | None = None
        if follow_up:
            follow_up_selected_suggestion = follow_up.get("selected_suggestion")
            follow_up_anchor_event_id = follow_up.get("anchor_event_id")
            follow_up_source = follow_up.get("source")

        # Lightweight direct-response bypass for trivial prompts (e.g., "hi", "thanks").
        # This intentionally avoids warm-up waits, connector loading, and full domain chat init.
        if message:
            try:
                direct_response = self._try_lightweight_direct_response(
                    message=message,
                    attachments=attachments,
                    skills=skills,
                    thinking_mode=thinking_mode,
                    follow_up=follow_up,
                )
                if direct_response:
                    async for event in self._emit_lightweight_direct_response(
                        session_id=session_id,
                        user_id=user_id,
                        message=message,
                        response=direct_response,
                        timestamp=timestamp,
                        follow_up_selected_suggestion=follow_up_selected_suggestion,
                        follow_up_anchor_event_id=follow_up_anchor_event_id,
                        follow_up_source=follow_up_source,
                    ):
                        emitted_events += 1
                        yield event
                    return
            except Exception as e:
                logger.warning(
                    "Lightweight direct-response bypass failed for session %s; falling back to full chat path: %s",
                    session_id,
                    e,
                )

        # Set correlation IDs for structured logging throughout the call chain
        try:
            from app.infrastructure.structured_logging import set_session_id, set_user_id

            set_session_id(session_id)
            set_user_id(user_id)
        except ImportError:
            pass  # Structured logging not available

        # Prevent first-chat overlap with active background warm-up for this session.
        await self._wait_for_sandbox_warmup_if_needed(session_id)

        # Load user's connected MCP server configs from connectors
        extra_mcp_configs: dict | None = None
        try:
            from app.application.services.connector_service import get_connector_service

            connector_service = get_connector_service()
            user_mcp_list = await connector_service.get_user_mcp_configs(user_id)
            if user_mcp_list:
                extra_mcp_configs = dict(user_mcp_list)
        except Exception as e:
            logger.warning(f"Failed to load user MCP connectors for {user_id}: {e}")

        # Resolve skill auto-trigger policy from persisted user settings, with env default fallback.
        auto_trigger_enabled = get_settings().skill_auto_trigger_enabled
        try:
            async with asyncio.timeout(0.25):
                auto_trigger_enabled = await self._settings_service.get_skill_auto_trigger_enabled(user_id)
        except Exception as e:
            logger.debug(
                "Falling back to environment skill auto-trigger policy for user %s: %s",
                user_id,
                e,
            )

        # Cancellation: Create cancel_event BEFORE domain service call so it can propagate
        # This allows SSE disconnect to stop domain layer processing (tools, LLM calls, etc.)
        cancel_event = asyncio.Event()
        self._session_cancel_events[session_id] = cancel_event
        logger.debug(
            "[DEBUG-SVC] new cancel_event registered session=%s event_obj=%s event_id=%s has_msg=%s",
            session_id,
            id(cancel_event),
            event_id,
            bool(message and message.strip()),
        )

        # Guard long stalls waiting for the next domain event.
        # We use a two-stage policy:
        # 1) soft timeout -> log warning and keep waiting (task may still be working),
        # 2) hard timeout -> emit timeout error and stop the stream.
        event_timeout_seconds = max(0.0, self.CHAT_EVENT_TIMEOUT_SECONDS)
        hard_timeout_seconds = max(0.0, self.CHAT_EVENT_HARD_TIMEOUT_SECONDS)
        event_stream = self._agent_domain_service.chat(
            session_id,
            user_id,
            message,
            timestamp,
            event_id,
            attachments,
            skills,
            extra_mcp_configs=extra_mcp_configs,
            auto_trigger_enabled=auto_trigger_enabled,
            thinking_mode=thinking_mode,
            follow_up_selected_suggestion=follow_up_selected_suggestion,
            follow_up_anchor_event_id=follow_up_anchor_event_id,
            follow_up_source=follow_up_source,
            cancel_event=cancel_event,  # NEW: Pass to domain layer for proper cancellation
        )
        stream_iter = event_stream.__aiter__()

        # Event resumption: skip events up to and including event_id
        # This enables page refresh to resume from the last received event
        skip_until_resume_point = bool(event_id)
        skipped_resume_events = 0
        resume_skip_started_at = time.monotonic() if skip_until_resume_point else None
        resume_state_recorded = False

        def _build_resume_gap_warning(
            reason: str,
            checkpoint_event_id: str | None = None,
            skip_elapsed_seconds: float = 0.0,
        ) -> ErrorEvent:
            return ErrorEvent(
                error="Reconnect gap detected. Resuming from the latest available event.",
                error_type="stream_gap",
                error_code="stream_gap_detected",
                error_category="transport",
                severity="warning",
                recoverable=True,
                can_resume=True,
                retry_hint="Reconnected successfully. Some previously streamed updates may be skipped or repeated.",
                checkpoint_event_id=checkpoint_event_id,
                details={
                    "session_id": session_id,
                    "resume_cursor": event_id,
                    "reason": reason,
                    "skipped_events": skipped_resume_events,
                    "skip_elapsed_seconds": round(skip_elapsed_seconds, 3),
                },
            )

        if event_id:
            logger.info(f"Event resumption enabled: skipping events until event_id={event_id}")

            # Validate cursor format: Redis stream IDs (e.g., "1771867510458-0")
            # cannot match UUID-format domain event IDs.  Detect the mismatch
            # early to avoid scanning 200 events before falling back.
            if re.match(r"^\d+-\d+$", event_id):
                logger.info(
                    "Resume cursor %s is a Redis stream ID; domain service will read from that position directly",
                    event_id,
                )
                skip_until_resume_point = False
                resume_state_recorded = True
                pm.record_sse_resume_cursor_state(endpoint="chat", state="redis_cursor")
                # No gap warning — domain service reads from this position; events flow normally
        else:
            resume_state_recorded = True
            pm.record_sse_resume_cursor_state(endpoint="chat", state="absent")

        cancel_task: asyncio.Task | None = None
        next_task: asyncio.Task | None = None
        last_event_at = time.monotonic()
        wait_beacon_interval_seconds = max(1.0, self.CHAT_WAIT_BEACON_INTERVAL_SECONDS)
        try:
            next_task = asyncio.create_task(stream_iter.__anext__())
            cancel_task = asyncio.create_task(cancel_event.wait())

            while True:
                # Race: next event vs cancellation (client disconnect).
                # asyncio.wait(timeout=...) returns done/pending and does NOT cancel pending tasks.
                done, _ = await asyncio.wait(
                    [next_task, cancel_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=min(event_timeout_seconds, wait_beacon_interval_seconds)
                    if event_timeout_seconds > 0
                    else wait_beacon_interval_seconds,
                )

                if not done:
                    idle_seconds = time.monotonic() - last_event_at
                    logger.debug(
                        "Chat stream idle for session %s: %.2fs without domain events; continuing to wait",
                        session_id,
                        idle_seconds,
                    )
                    if idle_seconds >= wait_beacon_interval_seconds:
                        emitted_events += 1
                        yield ProgressEvent(
                            phase=PlanningPhase.WAITING,
                            message="Still working on your request...",
                            progress_percent=None,
                            estimated_duration_seconds=round(idle_seconds),
                            wait_elapsed_seconds=round(idle_seconds),
                            wait_stage="execution_wait",
                        )
                    if hard_timeout_seconds > 0 and idle_seconds >= hard_timeout_seconds:
                        logger.warning(
                            "Chat stream hard timeout for session %s after %.2fs without progress",
                            session_id,
                            idle_seconds,
                        )
                        if next_task is not None and not next_task.done():
                            next_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await next_task
                        yield ErrorEvent(
                            error=f"Chat stream timed out after {hard_timeout_seconds:.1f}s without progress",
                            error_type="timeout",
                            recoverable=True,
                            retry_hint="Try again, or simplify the request.",
                            error_code="domain_stream_idle_hard_timeout",
                            error_category="timeout",
                            severity="warning",
                            retry_after_ms=5000,
                            can_resume=True,
                            details={
                                "session_id": session_id,
                                "idle_seconds": round(idle_seconds, 3),
                                "soft_timeout_seconds": event_timeout_seconds,
                                "hard_timeout_seconds": hard_timeout_seconds,
                            },
                        )
                        return
                    continue

                if cancel_task in done:
                    logger.debug(
                        "[DEBUG-SVC] CANCEL EVENT DETECTED session=%s event_obj=%s", session_id, id(cancel_event)
                    )
                    logger.info("Chat stream cancelled for session %s (client disconnected)", session_id)
                    if next_task is not None and not next_task.done():
                        next_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await next_task
                    return

                try:
                    event = next_task.result()
                except StopAsyncIteration:
                    if skip_until_resume_point and event_id:
                        skip_elapsed_seconds = (
                            time.monotonic() - resume_skip_started_at if resume_skip_started_at is not None else 0.0
                        )
                        if not resume_state_recorded:
                            pm.record_sse_resume_cursor_state(endpoint="chat", state="stale")
                            resume_state_recorded = True
                        pm.record_sse_resume_cursor_fallback(endpoint="chat", reason="stale_cursor")
                        emitted_events += 1
                        yield _build_resume_gap_warning(
                            reason="stale_cursor", skip_elapsed_seconds=skip_elapsed_seconds
                        )
                    elif event_id and not skip_until_resume_point and emitted_events == 0:
                        # Resume point was found but the stream ended immediately after —
                        # the client is fully caught up.  emitted_events == 0 ensures we
                        # only reach here when the cursor was the final event (all other
                        # resume paths emit at least one gap warning before StopAsyncIteration).
                        skip_elapsed_seconds = (
                            time.monotonic() - resume_skip_started_at if resume_skip_started_at is not None else 0.0
                        )
                        pm.record_sse_resume_cursor_state(endpoint="chat", state="found_at_end")
                        emitted_events += 1
                        yield _build_resume_gap_warning(
                            reason="stream_ended_at_cursor",
                            skip_elapsed_seconds=skip_elapsed_seconds,
                        )
                    break

                last_event_at = time.monotonic()
                next_task = asyncio.create_task(stream_iter.__anext__())

                # Event resumption: skip already-sent events
                if skip_until_resume_point:
                    current_event_id = getattr(event, "event_id", None) or getattr(event, "id", None)
                    if current_event_id:
                        if current_event_id == event_id:
                            # Found the resume point - start sending events AFTER this one
                            logger.info(f"Resume point found at event_id={event_id}, starting fresh event stream")
                            skip_until_resume_point = False
                            if not resume_state_recorded:
                                pm.record_sse_resume_cursor_state(endpoint="chat", state="found")
                                resume_state_recorded = True
                            continue  # Skip the resume-point event itself

                        skipped_resume_events += 1
                        skip_elapsed_seconds = (
                            time.monotonic() - resume_skip_started_at if resume_skip_started_at is not None else 0.0
                        )
                        if (
                            skipped_resume_events >= self.CHAT_RESUME_MAX_SKIPPED_EVENTS
                            or skip_elapsed_seconds >= self.CHAT_RESUME_MAX_SKIP_SECONDS
                        ):
                            # Stale/expired cursor: resume cursor was not found within the threshold.
                            # Notify the client with a gap warning so it can handle the discontinuity,
                            # then resume streaming from the current event.
                            logger.warning(
                                "Resume cursor %s not found for session %s after %d skipped events (%.2fs). "
                                "Disabling skip mode to preserve forward progress.",
                                event_id,
                                session_id,
                                skipped_resume_events,
                                skip_elapsed_seconds,
                            )
                            skip_until_resume_point = False
                            if not resume_state_recorded:
                                pm.record_sse_resume_cursor_state(endpoint="chat", state="stale")
                                resume_state_recorded = True
                            pm.record_sse_resume_cursor_fallback(endpoint="chat", reason="stale_cursor")
                            emitted_events += 1
                            yield _build_resume_gap_warning(
                                reason="stale_cursor",
                                checkpoint_event_id=str(current_event_id),
                                skip_elapsed_seconds=skip_elapsed_seconds,
                            )

                        if skip_until_resume_point:
                            continue  # Still searching — skip this event.
                    else:
                        # Event has no event_id. Cannot safely skip without risking an infinite
                        # loop; disable skip mode so this and all subsequent events are emitted.
                        logger.debug(
                            "Event without event_id during resumption: %s; disabling skip mode",
                            type(event).__name__,
                        )
                        skip_until_resume_point = False
                        if not resume_state_recorded:
                            pm.record_sse_resume_cursor_state(endpoint="chat", state="stale")
                            resume_state_recorded = True
                        pm.record_sse_resume_cursor_fallback(endpoint="chat", reason="missing_event_id")
                        emitted_events += 1
                        yield _build_resume_gap_warning(reason="missing_event_id")

                logger.debug(f"Received event: {event}")
                emitted_events += 1
                yield event
        finally:
            _current_evt = self._session_cancel_events.get(session_id)
            _is_mine = _current_evt is cancel_event if _current_evt else False
            logger.debug(
                "[DEBUG-SVC] chat:finally session=%s cancel_event_obj=%s current_in_map=%s is_mine=%s",
                session_id,
                id(cancel_event),
                id(_current_evt) if _current_evt else None,
                _is_mine,
            )
            # CRITICAL FIX: Only remove cancel_event if it's still OURS.
            # If a new chat() call already replaced it, don't clobber theirs.
            if self._session_cancel_events.get(session_id) is cancel_event:
                self._session_cancel_events.pop(session_id, None)
            else:
                logger.debug(
                    "[DEBUG-SVC] chat:finally SKIPPED pop - cancel_event was replaced by newer stream session=%s",
                    session_id,
                )
            if next_task is not None:
                if not next_task.done():
                    next_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await next_task
                # Retrieve result to suppress "Task exception was never retrieved"
                # (e.g. StopAsyncIteration when stream ends while cancel fires)
                # Note: CancelledError is BaseException (not Exception) in Python 3.8+
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    next_task.result()
            # Cancel the cancel_task to avoid "Task was destroyed but it is pending" on disconnect
            if cancel_task is not None and not cancel_task.done():
                cancel_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_task
            with contextlib.suppress(Exception):
                await stream_iter.aclose()

            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "Chat with session %s completed in %.2fms (events=%d)",
                session_id,
                elapsed_ms,
                emitted_events,
            )

    def _try_lightweight_direct_response(
        self,
        message: str,
        attachments: list[dict] | None,
        skills: list[str] | None,
        thinking_mode: str | None,
        follow_up: dict | None,
    ) -> str | None:
        """Return a deterministic direct response for tiny prompts, when safe."""
        # Only bypass for bare chat prompts. Any enriched context should go through full flow.
        if attachments or skills or thinking_mode or follow_up is not None:
            return None

        normalized = message.strip()
        if not normalized or len(normalized) > 120:
            return None

        import re

        from app.domain.services.agents.smart_router import SmartRouter

        # Match direct-response patterns first to avoid SmartRouter's ambiguity guard
        # suppressing short greetings like "hi".
        for pattern, response in SmartRouter.DIRECT_RESPONSE_PATTERNS.items():
            if re.match(pattern, normalized, flags=re.IGNORECASE):
                return response
        return None

    async def _emit_lightweight_direct_response(
        self,
        session_id: str,
        user_id: str,
        message: str,
        response: str,
        timestamp: datetime | None,
        follow_up_selected_suggestion: str | None,
        follow_up_anchor_event_id: str | None,
        follow_up_source: str | None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Persist and emit a compact user/assistant exchange without task initialization."""
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            raise RuntimeError("Session not found")

        user_event = MessageEvent(
            role="user",
            message=message,
            follow_up_selected_suggestion=follow_up_selected_suggestion,
            follow_up_anchor_event_id=follow_up_anchor_event_id,
            follow_up_source=follow_up_source,
        )
        assistant_event = MessageEvent(role="assistant", message=response)
        done_event = DoneEvent()

        now = timestamp or datetime.now(UTC)
        await self._session_repository.update_latest_message(session_id, message, now)
        await self._session_repository.add_event(session_id, user_event)
        await self._session_repository.add_event(session_id, assistant_event)
        await self._session_repository.add_event(session_id, done_event)

        logger.info(
            "Lightweight direct response served for session %s (message=%r)",
            session_id,
            message[:40],
        )

        yield user_event
        yield assistant_event
        yield done_event

    async def get_session(self, session_id: str, user_id: str | None = None) -> Session | None:
        """Get a session by ID (lightweight — excludes events/files)."""
        logger.info(f"Getting session {session_id} for user {user_id}")
        if not user_id:
            session = await self._session_repository.find_by_id(session_id)
        else:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
        return session

    async def get_session_full(self, session_id: str, user_id: str | None = None) -> Session | None:
        """Get a session by ID with full payload (includes events/files)."""
        logger.info(f"Getting full session {session_id} for user {user_id}")
        if not user_id:
            session = await self._session_repository.find_by_id_full(session_id)
        else:
            session = await self._session_repository.find_by_id_and_user_id_full(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
        return session

    async def get_all_sessions(self, user_id: str) -> list[Session]:
        """Get all sessions for a specific user"""
        logger.debug(f"Getting all sessions for user {user_id}")
        return await self._session_repository.find_by_user_id(user_id)

    async def delete_session(self, session_id: str, user_id: str) -> None:
        """Delete a session, ensuring it belongs to the user.

        Destroys the associated sandbox container before deleting the session
        record to prevent orphaned Docker containers.
        Idempotent: returns silently if session no longer exists (e.g. already
        deleted by a concurrent browser cleanup after a crash).
        """
        logger.info(f"Deleting session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.info(f"Session {session_id} already gone — delete is a no-op")
            return

        # Stop any running task first
        await self._cancel_sandbox_warmup_task(session_id)
        try:
            await self._agent_domain_service.stop_session(session_id)
        except Exception as e:
            logger.warning(f"Failed to stop session {session_id} before deletion: {e}")

        await self._session_repository.delete(session_id)
        logger.info(f"Session {session_id} deleted successfully")

        # Clean up persisted login-state files to prevent orphaned auth snapshots
        try:
            BrowserLoginStateStore().delete_state(user_id, session_id)
        except Exception as e:  # pragma: no cover — best-effort cleanup
            logger.debug("Failed to clean up login state for session %s: %s", session_id, e)

    async def stop_session(self, session_id: str, user_id: str) -> None:
        """Stop a session, ensuring it belongs to the user.

        Idempotent: returns silently if session no longer exists (e.g. already
        cleaned up after a browser crash or race with delete).
        """
        logger.info(f"Stopping session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.info(f"Session {session_id} already gone — stop is a no-op")
            return
        if session.status in (SessionStatus.RUNNING, SessionStatus.INITIALIZING):
            try:
                from app.domain.external.observability import get_metrics

                get_metrics().record_counter("user_stop_before_done_total")
            except Exception as e:
                logger.debug("Could not record user_stop_before_done metric: %s", e)
        await self._cancel_sandbox_warmup_task(session_id)
        await self._agent_domain_service.stop_session(session_id)
        logger.info(f"Session {session_id} stopped successfully")

    async def pause_session(self, session_id: str, user_id: str) -> bool:
        """Pause a session for user takeover, ensuring it belongs to the user"""
        logger.info(f"Pausing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")
        result = await self._agent_domain_service.pause_session(session_id)
        if result:
            logger.info(f"Session {session_id} paused successfully")
        return result

    async def resume_session(
        self, session_id: str, user_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session after user takeover, ensuring it belongs to the user

        Args:
            session_id: Session ID to resume
            user_id: User ID for ownership verification
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state
        """
        logger.info(f"Resuming session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")
        result = await self._agent_domain_service.resume_session(
            session_id, context=context, persist_login_state=persist_login_state
        )
        if result:
            logger.info(f"Session {session_id} resumed successfully")
        return result

    async def start_takeover(self, session_id: str, user_id: str, reason: str = "manual") -> bool:
        """Start browser takeover, pausing agent first.

        Args:
            session_id: Session ID to take over
            user_id: User ID for ownership verification
            reason: Reason for takeover (manual|captcha|login|2fa|payment|verification)
        """
        return await self._session_lifecycle_service.start_takeover(session_id, user_id, reason=reason)

    async def end_takeover(
        self,
        session_id: str,
        user_id: str,
        context: str | None = None,
        persist_login_state: bool | None = None,
        resume_agent: bool = True,
    ) -> bool:
        """End browser takeover and optionally resume the agent.

        Args:
            session_id: Session ID to end takeover for
            user_id: User ID for ownership verification
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state
            resume_agent: Whether to resume the agent
        """
        return await self._session_lifecycle_service.end_takeover(
            session_id, user_id, context=context, persist_login_state=persist_login_state, resume_agent=resume_agent
        )

    async def get_takeover_status(self, session_id: str, user_id: str) -> dict:
        """Get takeover status for a session."""
        return await self._session_lifecycle_service.get_takeover_status(session_id, user_id)

    async def rename_session(self, session_id: str, user_id: str, title: str) -> None:
        """Rename a session, ensuring it belongs to the user"""
        logger.info(f"Renaming session {session_id} for user {user_id} to '{title}'")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        await self._session_repository.update_title(session_id, title)
        logger.info(f"Session {session_id} renamed successfully")

    async def update_session_fields(self, session_id: str, user_id: str, updates: dict[str, Any]) -> None:
        """Update arbitrary allowlisted fields on a session owned by *user_id*."""
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            raise NotFoundError("Session not found")
        await self._session_repository.update_by_id(session_id, updates)

    async def clear_unread_message_count(self, session_id: str, user_id: str) -> None:
        """Clear the unread message count for a session, ensuring it belongs to the user"""
        logger.info(f"Clearing unread message count for session {session_id} for user {user_id}")
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")
        await self._session_repository.update_unread_message_count(session_id, 0)
        logger.info(f"Unread message count cleared for session {session_id}")

    async def shutdown(self):
        logger.info("Closing all agents and cleaning up resources")
        for session_id in list(self._sandbox_warm_tasks.keys()):
            with contextlib.suppress(Exception):
                await self._cancel_sandbox_warmup_task(session_id)
        # Clean up all Agents and their associated sandboxes
        await self._agent_domain_service.shutdown()
        logger.info("All agents closed successfully")

    async def shell_view(self, session_id: str, shell_session_id: str, user_id: str) -> ShellViewResponse:
        """View shell session output, ensuring session belongs to the user"""
        logger.info(f"Getting shell view for session {session_id} for user {user_id}")

        # Guard: LLM sometimes passes tool names (e.g. "list_files") instead of
        # the actual shell session UUID. Fail fast with a clear message.
        try:
            uuid.UUID(shell_session_id)
        except (ValueError, AttributeError) as exc:
            raise InvalidStateException(
                f"Invalid shell_session_id '{shell_session_id}' — expected a UUID. "
                "The LLM may have passed a tool name instead of the session ID."
            ) from exc

        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        if not session.sandbox_id:
            raise RuntimeError("Session has no sandbox environment")

        # Get sandbox and shell output
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            raise RuntimeError("Sandbox environment not found")

        result = await sandbox.view_shell(shell_session_id, console=True)
        if result.success:
            return ShellViewResponse(**result.data)

        error_message = result.message or "Unknown sandbox error"
        if "HTTP 404" in error_message:
            missing_shell_markers = ("Session ID does not exist", "Session ID not found")
            if any(marker in error_message for marker in missing_shell_markers):
                logger.info(
                    "Shell session %s no longer exists in sandbox for session %s; returning empty output",
                    shell_session_id,
                    session_id,
                )
                return ShellViewResponse(output="", session_id=shell_session_id, console=[])
            raise NotFoundError(error_message)
        if "HTTP 409" in error_message:
            raise InvalidStateException(error_message)
        raise RuntimeError(f"Failed to get shell output: {error_message}")

    async def file_view(self, session_id: str, file_path: str, user_id: str) -> FileViewResponse:
        """View file content, ensuring session belongs to the user"""
        logger.info(f"Getting file view for session {session_id} for user {user_id}")
        cache_key = self._file_view_cache_key(session_id, user_id, file_path)
        now = time.monotonic()

        async with self._file_view_lock:
            self._prune_file_view_cache_locked(now)
            cached = self._file_view_cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]

            in_flight = self._file_view_inflight.get(cache_key)
            owner = False
            if in_flight is None:
                in_flight = asyncio.create_task(self._read_file_view_uncached(session_id, file_path, user_id))
                self._file_view_inflight[cache_key] = in_flight
                owner = True

        try:
            response = await asyncio.shield(in_flight)
        except Exception:
            if owner:
                async with self._file_view_lock:
                    current = self._file_view_inflight.get(cache_key)
                    if current is in_flight:
                        self._file_view_inflight.pop(cache_key, None)
            raise

        async with self._file_view_lock:
            if owner:
                self._file_view_cache[cache_key] = (time.monotonic() + self.FILE_VIEW_CACHE_TTL_SECONDS, response)
                current = self._file_view_inflight.get(cache_key)
                if current is in_flight:
                    self._file_view_inflight.pop(cache_key, None)
                self._prune_file_view_cache_locked(time.monotonic())

        return response

    async def _read_file_view_uncached(self, session_id: str, file_path: str, user_id: str) -> FileViewResponse:
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        if not session.sandbox_id:
            raise RuntimeError("Session has no sandbox environment")

        # Get sandbox and file content
        sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            raise RuntimeError("Sandbox environment not found")

        result = await sandbox.file_read(file_path)
        if result.success:
            return FileViewResponse(**result.data)

        error_message = result.message or "Failed to read file"
        # Gracefully handle binary or non-UTF8 content to avoid 500s in the UI.
        if "codec can't decode" in error_message or "invalid start byte" in error_message:
            return FileViewResponse(content=f"[Binary file: {file_path}. Download to view.]", file=file_path)

        raise NotFoundError(f"Failed to read file: {error_message}")

    async def init_workspace_from_manifest(
        self,
        session_id: str,
        manifest: WorkspaceManifest,
        user_id: str,
    ) -> WorkspaceManifestResponse:
        """Initialize a sandbox workspace from a manifest."""
        logger.info("Initializing workspace from manifest for session %s", session_id)
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error("Session %s not found for user %s", session_id, user_id)
            raise NotFoundError("Session not found")

        sandbox = await self._get_or_create_sandbox(session)
        settings = get_settings()

        template_raw = (manifest.template_id or settings.workspace_default_template or "none").strip()
        template_used = self._map_template_id(template_raw, settings.workspace_default_template)

        project_name = self._resolve_project_name(
            manifest.name,
            manifest.path,
            settings.workspace_default_project_name,
        )
        workspace_root = f"/workspace/{session.id}"
        project_root = posixpath.join(workspace_root, project_name)

        exists_result = await sandbox.workspace_exists(session.id)
        if not exists_result.success or not (exists_result.data or {}).get("exists", False):
            await sandbox.workspace_init(
                session.id,
                project_name=project_name,
                template=template_used,
            )

        # Ensure project directory exists
        await sandbox.exec_command(
            session.id,
            "/",
            f"mkdir -p {shlex.quote(project_root)}",
        )

        git_clone_success = None
        git_clone_message = None
        sanitized_git_remote = self._sanitize_git_remote(manifest.git_remote)
        if sanitized_git_remote and sanitized_git_remote.repo_url:
            auth_token = None
            if manifest.git_remote and manifest.git_remote.credentials:
                auth_token = (
                    manifest.git_remote.credentials.get("token")
                    or manifest.git_remote.credentials.get("auth_token")
                    or manifest.git_remote.credentials.get("access_token")
                )
            clone_result = await sandbox.git_clone(
                url=sanitized_git_remote.repo_url,
                target_dir=project_root,
                branch=sanitized_git_remote.branch,
                shallow=True,
                auth_token=auth_token,
            )
            git_clone_success = clone_result.success
            git_clone_message = clone_result.message

        files_written, files_failed, write_errors = await self._write_manifest_files(
            sandbox,
            session.id,
            project_root,
            manifest.path,
            manifest.files,
        )

        # Write .env from env_vars + secrets (do not persist secrets)
        env_content = self._format_env_content(manifest.env_vars, manifest.secrets)
        if env_content:
            env_path = self._safe_join(project_root, ".env")
            env_result = await sandbox.file_write(env_path, env_content)
            if not env_result.success:
                write_errors.append(
                    WorkspaceWriteError(path=env_path, message=env_result.message or "Failed to write .env")
                )
                files_failed += 1
            else:
                files_written += 1

        session.project_name = project_name
        session.project_path = project_root
        session.template_id = manifest.template_id
        session.template_used = template_used
        session.workspace_capabilities = manifest.capabilities or []
        session.dev_command = manifest.dev_command
        session.build_command = manifest.build_command
        session.test_command = manifest.test_command
        session.port = manifest.port
        session.env_var_keys = sorted(manifest.env_vars.keys()) if manifest.env_vars else []
        session.secret_keys = sorted(manifest.secrets.keys()) if manifest.secrets else []
        session.git_remote = sanitized_git_remote.model_dump(exclude={"credentials"}) if sanitized_git_remote else None

        await self._session_repository.save(session)

        return WorkspaceManifestResponse(
            session_id=session.id,
            workspace_root=workspace_root,
            project_root=project_root,
            project_name=project_name,
            project_path=manifest.path,
            template_id=manifest.template_id,
            template_used=template_used,
            capabilities=manifest.capabilities or [],
            files_written=files_written,
            files_failed=files_failed,
            write_errors=write_errors,
            env_var_keys=sorted(manifest.env_vars.keys()) if manifest.env_vars else [],
            secret_keys=sorted(manifest.secrets.keys()) if manifest.secrets else [],
            dev_command=manifest.dev_command,
            build_command=manifest.build_command,
            test_command=manifest.test_command,
            port=manifest.port,
            git_remote=sanitized_git_remote,
            git_clone_success=git_clone_success,
            git_clone_message=git_clone_message,
        )

    async def confirm_action(
        self,
        session_id: str,
        action_id: str,
        accept: bool,
        user_id: str,
    ) -> None:
        """Record user confirmation for a pending tool action."""
        logger.info(
            "Confirming tool action %s for session %s (user %s): %s",
            action_id,
            session_id,
            user_id,
            "accepted" if accept else "rejected",
        )
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        pending_action = session.pending_action or {}
        if pending_action.get("tool_call_id") != action_id:
            logger.warning(
                "Action %s does not match pending action for session %s",
                action_id,
                session_id,
            )

        await self._agent_domain_service.confirm_action(
            session_id=session_id,
            user_id=user_id,
            action_id=action_id,
            accept=accept,
        )

    async def is_session_shared(self, session_id: str) -> bool:
        """Check if a session is shared"""
        logger.info(f"Checking if session {session_id} is shared")
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            raise NotFoundError("Session not found")
        return session.is_shared

    async def get_session_files(self, session_id: str, user_id: str | None = None) -> list[FileInfo]:
        """Get files for a session, ensuring it belongs to the user"""
        logger.info(f"Getting files for session {session_id} for user {user_id}")
        session = await self.get_session_full(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")
        return session.files

    async def get_shared_session_files(self, session_id: str) -> list[FileInfo]:
        """Get files for a shared session"""
        logger.info(f"Getting files for shared session {session_id}")
        session = await self._session_repository.find_by_id_full(session_id)
        if not session or not session.is_shared:
            logger.error(f"Shared session {session_id} not found or not shared")
            raise NotFoundError("Session not found")
        return session.files

    async def persist_generated_artifact(
        self,
        *,
        session_id: str,
        user_id: str,
        local_path: str,
        filename: str | None = None,
        content_type: str | None = None,
        virtual_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> FileInfo | None:
        """Upload a locally generated artifact and attach it to the session."""
        logger.info("Persisting generated artifact for session %s from %s", session_id, local_path)

        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error("Session %s not found for user %s", session_id, user_id)
            raise NotFoundError("Session not found")

        artifact_path = Path(local_path)
        if not artifact_path.is_file():
            logger.warning("Generated artifact path does not exist: %s", local_path)
            return None

        file_bytes = artifact_path.read_bytes()
        if not file_bytes:
            logger.warning("Skipping empty generated artifact at %s", local_path)
            return None

        effective_filename = filename or artifact_path.name or "artifact"
        content_md5 = hashlib.md5(file_bytes).hexdigest()  # noqa: S324
        existing_file = await self._session_repository.get_file_by_path(session_id, virtual_path)
        existing_md5 = (existing_file.metadata or {}).get("content_md5") if existing_file else None
        if (
            existing_file
            and existing_file.file_id
            and existing_file.size == len(file_bytes)
            and (
                existing_md5 == content_md5
                or (
                    existing_file.file_path == virtual_path
                    and (existing_file.filename or effective_filename) == effective_filename
                )
            )
        ):
            return existing_file

        if existing_file and existing_file.file_id:
            with contextlib.suppress(Exception):
                await self._session_repository.remove_file(session_id, existing_file.file_id)
            with contextlib.suppress(Exception):
                await self._file_storage.delete_file(existing_file.file_id, user_id)

        uploaded = await self._file_storage.upload_file(
            BytesIO(file_bytes),
            effective_filename,
            user_id,
            content_type=content_type,
            metadata=metadata,
        )
        if not uploaded or not uploaded.file_id:
            logger.error("Generated artifact upload returned no file info for session %s", session_id)
            return None

        uploaded.filename = effective_filename
        uploaded.file_path = virtual_path
        uploaded.content_type = content_type or uploaded.content_type
        uploaded.size = len(file_bytes)
        uploaded.metadata = {
            **(uploaded.metadata or {}),
            **(metadata or {}),
            "content_md5": content_md5,
        }

        try:
            await self._session_repository.add_file(session_id, uploaded)
        except Exception:
            with contextlib.suppress(Exception):
                await self._file_storage.delete_file(uploaded.file_id, user_id)
            raise

        return uploaded

    async def share_session(self, session_id: str, user_id: str) -> None:
        """Share a session, ensuring it belongs to the user"""
        logger.info(f"Sharing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        await self._session_repository.update_shared_status(session_id, True)
        logger.info(f"Session {session_id} shared successfully")

    async def unshare_session(self, session_id: str, user_id: str) -> None:
        """Unshare a session, ensuring it belongs to the user"""
        logger.info(f"Unsharing session {session_id} for user {user_id}")
        # First verify the session belongs to the user
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        await self._session_repository.update_shared_status(session_id, False)
        logger.info(f"Session {session_id} unshared successfully")

    async def get_shared_session(self, session_id: str) -> Session | None:
        """Get a shared session by ID (no user authentication required)"""
        logger.info(f"Getting shared session {session_id}")
        session = await self._session_repository.find_by_id_full(session_id)
        if not session or not session.is_shared:
            logger.error(f"Shared session {session_id} not found or not shared")
            return None
        return session

    async def browse_url(self, session_id: str, user_id: str, url: str) -> AsyncGenerator[AgentEvent, None]:
        """Navigate browser directly to a URL from search results.

        This method uses the fast-path router to quickly navigate the browser
        to a specific URL, bypassing the full planning workflow.

        Args:
            session_id: Session ID
            user_id: User ID for ownership verification
            url: URL to navigate to

        Yields:
            Agent events for the navigation
        """
        logger.info(f"Browse URL request for session {session_id}: {url}")

        # Verify session ownership
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Session {session_id} not found for user {user_id}")
            raise NotFoundError("Session not found")

        # Delegate to domain service for fast-path browsing
        async for event in self._agent_domain_service.browse_url(session_id, url):
            yield event

    async def _get_or_create_sandbox(self, session: Session) -> Sandbox:
        sandbox = None
        if session.sandbox_id:
            sandbox = await self._sandbox_cls.get(session.sandbox_id)
        if not sandbox:
            sandbox = await self._sandbox_cls.create()
            session.sandbox_id = sandbox.id
        return sandbox

    def _resolve_project_name(
        self,
        name: str | None,
        path: str | None,
        default_name: str,
    ) -> str:
        derived_name = name or (PurePosixPath(path).name if path else "")
        safe_name = PurePosixPath(derived_name).name if derived_name else ""
        return safe_name or default_name

    def _map_template_id(self, template_id: str, default_template: str) -> str:
        key = template_id.strip().lower()
        template_map = {
            "none": "none",
            "python": "python",
            "node": "nodejs",
            "nodejs": "nodejs",
            "web": "web",
            "web-static": "web",
            "fullstack": "fullstack",
        }
        return template_map.get(key, default_template or "none")

    def _sanitize_git_remote(self, git_remote: GitRemoteSpec | None) -> GitRemoteSpec | None:
        if not git_remote:
            return None
        return GitRemoteSpec(
            repo_url=git_remote.repo_url,
            remote_name=git_remote.remote_name,
            branch=git_remote.branch,
        )

    async def _write_manifest_files(
        self,
        sandbox: Sandbox,
        session_id: str,
        project_root: str,
        manifest_root: str | None,
        files: dict[str, str],
    ) -> tuple[int, int, list[WorkspaceWriteError]]:
        if not files:
            return 0, 0, []

        normalized_manifest_root = self._normalize_manifest_root(manifest_root)
        targets: dict[str, str] = {}
        for raw_path, content in files.items():
            resolved = self._resolve_manifest_file_target(
                project_root,
                raw_path,
                normalized_manifest_root,
            )
            if not resolved:
                continue
            targets[resolved] = content

        if not targets:
            return 0, 0, []

        # Ensure directories exist
        directories = {posixpath.dirname(path) for path in targets if posixpath.dirname(path)}
        for directory in sorted(directories):
            await sandbox.exec_command(
                session_id,
                "/",
                f"mkdir -p {shlex.quote(directory)}",
            )

        files_written = 0
        files_failed = 0
        errors: list[WorkspaceWriteError] = []
        for path, content in targets.items():
            result = await sandbox.file_write(path, content)
            if result.success:
                files_written += 1
            else:
                files_failed += 1
                errors.append(WorkspaceWriteError(path=path, message=result.message or "Failed to write file"))

        return files_written, files_failed, errors

    def _normalize_manifest_root(self, manifest_root: str | None) -> str | None:
        if not manifest_root:
            return None
        normalized = manifest_root.replace("\\", "/").rstrip("/")
        return posixpath.normpath(normalized)

    def _resolve_manifest_file_target(
        self,
        project_root: str,
        raw_path: str,
        manifest_root: str | None,
    ) -> str | None:
        if not raw_path:
            return None
        raw_path = raw_path.replace("\\", "/")
        normalized_path = posixpath.normpath(raw_path)
        if normalized_path.startswith("/"):
            if manifest_root and normalized_path.startswith(manifest_root.rstrip("/") + "/"):
                relative_path = normalized_path[len(manifest_root.rstrip("/")) + 1 :]
            else:
                relative_path = normalized_path.lstrip("/")
        else:
            relative_path = normalized_path

        relative_path = relative_path.lstrip("/")
        if not relative_path or relative_path == ".":
            return None
        return self._safe_join(project_root, relative_path)

    def _safe_join(self, base: str, relative_path: str) -> str:
        normalized_base = base.rstrip("/")
        joined = posixpath.normpath(posixpath.join(normalized_base, relative_path))
        if joined == normalized_base or joined.startswith(normalized_base + "/"):
            return joined
        raise SecurityViolation("Resolved path escapes workspace root")

    def _format_env_content(self, env_vars: dict[str, str], secrets: dict[str, str]) -> str:
        if not env_vars and not secrets:
            return ""
        lines: list[str] = []
        for key, value in {**env_vars, **secrets}.items():
            lines.append(self._format_env_line(key, value))
        return "\n".join(lines) + "\n"

    def _format_env_line(self, key: str, value: str | None) -> str:
        safe_value = "" if value is None else str(value)
        needs_quotes = any(ch in safe_value for ch in [" ", "\t", "\n", '"', "'", "\\"])
        if needs_quotes:
            escaped = safe_value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            return f'{key}="{escaped}"'
        return f"{key}={safe_value}"
