import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import TypeAdapter

from app.core.config import get_settings
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
        mongodb_db: Any | None = None,  # MongoDB database for LangGraph checkpointing
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
        self._mongodb_db = mongodb_db  # For LangGraph checkpointing
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
        if not sandbox:
            # Phase 3: Try to acquire from pool if enabled
            settings = get_settings()
            if settings.sandbox_pool_enabled:
                try:
                    from app.core.sandbox_pool import get_sandbox_pool

                    pool = await get_sandbox_pool(self._sandbox_cls)
                    sandbox = await pool.acquire(timeout=5.0)
                    logger.info(f"Acquired sandbox {sandbox.id} from pool for session {session.id}")
                except Exception as e:
                    logger.warning(f"Failed to acquire from pool, creating on-demand: {e}")
                    sandbox = await self._sandbox_cls.create()
            else:
                sandbox = await self._sandbox_cls.create()
            session.sandbox_id = sandbox.id
            is_new_sandbox = True
            await self._session_repository.save(session)

        settings = get_settings()

        # Prepare parallel initialization tasks
        parallel_tasks = []

        # Workspace initialization (skip if lazy init is enabled - Phase 5)
        async def init_workspace():
            if settings.workspace_auto_init and not settings.workspace_lazy_init:
                try:
                    exists_result = await sandbox.workspace_exists(session.id)
                    if not exists_result.success or not exists_result.data.get("exists", False):
                        logger.info(f"Auto-initializing workspace for session {session.id}")
                        await sandbox.workspace_init(
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
                    await sandbox.ensure_framework(session.id)
                except Exception as e:
                    if settings.sandbox_framework_required:
                        raise
                    logger.warning(f"Sandbox framework init error (non-fatal): {e}")

        # Browser health check (verifies CDP connection)
        async def verify_browser():
            if hasattr(sandbox, "verify_browser_ready"):
                await sandbox.verify_browser_ready()

        parallel_tasks.append(init_workspace())
        parallel_tasks.append(init_framework())
        parallel_tasks.append(verify_browser())

        # Run all initialization tasks in parallel — log failures for diagnostics
        init_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
        init_names = ["workspace", "framework", "browser"]
        for name, result in zip(init_names, init_results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Session {session.id} {name} init failed: {result}")

        # BROWSER SESSION PROTOCOL: Only clear browser for brand new sandboxes
        # Previously, this also triggered when session.task_id was None, but that caused
        # browser restarts on every new task (fast prompts issue). Now we only clear for:
        # 1. New sandbox created (is_new_sandbox=True) - browser has no user state
        # For existing sandboxes with running tasks, preserve browser state to:
        # - Avoid VNC positioning issues (new windows shift right)
        # - Preserve ongoing browser work and navigation
        # - Allow smooth handling of fast/consecutive prompts
        should_clear_browser = is_new_sandbox

        # Browser connection is faster after parallel health check
        browser = await sandbox.get_browser(clear_session=should_clear_browser, verify_connection=False)
        if not browser:
            logger.error(f"Failed to get browser for Sandbox {sandbox_id}")
            raise RuntimeError(f"Failed to get browser for Sandbox {sandbox_id}")

        await self._session_repository.save(session)

        # Get multi-agent configuration from settings
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
            # MongoDB database for LangGraph checkpointing
            mongodb_db=self._mongodb_db,
            usage_recorder=self._usage_recorder,
            extra_mcp_configs=extra_mcp_configs,
        )

        task = self._task_cls.create(task_runner)
        session.task_id = task.id
        await self._session_repository.save(session)

        return task

    def _parse_command(self, message: str) -> tuple[str | None, str]:
        """Parse /command syntax from user message.

        Args:
            message: User message that may start with /command

        Returns:
            Tuple of (skill_id, remaining_message)
        """
        try:
            from app.domain.services.command_registry import get_command_registry

            registry = get_command_registry()
            skill_id, remaining = registry.parse_command(message)

            if skill_id:
                logger.info(f"Command invoked: {message.split()[0]} → skill '{skill_id}'")

            return skill_id, remaining

        except Exception as e:
            logger.warning(f"Failed to parse command: {e}")
            return None, message

    async def _apply_skill_triggers(self, message: str, user_skills: list[str] | None) -> tuple[list[str], list[str]]:
        """Apply skill trigger patterns to auto-activate skills.

        Matches the user message against skill trigger patterns and merges
        auto-triggered skills with user-provided skills.

        Args:
            message: User message to match against trigger patterns
            user_skills: Skills explicitly selected by the user

        Returns:
            Tuple of (combined_skills, newly_activated_skills)
            - combined_skills: All skills (user + auto-triggered)
            - newly_activated_skills: Only the skills that were auto-triggered
        """
        try:
            from app.domain.services.skill_trigger_matcher import get_skill_trigger_matcher

            matcher = await get_skill_trigger_matcher()
            matches = await matcher.find_matching_skills(message, max_matches=3, min_confidence=0.3)

            if not matches:
                return user_skills or [], []

            # Get auto-triggered skill IDs
            auto_triggered_ids = [m.skill_id for m in matches]
            logger.info(
                f"Auto-triggered {len(auto_triggered_ids)} skill(s) from message: {', '.join(auto_triggered_ids)}"
            )

            # Merge with user-provided skills (deduplicate)
            user_skill_set = set(user_skills or [])
            all_skills = list(user_skill_set | set(auto_triggered_ids))

            # Log which skills were newly activated
            newly_activated = [sid for sid in auto_triggered_ids if sid not in user_skill_set]
            if newly_activated:
                logger.info(f"Newly activated skills: {', '.join(newly_activated)}")

            return all_skills, newly_activated

        except Exception as e:
            logger.warning(f"Failed to apply skill triggers: {e}")
            # Return original skills on error
            return user_skills or [], []

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

        return resolved if resolved else None

    async def _get_task(self, session: Session) -> Task | None:
        """Get a task for the given session"""

        task_id = session.task_id
        if not task_id:
            return None

        return self._task_cls.get(task_id)

    async def stop_session(self, session_id: str) -> None:
        """Stop a session and destroy its sandbox.

        Cancels any running task and destroys the associated sandbox container
        to prevent orphaned Docker containers.
        """
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to stop non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)
        if task:
            task.cancel()

        # Destroy sandbox to prevent orphaned containers
        if session.sandbox_id:
            try:
                sandbox = await self._sandbox_cls.get(session.sandbox_id)
                if sandbox:
                    await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                    logger.info(f"Destroyed sandbox {session.sandbox_id} for session {session_id}")
            except TimeoutError:
                logger.warning(f"Sandbox {session.sandbox_id} destroy timed out during session stop")
            except Exception as e:
                logger.warning(f"Failed to destroy sandbox {session.sandbox_id} during stop: {e}")

        await self._session_repository.update_status(session_id, SessionStatus.COMPLETED)

        # Clean up session lock to prevent unbounded growth
        self._task_creation_locks.pop(session_id, None)

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
User's summary: {context_text if context_text else "No details provided."}

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
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Chat with an agent
        """

        try:
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
            if not session:
                logger.error(f"Attempted to chat with non-existent Session {session_id} for user {user_id}")
                raise RuntimeError("Session not found")

            task = await self._get_task(session)

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

                        if should_use_fast_path(message):
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
                                message_event = MessageEvent(message=message, role="user")
                                await self._session_repository.add_event(session_id, message_event)
                                yield message_event

                                # Execute fast path directly (no sandbox needed)
                                # Wrap in UsageContextManager so LLM token usage is recorded
                                msg = Message(message=message, attachments=[], skills=[])
                                async with UsageContextManager(
                                    user_id=user_id, session_id=session_id
                                ):
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
                            task = await self._create_task(session, extra_mcp_configs=extra_mcp_configs)
                            if not task:
                                raise RuntimeError("Failed to create task")

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

                    # Parse /command syntax (Superpowers command system)
                    command_skill_id, _message_without_command = self._parse_command(message)
                    if command_skill_id:
                        # Add command-invoked skill to skills list
                        skills = list(set((skills or []) + [command_skill_id]))
                    elif "/skill-creator" in message.lower():
                        # Fallback: detect embedded /skill-creator (e.g., from "Build with Pythinker" button)
                        skills = list(set((skills or []) + ["skill-creator"]))

                    # Skills are only active when explicitly selected by the user
                    # (from chatbox skill picker or settings). Auto-triggering is disabled
                    # to avoid unexpected skill activation.
                    skills_to_use = skills or []

                    resolved_attachments = await self._resolve_user_attachments(attachments, user_id)
                    message_event = MessageEvent(
                        message=message,
                        role="user",
                        attachments=resolved_attachments,
                        skills=skills_to_use,
                        deep_research=deep_research,
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
                                    prompt_chars = len(skill_context.prompt_addition) if skill_context.prompt_addition else 0
                                    tool_restrictions = skill_context.tool_restrictions or None
                            except Exception:
                                pass  # Non-critical — activation event still emitted

                            activation_event = SkillActivationEvent(
                                skill_ids=skills_to_use,
                                skill_names=skill_names,
                                prompt_chars=prompt_chars,
                                tool_restrictions=tool_restrictions,
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

            received_events = False
            while task and not task.done:
                event_id, event_str = await task.output_stream.get(start_id=latest_event_id, block_ms=0)
                if event_str is None:
                    await asyncio.sleep(0.1)  # Yield control, prevent busy-wait
                    continue
                received_events = True
                latest_event_id = event_id
                event = TypeAdapter(AgentEvent).validate_json(event_str)
                event.id = event_id
                logger.debug(f"Got event from Session {session_id}'s event queue: {type(event).__name__}")
                await self._session_repository.update_unread_message_count(session_id, 0)
                yield event
                if isinstance(event, (DoneEvent, ErrorEvent, WaitEvent)):
                    break

            # If the task completed without producing any events, emit a DoneEvent
            # so the SSE client knows the stream completed normally and doesn't retry
            if not received_events:
                logger.warning(f"Session {session_id} task completed without producing events")
                session = await self._session_repository.find_by_id(session_id)
                title = session.title if session else "Task completed"
                yield DoneEvent(title=title, summary="Session completed.")

            logger.info(f"Session {session_id} completed")

        except Exception as e:
            logger.exception(f"Error in Session {session_id}")
            event = ErrorEvent(error=str(e))
            await self._session_repository.add_event(session_id, event)
            # Mark session as failed so it doesn't stay stuck in RUNNING
            try:
                await self._session_repository.update_status(session_id, SessionStatus.FAILED)
            except Exception:
                logger.warning(f"Failed to update session {session_id} status to FAILED")
            yield event
        finally:
            await self._session_repository.update_unread_message_count(session_id, 0)
            # Extract and store memories from session (fire-and-forget)
            if self._memory_service:
                import contextlib

                with contextlib.suppress(Exception):
                    task = asyncio.ensure_future(self._extract_session_memories(session_id, user_id))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

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
            conversation: list[dict[str, str]] = []
            for event in session.events:
                if isinstance(event, MessageEvent):
                    conversation.append(
                        {
                            "role": event.role,
                            "content": event.message,
                        }
                    )

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
                browser = await sandbox.get_browser(clear_session=False, verify_connection=True)

        if not browser:
            logger.error(f"Browser not available for session {session_id}")
            yield ErrorEvent(error="Browser not available")
            yield DoneEvent()
            return

        # Use fast-path router for direct navigation
        fast_path = FastPathRouter(browser=browser, search_engine=self._search_engine)
        logger.info(f"Executing fast browse to {url} for session {session_id}")

        async for event in fast_path.execute_fast_browse(url):
            # Add events to session history for persistence
            if isinstance(event, (MessageEvent, DoneEvent, ErrorEvent)):
                await self._session_repository.add_event(session_id, event)
            yield event
