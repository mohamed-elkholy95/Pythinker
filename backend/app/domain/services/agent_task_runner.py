import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, Optional

from pydantic import TypeAdapter

from app.core.config import FlowMode, get_settings
from app.domain.external.browser import Browser
from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task, TaskRunner
from app.domain.models.event import (
    AgentEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    FileToolContent,
    FlowSelectionEvent,
    MCPHealthEvent,
    MessageEvent,
    ModeChangeEvent,
    ReportEvent,
    ResearchModeEvent,
    TitleEvent,
    ToolEvent,
    ToolProgressEvent,
    ToolStatus,
    ToolStreamEvent,
    WaitEvent,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.session import AgentMode, ResearchMode, SessionStatus
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.comparison_chart_generator import ComparisonChartGenerator
from app.domain.services.file_sync_manager import EventWithAttachments, FileSyncManager
from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.flows.fast_search import FastSearchFlow
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.orchestration.coordinator_flow import (
    CoordinatorFlow,
    CoordinatorMode,
    create_coordinator_flow,
)
from app.domain.services.plotly_chart_orchestrator import PlotlyChartOrchestrator
from app.domain.services.tool_content_handlers import get_content_handler_registry
from app.domain.services.tool_event_handler import ToolEventHandler
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.mcp_registry import get_mcp_registry
from app.domain.utils.cancellation import CancellationToken
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.application.services.screenshot_service import ScreenshotCaptureService
    from app.domain.models.state_manifest import StateManifest
    from app.domain.services.agent_factory import PythinkerAgentFactory
    from app.domain.services.attention_injector import AttentionInjector
    from app.domain.services.context_manager import SandboxContextManager
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class AgentTaskRunner(TaskRunner):
    """Agent task that can be cancelled.

    Supports multiple execution modes:
    - AGENT: Plan-Act flow with optional multi-agent step dispatch
    - DISCUSS: Simple conversational flow
    - COORDINATOR: Full multi-agent swarm execution (when enabled)
    """

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        llm: LLM,
        sandbox: Sandbox,
        browser: Browser,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        mode: AgentMode = AgentMode.AGENT,
        research_mode: ResearchMode = ResearchMode.DEEP_RESEARCH,
        enable_multi_agent: bool = True,
        enable_coordinator: bool = False,
        memory_service: Optional["MemoryService"] = None,
        flow_mode: FlowMode = FlowMode.PLAN_ACT,
        mongodb_db: Any | None = None,  # MongoDB database for workflow checkpointing
        agent_factory: Optional["PythinkerAgentFactory"] = None,
        usage_recorder: Callable[..., Coroutine[Any, Any, None]] | None = None,
        extra_mcp_configs: dict[str, Any] | None = None,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._usage_recorder = usage_recorder
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._search_engine = search_engine
        self._repository = agent_repository
        self._session_repository = session_repository
        self._json_parser = json_parser
        self._file_storage = file_storage
        self._mcp_repository = mcp_repository
        self._mcp_tool = MCPTool()
        self._extra_mcp_configs = extra_mcp_configs or {}
        self._mode = mode
        self._research_mode = research_mode
        self._deal_mode_emitted: bool = False

        # Multi-agent configuration
        self._enable_multi_agent = enable_multi_agent

        # Unified flow mode (resolves legacy booleans)
        self._flow_selection_reason: str | None = None
        if flow_mode == FlowMode.COORDINATOR:
            self._flow_mode = FlowMode.COORDINATOR
        elif enable_coordinator:
            self._flow_mode = FlowMode.COORDINATOR
            self._flow_selection_reason = "legacy_enable_coordinator"
        else:
            self._flow_mode = FlowMode.PLAN_ACT

        # Legacy compat
        self._enable_coordinator = self._flow_mode == FlowMode.COORDINATOR

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service

        # MongoDB database for workflow checkpointing
        self._mongodb_db = mongodb_db

        # Knowledge base service (RAG-Anything; None if feature disabled)
        try:
            from app.interfaces.dependencies import get_knowledge_base_service

            self._knowledge_base_service = get_knowledge_base_service()
        except Exception:
            self._knowledge_base_service = None

        # Prompt profile repository for DSPy/GEPA optimization (None if feature disabled)
        try:
            from app.interfaces.dependencies import get_prompt_profile_repository

            self._prompt_profile_repo = get_prompt_profile_repository()
        except Exception:
            self._prompt_profile_repo = None

        # Pythinker-style agent factory and components
        self._agent_factory: PythinkerAgentFactory | None = agent_factory
        self._manifest: StateManifest | None = None
        self._context_manager: SandboxContextManager | None = None
        self._attention_injector: AttentionInjector | None = None
        self._initialized: bool = False

        # Screenshot capture service (created after sandbox init if enabled)
        self._screenshot_service: ScreenshotCaptureService | None = None
        self._background_tasks: set[asyncio.Task[object]] = set()

        # Current task description for attention manipulation
        self.current_task: str | None = None

        # Tool metadata caches for enhanced UI
        self._tool_start_times: dict[str, float] = {}
        self._file_before_cache: dict[str, str] = {}
        self._pending_tool_calls: dict[str, dict] = {}
        self._cancel_event = asyncio.Event()
        self._cancel_token = CancellationToken(event=self._cancel_event, session_id=self._session_id)

        # Tool event handler for action/observation metadata enrichment
        self._tool_event_handler = ToolEventHandler()
        # Per-tool content handler registry (replaces elif chain)
        self._content_handlers = get_content_handler_registry()
        self._comparison_chart_generator = ComparisonChartGenerator()
        # Phase 4: Plotly chart orchestrator (feature-flagged)
        self._plotly_chart_orchestrator = PlotlyChartOrchestrator(sandbox=self._sandbox, session_id=session_id)

        # File sync manager — delegated from AgentTaskRunner (Phase 3C extraction)
        self._file_sync_manager = FileSyncManager(
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            sandbox=sandbox,
            file_storage=file_storage,
            session_repository=session_repository,
        )

        # Initialize flows based on mode
        self._plan_act_flow: PlanActFlow | None = None
        self._discuss_flow: DiscussFlow | None = None
        self._coordinator_flow: CoordinatorFlow | None = None
        self._fast_search_flow: FastSearchFlow | None = None

        if mode == AgentMode.AGENT:
            if research_mode == ResearchMode.FAST_SEARCH:
                self._init_fast_search_flow()
            elif self._flow_mode == FlowMode.COORDINATOR:
                self._init_coordinator_flow()
            else:
                self._init_plan_act_flow()
        else:
            self._init_discuss_flow()

        logger.info(
            "Flow selected: mode=%s, research_mode=%s, flow=%s, session=%s, reason=%s",
            mode.value,
            research_mode.value,
            self._flow_mode.value,
            session_id,
            self._flow_selection_reason,
        )

    def _fire_and_forget(self, coro: object) -> None:
        """Create a fire-and-forget task with proper reference tracking."""
        task = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[object]) -> None:
        """Consume background task outcomes to avoid unretrieved-exception noise."""
        self._background_tasks.discard(task)
        with suppress(asyncio.CancelledError):
            error = task.exception()
            if error is not None:
                logger.warning("Background task failed for Agent %s: %s", self._agent_id, error)

    def request_cancellation(self) -> None:
        """Signal cooperative cancellation to long-running flow operations."""
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            logger.info("Cancellation requested for Agent %s session %s", self._agent_id, self._session_id)

    def _init_plan_act_flow(self) -> None:
        """Initialize PlanActFlow for Agent mode"""
        if self._plan_act_flow is None:
            settings = get_settings()
            from app.core.config import get_feature_flags

            feature_flags = get_feature_flags()
            rapidfuzz_matcher = None
            symspell_provider = None

            if settings.typo_correction_rapidfuzz_enabled:
                try:
                    from app.infrastructure.text.rapidfuzz_matcher import RapidFuzzMatcher

                    rapidfuzz_matcher = RapidFuzzMatcher()
                except Exception as exc:
                    logger.warning("RapidFuzz matcher unavailable; falling back to difflib: %s", exc)

            if settings.typo_correction_symspell_enabled:
                try:
                    from app.infrastructure.text.symspell_provider import SymSpellProvider

                    symspell_provider = SymSpellProvider(
                        dictionary_path=settings.typo_correction_symspell_dictionary_path,
                        bigram_path=settings.typo_correction_symspell_bigram_path,
                        max_edit_distance=settings.typo_correction_symspell_max_edit_distance,
                        prefix_length=settings.typo_correction_symspell_prefix_length,
                    )
                except Exception as exc:
                    logger.warning("SymSpell provider unavailable; falling back to base validator: %s", exc)

            from app.infrastructure.observability.typo_correction_analytics import (
                get_typo_correction_analytics,
            )

            typo_analytics = get_typo_correction_analytics()

            # Scraper adapter — injected into flows so domain layer stays infra-free
            _scraper = None
            try:
                from app.infrastructure.external.scraper import get_scraping_adapter

                _scraper = get_scraping_adapter()
            except Exception as exc:
                logger.debug("Scraping adapter unavailable: %s", exc)

            # DealFinder adapter — injected so domain layer stays infra-free.
            # Auto-enabled when user intent is deal-related (even if deal_scraper_enabled=False).
            _deal_finder = None
            _deal_intent_detected = False
            if _scraper and self._search_engine:
                _should_enable_deals = settings.deal_scraper_enabled
                if not _should_enable_deals:
                    # Auto-detect deal intent from the latest user message
                    from app.domain.services.prompts.deal_finding import detect_deal_intent

                    _latest_msg = ""
                    if hasattr(self, "_messages") and self._messages:
                        _latest_msg = self._messages[-1].content or ""
                    _deal_intent_detected = detect_deal_intent(_latest_msg)
                    _should_enable_deals = _deal_intent_detected

                if _should_enable_deals:
                    try:
                        from app.infrastructure.external.deal_finder import get_deal_finder_adapter

                        _deal_finder = get_deal_finder_adapter(scraper=_scraper, search_engine=self._search_engine)
                        if _deal_intent_detected:
                            logger.info("DealFinder auto-enabled via intent detection for session %s", self._session_id)
                    except Exception as exc:
                        logger.warning("DealFinder adapter unavailable: %s", exc)

            # WP-6: CheckpointManager for cross-restart workflow persistence.
            # Inject a real MongoDB collection so checkpoints survive process restarts.
            # Falls back gracefully to in-memory storage when MongoDB is unavailable.
            _checkpoint_manager = None
            if settings.feature_workflow_checkpointing:
                try:
                    from app.domain.services.flows.checkpoint_manager import CheckpointManager
                    from app.infrastructure.storage.mongodb import get_mongodb

                    _mongo_checkpoint_collection = None
                    try:
                        _mongo_checkpoint_collection = get_mongodb().database["workflow_checkpoints"]
                    except Exception as _mc_err:
                        logger.debug(
                            "MongoDB checkpoint collection unavailable, using in-memory fallback: %s",
                            _mc_err,
                        )

                    _checkpoint_manager = CheckpointManager(
                        mongodb_collection=_mongo_checkpoint_collection,
                        ttl_hours=24,
                        auto_cleanup=True,
                    )
                    logger.debug(
                        "CheckpointManager initialized for session %s (persistent=%s)",
                        self._session_id,
                        _mongo_checkpoint_collection is not None,
                    )
                except Exception as exc:
                    logger.warning("CheckpointManager unavailable: %s", exc)

            self._plan_act_flow = PlanActFlow(
                self._agent_id,
                self._repository,
                self._session_id,
                self._session_repository,
                self._llm,
                self._sandbox,
                self._browser,
                self._json_parser,
                self._mcp_tool,
                self._search_engine,
                cdp_url=self._sandbox.cdp_url,
                enable_verification=settings.enable_plan_verification,
                enable_multi_agent=self._enable_multi_agent,
                memory_service=self._memory_service,
                user_id=self._user_id,
                file_sweep_callback=self._sweep_workspace_files,
                feature_flags=feature_flags,
                browser_agent_enabled=settings.browser_agent_enabled,
                rapidfuzz_matcher=rapidfuzz_matcher,
                symspell_provider=symspell_provider,
                correction_event_sink=typo_analytics.record_event,
                feedback_lookup=typo_analytics.get_feedback_override,
                cancel_token=self._cancel_token,
                research_mode=self._research_mode.value,
                knowledge_base_service=self._knowledge_base_service,
                prompt_profile_repo=self._prompt_profile_repo,
                scraper=_scraper,
                deal_finder=_deal_finder,
                checkpoint_manager=_checkpoint_manager,
            )
            # Inject circuit breaker for tool-level failure protection
            try:
                from app.infrastructure.adapters.circuit_breaker_adapter import ToolCircuitBreakerAdapter

                self._plan_act_flow.set_circuit_breaker(ToolCircuitBreakerAdapter())
            except Exception as e:
                logger.debug(f"Circuit breaker adapter unavailable: {e}")

            logger.debug(
                f"Initialized PlanActFlow for agent {self._agent_id} "
                f"(verification={settings.enable_plan_verification}, multi_agent={self._enable_multi_agent}, "
                f"memory_service={'enabled' if self._memory_service else 'disabled'})"
            )

    def _init_coordinator_flow(self) -> None:
        """Initialize CoordinatorFlow for full multi-agent swarm execution"""
        if self._coordinator_flow is None:
            self._coordinator_flow = create_coordinator_flow(
                agent_id=self._agent_id,
                session_id=self._session_id,
                agent_repository=self._repository,
                session_repository=self._session_repository,
                llm=self._llm,
                sandbox=self._sandbox,
                browser=self._browser,
                json_parser=self._json_parser,
                mcp_tool=self._mcp_tool,
                search_engine=self._search_engine,
                mode=CoordinatorMode.AUTO,
            )
            logger.info(f"Initialized CoordinatorFlow for agent {self._agent_id}")

    def _init_discuss_flow(self) -> None:
        """Initialize DiscussFlow for Discuss mode"""
        if self._discuss_flow is None:
            settings = get_settings()

            # Inject conversation context and memory services for cross-session recall
            conversation_context_service = None
            try:
                from app.domain.services.conversation_context_service import get_conversation_context_service

                conversation_context_service = get_conversation_context_service()
            except Exception:
                logger.debug("Conversation context service unavailable for DiscussFlow")

            self._discuss_flow = DiscussFlow(
                self._agent_id,
                self._repository,
                self._session_id,
                self._session_repository,
                self._llm,
                self._json_parser,
                self._search_engine,
                default_language=settings.default_language,
                memory_service=self._memory_service,
                conversation_context_service=conversation_context_service,
                user_id=self._user_id,
            )
            logger.debug(f"Initialized DiscussFlow for agent {self._agent_id}")

    def _init_fast_search_flow(self) -> None:
        """Initialize FastSearchFlow for fast search mode"""
        if self._fast_search_flow is None:
            self._fast_search_flow = FastSearchFlow(
                session_id=self._session_id,
                llm=self._llm,
                search_engine=self._search_engine,
            )
            logger.debug(f"Initialized FastSearchFlow for session {self._session_id}")

    async def initialize(self) -> None:
        """Initialize Pythinker-style components from the agent factory.

        This method should be called before running tasks to set up
        the state manifest, context manager, and attention injector
        for Pythinker-style context management.

        If no agent_factory was provided, this method is a no-op.
        The method is idempotent - calling it multiple times has no effect.
        """
        if self._initialized:
            return

        if self._agent_factory is None:
            logger.debug(f"Agent {self._agent_id}: No agent factory provided, skipping Pythinker initialization")
            return

        components = self._agent_factory.get_session_components(self._session_id)
        self._manifest = components.get("manifest")
        self._context_manager = components.get("context_manager")
        self._attention_injector = components.get("attention_injector")
        self._initialized = True

        logger.info(f"Agent {self._agent_id}: Initialized Pythinker components for session {self._session_id}")

    async def _set_current_task(self, task_description: str) -> None:
        """Set the current task description for attention manipulation.

        This stores the task locally and, if a context manager is available,
        sets the goal in the context manager for attention manipulation.

        Args:
            task_description: The task description to set.
        """
        self.current_task = task_description

        if self._context_manager is not None:
            await self._context_manager.set_goal(task_description)
            logger.debug(f"Agent {self._agent_id}: Set goal in context manager: {task_description[:50]}...")

    async def _switch_to_agent_mode(self, task_description: str) -> None:
        """Switch from Discuss mode to Agent mode"""
        logger.info(f"Switching to Agent mode for task: {task_description}")
        self._mode = AgentMode.AGENT

        # Initialize appropriate flow based on configuration
        # Note: mode switch always goes to plan_act (deep research), not fast search
        if self._flow_mode == FlowMode.COORDINATOR:
            self._init_coordinator_flow()
        else:
            self._init_plan_act_flow()

        await self._session_repository.update_mode(self._session_id, AgentMode.AGENT)

    @property
    def _flow(self) -> BaseFlow | None:
        """Get the current flow based on mode, research mode, and configuration."""
        if self._mode == AgentMode.AGENT:
            if self._research_mode == ResearchMode.FAST_SEARCH and self._fast_search_flow:
                return self._fast_search_flow
            if self._flow_mode == FlowMode.COORDINATOR and self._coordinator_flow:
                return self._coordinator_flow
            return self._plan_act_flow
        return self._discuss_flow

    async def _put_and_add_event(self, task: Task, event: AgentEvent) -> None:
        event_id = await task.output_stream.put(event.model_dump_json())
        event.id = event_id
        await self._session_repository.add_event(self._session_id, event)

    async def _pop_event(self, task: Task) -> AgentEvent | None:
        event_id, event_str = await task.input_stream.pop()
        if event_str is None:
            logger.warning(f"Agent {self._agent_id} received empty message")
            return None
        event = TypeAdapter(AgentEvent).validate_json(event_str)
        event.id = event_id
        return event

    # ── File Sync (delegated to FileSyncManager — Phase 3C extraction) ──

    def _infer_content_type(self, file_path: str, existing_content_type: str | None = None) -> str | None:
        """Infer MIME type from file extension if not already known."""
        return self._file_sync_manager.infer_content_type(file_path, existing_content_type)

    async def _sync_file_to_storage(self, file_path: str, content_type: str | None = None) -> FileInfo | None:
        """Download a file from sandbox and upload to storage (delegated to FileSyncManager)."""
        return await self._file_sync_manager.sync_file_to_storage(file_path, content_type)

    async def _sync_file_to_storage_with_retry(
        self,
        file_path: str,
        content_type: str | None = None,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.2,
    ) -> FileInfo | None:
        """Sync file to storage with retries (delegated to FileSyncManager)."""
        return await self._file_sync_manager.sync_file_to_storage_with_retry(
            file_path, content_type, max_attempts, initial_delay_seconds
        )

    async def _sync_file_to_sandbox(self, file_id: str) -> FileInfo | None:
        """Download file from storage to sandbox (delegated to FileSyncManager)."""
        return await self._file_sync_manager.sync_file_to_sandbox(file_id)

    async def _sweep_workspace_files(self) -> list[FileInfo]:
        """Discover and sync deliverable files in workspace (delegated to FileSyncManager)."""
        return await self._file_sync_manager.sweep_workspace_files()

    async def _sync_event_attachments_to_storage(self, event: EventWithAttachments) -> None:
        """Sync event attachments to storage (delegated to FileSyncManager)."""
        await self._file_sync_manager.sync_event_attachments_to_storage(event)

    async def _ensure_report_file(self, event: ReportEvent) -> None:
        """Persist report content as a file in the sandbox and attach it to the event."""
        if not self._sandbox:
            return
        if not event.content or not event.content.strip():
            return

        existing = event.attachments or []

        # Include the full pre-summarization markdown (from the agent's file_write
        # during execution) as an attachment so users get the complete original report
        # alongside the summarized version.
        full_content = self._get_pre_trim_report_content()
        if full_content and full_content.strip() and full_content.strip() != event.content.strip():
            full_name = f"full-report-{event.id}.md"
            if not self._has_attachment(existing, full_name):
                full_path = f"/workspace/{self._session_id}/{full_name}"
                try:
                    result = await self._sandbox.file_write(file=full_path, content=full_content)
                    write_ok = result is None or not hasattr(result, "success") or result.success
                    if write_ok:
                        full_size = len(full_content.encode("utf-8"))
                        full_info = FileInfo(
                            filename=full_name,
                            file_path=full_path,
                            size=full_size,
                            content_type="text/markdown",
                            user_id=self._user_id,
                            metadata={"is_report": True, "is_full_report": True, "title": event.title},
                        )
                        existing = [*existing, full_info]
                        logger.info(
                            "Attached full pre-summarization report (%d chars) for session=%s",
                            full_size,
                            self._session_id,
                        )
                    else:
                        logger.warning("Agent %s: Failed to write full report file (success=False)", self._agent_id)
                except Exception as e:
                    logger.warning("Agent %s: Failed to write full report file: %s", self._agent_id, e)

        expected_name = f"report-{event.id}.md"
        if not self._has_attachment(existing, expected_name):
            file_path = f"/workspace/{self._session_id}/{expected_name}"
            try:
                result = await self._sandbox.file_write(file=file_path, content=event.content)
                if result is not None and hasattr(result, "success") and not result.success:
                    logger.warning(f"Agent {self._agent_id}: Failed to write report file '{file_path}' (success=False)")
                    return
            except Exception as e:
                logger.warning(f"Agent {self._agent_id}: Failed to write report file '{file_path}': {e}")
                return

            report_size = len(event.content.encode("utf-8"))
            report_info = FileInfo(
                filename=expected_name,
                file_path=file_path,
                size=report_size,
                content_type="text/markdown",
                user_id=self._user_id,
                metadata={"is_report": True, "title": event.title},
            )
            existing = [*existing, report_info]

        chart_mode = self._resolve_chart_generation_mode()
        if chart_mode in {"skip", "regenerate"}:
            existing, removed = self._strip_comparison_chart_attachments(existing, event.id)
            if removed:
                logger.info(
                    "Removed %s existing comparison chart attachment(s) for report_id=%s mode=%s session=%s",
                    removed,
                    event.id,
                    chart_mode,
                    self._session_id,
                )

        if chart_mode == "skip":
            logger.info(
                "Skipping comparison chart generation for report_id=%s session=%s due to user override",
                event.id,
                self._session_id,
            )
            event.attachments = existing
            return

        existing = await self._ensure_comparison_chart_file(
            event,
            existing,
            force_generation=chart_mode in {"force", "regenerate"},
            generation_mode=chart_mode,
        )
        event.attachments = existing

    async def _ensure_comparison_chart_file(
        self,
        event: ReportEvent,
        attachments: list[FileInfo],
        *,
        force_generation: bool,
        generation_mode: str,
    ) -> list[FileInfo]:
        """Generate and attach comparison chart(s) when report content contains comparison data.

        Phase 4: Uses Plotly (HTML+PNG) if feature flag enabled, otherwise uses legacy SVG.
        """
        settings = get_settings()

        # Phase 4: Use Plotly if feature flag enabled
        if settings.feature_plotly_charts_enabled:
            return await self._ensure_plotly_chart_files(event, attachments, force_generation, generation_mode)

        # Legacy SVG path (Phase 6 will remove this)
        return await self._ensure_legacy_svg_chart(event, attachments, force_generation, generation_mode)

    async def _ensure_plotly_chart_files(
        self,
        event: ReportEvent,
        attachments: list[FileInfo],
        force_generation: bool,
        generation_mode: str,
    ) -> list[FileInfo]:
        """Generate Plotly HTML+PNG chart files (Phase 4)."""
        html_name = f"comparison-chart-{event.id}.html"
        png_name = f"comparison-chart-{event.id}.png"

        # Check if already generated
        if self._has_attachment(attachments, html_name) or self._has_attachment(attachments, png_name):
            return attachments

        # Run Plotly chart orchestrator
        chart_result = await self._plotly_chart_orchestrator.generate_chart(
            report_title=event.title,
            markdown_content=event.content,
            report_id=event.id,
            force_generation=force_generation,
        )

        if chart_result is None:
            if force_generation:
                logger.info(
                    "Plotly chart forced but no chartable table found for report_id=%s session=%s",
                    event.id,
                    self._session_id,
                )
            return attachments

        # Create FileInfo for HTML
        html_info = FileInfo(
            filename=html_name,
            file_path=chart_result.html_path,
            size=chart_result.html_size,
            content_type="text/html",
            user_id=self._user_id,
            metadata={
                "is_comparison_chart": True,
                "chart_engine": "plotly",
                "chart_format": "plotly_html_png",
                "chart_kind": chart_result.chart_kind,
                "metric_name": chart_result.metric_name,
                "source_report_id": event.id,
                "source_report_title": event.title,
                "data_points": chart_result.data_points,
                "generation_mode": generation_mode,
                "generated_at_unix_ms": int(time.time() * 1000),
            },
        )

        # Create FileInfo for PNG
        png_info = FileInfo(
            filename=png_name,
            file_path=chart_result.png_path,
            size=chart_result.png_size,
            content_type="image/png",
            user_id=self._user_id,
            metadata={
                "is_comparison_chart": True,
                "chart_engine": "plotly",
                "chart_format": "plotly_html_png",
                "chart_kind": chart_result.chart_kind,
                "metric_name": chart_result.metric_name,
                "source_report_id": event.id,
                "source_report_title": event.title,
                "data_points": chart_result.data_points,
                "generation_mode": generation_mode,
                "generated_at_unix_ms": int(time.time() * 1000),
            },
        )

        logger.info(
            "Plotly chart generated: session=%s report_id=%s mode=%s kind=%s metric=%s points=%s html=%s png=%s",
            self._session_id,
            event.id,
            generation_mode,
            chart_result.chart_kind,
            chart_result.metric_name or "n/a",
            chart_result.data_points,
            chart_result.html_size,
            chart_result.png_size,
        )
        return [*attachments, html_info, png_info]

    async def _ensure_legacy_svg_chart(
        self,
        event: ReportEvent,
        attachments: list[FileInfo],
        force_generation: bool,
        generation_mode: str,
    ) -> list[FileInfo]:
        """Generate legacy SVG chart (Phase 6 will remove this)."""
        chart_name = f"comparison-chart-{event.id}.svg"
        if self._has_attachment(attachments, chart_name):
            return attachments

        chart = self._comparison_chart_generator.generate_chart(
            report_title=event.title,
            markdown_content=event.content,
            force_generation=force_generation,
        )
        if chart is None:
            if force_generation:
                logger.info(
                    "Comparison chart forced but no chartable table found for report_id=%s session=%s",
                    event.id,
                    self._session_id,
                )
            return attachments

        file_path = f"/home/ubuntu/{chart_name}"
        try:
            result = await self._sandbox.file_write(file=file_path, content=chart.svg_content)
            if result is not None and hasattr(result, "success") and not result.success:
                logger.warning(f"Agent {self._agent_id}: Failed to write chart file '{file_path}' (success=False)")
                return attachments
        except Exception as e:
            logger.warning(f"Agent {self._agent_id}: Failed to write chart file '{file_path}': {e}")
            return attachments

        chart_info = FileInfo(
            filename=chart_name,
            file_path=file_path,
            size=len(chart.svg_content.encode("utf-8")),
            content_type="image/svg+xml",
            user_id=self._user_id,
            metadata={
                "is_comparison_chart": True,
                "chart_kind": chart.chart_kind,
                "metric_name": chart.metric_name,
                "source_report_id": event.id,
                "source_report_title": event.title,
                "data_points": chart.data_points,
                "chart_width": chart.width,
                "chart_height": chart.height,
                "chart_format": chart.output_format,
                "generation_mode": generation_mode,
                "generated_at_unix_ms": int(time.time() * 1000),
            },
        )
        logger.info(
            "Comparison chart generated: session=%s report_id=%s mode=%s kind=%s metric=%s points=%s size=%sx%s",
            self._session_id,
            event.id,
            generation_mode,
            chart.chart_kind,
            chart.metric_name or "n/a",
            chart.data_points,
            chart.width,
            chart.height,
        )
        return [*attachments, chart_info]

    def _has_attachment(self, attachments: list[FileInfo], expected_name: str) -> bool:
        """Check if an attachment exists by filename or path suffix."""
        for attachment in attachments:
            if attachment.filename == expected_name:
                return True
            if attachment.file_path and attachment.file_path.endswith(expected_name):
                return True
        return False

    def _get_pre_trim_report_content(self) -> str | None:
        """Retrieve the full pre-summarization markdown from the executor's cache.

        The executor caches file_write content before token trimming so that the
        original report written during execution survives aggressive memory pruning.
        This method exposes that cache for inclusion as an attachment.
        """
        flow = self._flow
        if flow and hasattr(flow, "executor"):
            executor = flow.executor
            if hasattr(executor, "_pre_trim_report_cache"):
                cache = executor._pre_trim_report_cache
                if isinstance(cache, str):
                    return cache
        return None

    def _resolve_chart_generation_mode(self) -> str:
        """Resolve user override for chart generation from current task text."""
        task_text = self.current_task or ""
        if not task_text.strip():
            return "auto"

        directive_pattern = re.compile(
            r"(?:^|\s|\[)(?:--)?chart\s*[:=]\s*(skip|off|disable|none|force|on|enable|regenerate|refresh)\b",
            re.IGNORECASE,
        )
        explicit = list(directive_pattern.finditer(task_text))
        if explicit:
            value = explicit[-1].group(1).lower()
            if value in {"skip", "off", "disable", "none"}:
                return "skip"
            if value in {"regenerate", "refresh"}:
                return "regenerate"
            return "force"

        lowered = task_text.lower()
        if any(phrase in lowered for phrase in ("no chart", "without chart", "skip chart", "disable chart")):
            return "skip"
        if any(phrase in lowered for phrase in ("regenerate chart", "refresh chart", "rebuild chart")):
            return "regenerate"
        if any(phrase in lowered for phrase in ("include chart", "with chart", "add chart", "force chart")):
            return "force"

        return "auto"

    def _strip_comparison_chart_attachments(
        self, attachments: list[FileInfo], report_id: str
    ) -> tuple[list[FileInfo], int]:
        """Remove comparison chart attachment(s) for a report from an attachment list."""
        remaining: list[FileInfo] = []
        removed = 0
        for attachment in attachments:
            if self._is_comparison_chart_attachment(attachment, report_id):
                removed += 1
                continue
            remaining.append(attachment)
        return remaining, removed

    def _is_comparison_chart_attachment(self, attachment: FileInfo, report_id: str) -> bool:
        """Return True if attachment represents a generated comparison chart for this report."""
        expected_name = f"comparison-chart-{report_id}.svg"
        if attachment.filename == expected_name:
            return True
        if attachment.file_path and attachment.file_path.endswith(expected_name):
            return True
        metadata = attachment.metadata or {}
        return bool(metadata.get("is_comparison_chart")) and metadata.get("source_report_id") == report_id

    def _get_tool_execution_agent(self):
        """Return an agent instance capable of invoking tools."""
        flow = self._flow
        if hasattr(flow, "executor") and flow.executor:
            return flow.executor
        if hasattr(flow, "_agent") and flow._agent:
            return flow._agent
        if hasattr(flow, "agent") and flow.agent:
            return flow.agent
        return None

    async def execute_pending_action(
        self,
        task: Task,
        action_id: str,
        accept: bool,
    ) -> None:
        """Execute a pending tool action deterministically after confirmation."""
        session = await self._session_repository.find_by_id(self._session_id)
        if not session or not session.pending_action:
            logger.warning("No pending action found for session %s", self._session_id)
            return

        pending = session.pending_action
        if pending.get("tool_call_id") != action_id:
            logger.warning(
                "Pending action id mismatch for session %s: %s != %s",
                self._session_id,
                pending.get("tool_call_id"),
                action_id,
            )

        if not accept:
            await self._session_repository.update_pending_action(
                self._session_id,
                None,
                "rejected",
            )
            reject_event = ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=pending.get("tool_call_id"),
                tool_name=pending.get("tool_name"),
                function_name=pending.get("function_name"),
                function_args=pending.get("function_args", {}),
                function_result=ToolResult(success=False, message="Action rejected by user."),
                security_risk=pending.get("security_risk"),
                security_reason=pending.get("security_reason"),
                security_suggestions=pending.get("security_suggestions"),
                confirmation_state="rejected",
            )
            await self._put_and_add_event(task, reject_event)
            await self._put_and_add_event(
                task,
                MessageEvent(message="Action rejected by user.", role="assistant"),
            )
            return

        agent = self._get_tool_execution_agent()
        if not agent:
            logger.error("No tool execution agent available for session %s", self._session_id)
            return

        function_name = pending.get("function_name")
        function_args = pending.get("function_args", {})
        tool_call_id = pending.get("tool_call_id")
        tool_name = pending.get("tool_name")

        calling_event = ToolEvent(
            status=ToolStatus.CALLING,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            security_risk=pending.get("security_risk"),
            security_reason=pending.get("security_reason"),
            security_suggestions=pending.get("security_suggestions"),
            confirmation_state="confirmed",
        )
        await self._handle_tool_event(calling_event)
        await self._put_and_add_event(task, calling_event)

        try:
            tool = agent.get_tool(function_name)
            result = await agent.invoke_tool(
                tool,
                function_name,
                function_args,
                skip_security=True,
            )
        except Exception as exc:
            result = ToolResult(success=False, message=str(exc))

        called_event = ToolEvent(
            status=ToolStatus.CALLED,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            function_result=result,
            security_risk=pending.get("security_risk"),
            security_reason=pending.get("security_reason"),
            security_suggestions=pending.get("security_suggestions"),
            confirmation_state="confirmed",
        )
        await self._handle_tool_event(called_event)
        await self._put_and_add_event(task, called_event)

        await self._session_repository.update_pending_action(
            self._session_id,
            None,
            "confirmed",
        )

    async def _sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """Sync message attachments to sandbox (delegated to FileSyncManager)."""
        await self._file_sync_manager.sync_message_attachments_to_sandbox(event)

    @asynccontextmanager
    async def _usage_context(self):
        """Ensure LLM usage is attributed to the current user/session."""
        if self._user_id and self._session_id:
            async with UsageContextManager(
                user_id=self._user_id,
                session_id=self._session_id,
            ):
                yield
        else:
            yield

    async def _record_tool_call_usage(self) -> None:
        """Record tool call usage for usage dashboard metrics."""
        if not self._user_id or not self._usage_recorder:
            return
        try:
            await self._usage_recorder(
                user_id=self._user_id,
                session_id=self._session_id,
            )
        except Exception as e:
            logger.debug(f"Failed to record tool usage for Agent {self._agent_id}: {e}")

    async def _handle_tool_event(self, event: ToolEvent) -> None:
        """Enrich tool event with metadata and generate tool content.

        Uses ToolEventHandler for action/observation metadata enrichment,
        then handles async tool-specific content generation.
        """
        try:
            # Enrich action metadata using ToolEventHandler (action_type, command, cwd, file_path)
            self._tool_event_handler.enrich_action_metadata(event)

            if event.status == ToolStatus.CALLED and event.tool_name != "message":
                await self._record_tool_call_usage()

            # Handle CALLING status for streaming preview (file_write shows content being generated)
            if event.status == ToolStatus.CALLING:
                # Capture screenshot before visual tool execution
                if self._screenshot_service and event.tool_name in (
                    "browser",
                    "browser_agent",
                    "shell",
                    "code_executor",
                ):
                    self._screenshot_service.set_tool_context(
                        tool_call_id=event.tool_call_id,
                        tool_name=event.tool_name,
                        function_name=event.function_name,
                        action_type=event.action_type,
                    )
                    from app.domain.models.screenshot import ScreenshotTrigger

                    self._fire_and_forget(
                        self._screenshot_service.capture(
                            ScreenshotTrigger.TOOL_BEFORE,
                            tool_call_id=event.tool_call_id,
                            tool_name=event.tool_name,
                            function_name=event.function_name,
                        )
                    )

                # Track tool start time for duration measurement
                self._tool_start_times[event.tool_call_id] = time.perf_counter()

                if event.confirmation_state == "awaiting_confirmation":
                    pending_action = {
                        "tool_call_id": event.tool_call_id,
                        "tool_name": event.tool_name,
                        "function_name": event.function_name,
                        "function_args": event.function_args,
                        "security_risk": event.security_risk,
                        "security_reason": event.security_reason,
                        "security_suggestions": event.security_suggestions,
                    }
                    self._pending_tool_calls[event.tool_call_id] = pending_action
                    await self._session_repository.update_pending_action(
                        self._session_id,
                        pending_action,
                        "awaiting_confirmation",
                    )

                # Cache original file content for diff generation (use handler's helper)
                if self._tool_event_handler.needs_file_cache(event):
                    file_path = event.function_args.get("file")
                    if file_path:
                        try:
                            before_result = await self._sandbox.file_read(file_path)
                            if before_result.success:
                                self._file_before_cache[event.tool_call_id] = before_result.data.get("content", "")
                            else:
                                self._file_before_cache[event.tool_call_id] = ""
                        except Exception:
                            self._file_before_cache[event.tool_call_id] = ""

                # Show the content being written for streaming preview
                if self._tool_event_handler.needs_preview_content(event):
                    content = event.function_args.get("content", "")
                    if content:
                        event.tool_content = FileToolContent(content=content)
                        logger.debug(f"File write preview: {len(content)} chars")
            elif event.status == ToolStatus.CALLED:
                # Capture screenshot after visual tool execution
                if self._screenshot_service and event.tool_name in (
                    "browser",
                    "browser_agent",
                    "shell",
                    "code_executor",
                ):
                    from app.domain.models.screenshot import ScreenshotTrigger

                    self._fire_and_forget(
                        self._screenshot_service.capture(
                            ScreenshotTrigger.TOOL_AFTER,
                            tool_call_id=event.tool_call_id,
                            tool_name=event.tool_name,
                            function_name=event.function_name,
                        )
                    )
                    self._screenshot_service.clear_tool_context(tool_call_id=event.tool_call_id)

                # Duration measurement
                start_time = self._tool_start_times.pop(event.tool_call_id, None)
                if start_time is not None:
                    event.duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Clean up pending tool call tracking
                self._pending_tool_calls.pop(event.tool_call_id, None)

                # Enrich observation metadata using ToolEventHandler
                self._tool_event_handler.enrich_observation_metadata(event)

                # Dispatch to per-tool content handler (registry replaces elif chain)
                handler = self._content_handlers.get(event.tool_name)
                if handler:
                    await handler(event, self)
                elif event.tool_name in ("agent_mode", "message"):
                    # Control tools — no content needed
                    logger.debug("Processing %s tool event", event.tool_name)
                elif event.tool_name in ("wide_research", "scraping"):
                    # Handled elsewhere (WideResearchEvent/ReportEvent) or logging-only
                    logger.debug("Agent %s: Processing %s tool event", self._agent_id, event.tool_name)
                elif event.tool_name == "deal_scraper":
                    # Content already populated by base.py:_create_tool_event()
                    logger.debug("Agent %s: deal_scraper tool content from base.py", self._agent_id)
                else:
                    logger.warning("Agent %s received unknown tool event: %s", self._agent_id, event.tool_name)
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to generate tool content: {e}")

    async def run(self, task: Task) -> None:
        """Process agent's message queue and run the agent's flow"""
        try:
            self._cancel_event.clear()
            if self._plan_act_flow is not None:
                self._plan_act_flow.set_cancel_token(self._cancel_token)
            logger.info(f"Agent {self._agent_id} message processing task started (task_id={task.id})")

            # Initialize sandbox and MCP tool concurrently
            # Wire MCP health callback so events stream to the client
            _task_ref = task  # capture for closure

            async def _mcp_health_callback(summary: dict) -> None:
                """Emit per-server MCPHealthEvent for each server in the summary."""
                servers_info = summary.get("servers", {})
                for name in servers_info.get("healthy_names", []):
                    await self._put_and_add_event(
                        _task_ref,
                        MCPHealthEvent(server_name=name, healthy=True, tools_available=0),
                    )
                for name in servers_info.get("unhealthy_names", []):
                    await self._put_and_add_event(
                        _task_ref,
                        MCPHealthEvent(server_name=name, healthy=False, tools_available=0),
                    )

            self._mcp_tool.set_health_callback(_mcp_health_callback)

            async def init_mcp():
                config = await self._mcp_repository.get_mcp_config()
                # Merge user's extra MCP server configs (e.g. from connectors)
                if self._extra_mcp_configs:
                    for server_name, server_config in self._extra_mcp_configs.items():
                        config.mcp_servers[server_name] = server_config
                    logger.info(f"Agent {self._agent_id}: Merged {len(self._extra_mcp_configs)} user MCP connectors")
                await self._mcp_tool.initialized(config)

            init_results = await asyncio.gather(self._sandbox.ensure_sandbox(), init_mcp(), return_exceptions=True)
            # Log initialization failures but allow agent to continue (graceful degradation)
            for i, result in enumerate(init_results):
                if isinstance(result, Exception):
                    component = "sandbox" if i == 0 else "MCP"
                    logger.error(f"Agent {self._agent_id} {component} init failed: {result}")
            logger.debug(f"Agent {self._agent_id} concurrent initialization completed")

            # Register MCP manager in the global registry (for REST endpoints)
            if self._mcp_tool.manager is not None:
                get_mcp_registry().register(
                    self._user_id,
                    self._mcp_tool.manager,
                    self._mcp_tool.health_monitor,
                )

            # Initialize screenshot capture service after sandbox is ready
            settings = get_settings()
            if settings.screenshot_capture_enabled and not isinstance(init_results[0], Exception):
                try:
                    from app.application.services.screenshot_service import ScreenshotCaptureService
                    from app.domain.models.screenshot import ScreenshotTrigger

                    self._screenshot_service = ScreenshotCaptureService(self._sandbox, self._session_id)
                    self._fire_and_forget(self._screenshot_service.capture(ScreenshotTrigger.SESSION_START))
                    await self._screenshot_service.start_periodic()
                except Exception as e:
                    logger.debug(f"Screenshot capture init failed (non-critical): {e}")

            # Emit flow selection telemetry
            flow_event = FlowSelectionEvent(
                flow_mode=self._flow_mode.value,
                model=getattr(self._llm, "model", None),
                session_id=self._session_id,
                reason=self._flow_selection_reason,
            )
            await self._put_and_add_event(task, flow_event)

            while not await task.input_stream.is_empty():
                event = await self._pop_event(task)
                if event is None:
                    continue  # Skip empty/unparseable events
                message = ""
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)

                logger.info(f"Agent {self._agent_id} received new message: {message[:50]}...")

                # Build attachments list, handling None case
                attachments = [attachment.file_path for attachment in event.attachments] if event.attachments else []

                # Log skills for debugging skill activation
                if event.skills:
                    logger.info(f"Agent {self._agent_id} received skills: {event.skills}")

                message_obj = Message(
                    message=message,
                    attachments=attachments,
                    skills=event.skills or [],
                    thinking_mode=event.thinking_mode,
                )

                # Set current task for attention manipulation (Pythinker pattern)
                if message:
                    await self._set_current_task(message)

                async for event in self._run_flow(message_obj, task):
                    # Check if task is paused (for user takeover)
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused, waiting for resume...")
                        await asyncio.sleep(0.5)

                    # ToolStreamEvent and ToolProgressEvent are ephemeral (preview only)
                    # — send to SSE but skip persistence
                    if isinstance(event, (ToolStreamEvent, ToolProgressEvent)):
                        await task.output_stream.put(event.model_dump_json())
                        continue

                    await self._put_and_add_event(task, event)
                    if isinstance(event, TitleEvent):
                        await self._session_repository.update_title(self._session_id, event.title)
                    elif isinstance(event, MessageEvent):
                        await self._session_repository.update_latest_message(
                            self._session_id, event.message, event.timestamp
                        )
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(event, WaitEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.WAITING)
                        return
                    if not await task.input_stream.is_empty():
                        break

            # Send DoneEvent when task completes normally
            await self._put_and_add_event(task, DoneEvent())
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
            logger.info(f"Agent {self._agent_id} task completed successfully")
        except asyncio.CancelledError:
            logger.info(f"Agent {self._agent_id} task cancelled")
            # Cancellation terminal status is managed by the caller path:
            # - explicit stop_session marks COMPLETED
            # - transport/disconnect cancellation marks FAILED
            # Avoid emitting DoneEvent here to prevent false "task completed"
            # UI state with unfinished plan steps.
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} task encountered exception: {e!s}")
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {e!s}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.FAILED)

    async def _run_flow(self, message: Message, task: Task | None = None) -> AsyncGenerator[BaseEvent, None]:
        """Process a single message through the agent's flow and yield events

        Args:
            message: The message to process
            task: Optional task reference for pause checking
        """
        if not message.message:
            logger.warning(f"Agent {self._agent_id} received empty message")
            yield ErrorEvent(error="No message")
            return

        mode_switch_task: str | None = None

        # Detect deal/price intent from user query for badge auto-switch
        _is_deal_query = (
            not self._deal_mode_emitted
            and self._research_mode != ResearchMode.DEAL_FINDING
            and re.search(
                r"\b(deal|deals|price|prices|pricing|cheap|cheapest|coupon|coupons|"
                r"discount|discounts|promo|sale|bargain|offer|offers|cost|affordable|"
                r"buy|purchase|lowest.price|best.price|compare.prices?)\b",
                message.message,
                re.IGNORECASE,
            )
            is not None
        )

        async with self._usage_context():
            async for event in self._flow.run(message):
                # Check if task is paused (for user takeover) before processing each event
                if task and hasattr(task, "paused"):
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused in flow, waiting for resume...")
                        await asyncio.sleep(0.5)

                # Intercept the flow's ResearchModeEvent and replace with deal_finding
                # when the user query contains deal/price keywords
                if isinstance(event, ResearchModeEvent) and _is_deal_query and not self._deal_mode_emitted:
                    self._deal_mode_emitted = True
                    yield ResearchModeEvent(research_mode="deal_finding")
                    continue

                if isinstance(event, ToolEvent):
                    # TODO: move to tool function
                    await self._handle_tool_event(event)
                    # Auto-switch badge on first deal_scraper tool completion
                    if (
                        not self._deal_mode_emitted
                        and event.tool_name == "deal_scraper"
                        and event.status == ToolStatus.CALLED
                    ):
                        self._deal_mode_emitted = True
                        yield ResearchModeEvent(research_mode="deal_finding")
                elif isinstance(event, ReportEvent):
                    await self._ensure_report_file(event)
                    # Sync attachments to storage for events that contain file references
                    # This resolves file_path to file_id for proper frontend access
                    await self._sync_event_attachments_to_storage(event)
                elif isinstance(event, MessageEvent):
                    # Sync attachments to storage for events that contain file references
                    # This resolves file_path to file_id for proper frontend access
                    await self._sync_event_attachments_to_storage(event)
                elif isinstance(event, ModeChangeEvent) and event.mode == "agent" and self._mode == AgentMode.DISCUSS:
                    # Handle mode switch from Discuss to Agent
                    # Get the task from the discuss flow
                    mode_switch_task = mode_switch_task or (
                        self._discuss_flow.mode_switch_task
                        if self._discuss_flow and self._discuss_flow.mode_switch_task
                        else None
                    )
                    yield event
                    continue
                yield event

        # If mode switch was requested, switch to Agent mode and re-run with the task
        if mode_switch_task and self._mode == AgentMode.DISCUSS:
            logger.info(f"Executing mode switch to Agent for task: {mode_switch_task}")
            await self._switch_to_agent_mode(mode_switch_task)

            # Create a new message with the task description (preserve skills from original message)
            task_message = Message(
                message=mode_switch_task,
                attachments=message.attachments,
                skills=message.skills,
            )

            # Run through Agent mode flow
            async with self._usage_context():
                async for event in self._flow.run(task_message):
                    # Check if task is paused (for user takeover)
                    if task and hasattr(task, "paused"):
                        while task.paused:
                            logger.debug(f"Agent {self._agent_id} paused in mode switch flow, waiting for resume...")
                            await asyncio.sleep(0.5)

                    if isinstance(event, ToolEvent):
                        await self._handle_tool_event(event)
                    elif isinstance(event, ReportEvent):
                        await self._ensure_report_file(event)
                        # Sync attachments to storage for events that contain file references
                        await self._sync_event_attachments_to_storage(event)
                    elif isinstance(event, MessageEvent):
                        # Sync attachments to storage for events that contain file references
                        await self._sync_event_attachments_to_storage(event)
                    yield event

        logger.info(f"Agent {self._agent_id} completed processing one message")

    async def on_done(self, task: Task) -> None:
        """Called when the task is done"""
        logger.info(f"Agent {self._agent_id} task done")

    async def destroy(self) -> None:
        """Destroy the task and release resources"""
        logger.info("Starting to destroy agent task")

        # Stop periodic screenshot capture and take final screenshot
        if self._screenshot_service:
            from app.domain.models.screenshot import ScreenshotTrigger

            try:
                await self._screenshot_service.stop_periodic()
            except Exception as e:
                logger.warning(
                    "Failed to stop periodic screenshot capture for session %s: %s",
                    self._session_id,
                    e,
                    exc_info=True,
                )

            try:
                final_screenshot = await self._screenshot_service.capture(ScreenshotTrigger.SESSION_END)
                if final_screenshot is None:
                    logger.warning(
                        "SESSION_END screenshot capture returned no image for session %s",
                        self._session_id,
                    )
            except Exception as e:
                logger.warning(
                    "SESSION_END screenshot capture failed for session %s: %s",
                    self._session_id,
                    e,
                    exc_info=True,
                )

        # ORPHANED TASK FIX: Cancel all background tasks (fire-and-forget tasks)
        # Prevents orphaned tasks from continuing after session ends
        if self._background_tasks:
            logger.debug(f"Cancelling {len(self._background_tasks)} background tasks for session {self._session_id}")
            for task in list(self._background_tasks):
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=2.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass  # Expected - task was cancelled
                    except Exception as e:
                        logger.warning(f"Background task cleanup raised exception: {e}")
            self._background_tasks.clear()

        # Cleanup background tasks on the execution agent (e.g. background memory saves)
        agent = self._get_tool_execution_agent()
        if agent and hasattr(agent, "cleanup_background_tasks"):
            try:
                await agent.cleanup_background_tasks(timeout=5.0)
            except Exception as e:
                logger.warning(f"Background task cleanup failed for Agent {self._agent_id}: {e}")

        # Cleanup Pythinker agent factory session if available
        if self._agent_factory:
            logger.debug(f"Cleaning up Agent {self._agent_id}'s Pythinker factory session")
            self._agent_factory.cleanup_session(self._session_id)

        # Shutdown coordinator flow if used
        if self._coordinator_flow:
            logger.debug(f"Shutting down Agent {self._agent_id}'s coordinator flow")
            await self._coordinator_flow.shutdown()

        # Destroy sandbox environment with timeout to avoid hanging on container cleanup
        if self._sandbox:
            # Release pooled browser connection before sandbox cleanup to prevent pool exhaustion
            if self._browser and hasattr(self._sandbox, "release_pooled_browser"):
                try:
                    await self._sandbox.release_pooled_browser(self._browser, had_error=False)
                except Exception as e:
                    logger.debug(f"Pooled browser release failed (non-critical): {e}")
            logger.debug(f"Destroying Agent {self._agent_id}'s sandbox environment")
            try:
                await asyncio.wait_for(self._sandbox.destroy(), timeout=15.0)
            except TimeoutError:
                logger.warning(f"Sandbox destroy timed out for Agent {self._agent_id}")
            except Exception as e:
                logger.warning(f"Sandbox destroy failed for Agent {self._agent_id}: {e}")

        if self._mcp_tool:
            # Unregister from global MCP registry before cleanup
            get_mcp_registry().unregister(self._user_id)
            logger.debug(f"Destroying Agent {self._agent_id}'s MCP tool")
            try:
                await asyncio.wait_for(self._mcp_tool.cleanup(), timeout=10.0)
            except TimeoutError:
                logger.warning(f"MCP tool cleanup timed out for Agent {self._agent_id}")
            except Exception as e:
                logger.warning(f"MCP tool cleanup failed for Agent {self._agent_id}: {e}")

        # Clean up tool metadata caches to prevent unbounded growth
        self._tool_start_times.clear()
        self._file_before_cache.clear()
        self._pending_tool_calls.clear()

        logger.debug(f"Agent {self._agent_id} has been fully closed and resources cleared")
