"""Agent Task Factory.

Handles task creation, intent classification, attachment resolution,
and reactivation context building.
Extracted from AgentDomainService to follow Single Responsibility Principle.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, Session
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.services.browser_login_state_store import BrowserLoginStateStore
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class AgentTaskFactory:
    """Creates agent tasks and handles intent classification and attachment resolution.

    This class encapsulates the complex task creation logic that was previously
    in AgentDomainService, including sandbox acquisition, browser initialization,
    and parallel init orchestration.
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
        mongodb_db: Any | None = None,
        usage_recorder: Callable[..., Coroutine[Any, Any, None]] | None = None,
    ) -> None:
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
        self._mongodb_db = mongodb_db
        self._login_state_store = BrowserLoginStateStore()

    async def create_task(self, session: Session, extra_mcp_configs: dict[str, Any] | None = None) -> Task:
        """Create a new agent task.

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
            async def init_workspace() -> None:
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
            async def init_framework() -> None:
                if settings.sandbox_framework_enabled:
                    try:
                        await target_sandbox.ensure_framework(session.id)
                    except Exception as e:
                        if settings.sandbox_framework_required:
                            raise
                        logger.warning(f"Sandbox framework init error (non-fatal): {e}")

            # Browser health check (verifies CDP connection)
            async def verify_browser() -> None:
                if hasattr(target_sandbox, "verify_browser_ready"):
                    browser_ready = await target_sandbox.verify_browser_ready()
                    if not browser_ready:
                        raise RuntimeError(f"Sandbox browser is not ready: {target_sandbox.id}")

            parallel_tasks.append(init_workspace())
            parallel_tasks.append(init_framework())
            parallel_tasks.append(verify_browser())

            # Run all initialization tasks in parallel -- log failures for diagnostics
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
        # - Avoid live preview positioning issues (new windows shift right)
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

        if should_clear_browser and session.persist_login_state:
            stored_state = self._login_state_store.load_state(session.user_id, session.id)
            if stored_state:
                import_storage_state = getattr(browser, "import_storage_state", None)
                if callable(import_storage_state):
                    restored = await import_storage_state(stored_state)
                    if restored:
                        logger.info("Restored persisted login state for session %s", session.id)
                else:
                    logger.warning("Browser implementation does not support storage-state restore")

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
            research_mode=session.research_mode,  # Pass research strategy to task runner
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

    async def classify_intent_with_context(
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

    async def resolve_user_attachments(self, attachments: list[dict] | None, user_id: str) -> list[FileInfo] | None:
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

    async def build_reactivation_context(self, session_id: str) -> str | None:
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

    async def get_task(self, session: Session) -> Task | None:
        """Get a task for the given session."""
        task_id = session.task_id
        if not task_id:
            return None
        return self._task_cls.get(task_id)
