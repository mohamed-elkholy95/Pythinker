"""Agent Domain Service - Orchestrator.

Coordinates agent task execution by composing:
- AgentSessionLifecycle: session stop/pause/resume/teardown
- AgentTaskFactory: task creation, intent classification, attachment resolution

This class preserves the original public interface while delegating
to focused sub-services internally.
"""

import asyncio
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
from app.domain.services.agents.agent_session_lifecycle import AgentSessionLifecycle
from app.domain.services.agents.agent_task_factory import AgentTaskFactory
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.workspace import get_session_workspace_initializer
from app.domain.utils.cancellation import CancellationToken

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

# Setup logging
logger = logging.getLogger(__name__)


class AgentDomainService:
    """Agent domain service orchestrator.

    Coordinates the work of planning agent and execution agent by composing
    AgentSessionLifecycle and AgentTaskFactory sub-services.
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox_cls: type[Sandbox],
        task_cls: type[Task],
        json_parser: "Any",
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        memory_service: Optional["MemoryService"] = None,
        mongodb_db: Any | None = None,  # MongoDB database for workflow checkpointing
        usage_recorder: Callable[..., Coroutine[Any, Any, None]] | None = None,
    ):
        self._session_repository = session_repository
        self._sandbox_cls = sandbox_cls
        self._llm = llm
        self._search_engine = search_engine
        self._task_cls = task_cls
        self._file_storage = file_storage
        self._memory_service = memory_service

        # Conversation context: real-time vectorization during active sessions
        from app.domain.services.conversation_context_service import get_conversation_context_service

        self._conversation_context_service = get_conversation_context_service()
        self._turn_counter = 0

        # Compose sub-services
        self._lifecycle = AgentSessionLifecycle(
            session_repository=session_repository,
            sandbox_cls=sandbox_cls,
            task_cls=task_cls,
        )

        self._task_factory = AgentTaskFactory(
            agent_repository=agent_repository,
            session_repository=session_repository,
            llm=llm,
            sandbox_cls=sandbox_cls,
            task_cls=task_cls,
            json_parser=json_parser,
            file_storage=file_storage,
            mcp_repository=mcp_repository,
            search_engine=search_engine,
            memory_service=memory_service,
            mongodb_db=mongodb_db,
            usage_recorder=usage_recorder,
        )

        # Global concurrency guard: limits active agent tasks to available sandbox slots.
        # When saturated, new chat() calls wait (not reject) -- matching queue semantics
        # without the overhead of a separate worker process.
        from app.core.config import get_settings as _init_settings

        self._agent_concurrency = asyncio.Semaphore(_init_settings().max_concurrent_agents)
        logger.info("AgentDomainService initialization completed")

    # ------------------------------------------------------------------
    # Delegation properties for backward compatibility
    # Tests and internal code access these directly on the service instance.
    # ------------------------------------------------------------------

    @property
    def _task_creation_locks(self) -> dict[str, asyncio.Lock]:
        """Expose lifecycle's task creation locks for backward compatibility."""
        return self._lifecycle._task_creation_locks

    @property
    def _background_tasks(self) -> set[asyncio.Task[None]]:
        """Expose lifecycle's background tasks for backward compatibility."""
        return self._lifecycle._background_tasks

    # ------------------------------------------------------------------
    # Delegation methods for backward compatibility (used by tests)
    # ------------------------------------------------------------------

    def _get_task_creation_lock(self, session_id: str) -> asyncio.Lock:
        """Delegate to lifecycle manager."""
        return self._lifecycle._get_task_creation_lock(session_id)

    def _register_background_task(self, task: asyncio.Task[None]) -> None:
        """Delegate to lifecycle manager."""
        self._lifecycle._register_background_task(task)

    def _on_background_task_done(self, task: asyncio.Task[None]) -> None:
        """Delegate to lifecycle manager."""
        self._lifecycle._on_background_task_done(task)

    async def _force_destroy_sandbox(self, sandbox: Sandbox, sandbox_id: str, session_id: str) -> bool:
        """Delegate to lifecycle manager."""
        return await self._lifecycle._force_destroy_sandbox(sandbox, sandbox_id, session_id)

    async def _teardown_session_runtime(
        self,
        session_id: str,
        session: Session | None = None,
        *,
        status: SessionStatus | None = None,
        destroy_sandbox: bool = True,
    ) -> None:
        """Delegate to lifecycle manager."""
        await self._lifecycle._teardown_session_runtime(
            session_id, session=session, status=status, destroy_sandbox=destroy_sandbox
        )

    async def _get_task(self, session: Session) -> Task | None:
        """Delegate to task factory."""
        return await self._task_factory.get_task(session)

    async def _create_task(self, session: Session, extra_mcp_configs: dict[str, Any] | None = None) -> Task:
        """Delegate to task factory."""
        return await self._task_factory.create_task(session, extra_mcp_configs=extra_mcp_configs)

    async def _classify_intent_with_context(
        self,
        message: str,
        session: Session,
        attachments: list[dict] | None = None,
        skills: list[str] | None = None,
    ) -> AgentMode | None:
        """Delegate to task factory."""
        return await self._task_factory.classify_intent_with_context(
            message=message, session=session, attachments=attachments, skills=skills
        )

    async def _resolve_user_attachments(self, attachments: list[dict] | None, user_id: str) -> list[FileInfo] | None:
        """Delegate to task factory."""
        return await self._task_factory.resolve_user_attachments(attachments, user_id)

    async def _build_reactivation_context(self, session_id: str) -> str | None:
        """Delegate to task factory."""
        return await self._task_factory.build_reactivation_context(session_id)

    # ------------------------------------------------------------------
    # Public interface (unchanged)
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Clean up all Agent's resources."""
        logger.info("Starting to close all Agents")
        await self._task_cls.destroy()
        logger.info("All agents closed successfully")

    async def stop_session(self, session_id: str) -> None:
        """Stop a session and destroy its sandbox."""
        await self._lifecycle.stop_session(session_id)

    async def pause_session(self, session_id: str) -> bool:
        """Pause a session (for user takeover)."""
        return await self._lifecycle.pause_session(session_id)

    async def resume_session(
        self, session_id: str, context: str | None = None, persist_login_state: bool | None = None
    ) -> bool:
        """Resume a paused session (after user takeover)."""
        return await self._lifecycle.resume_session(
            session_id, context=context, persist_login_state=persist_login_state
        )

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
        """Chat with an agent.

        Args:
            cancel_event: Event that signals cancellation (e.g., SSE disconnect).
                Domain service checks this periodically and cancels active task execution.
        """

        # Acquire concurrency slot -- blocks when all sandbox slots are busy.
        await self._agent_concurrency.acquire()

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
                if isinstance(event, DoneEvent):
                    terminal_status = SessionStatus.COMPLETED
                    await self._session_repository.update_status(session_id, SessionStatus.COMPLETED)
                    yield event
                    break
                if isinstance(event, ErrorEvent):
                    terminal_status = SessionStatus.FAILED
                    await self._session_repository.update_status(session_id, SessionStatus.FAILED)
                    self._record_conversation_turn(event, session_id, user_id)
                    yield event
                    break

                # Record conversation turn for real-time context vectorization
                self._record_conversation_turn(event, session_id, user_id)

                yield event
                if isinstance(event, WaitEvent):
                    break

            # If the task completed without producing any events, emit a DoneEvent
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
            self._agent_concurrency.release()
            await self._session_repository.update_unread_message_count(session_id, 0)
            # Flush remaining conversation context turns (non-blocking)
            if self._conversation_context_service:
                import contextlib

                with contextlib.suppress(Exception):
                    await self._conversation_context_service.flush_remaining()
                    self._conversation_context_service.reset_session_state()
                    self._turn_counter = 0
            # Extract and store memories from session (fire-and-forget)
            if self._memory_service:
                import contextlib

                with contextlib.suppress(Exception):
                    task = asyncio.ensure_future(self._extract_session_memories(session_id, user_id))
                    self._register_background_task(task)

    def _record_conversation_turn(self, event: BaseEvent, session_id: str, user_id: str) -> None:
        """Fire-and-forget: extract and buffer a conversation turn from an SSE event.

        Non-blocking — errors are suppressed. The turn is buffered in the
        ConversationContextService and batch-flushed to Qdrant periodically.
        """
        if not self._conversation_context_service:
            return

        try:
            turn = self._conversation_context_service.extract_turn_from_event(
                event, session_id, user_id, self._turn_counter
            )
            if turn:
                self._turn_counter += 1
                _task = asyncio.create_task(self._conversation_context_service.record_turn(turn))  # noqa: RUF006 — fire-and-forget by design
        except Exception:
            logger.debug("Failed to record conversation turn", exc_info=True)

    async def _extract_session_memories(self, session_id: str, user_id: str) -> None:
        """Extract and store memories from a completed session.

        Called asynchronously after session completion. Failures are logged
        but never propagate -- memory extraction is non-critical.
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
                    # Keep updating -- last assistant message is the final result
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
