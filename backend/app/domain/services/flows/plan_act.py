import asyncio
import importlib
import logging
import os
import re
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from app.domain.exceptions.base import LLMKeysExhaustedError, SessionNotFoundException
from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.logging import get_agent_logger
from app.domain.external.sandbox import Sandbox
from app.domain.external.scraper import Scraper
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    ConfidenceEvent,
    DoneEvent,
    ErrorEvent,
    FlowTransitionEvent,
    MessageEvent,
    PlanEvent,
    PlanningPhase,
    PlanStatus,
    ProgressEvent,
    ReportEvent,
    ResearchModeEvent,
    StepEvent,
    StepStatus,
    TitleEvent,
    ToolEvent,
    ToolStatus,
    VerificationEvent,
    VerificationStatus,
    WaitEvent,
    WideResearchEvent,
    WideResearchStatus,
    WorkspaceEvent,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Step
from app.domain.models.request_contract import RequestContract
from app.domain.models.session import SessionStatus
from app.domain.models.state_model import AgentStatus, StateTransitionError, validate_transition
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.complexity_assessor import ComplexityAssessor
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.planner import PlannerAgent

# Import research task detection for acknowledgment messages
from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator
from app.domain.services.flows.base import BaseFlow, FlowStatus
from app.domain.services.flows.fast_ack_refiner import FastAcknowledgmentRefiner
from app.domain.services.flows.fast_path import (
    FastPathRouter,
    QueryIntent,
    is_suggestion_follow_up_message,
)
from app.domain.services.flows.phase_router import PhaseRouter
from app.domain.services.flows.prompt_quick_validator import (
    CorrectionEvent,
    PromptQuickValidator,
    SimilarityMatcher,
    SpellCorrectionProvider,
)
from app.domain.services.flows.request_contract_extractor import extract as extract_request_contract
from app.domain.services.flows.step_failure import StepFailureHandler
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.chart import ChartTool
from app.domain.services.tools.code_executor import CodeExecutorTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.shell import ShellTool
from app.domain.utils.json_parser import JsonParser

# BrowserAgentTool is optional (requires browser_use package)
try:
    from app.domain.services.tools.browser_agent import BROWSER_USE_AVAILABLE, BrowserAgentTool
except ImportError:
    BrowserAgentTool = None
    BROWSER_USE_AVAILABLE = False

from app.core.config import get_settings
from app.domain.external.observability import get_metrics, get_tracer
from app.domain.services.agents.compliance_gates import ComplianceReport, get_compliance_gates
from app.domain.services.agents.delivery_fidelity import DeliveryFidelityChecker
from app.domain.services.agents.error_handler import ErrorContext, ErrorHandler, ErrorType

# Import error integration bridge for coordinated health assessment
from app.domain.services.agents.error_integration import (
    AgentHealthLevel,
    ErrorIntegrationBridge,
)
from app.domain.services.agents.guardrails import InputGuardrails, OutputGuardrails

# Import memory management for Phase 3 proactive compaction
from app.domain.services.agents.memory_manager import (
    get_memory_manager,
)
from app.domain.services.agents.response_policy import (
    ResponsePolicy,
    ResponsePolicyEngine,
    TaskAssessment,
    VerbosityMode,
)
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.services.flows.error_recovery_handler import ErrorRecoveryHandler
from app.domain.services.flows.flow_step_executor import FlowStepExecutor
from app.domain.services.orchestration.agent_factory import (
    DefaultAgentFactory,
    SpecializedAgentFactory,
)

# Import orchestration components for multi-agent dispatch
from app.domain.services.orchestration.agent_types import (
    AgentRegistry,
    get_agent_registry,
)
from app.domain.services.prediction.failure_predictor import FailurePredictor
from app.domain.services.tools.canvas import CanvasTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.skill_creator import get_skill_creator_tools
from app.domain.services.tools.skill_invoke import create_skill_invoke_tool
from app.domain.services.validation.plan_validator import PlanValidator
from app.domain.utils.cancellation import CancellationToken

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


def should_bypass_fast_path_for_suggestion(message: Message, has_recent_assistant_reply: bool) -> bool:
    """Determine if message should bypass fast path due to being a suggestion follow-up.

    Uses two detection methods (in priority order):
    1. Metadata-based: Check message.follow_up_source == "suggestion_click" (primary)
    2. Regex-based: Check if message matches known suggestion patterns (fallback)

    Args:
        message: The user message with potential follow-up metadata
        has_recent_assistant_reply: Whether there's a recent assistant message in session

    Returns:
        True if should bypass fast path (use full contextual flow)
        False if can proceed with fast path evaluation
    """
    # Primary detection: Metadata from frontend (check BEFORE has_recent_assistant_reply guard)
    # This ensures explicit suggestion_click metadata always bypasses fast path
    if message.follow_up_source == "suggestion_click":
        return True

    # For regex/fallback detection, require recent assistant reply
    if not has_recent_assistant_reply:
        return False

    # Fallback detection: Regex pattern matching (backwards compatibility)
    return is_suggestion_follow_up_message(message.message)


class PlanActFlow(BaseFlow):
    """Plan-Act flow with optional multi-agent step dispatch.

    When enable_multi_agent is True, steps are dispatched to specialized agents
    based on their descriptions using the AgentRegistry.
    """

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        session_id: str,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox: Sandbox,
        browser: Browser,
        json_parser: JsonParser,
        mcp_tool: MCPTool,
        search_engine: SearchEngine | None = None,
        cdp_url: str | None = None,
        enable_verification: bool = True,
        enable_multi_agent: bool = True,
        memory_service: Optional["MemoryService"] = None,
        user_id: str | None = None,
        file_sweep_callback: Callable[[], Coroutine[Any, Any, None]] | None = None,
        feature_flags: dict[str, bool] | None = None,
        browser_agent_enabled: bool = False,
        alert_port=None,
        rapidfuzz_matcher: SimilarityMatcher | None = None,
        symspell_provider: SpellCorrectionProvider | None = None,
        correction_event_sink: Callable[[CorrectionEvent], None] | None = None,
        feedback_lookup: Callable[[str], str | None] | None = None,
        cancel_token: CancellationToken | None = None,
        research_mode: str = "deep_research",
        knowledge_base_service=None,
        prompt_profile_repo=None,
        scraper: Scraper | None = None,
        checkpoint_manager=None,
    ):
        self._feature_flags = feature_flags
        self._research_mode = research_mode
        self._workspace_output_path: str | None = None  # Set during run() for deep_research
        # PR-7: lazy PromptProfileResolver — built on first use if feature flags are active
        self._profile_resolver: Any = None
        self._prompt_profile_repo = prompt_profile_repo
        self._alert_port = alert_port
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._log = get_agent_logger(agent_id, session_id)
        self.status = AgentStatus.IDLE
        self._cancel_token = cancel_token or CancellationToken.null()
        self._last_transition_time: float = time.time()
        self.plan = None
        self._file_sweep_callback = file_sweep_callback

        # Store references for multi-agent factory initialization
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._json_parser = json_parser
        self._mcp_tool = mcp_tool
        self._search_engine = search_engine
        self._search_tool: SearchTool | None = None

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # WP-6: CheckpointManager for cross-restart workflow persistence
        self._checkpoint_manager = checkpoint_manager

        # Phase 4: Track selected prompt variant so record_outcome() can close the bandit loop
        self._selected_prompt_variant_id: str | None = None
        self._planning_start_time: float | None = None

        # Conversation context: real-time retrieval for step execution
        from app.domain.services.conversation_context_service import get_conversation_context_service

        self._conversation_context_service = get_conversation_context_service()

        # Phase 5: Checkpoint tracking for incremental progress saves
        self._checkpoint_interval = 5  # Write checkpoint every 5 steps
        self._steps_completed_count = 0

        # Role-scoped memory for context injection (Phase 4: Role-Scoped Memory Access)
        from app.domain.services.role_scoped_memory import RoleScopedMemory

        self._scoped_memory: dict[str, RoleScopedMemory] = {}
        if memory_service and user_id:
            self._scoped_memory = {
                "planner": RoleScopedMemory(memory_service, "planner", user_id),
                "executor": RoleScopedMemory(memory_service, "executor", user_id),
                "researcher": RoleScopedMemory(memory_service, "researcher", user_id),
                "reflector": RoleScopedMemory(memory_service, "reflector", user_id),
            }

        # State management for error recovery (delegated to ErrorRecoveryHandler)
        self._error_recovery = ErrorRecoveryHandler(ErrorHandler())

        # Backward-compatible aliases for callers that read these attributes
        self._error_handler = self._error_recovery.error_handler

        # Verification state (Phase 1: Plan-Verify-Execute)
        self._verification_verdict: str | None = None
        self._verification_feedback: str | None = None
        self._verification_loops = 0
        self._max_verification_loops = 1  # Reduced from 2 to 1 for faster response

        # Plan validation failure tracking
        self._plan_validation_failures = 0
        self._max_plan_validation_failures = 3

        # Phase 2: Proactive token budget management (feature-flagged)
        self._token_budget = None  # Created at flow start if flag enabled

        tools = [
            ShellTool(sandbox),
            BrowserTool(browser, scraper=scraper),
            FileTool(sandbox, session_id=session_id),
            CodeExecutorTool(sandbox=sandbox, session_id=session_id),
            ChartTool(sandbox=sandbox, session_id=session_id),
            MessageTool(),
            IdleTool(),
            mcp_tool,
        ]

        # Only add search tool when search_engine is not None
        # Pass browser to SearchTool for visual search when search_prefer_browser is enabled
        if search_engine:
            self._search_tool = SearchTool(search_engine, browser=browser, scraper=scraper)
            tools.append(self._search_tool)

        # Add browser agent tool when cdp_url is available, enabled, and browser_use is installed
        if cdp_url and browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
            try:
                tools.append(BrowserAgentTool(cdp_url))
                logger.info(f"Browser agent tool enabled for Agent {agent_id}")
            except ImportError as e:
                logger.warning(f"Browser agent tool not available: {e}")

        # Add ScrapingTool when enabled (structured extraction + stealth batch fetch)
        if get_settings().scraping_tool_enabled and scraper:
            from app.domain.services.tools.scraping import ScrapingTool

            tools.append(ScrapingTool(scraper=scraper, memory_service=memory_service, user_id=user_id))
            logger.info(f"ScrapingTool enabled for Agent {agent_id}")

        # Add skill creator tools for custom skill creation (Phase 3: Custom Skills)
        # Pending events queue for skill delivery events from tools
        self._pending_events: list[BaseEvent] = []
        skill_tools = get_skill_creator_tools(
            user_id=user_id,
            emit_event=lambda e: self._pending_events.append(e),
        )
        tools.extend(skill_tools)
        logger.debug(f"Added {len(skill_tools)} skill creator tools for Agent {agent_id}")

        # Phase 3.5: Skill invoke tool (initialized with empty skills, populated in run())
        # This meta-tool allows AI to invoke skills dynamically during execution
        self._skill_invoke_tool = create_skill_invoke_tool(
            available_skills=[],
            session_id=session_id,
        )
        tools.append(self._skill_invoke_tool)
        self._skill_invoke_initialized = False

        # Canvas tool for visual design creation
        from app.application.services.canvas_service import get_canvas_service

        canvas_service = get_canvas_service()
        canvas_tool = CanvasTool(
            canvas_service=canvas_service,
            user_id=user_id or "",
            session_id=session_id,
        )
        tools.append(canvas_tool)
        logger.debug(f"Added canvas tool for Agent {agent_id}")

        # Knowledge base tool (conditional on feature flag + service availability)
        if knowledge_base_service is not None:
            try:
                from app.domain.services.tools.knowledge_base import KnowledgeBaseTool

                kb_tool = KnowledgeBaseTool(
                    kb_service=knowledge_base_service,
                    user_id=user_id or "",
                )
                tools.append(kb_tool)
                logger.debug(f"Added knowledge base tool for Agent {agent_id}")
            except Exception as _kb_exc:
                logger.warning("Failed to add knowledge base tool: %s", _kb_exc)

        # Create Tree-of-Thoughts explorer if feature enabled
        thought_tree_explorer = None
        flags = self._resolve_feature_flags()
        if flags.get("tree_of_thoughts"):
            try:
                from app.domain.services.agents.reasoning.thought_tree import (
                    ThoughtTreeExplorer,
                )

                thought_tree_explorer = ThoughtTreeExplorer(llm=llm)
                logger.debug("Tree-of-Thoughts explorer enabled for planner")
            except Exception as e:
                logger.warning(f"Failed to create ThoughtTreeExplorer: {e}")

        # Create planner and execution agents
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            memory_service=memory_service,
            user_id=user_id,
            thought_tree_explorer=thought_tree_explorer,
            feature_flags=feature_flags,
            cancel_token=self._cancel_token,
            search_engine=self._search_engine,
        )
        logger.debug(f"Created planner agent for Agent {self._agent_id}")

        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            memory_service=memory_service,
            user_id=user_id,
            feature_flags=feature_flags,
            cancel_token=self._cancel_token,
        )
        logger.debug(f"Created execution agent for Agent {self._agent_id}")

        # Create verifier agent (Phase 1: Plan-Verify-Execute)
        self.verifier: VerifierAgent | None = None
        if enable_verification:
            # Create self-consistency checker if feature enabled
            consistency_checker = None
            if flags.get("self_consistency"):
                try:
                    from app.domain.services.agents.reasoning.self_consistency import (
                        SelfConsistencyChecker,
                    )

                    consistency_checker = SelfConsistencyChecker(llm=llm, default_n_paths=3)
                    logger.debug("Self-consistency checker enabled for verifier")
                except Exception as e:
                    logger.warning(f"Failed to create SelfConsistencyChecker: {e}")

            self.verifier = VerifierAgent(
                llm=llm,
                json_parser=json_parser,
                tools=tools,
                config=VerifierConfig(
                    enabled=True,
                    skip_simple_plans=True,
                    simple_plan_max_steps=3,  # Increased from 2 to skip verification for more plans
                    max_revision_loops=1,  # Reduced from 2 for faster response
                ),
                self_consistency_checker=consistency_checker,
                feature_flags=feature_flags,
            )
            logger.info(f"VerifierAgent enabled for Agent {agent_id}")

        # Phase 3: ReflectionAgent for mid-execution course correction and memory write-back.
        # Wired here so the default PlanActFlow path benefits from reflection — previously
        # only the deprecated PlanActGraphFlow invoked the reflector.
        self._reflection_agent = None
        if flags.get("feature_meta_cognition_enabled", True):
            try:
                from app.domain.services.agents.reflection import ReflectionAgent

                self._reflection_agent = ReflectionAgent(
                    llm=llm,
                    json_parser=json_parser,
                    feature_flags=feature_flags,
                    memory_service=memory_service,
                    user_id=user_id,
                    session_id=session_id,
                )
                logger.debug("ReflectionAgent initialized for PlanActFlow (default path)")
            except Exception as _refl_err:
                logger.warning("ReflectionAgent unavailable: %s", _refl_err)

        # Track background tasks for cleanup
        self._background_tasks: set = set()

        # Debouncing for background tasks (P1.4: reduce event loop contention)
        self._last_compact_time: datetime | None = None
        self._compact_debounce_seconds = 10  # Min seconds between compactions
        self._last_save_time: datetime | None = None
        self._save_debounce_seconds = 5  # Min seconds between saves

        # Task state manager for todo recitation
        self._task_state_manager = TaskStateManager(sandbox)
        self.planner._task_state_manager = self._task_state_manager
        self.executor._task_state_manager = self._task_state_manager

        # Compliance gates for output quality checks
        self._compliance_gates = get_compliance_gates()

        # Multi-agent dispatch configuration
        self._enable_multi_agent = enable_multi_agent
        self._agent_registry: AgentRegistry | None = None

        self._agent_factory: DefaultAgentFactory | None = None
        self._specialized_agents: dict[str, BaseAgent] = {}

        if enable_multi_agent:
            self._init_multi_agent_dispatch()

        # Extracted sub-coordinators
        settings = get_settings()
        self._ack_generator = AcknowledgmentGenerator()
        self._ack_refiner = FastAcknowledgmentRefiner(
            llm=llm,
            fallback_generator=self._ack_generator,
            timeout_seconds=settings.fast_ack_refiner_timeout,
            traceback_sample_rate=settings.fast_ack_refiner_traceback_sample_rate,
        )
        self._prompt_quick_validator = PromptQuickValidator(
            enabled=settings.typo_correction_enabled,
            log_corrections=settings.typo_correction_log_events,
            confidence_threshold=settings.typo_correction_confidence_threshold,
            rapidfuzz_score_cutoff=settings.typo_correction_rapidfuzz_score_cutoff,
            max_suggestions=settings.typo_correction_max_suggestions,
            rapidfuzz_matcher=rapidfuzz_matcher,
            symspell_provider=symspell_provider,
            correction_event_sink=correction_event_sink,
            feedback_lookup=feedback_lookup,
        )
        self._step_failure_handler = StepFailureHandler()
        self._phase_router = PhaseRouter(self._step_failure_handler)

        # Step-level orchestration — delegated to FlowStepExecutor (Phase 3B extraction)
        self._flow_step_executor = FlowStepExecutor(
            default_executor=self.executor,
            phase_router=self._phase_router,
            step_failure_handler=self._step_failure_handler,
            agent_id=self._agent_id,
            session_id=self._session_id,
            enable_multi_agent=self._enable_multi_agent,
            agent_registry=self._agent_registry,
            agent_factory=self._agent_factory,
        )
        # Backward-compatible alias: _specialized_agents shared by reference
        self._specialized_agents = self._flow_step_executor._specialized_agents

        # Workflow loop safety limits
        self._max_workflow_transitions = 300

        # Phase 3: Proactive memory compaction tracking
        self._memory_manager = get_memory_manager()
        self._iteration_count = 0
        self._recent_tools: list[str] = []
        self._max_recent_tools = 10

        # Cache complexity score for skip-update optimization
        self._cached_complexity: float | None = None

        # Phase tracking for structured agent flow
        self._current_phase_id: str | None = None

        # Adaptive response policy and clarification state
        self._input_guardrails = InputGuardrails()
        self._response_policy_engine = ResponsePolicyEngine()
        self._response_policy: ResponsePolicy | None = None
        self._task_assessment: TaskAssessment | None = None

        # Phase 1: Request contract (extracted at ingress when enable_request_contract)
        self._request_contract: RequestContract | None = None

        # Error Integration Bridge for coordinated health assessment
        self._error_bridge = ErrorIntegrationBridge(
            error_handler=self._error_handler,
            memory_manager=self._memory_manager,
            feature_flags=feature_flags,
        )

    def set_circuit_breaker(self, circuit_breaker) -> None:
        """Inject circuit breaker for tool-level failure protection.

        Called by the task runner after construction to avoid
        domain→infrastructure import violations.
        """
        self.executor._circuit_breaker = circuit_breaker

    def set_cancel_token(self, cancel_token: CancellationToken | None) -> None:
        """Inject or replace cancellation token for cooperative cancellation checks."""
        self._cancel_token = cancel_token or CancellationToken.null()

    async def _check_cancelled(self) -> None:
        """Raise CancelledError when cancellation has been requested."""
        await self._cancel_token.check_cancelled()

    def _track_background_task(self, task: asyncio.Task[Any]) -> None:
        """Track background tasks and surface failures."""
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        """Consume background task result and log non-cancellation failures."""
        self._background_tasks.discard(task)
        with suppress(asyncio.CancelledError):
            error = task.exception()
            if error is not None:
                logger.warning("PlanActFlow background task failed for agent %s: %s", self._agent_id, error)

    def _resolve_feature_flags(self) -> dict[str, bool]:
        """Return injected feature flags, falling back to core config."""
        if self._feature_flags is not None:
            return self._feature_flags
        from app.core.config import get_feature_flags

        return get_feature_flags()

    def _resolve_alert_port(self):
        """Return injected alert port, falling back to core alert manager."""
        if self._alert_port is not None:
            return self._alert_port
        from app.core.alert_manager import get_alert_manager

        return get_alert_manager()

    # ------------------------------------------------------------------
    # PR-7: Prompt profile resolver helpers
    # ------------------------------------------------------------------

    def _get_profile_resolver(self) -> Any:
        """Return the PromptProfileResolver, building it lazily if needed.

        Returns None when both ``feature_prompt_profile_runtime`` and
        ``feature_prompt_profile_shadow`` are disabled (fast path — zero overhead).
        """
        settings = get_settings()
        runtime_enabled = getattr(settings, "feature_prompt_profile_runtime", False)
        shadow_enabled = getattr(settings, "feature_prompt_profile_shadow", True)
        if not runtime_enabled and not shadow_enabled:
            return None
        if self._profile_resolver is None:
            try:
                from app.domain.services.prompt_optimization.profile_resolver import (
                    build_profile_resolver_from_settings,
                )

                # Use injected repository if available, otherwise build from settings only
                repo = self._prompt_profile_repo
                if repo is not None:
                    self._profile_resolver = build_profile_resolver_from_settings(repo)
                else:
                    logger.debug("No prompt profile repository injected; profile resolver disabled")
                    return None
                logger.debug("PromptProfileResolver initialized for agent %s", self._agent_id)
            except Exception as exc:
                logger.warning("Failed to initialize PromptProfileResolver: %s", exc)
                return None
        return self._profile_resolver

    async def _resolve_profile_patch(self, target: Any) -> str | None:
        """Resolve the prompt profile patch text for ``target`` (PLANNER or EXECUTION).

        Returns:
            Patch text string when an active/canary profile applies.
            None in baseline, shadow, or error cases (zero behavior change).
        """
        resolver = self._get_profile_resolver()
        if resolver is None:
            return None
        try:
            from app.core.prometheus_metrics import record_profile_selection
            from app.domain.models.prompt_profile import ProfileSelectionMode

            sel = await resolver.resolve(self._session_id, target=target)
            record_profile_selection(
                profile_id=sel.profile_id or "none",
                target=target.value,
                mode=sel.mode.value,
            )
            if sel.mode == ProfileSelectionMode.SHADOW:
                logger.debug(
                    "Profile resolver: shadow mode for target=%s profile=%s (not applied)",
                    target.value,
                    sel.profile_id,
                )
                with suppress(Exception):
                    from app.core.prometheus_metrics import record_shadow_delta

                    record_shadow_delta(metric="shadow_evaluated", target=target.value, delta=0.0)
                return None
            if sel.mode == ProfileSelectionMode.BASELINE:
                return None
            # ACTIVE or CANARY — extract patch text
            if sel.profile is not None:
                patch = sel.profile.get_patch(target)
                if patch is not None:
                    logger.info(
                        "Applying profile patch %s/%s to %s prompt",
                        sel.profile_id,
                        patch.variant_id,
                        target.value,
                    )
                    return patch.patch_text
            return None
        except Exception as exc:
            logger.warning("Failed to resolve profile patch for %s: %s", target.value, exc)
            with suppress(Exception):
                from app.core.prometheus_metrics import record_profile_fallback

                record_profile_fallback(reason=type(exc).__name__)
            return None

    def _init_multi_agent_dispatch(self) -> None:
        """Initialize the multi-agent dispatch system."""
        self._agent_registry = get_agent_registry()
        self._agent_factory = SpecializedAgentFactory(
            agent_repository=self._repository,
            llm=self._llm,
            json_parser=self._json_parser,
            sandbox=self._sandbox,
            browser=self._browser,
            search_engine=self._search_engine,
            mcp_tool=self._mcp_tool,
        )
        logger.info(f"Multi-agent dispatch enabled for Agent {self._agent_id}")

    async def _init_skill_invoke_tool(self) -> None:
        """Initialize the skill_invoke tool with available skills.

        Phase 3.5: Populate the skill_invoke meta-tool with AI-invokable skills
        so the agent can dynamically invoke skills during execution.
        """
        if self._skill_invoke_initialized:
            return

        try:
            from app.domain.services.skill_registry import get_skill_registry

            registry = await get_skill_registry()
            ai_skills = await registry.get_ai_invokable_skills()

            if ai_skills:
                self._skill_invoke_tool.set_available_skills(ai_skills)
                logger.info(f"Initialized skill_invoke tool with {len(ai_skills)} AI-invokable skills")
            else:
                logger.debug("No AI-invokable skills available for skill_invoke tool")

            self._skill_invoke_initialized = True

        except Exception as e:
            logger.warning(f"Failed to initialize skill_invoke tool: {e}")
            self._skill_invoke_initialized = True  # Avoid repeated failures

    async def _verify_browser_ready(self, session) -> bool:
        """Verify browser is ready for fast path operations.

        Phase 2 enhancement: Quick health check to determine if browser
        can be used for fast path, enabling instant "open X" responses.

        Args:
            session: Current session object

        Returns:
            True if browser is verified ready, False otherwise
        """
        if not session.sandbox_id:
            logger.debug("No sandbox_id, browser not ready")
            return False

        try:
            # Quick browser health check via sandbox
            from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

            sandbox = await DockerSandbox.get(session.sandbox_id)
            if not sandbox:
                logger.debug(f"Sandbox {session.sandbox_id} not found")
                return False

            # Check browser health (should be instant if pre-warmed)
            if hasattr(sandbox, "browser_health_check"):
                is_healthy = await asyncio.wait_for(sandbox.browser_health_check(), timeout=2.0)
                if is_healthy:
                    logger.debug("Browser health check passed")
                    return True
                logger.debug("Browser health check failed")
                return False

            # Fallback: check if browser object is healthy
            if self._browser and hasattr(self._browser, "is_healthy"):
                is_healthy = self._browser.is_healthy()
                logger.debug(f"Browser is_healthy: {is_healthy}")
                return is_healthy

            # Conservative default: assume ready if we have a browser
            return self._browser is not None

        except TimeoutError:
            logger.warning("Browser health check timed out")
            return False
        except Exception as e:
            logger.warning(f"Browser readiness check failed: {e}")
            return False

    def _extract_skill_creator_command(self, user_message: str) -> tuple[str, str] | None:
        """Extract /skill-creator command and arguments from the user message."""
        match = re.search(r"/(skill-creator)(?![\w-])(?:\s+([^\n]*))?", user_message, flags=re.IGNORECASE)
        if not match:
            return None
        arguments = (match.group(2) or "").strip()
        return "skill-creator", arguments

    async def _emit_skill_invoke_events(self, skill_name: str, arguments: str) -> AsyncGenerator[BaseEvent, None]:
        """Emit tool events for skill_invoke to mirror skill loading UX."""
        await self._init_skill_invoke_tool()
        tool_call_id = str(uuid4())
        function_args = {"skill_name": skill_name, "arguments": arguments}

        calling_event = self.executor._create_tool_event(
            tool_call_id=tool_call_id,
            tool_name="skill",
            function_name="skill_invoke",
            function_args=function_args,
            status=ToolStatus.CALLING,
        )
        yield calling_event

        try:
            result = await self._skill_invoke_tool.execute(skill_name=skill_name, arguments=arguments)
        except Exception as e:
            result = {"success": False, "error": str(e)}

        called_event = self.executor._create_tool_event(
            tool_call_id=tool_call_id,
            tool_name="skill",
            function_name="skill_invoke",
            function_args=function_args,
            status=ToolStatus.CALLED,
            function_result=result,
        )
        yield called_event

    # ── Agent selection (delegated to FlowStepExecutor) ──────────────

    async def _get_executor_for_step(self, step: Step) -> BaseAgent:
        """Select the appropriate executor for a step (delegated to FlowStepExecutor)."""
        return await self._flow_step_executor.get_executor_for_step(step)

    def _background_compact_memory(self, force: bool = False, reason: str = "") -> None:
        """Schedule memory compaction as a non-blocking background task with debouncing.

        Uses Phase 3 proactive compaction triggers to determine if compaction
        is needed before actually performing it. Debouncing prevents excessive
        compaction calls that could contend for event loop resources.

        Args:
            force: Force compaction regardless of trigger rules and debounce
            reason: Reason for forced compaction (logged)
        """
        # Debounce check (skip if compacted recently, unless forced)
        now = datetime.now(UTC)
        if not force and self._last_compact_time:
            elapsed = (now - self._last_compact_time).total_seconds()
            if elapsed < self._compact_debounce_seconds:
                logger.debug(
                    f"Skipping compaction, last was {elapsed:.1f}s ago (debounce: {self._compact_debounce_seconds}s)"
                )
                return

        self._last_compact_time = now

        async def _compact():
            try:
                # Estimate current tokens from executor memory
                await self.executor._ensure_memory()
                current_tokens = self.executor.memory.estimate_tokens()

                # Track token usage for growth rate analysis
                self._memory_manager.track_token_usage(current_tokens)

                # Get pressure status
                pressure = self._memory_manager.get_pressure_status(current_tokens)

                # Check if compaction should be triggered
                should_compact, trigger_reason = self._memory_manager.should_trigger_compaction(
                    pressure=pressure, recent_tools=self._recent_tools, iteration_count=self._iteration_count
                )

                if force or should_compact:
                    compact_reason = reason if force else trigger_reason
                    logger.info(
                        f"Agent {self._agent_id} triggering memory compaction: {compact_reason} "
                        f"(tokens: {current_tokens}, pressure: {pressure.level.value})"
                    )

                    messages = self.executor.memory.get_messages()
                    flags = self._resolve_feature_flags()

                    if flags.get("context_optimization"):
                        optimized_messages, report = self._memory_manager.optimize_context(
                            messages,
                            preserve_recent=10,
                            token_threshold=int(pressure.max_tokens * 0.65),
                        )
                        if report.tokens_saved > 0:
                            self.executor.memory.messages = optimized_messages
                            await self._repository.save_memory(self._agent_id, self.executor.name, self.executor.memory)
                            logger.info(
                                f"Agent {self._agent_id} context optimization saved {report.tokens_saved} tokens "
                                f"(semantic={report.semantic_compacted}, temporal={report.temporal_compacted})"
                            )
                            logger.debug(f"Agent {self._agent_id} background memory compact completed")
                            return

                    # Use smart compaction with result extraction
                    compacted_messages, tokens_saved = self._memory_manager.compact_messages_batch(
                        messages,
                        preserve_recent=10,
                        token_threshold=int(pressure.max_tokens * 0.7),  # Compact when at 70%
                    )

                    if tokens_saved > 0:
                        # Update memory with compacted messages
                        self.executor.memory.messages = compacted_messages
                        await self._repository.save_memory(self._agent_id, self.executor.name, self.executor.memory)
                        logger.info(f"Agent {self._agent_id} compaction saved {tokens_saved} tokens")
                    else:
                        # Fallback to simple compact if no savings from smart compaction
                        await self.executor.compact_memory()

                    logger.debug(f"Agent {self._agent_id} background memory compact completed")
                else:
                    logger.debug(
                        f"Agent {self._agent_id} skipping compaction "
                        f"(tokens: {current_tokens}, pressure: {pressure.level.value})"
                    )
            except Exception as e:
                logger.warning(f"Agent {self._agent_id} background memory compact failed: {e}")

        task = asyncio.create_task(_compact())
        self._track_background_task(task)

    def _track_tool_usage(self, tool_name: str) -> None:
        """Track recent tool usage for proactive compaction decisions."""
        self._recent_tools.append(tool_name)
        if len(self._recent_tools) > self._max_recent_tools:
            self._recent_tools = self._recent_tools[-self._max_recent_tools :]

    async def _save_progress_artifact(self) -> None:
        """Save current plan progress to sandbox for session bridging.

        Writes a structured status file so that if the context window is
        exhausted and a new session continues the task, it can load the
        progress state without re-discovering completed work.
        """
        if not self.plan or not self._sandbox:
            return
        try:
            import json

            completed_steps = []
            pending_steps = []
            for step in self.plan.steps:
                step_info = {
                    "id": str(step.id),
                    "description": step.description[:200],
                    "status": step.status.value if hasattr(step.status, "value") else str(step.status),
                }
                if step.status == ExecutionStatus.COMPLETED:
                    step_info["result"] = str(step.result)[:500] if step.result else None
                    completed_steps.append(step_info)
                else:
                    pending_steps.append(step_info)

            artifact = json.dumps(
                {
                    "plan_title": self.plan.title or "Untitled",
                    "total_steps": len(self.plan.steps),
                    "completed": completed_steps,
                    "pending": pending_steps,
                    "session_id": self._session_id,
                },
                indent=2,
            )

            await self._sandbox.file_write(
                file="/home/ubuntu/.agent_progress.json",
                content=artifact,
            )
            # Clear negative cache so _load_progress_artifact will find the file
            self._progress_file_confirmed_absent = False
            logger.debug(f"Saved progress artifact: {len(completed_steps)}/{len(self.plan.steps)} steps")
        except Exception as e:
            logger.debug(f"Failed to save progress artifact: {e}")

    async def _write_checkpoint(
        self,
        step_index: int,
        is_final: bool = False,
    ) -> None:
        """Write execution checkpoint to memory.

        Phase 5: Incremental checkpoints prevent context loss in long sessions
        by persisting progress as high-importance memories.

        Args:
            step_index: Current step index (0-based)
            is_final: Whether this is the final checkpoint
        """
        if not self._memory_service or not self._user_id or not self.plan:
            return

        try:
            from app.domain.models.long_term_memory import MemoryImportance, MemorySource, MemoryType

            # Summarize progress
            completed_steps = []
            for i, step in enumerate(self.plan.steps):
                if i <= step_index and step.status == ExecutionStatus.COMPLETED:
                    status_str = "✓ Success" if step.success else "✗ Failed"
                    result_preview = str(step.result)[:100] if step.result else "completed"
                    completed_steps.append(f"Step {i + 1}: {status_str} - {step.description[:80]} ({result_preview})")

            if not completed_steps:
                return

            summary = f"Execution checkpoint (steps 1-{step_index + 1}):\n"
            summary += "\n".join(completed_steps[-10:])  # Last 10 steps to keep checkpoint concise

            # Store as high-importance memory
            await self._memory_service.store_memory(
                user_id=self._user_id,
                content=summary,
                memory_type=MemoryType.PROJECT_CONTEXT,
                importance=MemoryImportance.CRITICAL if is_final else MemoryImportance.HIGH,
                source=MemorySource.SYSTEM,
                session_id=self._session_id,
                tags=["checkpoint", "execution", "final" if is_final else "incremental"],
                metadata={
                    "step_index": step_index,
                    "total_steps": len(self.plan.steps),
                    "is_final": is_final,
                    "plan_title": self.plan.title or "Untitled",
                    "checkpoint_timestamp": datetime.now(UTC).isoformat(),
                },
                generate_embedding=True,
            )

            logger.info(f"Checkpoint written at step {step_index + 1} ({'final' if is_final else 'incremental'})")
        except Exception as e:
            logger.warning(f"Failed to write checkpoint: {e}")

        # WP-6: Persist plan checkpoint to CheckpointManager for cross-restart recovery
        if self._checkpoint_manager and self.plan:
            try:
                _settings = get_settings()
                if _settings.feature_workflow_checkpointing:
                    await self._checkpoint_manager.save_plan_checkpoint(
                        session_id=self._session_id,
                        plan_id=self.plan.id,
                        completed_steps=[str(s.id) for s in self.plan.steps if s.status == ExecutionStatus.COMPLETED],
                        step_results={
                            str(s.id): str(s.result or "")[:500]
                            for s in self.plan.steps
                            if s.status == ExecutionStatus.COMPLETED and s.result
                        },
                        stage_index=step_index,
                        metadata={
                            "step_index": step_index,
                            "is_final": is_final,
                            "session_id": self._session_id,
                        },
                    )
            except Exception as _ckpt_err:
                logger.debug("WP-6 CheckpointManager write failed (non-critical): %s", _ckpt_err)

    def _apply_plan_checkpoint(self, checkpoint: Any) -> None:
        """Apply a WorkflowCheckpoint to the current plan, marking completed steps as done.

        WP-6: When a session resumes after an interruption, this method uses the
        persisted checkpoint to skip steps already completed in the prior run,
        complementing the existing StepEvent-based status restoration.

        Args:
            checkpoint: WorkflowCheckpoint with completed_steps and step_results
        """
        if not self.plan or not checkpoint or not checkpoint.completed_steps:
            return

        completed_set = set(checkpoint.completed_steps)
        restored = 0
        for step in self.plan.steps:
            step_id = str(step.id)
            if step_id in completed_set and step.status != ExecutionStatus.COMPLETED:
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                if step_id in (checkpoint.step_results or {}):
                    step.result = str(checkpoint.step_results[step_id])
                restored += 1

        if restored > 0:
            logger.info(
                "WP-6 checkpoint applied: %d/%d steps marked completed for session %s",
                restored,
                len(self.plan.steps),
                self._session_id,
            )

    async def _load_progress_artifact(self) -> dict | None:
        """Load previously saved progress artifact from sandbox.

        Uses a negative-result cache to avoid repeated network calls when
        the file doesn't exist yet (common before the agent writes its first
        checkpoint). The flag is reset when _save_progress_artifact succeeds.

        Returns:
            Progress dict if found, None otherwise
        """
        if not self._sandbox:
            return None

        # Skip the network call if a previous check already confirmed absence
        if getattr(self, "_progress_file_confirmed_absent", False):
            return None

        progress_path = "/home/ubuntu/.agent_progress.json"

        try:
            # Check existence first to avoid 404 log noise in the sandbox container
            exists_result = await self._sandbox.file_exists(progress_path)
            if not exists_result or not exists_result.success:
                self._progress_file_confirmed_absent = True
                return None
            # data can be dict or raw — handle both
            exists_data = exists_result.data
            if isinstance(exists_data, dict) and not exists_data.get("exists"):
                self._progress_file_confirmed_absent = True
                return None

            import json

            result = await self._sandbox.file_read(file=progress_path)
            if result and result.success and result.data:
                return json.loads(str(result.data))
        except Exception:
            logger.debug("Failed to read agent progress file", exc_info=True)
        return None

    def _assign_phases_to_plan(self) -> None:
        """Assign phases to plan steps (delegated to PhaseRouter)."""
        if self.plan:
            self._phase_router.assign_phases_to_plan(self.plan)

    def _transition_to(self, new_status: AgentStatus, *, force: bool = False, reason: str = "") -> None:
        """Transition to a new status with optional validation."""
        if self.status == new_status:
            return
        if not force and not validate_transition(self.status, new_status):
            message = f"Invalid transition from {self.status.value} to {new_status.value}"
            if reason:
                message = f"{message} ({reason})"
            logger.error(message)
            raise StateTransitionError(self.status, new_status, message)
        if force and not validate_transition(self.status, new_status):
            logger.warning(
                f"Forcing transition from {self.status.value} to {new_status.value}"
                f"{' (' + reason + ')' if reason else ''}"
            )
        old_status = self.status
        self.status = new_status

        # Emit structured flow transition event for observability
        now = time.time()
        elapsed_ms = (now - self._last_transition_time) * 1000
        self._last_transition_time = now
        current_step = self.plan.get_running_step() if self.plan else None
        self._pending_events.append(
            FlowTransitionEvent(
                from_state=old_status.value,
                to_state=new_status.value,
                reason=reason or None,
                step_id=current_step.id if current_step else None,
                elapsed_ms=round(elapsed_ms, 1),
            )
        )

        self._log.workflow_transition(
            from_state=old_status.value,
            to_state=new_status.value,
            reason=reason,
        )
        # Reset per-phase counters on successful forward transitions
        if new_status == AgentStatus.EXECUTING:
            self._plan_validation_failures = 0
            self._error_recovery.reset_cycle_counter()

        # Set phase-based tool filtering on agents to reduce hallucination
        if new_status == AgentStatus.PLANNING:
            self.planner._active_phase = "planning"
        elif new_status == AgentStatus.EXECUTING:
            self.executor._active_phase = None  # All tools for execution
        elif new_status == AgentStatus.VERIFYING:
            if self.verifier and hasattr(self.verifier, "_active_phase"):
                self.verifier._active_phase = "verifying"
        elif new_status == AgentStatus.SUMMARIZING:
            self.executor._active_phase = None  # All tools for summarization

        # Phase 2: Rebalance token budget at phase transitions
        self._rebalance_token_budget(old_status, new_status)

    def _initialize_token_budget(self) -> None:
        """Create a TokenBudget at flow start if the feature flag is enabled.

        Called once at the beginning of the run loop. Creates a budget and
        propagates it to the planner and executor agents.
        """
        flags = self._resolve_feature_flags()
        if not flags.get("token_budget_manager"):
            return

        try:
            from app.domain.services.agents.token_budget_manager import TokenBudgetManager

            budget_mgr = TokenBudgetManager(self.executor._token_manager)
            self._token_budget = budget_mgr.create_budget()

            # Propagate budget to all agents
            self.planner.set_token_budget(self._token_budget)
            self.executor.set_token_budget(self._token_budget)
            if self.verifier and hasattr(self.verifier, "set_token_budget"):
                self.verifier.set_token_budget(self._token_budget)

            logger.info(
                "Token budget initialized: %d effective tokens across %d phases",
                self._token_budget.effective_limit,
                len(self._token_budget.phases),
            )
        except Exception as e:
            logger.warning("Failed to initialize token budget (non-critical): %s", e)
            self._token_budget = None

    def _rebalance_token_budget(self, old_status: AgentStatus, new_status: AgentStatus) -> None:
        """Rebalance unused tokens from completed phase to next phase.

        Called inside _transition_to() on every phase change. No-op when
        the feature flag is disabled or no budget is set.
        """
        if self._token_budget is None:
            return

        try:
            from app.domain.services.agents.token_budget_manager import (
                BudgetPhase,
                TokenBudgetManager,
            )

            phase_map = {
                AgentStatus.PLANNING: BudgetPhase.PLANNING,
                AgentStatus.EXECUTING: BudgetPhase.EXECUTION,
                AgentStatus.SUMMARIZING: BudgetPhase.SUMMARIZATION,
            }

            completed_phase = phase_map.get(old_status)
            next_phase = phase_map.get(new_status)

            if completed_phase and next_phase and completed_phase != next_phase:
                budget_mgr = TokenBudgetManager(self.executor._token_manager)
                budget_mgr.rebalance(self._token_budget, completed_phase, next_phase)
                logger.debug(
                    "Token budget rebalanced: %s → %s (remaining: %d)",
                    completed_phase.value,
                    next_phase.value,
                    self._token_budget.total_remaining,
                )
        except Exception as e:
            logger.warning("Token budget rebalance failed (non-critical): %s", e)

    async def _generate_acknowledgment(self, user_message: str) -> str:
        """Generate an acknowledgment message before starting to plan."""
        return await self._ack_refiner.generate(user_message)

    def _validate_plan_before_execution(self) -> bool:
        """Validate plan before execution; returns True if safe to proceed."""
        if not self.plan:
            logger.warning("No plan available for validation")
            return False

        flags = self._resolve_feature_flags()
        if flags.get("plan_validation_v2"):
            tool_names = [
                t.get("function", {}).get("name", "")
                for t in (self.planner.get_available_tools() if self.planner else []) or []
            ]
            validation = PlanValidator(tool_names=tool_names).validate(self.plan)
        else:
            validation = self.plan.validate_plan()

        passed = validation.passed
        if not passed:
            error_summary = "; ".join(validation.errors[:3])
            logger.warning(f"Plan validation failed: {error_summary}")
            if hasattr(validation, "to_summary"):
                summary = validation.to_summary()
            else:
                summary = "\n- " + "\n- ".join(validation.errors[:5])
            if flags.get("plan_validation_v2") and flags.get("shadow_mode", True):
                return True
            self._verification_verdict = "revise"
            self._verification_feedback = "Plan validation failed:" + summary
            return False

        if validation.warnings:
            logger.info(f"Plan validation warnings: {', '.join(validation.warnings[:3])}")
        return True

    def _route_after_revision_needed(self) -> tuple[AgentStatus, str]:
        """Determine next status when verifier requests plan revision.

        The workflow should never execute an unrevised plan after a revision request.
        """
        if self._verification_loops < self._max_verification_loops:
            return AgentStatus.PLANNING, "verification requested plan revision"

        self._plan_validation_failures += 1
        if self._plan_validation_failures >= self._max_plan_validation_failures:
            return AgentStatus.SUMMARIZING, "max verification revisions reached without a valid plan"

        # Reset loop counter so a forced replan can complete one fresh verification cycle.
        self._verification_loops = 0
        return AgentStatus.PLANNING, "max verification loops reached; forcing replanning"

    def _run_compliance_gates(self, content: str, attachments: list[Any] | None = None) -> ComplianceReport:
        """Run compliance gates on final output content."""
        artifacts: list[dict[str, Any]] = []
        for attachment in attachments or []:
            path = getattr(attachment, "file_path", None) or getattr(attachment, "path", None)
            if path:
                artifacts.append({"path": path, "type": "file"})
        return self._compliance_gates.check_all(content, artifacts=artifacts, sources=[])

    def _evaluate_response_policy_for_message(
        self,
        message_text: str,
        *,
        verbosity_preference: str = "adaptive",
        quality_floor_enforced: bool = True,
    ) -> tuple[TaskAssessment, ResponsePolicy]:
        """Evaluate adaptive response policy for the current user message."""
        guardrail_result = self._input_guardrails.analyze(message_text)
        assessment = self._response_policy_engine.assess_task(
            task_description=message_text,
            complexity_score=self._cached_complexity,
            guardrail_result=guardrail_result,
        )
        policy = self._response_policy_engine.decide_policy(
            assessment=assessment,
            verbosity_preference=verbosity_preference,
            quality_floor_enforced=quality_floor_enforced,
        )

        self._task_assessment = assessment
        self._response_policy = policy
        self.executor.set_response_policy(policy)

        metrics = get_metrics()
        metrics.record_counter("response_policy_mode_total", labels={"mode": policy.mode.value})
        return assessment, policy

    def _should_pause_for_clarification(
        self,
        session_status: SessionStatus,
        assessment: TaskAssessment,
        clarification_policy: str = "auto",
    ) -> bool:
        """Determine whether we should ask for clarification and pause execution."""
        if session_status != SessionStatus.PENDING:
            return False
        return self._response_policy_engine.should_request_clarification(
            assessment, clarification_policy=clarification_policy
        )

    def _build_clarification_question(self, assessment: TaskAssessment) -> str:
        """Build the clarification question shown to the user."""
        return self._response_policy_engine.build_clarification_prompt(assessment)

    def _background_save_task_state(self, force: bool = False) -> None:
        """Schedule task state save as a non-blocking background task with debouncing.

        Args:
            force: Force save regardless of debounce timer
        """
        # Debounce check (skip if saved recently, unless forced)
        now = datetime.now(UTC)
        if not force and self._last_save_time:
            elapsed = (now - self._last_save_time).total_seconds()
            if elapsed < self._save_debounce_seconds:
                logger.debug(
                    f"Skipping task state save, last was {elapsed:.1f}s ago (debounce: {self._save_debounce_seconds}s)"
                )
                return

        self._last_save_time = now

        async def _save():
            try:
                await self._task_state_manager.save_to_sandbox()
                logger.debug(f"Agent {self._agent_id} task state saved to sandbox")
            except Exception as e:
                logger.warning(f"Agent {self._agent_id} task state save failed: {e}")

        task = asyncio.create_task(_save())
        self._track_background_task(task)

    # ── Step routing helpers (delegated to FlowStepExecutor) ──────────

    def _handle_step_failure(self, failed_step: Step) -> list[str]:
        """Handle step failure (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.handle_step_failure(self.plan, failed_step)

    def _should_skip_step(self, step: Step) -> tuple[bool, str]:
        """Check if step should be skipped (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.should_skip_step(self.plan, step)

    def _check_and_skip_steps(self) -> list[str]:
        """Check all pending steps for skipping (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.check_and_skip_steps(self.plan)

    def _is_read_only_step(self, step: Step) -> bool:
        """Check if step is read-only (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.is_read_only_step(step)

    def _is_research_or_complex_task(self, step: Step | None = None) -> bool:
        """Detect research/complex tasks (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.is_research_or_complex_task(self.plan, step, self._cached_complexity)

    def _should_skip_plan_update(self, step: Step, remaining_steps: int) -> tuple[bool, str]:
        """Determine if plan update should be skipped (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.should_skip_plan_update(
            step, remaining_steps, self.plan, self._cached_complexity
        )

    def _check_step_dependencies(self, step: Step) -> bool:
        """Check step dependencies (delegated to FlowStepExecutor)."""
        return self._flow_step_executor.check_step_dependencies(self.plan, step)

    @asynccontextmanager
    async def state_context(self, new_status: AgentStatus):
        """
        Context manager for state transitions with automatic error handling.

        Automatically transitions to ERROR state on exception and
        preserves previous status for recovery.

        Usage:
            async with self.state_context(AgentStatus.PLANNING):
                # Do planning work
                # Auto-transitions to ERROR on exception
        """
        old_status = self.status
        self._transition_to(new_status)

        # Enhanced logging with structured context
        logger.info(
            "Workflow state transition",
            extra={
                "session_id": self._session_id,
                "agent_id": self._agent_id,
                "from_state": old_status.value,
                "to_state": new_status.value,
                "iteration_count": getattr(self, "_iteration_count", 0),
            },
        )

        # Capture transition with observability span
        trace_ctx = getattr(self, "_trace_context", None)

        span_name = f"workflow:{new_status.value}"

        if trace_ctx:
            with trace_ctx.span(span_name, "plan_create") as span:
                span.set_attribute("workflow.from_state", old_status.value)
                span.set_attribute("workflow.to_state", new_status.value)
                span.set_attribute("workflow.session_id", self._session_id)
                span.set_attribute("workflow.agent_id", self._agent_id)

                try:
                    yield
                except Exception as e:
                    self._error_recovery.record_error(e, old_status)
                    self._transition_to(AgentStatus.ERROR, force=True, reason="state context error")

                    span.set_status("error", str(e))
                    logger.error(
                        f"Agent {self._agent_id} error in state {new_status}",
                        extra={
                            "session_id": self._session_id,
                            "from_state": old_status.value,
                            "to_state": new_status.value,
                            "error": str(e),
                        },
                    )
                    raise
        else:
            try:
                yield
            except Exception as e:
                self._error_recovery.record_error(e, old_status)
                self._transition_to(AgentStatus.ERROR, force=True, reason="state context error")
                logger.error(f"Agent {self._agent_id} error in state {new_status}: {e}")
                raise

    async def handle_error_state(self) -> bool:
        """Handle ERROR state with recovery attempts (delegated to ErrorRecoveryHandler).

        Returns:
            True if recovery successful and can continue, False otherwise.
        """
        # Build the optional recovery-prompt injection callback
        inject_fn = None
        if hasattr(self, "executor") and self.executor and hasattr(self.executor, "memory") and self.executor.memory:

            def _inject(prompt: str) -> None:
                self.executor.memory.add_message({"role": "system", "content": prompt})

            inject_fn = _inject

        return await self._error_recovery.attempt_recovery(
            current_flow_status=self.status,
            transition_fn=self._transition_to,
            inject_recovery_fn=inject_fn,
        )

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        tracer = get_tracer()
        settings = get_settings()

        # Create trace context for this run
        with tracer.trace(
            "agent-run",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]},
        ) as trace_ctx:
            try:
                await self._check_cancelled()
                # Wall-clock ceiling (default 1 hour) prevents runaway agents
                async with asyncio.timeout(settings.max_execution_time_seconds):
                    inner = self._run_with_trace(message, trace_ctx).__aiter__()
                    while True:
                        await self._check_cancelled()
                        try:
                            # Idle timeout (default 5 min) resets on every yielded event
                            async with asyncio.timeout(settings.workflow_idle_timeout_seconds):
                                event = await inner.__anext__()
                        except StopAsyncIteration:
                            break
                        except TimeoutError:
                            idle_mins = settings.workflow_idle_timeout_seconds // 60
                            logger.warning(
                                "Agent %s idle timeout after %ds for session %s",
                                self._agent_id,
                                settings.workflow_idle_timeout_seconds,
                                self._session_id,
                            )
                            yield ErrorEvent(
                                error=f"The agent hasn't produced output for {idle_mins} minutes and may be stuck.",
                                error_type="timeout",
                                recoverable=True,
                                can_resume=True,
                                error_code="workflow_idle_timeout",
                                retry_hint='Click "Continue" to resume the task from where it left off.',
                            )
                            yield DoneEvent()
                            return
                        yield event
            except asyncio.CancelledError:
                logger.info("Agent %s workflow cancelled for session %s", self._agent_id, self._session_id)
                raise
            except TimeoutError:
                wall_mins = settings.max_execution_time_seconds // 60
                logger.error(
                    "Agent %s wall-clock timeout after %ds for session %s",
                    self._agent_id,
                    settings.max_execution_time_seconds,
                    self._session_id,
                )
                yield ErrorEvent(
                    error=f"The task reached the {wall_mins}-minute time limit.",
                    error_type="timeout",
                    recoverable=True,
                    can_resume=True,
                    error_code="workflow_wall_clock_timeout",
                    retry_hint='Click "Continue" to pick up where the agent left off.',
                )
                yield DoneEvent()

    async def _run_with_trace(self, message: Message, trace_ctx) -> AsyncGenerator[BaseEvent, None]:
        """Internal run method with tracing."""
        await self._check_cancelled()

        # Phase 2: Initialize proactive token budget at flow start
        self._initialize_token_budget()

        # Emit research mode event so frontend can adapt layout (e.g., auto-open browser panel)
        yield ResearchModeEvent(research_mode=self._research_mode)

        # Step 2: Create structured output workspace for Deep Research
        if self._research_mode == "deep_research":
            workspace_base = f"/workspace/{self._session_id}"
            workspace_path = f"{workspace_base}/output"
            workspace_structure = {
                "reports": "Markdown reports, analysis documents",
                "charts": "Plotly charts (HTML/PNG), visualizations",
                "data": "CSV, JSON, raw extracted data",
                "code": "Scripts, code samples, notebooks",
            }
            subdirs = " ".join(f"{workspace_path}/{d}" for d in workspace_structure)
            mkdir_cmd = f"mkdir -p {subdirs}"
            try:
                result = await self._sandbox.exec_command(self._session_id, workspace_base, mkdir_cmd)
                if result.success:
                    self._workspace_output_path = workspace_path
                    logger.info("Deep Research workspace created: %s", workspace_path)

                    # Verify directories were actually created
                    verify_cmd = " && ".join(f"test -d {workspace_path}/{d}" for d in workspace_structure)
                    verify_result = await self._sandbox.exec_command(self._session_id, workspace_base, verify_cmd)
                    if not verify_result.success:
                        logger.warning("Workspace directory verification failed — some dirs may be missing")
                else:
                    logger.warning("Workspace mkdir failed, using fallback: %s", result.message)
                    self._workspace_output_path = workspace_base
                    workspace_structure = {}
            except Exception as e:
                logger.warning("Workspace creation failed, using fallback: %s", e)
                self._workspace_output_path = workspace_base
                workspace_structure = {}

            # Persist workspace path to session metadata for resilience
            try:
                session = await self._session_repository.find_by_id(self._session_id)
                if session:
                    ws = session.workspace_structure or {}
                    ws["_output_path"] = self._workspace_output_path
                    ws.update(workspace_structure)
                    await self._session_repository.update_by_id(self._session_id, {"workspace_structure": ws})
            except Exception as e:
                logger.debug("Workspace path persistence to session failed (non-critical): %s", e)

            # Notify frontend of workspace initialization
            yield WorkspaceEvent(
                action="initialized",
                workspace_type="research",
                workspace_path=self._workspace_output_path,
                structure=workspace_structure or None,
            )

            # Inject workspace-aware instructions into executor prompt
            from app.domain.services.prompts.execution import build_workspace_context

            self.executor.system_prompt += build_workspace_context(self._workspace_output_path)

        original_message = message.message
        settings = get_settings()

        # Phase 1: Extract RequestContract at ingress (before validation)
        if settings.enable_request_contract:
            self._request_contract = extract_request_contract(original_message)
            logger.debug(
                "RequestContract extracted: entities=%s, versions=%s",
                self._request_contract.locked_entities,
                self._request_contract.locked_versions,
            )

        locked_entities = self._request_contract.locked_entities if self._request_contract else None
        validated_message = self._prompt_quick_validator.validate(original_message, locked_entities=locked_entities)
        effective_message = message
        if validated_message != original_message:
            logger.info(
                "Prompt quick validation updated message for session %s: %s -> %s",
                self._session_id,
                original_message[:120],
                validated_message[:120],
            )
            effective_message = message.model_copy(deep=True)
            effective_message.message = validated_message

        # Keep original message immutable for traceability; process with the validated copy only.
        message = effective_message

        # TODO: move to task runner
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise SessionNotFoundException(self._session_id)
        await self._check_cancelled()

        # Phase 3.5: Initialize skill_invoke tool with available skills (lazy load)
        await self._init_skill_invoke_tool()
        await self._check_cancelled()

        # Cross-session learning: load historical error patterns
        if self._user_id and self._memory_service:
            try:
                await self._error_bridge.on_session_start(self._user_id, self._memory_service)
            except Exception as e:
                logger.debug(f"Error pattern loading failed (non-critical): {e}")

        # === INSTANT ACKNOWLEDGMENT: Emit before any processing ===
        # This gives users immediate feedback that their message was received
        if session.status not in (SessionStatus.WAITING, SessionStatus.RUNNING):
            # Emit text acknowledgment
            acknowledgment = await self._generate_acknowledgment(message.message)
            yield MessageEvent(message=acknowledgment)
            logger.info(f"Emitted acknowledgment for session {self._session_id}")

            # Emit analyzing progress event
            yield ProgressEvent(
                phase=PlanningPhase.ANALYZING,
                message="Analyzing your request...",
                progress_percent=15,
            )

        # === ANCHOR CONTEXT: Inject referenced event context for follow-ups ===
        if message.follow_up_anchor_event_id and self._session_repository:
            try:
                anchor_event = await self._session_repository.get_event_by_id(
                    self._session_id, message.follow_up_anchor_event_id
                )
                if anchor_event:
                    anchor_text = ""
                    if isinstance(anchor_event, dict):
                        etype = anchor_event.get("type", "")
                        if etype == "report":
                            title = anchor_event.get("title", "")
                            content = anchor_event.get("content", "")
                            anchor_text = f"{title}: {content}"[:500]
                        elif etype == "message":
                            anchor_text = (anchor_event.get("message", ""))[:500]
                        else:
                            anchor_text = str(anchor_event)[:500]
                    else:
                        if hasattr(anchor_event, "title") and hasattr(anchor_event, "content"):
                            anchor_text = f"{anchor_event.title}: {anchor_event.content}"[:500]
                        elif hasattr(anchor_event, "message"):
                            anchor_text = anchor_event.message[:500]
                    if anchor_text:
                        context_prefix = f"[Context from previous result: {anchor_text}]\n\n"
                        message = message.model_copy(deep=True)
                        message.message = context_prefix + message.message
                        logger.info(
                            "Injected anchor context (%d chars) for session %s",
                            len(anchor_text),
                            self._session_id,
                        )
                else:
                    logger.warning(
                        "Anchor event %s not found for session %s",
                        message.follow_up_anchor_event_id,
                        self._session_id,
                    )
            except Exception:
                logger.warning("Failed to retrieve anchor event", exc_info=True)

        # === FAST PATH: Check if this is a simple query that can skip planning ===
        # Always classify messages to detect greetings/simple queries
        # Greetings and knowledge queries work regardless of session status
        # Browser/search intents are intentionally routed through full workflow
        # to ensure the agent performs full browsing/page traversal.
        logger.info(f"Fast path check: session.status={session.status}, message={message.message[:50]}")

        try:
            await self._check_cancelled()
            fast_path_router = FastPathRouter(
                browser=self._browser,
                llm=self._llm,
                search_engine=self._search_engine,
            )
            intent, params = fast_path_router.classify(message.message)
            logger.info(f"Fast path classification: intent={intent.value}, params={params}")

            # Determine if fast path can be used based on intent
            use_fast_path = False
            skip_reason = ""
            has_recent_assistant_reply = any(
                isinstance(event, MessageEvent) and event.role == "assistant" and bool((event.message or "").strip())
                for event in reversed(session.events or [])
            )
            is_suggestion_follow_up = should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply)

            if is_suggestion_follow_up:
                # Log which detection method was used for observability
                detection_method = (
                    "metadata (follow_up_source='suggestion_click')"
                    if message.follow_up_source == "suggestion_click"
                    else "regex pattern match"
                )
                skip_reason = (
                    f"suggestion follow-up detected via {detection_method}, requires contextual session history"
                )
                logger.info(f"Skipping fast path: {skip_reason}")
            elif intent == QueryIntent.GREETING:
                # Greetings don't need browser or tools - always use fast path, even during init
                use_fast_path = True
            elif intent == QueryIntent.KNOWLEDGE:
                # Knowledge queries don't need browser - always safe, even during init
                use_fast_path = True
            elif intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH):
                # Policy: always use full workflow for browse/search so the agent
                # can run search->open->multi-page browsing steps when needed.
                skip_reason = f"{intent.value} uses full workflow by policy"
            else:
                skip_reason = "TASK intent requires full workflow"

            if use_fast_path:
                logger.info(f"Fast path activated for {intent.value} query: {message.message[:50]}...")

                # Update session status
                await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)

                # Execute fast path and yield all events.
                # For non-GREETING intents, inject a TitleEvent immediately before DoneEvent
                # so the sidebar title is populated (fast paths skip the planner that normally
                # generates TitleEvent).
                async for event in fast_path_router.execute(intent, params, message):
                    if isinstance(event, DoneEvent) and intent != QueryIntent.GREETING:
                        raw = (message.message or "").strip()
                        fast_title = raw[:60].rstrip() + ("…" if len(raw) > 60 else "")
                        yield TitleEvent(title=fast_title)
                    yield event

                # For GREETING, keep session PENDING (waiting for actual task)
                # For other fast paths (currently KNOWLEDGE), mark as COMPLETED
                if intent == QueryIntent.GREETING:
                    await self._session_repository.update_status(self._session_id, SessionStatus.PENDING)
                    logger.info(f"Greeting fast path completed, session {self._session_id} waiting for task")
                else:
                    await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
                    logger.info(f"Fast path completed for session {self._session_id}")

                return  # Exit early - don't proceed with full workflow
            elif intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH) and skip_reason:
                logger.info(f"Fast path skipped for {intent.value} - {skip_reason}, using normal workflow")
            elif skip_reason:
                logger.debug(f"Fast path skipped: {skip_reason}")
        except Exception as e:
            logger.exception(f"Fast path analysis failed: {e}")
            yield ErrorEvent(error=f"Failed to analyze request: {str(e)[:200]}")
            # Continue with normal workflow instead of failing completely

        # === END FAST PATH ===

        # Assess task complexity and set dynamic iteration limits (Phase 3)
        await self._check_cancelled()
        if session.complexity_score is None and session.status == SessionStatus.PENDING:
            assessor = ComplexityAssessor()
            assessment = assessor.assess_task_complexity(
                task_description=message.message, is_multi_task=session.multi_task_challenge is not None
            )

            # Store complexity score and iteration limit in session
            session.complexity_score = assessment.score
            session.iteration_limit_override = assessment.recommended_iterations

            # Cache complexity for skip-update optimization
            self._cached_complexity = assessment.score

            # Apply iteration limit to executor
            self.executor.max_iterations = assessment.recommended_iterations

            logger.info(
                f"Task complexity: {assessment.category} ({assessment.score:.2f}), "
                f"setting iteration limit to {assessment.recommended_iterations}"
            )

            # Update session with complexity info
            await self._session_repository.update_by_id(
                self._session_id,
                {"complexity_score": assessment.score, "iteration_limit_override": assessment.recommended_iterations},
            )
        elif session.iteration_limit_override:
            # Reuse existing iteration limit override
            self.executor.max_iterations = session.iteration_limit_override
            # Cache existing complexity score
            if session.complexity_score is not None:
                self._cached_complexity = session.complexity_score
            logger.debug(f"Applying existing iteration limit: {session.iteration_limit_override}")

        # Load user settings for adaptive verbosity and clarification policy
        verbosity_preference = "adaptive"
        clarification_policy = "auto"
        quality_floor_enforced = True
        if self._user_id:
            try:
                settings_service_module = importlib.import_module("app.application.services.settings_service")
                user_settings = await settings_service_module.get_settings_service().get_user_settings(self._user_id)
                verbosity_preference = user_settings.get("response_verbosity_preference", "adaptive")
                clarification_policy = user_settings.get("clarification_policy", "auto")
                quality_floor_enforced = user_settings.get("quality_floor_enforced", True)
            except Exception as e:
                logger.debug("Could not load user settings for response policy: %s", e)

        task_assessment, response_policy = self._evaluate_response_policy_for_message(
            message.message,
            verbosity_preference=verbosity_preference,
            quality_floor_enforced=quality_floor_enforced,
        )
        flags = self._resolve_feature_flags()
        shadow_mode = flags.get("adaptive_verbosity_shadow", False)

        logger.info(
            "Response policy: mode=%s complexity=%.2f risk=%.2f ambiguity=%.2f confidence=%.2f shadow=%s",
            response_policy.mode.value,
            task_assessment.complexity_score,
            task_assessment.risk_score,
            task_assessment.ambiguity_score,
            task_assessment.confidence_score,
            shadow_mode,
        )

        would_pause = self._should_pause_for_clarification(session.status, task_assessment, clarification_policy)
        if shadow_mode and would_pause:
            logger.info(
                "Shadow mode: would have requested clarification (ambiguity=%.2f confidence=%.2f), proceeding with standard output",
                task_assessment.ambiguity_score,
                task_assessment.confidence_score,
            )
            response_policy = ResponsePolicy(
                mode=VerbosityMode.STANDARD,
                min_required_sections=["final result"],
                allow_compression=False,
            )
            self._response_policy = response_policy
            self.executor.set_response_policy(response_policy)
            would_pause = False

        if would_pause:
            get_metrics().record_counter("clarification_requested_total", labels={"reason": "ambiguous_request"})
            clarification_question = self._build_clarification_question(task_assessment)
            logger.info("Pausing for clarification before execution")
            yield ConfidenceEvent(
                decision="clarification_requested",
                confidence=task_assessment.confidence_score,
                level="low" if task_assessment.confidence_score < 0.5 else "medium",
                action_recommendation="ask_user",
                supporting_factors=[],
                risk_factors=[
                    f"ambiguity_score={task_assessment.ambiguity_score:.2f}",
                    *task_assessment.clarification_questions[:1],
                ],
            )
            yield MessageEvent(message=clarification_question)
            yield WaitEvent(wait_reason="user_input", suggest_user_takeover="none")
            return

        if shadow_mode:
            response_policy = ResponsePolicy(
                mode=VerbosityMode.STANDARD,
                min_required_sections=response_policy.min_required_sections,
                allow_compression=False,
            )
            self._response_policy = response_policy
            self.executor.set_response_policy(response_policy)

        if session.status != SessionStatus.PENDING:
            logger.debug(f"Session {self._session_id} is not in PENDING status, rolling back")
            await self.executor.roll_back(message)
            await self.planner.roll_back(message)

        if session.status == SessionStatus.RUNNING:
            logger.debug(f"Session {self._session_id} is in RUNNING status")
            self._transition_to(AgentStatus.PLANNING)

        if session.status == SessionStatus.WAITING:
            logger.debug(f"Session {self._session_id} is in WAITING status")
            get_metrics().record_counter("clarification_resolved_total", labels={"source": "user_reply"})
            if session.updated_at:
                updated = (
                    session.updated_at.replace(tzinfo=UTC) if session.updated_at.tzinfo is None else session.updated_at
                )
                wait_seconds = (datetime.now(UTC) - updated).total_seconds()
                if wait_seconds > 0:
                    get_metrics().record_histogram("clarification_wait_seconds", value=wait_seconds)
            self._transition_to(AgentStatus.EXECUTING, force=True, reason="resume waiting session")

        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)
        self.plan = session.get_last_plan()

        # Restore step statuses from StepEvents when resuming with an existing plan
        if self.plan and self.plan.steps:
            # Map StepStatus to ExecutionStatus
            step_status_map = {
                StepStatus.COMPLETED: ExecutionStatus.COMPLETED,
                StepStatus.FAILED: ExecutionStatus.FAILED,
                StepStatus.RUNNING: ExecutionStatus.RUNNING,
                StepStatus.STARTED: ExecutionStatus.RUNNING,
            }
            # Find the latest status for each step from StepEvents
            step_statuses: dict[str, ExecutionStatus] = {}
            for event in session.events:
                if isinstance(event, StepEvent) and event.step:
                    step_id = str(event.step.id)
                    if event.status in step_status_map:
                        step_statuses[step_id] = step_status_map[event.status]

            # Apply restored statuses to plan steps
            for step in self.plan.steps:
                step_id = str(step.id)
                if step_id in step_statuses:
                    step.status = step_statuses[step_id]
                    logger.debug(f"Restored step {step_id} status to {step.status}")

            # WP-6: Augment with CheckpointManager data for steps missed by StepEvent restoration
            if self._checkpoint_manager and settings.feature_workflow_checkpointing:
                try:
                    _ckpt_wf_id = await self._checkpoint_manager.has_resumable_checkpoint(self._session_id)
                    if _ckpt_wf_id:
                        _ckpt = await self._checkpoint_manager.load_checkpoint(_ckpt_wf_id, self._session_id)
                        if _ckpt:
                            self._apply_plan_checkpoint(_ckpt)
                except Exception as _ckpt_err:
                    logger.debug("WP-6 checkpoint restoration failed (non-critical): %s", _ckpt_err)

        # Reinitialize TaskStateManager when resuming with an existing plan
        if self.plan and self.plan.steps:
            # Get the original objective from the first user message event
            original_objective = ""
            for event in session.events:
                if hasattr(event, "role") and event.role == "user" and hasattr(event, "message"):
                    original_objective = event.message or ""
                    break

            self._task_state_manager.initialize_from_plan(
                objective=original_objective or message.message,
                steps=[{"id": s.id, "description": s.description} for s in self.plan.steps],
            )
            logger.info(f"TaskStateManager initialized with {len(self.plan.steps)} steps for resumed session")

        # Session bridging: load prior progress artifact if resuming
        if not self.plan:
            prior_progress = await self._load_progress_artifact()
            if prior_progress:
                logger.info(
                    f"Loaded progress artifact: {len(prior_progress.get('completed', []))}/"
                    f"{prior_progress.get('total_steps', 0)} steps completed from prior session"
                )

        logger.info(f"Agent {self._agent_id} started processing message: {message.message[:50]}...")

        # NOTE: Acknowledgment moved earlier (before fast path) for instant feedback

        # Skill-creator command tool events are now handled by the command registry
        # in agent_domain_service.py — the "skill-creator" skill's system_prompt_addition
        # is injected via the normal skill context pipeline (execution.py/planner.py).

        # === THINKING MODE: propagate user model-tier override to executor ===
        # 'fast' -> FAST tier, 'deep_think' -> POWERFUL tier, None/'auto' -> complexity-based auto
        if message.thinking_mode and message.thinking_mode != "auto":
            self.executor.set_thinking_mode(message.thinking_mode)
            logger.info(
                "Thinking mode override applied for session %s: %s",
                self._session_id,
                message.thinking_mode,
            )
        else:
            self.executor.set_thinking_mode(None)  # Reset to auto

        # WP-5: Inject distributed trace context into executor/planner so that
        # invoke_tool() can create per-tool child spans for observability.
        if settings.feature_tool_tracing:
            self.executor._trace_ctx = trace_ctx
            self.planner._trace_ctx = trace_ctx

        step = None
        while True:
            await self._check_cancelled()
            # Phase 3: Track iteration count for proactive compaction
            self._iteration_count += 1

            # Workflow loop safety: prevent infinite state transitions
            if self._iteration_count > self._max_workflow_transitions:
                logger.error(
                    f"Agent {self._agent_id} exceeded max workflow transitions "
                    f"({self._max_workflow_transitions}), forcing summarization"
                )
                self._transition_to(AgentStatus.SUMMARIZING, force=True, reason="max transitions exceeded")

            try:
                # Handle error state with recovery
                if self.status == AgentStatus.ERROR:
                    if await self.handle_error_state():
                        logger.info(f"Agent {self._agent_id} recovered from error state")
                        continue
                    else:
                        # Cannot recover, yield error and exit
                        _ec = self._error_recovery.error_context
                        error_msg = _ec.message if _ec else "Unknown error"
                        error_type = _ec.error_type.value if _ec else "unknown"
                        yield ErrorEvent(
                            error=f"Agent failed after recovery attempts: {error_msg}",
                            error_type=error_type,
                            recoverable=False,
                        )
                        break

                if self.status == AgentStatus.IDLE:
                    logger.info(
                        f"Agent {self._agent_id} state changed from {AgentStatus.IDLE} to {AgentStatus.PLANNING}"
                    )
                    self._transition_to(AgentStatus.PLANNING)
                elif self.status == AgentStatus.PLANNING:
                    # Create plan with tracing
                    await self._check_cancelled()
                    logger.info(f"Agent {self._agent_id} started creating plan")
                    with trace_ctx.span("planning", "plan_create") as plan_span:
                        # Pass replan context if we're replanning after verification
                        replan_context = self._verification_feedback if self._verification_verdict == "revise" else None

                        # Inject cross-session memory context (Phase 4: Role-Scoped Memory)
                        # Phase 3: Enhanced with similar task context
                        if "planner" in self._scoped_memory:
                            try:
                                memory_context_parts = []

                                # Phase 3: Add similar tasks from past sessions
                                if self._memory_service and self._user_id:
                                    try:
                                        similar_tasks = await self._memory_service.find_similar_tasks(
                                            user_id=self._user_id,
                                            task_description=message.message,
                                            limit=5,
                                        )
                                        if similar_tasks:
                                            task_lines = ["## Past Experience"]
                                            for task in similar_tasks:
                                                outcome = "succeeded" if task.get("success") else "failed"
                                                summary = task.get("content_summary", "")[:200]
                                                task_lines.append(f"- {summary} ({outcome})")
                                            memory_context_parts.append("\n".join(task_lines))
                                            logger.debug(
                                                f"Injected {len(similar_tasks)} similar tasks into planning context"
                                            )
                                    except Exception as e:
                                        logger.debug(f"Similar task retrieval failed: {e}")

                                # Original role-scoped memory
                                role_memory = await self._scoped_memory["planner"].get_context(message.message)
                                if role_memory:
                                    memory_context_parts.append(role_memory)

                                # Combine all memory contexts
                                if memory_context_parts:
                                    memory_context = "\n\n".join(memory_context_parts)
                                    if replan_context:
                                        replan_context = f"{memory_context}\n\n{replan_context}"
                                    else:
                                        replan_context = memory_context
                                    logger.debug(
                                        "Injected role-scoped planner memory (%d chars)",
                                        len(memory_context),
                                    )
                            except Exception as e:
                                logger.debug("Role-scoped memory injection skipped: %s", e)

                        # Phase 3: Meta-cognition knowledge boundary assessment
                        if settings.feature_meta_cognition_enabled:
                            try:
                                from app.domain.services.agents.reasoning.meta_cognition import (
                                    get_meta_cognition,
                                )

                                # Collect tool schemas for awareness
                                _meta_tool_schemas: list[dict[str, Any]] = []
                                for _t in getattr(self.executor, "tools", []):
                                    with suppress(Exception):
                                        _meta_tool_schemas.extend(_t.get_tools())

                                meta = get_meta_cognition(tools=_meta_tool_schemas)
                                assessment = meta.assess_knowledge_boundaries(
                                    task=message.message,
                                    context={"session_id": self._session_id},
                                )
                                if assessment.blocking_gaps:
                                    _gap_lines = "\n".join(f"- {g.description}" for g in assessment.blocking_gaps)
                                    _gap_suffix = f"\n\n## Known Knowledge Gaps\n{_gap_lines}"
                                    replan_context = f"{replan_context}{_gap_suffix}" if replan_context else _gap_suffix
                                    logger.debug(
                                        "Meta-cognition: injected %d knowledge gaps into planning context",
                                        len(assessment.blocking_gaps),
                                    )
                            except Exception as _meta_plan_err:
                                logger.debug(
                                    "Meta-cognition planning injection skipped (non-critical): %s",
                                    _meta_plan_err,
                                )

                        # PR-7: Resolve prompt profile patches (shadow/active mode)
                        from app.domain.models.prompt_profile import PromptTarget as _PromptTarget

                        # Resolve SYSTEM patch early and apply to both planner and executor
                        _system_patch = await self._resolve_profile_patch(_PromptTarget.SYSTEM)
                        if _system_patch:
                            self.planner.system_prompt += (
                                f"\n<!-- profile_patch target=system -->\n{_system_patch}\n<!-- /profile_patch -->\n"
                            )
                            self.executor.system_prompt += (
                                f"\n<!-- profile_patch target=system -->\n{_system_patch}\n<!-- /profile_patch -->\n"
                            )

                        _planner_patch = await self._resolve_profile_patch(_PromptTarget.PLANNER)

                        # Phase 4: Prompt variant selection via Thompson-sampling bandit
                        if settings.feature_prompt_profile_runtime:
                            try:
                                from app.domain.services.agents.learning.prompt_optimizer import (
                                    get_prompt_optimizer,
                                )

                                _optimizer = get_prompt_optimizer()
                                # Lazily seed bandit with auto-generated planner variants
                                _optimizer.auto_generate_variants(
                                    category="planner",
                                    base_prompt=self.planner.system_prompt,
                                    num_variants=3,
                                )
                                # Bootstrap phase: allow selection with 0 trials so the bandit
                                # can accumulate outcomes before enforcing MIN_TRIALS filter.
                                _best_variant = _optimizer.get_best_variant("planner", min_trials=0)
                                if _best_variant and _best_variant.prompt_template:
                                    self.planner.system_prompt = _best_variant.prompt_template
                                    # Track which variant was applied so record_outcome() can
                                    # close the feedback loop at COMPLETED/ERROR state.
                                    self._selected_prompt_variant_id = _best_variant.variant_id
                                    self._planning_start_time = time.time()
                                    logger.debug(
                                        "Phase 4: Applied prompt variant '%s' for planner (success_rate=%.2f, trials=%d)",
                                        _best_variant.variant_id,
                                        _best_variant.success_rate,
                                        _best_variant.total_trials,
                                    )
                            except Exception as _var_err:
                                logger.debug("Prompt variant selection skipped (non-critical): %s", _var_err)

                        # Deep Research: inject browser-first emphasis + workspace instructions
                        _saved_planner_prompt = self.planner.system_prompt
                        if self._research_mode == "deep_research":
                            wp = self._workspace_output_path or f"/workspace/{self._session_id}/output"
                            self.planner.system_prompt += (
                                "\n\n## Research Strategy: Browser-First Deep Research\n"
                                "You are a researcher agent. Your PRIMARY instrument is the web browser. "
                                "Always prefer browser_navigate and browser_agent_extract over simple API searches. "
                                "Browse multiple authoritative sources, extract content directly from web pages, "
                                "and verify information visually. Use info_search_web only for initial discovery, "
                                "then follow up with browser-based deep reading of the most relevant results.\n\n"
                                "## Workspace & Deliverables\n"
                                f"All deliverable files MUST be saved to: `{wp}/`\n"
                                "Directory structure:\n"
                                f"- `{wp}/reports/` — Markdown reports, analysis documents\n"
                                f"- `{wp}/charts/` — Plotly charts (HTML), visualizations, images\n"
                                f"- `{wp}/data/` — CSV, JSON, raw extracted data\n"
                                f"- `{wp}/code/` — Scripts, code samples, notebooks\n\n"
                                "Your FINAL step must compile and deliver all workspace files to the user."
                            )

                        async for event in self.planner.create_plan(
                            message,
                            replan_context=replan_context,
                            profile_patch_text=_planner_patch,
                        ):
                            await self._check_cancelled()
                            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                                self.plan = event.plan

                                # Propagate pre-planning search context to execution agent
                                if hasattr(self.planner, "_last_search_context") and self.planner._last_search_context:
                                    self.executor._pre_planning_search_context = self.planner._last_search_context
                                    logger.info("Propagated pre-planning search context to execution agent")

                                # Infer smart dependencies for BLOCKED cascade and parallel execution
                                self.plan.infer_smart_dependencies(use_sequential_fallback=True)

                                # Build and assign phases based on complexity
                                self._assign_phases_to_plan()

                                plan_span.set_attribute("plan.steps", len(event.plan.steps))
                                plan_span.set_attribute("plan.title", event.plan.title)
                                plan_span.set_attribute("plan.phases", len(self.plan.phases))
                                logger.info(
                                    f"Agent {self._agent_id} created plan successfully with {len(event.plan.steps)} steps"
                                )

                                # Initialize task state for recitation
                                self._task_state_manager.initialize_from_plan(
                                    objective=message.message,
                                    steps=[{"id": s.id, "description": s.description} for s in event.plan.steps],
                                )

                                yield TitleEvent(title=event.plan.title)
                                # Skip plan.message - execute silently without explaining
                            yield event

                        # Restore planner prompt after deep research injection
                        self.planner.system_prompt = _saved_planner_prompt

                    # Validate plan before proceeding
                    if not self._validate_plan_before_execution():
                        self._plan_validation_failures += 1
                        if self._plan_validation_failures >= self._max_plan_validation_failures:
                            logger.error(
                                f"Agent {self._agent_id} plan validation failed {self._plan_validation_failures} times, "
                                "forcing summarization"
                            )
                            self._transition_to(
                                AgentStatus.SUMMARIZING, force=True, reason="repeated plan validation failures"
                            )
                            continue
                        logger.info(
                            f"Agent {self._agent_id} replanning due to validation errors "
                            f"({self._plan_validation_failures}/{self._max_plan_validation_failures})"
                        )
                        continue

                    # Reset verification feedback after replanning
                    self._verification_verdict = None
                    self._verification_feedback = None

                    if not self.plan or len(self.plan.steps) == 0:
                        logger.info(f"Agent {self._agent_id} created plan successfully with no steps")
                        self._transition_to(AgentStatus.COMPLETED)
                    elif self.verifier:
                        # Transition to verification if verifier is enabled
                        logger.info(
                            f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.VERIFYING}"
                        )
                        self._transition_to(AgentStatus.VERIFYING)
                    else:
                        logger.info(
                            f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.EXECUTING}"
                        )
                        self._transition_to(AgentStatus.EXECUTING)

                elif self.status == AgentStatus.VERIFYING:
                    # Verify plan before execution (Phase 1: Plan-Verify-Execute)
                    await self._check_cancelled()
                    logger.info(f"Agent {self._agent_id} started verifying plan")
                    with trace_ctx.span("verifying", "agent_step") as verify_span:
                        async for event in self.verifier.verify_plan(
                            plan=self.plan, user_request=message.message, task_context=""
                        ):
                            await self._check_cancelled()
                            yield event

                            # Capture verification result
                            if isinstance(event, VerificationEvent):
                                if event.status == VerificationStatus.PASSED:
                                    self._verification_verdict = "pass"
                                    verify_span.set_attribute("verification.verdict", "pass")
                                elif event.status == VerificationStatus.REVISION_NEEDED:
                                    self._verification_verdict = "revise"
                                    self._verification_feedback = event.revision_feedback
                                    self._verification_loops += 1
                                    verify_span.set_attribute("verification.verdict", "revise")
                                elif event.status == VerificationStatus.FAILED:
                                    self._verification_verdict = "fail"
                                    verify_span.set_attribute("verification.verdict", "fail")

                    # Route based on verification verdict
                    if self._verification_verdict == "pass":
                        logger.info(f"Agent {self._agent_id} plan verified, proceeding to execution")
                        if not self._validate_plan_before_execution():
                            self._plan_validation_failures += 1
                            if self._plan_validation_failures >= self._max_plan_validation_failures:
                                logger.error(f"Agent {self._agent_id} repeated validation failures, summarizing")
                                self._transition_to(
                                    AgentStatus.SUMMARIZING, force=True, reason="repeated validation failures"
                                )
                            else:
                                logger.info(f"Agent {self._agent_id} plan failed validation after verification")
                                self._transition_to(AgentStatus.PLANNING)
                        else:
                            self._transition_to(AgentStatus.EXECUTING)
                    elif self._verification_verdict == "revise":
                        next_status, transition_reason = self._route_after_revision_needed()
                        if next_status == AgentStatus.SUMMARIZING:
                            logger.warning(
                                f"Agent {self._agent_id} max verification revisions reached, summarizing "
                                "instead of executing unrevised plan"
                            )
                            self._transition_to(AgentStatus.SUMMARIZING, force=True, reason=transition_reason)
                        elif "forcing replanning" in transition_reason:
                            logger.warning(
                                f"Agent {self._agent_id} max verification loops reached, forcing replanning "
                                f"({self._plan_validation_failures}/{self._max_plan_validation_failures})"
                            )
                            self._transition_to(AgentStatus.PLANNING, reason=transition_reason)
                        else:
                            logger.info(f"Agent {self._agent_id} plan needs revision, returning to planning")
                            self._transition_to(AgentStatus.PLANNING, reason=transition_reason)
                    elif self._verification_verdict == "fail":
                        logger.info(f"Agent {self._agent_id} plan verification failed, summarizing")
                        self._transition_to(AgentStatus.SUMMARIZING)
                    else:
                        # Default: proceed with execution
                        if not self._validate_plan_before_execution():
                            self._plan_validation_failures += 1
                            if self._plan_validation_failures >= self._max_plan_validation_failures:
                                logger.error(f"Agent {self._agent_id} repeated validation failures, summarizing")
                                self._transition_to(
                                    AgentStatus.SUMMARIZING, force=True, reason="repeated validation failures"
                                )
                            else:
                                logger.info(f"Agent {self._agent_id} plan failed validation after verification")
                                self._transition_to(AgentStatus.PLANNING)
                        else:
                            self._transition_to(AgentStatus.EXECUTING)

                elif self.status == AgentStatus.EXECUTING:
                    # Execute plan
                    await self._check_cancelled()
                    if not self._validate_plan_before_execution():
                        self._plan_validation_failures += 1
                        if self._plan_validation_failures >= self._max_plan_validation_failures:
                            logger.error(f"Agent {self._agent_id} repeated validation failures, summarizing")
                            self._transition_to(
                                AgentStatus.SUMMARIZING, force=True, reason="repeated validation failures"
                            )
                        else:
                            logger.info(
                                f"Agent {self._agent_id} plan failed validation before execution "
                                f"({self._plan_validation_failures}/{self._max_plan_validation_failures})"
                            )
                            self._transition_to(AgentStatus.PLANNING, force=True, reason="plan validation failed")
                        continue

                    self.plan.status = ExecutionStatus.RUNNING
                    step = self.plan.get_next_step()
                    if not step:
                        # Before transitioning to SUMMARIZING, try to unblock steps
                        if self.plan.has_blocked_steps():
                            unblocked = self.plan.unblock_independent_steps()
                            if unblocked:
                                logger.info(
                                    f"Agent {self._agent_id} unblocked {len(unblocked)} steps "
                                    f"with partial results: {unblocked}"
                                )
                                continue
                            # Still blocked — log which steps are stuck
                            blocked = self.plan.get_blocked_steps()
                            logger.warning(
                                f"Agent {self._agent_id} has {len(blocked)} blocked steps "
                                f"that cannot be unblocked: "
                                f"{[s.description[:60] for s in blocked]}"
                            )
                        logger.info(
                            f"Agent {self._agent_id} has no more steps, state changed from {AgentStatus.EXECUTING} to {AgentStatus.COMPLETED}"
                        )
                        # Phase 5: Write final checkpoint before summarizing
                        if self._steps_completed_count > 0:
                            last_completed_index = next(
                                (
                                    len(self.plan.steps) - 1 - i
                                    for i, s in enumerate(reversed(self.plan.steps))
                                    if s.status == ExecutionStatus.COMPLETED
                                ),
                                -1,
                            )
                            if last_completed_index >= 0:
                                await self._write_checkpoint(last_completed_index, is_final=True)

                        # Phase 3: Reflection memory write-back — wire ReflectionAgent into
                        # the default PlanActFlow path so TASK_OUTCOME memories accumulate
                        # for cross-session learning (previously only in deprecated PlanActGraphFlow).
                        if self._reflection_agent is not None and self.plan is not None:
                            try:
                                from app.domain.models.reflection import (
                                    ProgressMetrics as _ProgressMetrics,
                                )

                                _completed = [s for s in self.plan.steps if s.status == ExecutionStatus.COMPLETED]
                                _failed = [
                                    s for s in self.plan.steps if not s.success and s.status != ExecutionStatus.BLOCKED
                                ]
                                _progress = _ProgressMetrics(
                                    steps_completed=len(_completed),
                                    steps_remaining=0,
                                    total_steps=len(self.plan.steps),
                                    successful_actions=len(_completed),
                                    failed_actions=len(_failed),
                                    errors=[s.notes or "" for s in _failed if s.notes],
                                )
                                _trigger = self._reflection_agent.should_reflect(_progress)
                                if _trigger is not None:
                                    async for _refl_event in self._reflection_agent.reflect(
                                        goal=message.message if hasattr(message, "message") else "",
                                        plan=self.plan,
                                        progress=_progress,
                                        trigger_type=_trigger,
                                    ):
                                        await self._check_cancelled()
                                        yield _refl_event
                            except Exception as _refl_err:
                                logger.debug("Reflection skipped (non-critical): %s", _refl_err)

                        self._transition_to(AgentStatus.SUMMARIZING)
                        continue

                    # Check if step should be skipped (blocked by previous failures)
                    if step.status == ExecutionStatus.BLOCKED:
                        logger.info(f"Skipping blocked step {step.id}: {step.notes or 'blocked by dependency'}")
                        await self._task_state_manager.update_step_status(str(step.id), "blocked")
                        continue

                    # Check dependencies are satisfied
                    if not self._check_step_dependencies(step):
                        logger.warning(f"Step {step.id} has unsatisfied dependencies, marking as blocked")
                        step.mark_blocked("Unsatisfied dependencies")
                        await self._task_state_manager.update_step_status(str(step.id), "blocked")
                        continue

                    # Execute step with tracing
                    logger.info(f"Agent {self._agent_id} started executing step {step.id}: {step.description[:50]}...")

                    with trace_ctx.span(
                        f"step:{step.id}",
                        "agent_step",
                        {"step.id": step.id, "step.description": step.description[:100]},
                    ) as step_span:
                        # Retry loop: honor step.retry_policy
                        retry = step.retry_policy
                        max_attempts = 1 + retry.max_retries
                        attempt = 0
                        backoff = retry.backoff_seconds

                        # PR-7: Resolve execution prompt profile patch once before retry loop
                        from app.domain.models.prompt_profile import PromptTarget as _PromptTarget

                        _exec_patch = await self._resolve_profile_patch(_PromptTarget.EXECUTION)

                        for attempt in range(max_attempts):
                            await self._check_cancelled()
                            if attempt > 0:
                                logger.info(
                                    f"Step {step.id} retry {attempt}/{retry.max_retries} after {backoff:.1f}s backoff"
                                )
                                step_span.set_attribute("step.retry_attempt", attempt)
                                if await self._cancel_token.wait_for_cancellation(backoff):
                                    await self._check_cancelled()
                                backoff *= retry.backoff_multiplier
                                # Reset step state for retry
                                step.success = False
                                step.error = None
                                step.result = None

                            # Mark step as in progress BEFORE execution starts
                            # This fixes "0/4" stall by updating progress immediately
                            step.status = ExecutionStatus.RUNNING
                            await self._task_state_manager.update_step_status(str(step.id), "in_progress")

                            # Emit PlanEvent so frontend sees updated progress immediately
                            yield PlanEvent(status=PlanStatus.UPDATED, plan=self.plan)

                            # Select appropriate executor for this step (multi-agent dispatch)
                            await self._check_cancelled()
                            step_executor = await self._get_executor_for_step(step)
                            if step_executor != self.executor:
                                step_span.set_attribute(
                                    "step.executor",
                                    step_executor.name
                                    if hasattr(step_executor, "name")
                                    else type(step_executor).__name__,
                                )
                                logger.info(f"Using specialized executor for step {step.id}")

                            # Phase 1/4: Pass request contract for search fidelity and entity context
                            if hasattr(step_executor, "set_request_contract") and self._request_contract:
                                step_executor.set_request_contract(self._request_contract)

                            # Pre-step: retrieve conversation context from Qdrant
                            conversation_context: str | None = None
                            if self._conversation_context_service and self._user_id:
                                try:
                                    conv_ctx = await self._conversation_context_service.retrieve_context(
                                        user_id=self._user_id,
                                        session_id=self._session_id,
                                        query=step.description or "",
                                        current_turn_number=getattr(self, "_steps_completed_count", 0),
                                    )
                                    if not conv_ctx.is_empty:
                                        formatted = conv_ctx.format_for_injection(max_chars=3000)
                                        if formatted:
                                            conversation_context = formatted
                                            logger.debug(
                                                "Retrieved conversation context (%d chars, %d turns) for step %s",
                                                len(formatted),
                                                conv_ctx.total_turns,
                                                step.id,
                                            )
                                except Exception as ctx_err:
                                    logger.debug("Conversation context retrieval failed (non-critical): %s", ctx_err)

                            # Phase 4 P1: Mark step executing to prevent compaction
                            if hasattr(step_executor, "_token_manager"):
                                step_executor._token_manager.mark_step_executing()

                            async for event in step_executor.execute_step(
                                self.plan,
                                step,
                                message,
                                conversation_context=conversation_context,
                                profile_patch_text=_exec_patch,
                            ):
                                await self._check_cancelled()
                                # Phase 3: Track tool usage for proactive compaction
                                if isinstance(event, ToolEvent) and event.tool_name:
                                    self._track_tool_usage(event.tool_name)
                                    # Emit WideResearchEvent to drive frontend live overlay
                                    if event.tool_name == "wide_research":
                                        _wr_args = event.function_args
                                        _wr_topic: str = _wr_args.get("topic", "")
                                        _wr_queries: list[str] = _wr_args.get("queries", [])
                                        _wr_types: list[str] = _wr_args.get("search_types") or ["info"]
                                        if event.status == ToolStatus.CALLING:
                                            yield WideResearchEvent(
                                                research_id=event.tool_call_id,
                                                topic=_wr_topic,
                                                status=WideResearchStatus.SEARCHING,
                                                total_queries=len(_wr_queries),
                                                completed_queries=0,
                                                search_types=_wr_types,
                                                current_query=_wr_queries[0] if _wr_queries else None,
                                            )
                                yield event
                                # Emit WideResearchEvent completion after tool result arrives
                                if (
                                    isinstance(event, ToolEvent)
                                    and event.tool_name == "wide_research"
                                    and event.status == ToolStatus.CALLED
                                ):
                                    _wr_args = event.function_args
                                    _wr_topic = _wr_args.get("topic", "")
                                    _wr_queries = _wr_args.get("queries", [])
                                    _wr_types = _wr_args.get("search_types") or ["info"]
                                    yield WideResearchEvent(
                                        research_id=event.tool_call_id,
                                        topic=_wr_topic,
                                        status=WideResearchStatus.COMPLETED,
                                        total_queries=len(_wr_queries),
                                        completed_queries=len(_wr_queries),
                                        search_types=_wr_types,
                                    )

                                # Yield any pending events from skill creator tools (Phase 3: Custom Skills)
                                while self._pending_events:
                                    pending_event = self._pending_events.pop(0)
                                    logger.info(f"Yielding pending event: {type(pending_event).__name__}")
                                    yield pending_event

                            # Phase 4 P1: Mark step completed to allow compaction
                            if hasattr(step_executor, "_token_manager"):
                                step_executor._token_manager.mark_step_completed()

                            # Check if stuck recovery was exhausted — force-fail the step
                            if (
                                hasattr(step_executor, "is_stuck_recovery_exhausted")
                                and step_executor.is_stuck_recovery_exhausted()
                            ):
                                logger.warning(f"Step {step.id} stuck recovery exhausted — force-failing and advancing")
                                step.success = False
                                step.error = "Stuck — exceeded retry limit. Moving to next step."
                                step.status = ExecutionStatus.FAILED
                                step.notes = (
                                    step.notes or ""
                                ) + "\n[Auto-failed: agent stuck in loop, recovery exhausted]"
                                # Reset stuck detector for fresh detection on next step
                                step_executor.reset_reliability_state()
                                break

                            # If step succeeded, break out of retry loop
                            if step.success:
                                break

                            # Classify error using ErrorHandler for structured retry decisions
                            if step.error and attempt < max_attempts - 1:
                                err_ctx = self._error_handler.classify_error(RuntimeError(step.error))
                                is_timeout_err = err_ctx.error_type in (
                                    ErrorType.TIMEOUT,
                                    ErrorType.BROWSER_TIMEOUT,
                                )
                                should_retry = err_ctx.recoverable and (
                                    (is_timeout_err and retry.retry_on_timeout)
                                    or (not is_timeout_err and retry.retry_on_tool_error)
                                )
                            else:
                                should_retry = False
                            if not should_retry:
                                break

                        step_span.set_attribute("step.attempts", attempt + 1)

                        # Mark step status based on actual success/failure
                        # Belt-and-suspenders: explicitly sync step.status with step.success
                        # to guarantee the final PlanEvent carries correct statuses.
                        if step.success:
                            step.status = ExecutionStatus.COMPLETED
                            await self._task_state_manager.update_step_status(str(step.id), "completed")
                        else:
                            step.status = ExecutionStatus.FAILED
                            await self._task_state_manager.update_step_status(str(step.id), "failed")
                        step_span.set_attribute("step.success", step.success)

                        # Emit PlanEvent so frontend progress bar reflects step completion immediately
                        yield PlanEvent(status=PlanStatus.UPDATED, plan=self.plan)

                        # Session bridging: save progress after each step
                        await self._save_progress_artifact()

                        # Phase 5: Incremental checkpoints every N steps
                        if step.success:
                            self._steps_completed_count += 1
                            # Write checkpoint every 5 completed steps
                            if self._steps_completed_count % self._checkpoint_interval == 0:
                                # Find step index in plan
                                step_index = next((i for i, s in enumerate(self.plan.steps) if s.id == step.id), -1)
                                if step_index >= 0:
                                    await self._write_checkpoint(step_index, is_final=False)

                        # Handle step failure - cascade blocking to dependent steps
                        if not step.success and step.status == ExecutionStatus.FAILED:
                            blocked_step_ids = self._handle_step_failure(step)
                            if blocked_step_ids:
                                step_span.set_attribute("step.blocked_dependents", len(blocked_step_ids))
                                logger.info(
                                    f"Step {step.id} failure blocked {len(blocked_step_ids)} dependent steps: "
                                    f"{blocked_step_ids}"
                                )

                    # Check if we can skip plan update phase for faster response
                    # Skipping saves 2-5 seconds by avoiding an LLM call
                    flags = self._resolve_feature_flags()
                    if flags.get("failure_prediction"):
                        try:
                            progress = self._task_state_manager.get_progress_metrics()
                            token_usage_pct = None
                            try:
                                await self.executor._ensure_memory()
                                pressure = self._memory_manager.get_pressure_status(
                                    self.executor.memory.estimate_tokens()
                                )
                                token_usage_pct = pressure.usage_ratio
                            except Exception as e:
                                logger.debug(f"Token pressure lookup failed: {e}")

                            prediction = FailurePredictor().predict(
                                progress=progress,
                                recent_actions=self._task_state_manager.get_recent_actions(),
                                stuck_analysis=None,
                                token_usage_pct=token_usage_pct,
                            )
                            get_metrics().record_failure_prediction(
                                "predicted" if prediction.will_fail else "clear",
                                prediction.probability,
                            )
                            await self._resolve_alert_port().check_thresholds(
                                self._session_id,
                                {"failure_prediction_probability": prediction.probability},
                            )
                            if prediction.will_fail:
                                note = (
                                    f"Failure prediction: {prediction.probability:.0%} risk. "
                                    f"Factors: {', '.join(prediction.factors) or 'unknown'}. "
                                    f"Recommended: {prediction.recommended_action}."
                                )
                                if step.notes:
                                    step.notes = f"{step.notes}\n{note}"
                                else:
                                    step.notes = note
                        except Exception as e:
                            logger.debug(f"Failure prediction failed: {e}")

                    remaining_steps = [s for s in self.plan.steps if not s.is_done()]
                    skip_update, skip_reason = self._should_skip_plan_update(step, len(remaining_steps))

                    if skip_update:
                        logger.debug(f"Skipping plan update: {skip_reason}")
                        # Go directly to EXECUTING (or will exit loop if no more steps)
                        self._transition_to(AgentStatus.EXECUTING)
                    else:
                        logger.info(
                            f"Agent {self._agent_id} completed step {step.id}, state changed from {AgentStatus.EXECUTING} to {AgentStatus.UPDATING}"
                        )
                        # Non-blocking background memory compaction
                        self._background_compact_memory()
                        # Non-blocking background task state save to sandbox
                        self._background_save_task_state()
                        self._transition_to(AgentStatus.UPDATING)
                elif self.status == AgentStatus.UPDATING:
                    # Update plan with tracing
                    await self._check_cancelled()
                    logger.info(f"Agent {self._agent_id} started updating plan")
                    with trace_ctx.span("plan-update", "plan_update") as update_span:
                        async for event in self.planner.update_plan(self.plan, step):
                            await self._check_cancelled()
                            yield event
                        update_span.set_attribute(
                            "plan.remaining_steps", len([s for s in self.plan.steps if not s.is_done()])
                        )
                    logger.info(
                        f"Agent {self._agent_id} plan update completed, state changed from {AgentStatus.UPDATING} to {AgentStatus.EXECUTING}"
                    )
                    if not self._validate_plan_before_execution():
                        self._plan_validation_failures += 1
                        if self._plan_validation_failures >= self._max_plan_validation_failures:
                            logger.error(
                                f"Agent {self._agent_id} repeated validation failures after update, summarizing"
                            )
                            self._transition_to(
                                AgentStatus.SUMMARIZING, force=True, reason="repeated validation failures"
                            )
                            continue
                        logger.info(
                            f"Agent {self._agent_id} plan update failed validation, replanning "
                            f"({self._plan_validation_failures}/{self._max_plan_validation_failures})"
                        )
                        self._transition_to(AgentStatus.PLANNING, force=True, reason="plan update validation failed")
                        continue
                    self._transition_to(AgentStatus.EXECUTING)
                elif self.status == AgentStatus.SUMMARIZING:
                    # Conclusion with tracing
                    await self._check_cancelled()
                    logger.info(f"Agent {self._agent_id} started summarizing")

                    # Sweep workspace for untracked files before summarizing
                    if self._file_sweep_callback:
                        try:
                            await self._file_sweep_callback()
                        except Exception as e:
                            logger.warning(f"File sweep failed before summarizing: {e}")

                    # Inject workspace deliverables listing into summarization context
                    workspace_file_count = 0
                    if self._research_mode == "deep_research" and self._workspace_output_path:
                        try:
                            wp = self._workspace_output_path
                            # Primary: GNU find -printf for size-annotated listing
                            tree_cmd = f"find {wp} -type f -printf '%P  (%s bytes)\\n' 2>/dev/null | sort | head -100"
                            tree_result = await self._sandbox.exec_command(self._session_id, wp, tree_cmd)
                            listing = ""
                            if tree_result.success:
                                listing = (tree_result.data or {}).get("output", "").strip()

                            # Fallback: plain find if -printf is unavailable (Alpine/BusyBox)
                            if not listing:
                                fallback_cmd = f"find {wp} -type f 2>/dev/null | sed 's|^{wp}/||' | sort | head -100"
                                fb_result = await self._sandbox.exec_command(self._session_id, wp, fallback_cmd)
                                if fb_result.success:
                                    listing = (fb_result.data or {}).get("output", "").strip()

                            if listing:
                                workspace_file_count = listing.count("\n") + 1
                                deliverables_ctx = (
                                    "\n\n## Workspace Deliverables\n"
                                    "The following files were created during this research session:\n"
                                    f"```\n{listing}\n```\n"
                                    'Include a "## Deliverables" section in your final report '
                                    "listing each file with a brief description of its contents."
                                )
                                self.executor.system_prompt += deliverables_ctx
                                logger.info(
                                    "Injected workspace listing (%d files) into summarization context",
                                    workspace_file_count,
                                )
                        except Exception as e:
                            logger.warning("Workspace listing for summarization failed: %s", e)

                        # Notify frontend that deliverables are cataloged
                        yield WorkspaceEvent(
                            action="deliverables_ready",
                            workspace_type="research",
                            workspace_path=self._workspace_output_path,
                            deliverables_count=workspace_file_count,
                        )

                    # Fetch session files to include in the final report
                    session_files: list[FileInfo] = []
                    try:
                        session = await self._session_repository.find_by_id(self._session_id)
                        if session and session.files:
                            session_files = session.files
                            logger.debug(f"Found {len(session_files)} session files to include in report")
                    except Exception as e:
                        logger.warning(f"Failed to fetch session files: {e}")

                    summarization_start = time.perf_counter()
                    metrics_port = get_metrics()
                    _eval_final_content = ""  # WP-3: capture last summary content for eval gate
                    with trace_ctx.span("summarizing", "agent_step") as summary_span:
                        async for event in self.executor.summarize(response_policy=self._response_policy):
                            await self._check_cancelled()
                            if isinstance(event, ErrorEvent):
                                logger.warning(f"Agent {self._agent_id} summarization failed: {event.error}")
                                yield event
                                # Bridge ErrorEvent → ErrorContext so handle_error_state() can recover.
                                # ErrorEvents bypass state_context's except block (they aren't Exceptions),
                                # so we must populate _error_context via ErrorRecoveryHandler.
                                self._error_recovery.record_error_context(
                                    ErrorContext(
                                        error_type=ErrorType.TOOL_EXECUTION,
                                        message=f"Summarization failed: {event.error}",
                                        recoverable=True,
                                        recovery_strategy="Retry summarization with relaxed coverage requirements",
                                    ),
                                    status=AgentStatus.SUMMARIZING,
                                )
                                self._transition_to(AgentStatus.ERROR, force=True, reason="summarization failed")
                                break

                            if isinstance(event, (ReportEvent, MessageEvent)):
                                content = event.content if isinstance(event, ReportEvent) else event.message
                                content = content or ""
                                _eval_final_content = content  # WP-3: track latest summary

                                # Phase 0: OutputGuardrails analysis (gated by enable_output_guardrails_in_flow)
                                settings = get_settings()
                                if settings.enable_output_guardrails_in_flow:
                                    guardrail_start = time.perf_counter()
                                    output_guardrails = OutputGuardrails(
                                        check_relevance=True,
                                        check_consistency=True,
                                    )
                                    guardrail_result = output_guardrails.analyze(
                                        output=content,
                                        original_query=message.message,
                                        context=(str(self._request_contract) if self._request_contract else None),
                                    )
                                    metrics_port.record_histogram(
                                        "guardrail_latency_seconds",
                                        value=time.perf_counter() - guardrail_start,
                                        labels={"phase": "relevance"},
                                    )
                                    if guardrail_result.issues:
                                        for issue in guardrail_result.issues:
                                            metrics_port.record_counter(
                                                "guardrail_tripwire_total",
                                                labels={"guardrail": issue.issue_type.value},
                                            )
                                            severity = (
                                                "high"
                                                if issue.severity >= 0.7
                                                else "medium"
                                                if issue.severity >= 0.5
                                                else "low"
                                            )
                                            metrics_port.record_counter(
                                                "output_relevance_failures_total",
                                                labels={"severity": severity},
                                            )
                                        logger.warning(
                                            "OutputGuardrails: %d issues (needs_revision=%s): %s",
                                            len(guardrail_result.issues),
                                            guardrail_result.needs_revision,
                                            [i.description for i in guardrail_result.issues],
                                        )
                                    if (
                                        not guardrail_result.should_deliver
                                        and settings.delivery_fidelity_mode == "enforce"
                                    ):
                                        yield ErrorEvent(
                                            error="Output guardrails blocked delivery: "
                                            + (
                                                guardrail_result.revision_guidance
                                                or "quality/relevance issues detected"
                                            )
                                        )
                                        self._transition_to(
                                            AgentStatus.ERROR,
                                            force=True,
                                            reason="output guardrails blocked",
                                        )
                                        break

                                # Phase 3: Delivery fidelity check (entity/version presence)
                                if settings.enable_delivery_fidelity_v2 and self._request_contract:
                                    fidelity_checker = DeliveryFidelityChecker()
                                    fidelity_result = fidelity_checker.check_entity_fidelity(
                                        content, self._request_contract
                                    )
                                    if not fidelity_result.passed:
                                        metrics_port.record_counter(
                                            "entity_drift_detected_total",
                                            labels={"phase": "summarize"},
                                        )
                                        logger.warning(
                                            "Delivery fidelity: missing entities %s (score=%.2f)",
                                            fidelity_result.missing_entities,
                                            fidelity_result.fidelity_score,
                                        )
                                        if (
                                            settings.delivery_fidelity_mode == "enforce"
                                            and fidelity_result.fidelity_score < 0.8
                                        ):
                                            metrics_port.record_counter(
                                                "delivery_fidelity_blocks_total",
                                                labels={"mode": "enforce"},
                                            )
                                            yield ErrorEvent(
                                                error="Delivery fidelity failed: missing "
                                                + ", ".join(fidelity_result.missing_entities)
                                            )
                                            self._transition_to(
                                                AgentStatus.ERROR,
                                                force=True,
                                                reason="delivery fidelity failed",
                                            )
                                            break

                                # Merge session files with any attachments from the LLM
                                event_attachments = event.attachments if hasattr(event, "attachments") else None
                                all_attachments = list(session_files) if session_files else []
                                if event_attachments:
                                    # Add LLM attachments that aren't already in session files
                                    # Deduplicate by both full path and filename (basename) to handle path variations
                                    existing_paths = {f.file_path for f in all_attachments if f.file_path}
                                    existing_filenames = {
                                        os.path.basename(f.file_path) for f in all_attachments if f.file_path
                                    }
                                    for att in event_attachments:
                                        if att.file_path:
                                            basename = os.path.basename(att.file_path)
                                            # Skip if exact path OR filename already exists
                                            if (
                                                att.file_path not in existing_paths
                                                and basename not in existing_filenames
                                            ):
                                                all_attachments.append(att)
                                                existing_paths.add(att.file_path)
                                                existing_filenames.add(basename)

                                # Update event with merged attachments
                                if all_attachments and isinstance(event, (ReportEvent, MessageEvent)):
                                    event.attachments = all_attachments

                                compliance_report = self._run_compliance_gates(content, all_attachments or None)
                                summary_span.set_attribute("compliance.passed", compliance_report.passed)
                                if compliance_report.blocking_issues:
                                    summary_span.set_attribute(
                                        "compliance.blocking", len(compliance_report.blocking_issues)
                                    )
                                if not compliance_report.passed:
                                    logger.warning(
                                        "Compliance gates failed: " + "; ".join(compliance_report.blocking_issues)
                                    )
                                    yield ErrorEvent(
                                        error="Compliance gates failed: " + "; ".join(compliance_report.blocking_issues)
                                    )
                                    self._transition_to(AgentStatus.ERROR, force=True, reason="compliance gates failed")
                                    break
                            yield event
                    summarization_duration = time.perf_counter() - summarization_start
                    metrics_port.record_histogram(
                        "workflow_phase_duration_seconds",
                        value=summarization_duration,
                        labels={"phase": "summarizing"},
                    )
                    if self.status == AgentStatus.ERROR:
                        continue

                    # WP-3: Ragas eval gate — runs in shadow mode (enable_eval_gates=False by default).
                    # When enabled, emits EvalMetricsEvent with hallucination/faithfulness scores
                    # and logs a warning if hallucination_score > 0.5 for observability.
                    if settings.enable_eval_gates and _eval_final_content:
                        try:
                            from app.domain.models.event import EvalMetricsEvent
                            from app.domain.services.evaluation.ragas_metrics import RagasEvaluator

                            _step_summaries = [
                                s.result[:300] if s.result else s.description
                                for s in (self.plan.steps if self.plan else [])
                                if s.status == ExecutionStatus.COMPLETED
                            ]
                            _evaluator = RagasEvaluator(llm_client=self._llm)
                            _eval_batch = await _evaluator.evaluate_all(
                                question=message.message,
                                answer=_eval_final_content,
                                context=_step_summaries[:10],  # cap context size
                            )
                            _hallucination_result = next(
                                (r for r in _eval_batch.results if r.metric_type.value == "hallucination_score"),
                                None,
                            )
                            _hallucination_score = _hallucination_result.score if _hallucination_result else 0.0
                            if _hallucination_score > 0.5:
                                logger.warning(
                                    "Eval gate: high hallucination score %.2f for session %s",
                                    _hallucination_score,
                                    self._session_id,
                                )
                            metrics_port.increment(
                                "pythinker_eval_gate_runs_total",
                                labels={"session": self._session_id[:8]},
                            )
                            yield EvalMetricsEvent(
                                metrics=_eval_batch.to_dict(),
                                hallucination_score=_hallucination_score,
                                passed=_hallucination_score <= 0.5,
                            )
                        except Exception as _eval_err:
                            logger.debug("Eval gate skipped (non-critical): %s", _eval_err)

                    logger.info(
                        f"Agent {self._agent_id} summarizing completed, state changed from {AgentStatus.SUMMARIZING} to {AgentStatus.COMPLETED}"
                    )
                    self._transition_to(AgentStatus.COMPLETED)
                elif self.status == AgentStatus.COMPLETED:
                    # Reconcile: ensure every successful step carries COMPLETED status
                    # before emitting the final PlanEvent (guards against any missed updates).
                    for s in self.plan.steps:
                        if s.success and s.status != ExecutionStatus.COMPLETED:
                            s.status = ExecutionStatus.COMPLETED
                    self.plan.status = ExecutionStatus.COMPLETED
                    logger.info(f"Agent {self._agent_id} plan has been completed")
                    yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)

                    # Phase 4: Close the Thompson-sampling feedback loop by recording
                    # a successful outcome for the variant used during planning.
                    if self._selected_prompt_variant_id and settings.feature_prompt_profile_runtime:
                        try:
                            from app.domain.services.agents.learning.prompt_optimizer import (
                                PromptOutcome,
                                get_prompt_optimizer,
                            )

                            _latency_ms = (
                                (time.time() - self._planning_start_time) * 1000 if self._planning_start_time else None
                            )
                            get_prompt_optimizer().record_outcome(
                                "planner",
                                PromptOutcome(
                                    variant_id=self._selected_prompt_variant_id,
                                    success=True,
                                    latency_ms=_latency_ms,
                                ),
                            )
                            logger.debug(
                                "Phase 4: Recorded successful outcome for prompt variant '%s'",
                                self._selected_prompt_variant_id,
                            )
                        except Exception as _rec_err:
                            logger.debug("Prompt outcome recording skipped (non-critical): %s", _rec_err)

                    # Cross-session learning: persist error patterns at session end
                    if self._memory_service:
                        try:
                            await self._error_bridge.on_session_end(self._memory_service)
                        except Exception as e:
                            logger.debug(f"Error pattern persistence failed (non-critical): {e}")

                    self._transition_to(AgentStatus.IDLE)
                    break

            except Exception as e:
                # Classify and handle error via ErrorRecoveryHandler
                err_ctx = self._error_recovery.record_error(e, self.status)
                self._transition_to(AgentStatus.ERROR, force=True, reason="exception handler")

                if isinstance(e, LLMKeysExhaustedError):
                    logger.debug("Agent %s: API keys exhausted — failing fast", self._agent_id)
                else:
                    logger.error(f"Agent {self._agent_id} encountered error: {e}")

                # Add error span with health assessment
                with trace_ctx.span("error", "error_recovery") as error_span:
                    error_span.set_attribute("error.type", str(err_ctx.error_type))
                    error_span.set_attribute("error.recoverable", err_ctx.recoverable)
                    error_span.set_attribute("error.message", str(e)[:200])

                    # Use error bridge for health assessment
                    try:
                        health = self._error_bridge.assess_agent_health()
                        error_span.set_attribute("agent.health_level", health.level.value)
                        error_span.set_attribute("agent.error_count", health.error_count_recent)

                        if health.level == AgentHealthLevel.CRITICAL:
                            logger.warning(
                                f"Agent {self._agent_id} health CRITICAL: {', '.join(health.recommended_actions)}"
                            )
                    except Exception as health_err:
                        logger.debug(f"Health assessment failed: {health_err}")

                # Phase 4: Record failure outcome so the bandit learns from bad variants
                if self._selected_prompt_variant_id and settings.feature_prompt_profile_runtime:
                    try:
                        from app.domain.services.agents.learning.prompt_optimizer import (
                            PromptOutcome,
                            get_prompt_optimizer,
                        )

                        get_prompt_optimizer().record_outcome(
                            "planner",
                            PromptOutcome(
                                variant_id=self._selected_prompt_variant_id,
                                success=False,
                                error=str(e)[:200],
                            ),
                        )
                    except Exception:
                        logger.debug("prompt_optimizer.record_outcome failed (non-critical)")

                # If not recoverable, yield error and exit
                if not err_ctx.recoverable:
                    yield ErrorEvent(error=f"Unrecoverable error: {err_ctx.message}")
                    break

        yield DoneEvent()

        logger.info(f"Agent {self._agent_id} message processing completed")

    def is_done(self) -> bool:
        return self.status == AgentStatus.IDLE

    def get_status(self) -> FlowStatus:
        """Map internal AgentStatus to canonical FlowStatus."""
        _map = {
            AgentStatus.IDLE: FlowStatus.IDLE,
            AgentStatus.PLANNING: FlowStatus.PLANNING,
            AgentStatus.EXECUTING: FlowStatus.EXECUTING,
            AgentStatus.VERIFYING: FlowStatus.VERIFYING,
            AgentStatus.REFLECTING: FlowStatus.REFLECTING,
            AgentStatus.SUMMARIZING: FlowStatus.SUMMARIZING,
            AgentStatus.COMPLETED: FlowStatus.COMPLETED,
            AgentStatus.UPDATING: FlowStatus.EXECUTING,
            AgentStatus.ERROR: FlowStatus.FAILED,
        }
        return _map.get(self.status, FlowStatus.IDLE)
