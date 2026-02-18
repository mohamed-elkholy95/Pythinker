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
from app.domain.services.orchestration.agent_factory import (
    DefaultAgentFactory,
    SpecializedAgentFactory,
)

# Import orchestration components for multi-agent dispatch
from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentRegistry,
    AgentType,
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

# ---------------------------------------------------------------------------
# Research keywords reused for parallel research detection (matches _assign_phases_to_plan)
# ---------------------------------------------------------------------------
_RESEARCH_KEYWORDS = frozenset(
    {
        "search",
        "find",
        "gather",
        "collect",
        "browse",
        "explore",
        "research",
        "investigate",
        "look up",
        "discover",
    }
)


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
        enable_parallel_execution: bool = False,
        parallel_max_concurrency: int = 3,
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
    ):
        self._feature_flags = feature_flags
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

        # State management for error recovery
        self._previous_status: AgentStatus | None = None
        self._error_context: ErrorContext | None = None
        self._error_handler = ErrorHandler()
        self._max_error_recovery_attempts = 3
        self._error_recovery_attempts = 0
        self._total_error_count = 0  # Track total errors across all recovery cycles
        self._max_total_errors = 10  # Absolute limit on errors per run

        # Verification state (Phase 1: Plan-Verify-Execute)
        self._verification_verdict: str | None = None
        self._verification_feedback: str | None = None
        self._verification_loops = 0
        self._max_verification_loops = 1  # Reduced from 2 to 1 for faster response

        # Plan validation failure tracking
        self._plan_validation_failures = 0
        self._max_plan_validation_failures = 3

        tools = [
            ShellTool(sandbox),
            BrowserTool(browser),
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
            self._search_tool = SearchTool(search_engine, browser=browser)
            tools.append(self._search_tool)

        # Add browser agent tool when cdp_url is available, enabled, and browser_use is installed
        if cdp_url and browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
            try:
                tools.append(BrowserAgentTool(cdp_url))
                logger.info(f"Browser agent tool enabled for Agent {agent_id}")
            except ImportError as e:
                logger.warning(f"Browser agent tool not available: {e}")

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

    def _extract_agent_type(self, step_description: str) -> str | None:
        """Extract [AGENT_TYPE] prefix from step description.

        Example: "[RESEARCH] Find documentation on the topic" -> "research"
        """
        match = re.search(r"\[([A-Z_]+)\]", step_description)
        if match:
            return match.group(1).lower()
        return None

    def _infer_capabilities(self, step: Step) -> set[AgentCapability]:
        """Infer required capabilities from step description."""
        capabilities: set[AgentCapability] = set()
        desc_lower = step.description.lower()

        # Map keywords to capabilities
        capability_keywords = {
            AgentCapability.WEB_BROWSING: ["browse", "website", "page", "click", "navigate", "visit"],
            AgentCapability.WEB_SEARCH: ["search", "find", "lookup", "query", "google"],
            AgentCapability.CODE_WRITING: ["code", "implement", "write", "function", "class", "script", "program"],
            AgentCapability.CODE_REVIEW: ["review", "check", "audit", "verify code", "find bugs"],
            AgentCapability.FILE_OPERATIONS: ["file", "read", "write", "save", "create file", "modify"],
            AgentCapability.SHELL_COMMANDS: ["run", "execute", "shell", "command", "terminal", "bash"],
            AgentCapability.RESEARCH: ["research", "investigate", "study", "analyze", "gather"],
            AgentCapability.SUMMARIZATION: ["summarize", "summary", "brief", "overview", "condense"],
        }

        for capability, keywords in capability_keywords.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    capabilities.add(capability)
                    break

        return capabilities

    async def _get_executor_for_step(self, step: Step) -> BaseAgent:
        """Select the appropriate executor for a step.

        Uses the AgentRegistry to select a specialized agent based on:
        1. Explicit [AGENT_TYPE] prefix in step description
        2. Inferred capabilities from step description
        3. Falls back to the default ExecutionAgent

        Args:
            step: The step to get an executor for

        Returns:
            A BaseAgent (specialized or default ExecutionAgent)
        """
        if not self._enable_multi_agent or not self._agent_registry:
            return self.executor

        # Check for explicit agent type in step
        agent_type_hint = self._extract_agent_type(step.description)

        # Check if step has agent_type set
        if step.agent_type:
            agent_type_hint = step.agent_type

        # Try to match by type first
        if agent_type_hint:
            try:
                agent_type = AgentType(agent_type_hint)
                spec = self._agent_registry.get(agent_type)
                if spec:
                    # Check if we already have this agent created
                    cache_key = f"{agent_type.value}_{self._agent_id}"
                    if cache_key not in self._specialized_agents:
                        agent = await self._agent_factory.create_agent(
                            agent_type,
                            f"{self._agent_id}_{agent_type.value}",
                            spec,
                        )
                        self._specialized_agents[cache_key] = agent
                        logger.info(f"Created specialized {agent_type.value} agent for step")
                    return self._specialized_agents[cache_key]
            except ValueError:
                logger.debug(f"Unknown agent type hint: {agent_type_hint}")

        # Try to match by inferred capabilities
        capabilities = self._infer_capabilities(step)
        if capabilities:
            candidates = self._agent_registry.select_for_task(
                task_description=step.description,
                context={"session_id": self._session_id},
                required_capabilities=capabilities,
            )
            if candidates:
                best_spec = candidates[0]
                cache_key = f"{best_spec.agent_type.value}_{self._agent_id}"
                if cache_key not in self._specialized_agents:
                    agent = await self._agent_factory.create_agent(
                        best_spec.agent_type,
                        f"{self._agent_id}_{best_spec.agent_type.value}",
                        best_spec,
                    )
                    self._specialized_agents[cache_key] = agent
                    logger.info(
                        f"Selected specialized {best_spec.agent_type.value} agent "
                        f"for step based on capabilities: {capabilities}"
                    )
                return self._specialized_agents[cache_key]

        # Fall back to default executor
        return self.executor

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
        """Assign phases to plan steps based on step descriptions.

        Groups steps into logical phases (research, analysis, report, delivery)
        for structured progress display in the frontend.
        """
        from app.domain.models.plan import Phase, PhaseType

        if not self.plan or not self.plan.steps:
            return

        # For simple plans (<=3 steps), use a single execution phase
        if len(self.plan.steps) <= 3:
            self.plan.phases = [
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Executing",
                    description="Executing plan steps",
                    order=0,
                    step_ids=[s.id for s in self.plan.steps],
                ),
            ]
            return

        # For larger plans, group steps into phases heuristically
        research_ids: list[str] = []
        analysis_ids: list[str] = []
        report_ids: list[str] = []

        research_keywords = {"search", "find", "gather", "collect", "browse", "explore", "research", "investigate"}
        report_keywords = {"write", "create", "compile", "draft", "generate", "report", "summarize", "compose"}

        for step in self.plan.steps:
            desc_lower = step.description.lower()
            if any(kw in desc_lower for kw in research_keywords):
                research_ids.append(step.id)
            elif any(kw in desc_lower for kw in report_keywords):
                report_ids.append(step.id)
            else:
                analysis_ids.append(step.id)

        phases: list[Phase] = []
        order = 0
        if research_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Research",
                    description="Gathering information",
                    order=order,
                    step_ids=research_ids,
                )
            )
            order += 1
        if analysis_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.ANALYSIS_SYNTHESIS,
                    label="Analysis",
                    description="Analyzing findings",
                    order=order,
                    step_ids=analysis_ids,
                )
            )
            order += 1
        if report_ids:
            phases.append(
                Phase(
                    phase_type=PhaseType.REPORT_GENERATION,
                    label="Report",
                    description="Generating output",
                    order=order,
                    step_ids=report_ids,
                )
            )

        # Fallback: if all steps ended up in one bucket or none matched
        if not phases:
            phases = [
                Phase(
                    phase_type=PhaseType.RESEARCH_FOUNDATION,
                    label="Executing",
                    description="Executing plan steps",
                    order=0,
                    step_ids=[s.id for s in self.plan.steps],
                ),
            ]

        self.plan.phases = phases

    # -----------------------------------------------------------------------
    # Parallel Research (MindSearch-inspired)
    # -----------------------------------------------------------------------

    def _should_use_parallel_research(self) -> bool:
        """Detect if the current plan should use parallel sub-question search.

        Returns True when:
        - Feature flag is enabled
        - Thinking mode is NOT 'fast' (fast mode skips parallel research for speed)
        - Plan has enough research-type steps (>= min_subquestions)
        - We are NOT already in deep_research mode (which has its own flow)
        """
        settings = get_settings()
        if not settings.parallel_research_enabled:
            return False

        # Fast thinking mode opts out of parallel research — speed over coverage
        if getattr(self, "_current_thinking_mode", None) == "fast":
            return False

        if not self.plan or not self.plan.steps:
            return False

        research_steps = self._get_research_steps()
        return len(research_steps) >= settings.parallel_research_min_subquestions

    def _get_research_steps(self) -> list[Step]:
        """Identify steps that are search/research tasks.

        Uses the same keyword set as _assign_phases_to_plan for consistency.
        """
        research_steps = []
        for step in self.plan.steps:
            if step.status != ExecutionStatus.PENDING:
                continue
            desc_lower = step.description.lower()
            if any(kw in desc_lower for kw in _RESEARCH_KEYWORDS):
                research_steps.append(step)
        return research_steps

    def _partition_research_steps(self) -> tuple[list[Step], list[Step]]:
        """Split plan steps into research steps (parallelizable) and remaining steps.

        Returns:
            (research_steps, remaining_steps) — both in original order.
        """
        research_ids = {s.id for s in self._get_research_steps()}
        research = [s for s in self.plan.steps if s.id in research_ids]
        remaining = [s for s in self.plan.steps if s.id not in research_ids]
        return research, remaining

    async def _execute_parallel_research_steps(
        self,
        research_steps: list[Step],
        trace_ctx: Any,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute research steps in parallel via WideResearchOrchestrator.

        This is the core MindSearch-inspired enhancement: instead of executing
        search steps one-at-a-time through the standard executor, we fan them
        out concurrently and collect results.

        Args:
            research_steps: Steps identified as search/research tasks
            trace_ctx: Tracing context for observability
        """
        from app.domain.models.event import (
            DeepResearchEvent,
            DeepResearchQueryData,
            DeepResearchQueryStatus,
            DeepResearchStatus,
        )
        from app.domain.services.agents.research_query_decomposer import ResearchQueryDecomposer
        from app.domain.services.research.search_adapter import SearchToolAdapter
        from app.domain.services.research.wide_research import WideResearchOrchestrator

        settings = get_settings()

        if not self._search_engine:
            logger.warning("Parallel research skipped: no search engine available")
            return

        research_id = uuid4().hex[:12]

        # ── Query generation: LLM decomposition or step descriptions ────
        if settings.parallel_research_llm_decomposition and self._llm:
            # Combine all research step descriptions into a single question
            combined_question = "; ".join(s.description for s in research_steps)
            decomposer = ResearchQueryDecomposer()
            queries = await decomposer.decompose(combined_question, self._llm)
            logger.info(
                f"Agent {self._agent_id} LLM decomposition produced "
                f"{len(queries)} sub-questions from {len(research_steps)} steps"
            )
        else:
            # Fallback: use step descriptions directly (Phase 1 behaviour)
            queries = [step.description for step in research_steps]

        logger.info(
            f"Agent {self._agent_id} starting parallel research: "
            f"{len(queries)} sub-questions, max_concurrency={settings.parallel_research_max_concurrency}"
        )

        # Emit initial research progress event (reuse DeepResearchEvent protocol)
        query_data = [
            DeepResearchQueryData(
                id=str(idx),
                query=q,
                status=DeepResearchQueryStatus.PENDING,
            )
            for idx, q in enumerate(queries)
        ]
        yield DeepResearchEvent(
            research_id=research_id,
            status=DeepResearchStatus.STARTED,
            total_queries=len(queries),
            completed_queries=0,
            queries=query_data,
            auto_run=True,
        )

        # Create orchestrator with search adapter
        adapter = SearchToolAdapter(self._search_engine)
        completed_count = 0

        async def on_progress(task: Any) -> None:
            """Track progress for event emission."""
            nonlocal completed_count
            if hasattr(task, "status") and task.status.value in ("completed", "failed"):
                completed_count += 1

        orchestrator = WideResearchOrchestrator(
            session_id=self._session_id,
            search_tool=adapter,
            llm=None,  # Synthesis done by ExecutionAgent.summarize(), not here
            max_concurrency=settings.parallel_research_max_concurrency,
            on_progress=on_progress,
        )

        # Decompose and execute — with optional dependency ordering
        with trace_ctx.span("parallel_research", "agent_step") as research_span:
            research_span.set_attribute("research.query_count", len(queries))

            tasks = await orchestrator.decompose(queries, parent_id=self._session_id)

            # Check for inter-query dependencies via TaskDecomposer
            from app.domain.services.agents.task_decomposer import TaskDecomposer

            combined_text = "\n".join(queries)
            decomposer = TaskDecomposer()
            decomp_result = decomposer.decompose(combined_text)

            if len(decomp_result.parallel_groups) > 1 and decomp_result.strategy.value != "atomic":
                # Dependencies detected — execute level-by-level with context
                # Map decomposer subtask indices → research task indices
                parallel_groups: list[list[int]] = []
                subtask_ids = [s.id for s in decomp_result.subtasks]
                for group in decomp_result.parallel_groups:
                    indices = []
                    for sid in group:
                        if sid in subtask_ids:
                            idx = subtask_ids.index(sid)
                            if idx < len(tasks):
                                indices.append(idx)
                    if indices:
                        parallel_groups.append(indices)

                if parallel_groups:
                    logger.info(f"Dependency-aware execution: {len(parallel_groups)} levels")
                    research_span.set_attribute("research.dependency_levels", len(parallel_groups))
                    completed_tasks = await orchestrator.execute_with_dependencies(tasks, parallel_groups)
                else:
                    completed_tasks = await orchestrator.execute_parallel(tasks)
            else:
                # No dependencies — fully parallel (Phase 1 behaviour)
                completed_tasks = await orchestrator.execute_parallel(tasks)

            research_span.set_attribute(
                "research.completed",
                sum(1 for t in completed_tasks if t.status.value == "completed"),
            )

        # ── Map results back ──────────────────────────────────────────
        # When LLM decomposition is used, the number of completed_tasks
        # may differ from research_steps.  We collect ALL task results
        # into the executor context, and mark original plan steps as
        # completed so the sequential loop skips them.

        accumulated_findings: list[str] = []
        successful_tasks = 0

        # Collect results and track sources from all completed tasks
        for task in completed_tasks:
            if task.status.value == "completed" and task.result:
                successful_tasks += 1
                accumulated_findings.append(f"## {task.query}\n{task.result}")

                if task.sources:
                    for source_url in task.sources:
                        self.executor._track_parallel_research_source(url=source_url, query=task.query)

        # Mark original plan research steps as completed
        for step in research_steps:
            step.status = ExecutionStatus.COMPLETED
            step.success = successful_tasks > 0
            step.result = f"Covered by parallel research ({successful_tasks} sub-queries)"
            yield StepEvent(step=step, status=StepStatus.COMPLETED)
            await self._task_state_manager.update_step_status(str(step.id), "completed")

        # Emit completion event with actual query data
        final_query_data = [
            DeepResearchQueryData(
                id=str(idx),
                query=task.query,
                status=DeepResearchQueryStatus.COMPLETED
                if task.status.value == "completed"
                else DeepResearchQueryStatus.FAILED,
            )
            for idx, task in enumerate(completed_tasks)
        ]
        yield DeepResearchEvent(
            research_id=research_id,
            status=DeepResearchStatus.COMPLETED,
            total_queries=len(queries),
            completed_queries=successful_tasks,
            queries=final_query_data,
            auto_run=True,
        )

        if accumulated_findings:
            research_context = "\n\n---\n\n".join(accumulated_findings)
            self.executor._parallel_research_context = research_context
            logger.info(
                f"Parallel research complete: {len(accumulated_findings)} findings "
                f"({len(research_context)} chars) injected into executor context"
            )

        # Update plan progress
        yield PlanEvent(status=PlanStatus.UPDATED, plan=self.plan)

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
            self._error_recovery_attempts = 0

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

    async def _generate_acknowledgment(self, user_message: str) -> str:
        """Generate an acknowledgment message before starting to plan."""
        return await self._ack_refiner.generate(user_message)

    def _extract_research_topic(self, user_message: str) -> str | None:
        """Extract the research topic from the user's message."""
        return self._ack_generator._extract_research_topic(user_message)

    async def _execute_deep_research(
        self, topic: str, original_message: str, trace_ctx
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute deep research through the DeepResearchFlow manager path."""
        del original_message, trace_ctx  # Reserved for future tracing hooks

        from app.core.deep_research_manager import get_deep_research_manager
        from app.domain.models.deep_research import DeepResearchConfig
        from app.domain.models.event import DeepResearchEvent, DeepResearchStatus
        from app.domain.services.flows.deep_research import DeepResearchFlow
        from app.domain.services.flows.phased_research import PhasedResearchFlow

        logger.info(f"Executing deep research on topic: {topic}")

        if self._search_engine is None:
            yield MessageEvent(message="Search capabilities are not available for deep research.")
            yield DoneEvent()
            return

        deep_flags = self._resolve_feature_flags()
        if deep_flags.get("phased_research"):
            phased_flow = PhasedResearchFlow(
                search_engine=self._search_engine,
                session_id=self._session_id,
            )

            try:
                async for event in phased_flow.run(topic):
                    yield event
                yield DoneEvent()
            except Exception as e:
                logger.error(f"Phased deep research failed: {e}")
                yield ErrorEvent(error=f"Deep research failed: {e}")
                yield DoneEvent()
            return

        queries = self._generate_research_queries(topic)
        if not queries:
            yield MessageEvent(message="I couldn't generate valid research queries for that topic.")
            yield DoneEvent()
            return

        flow = DeepResearchFlow(search_engine=self._search_engine, session_id=self._session_id)
        manager = get_deep_research_manager()
        registered = False

        try:
            await manager.register(self._session_id, flow)
            registered = True

            config = DeepResearchConfig(
                queries=queries,
                auto_run=True,  # Preserve current immediate-run behavior
                max_concurrent=min(5, max(1, len(queries))),
            )

            completed_event: DeepResearchEvent | None = None
            async for event in flow.run(config):
                # Keep frontend status text stable while per-query updates stream through query payloads.
                if event.status in {
                    DeepResearchStatus.QUERY_STARTED,
                    DeepResearchStatus.QUERY_COMPLETED,
                    DeepResearchStatus.QUERY_SKIPPED,
                }:
                    event = event.model_copy(update={"status": DeepResearchStatus.STARTED})
                # Hold the COMPLETED event — emit SUMMARIZING first so the phase bar
                # transitions properly before the final completion signal.
                if event.status == DeepResearchStatus.COMPLETED:
                    completed_event = event
                else:
                    yield event

            # Signal summarizing phase so the progress bar shows it as active
            if completed_event is not None:
                yield completed_event.model_copy(update={"status": DeepResearchStatus.SUMMARIZING})

            summary = flow.generate_research_summary()
            if summary:
                yield ReportEvent(
                    id=str(uuid4()),
                    title=f"Research: {topic}",
                    content=summary,
                    attachments=[],
                )

            # Emit final completed event after the report is ready
            if completed_event is not None:
                yield completed_event

            yield DoneEvent()
        except Exception as e:
            logger.error(f"Deep research failed: {e}")
            yield ErrorEvent(error=f"Deep research failed: {e}")
            yield DoneEvent()
        finally:
            if registered:
                await manager.unregister(self._session_id)

    def _generate_research_queries(self, topic: str) -> list[str]:
        """Generate search queries from a research topic.

        Args:
            topic: The research topic

        Returns:
            A list of search queries for comprehensive coverage
        """
        # Start with the topic itself
        queries = [topic]

        # Add variations for broader coverage
        topic_lower = topic.lower()

        # Add "best" query if not already present and topic doesn't start with an article
        if "best" not in topic_lower and not topic_lower.startswith(("the ", "a ", "an ")):
            queries.append(f"best {topic}")

        # Add "comparison" query if not already present
        if "comparison" not in topic_lower and "compare" not in topic_lower:
            queries.append(f"{topic} comparison")

        # Add "review" query for product/service topics
        if "review" not in topic_lower:
            queries.append(f"{topic} review")

        # Add year if not present (for recency)
        current_year = datetime.now(UTC).year
        if str(current_year) not in topic and str(current_year - 1) not in topic:
            queries.append(f"{topic} {current_year}")

        return queries[:5]  # Limit to 5 queries

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

    def _handle_step_failure(self, failed_step: Step) -> list[str]:
        """Handle step failure by marking dependent steps as blocked."""
        if not self.plan:
            return []
        return self._step_failure_handler.handle_failure(self.plan, failed_step)

    def _should_skip_step(self, step: Step) -> tuple[bool, str]:
        """Check if a step should be skipped."""
        if not self.plan:
            return False, ""
        return self._step_failure_handler.should_skip_step(self.plan, step)

    def _check_and_skip_steps(self) -> list[str]:
        """Check all pending steps and skip those that should be skipped."""
        if not self.plan:
            return []
        return self._step_failure_handler.check_and_skip_steps(self.plan)

    def _is_read_only_step(self, step: Step) -> bool:
        """Check if a step is likely read-only (doesn't modify state).

        Read-only steps don't require plan updates after completion since they
        don't change the execution context significantly.

        Args:
            step: The step to check

        Returns:
            True if the step appears to be read-only
        """
        if not step or not step.description:
            return False

        desc_lower = step.description.lower()

        # Research-style steps can discover new work and should keep plan updates enabled.
        dynamic_research_patterns = [
            "research",
            "investigate",
            "explore",
            "analyze",
            "review",
            "compare",
            "search",
            "browse",
            "fetch",
            "retrieve",
            "verify",
            "validate",
            "cross-check",
            "benchmark",
        ]
        if any(pattern in desc_lower for pattern in dynamic_research_patterns):
            return False

        # Read-only action patterns
        read_only_patterns = [
            "read",
            "view",
            "list",
            "check",
            "inspect",
            "show",
            "display",
            "print",
            "understand",
            "learn",
        ]

        # Write action patterns (if present, NOT read-only)
        write_patterns = [
            "write",
            "create",
            "modify",
            "update",
            "delete",
            "remove",
            "install",
            "execute",
            "run",
            "build",
            "compile",
            "deploy",
            "change",
            "edit",
            "save",
            "store",
            "set",
            "configure",
        ]

        has_read_pattern = any(pattern in desc_lower for pattern in read_only_patterns)
        has_write_pattern = any(pattern in desc_lower for pattern in write_patterns)

        # Read-only if has read patterns but no write patterns
        return has_read_pattern and not has_write_pattern

    def _is_research_or_complex_task(self, step: Step | None = None) -> bool:
        """Detect tasks where dynamic plan updates should remain enabled."""
        try:
            if (
                hasattr(self, "_cached_complexity")
                and self._cached_complexity is not None
                and self._cached_complexity >= 0.45
            ):
                return True
        except Exception:
            logger.debug("Complexity probe failed while checking dynamic plan update eligibility", exc_info=True)

        research_patterns = [
            "research",
            "investigate",
            "explore",
            "analyze",
            "compare",
            "multi-source",
            "multiple sources",
            "benchmark",
            "report",
            "citation",
            "cross-check",
            "verify findings",
            "validate findings",
        ]
        texts_to_scan: list[str] = []
        if step and step.description:
            texts_to_scan.append(step.description)
        if self.plan:
            if self.plan.goal:
                texts_to_scan.append(self.plan.goal)
            if self.plan.message:
                texts_to_scan.append(self.plan.message)

        for text in texts_to_scan:
            lowered = text.lower()
            if any(pattern in lowered for pattern in research_patterns):
                return True
        return False

    def _should_skip_plan_update(self, step: Step, remaining_steps: int) -> tuple[bool, str]:
        """Determine if plan update phase should be skipped for faster execution.

        Skipping plan updates saves 2-5 seconds per step by avoiding an LLM call.
        Safe to skip when the plan state is predictable.

        Args:
            step: The step that just completed
            remaining_steps: Number of pending steps remaining

        Returns:
            Tuple of (should_skip, reason)
        """
        # No remaining work means there is nothing left to update.
        if remaining_steps <= 0:
            return True, "no remaining steps"

        # Skip if step failed (will trigger replanning anyway)
        if not step.success:
            return True, "step failed"

        # Keep dynamic updates enabled for research/complex tasks so the planner
        # can add follow-up steps when discoveries require deeper investigation.
        if self._is_research_or_complex_task(step):
            return False, ""

        # Skip for simple tasks (complexity-based optimization)
        try:
            # Use cached complexity score if available
            if (
                hasattr(self, "_cached_complexity")
                and self._cached_complexity is not None
                and self._cached_complexity < 0.4  # Simple task threshold
            ):
                return True, f"simple task (complexity={self._cached_complexity:.2f})"
        except Exception as e:
            logger.debug(f"Complexity check failed, continuing with verification: {e}")

        # Skip for read-only steps (they don't change execution context)
        if self._is_read_only_step(step) and remaining_steps <= 1:
            return True, "read-only step"

        # For non-research tasks, skip update on final pending step.
        if remaining_steps == 1:
            return True, "final pending step"

        # Default: don't skip
        return False, ""

    def _check_step_dependencies(self, step: Step) -> bool:
        """Check if a step's dependencies are satisfied.

        A step can execute if all its dependencies are either:
        - Completed successfully
        - Skipped (considered successful)

        Args:
            step: The step to check

        Returns:
            True if all dependencies are satisfied, False otherwise
        """
        if not self.plan or not step.dependencies:
            return True

        for dep_id in step.dependencies:
            dep_step = next((s for s in self.plan.steps if s.id == dep_id), None)
            if not dep_step:
                # Dependency not found - treat as satisfied (might be external)
                continue

            if dep_step.status not in [ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED]:
                # Dependency not yet satisfied
                if dep_step.status in [ExecutionStatus.FAILED, ExecutionStatus.BLOCKED]:
                    # Dependency failed - this step should be blocked
                    step.mark_blocked(f"Dependency {dep_id} failed", blocked_by=dep_id)
                    return False
                if dep_step.status in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
                    # Dependency not yet complete - shouldn't happen if get_next_step works correctly
                    return False

        return True

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
                    self._previous_status = old_status
                    self._error_context = self._error_handler.classify_error(e)
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
                self._previous_status = old_status
                self._error_context = self._error_handler.classify_error(e)
                self._transition_to(AgentStatus.ERROR, force=True, reason="state context error")
                logger.error(f"Agent {self._agent_id} error in state {new_status}: {e}")
                raise

    async def handle_error_state(self) -> bool:
        """
        Handle ERROR state with recovery attempts.

        Returns:
            True if recovery successful and can continue, False otherwise
        """
        if self.status != AgentStatus.ERROR:
            return True

        if not self._error_context:
            logger.error("No error context available for recovery")
            return False

        # Track total errors across all recovery cycles (prevents slow infinite loops)
        self._total_error_count += 1
        if self._total_error_count >= self._max_total_errors:
            logger.error(f"Max total errors ({self._max_total_errors}) reached across all recovery cycles")
            return False

        if self._error_recovery_attempts >= self._max_error_recovery_attempts:
            logger.error(f"Max recovery attempts ({self._max_error_recovery_attempts}) reached")
            return False

        self._error_recovery_attempts += 1
        logger.info(f"Attempting error recovery ({self._error_recovery_attempts}/{self._max_error_recovery_attempts})")

        # Try to recover based on error type - restore previous status if recoverable
        if self._error_context.recoverable and self._previous_status:
            # Generate recovery prompt so the agent knows what went wrong
            recovery_prompt = self._error_handler.get_recovery_prompt(self._error_context)
            if recovery_prompt and hasattr(self, "executor") and self.executor:
                try:
                    if hasattr(self.executor, "memory") and self.executor.memory:
                        self.executor.memory.add_message({"role": "system", "content": recovery_prompt})
                        logger.info(f"Injected recovery prompt for {self._error_context.error_type.value}")
                except Exception as e:
                    logger.debug(f"Could not inject recovery prompt: {e}")

            self._transition_to(self._previous_status, force=True, reason="error recovery")
            self._previous_status = None
            logger.info(f"Recovered to previous state: {self.status}")
            return True

        return False

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
        # Browser-dependent queries (browse/search) need session to be PENDING or COMPLETED
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
                # Browser queries need session to be ready (not INITIALIZING)
                if session.status in (SessionStatus.PENDING, SessionStatus.COMPLETED):
                    browser_ready = await self._verify_browser_ready(session)
                    if browser_ready:
                        use_fast_path = True
                    else:
                        skip_reason = "browser not ready"
                else:
                    skip_reason = f"browser queries need initialized session (status={session.status.value})"
            else:
                skip_reason = "TASK intent requires full workflow"

            if use_fast_path:
                logger.info(f"Fast path activated for {intent.value} query: {message.message[:50]}...")

                # Update session status
                await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)

                # Execute fast path and yield all events
                async for event in fast_path_router.execute(intent, params, message):
                    yield event

                # For GREETING, keep session PENDING (waiting for actual task)
                # For other fast paths (BROWSE, SEARCH, KNOWLEDGE), mark as COMPLETED
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
            yield WaitEvent()
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

        # === DEEP RESEARCH MODE ===
        # When deep_research is True, directly execute wide_research tool
        # This provides parallel multi-source search capabilities
        # Track deep_research flag so parallel research doesn't double-trigger
        self._message_deep_research = message.deep_research
        self._parallel_research_done = False

        # === THINKING MODE: propagate user model-tier override to executor ===
        # 'fast' -> FAST tier, 'deep_think' -> POWERFUL tier, None/'auto' -> complexity-based auto
        self._current_thinking_mode = message.thinking_mode  # Store for parallel research gating
        if message.thinking_mode and message.thinking_mode != "auto":
            self.executor.set_thinking_mode(message.thinking_mode)
            logger.info(
                "Thinking mode override applied for session %s: %s",
                self._session_id,
                message.thinking_mode,
            )
        else:
            self.executor.set_thinking_mode(None)  # Reset to auto

        if message.deep_research:
            logger.info(f"Deep Research mode activated for session {self._session_id}")
            topic = self._extract_research_topic(message.message) or message.message
            logger.info(f"Deep Research topic: {topic}")

            # Execute wide_research directly through the search tool
            async for event in self._execute_deep_research(topic, message.message, trace_ctx):
                yield event

            # After deep research, proceed to summarization
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
            logger.info(f"Deep Research completed for session {self._session_id}")
            return
        # === END DEEP RESEARCH MODE ===

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
                        error_msg = self._error_context.message if self._error_context else "Unknown error"
                        error_type = self._error_context.error_type.value if self._error_context else "unknown"
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

                        async for event in self.planner.create_plan(message, replan_context=replan_context):
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
                        if self._verification_loops >= self._max_verification_loops:
                            logger.warning(
                                f"Agent {self._agent_id} max verification loops reached, proceeding with execution"
                            )
                            if not self._validate_plan_before_execution():
                                # After max verification loops, don't loop back to PLANNING — summarize
                                logger.warning(
                                    f"Agent {self._agent_id} plan invalid after max verifications, summarizing"
                                )
                                self._transition_to(
                                    AgentStatus.SUMMARIZING, force=True, reason="plan invalid after max verifications"
                                )
                            else:
                                self._transition_to(AgentStatus.EXECUTING)
                        else:
                            logger.info(f"Agent {self._agent_id} plan needs revision, returning to planning")
                            self._transition_to(AgentStatus.PLANNING)
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
                            continue

                    # === PARALLEL RESEARCH (MindSearch-inspired) ===
                    # Before entering the standard step-by-step loop, check if
                    # this plan has multiple research steps that can be fanned
                    # out concurrently for faster execution.
                    if (
                        not getattr(self, "_parallel_research_done", False)
                        and not getattr(self, "_message_deep_research", False)
                        and self._should_use_parallel_research()
                    ):
                        self._parallel_research_done = True  # Only run once per plan
                        research_steps, _remaining = self._partition_research_steps()
                        logger.info(
                            f"Agent {self._agent_id} routing {len(research_steps)} research steps "
                            f"to parallel execution (MindSearch mode)"
                        )
                        try:
                            async for event in self._execute_parallel_research_steps(research_steps, trace_ctx):
                                await self._check_cancelled()
                                yield event
                        except Exception as e:
                            logger.warning(
                                f"Parallel research failed, falling back to sequential: {e}",
                                exc_info=True,
                            )
                            # Reset steps so they can be picked up by the normal loop
                            for step in research_steps:
                                if step.status != ExecutionStatus.COMPLETED:
                                    step.status = ExecutionStatus.PENDING
                                    step.success = False
                                    step.result = None
                                    step.error = None
                        # === END PARALLEL RESEARCH ===
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
                    with trace_ctx.span("summarizing", "agent_step") as summary_span:
                        async for event in self.executor.summarize(response_policy=self._response_policy):
                            await self._check_cancelled()
                            if isinstance(event, ErrorEvent):
                                logger.warning(f"Agent {self._agent_id} summarization failed: {event.error}")
                                yield event
                                # Bridge ErrorEvent → ErrorContext so handle_error_state() can recover.
                                # ErrorEvents bypass state_context's except block (they aren't Exceptions),
                                # so we must populate _error_context manually.
                                self._error_context = ErrorContext(
                                    error_type=ErrorType.TOOL_EXECUTION,
                                    message=f"Summarization failed: {event.error}",
                                    recoverable=True,
                                    recovery_strategy="Retry summarization with relaxed coverage requirements",
                                )
                                self._previous_status = AgentStatus.SUMMARIZING
                                self._transition_to(AgentStatus.ERROR, force=True, reason="summarization failed")
                                break

                            if isinstance(event, (ReportEvent, MessageEvent)):
                                content = event.content if isinstance(event, ReportEvent) else event.message
                                content = content or ""

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

                    # Cross-session learning: persist error patterns at session end
                    if self._memory_service:
                        try:
                            await self._error_bridge.on_session_end(self._memory_service)
                        except Exception as e:
                            logger.debug(f"Error pattern persistence failed (non-critical): {e}")

                    self._transition_to(AgentStatus.IDLE)
                    break

            except Exception as e:
                # Classify and handle error with tracing
                self._error_context = self._error_handler.classify_error(e)
                self._previous_status = self.status
                self._transition_to(AgentStatus.ERROR, force=True, reason="exception handler")

                if isinstance(e, LLMKeysExhaustedError):
                    logger.debug("Agent %s: API keys exhausted — failing fast", self._agent_id)
                else:
                    logger.error(f"Agent {self._agent_id} encountered error: {e}")

                # Add error span with health assessment
                with trace_ctx.span("error", "error_recovery") as error_span:
                    error_span.set_attribute("error.type", str(self._error_context.error_type))
                    error_span.set_attribute("error.recoverable", self._error_context.recoverable)
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

                # If not recoverable, yield error and exit
                if not self._error_context.recoverable:
                    yield ErrorEvent(error=f"Unrecoverable error: {self._error_context.message}")
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
