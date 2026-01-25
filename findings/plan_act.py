import logging
import asyncio
import re
from contextlib import asynccontextmanager
from app.domain.services.flows.base import BaseFlow
from app.domain.models.agent import Agent
from app.domain.models.message import Message
from app.domain.models.plan import Step
from typing import AsyncGenerator, Optional, List, Dict, Any, Set
from enum import Enum
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    MessageEvent,
    DoneEvent,
    TitleEvent,
    IdleEvent,
    ErrorEvent,
    VerificationEvent,
    VerificationStatus,
    ToolEvent,
)
from app.domain.models.plan import ExecutionStatus
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.base import BaseAgent
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.external.file import FileStorage
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser
from app.domain.repositories.session_repository import SessionRepository
from app.domain.models.session import SessionStatus
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.file import FileTool

# BrowserAgentTool is optional (requires browser_use package)
try:
    from app.domain.services.tools.browser_agent import BrowserAgentTool, BROWSER_USE_AVAILABLE
except ImportError:
    BrowserAgentTool = None
    BROWSER_USE_AVAILABLE = False
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.agents.error_handler import ErrorHandler, ErrorType, ErrorContext
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.models.agent_response import VerificationVerdict
from app.core.config import get_settings
from app.infrastructure.observability import get_tracer, SpanKind

# Import orchestration components for multi-agent dispatch
from app.domain.services.orchestration.agent_types import (
    AgentType,
    AgentCapability,
    AgentRegistry,
    get_agent_registry,
)
from app.domain.services.orchestration.agent_factory import (
    DefaultAgentFactory,
    SpecializedAgentFactory,
)

# Import memory management for Phase 3 proactive compaction
from app.domain.services.agents.memory_manager import (
    MemoryManager,
    get_memory_manager,
    PressureLevel,
)

# Import error integration bridge for coordinated health assessment
from app.domain.services.agents.error_integration import (
    ErrorIntegrationBridge,
    AgentHealthLevel,
    IterationGuidance,
)

# Import parallel executor for Phase 4
from app.domain.services.flows.parallel_executor import (
    ParallelExecutor,
    ParallelExecutionMode,
    StepResult,
)

# Import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    VERIFYING = "verifying"  # Phase 1: Plan-Verify-Execute
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    UPDATING = "updating"
    REFLECTING = "reflecting"  # Phase 2: Enhanced Self-Reflection
    ERROR = "error"

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
        search_engine: Optional[SearchEngine] = None,
        cdp_url: Optional[str] = None,
        enable_verification: bool = True,
        enable_multi_agent: bool = False,
        enable_parallel_execution: bool = False,
        parallel_max_concurrency: int = 3,
        memory_service: Optional["MemoryService"] = None,
        user_id: Optional[str] = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self.status = AgentStatus.IDLE
        self.plan = None

        # Store references for multi-agent factory initialization
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._json_parser = json_parser
        self._mcp_tool = mcp_tool
        self._search_engine = search_engine

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service
        self._user_id = user_id

        # State management for error recovery
        self._previous_status: Optional[AgentStatus] = None
        self._error_context: Optional[ErrorContext] = None
        self._error_handler = ErrorHandler()
        self._max_error_recovery_attempts = 3
        self._error_recovery_attempts = 0

        # Verification state (Phase 1: Plan-Verify-Execute)
        self._verification_verdict: Optional[str] = None
        self._verification_feedback: Optional[str] = None
        self._verification_loops = 0
        self._max_verification_loops = 2

        tools = [
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            MessageTool(),
            IdleTool(),
            mcp_tool
        ]

        # Only add search tool when search_engine is not None
        if search_engine:
            tools.append(SearchTool(search_engine))

        # Add browser agent tool when cdp_url is available, enabled, and browser_use is installed
        settings = get_settings()
        if cdp_url and settings.browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
            try:
                tools.append(BrowserAgentTool(cdp_url))
                logger.info(f"Browser agent tool enabled for Agent {agent_id}")
            except ImportError as e:
                logger.warning(f"Browser agent tool not available: {e}")

        # Create planner and execution agents
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            memory_service=memory_service,
            user_id=user_id,
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
        )
        logger.debug(f"Created execution agent for Agent {self._agent_id}")

        # Create verifier agent (Phase 1: Plan-Verify-Execute)
        self.verifier: Optional[VerifierAgent] = None
        if enable_verification:
            self.verifier = VerifierAgent(
                llm=llm,
                json_parser=json_parser,
                tools=tools,
                config=VerifierConfig(
                    enabled=True,
                    skip_simple_plans=True,
                    simple_plan_max_steps=2,
                    max_revision_loops=2,
                )
            )
            logger.info(f"VerifierAgent enabled for Agent {agent_id}")

        # Track background tasks for cleanup
        self._background_tasks: set = set()

        # Task state manager for todo recitation
        self._task_state_manager = TaskStateManager(sandbox)

        # Multi-agent dispatch configuration
        self._enable_multi_agent = enable_multi_agent
        self._agent_registry: Optional[AgentRegistry] = None

        # Phase 4: Parallel step execution configuration
        self._enable_parallel_execution = enable_parallel_execution
        self._parallel_executor: Optional[ParallelExecutor] = None
        if enable_parallel_execution:
            self._parallel_executor = ParallelExecutor(
                max_concurrency=parallel_max_concurrency,
                mode=ParallelExecutionMode.PARALLEL,
            )
            logger.info(f"Parallel step execution enabled with max_concurrency={parallel_max_concurrency}")
        self._agent_factory: Optional[DefaultAgentFactory] = None
        self._specialized_agents: Dict[str, BaseAgent] = {}

        if enable_multi_agent:
            self._init_multi_agent_dispatch()

        # Phase 3: Proactive memory compaction tracking
        self._memory_manager = get_memory_manager()
        self._iteration_count = 0
        self._recent_tools: List[str] = []
        self._max_recent_tools = 10

        # Error Integration Bridge for coordinated health assessment
        self._error_bridge = ErrorIntegrationBridge(
            error_handler=self._error_handler,
            memory_manager=self._memory_manager,
        )

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

    def _extract_agent_type(self, step_description: str) -> Optional[str]:
        """Extract [AGENT_TYPE] prefix from step description.

        Example: "[RESEARCH] Find documentation on the topic" -> "research"
        """
        match = re.search(r"\[([A-Z_]+)\]", step_description)
        if match:
            return match.group(1).lower()
        return None

    def _infer_capabilities(self, step: Step) -> Set[AgentCapability]:
        """Infer required capabilities from step description."""
        capabilities: Set[AgentCapability] = set()
        desc_lower = step.description.lower()

        # Map keywords to capabilities
        capability_keywords = {
            AgentCapability.WEB_BROWSING: [
                "browse", "website", "page", "click", "navigate", "visit"
            ],
            AgentCapability.WEB_SEARCH: [
                "search", "find", "lookup", "query", "google"
            ],
            AgentCapability.CODE_WRITING: [
                "code", "implement", "write", "function", "class", "script", "program"
            ],
            AgentCapability.CODE_REVIEW: [
                "review", "check", "audit", "verify code", "find bugs"
            ],
            AgentCapability.FILE_OPERATIONS: [
                "file", "read", "write", "save", "create file", "modify"
            ],
            AgentCapability.SHELL_COMMANDS: [
                "run", "execute", "shell", "command", "terminal", "bash"
            ],
            AgentCapability.RESEARCH: [
                "research", "investigate", "study", "analyze", "gather"
            ],
            AgentCapability.SUMMARIZATION: [
                "summarize", "summary", "brief", "overview", "condense"
            ],
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
        """Schedule memory compaction as a non-blocking background task.

        Uses Phase 3 proactive compaction triggers to determine if compaction
        is needed before actually performing it.

        Args:
            force: Force compaction regardless of trigger rules
            reason: Reason for forced compaction (logged)
        """
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
(Content truncated due to size limit. Use line ranges to read remaining content)