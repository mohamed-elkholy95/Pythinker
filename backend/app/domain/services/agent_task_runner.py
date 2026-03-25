import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, Optional

from pydantic import TypeAdapter

from app.core.config import FlowMode, get_feature_flags, get_settings
from app.domain.external.browser import Browser
from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task, TaskRunner
from app.domain.models.agent_usage import AgentRunStatus
from app.domain.models.event import (
    AgentEvent,
    BaseEvent,
    CanvasToolContent,
    CanvasUpdateEvent,
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
from app.domain.models.session import AgentMode, PendingAction, PendingActionStatus, ResearchMode, SessionStatus
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

_CANVAS_MUTATION_OPERATIONS = frozenset(
    {
        "create_project",
        "add_element",
        "modify_element",
        "delete_elements",
        "generate_image",
        "arrange_layer",
    }
)


def _extract_mcp_server_name(tool_name: str | None) -> str | None:
    """Parse the MCP server name from the `mcp__server__tool` naming convention."""
    if not tool_name:
        return None
    parts = tool_name.split("__")
    if len(parts) >= 3 and parts[0] == "mcp":
        return parts[1]
    return None


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
        usage_recorder: Callable[..., Coroutine[Any, Any, object | None]] | None = None,
        extra_mcp_configs: dict[str, Any] | None = None,
        # Optional feature services (injected from application layer)
        text_matcher: Any | None = None,
        spell_provider: Any | None = None,
        typo_analytics: Any | None = None,
        scraping_adapter: Any | None = None,
        deal_finder_adapter: Any | None = None,
        checkpoint_db: Any | None = None,
        cron_bridge: Any | None = None,
        skill_package_repo: Any | None = None,
        circuit_breaker: Any | None = None,
        screenshot_service: Optional["ScreenshotCaptureService"] = None,
        knowledge_base_service: Any | None = None,
        prompt_profile_repo: Any | None = None,
        conversation_context_service: Any | None = None,
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
        # Coerce enums that may arrive as plain str from MongoDB
        if isinstance(mode, str) and not isinstance(mode, AgentMode):
            try:
                mode = AgentMode(mode)
            except ValueError:
                mode = AgentMode.AGENT
        self._mode = mode
        if isinstance(research_mode, str) and not isinstance(research_mode, ResearchMode):
            try:
                research_mode = ResearchMode(research_mode)
            except ValueError:
                research_mode = ResearchMode.DEEP_RESEARCH
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
        self._knowledge_base_service = knowledge_base_service

        # Prompt profile repository for DSPy/GEPA optimization (None if feature disabled)
        self._prompt_profile_repo = prompt_profile_repo

        # Pythinker-style agent factory and components
        self._agent_factory: PythinkerAgentFactory | None = agent_factory
        self._manifest: StateManifest | None = None
        self._context_manager: SandboxContextManager | None = None
        self._attention_injector: AttentionInjector | None = None
        self._initialized: bool = False

        # Optional feature services (injected from application layer)
        self._text_matcher = text_matcher
        self._spell_provider = spell_provider
        self._typo_analytics = typo_analytics
        self._scraping_adapter = scraping_adapter
        self._deal_finder_adapter = deal_finder_adapter
        self._checkpoint_db = checkpoint_db
        self._cron_bridge = cron_bridge
        self._skill_package_repo = skill_package_repo
        self._circuit_breaker = circuit_breaker
        self._conversation_context_service = conversation_context_service

        # Screenshot capture service (created after sandbox init if enabled)
        self._screenshot_service: ScreenshotCaptureService | None = screenshot_service
        self._background_tasks: set[asyncio.Task[object]] = set()
        # True after release_task_resources() — avoids double-clear and lets destroy() add session teardown
        self._task_resources_released: bool = False

        # Current task description for attention manipulation
        self.current_task: str | None = None

        # Tool metadata caches for enhanced UI
        self._tool_start_times: dict[str, float] = {}
        self._file_before_cache: dict[str, str] = {}
        self._pending_tool_calls: dict[str, PendingAction] = {}
        self._cancel_event = asyncio.Event()
        self._cancel_token = CancellationToken(event=self._cancel_event, session_id=self._session_id)
        self._terminal_status: SessionStatus | None = None
        self._run_id: str | None = None

        # Tool event handler for action/observation metadata enrichment
        self._tool_event_handler = ToolEventHandler()
        # Per-tool content handler registry (replaces elif chain)
        self._content_handlers = get_content_handler_registry()
        self._comparison_chart_generator = ComparisonChartGenerator()
        # Phase 5: LLM-powered Plotly chart orchestrator
        self._plotly_chart_orchestrator = PlotlyChartOrchestrator(
            sandbox=self._sandbox,
            session_id=session_id,
            llm=self._llm,
        )
        self._delivery_scope_id: str | None = None
        self._delivery_scope_root: str | None = None
        self._workspace_deliverables_root: str | None = None  # Set from session.workspace_structure

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
        # Always-present default; conditionally replaced in _init_plan_act_flow()
        self._lead_agent_runtime: object | None = None

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

    @property
    def session_id(self) -> str:
        """Session ID -- exposed for RedisStreamTask liveness signal."""
        return self._session_id

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
        if self._terminal_status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        ):
            logger.debug(
                "Ignoring cancellation request for Agent %s session %s in terminal state %s",
                self._agent_id,
                self._session_id,
                self._terminal_status.value,
            )
            return
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            logger.info("Cancellation requested for Agent %s session %s", self._agent_id, self._session_id)

    def hydrate_reactivation_sources(self, sources: list) -> None:
        """Restore persisted sources into the executor's SourceTracker.

        Called before run() to hydrate grounding context from prior report
        events into the new executor so hallucination verification has
        access to the original sources.
        """
        flow = getattr(self, "_plan_act_flow", None)
        executor = getattr(flow, "executor", None)
        if executor and hasattr(executor, "restore_collected_sources"):
            executor.restore_collected_sources(sources)
            logger.info(
                "Hydrated %d persisted sources into executor for session %s",
                len(sources),
                self._session_id,
            )

    def _init_plan_act_flow(self) -> None:
        """Initialize PlanActFlow for Agent mode"""
        if self._plan_act_flow is None:
            settings = get_settings()
            feature_flags = get_feature_flags()

            # Use injected text matcher if available and feature-enabled
            rapidfuzz_matcher = None
            if settings.typo_correction_rapidfuzz_enabled and self._text_matcher:
                rapidfuzz_matcher = self._text_matcher

            # Use injected spell provider if available and feature-enabled
            symspell_provider = None
            if settings.typo_correction_symspell_enabled and self._spell_provider:
                symspell_provider = self._spell_provider

            # Use injected scraping adapter
            _scraper = self._scraping_adapter

            # DealFinder adapter — enabled only when deal_scraper_enabled=True in settings.
            # Runtime deal intent (detect_deal_intent on actual message) is handled
            # per-message in run() and switches research mode dynamically.
            _deal_finder = None
            if _scraper and self._search_engine and settings.deal_scraper_enabled and self._deal_finder_adapter:
                _deal_finder = self._deal_finder_adapter

            # WP-6: CheckpointManager for cross-restart workflow persistence.
            # Uses injected checkpoint_db (MongoDB collection) so checkpoints survive
            # process restarts. Falls back to in-memory when checkpoint_db is None.
            _checkpoint_manager = None
            if settings.feature_workflow_checkpointing:
                try:
                    from app.domain.services.flows.checkpoint_manager import CheckpointManager

                    _checkpoint_manager = CheckpointManager(
                        mongodb_collection=self._checkpoint_db,
                        ttl_hours=24,
                        auto_cleanup=True,
                    )
                    logger.debug(
                        "CheckpointManager initialized for session %s (persistent=%s)",
                        self._session_id,
                        self._checkpoint_db is not None,
                    )
                except Exception as exc:
                    logger.warning("CheckpointManager unavailable: %s", exc)

            # ── Cron Tool ────────────────────────────────
            _cron_service = self._cron_bridge if settings.cron_service_enabled else None

            # ── Spawn Tool (deferred) ────────────────────
            # SpawnTool requires SubagentManager provider wiring which depends
            # on the gateway runner connection (not yet available).  Will be
            # wired here once the gateway infrastructure is complete.

            # ── Skill Tools ──────────────────────────────
            _skill_loader = None
            if settings.skills_system_enabled:
                try:
                    from pathlib import Path

                    from nanobot.agent.skills import SkillsLoader

                    _skill_loader = SkillsLoader(workspace=Path(settings.skills_workspace_dir).expanduser())
                except Exception as exc:
                    logger.warning("SkillsLoader unavailable: %s", exc)

            # ── LeadAgentRuntime (opt-in via feature flag) ─────────
            self._lead_agent_runtime = None
            if feature_flags.get("feature_lead_agent_runtime", False):
                try:
                    from app.domain.services.runtime.lead_agent_runtime import (
                        LeadAgentRuntime,
                    )

                    self._lead_agent_runtime = LeadAgentRuntime(
                        session_id=self._session_id,
                        agent_id=self._agent_id,
                        workspace_base="/home/ubuntu",
                        memory_service=self._memory_service,
                    )
                    logger.info(
                        "LeadAgentRuntime initialized for session %s",
                        self._session_id,
                    )
                except Exception as exc:
                    logger.warning("LeadAgentRuntime unavailable: %s", exc)

            # Typo correction analytics — use injected service or create a no-op fallback
            _correction_event_sink = None
            _feedback_lookup = None
            if self._typo_analytics:
                _correction_event_sink = self._typo_analytics.record_event
                _feedback_lookup = self._typo_analytics.get_feedback_override

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
                scope_callback=self._set_delivery_scope,
                feature_flags=feature_flags,
                browser_agent_enabled=settings.browser_agent_enabled,
                rapidfuzz_matcher=rapidfuzz_matcher,
                symspell_provider=symspell_provider,
                correction_event_sink=_correction_event_sink,
                feedback_lookup=_feedback_lookup,
                cancel_token=self._cancel_token,
                research_mode=self._research_mode.value,
                knowledge_base_service=self._knowledge_base_service,
                prompt_profile_repo=self._prompt_profile_repo,
                scraper=_scraper,
                deal_finder=_deal_finder,
                checkpoint_manager=_checkpoint_manager,
                cron_service=_cron_service,
                skill_loader=_skill_loader,
                skill_package_repo=self._skill_package_repo,
            )
            # Inject circuit breaker for tool-level failure protection
            if self._circuit_breaker:
                self._plan_act_flow.set_circuit_breaker(self._circuit_breaker)

            logger.debug(
                f"Initialized PlanActFlow for agent {self._agent_id} "
                f"(verification={settings.enable_plan_verification}, multi_agent={self._enable_multi_agent}, "
                f"memory_service={'enabled' if self._memory_service else 'disabled'})"
            )

    def _set_delivery_scope(self, scope_id: str | None, workspace_root: str | None) -> None:
        """Record the active delivery scope and mirror it into file sync."""
        self._delivery_scope_id = scope_id
        self._delivery_scope_root = workspace_root.rstrip("/") if workspace_root else None
        self._file_sync_manager.set_delivery_scope(scope_id, workspace_root)

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
                conversation_context_service=self._conversation_context_service,
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

        If no agent_factory was provided, factory initialization is skipped.
        The method is idempotent - calling it multiple times has no effect.
        """
        if self._initialized:
            return

        # Initialize LeadAgentRuntime (runs BEFORE_RUN hook on all middlewares)
        if self._lead_agent_runtime is not None:
            try:
                ctx = await self._lead_agent_runtime.initialize()
                # Rebind task_state_manager path if workspace contract provided one
                workspace_contract = ctx.metadata.get("workspace_contract")
                if workspace_contract and self._plan_act_flow:
                    tsm = getattr(self._plan_act_flow, "_task_state_manager", None)
                    new_path = getattr(workspace_contract, "task_state_path", None)
                    if tsm and new_path:
                        tsm._file_path = new_path
                        logger.info(
                            "Runtime workspace contract rebind: task_state_path=%s",
                            new_path,
                        )
            except Exception as exc:
                logger.warning("LeadAgentRuntime.initialize() failed: %s", exc)

        if self._agent_factory is None:
            logger.debug(f"Agent {self._agent_id}: No agent factory provided, skipping Pythinker initialization")
            self._initialized = True
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
        await task.output_stream.put(event.model_dump_json())
        await self._session_repository.add_event(self._session_id, event)

    async def _pop_event(self, task: Task) -> AgentEvent | None:
        _redis_id, event_str = await task.input_stream.pop()
        if event_str is None:
            logger.warning(f"Agent {self._agent_id} received empty message")
            return None
        return TypeAdapter(AgentEvent).validate_json(event_str)

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
            file_path,
            content_type=content_type,
            max_attempts=max_attempts,
            initial_delay_seconds=initial_delay_seconds,
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

    @staticmethod
    def _rewrite_chart_image_urls(event: ReportEvent) -> None:
        """Rewrite local chart filenames in report content to API download URLs.

        After attachments are synced to storage, each attachment with a resolved
        file_id gets its markdown reference updated so the frontend can fetch the
        file via the files API instead of relying on a sandbox path.

        Handles both PNG images and HTML interactive chart links.

        Handles filename mismatch: the markdown uses ``comparison-chart-{id}.ext``
        but after sync the attachment filename may be the sandbox path basename
        (e.g. ``top_5_python_web_frameworks_....ext``).  We try both the synced
        filename AND the canonical ``comparison-chart-{report_id}.ext`` pattern.
        """
        if not event.attachments or not event.content:
            return

        rewrite_count = 0
        for attachment in event.attachments:
            content_type = getattr(attachment, "content_type", None)
            # Process PNG images and HTML interactive charts
            if content_type not in ("image/png", "text/html"):
                continue
            file_id = getattr(attachment, "file_id", None)
            if not file_id:
                continue
            filename = getattr(attachment, "name", None) or getattr(attachment, "filename", None)
            if not filename:
                continue

            download_url = f"/api/v1/files/{file_id}/download"
            old_content = event.content

            # Try synced filename first
            event.content = event.content.replace(
                f"]({filename})",
                f"]({download_url})",
            )

            # Fallback: try canonical comparison-chart-{id}.ext pattern
            ext = ".html" if content_type == "text/html" else ".png"
            canonical = f"comparison-chart-{event.id}{ext}" if event.id else None
            if canonical and canonical != filename and f"]({canonical})" in event.content:
                event.content = event.content.replace(
                    f"]({canonical})",
                    f"]({download_url})",
                )

            # Third fallback: try file_path basename (sync may preserve original sandbox name)
            att_file_path = getattr(attachment, "file_path", None)
            if att_file_path and event.content == old_content:
                path_basename = att_file_path.rsplit("/", 1)[-1] if "/" in att_file_path else att_file_path
                if path_basename and path_basename != filename and f"]({path_basename})" in event.content:
                    event.content = event.content.replace(
                        f"]({path_basename})",
                        f"]({download_url})",
                    )

            if event.content != old_content:
                rewrite_count += 1
                logger.debug(
                    "Rewrote chart reference: %s -> %s (type=%s)",
                    filename,
                    download_url,
                    content_type,
                )

        if rewrite_count > 0:
            logger.info("Rewrote %d chart reference(s) in report content", rewrite_count)
        elif any(
            getattr(a, "content_type", None) in ("image/png", "text/html") and getattr(a, "file_id", None)
            for a in (event.attachments or [])
        ):
            logger.warning(
                "Chart attachments have file_ids but no references were rewritten in report content "
                "(possible filename mismatch). Report id=%s",
                event.id,
            )

    async def _resolve_workspace_deliverables_root(self) -> str:
        """Resolve the deliverables directory from session workspace_structure.

        Falls back to /workspace/{session_id} if no workspace template was applied.
        """
        if self._workspace_deliverables_root:
            return self._workspace_deliverables_root

        try:
            session = await self._session_repository.find_by_id(self._session_id)
            workspace_structure = session.workspace_structure if session else None
            if isinstance(workspace_structure, dict) and workspace_structure:
                output_path = str(workspace_structure.get("_output_path") or "").rstrip("/")
                if output_path:
                    self._workspace_deliverables_root = f"{output_path}/reports"
                elif "deliverables" in workspace_structure:
                    self._workspace_deliverables_root = f"/workspace/{self._session_id}/deliverables"

            if self._workspace_deliverables_root:
                logger.debug(
                    "Resolved workspace deliverables root: %s (session=%s)",
                    self._workspace_deliverables_root,
                    self._session_id,
                )
                return self._workspace_deliverables_root
        except Exception as e:
            logger.debug("Could not resolve workspace deliverables: %s", e)

        return f"/workspace/{self._session_id}"

    async def _ensure_report_file(self, event: ReportEvent) -> None:
        """Persist report content as a file in the sandbox and attach it to the event."""
        if not self._sandbox:
            return
        if not event.content or not event.content.strip():
            return

        existing = event.attachments or []
        workspace_root = self._delivery_scope_root or await self._resolve_workspace_deliverables_root()
        report_metadata: dict[str, object] = {"is_report": True, "title": event.title}
        if self._delivery_scope_id and self._delivery_scope_root:
            report_metadata.update(
                {
                    "delivery_scope": self._delivery_scope_id,
                    "delivery_root": self._delivery_scope_root,
                }
            )

        # Include the full pre-summarization markdown (from the agent's file_write
        # during execution) as an attachment so users get the complete original report
        # alongside the summarized version.
        full_content = self._get_pre_trim_report_content()
        if full_content and full_content.strip() and full_content.strip() != event.content.strip():
            full_name = f"full-report-{event.id}.md"
            if not self._has_attachment(existing, full_name):
                full_path = f"{workspace_root}/{full_name}"
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
                            metadata={**report_metadata, "is_full_report": True},
                        )
                        existing = [full_info, *existing]
                        logger.info(
                            "Attached full pre-summarization report (%d chars) for session=%s",
                            full_size,
                            self._session_id,
                        )
                    else:
                        logger.warning("Agent %s: Failed to write full report file (success=False)", self._agent_id)
                except Exception as e:
                    logger.warning("Agent %s: Failed to write full report file: %s", self._agent_id, e)

        # --- Chart generation (before report write so references land in the file) ---
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

        chart_attachments: list[FileInfo] = []
        if chart_mode == "skip":
            logger.info(
                "Skipping comparison chart generation for report_id=%s session=%s due to user override",
                event.id,
                self._session_id,
            )
        else:
            pre_chart_count = len(existing)
            existing = await self._ensure_comparison_chart_file(
                event,
                existing,
                force_generation=chart_mode in {"force", "regenerate"},
                generation_mode=chart_mode,
            )
            chart_attachments = existing[pre_chart_count:]

        # Inject chart references into event.content before writing report file
        if chart_attachments:
            chart_lines = ["\n\n---\n\n## Charts\n"]
            for ci in chart_attachments:
                if ci.content_type == "image/png":
                    chart_lines.append(f"![Comparison Chart]({ci.filename})")
                elif ci.content_type == "text/html":
                    # Render as clickable link (rewritten to API URL after sync)
                    chart_lines.append(f"[Open interactive chart]({ci.filename})")
            event.content += "\n".join(chart_lines) + "\n"

        # --- Write summarized report file (now includes chart references) ---
        expected_name = f"report-{event.id}.md"
        if not self._has_attachment(existing, expected_name):
            file_path = f"{workspace_root}/{expected_name}"
            try:
                result = await self._sandbox.file_write(file=file_path, content=event.content)
                if result is not None and hasattr(result, "success") and not result.success:
                    logger.warning(f"Agent {self._agent_id}: Failed to write report file '{file_path}' (success=False)")
                    event.attachments = existing
                    return
            except Exception as e:
                logger.warning(f"Agent {self._agent_id}: Failed to write report file '{file_path}': {e}")
                event.attachments = existing
                return

            report_size = len(event.content.encode("utf-8"))
            report_info = FileInfo(
                filename=expected_name,
                file_path=file_path,
                size=report_size,
                content_type="text/markdown",
                user_id=self._user_id,
                metadata=dict(report_metadata),
            )
            existing = [*existing, report_info]

        # --- Generate PDF version of the report ---
        pdf_info = await self._generate_report_pdf(event, report_metadata)
        if pdf_info:
            existing = [*existing, pdf_info]

        event.attachments = existing

    async def _generate_report_pdf(
        self,
        event: ReportEvent,
        report_metadata: dict[str, object],
    ) -> FileInfo | None:
        """Generate a PDF version of the report and upload to storage.

        Uses the existing ReportLab pipeline (``build_pdf_bytes``) to convert
        the markdown content into a PDF, then uploads it to file storage so the
        frontend receives a download URL alongside the markdown attachment.

        Returns ``None`` on any failure — PDF generation is non-critical.
        """
        from io import BytesIO

        from app.core.config import get_settings
        from app.domain.utils.markdown_to_pdf import build_pdf_bytes

        try:
            settings = get_settings()
            pdf_bytes = build_pdf_bytes(
                title=event.title or "Report",
                content=event.content,
                sources=event.sources,
                include_toc=settings.telegram_pdf_include_toc,
                toc_min_sections=settings.telegram_pdf_toc_min_sections,
                preferred_font=settings.telegram_pdf_unicode_font,
            )
        except Exception as e:
            logger.warning("PDF generation failed for report %s: %s", event.id, e, exc_info=True)
            return None

        # Build a human-readable filename from the report title
        title_slug = re.sub(r"[^\w\s-]", "", (event.title or "report").lower())
        title_slug = re.sub(r"[\s_]+", "_", title_slug).strip("_")[:80]
        pdf_filename = f"{title_slug}.pdf" if title_slug else f"report-{event.id}.pdf"
        workspace_root = self._delivery_scope_root or await self._resolve_workspace_deliverables_root()
        virtual_path = f"{workspace_root}/{pdf_filename}"

        try:
            pdf_file_info = await self._file_storage.upload_file(
                file_data=BytesIO(pdf_bytes),
                filename=pdf_filename,
                user_id=self._user_id,
                content_type="application/pdf",
                metadata={**report_metadata, "is_pdf_report": True, "title": event.title},
            )
            if not pdf_file_info or not pdf_file_info.file_id:
                logger.warning("PDF upload returned no file info for report %s", event.id)
                return None

            # Set file_path so sync_event_attachments_to_storage won't filter it out,
            # and register directly with session.files (PDF was uploaded to storage
            # directly, not written to sandbox, so the sandbox→storage sync path
            # would fail to download it).
            pdf_file_info.file_path = virtual_path
            pdf_file_info.size = len(pdf_bytes)
            try:
                await self._session_repository.add_file(self._session_id, pdf_file_info)
            except Exception as add_err:
                logger.warning(
                    "Failed to register PDF with session %s: %s",
                    self._session_id,
                    add_err,
                )

            logger.info(
                "Auto-generated PDF report (%d bytes) for session=%s report_id=%s",
                len(pdf_bytes),
                self._session_id,
                event.id,
            )
            return pdf_file_info
        except Exception as e:
            logger.warning("PDF upload failed for report %s: %s", event.id, e)
            return None

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
        chart_error: str | None = None
        try:
            chart_result = await self._plotly_chart_orchestrator.generate_chart(
                report_title=event.title,
                markdown_content=event.content,
                report_id=event.id,
                force_generation=force_generation,
            )
        except Exception as exc:
            chart_result = None
            chart_error = f"{type(exc).__name__}: {exc}"

        if chart_result is None:
            # Chart extraction failure from an actual error is a warning;
            # "no chart data" is expected for non-quantitative reports (info).
            _chart_msg = chart_error or "no chart data extracted from report"
            _log_fn = logger.warning if chart_error else logger.info
            _log_fn(
                "Plotly chart unavailable for report_id=%s session=%s: %s. Falling back to legacy SVG.",
                event.id,
                self._session_id,
                _chart_msg,
            )
            return await self._ensure_legacy_svg_chart(
                event,
                attachments,
                force_generation=force_generation,
                generation_mode=f"{generation_mode}_fallback_svg",
            )

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

        When the cache is empty, falls back to scanning conversation memory for the
        last ``file_write`` tool call that wrote markdown content.
        """
        flow = self._flow
        if flow and hasattr(flow, "executor"):
            executor = flow.executor
            # Primary: cached pre-trim content
            if hasattr(executor, "_pre_trim_report_cache"):
                cache = executor._pre_trim_report_cache
                if isinstance(cache, str) and cache.strip():
                    return cache
            # Fallback: recover from file_write tool call in conversation memory
            if hasattr(executor, "_response_generator"):
                rg = executor._response_generator
                if hasattr(rg, "extract_report_from_file_write_memory"):
                    try:
                        recovered = rg.extract_report_from_file_write_memory()
                        if isinstance(recovered, str) and recovered.strip():
                            logger.info(
                                "Recovered full report from file_write memory for session=%s (%d chars)",
                                self._session_id,
                                len(recovered),
                            )
                            return recovered
                    except Exception as e:
                        logger.warning("Failed to recover report from file_write memory: %s", e)
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
        if pending.tool_call_id != action_id:
            logger.warning(
                "Pending action id mismatch for session %s: %s != %s",
                self._session_id,
                pending.tool_call_id,
                action_id,
            )

        if not accept:
            await self._session_repository.update_pending_action(
                self._session_id,
                None,
                PendingActionStatus.REJECTED,
            )
            reject_event = ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=pending.tool_call_id,
                tool_name=pending.tool_name,
                function_name=pending.function_name,
                function_args=pending.function_args,
                function_result=ToolResult(success=False, message="Action rejected by user."),
                security_risk=pending.security_risk,
                security_reason=pending.security_reason,
                security_suggestions=pending.security_suggestions,
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

        function_name = pending.function_name
        function_args = pending.function_args
        tool_call_id = pending.tool_call_id
        tool_name = pending.tool_name

        calling_event = ToolEvent(
            status=ToolStatus.CALLING,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            security_risk=pending.security_risk,
            security_reason=pending.security_reason,
            security_suggestions=pending.security_suggestions,
            confirmation_state="confirmed",
        )
        emitted_events = await self._handle_tool_event(calling_event)
        await self._put_and_add_event(task, calling_event)
        for emitted_event in emitted_events:
            await self._put_and_add_event(task, emitted_event)

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
            security_risk=pending.security_risk,
            security_reason=pending.security_reason,
            security_suggestions=pending.security_suggestions,
            confirmation_state="confirmed",
        )
        emitted_events = await self._handle_tool_event(called_event)
        await self._put_and_add_event(task, called_event)
        for emitted_event in emitted_events:
            await self._put_and_add_event(task, emitted_event)

        await self._session_repository.update_pending_action(
            self._session_id,
            None,
            None,
        )

    async def _sync_project_files_to_sandbox(self, files: list[FileInfo]) -> list[str]:
        """Sync project files from MinIO to sandbox via FileSyncManager.

        Reuses the same pipeline as per-message attachments so files land at
        the correct path (/home/ubuntu/upload/) and the result is checked.

        Returns:
            List of sandbox file paths that were successfully synced.
        """
        synced_paths: list[str] = []
        for file_info in files:
            try:
                if not file_info.file_id:
                    continue
                result = await self._file_sync_manager.sync_file_to_sandbox(file_info.file_id)
                if result and result.file_path:
                    synced_paths.append(result.file_path)
                    logger.info("Synced project file to sandbox: %s", result.file_path)
                else:
                    logger.warning("Project file sync returned no path for %s", file_info.filename)
            except Exception as e:
                logger.warning("Failed to sync project file %s: %s", file_info.filename, e)
        return synced_paths

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
                run_id=self._run_id,
            ):
                yield
        else:
            yield

    async def _start_agent_run_usage(self) -> None:
        """Start a usage run for this task execution."""
        if not self._user_id or not self._usage_recorder:
            return
        try:
            result = await self._usage_recorder(
                action="start_run",
                user_id=self._user_id,
                session_id=self._session_id,
                agent_id=self._agent_id,
                entrypoint="task_run",
            )
            if isinstance(result, str):
                self._run_id = result
            elif hasattr(result, "run_id"):
                self._run_id = result.run_id
        except Exception as e:
            logger.warning(
                "Failed to start usage run for agent %s user %s; run_id will remain unset",
                self._agent_id,
                self._user_id,
                exc_info=e,
            )

    async def _finish_agent_run_usage(self, status: AgentRunStatus | None) -> None:
        """Finish the active usage run with its terminal status."""
        if not self._user_id or not self._usage_recorder or not self._run_id or status is None:
            return
        try:
            await self._usage_recorder(
                action="finish_run",
                user_id=self._user_id,
                session_id=self._session_id,
                run_id=self._run_id,
                status=status.value,
            )
        except Exception as e:
            logger.warning(
                "Failed to finalize usage run for agent %s user %s run %s",
                self._agent_id,
                self._user_id,
                self._run_id,
                exc_info=e,
            )

    async def _record_tool_call_usage(self, event: ToolEvent) -> None:
        """Record tool call usage for usage dashboard metrics."""
        if not self._user_id or not self._usage_recorder or not self._run_id:
            return
        try:
            tool_result = event.function_result if isinstance(event.function_result, ToolResult) else None
            status = "completed"
            error_type = None
            if tool_result is not None and not tool_result.success:
                status = "failed"
                error_type = tool_result.message
            await self._usage_recorder(
                action="record_tool_call",
                user_id=self._user_id,
                session_id=self._session_id,
                run_id=self._run_id,
                tool_name=event.tool_name,
                mcp_server=_extract_mcp_server_name(event.tool_name),
                status=status,
                duration_ms=event.duration_ms,
                error_type=error_type,
                started_at=event.started_at,
                completed_at=event.completed_at,
            )
        except Exception as e:
            logger.debug(f"Failed to record tool usage for Agent {self._agent_id}: {e}")

    def _build_canvas_update_event(self, event: ToolEvent) -> CanvasUpdateEvent | None:
        """Build a versioned canvas update event from a successful canvas mutation."""
        if event.status != ToolStatus.CALLED or event.tool_name != "canvas":
            return None

        function_result = event.function_result
        if not isinstance(function_result, ToolResult) or not function_result.success:
            return None

        tool_content = event.tool_content
        if not isinstance(tool_content, CanvasToolContent):
            return None

        if tool_content.operation not in _CANVAS_MUTATION_OPERATIONS:
            return None

        if not tool_content.project_id or tool_content.version is None:
            return None

        return CanvasUpdateEvent(
            project_id=tool_content.project_id,
            session_id=tool_content.session_id or self._session_id,
            operation=tool_content.operation,
            element_count=tool_content.element_count,
            project_name=tool_content.project_name,
            version=tool_content.version,
            changed_element_ids=tool_content.changed_element_ids,
            source="agent",
        )

    async def _handle_tool_event(self, event: ToolEvent) -> list[BaseEvent]:
        """Enrich tool event with metadata and generate tool content.

        Uses ToolEventHandler for action/observation metadata enrichment,
        then handles async tool-specific content generation.
        """
        emitted_events: list[BaseEvent] = []

        # ── Runtime: before_tool / after_tool hooks ──────────────────
        if self._lead_agent_runtime is not None and self._lead_agent_runtime.context is not None:
            try:
                if event.status == ToolStatus.CALLING:
                    runtime_ctx = self._lead_agent_runtime.context
                    runtime_ctx.metadata["current_tool"] = event.tool_name
                    runtime_ctx.metadata["current_tool_args"] = event.function_args
                    await self._lead_agent_runtime.before_tool(runtime_ctx)
                elif event.status == ToolStatus.CALLED:
                    runtime_ctx = self._lead_agent_runtime.context
                    runtime_ctx.metadata["tool_result"] = (
                        event.function_result.message if event.function_result else None
                    )
                    await self._lead_agent_runtime.after_tool(runtime_ctx)
            except Exception as exc:
                logger.warning("LeadAgentRuntime tool hook failed: %s", exc)

        try:
            # Enrich action metadata using ToolEventHandler (action_type, command, cwd, file_path)
            self._tool_event_handler.enrich_action_metadata(event)

            if event.status == ToolStatus.CALLED and event.tool_name != "message":
                await self._record_tool_call_usage(event)

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
                    pending_action = PendingAction(
                        tool_call_id=event.tool_call_id,
                        tool_name=event.tool_name,
                        function_name=event.function_name,
                        function_args=event.function_args,
                        security_risk=event.security_risk,
                        security_reason=event.security_reason,
                        security_suggestions=event.security_suggestions,
                    )
                    self._pending_tool_calls[event.tool_call_id] = pending_action
                    await self._session_repository.update_pending_action(
                        self._session_id,
                        pending_action,
                        PendingActionStatus.AWAITING_CONFIRMATION,
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
                elif event.tool_name == "skill_invoke":
                    # Skill invocation — content handled by skill_invoke tool
                    logger.debug("Agent %s: skill_invoke tool event processed", self._agent_id)
                else:
                    logger.warning("Agent %s received unknown tool event: %s", self._agent_id, event.tool_name)

                canvas_update_event = self._build_canvas_update_event(event)
                if canvas_update_event is not None:
                    emitted_events.append(canvas_update_event)
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to generate tool content: {e}")
        return emitted_events

    async def run(self, task: Task) -> None:
        """Process agent's message queue and run the agent's flow"""
        final_usage_status: AgentRunStatus | None = None
        try:
            self._cancel_event.clear()
            self._terminal_status = None
            if self._plan_act_flow is not None:
                self._plan_act_flow.set_cancel_token(self._cancel_token)
            logger.info(f"Agent {self._agent_id} message processing task started (task_id={task.id})")
            with suppress(Exception):
                from app.core.prometheus_metrics import active_sessions

                active_sessions.inc({})
            await self._start_agent_run_usage()

            # Ensure runtime is initialized (idempotent)
            await self.initialize()

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
            if (
                settings.screenshot_capture_enabled
                and self._screenshot_service
                and not isinstance(init_results[0], Exception)
            ):
                try:
                    from app.domain.models.screenshot import ScreenshotTrigger

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

            # === PROJECT CONTEXT INJECTION ===
            _project_context = None
            try:
                _session = await self._session_repository.find_by_id(self._session_id)
                _project_context = getattr(_session, "project_context", None) if _session else None
            except Exception as _pc_err:
                logger.warning("Failed to load session for project context: %s", _pc_err)

            _project_file_paths: list[str] = []
            if _project_context and _project_context.has_context():
                # 1. Inject project instructions into system prompt
                if _project_context.instructions:
                    _instructions_text = _project_context.instructions_text()
                    if self._plan_act_flow and hasattr(self._plan_act_flow, "executor"):
                        self._plan_act_flow.executor.system_prompt = (
                            _instructions_text + "\n\n" + self._plan_act_flow.executor.system_prompt
                        )
                        logger.info(
                            "Injected project instructions into PlanAct system prompt (%d chars)",
                            len(_instructions_text),
                        )
                    if self._discuss_flow and hasattr(self._discuss_flow, "system_prompt"):
                        self._discuss_flow.system_prompt = (
                            _instructions_text + "\n\n" + self._discuss_flow.system_prompt
                        )

                # 2. Sync project files to sandbox and collect paths
                if _project_context.files:
                    try:
                        _project_file_paths = await self._sync_project_files_to_sandbox(_project_context.files)
                    except Exception as e:
                        logger.warning("Project file sync failed (non-fatal): %s", e)

                # 3. Inject file manifest into system prompt (all flow types)
                _file_manifest = _project_context.file_manifest_text()
                if _file_manifest:
                    if self._plan_act_flow and hasattr(self._plan_act_flow, "executor"):
                        self._plan_act_flow.executor.system_prompt += "\n\n" + _file_manifest
                    if self._discuss_flow and hasattr(self._discuss_flow, "system_prompt"):
                        self._discuss_flow.system_prompt += "\n\n" + _file_manifest
                    logger.info("Injected project file manifest into system prompt")

                logger.info(
                    "Project context injected: instructions=%s, files=%d, skills=%d",
                    bool(_project_context.instructions),
                    len(_project_context.files),
                    len(_project_context.skill_ids),
                )

            while not await task.input_stream.is_empty():
                event = await self._pop_event(task)
                if event is None:
                    continue  # Skip empty/unparseable events
                message = ""
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)

                logger.info(f"Agent {self._agent_id} received new message: {message[:50]}...")

                # Build attachments list: per-message + project files
                attachments = [attachment.file_path for attachment in event.attachments] if event.attachments else []
                # Merge project file paths so they appear in the Attachments: field
                if _project_file_paths:
                    _existing_paths = set(attachments)
                    attachments.extend(p for p in _project_file_paths if p not in _existing_paths)

                # Log skills for debugging skill activation
                if event.skills:
                    logger.info(f"Agent {self._agent_id} received skills: {event.skills}")

                # Merge project skills server-side
                _msg_skills = list(event.skills or [])
                if _project_context and _project_context.skill_ids:
                    _existing_skill_set = set(_msg_skills)
                    _msg_skills.extend(_sid for _sid in _project_context.skill_ids if _sid not in _existing_skill_set)
                    if len(_msg_skills) > len(event.skills or []):
                        logger.info(
                            "Merged %d project skills (total: %d)",
                            len(_project_context.skill_ids),
                            len(_msg_skills),
                        )

                message_obj = Message(
                    message=message,
                    attachments=attachments,
                    skills=_msg_skills,
                    thinking_mode=event.thinking_mode,
                )

                # Set current task for attention manipulation (Pythinker pattern)
                if message:
                    await self._set_current_task(message)

                _flow_ended_with_error = False
                _flow_emitted_done = False
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
                        # If the title looks like a naive truncation (ends with …),
                        # fire a background LLM call to generate a smarter title.
                        if event.title.endswith("…") and message:
                            from app.domain.services.session_title_generator import generate_smart_title

                            self._fire_and_forget(
                                generate_smart_title(
                                    self._llm,
                                    self._session_id,
                                    message,
                                    self._session_repository,
                                )
                            )
                    elif isinstance(event, MessageEvent):
                        await self._session_repository.update_latest_message(
                            self._session_id, event.message, event.timestamp
                        )
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(event, WaitEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.WAITING)
                        return
                    # Track whether the flow itself terminated with an error signal.
                    # If so, skip DoneEvent — emitting it would race with the domain
                    # service's FAILED write and non-deterministically flip the status
                    # back to COMPLETED.
                    _flow_ended_with_error = isinstance(event, ErrorEvent)
                    if isinstance(event, DoneEvent):
                        _flow_emitted_done = True
                    if not await task.input_stream.is_empty():
                        break

            if _flow_ended_with_error:
                # Flow signalled a terminal error (e.g. delivery-gate block). The
                # domain service already writes FAILED when it reads the ErrorEvent;
                # reinforce here to eliminate the race.
                await self._session_repository.update_status(self._session_id, SessionStatus.FAILED)
                self._terminal_status = SessionStatus.FAILED
                final_usage_status = AgentRunStatus.FAILED
                logger.warning(
                    f"Agent {self._agent_id} flow ended with ErrorEvent — marking FAILED, skipping DoneEvent"
                )
            else:
                await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
                self._terminal_status = SessionStatus.COMPLETED
                final_usage_status = AgentRunStatus.COMPLETED
                if _flow_emitted_done:
                    logger.info(
                        "Agent %s flow already emitted DoneEvent — skipping synthetic completion event",
                        self._agent_id,
                    )
                else:
                    # Send DoneEvent when task completes normally and flow did not
                    # already terminate with one.
                    await self._put_and_add_event(task, DoneEvent())
                    logger.info(f"Agent {self._agent_id} task completed successfully")
        except asyncio.CancelledError:
            logger.info(f"Agent {self._agent_id} task cancelled")
            if self._terminal_status is None:
                self._terminal_status = SessionStatus.CANCELLED
            final_usage_status = AgentRunStatus.CANCELLED
            # Cancellation terminal status is managed by the caller path:
            # - explicit stop_session marks COMPLETED
            # - transport/disconnect cancellation marks FAILED
            # Avoid emitting DoneEvent here to prevent false "task completed"
            # UI state with unfinished plan steps.
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} task encountered exception: {e!s}")
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {e!s}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.FAILED)
            self._terminal_status = SessionStatus.FAILED
            final_usage_status = AgentRunStatus.FAILED
        finally:
            with suppress(Exception):
                from app.core.prometheus_metrics import active_sessions

                active_sessions.dec({})
            await self._finish_agent_run_usage(final_usage_status)

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

        # Deal intent can dynamically switch deep_research -> deal_finding to avoid
        # browser-first behavior for shopping tasks.
        from app.domain.services.prompts.deal_finding import detect_deal_intent

        is_deal_intent = detect_deal_intent(message.message)
        if is_deal_intent and self._research_mode != ResearchMode.DEAL_FINDING:
            previous_mode = self._research_mode
            self._research_mode = ResearchMode.DEAL_FINDING
            if self._plan_act_flow and hasattr(self._plan_act_flow, "set_research_mode"):
                self._plan_act_flow.set_research_mode(ResearchMode.DEAL_FINDING.value)
            logger.info(
                "Dynamic research mode switch applied: %s -> %s (session=%s)",
                previous_mode.value,
                ResearchMode.DEAL_FINDING.value,
                self._session_id,
            )

        # ── Runtime: before_step hook ──────────────────────────────────
        if self._lead_agent_runtime is not None and self._lead_agent_runtime.context is not None:
            try:
                runtime_ctx = self._lead_agent_runtime.context
                runtime_ctx.metadata["user_request"] = message.message
                runtime_ctx = await self._lead_agent_runtime.before_step(runtime_ctx)

                # Clarification gate: if a middleware flagged clarification needed,
                # surface the question to the user and pause the flow.
                if runtime_ctx.metadata.get("awaiting_clarification"):
                    for evt in runtime_ctx.events:
                        if isinstance(evt, dict) and evt.get("type") == "clarification":
                            yield MessageEvent(message=evt["formatted"])
                    yield WaitEvent()
                    return
            except Exception as exc:
                logger.warning("LeadAgentRuntime.before_step() failed: %s", exc)

        _step_output_text: str = ""

        async with self._usage_context():
            async for event in self._flow.run(message):
                # Check if task is paused (for user takeover) before processing each event
                if task and hasattr(task, "paused"):
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused in flow, waiting for resume...")
                        await asyncio.sleep(0.5)

                # Backward-compatible UI badge forcing for deal intent in non-deal sessions.
                if isinstance(event, ResearchModeEvent) and is_deal_intent and not self._deal_mode_emitted:
                    self._deal_mode_emitted = True
                    yield ResearchModeEvent(research_mode="deal_finding")
                    continue

                if isinstance(event, ToolEvent):
                    # TODO: move to tool function
                    emitted_events = await self._handle_tool_event(event)
                    # Auto-switch badge on first deal_scraper tool completion
                    if (
                        not self._deal_mode_emitted
                        and event.tool_name == "deal_scraper"
                        and event.status == ToolStatus.CALLED
                    ):
                        self._deal_mode_emitted = True
                        yield ResearchModeEvent(research_mode="deal_finding")
                else:
                    emitted_events = []

                # Track final textual output for runtime after_step metadata
                if isinstance(event, MessageEvent) and event.message:
                    _step_output_text = event.message

                if isinstance(event, ReportEvent):
                    await self._ensure_report_file(event)
                    # Sync attachments to storage for events that contain file references
                    # This resolves file_path to file_id for proper frontend access
                    await self._sync_event_attachments_to_storage(event)
                    self._rewrite_chart_image_urls(event)
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
                for emitted_event in emitted_events:
                    yield emitted_event

        # ── Runtime: after_step hook ──────────────────────────────────
        if self._lead_agent_runtime is not None and self._lead_agent_runtime.context is not None:
            try:
                runtime_ctx = self._lead_agent_runtime.context
                runtime_ctx.metadata["step_output"] = _step_output_text
                # Build source context for grounding evaluation
                executor = getattr(self._plan_act_flow, "executor", None)
                if executor and hasattr(executor, "_build_source_context"):
                    runtime_ctx.metadata["source_context"] = executor._build_source_context()
                await self._lead_agent_runtime.after_step(runtime_ctx)
            except Exception as exc:
                logger.warning("LeadAgentRuntime.after_step() failed: %s", exc)

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
                        emitted_events = await self._handle_tool_event(event)
                    else:
                        emitted_events = []

                    if isinstance(event, ReportEvent):
                        await self._ensure_report_file(event)
                        # Sync attachments to storage for events that contain file references
                        await self._sync_event_attachments_to_storage(event)
                        self._rewrite_chart_image_urls(event)
                    elif isinstance(event, MessageEvent):
                        # Sync attachments to storage for events that contain file references
                        await self._sync_event_attachments_to_storage(event)
                    yield event
                    for emitted_event in emitted_events:
                        yield emitted_event

        logger.info(f"Agent {self._agent_id} completed processing one message")

    async def on_done(self, task: Task) -> None:
        """Called when the task is done — run final workspace sweep to catch all files."""
        logger.info(f"Agent {self._agent_id} task done, running final file sweep")
        try:
            synced = await self._sweep_workspace_files()
            if synced:
                logger.info(
                    "Agent %s: Final sweep synced %d file(s) to session %s",
                    self._agent_id,
                    len(synced),
                    self._session_id,
                )
        except Exception as e:
            logger.warning("Agent %s: Final file sweep failed: %s", self._agent_id, e)

    async def release_task_resources(self) -> None:
        """Release memory after a single task completes without tearing down the sandbox.

        Call this when the Redis task finishes so planner/executor/verifier memory is freed.
        Does **not** destroy the sandbox, MCP, or Pythinker factory session — those may be
        shared across follow-up tasks in the same chat session.
        """
        if self._task_resources_released:
            return
        self._task_resources_released = True

        logger.info("Releasing agent task memory after run (session=%s)", self._session_id)

        # Finalize LeadAgentRuntime (runs AFTER_RUN hook on all middlewares)
        if self._lead_agent_runtime is not None and self._lead_agent_runtime.context is not None:
            try:
                await self._lead_agent_runtime.finalize()
            except Exception as exc:
                logger.warning("LeadAgentRuntime.finalize() failed: %s", exc)

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
        if self._background_tasks:
            logger.debug(f"Cancelling {len(self._background_tasks)} background tasks for session {self._session_id}")
            for task in list(self._background_tasks):
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=2.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    except Exception as e:
                        logger.warning(f"Background task cleanup raised exception: {e}")
            self._background_tasks.clear()

        await self._cleanup_flow_agents()

        # Clean up tool metadata caches to prevent unbounded growth
        self._tool_start_times.clear()
        self._file_before_cache.clear()
        self._pending_tool_calls.clear()

        # Release flow reference to allow GC of all sub-agents
        self._plan_act_flow = None
        self._discuss_flow = None
        self._fast_search_flow = None

        import gc

        gc.collect()

        logger.debug("Agent %s: task memory released (sandbox retained for session reuse)", self._agent_id)

    async def destroy(self) -> None:
        """Full teardown: session stop, app shutdown, or forced cleanup. Destroys sandbox and MCP."""
        logger.info("Starting to destroy agent task")

        await self.release_task_resources()

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
            get_mcp_registry().unregister(self._user_id)
            logger.debug(f"Destroying Agent {self._agent_id}'s MCP tool")
            try:
                await asyncio.wait_for(self._mcp_tool.cleanup(), timeout=10.0)
            except TimeoutError:
                logger.warning(f"MCP tool cleanup timed out for Agent {self._agent_id}")
            except Exception as e:
                logger.warning(f"MCP tool cleanup failed for Agent {self._agent_id}: {e}")

        import gc

        gc.collect()

        logger.debug(f"Agent {self._agent_id} has been fully closed and resources cleared")

    async def _cleanup_flow_agents(self) -> None:
        """Release memory held by all sub-agents in the current flow.

        PlanActFlow creates planner, executor, verifier, and reflection agents,
        each holding ~50K+ token conversation histories. Without explicit cleanup
        these accumulate across sequential tasks, causing ~500MB+ growth per task.

        Idempotent: safe to call from both on_done() and destroy().
        """
        if getattr(self, "_flow_agents_cleaned", False):
            return
        flow = self._flow
        if flow is None:
            return

        _agents_cleaned = 0
        _agent_names = ["planner", "executor", "verifier", "_reflection_agent"]
        for attr_name in _agent_names:
            agent = getattr(flow, attr_name, None)
            if agent is None:
                continue
            try:
                # 1. Cancel pending background tasks (memory saves, etc.)
                if hasattr(agent, "cleanup_background_tasks"):
                    await agent.cleanup_background_tasks(timeout=3.0)

                # 2. Clear conversation history — the biggest memory consumer
                # Guard against None (agent may be partially initialized after hot reload)
                if hasattr(agent, "memory") and agent.memory is not None:
                    msg_count = len(getattr(agent.memory, "messages", []))
                    agent.memory.messages = []
                    logger.debug(
                        "Cleared %d messages from %s.memory for session %s",
                        msg_count,
                        attr_name,
                        self._session_id,
                    )

                # 3. Clear efficiency nudges list
                if hasattr(agent, "_efficiency_nudges"):
                    agent._efficiency_nudges.clear()

                # 4. Clear tool result caches
                if hasattr(agent, "_tool_result_store") and agent._tool_result_store:
                    agent._tool_result_store = None

                # 5. Drop execution-scoped context (SourceTracker, StepExecutor) — no prior callers
                if attr_name == "executor" and hasattr(agent, "clear_context"):
                    try:
                        agent.clear_context()
                    except Exception as _ctx_err:
                        logger.debug("Executor clear_context skipped: %s", _ctx_err)

                _agents_cleaned += 1
            except Exception as e:
                logger.warning(
                    "Cleanup failed for %s agent in session %s: %s",
                    attr_name,
                    self._session_id,
                    e,
                )

        # 5. Clear flow-level caches
        if hasattr(flow, "_url_failure_guard"):
            flow._url_failure_guard = None
        if hasattr(flow, "_background_tasks"):
            flow._background_tasks.clear()
        if hasattr(flow, "_task_state_manager"):
            flow._task_state_manager = None

        self._flow_agents_cleaned = True
        if _agents_cleaned > 0:
            logger.info(
                "Released memory from %d flow agent(s) for session %s",
                _agents_cleaned,
                self._session_id,
            )
