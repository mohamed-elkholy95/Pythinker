import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any, ClassVar, Optional

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
    BrowserAgentToolContent,
    BrowserToolContent,
    CanvasToolContent,
    ChartToolContent,
    DoneEvent,
    ErrorEvent,
    FileToolContent,
    FlowSelectionEvent,
    McpToolContent,
    MessageEvent,
    ModeChangeEvent,
    ReportEvent,
    SearchToolContent,
    ShellToolContent,
    TitleEvent,
    ToolEvent,
    ToolStatus,
    ToolStreamEvent,
    WaitEvent,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.search import SearchResults
from app.domain.models.session import AgentMode, SessionStatus
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.comparison_chart_generator import ComparisonChartGenerator
from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.orchestration.coordinator_flow import (
    CoordinatorFlow,
    CoordinatorMode,
    create_coordinator_flow,
)
from app.domain.services.plotly_chart_orchestrator import PlotlyChartOrchestrator
from app.domain.services.tool_event_handler import ToolEventHandler
from app.domain.services.tools.mcp import MCPTool
from app.domain.utils.cancellation import CancellationToken
from app.domain.utils.diff import build_unified_diff
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.application.services.screenshot_service import ScreenshotCaptureService
    from app.domain.models.state_manifest import StateManifest
    from app.domain.services.agent_factory import PythinkerAgentFactory
    from app.domain.services.attention_injector import AttentionInjector
    from app.domain.services.context_manager import SandboxContextManager
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Type alias for events that contain attachments requiring storage sync
# Both MessageEvent and ReportEvent have an 'attachments' field of type Optional[List[FileInfo]]
EventWithAttachments = MessageEvent | ReportEvent

# File sweep constants — extensions worth delivering to users
DELIVERABLE_EXTENSIONS = {
    # Documents
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".doc",
    ".rtf",
    ".csv",
    ".tsv",
    # Code
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".bash",
    ".zsh",
    # Data
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    # Other
    ".sql",
    ".graphql",
    ".proto",
    ".dockerfile",
    ".makefile",
}
SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".cache",
    ".npm",
    ".local",
    ".config",
    "snap",
    ".pnpm-store",
    ".pki",
}
MAX_SYNC_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_SWEEP_FILES = 50


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
        self._comparison_chart_generator = ComparisonChartGenerator()
        # Phase 4: Plotly chart orchestrator (feature-flagged)
        self._plotly_chart_orchestrator = PlotlyChartOrchestrator(sandbox=self._sandbox, session_id=session_id)

        # Initialize flows based on mode
        self._plan_act_flow: PlanActFlow | None = None
        self._discuss_flow: DiscussFlow | None = None
        self._coordinator_flow: CoordinatorFlow | None = None

        if mode == AgentMode.AGENT:
            if self._flow_mode == FlowMode.COORDINATOR:
                self._init_coordinator_flow()
            else:
                self._init_plan_act_flow()
        else:
            self._init_discuss_flow()

        logger.info(
            "Flow selected: mode=%s, flow=%s, session=%s, reason=%s",
            mode.value,
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
                enable_parallel_execution=settings.enable_parallel_execution,
                parallel_max_concurrency=settings.parallel_max_concurrency,
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
                f"parallel={settings.enable_parallel_execution}, memory_service={'enabled' if self._memory_service else 'disabled'})"
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
            self._discuss_flow = DiscussFlow(
                self._agent_id,
                self._repository,
                self._session_id,
                self._session_repository,
                self._llm,
                self._json_parser,
                self._search_engine,
                default_language=settings.default_language,
            )
            logger.debug(f"Initialized DiscussFlow for agent {self._agent_id}")

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
        if self._flow_mode == FlowMode.COORDINATOR:
            self._init_coordinator_flow()
        else:
            self._init_plan_act_flow()

        await self._session_repository.update_mode(self._session_id, AgentMode.AGENT)

    @property
    def _flow(self) -> BaseFlow | None:
        """Get the current flow based on mode and configuration."""
        if self._mode == AgentMode.AGENT:
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

    # Extension-based MIME type fallback map (Phase 1: MIME hardening)
    _EXTENSION_MIME_MAP: ClassVar[dict[str, str]] = {
        ".html": "text/html",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
    }

    def _infer_content_type(self, file_path: str, existing_content_type: str | None = None) -> str | None:
        """
        Infer MIME type from file extension if not already known.

        Args:
            file_path: Path to file
            existing_content_type: Already-known content type (from FileInfo metadata)

        Returns:
            Content type string, or None if cannot be determined
        """
        if existing_content_type:
            return existing_content_type

        # Try extension-based fallback
        import os

        _, ext = os.path.splitext(file_path.lower())
        return self._EXTENSION_MIME_MAP.get(ext)

    async def _sync_file_to_storage(self, file_path: str, content_type: str | None = None) -> FileInfo | None:
        """
        Download a file from the sandbox and upload it to storage (MinIO/GridFS).

        This method:
        1. Validates the file_path is not empty
        2. Downloads the file content from the sandbox
        3. Validates the content is not empty
        4. Removes any existing file with the same path (to handle updates)
        5. Infers content_type from extension if not provided (Phase 1: MIME hardening)
        6. Uploads to storage with correct MIME type and registers with the session
        7. Returns a fully populated FileInfo with file_id

        Args:
            file_path: The path to the file in the sandbox (e.g., /home/ubuntu/report.md)
            content_type: Optional MIME type (if known from FileInfo metadata)

        Returns:
            FileInfo with valid file_id if successful, None if sync fails
        """
        # Validate input
        if not file_path or not file_path.strip():
            logger.warning(f"Agent {self._agent_id}: Cannot sync file with empty path")
            return None

        try:
            # Check if file already exists in session
            existing_file = await self._session_repository.get_file_by_path(self._session_id, file_path)

            # Download file from sandbox
            file_data = await self._sandbox.file_download(file_path)

            # Validate file content
            if file_data is None:
                logger.warning(f"Agent {self._agent_id}: File download returned None for '{file_path}'")
                return None

            if file_data.getbuffer().nbytes == 0:
                logger.warning(f"Agent {self._agent_id}: File '{file_path}' is empty (0 bytes)")
                # Still allow empty files - some use cases may need them

            # Remove existing file if present (to handle file updates)
            if existing_file and existing_file.file_id:
                logger.debug(
                    f"Agent {self._agent_id}: Removing existing file for path '{file_path}' "
                    f"(file_id={existing_file.file_id})"
                )
                await self._session_repository.remove_file(self._session_id, existing_file.file_id)

            # Extract filename from path
            file_name = file_path.split("/")[-1]
            if not file_name:
                file_name = "unnamed_file"
                logger.warning(
                    f"Agent {self._agent_id}: Could not extract filename from '{file_path}', using '{file_name}'"
                )

            # Infer content type if not provided (Phase 1: MIME hardening)
            resolved_content_type = self._infer_content_type(file_path, content_type)
            if resolved_content_type:
                logger.debug(
                    f"Agent {self._agent_id}: Uploading '{file_name}' with content_type='{resolved_content_type}'"
                )

            # Upload to storage with MIME type (Phase 1: MIME hardening fix)
            file_info = await self._file_storage.upload_file(
                file_data, file_name, self._user_id, content_type=resolved_content_type
            )

            # Validate upload result
            if not file_info:
                logger.error(f"Agent {self._agent_id}: File storage returned None for '{file_path}'")
                return None

            if not file_info.file_id:
                logger.error(f"Agent {self._agent_id}: Uploaded file has no file_id for '{file_path}'")
                return None

            # Set the file_path for reference
            file_info.file_path = file_path

            # Register file with session
            await self._session_repository.add_file(self._session_id, file_info)

            logger.debug(
                f"Agent {self._agent_id}: Successfully synced file '{file_path}' "
                f"-> file_id={file_info.file_id}, size={file_data.getbuffer().nbytes} bytes"
            )

            return file_info

        except FileNotFoundError as e:
            logger.warning(f"Agent {self._agent_id}: File not found in sandbox: '{file_path}' - {e}")
            return None
        except Exception as e:
            logger.exception(f"Agent {self._agent_id}: Failed to sync file '{file_path}': {e}")
            return None

    async def _sync_file_to_storage_with_retry(
        self,
        file_path: str,
        content_type: str | None = None,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.2,
    ) -> FileInfo | None:
        """Sync file to storage with short retries for sandbox-write race windows."""
        if max_attempts < 1:
            max_attempts = 1

        delay = initial_delay_seconds
        for attempt in range(1, max_attempts + 1):
            file_info = await self._sync_file_to_storage(file_path, content_type=content_type)
            if file_info is not None:
                return file_info

            if attempt < max_attempts:
                logger.debug(
                    "Agent %s: Retrying file sync for '%s' (attempt %s/%s after %.2fs)",
                    self._agent_id,
                    file_path,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2

        return None

    async def _sync_file_to_sandbox(self, file_id: str) -> FileInfo | None:
        """Download file from storage to sandbox"""
        try:
            file_data, file_info = await self._file_storage.download_file(file_id, self._user_id)
            file_path = "/home/ubuntu/upload/" + file_info.filename
            result = await self._sandbox.file_upload(file_data, file_path)
            if result.success:
                file_info.file_path = file_path
                return file_info
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to sync file: {e}")

    async def _sweep_workspace_files(self) -> list[FileInfo]:
        """
        Discover and sync deliverable files in the session workspace.

        Runs a find command scoped to `/workspace/<session_id>` to avoid pulling
        unrelated files from shared home directories (for example package caches).
        Then syncs any files that are not already tracked in session.files.

        Returns:
            List of newly synced FileInfo objects.
        """
        try:
            workspace_root = f"/workspace/{self._session_id}"

            # Build find command: search only session workspace, filter by extension,
            # skip junk dirs, limit size.
            prune_clauses = " -o ".join(f'-name "{d}"' for d in sorted(SKIP_DIRECTORIES))
            ext_clauses = " -o ".join(f'-name "*{ext}"' for ext in sorted(DELIVERABLE_EXTENSIONS))
            find_cmd = (
                f"find {workspace_root} "
                f"\\( {prune_clauses} \\) -prune -o "
                f"\\( -type f \\( {ext_clauses} \\) "
                f"-size -{MAX_SYNC_FILE_SIZE}c -print \\) "
                f"2>/dev/null | head -n {MAX_SWEEP_FILES}"
            )

            result = await self._sandbox.exec_command("sweep", workspace_root, find_cmd)
            if not result.success:
                logger.warning(f"Agent {self._agent_id}: File sweep find command failed: {result.message}")
                return []

            output = (result.data or {}).get("output", "")
            if not output or not output.strip():
                logger.debug(f"Agent {self._agent_id}: File sweep found no files")
                return []

            discovered_paths = [p.strip() for p in output.strip().split("\n") if p.strip()]
            # Defense-in-depth: only keep files from this session workspace.
            discovered_paths = [p for p in discovered_paths if p.startswith(f"{workspace_root}/")]
            if not discovered_paths:
                return []

            # Get already-tracked files
            session = await self._session_repository.find_by_id(self._session_id)
            existing_paths: set[str] = set()
            if session and session.files:
                for f in session.files:
                    if f.file_path:
                        existing_paths.add(f.file_path)

            # Filter to only untracked files
            new_paths = [p for p in discovered_paths if p not in existing_paths]
            if not new_paths:
                logger.debug(f"Agent {self._agent_id}: File sweep — all {len(discovered_paths)} files already tracked")
                return []

            logger.info(
                f"Agent {self._agent_id}: File sweep found {len(new_paths)} untracked files "
                f"(of {len(discovered_paths)} total)"
            )

            # Sync untracked files concurrently (capped)
            sync_tasks = [self._sync_file_to_storage(p) for p in new_paths[:MAX_SWEEP_FILES]]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            synced: list[FileInfo] = []
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    logger.warning(f"Agent {self._agent_id}: Failed to sweep-sync '{new_paths[i]}': {res}")
                elif res is not None:
                    synced.append(res)

            logger.info(f"Agent {self._agent_id}: File sweep synced {len(synced)}/{len(new_paths)} files")
            return synced

        except Exception as e:
            logger.exception(f"Agent {self._agent_id}: File sweep failed: {e}")
            return []

    async def _sync_event_attachments_to_storage(self, event: EventWithAttachments) -> None:
        """
        Sync event attachments to storage and update the event with resolved FileInfo objects.

        This method handles attachment syncing for any event type that has an attachments field
        (MessageEvent, ReportEvent, etc.). It:
        1. Filters out attachments with invalid/missing file_path
        2. Syncs valid attachments to GridFS storage concurrently
        3. Updates the event's attachments with fully resolved FileInfo objects (with file_id)
        4. Logs warnings for failed syncs but continues processing other attachments

        Args:
            event: An event with an attachments field (MessageEvent or ReportEvent)
        """
        synced_attachments: list[FileInfo] = []
        event_type = event.type

        try:
            if not event.attachments:
                logger.debug(f"Agent {self._agent_id}: {event_type} event has no attachments to sync")
                return

            # Filter valid attachments - must have a non-empty file_path
            valid_attachments = []
            for attachment in event.attachments:
                if attachment.file_path and attachment.file_path.strip():
                    valid_attachments.append(attachment)
                else:
                    logger.warning(
                        f"Agent {self._agent_id}: Skipping attachment with invalid file_path: "
                        f"file_id={attachment.file_id}, filename={attachment.filename}"
                    )

            if not valid_attachments:
                logger.debug(f"Agent {self._agent_id}: No valid attachments to sync for {event_type} event")
                event.attachments = []
                return

            logger.info(
                f"Agent {self._agent_id}: Syncing {len(valid_attachments)} attachments "
                f"for {event_type} event to storage"
            )

            # Sync all valid attachments concurrently (Phase 1: pass content_type from metadata)
            sync_tasks = [
                self._sync_file_to_storage(attachment.file_path, content_type=attachment.content_type)
                for attachment in valid_attachments
            ]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            # Process results, collecting successfully synced attachments
            for i, result in enumerate(results):
                file_path = valid_attachments[i].file_path
                if isinstance(result, Exception):
                    logger.warning(f"Agent {self._agent_id}: Failed to sync attachment '{file_path}': {result}")
                elif result is None:
                    logger.warning(f"Agent {self._agent_id}: Sync returned None for attachment '{file_path}'")
                elif not result.file_id:
                    logger.warning(f"Agent {self._agent_id}: Synced attachment '{file_path}' has no file_id")
                else:
                    synced_attachments.append(result)
                    logger.debug(
                        f"Agent {self._agent_id}: Successfully synced attachment "
                        f"'{file_path}' -> file_id={result.file_id}"
                    )
            logger.info(
                f"Agent {self._agent_id}: Successfully synced {len(synced_attachments)}/{len(valid_attachments)} "
                f"attachments for {event_type} event"
            )

        except Exception as e:
            logger.exception(
                f"Agent {self._agent_id}: Unexpected error syncing attachments for {event_type} event: {e}"
            )

        # Always update event attachments - either with synced files or empty list
        # This ensures no null file_ids remain in the event
        event.attachments = synced_attachments

    async def _ensure_report_file(self, event: ReportEvent) -> None:
        """Persist report content as a file in the sandbox and attach it to the event."""
        if not self._sandbox:
            return
        if not event.content or not event.content.strip():
            return

        existing = event.attachments or []
        expected_name = f"report-{event.id}.md"
        if not self._has_attachment(existing, expected_name):
            file_path = f"/home/ubuntu/{expected_name}"
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
        """Sync message attachments concurrently and update event attachments"""
        attachments: list[FileInfo] = []
        try:
            if event.attachments:
                # Sync all attachments concurrently
                sync_tasks = [self._sync_file_to_sandbox(attachment.file_id) for attachment in event.attachments]
                results = await asyncio.gather(*sync_tasks, return_exceptions=True)

                # Process results and add to session
                add_file_tasks = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"Sandbox sync failed: {result}")
                    elif result:
                        attachments.append(result)
                        add_file_tasks.append(self._session_repository.add_file(self._session_id, result))

                # Add files to session concurrently
                if add_file_tasks:
                    await asyncio.gather(*add_file_tasks, return_exceptions=True)

            event.attachments = attachments
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to sync attachments to event: {e}")

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

                if event.tool_name == "browser":
                    # Extract page content from function result if available
                    page_content = None
                    if event.function_result and hasattr(event.function_result, "data"):
                        result_data = event.function_result.data
                        if isinstance(result_data, dict):
                            # Try to get content from various possible fields
                            page_content = (
                                result_data.get("content") or result_data.get("text") or result_data.get("data")
                            )
                        elif isinstance(result_data, str):
                            page_content = result_data
                    event.tool_content = BrowserToolContent(content=page_content)
                elif event.tool_name == "search":
                    # Normalize search results for SearchContentView
                    search_results: ToolResult[SearchResults] = event.function_result
                    logger.debug(f"Search tool results: {search_results}")

                    normalized_results: list[Any] = []
                    if hasattr(search_results, "data") and search_results.data:
                        data = search_results.data
                        if isinstance(data, SearchResults):
                            normalized_results = data.results
                        elif isinstance(data, dict):
                            if isinstance(data.get("results"), list):
                                normalized_results = data["results"]
                            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("results"), list):
                                normalized_results = data["data"]["results"]

                    logger.info(
                        "Search tool results count=%s tool_call_id=%s",
                        len(normalized_results),
                        event.tool_call_id,
                    )
                    event.tool_content = SearchToolContent(results=normalized_results)
                elif event.tool_name == "chart":
                    # Handle chart tool events - sync HTML and PNG to storage
                    if event.function_result and hasattr(event.function_result, "data"):
                        # Safely coerce data to dict (handles non-dict or None values)
                        raw_data = getattr(event.function_result, "data", None)
                        data = dict(raw_data) if isinstance(raw_data, dict) else {}
                        tool_success = bool(getattr(event.function_result, "success", False))
                        tool_message = str(getattr(event.function_result, "message", "") or "")

                        html_path = data.get("html_path")
                        png_path = data.get("png_path")

                        # Sync files independently (not requiring both to exist)
                        html_info = None
                        png_info = None
                        sync_errors: list[str] = []
                        if not tool_success and tool_message:
                            # Preserve tool-level failures (e.g., script/runtime errors) so
                            # frontend shows a concrete cause instead of generic "unavailable".
                            sync_errors.append(tool_message)
                        elif tool_success and not html_path and not png_path:
                            # Successful result with missing paths is still an error condition.
                            sync_errors.append("Chart generation returned no output files")
                        sync_tasks = []

                        if html_path:
                            sync_tasks.append(
                                self._sync_file_to_storage_with_retry(
                                    html_path,
                                    content_type="text/html",
                                    max_attempts=3,
                                )
                            )
                        if png_path:
                            sync_tasks.append(
                                self._sync_file_to_storage_with_retry(
                                    png_path,
                                    content_type="image/png",
                                    max_attempts=3,
                                )
                            )

                        # Execute syncs concurrently if any exist
                        if sync_tasks:
                            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

                            # Map results back to html_info/png_info based on which paths were present
                            result_idx = 0
                            if html_path:
                                if isinstance(results[result_idx], Exception):
                                    sync_errors.append(f"HTML sync failed: {results[result_idx]}")
                                    logger.warning(f"HTML sync failed: {results[result_idx]}")
                                elif results[result_idx] is None:
                                    sync_errors.append("HTML file missing or empty in sandbox")
                                    logger.warning("HTML sync returned None for %s", html_path)
                                else:
                                    html_info = results[result_idx]
                                result_idx += 1
                            if png_path:
                                if isinstance(results[result_idx], Exception):
                                    sync_errors.append(f"PNG sync failed: {results[result_idx]}")
                                    logger.warning(f"PNG sync failed: {results[result_idx]}")
                                elif results[result_idx] is None:
                                    sync_errors.append("PNG file missing or empty in sandbox")
                                    logger.warning("PNG sync returned None for %s", png_path)
                                else:
                                    png_info = results[result_idx]

                        # Build error message if any sync failed
                        chart_error = "; ".join(sync_errors) if sync_errors else None

                        # Set ChartToolContent on the event
                        event.tool_content = ChartToolContent(
                            chart_type=data.get("chart_type", "bar"),
                            title=data.get("title", "Chart"),
                            html_file_id=html_info.file_id if html_info else None,
                            png_file_id=png_info.file_id if png_info else None,
                            html_filename=html_info.filename if html_info else None,
                            png_filename=png_info.filename if png_info else None,
                            html_size=data.get("html_size"),
                            data_points=data.get("data_points", 0),
                            series_count=data.get("series_count", 0),
                            error=chart_error,
                        )

                        logger.info(
                            "Chart created: type=%s title=%s data_points=%s series=%s html=%s png=%s error=%s",
                            data.get("chart_type"),
                            data.get("title"),
                            data.get("data_points"),
                            data.get("series_count"),
                            "synced" if html_info else "missing/failed",
                            "synced" if png_info else "missing/failed",
                            chart_error,
                        )
                elif event.tool_name == "shell":
                    # observation_type set by ToolEventHandler
                    if event.function_result and hasattr(event.function_result, "data"):
                        data = event.function_result.data or {}
                        if isinstance(data, dict):
                            event.stdout = data.get("output")
                            event.exit_code = data.get("returncode")
                    if "id" in event.function_args:
                        shell_result = await self._sandbox.view_shell(event.function_args["id"], console=True)
                        event.tool_content = ShellToolContent(console=shell_result.data.get("console", []))
                    else:
                        event.tool_content = ShellToolContent(console="(No Console)")
                elif event.tool_name == "file":
                    # observation_type set by ToolEventHandler
                    if "file" in event.function_args:
                        file_path = event.function_args["file"]
                        # Read file and sync to storage concurrently
                        file_read_task = self._sandbox.file_read(file_path)
                        sync_task = self._sync_file_to_storage(file_path)
                        file_read_result, _ = await asyncio.gather(file_read_task, sync_task, return_exceptions=True)
                        if isinstance(file_read_result, Exception):
                            file_content = f"(Error: {file_read_result})"
                        elif (
                            file_read_result is None
                            or not hasattr(file_read_result, "data")
                            or file_read_result.data is None
                        ):
                            file_content = "(Error: file not found or empty response)"
                        else:
                            file_content = file_read_result.data.get("content", "")
                        event.tool_content = FileToolContent(content=file_content)

                        before_content = self._file_before_cache.pop(event.tool_call_id, "")
                        diff_text = build_unified_diff(before_content, file_content, file_path)
                        if diff_text:
                            event.diff = diff_text
                    else:
                        event.tool_content = FileToolContent(content="(No Content)")
                elif event.tool_name == "mcp":
                    logger.debug(f"Processing MCP tool event: function_result={event.function_result}")
                    if event.function_result:
                        if hasattr(event.function_result, "data") and event.function_result.data:
                            logger.debug(f"MCP tool result data: {event.function_result.data}")
                            event.tool_content = McpToolContent(result=event.function_result.data)
                        elif hasattr(event.function_result, "success") and event.function_result.success:
                            logger.debug(f"MCP tool result (success, no data): {event.function_result}")
                            result_data = (
                                event.function_result.model_dump()
                                if hasattr(event.function_result, "model_dump")
                                else str(event.function_result)
                            )
                            event.tool_content = McpToolContent(result=result_data)
                        else:
                            logger.debug(f"MCP tool result (fallback): {event.function_result}")
                            event.tool_content = McpToolContent(result=str(event.function_result))
                    else:
                        logger.warning("MCP tool: No function_result found")
                        event.tool_content = McpToolContent(result="No result available")

                    logger.debug(f"MCP tool_content set to: {event.tool_content}")
                    if event.tool_content:
                        logger.debug(f"MCP tool_content.result: {event.tool_content.result}")
                        logger.debug(f"MCP tool_content dict: {event.tool_content.model_dump()}")
                elif event.tool_name in ("browser_agent", "browsing"):
                    logger.debug(f"Processing {event.tool_name} tool event: function_result={event.function_result}")
                    if event.function_result:
                        result_data = event.function_result.data if hasattr(event.function_result, "data") else {}
                        steps_taken = result_data.get("steps_taken", 0) if isinstance(result_data, dict) else 0
                        result = (
                            result_data.get("result", str(result_data))
                            if isinstance(result_data, dict)
                            else str(result_data)
                        )
                        event.tool_content = BrowserAgentToolContent(result=result, steps_taken=steps_taken)
                    else:
                        event.tool_content = BrowserAgentToolContent(result="No result available", steps_taken=0)
                elif event.tool_name == "agent_mode":
                    # agent_mode is a control tool, no special content needed
                    logger.debug("Processing agent_mode tool event")
                elif event.tool_name == "message":
                    # message tool events don't need tool_content
                    logger.debug("Processing message tool event")
                elif event.tool_name == "code_executor":
                    # observation_type set by ToolEventHandler
                    # Code execution output shown in terminal-like view
                    if event.function_result and hasattr(event.function_result, "data"):
                        data = event.function_result.data
                        if isinstance(data, dict):
                            # Artifact operations should surface file content directly
                            if event.function_name == "code_save_artifact":
                                content = event.function_args.get("content")
                                if isinstance(content, str):
                                    event.tool_content = FileToolContent(content=content)
                                else:
                                    event.tool_content = FileToolContent(content="")
                                artifact_path = data.get("path")
                                if isinstance(artifact_path, str):
                                    event.file_path = artifact_path
                                    if getattr(event.function_result, "success", False):
                                        await self._sync_file_to_storage(artifact_path)
                            elif event.function_name == "code_read_artifact":
                                content = data.get("content")
                                if isinstance(content, str):
                                    event.tool_content = FileToolContent(content=content)
                                else:
                                    event.tool_content = FileToolContent(content="")
                                artifact_path = data.get("path")
                                if isinstance(artifact_path, str):
                                    event.file_path = artifact_path
                                else:
                                    artifact_name = data.get("filename")
                                    if isinstance(artifact_name, str):
                                        event.file_path = artifact_name
                            else:
                                # Extract stdout/stderr for console display
                                console_output = []
                                if data.get("stdout"):
                                    console_output.append(data["stdout"])
                                if data.get("stderr"):
                                    console_output.append(f"[stderr] {data['stderr']}")
                                if data.get("exit_code") is not None:
                                    console_output.append(f"[exit code: {data['exit_code']}]")
                                event.stdout = data.get("stdout")
                                event.stderr = data.get("stderr")
                                event.exit_code = data.get("exit_code")
                                event.tool_content = ShellToolContent(
                                    console="\n".join(console_output) if console_output else "(No output)"
                                )

                                # Sync artifacts to session files
                                artifacts = data.get("artifacts", [])
                                if artifacts:
                                    sync_tasks = []
                                    for artifact in artifacts:
                                        artifact_path = artifact.get("path") if isinstance(artifact, dict) else None
                                        if artifact_path:
                                            sync_tasks.append(self._sync_file_to_storage(artifact_path))
                                    if sync_tasks:
                                        await asyncio.gather(*sync_tasks, return_exceptions=True)
                                        logger.debug(
                                            f"Agent {self._agent_id}: Synced {len(sync_tasks)} artifacts from code_executor"
                                        )
                        else:
                            event.tool_content = ShellToolContent(console=str(data) if data else "(No output)")
                    else:
                        event.tool_content = ShellToolContent(console="(No output)")
                elif event.tool_name == "canvas":
                    operation = event.function_name.replace("canvas_", "") if event.function_name else "unknown"
                    project_id: str | None = None
                    project_name: str | None = None
                    element_count = 0
                    image_urls: list[str] | None = None

                    data: Any | None = None
                    if event.function_result and hasattr(event.function_result, "data"):
                        data = event.function_result.data

                    if isinstance(data, dict):
                        project_id = data.get("project_id") or data.get("id")
                        project_name = data.get("project_name") or data.get("name")
                        if isinstance(data.get("elements"), list):
                            element_count = len(data["elements"])
                        elif isinstance(data.get("element_count"), int):
                            element_count = data["element_count"]
                        else:
                            pages = data.get("pages")
                            if isinstance(pages, list):
                                for page in pages:
                                    if isinstance(page, dict):
                                        elems = page.get("elements")
                                        if isinstance(elems, list):
                                            element_count += len(elems)
                        if isinstance(data.get("image_url"), str):
                            image_urls = [data["image_url"]]
                        elif isinstance(data.get("image_urls"), list):
                            image_urls = [str(url) for url in data["image_urls"]]

                    if not project_id:
                        arg_project_id = event.function_args.get("project_id")
                        if isinstance(arg_project_id, str):
                            project_id = arg_project_id

                    if not project_name:
                        arg_name = event.function_args.get("name")
                        if isinstance(arg_name, str):
                            project_name = arg_name

                    event.tool_content = CanvasToolContent(
                        operation=operation,
                        project_id=project_id,
                        project_name=project_name,
                        element_count=element_count,
                        image_urls=image_urls,
                    )
                elif event.tool_name == "wide_research":
                    # wide_research results are handled via WideResearchEvent and ReportEvent
                    logger.debug("Processing wide_research tool event")
                elif event.tool_name == "export":
                    # Sync exported files (archives, reports) to session files
                    if event.function_result and hasattr(event.function_result, "data"):
                        data = event.function_result.data
                        if isinstance(data, dict):
                            # Export tools return the created file path
                            export_path = data.get("path") or data.get("file_path") or data.get("output_path")
                            if export_path:
                                await self._sync_file_to_storage(export_path)
                                logger.debug(f"Agent {self._agent_id}: Synced export file '{export_path}'")
                else:
                    logger.warning(f"Agent {self._agent_id} received unknown tool event: {event.tool_name}")
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
                    deep_research=event.deep_research or False,
                )

                # Set current task for attention manipulation (Pythinker pattern)
                if message:
                    await self._set_current_task(message)

                async for event in self._run_flow(message_obj, task):
                    # Check if task is paused (for user takeover)
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused, waiting for resume...")
                        await asyncio.sleep(0.5)

                    # ToolStreamEvent is ephemeral (preview only) — send to SSE but skip persistence
                    if isinstance(event, ToolStreamEvent):
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

        async with self._usage_context():
            async for event in self._flow.run(message):
                # Check if task is paused (for user takeover) before processing each event
                if task and hasattr(task, "paused"):
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused in flow, waiting for resume...")
                        await asyncio.sleep(0.5)

                if isinstance(event, ToolEvent):
                    # TODO: move to tool function
                    await self._handle_tool_event(event)
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
                deep_research=message.deep_research,
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
