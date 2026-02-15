import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import TypeAdapter

from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task
from app.domain.models.event import AgentEvent, BaseEvent, DoneEvent, ErrorEvent, MessageEvent, WaitEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.workspace import get_session_workspace_initializer
from app.domain.utils.cancellation import CancellationToken
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

# Setup logging
logger = logging.getLogger(__name__)


class AgentDomainService:
    """
    Agent domain service, responsible for coordinating the work of planning agent and execution agent
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox_cls: type[Sandbox],
        task_cls: type[Task],
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        memory_service: Optional["MemoryService"] = None,
        mongodb_db: Any | None = None,  # MongoDB database for workflow checkpointing
        usage_recorder: Callable[..., Coroutine[Any, Any, None]] | None = None,
    ):
        self._repository = agent_repository
        self._session_repository = session_repository
        self._llm = llm
        self._sandbox_cls = sandbox_cls
        self._search_engine = search_engine
        self._task_cls = task_cls
        self._json_parser = json_parser
        self._file_storage = file_storage
        self._mcp_repository = mcp_repository
        self._memory_service = memory_service
        self._usage_recorder = usage_recorder
        self._mongodb_db = mongodb_db  # For workflow checkpointing
        # Session-level locks to prevent concurrent task creation for the same session
        # This prevents race conditions when fast prompts arrive in quick succession
        self._task_creation_locks: dict[str, asyncio.Lock] = {}
        # Background tasks (prevents garbage collection of fire-and-forget tasks)
        self._background_tasks: set[asyncio.Task[None]] = set()
        logger.info("AgentDomainService initialization completed")

    def _get_task_creation_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for task creation for a specific session."""
        if session_id not in self._task_creation_locks:
            self._task_creation_locks[session_id] = asyncio.Lock()
        return self._task_creation_locks[session_id]

    def _register_background_task(self, task: asyncio.Task[None]) -> None:
        """Track background tasks and consume failures for observability."""
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """Consume background task results to avoid silent failures."""
        self._background_tasks.discard(task)
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning("Background task failed in AgentDomainService: %s", exc)

    async def _force_destroy_sandbox(self, sandbox: Sandbox, sandbox_id: str, session_id: str) -> bool:
        """Best-effort force destroy fallback when graceful destroy times out."""
        force_destroy = getattr(sandbox, "force_destroy", None)
        if not callable(force_destroy):
            logger.warning(
                "Sandbox %s for session %s does not expose force_destroy(); deferred cleanup only",
                sandbox_id,
                session_id,
            )
            return False
        try:
            destroyed = await force_destroy()
            if destroyed:
                logger.info("Force-destroyed sandbox %s for session %s", sandbox_id, session_id)
            else:
                logger.warning("force_destroy returned False for sandbox %s (session %s)", sandbox_id, session_id)
            return bool(destroyed)
        except Exception as e:
            logger.warning("Force-destroy fallback failed for sandbox %s (session %s): %s", sandbox_id, session_id, e)
            return False

    async def shutdown(self) -> None:
        """Clean up all Agent's resources"""
        logger.info("Starting to close all Agents")
        await self._task_cls.destroy()
        logger.info("All agents closed successfully")

    async def _create_task(self, session: Session, extra_mcp_configs: dict[str, Any] | None = None) -> Task:
        """Create a new agent task

        Optimized for fast initialization by running independent operations in parallel:
        - Workspace initialization (if enabled and not lazy)
        - Framework bootstrap (if enabled)
        - Browser health check

        Phase 1 optimization: Parallel initialization reduces startup time by 5-10 seconds.
        Phase 3 optimization: Sandbox pool provides instant sandbox allocation.
        """
        sandbox = None
        sandbox_id = session.sandbox_id
        is_new_sandbox = False

        if sandbox_id:
            sandbox = await self._sandbox_cls.get(sandbox_id)
        from app.core.config import get_settings

        settings = get_settings()
        sandbox_lifecycle_mode = getattr(settings, "sandbox_lifecycle_mode", "static")
        ephemeral_lifecycle = sandbox_lifecycle_mode == "ephemeral"
        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )
        sandbox_pool_enabled = (
            bool(getattr(settings, "sandbox_pool_enabled", False))
            and not uses_static_sandboxes
            and not ephemeral_lifecycle
        )
        owns_session_sandbox = sandbox_lifecycle_mode == "ephemeral"

        def bind_sandbox_metadata(target_sandbox: Sandbox) -> None:
            session.sandbox_id = target_sandbox.id
            session.sandbox_owned = owns_session_sandbox
            session.sandbox_lifecycle_mode = sandbox_lifecycle_mode
            session.sandbox_created_at = datetime.now(UTC) if owns_session_sandbox else None

        async def acquire_sandbox_from_pool() -> Sandbox:
            if sandbox_pool_enabled:
                try:
                    from app.core.sandbox_pool import get_sandbox_pool

                    pool = await get_sandbox_pool(self._sandbox_cls)
                    acquired = await pool.acquire(timeout=5.0)
                    logger.info(f"Acquired sandbox {acquired.id} from pool for session {session.id}")
                    return acquired
                except Exception as e:
                    logger.warning(f"Failed to acquire from pool, creating on-demand: {e}")
            elif uses_static_sandboxes and bool(getattr(settings, "sandbox_pool_enabled", False)):
                logger.debug(
                    "Skipping sandbox pool for session %s because SANDBOX_ADDRESS is configured",
                    session.id,
                )
            return await self._sandbox_cls.create()

        async def recycle_sandbox(current_sandbox: Sandbox, reason: str) -> Sandbox:
            logger.warning(f"Recycling sandbox {current_sandbox.id} for session {session.id}: {reason}")
            if hasattr(current_sandbox, "destroy"):
                try:
                    await current_sandbox.destroy()
                except Exception as e:
                    logger.debug(f"Sandbox destroy failed during recycle (non-critical): {e}")

            replacement = await acquire_sandbox_from_pool()
            bind_sandbox_metadata(replacement)
            await self._session_repository.save(session)
            return replacement

        async def run_parallel_init(target_sandbox: Sandbox) -> None:
            # Prepare parallel initialization tasks
            parallel_tasks = []

            # Workspace initialization (skip if lazy init is enabled - Phase 5)
            async def init_workspace():
                if settings.workspace_auto_init and not settings.workspace_lazy_init:
                    try:
                        exists_result = await target_sandbox.workspace_exists(session.id)
                        if not exists_result.success or not exists_result.data.get("exists", False):
                            logger.info(f"Auto-initializing workspace for session {session.id}")
                            await target_sandbox.workspace_init(
                                session_id=session.id,
                                project_name=settings.workspace_default_project_name,
                                template=settings.workspace_default_template,
                            )
                    except Exception as e:
                        logger.warning(f"Workspace auto-init error (non-fatal): {e}")

            # Framework bootstrap
            async def init_framework():
                if settings.sandbox_framework_enabled:
                    try:
                        await target_sandbox.ensure_framework(session.id)
                    except Exception as e:
                        if settings.sandbox_framework_required:
                            raise
                        logger.warning(f"Sandbox framework init error (non-fatal): {e}")

            # Browser health check (verifies CDP connection)
            async def verify_browser():
                if hasattr(target_sandbox, "verify_browser_ready"):
                    browser_ready = await target_sandbox.verify_browser_ready()
                    if not browser_ready:
                        raise RuntimeError(f"Sandbox browser is not ready: {target_sandbox.id}")

            parallel_tasks.append(init_workspace())
            parallel_tasks.append(init_framework())
            parallel_tasks.append(verify_browser())

            # Run all initialization tasks in parallel — log failures for diagnostics
            init_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            init_names = ["workspace", "framework", "browser"]
            browser_init_error: Exception | None = None
            for name, result in zip(init_names, init_results, strict=True):
                if isinstance(result, Exception):
                    logger.error(f"Session {session.id} {name} init failed: {result}")
                    if name == "browser":
                        browser_init_error = result

            if browser_init_error is not None:
                raise RuntimeError(f"Browser init failed for sandbox {target_sandbox.id}") from browser_init_error

        if not sandbox:
            sandbox = await acquire_sandbox_from_pool()
            bind_sandbox_metadata(sandbox)
            sandbox_id = sandbox.id
            is_new_sandbox = True
            await self._session_repository.save(session)
        else:
            metadata_changed = False
            if session.sandbox_owned != owns_session_sandbox:
                session.sandbox_owned = owns_session_sandbox
                metadata_changed = True
            if session.sandbox_lifecycle_mode != sandbox_lifecycle_mode:
                session.sandbox_lifecycle_mode = sandbox_lifecycle_mode
                metadata_changed = True
            if owns_session_sandbox and session.sandbox_created_at is None:
                session.sandbox_created_at = datetime.now(UTC)
                metadata_changed = True
            elif not owns_session_sandbox and session.sandbox_created_at is not None:
                session.sandbox_created_at = None
                metadata_changed = True
            if metadata_changed:
                await self._session_repository.save(session)

        try:
            await run_parallel_init(sandbox)
        except Exception as e:
            sandbox = await recycle_sandbox(sandbox, str(e))
            sandbox_id = sandbox.id
            is_new_sandbox = True
            await run_parallel_init(sandbox)

        # BROWSER SESSION PROTOCOL: Only clear browser for brand new sandboxes
        # Previously, this also triggered when session.task_id was None, but that caused
        # browser restarts on every new task (fast prompts issue). Now we only clear for:
        # 1. New sandbox created (is_new_sandbox=True) - browser has no user state
        # For existing sandboxes with running tasks, preserve browser state to:
        # - Avoid VNC positioning issues (new windows shift right)
        # - Preserve ongoing browser work and navigation
        # - Allow smooth handling of fast/consecutive prompts
        should_clear_browser = is_new_sandbox
        browser_init_timeout = min(settings.browser_init_timeout, 20.0)
        if browser_init_timeout != settings.browser_init_timeout:
            logger.info(
                "Clamped browser init timeout from %.1fs to %.1fs to avoid first-event stalls",
                settings.browser_init_timeout,
                browser_init_timeout,
            )

        # Browser connection is faster after parallel health check
        try:
            browser = await asyncio.wait_for(
                sandbox.get_browser(
                    clear_session=should_clear_browser,
                    verify_connection=False,
                    block_resources=True,
                ),
                timeout=browser_init_timeout,
            )
            # P1.5: Clear any leftover heavy content from previous sessions
            if should_clear_browser and browser.page:
                try:
                    await browser.page.goto("about:blank", timeout=5000)
                    logger.info("Cleared browser page to about:blank for new session")
                except Exception as clear_error:
                    logger.debug(f"Best-effort page clear failed: {clear_error}")
                    # Non-fatal - continue with session start
        except TimeoutError:
            logger.error(f"Browser init timed out for sandbox {sandbox.id}; recycling sandbox for session {session.id}")
            sandbox = await recycle_sandbox(sandbox, "browser initialization timeout")
            sandbox_id = sandbox.id
            is_new_sandbox = True
            should_clear_browser = True
            await run_parallel_init(sandbox)
            browser = await asyncio.wait_for(
                sandbox.get_browser(
                    clear_session=should_clear_browser,
                    verify_connection=False,
                    block_resources=True,
                ),
                timeout=browser_init_timeout,
            )
        except Exception as e:
            logger.error(
                "Browser init failed for sandbox %s; recycling sandbox for session %s: %s",
                sandbox.id,
                session.id,
                e,
            )
            sandbox = await recycle_sandbox(sandbox, f"browser initialization error: {e}")
            sandbox_id = sandbox.id
            is_new_sandbox = True
            should_clear_browser = True
            await run_parallel_init(sandbox)
            browser = await asyncio.wait_for(
                sandbox.get_browser(
                    clear_session=should_clear_browser,
                    verify_connection=False,
                    block_resources=True,
                ),
                timeout=browser_init_timeout,
            )
        if not browser:
            logger.error(f"Failed to get browser for Sandbox {sandbox_id}")
            raise RuntimeError(f"Failed to get browser for Sandbox {sandbox_id}")

        await self._session_repository.save(session)

        # Get multi-agent configuration from settings
        from app.core.config import get_settings

        settings = get_settings()

        task_runner = AgentTaskRunner(
            session_id=session.id,
            agent_id=session.agent_id,
            user_id=session.user_id,
            llm=self._llm,
            sandbox=sandbox,
            browser=browser,
            file_storage=self._file_storage,
            search_engine=self._search_engine,
            session_repository=self._session_repository,
            json_parser=self._json_parser,
            agent_repository=self._repository,
            mcp_repository=self._mcp_repository,
            mode=session.mode,  # Pass session mode to task runner
            # Multi-agent orchestration configuration
            enable_multi_agent=settings.enable_multi_agent,
            # Unified flow engine selection
            flow_mode=settings.resolved_flow_mode,
            # Long-term memory service (Phase 6: Qdrant integration)
            memory_service=self._memory_service,
            # MongoDB database for workflow checkpointing
            mongodb_db=self._mongodb_db,
            usage_recorder=self._usage_recorder,
            extra_mcp_configs=extra_mcp_configs,
        )

        task = self._task_cls.create(task_runner)
        session.task_id = task.id
        await self._session_repository.save(session)

        return task

    async def _classify_intent_with_context(
        self,
        message: str,
        session: Session,
        attachments: list[dict] | None = None,
        skills: list[str] | None = None,
    ) -> AgentMode | None:
        """Classify intent with context and return recommended mode if different from current.

        Uses the IntentClassifier's context-aware classification to consider:
        - Attachments (images force AGENT mode, documents force AGENT mode)
        - URLs in the message
        - Available skills
        - Conversation context (follow-up detection)

        Args:
            message: User message to classify
            session: Current session for mode and context
            attachments: Optional attachments from the message
            skills: Optional skills to consider

        Returns:
            AgentMode if mode should change, None if current mode is appropriate
        """
        try:
            from app.domain.services.agents.intent_classifier import (
                ClassificationContext,
                get_intent_classifier,
            )

            classifier = get_intent_classifier()

            # Build classification context from message and session
            context = ClassificationContext(
                attachments=[
                    {
                        "mime_type": att.get("content_type", ""),
                        "filename": att.get("filename", ""),
                        "type": att.get("type", ""),
                    }
                    for att in (attachments or [])
                ],
                available_skills=skills or [],
                conversation_length=len(session.events) if session.events else 0,
                is_follow_up=bool(session.events),
                urls=classifier.extract_urls(message),
                mcp_tools=[],  # MCP tools could be added here if needed
            )

            # Classify with context
            result = classifier.classify_with_context(message, context)

            logger.debug(
                "Context-aware intent classification",
                extra={
                    "message_preview": message[:50],
                    "current_mode": session.mode.value,
                    "recommended_mode": result.mode.value,
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "reasons": result.reasons,
                    "context_signals": result.context_signals,
                },
            )

            # Return recommended mode if different from current and confidence is high
            if result.mode != session.mode and result.confidence >= 0.75:
                logger.info(
                    f"Intent classification suggests mode change: {session.mode.value} -> {result.mode.value} "
                    f"(intent={result.intent}, confidence={result.confidence:.2f})"
                )
                return result.mode

            return None

        except Exception as e:
            logger.warning(f"Context-aware intent classification failed: {e}")
            return None

    async def _resolve_user_attachments(self, attachments: list[dict] | None, user_id: str) -> list[FileInfo] | None:
        """Resolve attachment metadata so UI can display accurate info (size/type)."""
        if not attachments:
            return None

        async def resolve_attachment(attachment: dict) -> FileInfo | None:
            file_id = attachment.get("file_id")
            filename = attachment.get("filename")
            content_type = attachment.get("content_type")
            size = attachment.get("size")
            upload_date = attachment.get("upload_date")

            if file_id:
                try:
                    file_info = await self._file_storage.get_file_info(file_id, user_id)
                    if file_info:
                        if not file_info.filename and filename:
                            file_info.filename = filename
                        if (file_info.size is None or file_info.size == 0) and size:
                            file_info.size = size
                        if not file_info.content_type and content_type:
                            file_info.content_type = content_type
                        if not file_info.upload_date and upload_date:
                            file_info.upload_date = upload_date
                        return file_info
                except Exception as exc:
                    logger.warning(f"Failed to fetch file info for attachment {file_id}: {exc}")

            if not file_id and not filename:
                return None

            return FileInfo(
                file_id=file_id,
                filename=filename,
                content_type=content_type,
                size=size,
                upload_date=upload_date,
                user_id=user_id,
            )

        results = await asyncio.gather(
            *[resolve_attachment(attachment) for attachment in attachments], return_exceptions=True
        )

        resolved: list[FileInfo] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Failed to resolve attachment: {result}")
                continue
            if result and (result.file_id or result.filename):
                resolved.append(result)

        return resolved or None

    async def _build_reactivation_context(self, session_id: str) -> str | None:
        """Build a summary of recent session history for reactivation context."""
        try:
            event_count = await self._session_repository.get_event_count(session_id)
            if event_count == 0:
                return None
            # Fetch last 10 events
            offset = max(0, event_count - 10)
            events = await self._session_repository.get_events_paginated(session_id, offset=offset, limit=10)
            if not events:
                return None

            lines: list[str] = []
            for evt in events:
                if isinstance(evt, dict):
                    etype = evt.get("type", "")
                    if etype == "message":
                        role = evt.get("role", "unknown")
                        text = (evt.get("message", ""))[:200]
                        lines.append(f"[{role}] {text}")
                    elif etype == "report":
                        title = evt.get("title", "Report")
                        lines.append(f"[report] {title}")
                else:
                    if hasattr(evt, "type"):
                        if evt.type == "message" and hasattr(evt, "message"):
                            role = getattr(evt, "role", "unknown")
                            lines.append(f"[{role}] {evt.message[:200]}")
                        elif evt.type == "report" and hasattr(evt, "title"):
                            lines.append(f"[report] {evt.title}")

            if not lines:
                return None
            return "[Session history for context]\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to build reactivation context: {e}")
            return None

    async def _get_task(self, session: Session) -> Task | None:
        """Get a task for the given session"""

        task_id = session.task_id
        if not task_id:
            return None

        return self._task_cls.get(task_id)

    async def _teardown_session_runtime(
        self,
        session_id: str,
        session: Session | None = None,
        *,
        status: SessionStatus | None = None,
        destroy_sandbox: bool = True,
    ) -> None:
        """Release runtime resources for a session in an idempotent way."""
        target_session = session or await self._session_repository.find_by_id(session_id)
        if not target_session:
            return

        # Idempotent early-exit: already stopped (no sandbox, terminal status)
        terminal_statuses = (SessionStatus.COMPLETED, SessionStatus.FAILED)
        if not target_session.sandbox_id and target_session.status in terminal_statuses:
            self._task_creation_locks.pop(session_id, None)
            return

        task = await self._get_task(target_session)
        if task:
            task.cancel()

        # Update status BEFORE sandbox destruction so frontend sees terminal state
        # immediately and does not observe stale in-flight status during teardown.
        target_session.task_id = None
        if status is not None:
            target_session.status = status
        await self._session_repository.save(target_session)

        if destroy_sandbox and target_session.sandbox_id:
            owns_sandbox = target_session.sandbox_owned or target_session.sandbox_lifecycle_mode == "ephemeral"
            if target_session.sandbox_lifecycle_mode is None and not target_session.sandbox_owned:
                from app.core.config import get_settings as _get_settings

                configured_lifecycle_mode = getattr(_get_settings(), "sandbox_lifecycle_mode", "static")
                if configured_lifecycle_mode == "ephemeral":
                    owns_sandbox = True

            if owns_sandbox:
                sandbox = None
                try:
                    sandbox = await self._sandbox_cls.get(target_session.sandbox_id)
                    if sandbox:
                        await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                        logger.info(f"Destroyed owned sandbox {target_session.sandbox_id} for session {session_id}")
                except TimeoutError:
                    logger.warning(f"Sandbox {target_session.sandbox_id} destroy timed out during teardown")
                    force_destroyed = False
                    if sandbox is not None:
                        try:
                            force_destroyed = await asyncio.wait_for(
                                self._force_destroy_sandbox(
                                    sandbox=sandbox,
                                    sandbox_id=target_session.sandbox_id,
                                    session_id=session_id,
                                ),
                                timeout=10.0,
                            )
                        except TimeoutError:
                            logger.warning(
                                "Force-destroy fallback timed out for sandbox %s (session %s)",
                                target_session.sandbox_id,
                                session_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "Force-destroy fallback raised for sandbox %s (session %s): %s",
                                target_session.sandbox_id,
                                session_id,
                                e,
                            )
                    if not force_destroyed and sandbox is not None:

                        async def _delayed_destroy() -> None:
                            with contextlib.suppress(Exception):
                                await sandbox.destroy()

                        self._register_background_task(asyncio.create_task(_delayed_destroy()))
                except Exception as e:
                    error_text = str(e)
                    if "No such container" in error_text:
                        logger.info(
                            "Sandbox %s already removed during teardown, continuing",
                            target_session.sandbox_id,
                        )
                    else:
                        logger.warning(f"Failed to destroy sandbox {target_session.sandbox_id} during teardown: {e}")
            else:
                logger.info(
                    "Skipping sandbox destroy for session %s (sandbox %s not owned by session)",
                    session_id,
                    target_session.sandbox_id,
                )

            # Clear sandbox references after destruction
            target_session.sandbox_id = None
            target_session.sandbox_owned = False
            target_session.sandbox_created_at = None
            await self._session_repository.save(target_session)

        # Clean up session lock to prevent unbounded growth
        self._task_creation_locks.pop(session_id, None)

    async def stop_session(self, session_id: str) -> None:
        """Stop a session and destroy its sandbox.

        Cancels any running task and destroys the associated sandbox container
        to prevent orphaned Docker containers.
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.info(f"Stop requested for non-existent Session {session_id}; treating as already stopped")
            return
        await self._teardown_session_runtime(
            session_id,
            session=session,
            status=SessionStatus.COMPLETED,
            destroy_sandbox=True,
        )

    async def pause_session(self, session_id: str) -> bool:
        """Pause a session (for user takeover)

        Returns:
            bool: True if the session was paused, False otherwise
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to pause non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)
        if task:
            result = task.pause()
            if result:
                logger.info(f"Session {session_id} paused for user takeover")
            return result
        return False

    async def resume_session(
        self, session_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session (after user takeover)

        Args:
            session_id: Session ID to resume
            context: Optional context about changes made during takeover
            persist_login_state: Optional flag to persist browser login state

        Returns:
            bool: True if the session was resumed, False otherwise
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to resume non-existent Session {session_id}")
            raise RuntimeError("Session not found")

        # If context is provided, inject it as a message event to inform the agent
        if context is not None:
            context_text = context.strip() if context else ""
            context_message = MessageEvent(
                message=f"""[User Browser Interaction]
The user interacted with the browser directly.
User's summary: {context_text or "No details provided."}

NOTE: The browser state may have changed. When you next use the browser:
1. Take a fresh screenshot to see the current state
2. Adapt your actions based on any changes the user made""",
                role="user",
            )
            await self._session_repository.add_event(session_id, context_message)
            logger.info(f"Injected user takeover context for session {session_id}")

            # Also put it in the task's input stream if task exists
            task = await self._get_task(session)
            if task:
                await task.input_stream.put(context_message.model_dump_json())

        # Handle persist_login_state if provided (store in session metadata for future reference)
        if persist_login_state is not None:
            session.persist_login_state = persist_login_state
            await self._session_repository.save(session)
            logger.info(f"Session {session_id} persist_login_state set to {persist_login_state}")

        task = await self._get_task(session)
        if task:
            result = task.resume()
            if result:
                logger.info(f"Session {session_id} resumed after user takeover")
            return result
        return False

    async def enqueue_user_message(
        self,
        session_id: str,
        user_id: str,
        message: str,
    ) -> None:
        """Enqueue a user message without opening an SSE stream."""
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Attempted to enqueue message for non-existent Session {session_id}")
            raise RuntimeError("Session not found")

        # Use session-level lock to prevent concurrent task creation
        task_lock = self._get_task_creation_lock(session_id)
        async with task_lock:
            # Re-fetch session to get latest state
            session = await self._session_repository.find_by_id(session_id)
            if not session:
                raise RuntimeError("Session not found")
            task = await self._get_task(session)
            if session.status != SessionStatus.RUNNING or task is None:
                task = await self._create_task(session)
                if not task:
                    raise RuntimeError("Failed to create task")

        await self._session_repository.update_latest_message(session_id, message, datetime.now())

        message_event = MessageEvent(message=message, role="user")
        event_id = await task.input_stream.put(message_event.model_dump_json())
        message_event.id = event_id
        await self._session_repository.add_event(session_id, message_event)

        await task.run()

    async def chat(
        self,
        session_id: str,
        user_id: str,
        message: str | None = None,
        timestamp: datetime | None = None,
        latest_event_id: str | None = None,
        attachments: list[dict] | None = None,
        skills: list[str] | None = None,
        deep_research: bool | None = None,
        extra_mcp_configs: dict[str, Any] | None = None,
        auto_trigger_enabled: bool | None = None,
        follow_up_selected_suggestion: str | None = None,
        follow_up_anchor_event_id: str | None = None,
        follow_up_source: str | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Chat with an agent

        Args:
            cancel_event: Event that signals cancellation (e.g., SSE disconnect).
                Domain service checks this periodically and cancels active task execution.
        """

        try:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
            if not session:
                logger.error(f"Attempted to chat with non-existent Session {session_id} for user {user_id}")
                raise RuntimeError("Session not found")

            task = await self._get_task(session)
            if cancel_event is not None and cancel_event.is_set():
                if task and not task.done:
                    task.cancel()
                    await self._teardown_session_runtime(
                        session_id,
                        session=session,
                        status=SessionStatus.FAILED,
                        destroy_sandbox=False,
                    )
                logger.info("Cancellation requested before processing session %s", session_id)
                return

            if message:
                # Deduplication check: Skip if same message was recently sent to this session
                # This prevents duplicate messages when:
                # - Page reloads or SSE reconnects during active task
                # - Backend restarts and frontend retries the request
                is_duplicate = False
                last_user_event = None
                if session.events:
                    for event in reversed(session.events):
                        if isinstance(event, MessageEvent) and event.role == "user":
                            last_user_event = event
                            break

                if last_user_event and last_user_event.message == message:
                    now = datetime.now(UTC)
                    latest_at = last_user_event.timestamp
                    if latest_at.tzinfo is None:
                        latest_at = latest_at.replace(tzinfo=UTC)
                    time_since_last = (now - latest_at).total_seconds()
                    if time_since_last < 300:  # Within 5 minutes (research tasks can take a while)

                        def normalize_skills(skill_ids: list[str] | None) -> list[str]:
                            return sorted({skill_id for skill_id in (skill_ids or []) if skill_id})

                        def normalize_attachments(items: list[dict] | list[FileInfo] | None) -> list[str]:
                            normalized: set[str] = set()
                            for item in items or []:
                                if isinstance(item, dict):
                                    value = item.get("file_id") or item.get("filename") or item.get("file_path")
                                else:
                                    value = item.file_id or item.filename or item.file_path
                                if value:
                                    normalized.add(value)
                            return sorted(normalized)

                        incoming_skills = normalize_skills(skills)
                        last_skills = normalize_skills(last_user_event.skills)
                        incoming_attachments = normalize_attachments(attachments)
                        last_attachments = normalize_attachments(last_user_event.attachments)

                        if incoming_skills == last_skills and incoming_attachments == last_attachments:
                            is_duplicate = True
                            logger.warning(
                                f"Skipping duplicate message for session {session_id} (same payload sent {time_since_last:.1f}s ago, status={session.status})"
                            )

                if is_duplicate:
                    # Don't add duplicate message
                    if session.status == SessionStatus.RUNNING and task:
                        # Session is still running, just reconnect to the event stream
                        logger.info(f"Session {session_id} reconnecting to running task (duplicate message skipped)")
                    else:
                        # Session completed or not running - return completed event without reprocessing
                        logger.info(
                            f"Session {session_id} duplicate after completion - not reprocessing (status={session.status})"
                        )
                        yield DoneEvent(
                            title=session.title or "Task completed", summary="This request was already processed."
                        )
                        return
                else:
                    # EARLY FAST PATH: For simple queries (GREETING/KNOWLEDGE) on new sessions,
                    # skip expensive task creation (sandbox + browser init ~60s) and respond directly.
                    # This reduces "Hello" latency from 60-90s to <2s.
                    if task is None and not attachments and not skills and not deep_research:
                        from app.domain.models.message import Message
                        from app.domain.services.flows.fast_path import (
                            FastPathRouter,
                            QueryIntent,
                            should_use_fast_path,
                        )

                        if should_use_fast_path(message, follow_up_source=follow_up_source):
                            fast_router = FastPathRouter(llm=self._llm, search_engine=self._search_engine)
                            intent, params = fast_router.classify(message)

                            if intent in (QueryIntent.GREETING, QueryIntent.KNOWLEDGE):
                                logger.info(
                                    f"Early fast path for session {session_id}: "
                                    f"intent={intent.value}, skipping task creation"
                                )

                                # Store user message event
                                await self._session_repository.update_latest_message(
                                    session_id, message, timestamp or datetime.now()
                                )
                                message_event = MessageEvent(
                                    message=message,
                                    role="user",
                                    follow_up_selected_suggestion=follow_up_selected_suggestion,
                                    follow_up_anchor_event_id=follow_up_anchor_event_id,
                                    follow_up_source=follow_up_source,
                                )
                                await self._session_repository.add_event(session_id, message_event)
                                yield message_event

                                # Execute fast path directly (no sandbox needed)
                                # Wrap in UsageContextManager so LLM token usage is recorded
                                msg = Message(
                                    message=message,
                                    attachments=[],
                                    skills=[],
                                    follow_up_selected_suggestion=follow_up_selected_suggestion,
                                    follow_up_anchor_event_id=follow_up_anchor_event_id,
                                    follow_up_source=follow_up_source,
                                )
                                async with UsageContextManager(user_id=user_id, session_id=session_id):
                                    async for event in fast_router.execute(intent, params, msg):
                                        await self._session_repository.add_event(session_id, event)
                                        yield event

                                return

                    # Context-aware intent classification to determine if mode should change
                    # This considers attachments, URLs, skills, and conversation context
                    recommended_mode = await self._classify_intent_with_context(
                        message=message,
                        session=session,
                        attachments=attachments,
                        skills=skills,
                    )

                    # Update session mode if classification recommends a change
                    if recommended_mode is not None and recommended_mode != session.mode:
                        logger.info(
                            f"Session {session_id} mode changed by intent classification: "
                            f"{session.mode.value} -> {recommended_mode.value}"
                        )
                        session.mode = recommended_mode
                        await self._session_repository.update_mode(session_id, recommended_mode)

                    # Use session-level lock to prevent concurrent task creation
                    # This prevents race conditions when fast prompts arrive before
                    # the first task is fully initialized
                    task_lock = self._get_task_creation_lock(session_id)
                    async with task_lock:
                        # Re-check task status inside the lock - another request may have
                        # already created the task while we were waiting for the lock
                        session = await self._session_repository.find_by_id(session_id)
                        if session:
                            task = await self._get_task(session)

                        if session and (session.status != SessionStatus.RUNNING or task is None):
                            if cancel_event is not None and cancel_event.is_set():
                                logger.info("Cancellation requested before task creation for session %s", session_id)
                                return
                            is_reactivation = session.status == SessionStatus.COMPLETED
                            task = await self._create_task(session, extra_mcp_configs=extra_mcp_configs)
                            if not task:
                                raise RuntimeError("Failed to create task")

                            # Inject session history context on reactivation
                            if is_reactivation:
                                logger.info(f"Session reactivation detected for {session_id}")
                                try:
                                    reactivation_ctx = await self._build_reactivation_context(session_id)
                                    if reactivation_ctx:
                                        from app.domain.models.event import MessageEvent as _MsgEvt

                                        ctx_event = _MsgEvt(
                                            role="assistant",
                                            message=reactivation_ctx,
                                        )
                                        await task.input_stream.put(ctx_event.model_dump_json())
                                        logger.info(
                                            "Injected reactivation context into task input (%d chars) for session %s",
                                            len(reactivation_ctx),
                                            session_id,
                                        )
                                except Exception as e:
                                    logger.warning(f"Reactivation context injection failed (non-fatal): {e}")

                            # Initialize workspace with template selection on first message
                            # (Phase 1: Multi-task workspace integration)
                            try:
                                if not session.workspace_structure and session.sandbox_id:
                                    sandbox = await self._sandbox_cls.get(session.sandbox_id)
                                    if sandbox:
                                        initializer = get_session_workspace_initializer(self._session_repository)
                                        workspace_structure = await initializer.initialize_workspace_if_needed(
                                            session=session, sandbox=sandbox, task_description=message
                                        )
                                        if workspace_structure:
                                            logger.info(
                                                f"Initialized workspace for session {session_id}: "
                                                f"{len(workspace_structure)} folders created"
                                            )
                            except Exception as e:
                                # Non-critical - log and continue
                                logger.warning(f"Workspace initialization error (non-fatal): {e}")

                    await self._session_repository.update_latest_message(
                        session_id, message, timestamp or datetime.now()
                    )

                    # Resolve skill activation through a single framework.
                    # Policy: auto-trigger is OFF by default; skills activate only via:
                    # 1) explicit chat-box selection
                    # 2) slash command (e.g. /brainstorm)
                    from app.domain.services.skill_activation_framework import get_skill_activation_framework

                    if auto_trigger_enabled is None:
                        from app.core.config import get_settings as _get_cfg

                        auto_trigger_enabled = _get_cfg().skill_auto_trigger_enabled

                    activation_framework = get_skill_activation_framework()
                    activation_result = await activation_framework.resolve(
                        message=message,
                        selected_skills=skills,
                        auto_trigger_enabled=auto_trigger_enabled,
                    )
                    skills_to_use = activation_result.skill_ids

                    resolved_attachments = await self._resolve_user_attachments(attachments, user_id)
                    message_event = MessageEvent(
                        message=message,
                        role="user",
                        attachments=resolved_attachments,
                        skills=skills_to_use,
                        deep_research=deep_research,
                        follow_up_selected_suggestion=follow_up_selected_suggestion,
                        follow_up_anchor_event_id=follow_up_anchor_event_id,
                        follow_up_source=follow_up_source,
                    )

                    event_id = await task.input_stream.put(message_event.model_dump_json())

                    message_event.id = event_id
                    await self._session_repository.add_event(session_id, message_event)

                    # Yield the user message event so frontend can display it immediately
                    yield message_event

                    # Emit skill activation event if user explicitly selected skills
                    if skills_to_use:
                        from app.domain.models.event import SkillActivationEvent
                        from app.domain.services.skill_registry import get_skill_registry

                        try:
                            registry = await get_skill_registry()
                            skill_names = []
                            for skill_id in skills_to_use:
                                skill = await registry.get_skill(skill_id)
                                if skill:
                                    skill_names.append(skill.name)

                            # Build context to populate prompt_chars and tool_restrictions
                            prompt_chars = 0
                            tool_restrictions: list[str] | None = None
                            try:
                                skill_context = await registry.build_context(skills_to_use, expand_dynamic=False)
                                if skill_context:
                                    prompt_chars = (
                                        len(skill_context.prompt_addition) if skill_context.prompt_addition else 0
                                    )
                                    tool_restrictions = (
                                        list(skill_context.allowed_tools) if skill_context.allowed_tools else None
                                    )
                            except Exception:
                                logger.debug("Failed to build skill context for activation event", exc_info=True)

                            activation_event = SkillActivationEvent(
                                skill_ids=skills_to_use,
                                skill_names=skill_names,
                                prompt_chars=prompt_chars,
                                tool_restrictions=tool_restrictions,
                                activation_sources=activation_result.activation_sources,
                                command_skill_id=activation_result.command_skill_id,
                                auto_trigger_enabled=activation_result.auto_trigger_enabled,
                            )
                            yield activation_event

                            logger.info(
                                f"Skills activated for session {session_id}: {', '.join(skill_names or skills_to_use)}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to emit skill activation event: {e}")

                    await task.run()
                    logger.debug(f"Put message into Session {session_id}'s event queue: {message[:50]}...")

            logger.info(f"Session {session_id} started")
            logger.debug(f"Session {session_id} task: {task}")

            # Create cancellation token for this session
            cancel_token = CancellationToken(event=cancel_event, session_id=session_id)
            from app.core.config import get_settings as _get_cfg

            stream_poll_block_ms = max(1, _get_cfg().redis_stream_poll_block_ms)

            received_events = False
            terminal_status: SessionStatus | None = None
            while task and not task.done:
                # Check for cancellation (SSE disconnect)
                if cancel_token.is_cancelled():
                    task.cancel()
                    await self._teardown_session_runtime(session_id, status=SessionStatus.FAILED, destroy_sandbox=False)
                    logger.info("Session %s cancelled during event loop", session_id)
                    return

                event_id, event_str = await task.output_stream.get(
                    start_id=latest_event_id,
                    block_ms=stream_poll_block_ms,
                )
                if event_str is None:
                    continue
                received_events = True
                latest_event_id = event_id
                event = TypeAdapter(AgentEvent).validate_json(event_str)
                event.id = event_id
                logger.debug(f"Got event from Session {session_id}'s event queue: {type(event).__name__}")
                await self._session_repository.update_unread_message_count(session_id, 0)

                # Detect terminal events and persist status BEFORE yielding to SSE.
                # This prevents a race condition where a page refresh between the
                # SSE send and _teardown_session_runtime sees "running" in the DB.
                if isinstance(event, DoneEvent):
                    terminal_status = SessionStatus.COMPLETED
                    await self._session_repository.update_status(session_id, SessionStatus.COMPLETED)
                    yield event
                    break
                if isinstance(event, ErrorEvent):
                    terminal_status = SessionStatus.FAILED
                    await self._session_repository.update_status(session_id, SessionStatus.FAILED)
                    yield event
                    break

                yield event
                if isinstance(event, WaitEvent):
                    break

            # If the task completed without producing any events, emit a DoneEvent
            # so the SSE client knows the stream completed normally and doesn't retry.
            # For no-op reconnects (no message/input and no active task), end silently
            # without forcing session completion.
            if not received_events:
                has_message_content = bool(message and message.strip())
                has_new_input = bool(
                    has_message_content
                    or attachments
                    or skills
                    or deep_research
                    or follow_up_selected_suggestion
                    or follow_up_anchor_event_id
                    or follow_up_source
                )
                if task is None and not has_new_input:
                    logger.info(
                        f"Session {session_id} has no active task and no new input; ending stream without completion event"
                    )
                    return

                logger.warning(f"Session {session_id} task completed without producing events")
                session = await self._session_repository.find_by_id(session_id)
                title = session.title if session else "Task completed"
                yield DoneEvent(title=title, summary="Session completed.")
                terminal_status = SessionStatus.COMPLETED

            if terminal_status is not None:
                await self._teardown_session_runtime(session_id, status=terminal_status, destroy_sandbox=False)

            logger.info(f"Session {session_id} completed")

        except Exception as e:
            logger.exception(f"Error in Session {session_id}")
            event = ErrorEvent(error=str(e))
            await self._session_repository.add_event(session_id, event)
            await self._teardown_session_runtime(session_id, status=SessionStatus.FAILED, destroy_sandbox=False)
            yield event
        finally:
            await self._session_repository.update_unread_message_count(session_id, 0)
            # Extract and store memories from session (fire-and-forget)
            if self._memory_service:
                import contextlib

                with contextlib.suppress(Exception):
                    task = asyncio.ensure_future(self._extract_session_memories(session_id, user_id))
                    self._register_background_task(task)

    async def _extract_session_memories(self, session_id: str, user_id: str) -> None:
        """Extract and store memories from a completed session.

        Called asynchronously after session completion. Failures are logged
        but never propagate — memory extraction is non-critical.
        """
        if not self._memory_service:
            return

        try:
            session = await self._session_repository.find_by_id(session_id)
            if not session or not session.events:
                return

            # Build conversation from message events
            conversation: list[dict[str, str]] = [
                {"role": event.role, "content": event.message}
                for event in session.events
                if isinstance(event, MessageEvent)
            ]

            if not conversation:
                return

            # Extract memories from conversation
            extracted = await self._memory_service.extract_from_conversation(
                user_id=user_id,
                conversation=conversation,
                session_id=session_id,
            )

            # Extract from task result if available
            task_description: str | None = None
            final_result: str | None = None
            for event in session.events:
                if isinstance(event, MessageEvent) and event.role == "user" and not task_description:
                    task_description = event.message
                elif isinstance(event, MessageEvent) and event.role == "assistant":
                    # Keep updating — last assistant message is the final result
                    final_result = event.message

            if task_description and final_result:
                task_memories = await self._memory_service.extract_from_task_result(
                    user_id=user_id,
                    task_description=task_description,
                    task_result=final_result,
                    success=True,
                    session_id=session_id,
                )
                extracted.extend(task_memories)

            # Store all extracted memories
            if extracted:
                await self._memory_service.store_many(
                    user_id=user_id,
                    memories=extracted,
                    session_id=session_id,
                )
                logger.info(f"Extracted {len(extracted)} memories from session {session_id}")

            # Store visited URLs and search queries as cross-session memory
            # This allows Qdrant to surface relevant prior research in future sessions
            try:
                from app.domain.services.agents.task_state_manager import get_task_state_manager

                tsm = get_task_state_manager()
                visited_urls = tsm.get_visited_urls()
                searched_queries = tsm.get_searched_queries()

                if visited_urls or searched_queries:
                    from app.domain.models.long_term_memory import (
                        MemoryImportance,
                        MemorySource,
                        MemoryType,
                    )

                    research_summary_parts = []
                    if task_description:
                        research_summary_parts.append(f"Research task: {task_description[:200]}")
                    if searched_queries:
                        research_summary_parts.append(
                            f"Search queries used: {', '.join(sorted(searched_queries)[:15])}"
                        )
                    if visited_urls:
                        research_summary_parts.append(
                            f"URLs visited ({len(visited_urls)}): {', '.join(sorted(visited_urls)[:10])}"
                        )

                    research_summary = "\n".join(research_summary_parts)
                    await self._memory_service.store_memory(
                        user_id=user_id,
                        content=research_summary,
                        memory_type=MemoryType.PROJECT_CONTEXT,
                        importance=MemoryImportance.LOW,
                        source=MemorySource.SYSTEM,
                        session_id=session_id,
                        tags=["research_history", "visited_urls"],
                        metadata={
                            "url_count": len(visited_urls),
                            "query_count": len(searched_queries),
                        },
                    )
                    logger.info(
                        f"Stored research context memory for session {session_id}: "
                        f"{len(visited_urls)} URLs, {len(searched_queries)} queries"
                    )
            except Exception as e:
                logger.debug(f"Failed to store research context memory: {e}")

        except Exception as e:
            logger.warning(f"Memory extraction failed for session {session_id}: {e}")

    async def confirm_action(
        self,
        session_id: str,
        user_id: str,
        action_id: str,
        accept: bool,
    ) -> None:
        """Confirm or reject a pending tool action and deterministically execute if accepted."""
        session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
        if not session:
            logger.error(f"Attempted to confirm action for non-existent Session {session_id}")
            raise RuntimeError("Session not found")

        # Use session-level lock to prevent concurrent task creation
        task_lock = self._get_task_creation_lock(session_id)
        async with task_lock:
            # Re-fetch session to get latest state
            session = await self._session_repository.find_by_id(session_id)
            if not session:
                raise RuntimeError("Session not found")
            task = await self._get_task(session)
            if not task or task.done:
                task = await self._create_task(session)

        runner = getattr(task, "runner", None) or getattr(task, "_runner", None)
        if not runner or not hasattr(runner, "execute_pending_action"):
            logger.warning("Task runner does not support pending action execution")
            return

        await runner.execute_pending_action(task, action_id, accept)

    async def browse_url(self, session_id: str, url: str) -> AsyncGenerator[BaseEvent, None]:
        """Navigate browser directly to a URL using fast-path.

        This method provides a quick way to navigate the browser to a specific URL,
        bypassing the full planning workflow. It's used when users click on search
        results to view them directly in the browser.

        Args:
            session_id: Session ID
            url: URL to navigate to

        Yields:
            Events for the navigation
        """
        from app.domain.services.flows.fast_path import FastPathRouter

        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Session {session_id} not found for browse_url")
            yield ErrorEvent(error="Session not found")
            yield DoneEvent()
            return

        # Get browser from sandbox
        sandbox = None
        browser = None
        if session.sandbox_id:
            sandbox = await self._sandbox_cls.get(session.sandbox_id)
            if sandbox:
                browser = await sandbox.get_browser(
                    clear_session=False,
                    verify_connection=True,
                    block_resources=True,
                )

        if not browser:
            logger.error(f"Browser not available for session {session_id}")
            yield ErrorEvent(error="Browser not available")
            yield DoneEvent()
            return

        # Use fast-path router for direct navigation
        fast_path = FastPathRouter(browser=browser, search_engine=self._search_engine)
        logger.info(f"Executing fast browse to {url} for session {session_id}")

        try:
            async for event in fast_path.execute_fast_browse(url):
                # Add events to session history for persistence
                if isinstance(event, (MessageEvent, DoneEvent, ErrorEvent)):
                    await self._session_repository.add_event(session_id, event)
                yield event
        finally:
            if sandbox and hasattr(sandbox, "release_pooled_browser"):
                try:
                    await sandbox.release_pooled_browser(browser, had_error=False)
                except Exception as e:
                    logger.debug(f"Pooled browser release failed (non-critical): {e}")
