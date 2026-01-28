import logging
import asyncio
import re
from contextlib import asynccontextmanager
from app.domain.services.flows.base import BaseFlow
from app.domain.models.agent import Agent
from app.domain.models.message import Message
from app.domain.models.plan import Step
from typing import AsyncGenerator, Optional, List, Dict, Any, Set
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    MessageEvent,
    ReportEvent,
    DoneEvent,
    TitleEvent,
    IdleEvent,
    ErrorEvent,
    VerificationEvent,
    VerificationStatus,
    ToolEvent,
)
from app.domain.models.plan import ExecutionStatus
from app.domain.models.state_model import AgentStatus, validate_transition, StateTransitionError
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
from app.domain.services.agents.compliance_gates import ComplianceReport, get_compliance_gates
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

# Import complexity assessor for dynamic iteration limits (Phase 3)
from app.domain.services.agents.complexity_assessor import ComplexityAssessor

logger = logging.getLogger(__name__)

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
        enable_multi_agent: bool = True,
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

        # Compliance gates for output quality checks
        self._compliance_gates = get_compliance_gates()

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
                should_compact, trigger_reason = self._memory_manager.should_trigger_compaction(
                    pressure=pressure,
                    recent_tools=self._recent_tools,
                    iteration_count=self._iteration_count
                )

                if force or should_compact:
                    compact_reason = reason if force else trigger_reason
                    logger.info(
                        f"Agent {self._agent_id} triggering memory compaction: {compact_reason} "
                        f"(tokens: {current_tokens}, pressure: {pressure.level.value})"
                    )

                    # Use smart compaction with result extraction
                    messages = self.executor.memory.to_messages()
                    compacted_messages, tokens_saved = self._memory_manager.compact_messages_batch(
                        messages,
                        preserve_recent=10,
                        token_threshold=int(pressure.max_tokens * 0.7)  # Compact when at 70%
                    )

                    if tokens_saved > 0:
                        # Update memory with compacted messages
                        self.executor.memory.messages = compacted_messages
                        await self._repository.save_memory(
                            self._agent_id, self.executor.name, self.executor.memory
                        )
                        logger.info(
                            f"Agent {self._agent_id} compaction saved {tokens_saved} tokens"
                        )
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
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _track_tool_usage(self, tool_name: str) -> None:
        """Track recent tool usage for proactive compaction decisions."""
        self._recent_tools.append(tool_name)
        if len(self._recent_tools) > self._max_recent_tools:
            self._recent_tools = self._recent_tools[-self._max_recent_tools:]

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
        self.status = new_status

    def _validate_plan_before_execution(self) -> bool:
        """Validate plan before execution; returns True if safe to proceed."""
        if not self.plan:
            logger.warning("No plan available for validation")
            return False

        validation = self.plan.validate_plan()
        if not validation.passed:
            error_summary = "; ".join(validation.errors[:3])
            logger.warning(f"Plan validation failed: {error_summary}")
            self._verification_verdict = "revise"
            self._verification_feedback = (
                "Plan validation failed:\n- " + "\n- ".join(validation.errors[:5])
            )
            return False

        if validation.warnings:
            logger.info(
                f"Plan validation warnings: {', '.join(validation.warnings[:3])}"
            )
        return True

    def _run_compliance_gates(self, content: str, attachments: Optional[List[Any]] = None) -> ComplianceReport:
        """Run compliance gates on final output content."""
        artifacts: List[Dict[str, Any]] = []
        for attachment in attachments or []:
            path = getattr(attachment, "file_path", None) or getattr(attachment, "path", None)
            if path:
                artifacts.append({"path": path, "type": "file"})
        return self._compliance_gates.check_all(content, artifacts=artifacts, sources=[])

    def _background_save_task_state(self) -> None:
        """Schedule task state save as a non-blocking background task."""
        async def _save():
            try:
                await self._task_state_manager.save_to_sandbox()
                logger.debug(f"Agent {self._agent_id} task state saved to sandbox")
            except Exception as e:
                logger.warning(f"Agent {self._agent_id} task state save failed: {e}")

        task = asyncio.create_task(_save())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _handle_step_failure(self, failed_step: Step) -> List[str]:
        """Handle step failure by marking dependent steps as blocked.

        Args:
            failed_step: The step that failed

        Returns:
            List of step IDs that were marked as blocked
        """
        if not self.plan:
            return []

        # Get the failure reason
        reason = failed_step.error or failed_step.result or "Step execution failed"

        # Mark dependent steps as blocked using cascade
        blocked_ids = self.plan.mark_blocked_cascade(
            blocked_step_id=failed_step.id,
            reason=reason[:200]  # Limit reason length
        )

        return blocked_ids

    def _should_skip_step(self, step: Step) -> tuple[bool, str]:
        """Check if a step should be skipped.

        Steps can be skipped if:
        - They're marked as optional and a dependency failed
        - The plan already achieved the step's goal through another path
        - The step is redundant based on previous results

        Args:
            step: The step to evaluate

        Returns:
            Tuple of (should_skip, reason)
        """
        if not self.plan:
            return False, ""

        # Check if any dependency is blocked (not failed, but blocked by another failure)
        for dep_id in step.dependencies:
            dep_step = next((s for s in self.plan.steps if s.id == dep_id), None)
            if dep_step and dep_step.status == ExecutionStatus.BLOCKED:
                # This step should also be blocked, not skipped
                return False, ""
            if dep_step and dep_step.status == ExecutionStatus.SKIPPED:
                # If dependency was skipped, this step might be skippable too
                # depending on whether it's truly dependent
                pass

        # Check for optional steps (indicated by description patterns)
        optional_patterns = ["optional", "if needed", "if required", "alternatively"]
        description_lower = step.description.lower()
        is_optional = any(pattern in description_lower for pattern in optional_patterns)

        if is_optional:
            # Check if we already have successful steps that might make this redundant
            completed_count = sum(
                1 for s in self.plan.steps
                if s.status == ExecutionStatus.COMPLETED and s.id != step.id
            )
            if completed_count > 0:
                # Could potentially skip - but be conservative
                return False, ""

        return False, ""

    def _check_and_skip_steps(self) -> List[str]:
        """Check all pending steps and skip those that should be skipped.

        Returns:
            List of step IDs that were skipped
        """
        if not self.plan:
            return []

        skipped_ids = []
        for step in self.plan.steps:
            if step.status == ExecutionStatus.PENDING:
                should_skip, reason = self._should_skip_step(step)
                if should_skip:
                    step.mark_skipped(reason)
                    skipped_ids.append(step.id)
                    logger.info(f"Skipped step {step.id}: {reason}")

        return skipped_ids

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
                    step.mark_blocked(
                        f"Dependency {dep_id} failed",
                        blocked_by=dep_id
                    )
                    return False
                elif dep_step.status in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
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
        logger.debug(f"Agent {self._agent_id} entering state: {new_status}")

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

        if self._error_recovery_attempts >= self._max_error_recovery_attempts:
            logger.error(f"Max recovery attempts ({self._max_error_recovery_attempts}) reached")
            return False

        self._error_recovery_attempts += 1
        logger.info(f"Attempting error recovery ({self._error_recovery_attempts}/{self._max_error_recovery_attempts})")

        # Try to recover based on error type
        if self._error_context.recoverable:
            # Restore previous status
            if self._previous_status:
                self._transition_to(self._previous_status, force=True, reason="error recovery")
                self._previous_status = None
                logger.info(f"Recovered to previous state: {self.status}")
                return True

        return False

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        tracer = get_tracer()

        # Create trace context for this run
        with tracer.trace(
            "agent-run",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]}
        ) as trace_ctx:
            async for event in self._run_with_trace(message, trace_ctx):
                yield event

    async def _run_with_trace(self, message: Message, trace_ctx) -> AsyncGenerator[BaseEvent, None]:
        """Internal run method with tracing."""
        # TODO: move to task runner
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise ValueError(f"Session {self._session_id} not found")

        # Assess task complexity and set dynamic iteration limits (Phase 3)
        if session.complexity_score is None and session.status == SessionStatus.PENDING:
            assessor = ComplexityAssessor()
            assessment = assessor.assess_task_complexity(
                task_description=message.message,
                is_multi_task=session.multi_task_challenge is not None
            )

            # Store complexity score and iteration limit in session
            session.complexity_score = assessment.score
            session.iteration_limit_override = assessment.recommended_iterations

            # Apply iteration limit to executor
            self.executor.max_iterations = assessment.recommended_iterations

            logger.info(
                f"Task complexity: {assessment.category} ({assessment.score:.2f}), "
                f"setting iteration limit to {assessment.recommended_iterations}"
            )

            # Update session with complexity info
            await self._session_repository.update_by_id(
                self._session_id,
                {"complexity_score": assessment.score, "iteration_limit_override": assessment.recommended_iterations}
            )
        elif session.iteration_limit_override:
            # Reuse existing iteration limit override
            self.executor.max_iterations = session.iteration_limit_override
            logger.debug(f"Applying existing iteration limit: {session.iteration_limit_override}")

        if session.status != SessionStatus.PENDING:
            logger.debug(f"Session {self._session_id} is not in PENDING status, rolling back")
            await self.executor.roll_back(message)
            await self.planner.roll_back(message)

        if session.status == SessionStatus.RUNNING:
            logger.debug(f"Session {self._session_id} is in RUNNING status")
            self._transition_to(AgentStatus.PLANNING)

        if session.status == SessionStatus.WAITING:
            logger.debug(f"Session {self._session_id} is in WAITING status")
            self._transition_to(AgentStatus.EXECUTING, force=True, reason="resume waiting session")

        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)
        self.plan = session.get_last_plan()

        logger.info(f"Agent {self._agent_id} started processing message: {message.message[:50]}...")
        step = None
        while True:
            # Phase 3: Track iteration count for proactive compaction
            self._iteration_count += 1

            try:
                # Handle error state with recovery
                if self.status == AgentStatus.ERROR:
                    if await self.handle_error_state():
                        logger.info(f"Agent {self._agent_id} recovered from error state")
                        continue
                    else:
                        # Cannot recover, yield error and exit
                        error_msg = self._error_context.message if self._error_context else "Unknown error"
                        yield ErrorEvent(error=f"Agent failed after recovery attempts: {error_msg}")
                        break

                if self.status == AgentStatus.IDLE:
                    logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.IDLE} to {AgentStatus.PLANNING}")
                    self._transition_to(AgentStatus.PLANNING)
                elif self.status == AgentStatus.PLANNING:
                    # Create plan with tracing
                    logger.info(f"Agent {self._agent_id} started creating plan")
                    with trace_ctx.span("planning", SpanKind.PLAN_CREATE) as plan_span:
                        # Pass replan context if we're replanning after verification
                        replan_context = self._verification_feedback if self._verification_verdict == "revise" else None
                        async for event in self.planner.create_plan(message, replan_context=replan_context):
                            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                                self.plan = event.plan

                                # Infer sequential dependencies for BLOCKED cascade
                                self.plan.infer_sequential_dependencies()

                                plan_span.set_attribute("plan.steps", len(event.plan.steps))
                                plan_span.set_attribute("plan.title", event.plan.title)
                                logger.info(f"Agent {self._agent_id} created plan successfully with {len(event.plan.steps)} steps")

                                # Initialize task state for recitation
                                self._task_state_manager.initialize_from_plan(
                                    objective=message.message,
                                    steps=[{"id": s.id, "description": s.description} for s in event.plan.steps]
                                )

                                yield TitleEvent(title=event.plan.title)
                                # Skip plan.message - execute silently without explaining
                            yield event

                    # Validate plan before proceeding
                    if not self._validate_plan_before_execution():
                        logger.info(f"Agent {self._agent_id} replanning due to validation errors")
                        continue

                    # Reset verification feedback after replanning
                    self._verification_verdict = None
                    self._verification_feedback = None

                    if len(event.plan.steps) == 0:
                        logger.info(f"Agent {self._agent_id} created plan successfully with no steps")
                        self._transition_to(AgentStatus.COMPLETED)
                    elif self.verifier:
                        # Transition to verification if verifier is enabled
                        logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.VERIFYING}")
                        self._transition_to(AgentStatus.VERIFYING)
                    else:
                        logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.EXECUTING}")
                        self._transition_to(AgentStatus.EXECUTING)

                elif self.status == AgentStatus.VERIFYING:
                    # Verify plan before execution (Phase 1: Plan-Verify-Execute)
                    logger.info(f"Agent {self._agent_id} started verifying plan")
                    with trace_ctx.span("verifying", SpanKind.AGENT_STEP) as verify_span:
                        async for event in self.verifier.verify_plan(
                            plan=self.plan,
                            user_request=message.message,
                            task_context=""
                        ):
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
                            logger.info(f"Agent {self._agent_id} plan failed validation after verification")
                            self._transition_to(AgentStatus.PLANNING)
                        else:
                            self._transition_to(AgentStatus.EXECUTING)
                    elif self._verification_verdict == "revise":
                        if self._verification_loops >= self._max_verification_loops:
                            logger.warning(
                                f"Agent {self._agent_id} max verification loops reached, "
                                "proceeding with execution"
                            )
                            if not self._validate_plan_before_execution():
                                logger.info(f"Agent {self._agent_id} plan failed validation after verification")
                                self._transition_to(AgentStatus.PLANNING)
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
                            logger.info(f"Agent {self._agent_id} plan failed validation after verification")
                            self._transition_to(AgentStatus.PLANNING)
                        else:
                            self._transition_to(AgentStatus.EXECUTING)

                elif self.status == AgentStatus.EXECUTING:
                    # Execute plan
                    if not self._validate_plan_before_execution():
                        logger.info(f"Agent {self._agent_id} plan failed validation before execution")
                        self._transition_to(AgentStatus.PLANNING, force=True, reason="plan validation failed")
                        continue
                    self.plan.status = ExecutionStatus.RUNNING
                    step = self.plan.get_next_step()
                    if not step:
                        logger.info(f"Agent {self._agent_id} has no more steps, state changed from {AgentStatus.EXECUTING} to {AgentStatus.COMPLETED}")
                        self._transition_to(AgentStatus.SUMMARIZING)
                        continue

                    # Check if step should be skipped (blocked by previous failures)
                    if step.status == ExecutionStatus.BLOCKED:
                        logger.info(
                            f"Skipping blocked step {step.id}: {step.notes or 'blocked by dependency'}"
                        )
                        self._task_state_manager.update_step_status(str(step.id), "blocked")
                        continue

                    # Check dependencies are satisfied
                    if not self._check_step_dependencies(step):
                        logger.warning(f"Step {step.id} has unsatisfied dependencies, marking as blocked")
                        step.mark_blocked("Unsatisfied dependencies")
                        self._task_state_manager.update_step_status(str(step.id), "blocked")
                        continue

                    # Execute step with tracing
                    logger.info(f"Agent {self._agent_id} started executing step {step.id}: {step.description[:50]}...")

                    with trace_ctx.span(
                        f"step:{step.id}",
                        SpanKind.AGENT_STEP,
                        {"step.id": step.id, "step.description": step.description[:100]}
                    ) as step_span:
                        # Mark step as in progress for task state
                        self._task_state_manager.update_step_status(str(step.id), "in_progress")

                        # Select appropriate executor for this step (multi-agent dispatch)
                        step_executor = await self._get_executor_for_step(step)
                        if step_executor != self.executor:
                            step_span.set_attribute("step.executor", step_executor.name if hasattr(step_executor, 'name') else type(step_executor).__name__)
                            logger.info(f"Using specialized executor for step {step.id}")

                        async for event in step_executor.execute_step(self.plan, step, message):
                            # Phase 3: Track tool usage for proactive compaction
                            if isinstance(event, ToolEvent) and event.tool_name:
                                self._track_tool_usage(event.tool_name)
                            yield event

                        # Mark step status based on actual success/failure
                        if step.success:
                            self._task_state_manager.update_step_status(str(step.id), "completed")
                        else:
                            self._task_state_manager.update_step_status(str(step.id), "failed")
                        step_span.set_attribute("step.success", step.success)

                        # Handle step failure - cascade blocking to dependent steps
                        if not step.success and step.status == ExecutionStatus.FAILED:
                            blocked_step_ids = self._handle_step_failure(step)
                            if blocked_step_ids:
                                step_span.set_attribute("step.blocked_dependents", len(blocked_step_ids))
                                logger.info(
                                    f"Step {step.id} failure blocked {len(blocked_step_ids)} dependent steps: "
                                    f"{blocked_step_ids}"
                                )

                    logger.info(f"Agent {self._agent_id} completed step {step.id}, state changed from {AgentStatus.EXECUTING} to {AgentStatus.UPDATING}")
                    # Non-blocking background memory compaction
                    self._background_compact_memory()
                    # Non-blocking background task state save to sandbox
                    self._background_save_task_state()
                    self._transition_to(AgentStatus.UPDATING)
                elif self.status == AgentStatus.UPDATING:
                    # Update plan with tracing
                    logger.info(f"Agent {self._agent_id} started updating plan")
                    with trace_ctx.span("plan-update", SpanKind.PLAN_UPDATE) as update_span:
                        async for event in self.planner.update_plan(self.plan, step):
                            yield event
                        update_span.set_attribute("plan.remaining_steps", len([s for s in self.plan.steps if not s.is_done()]))
                    logger.info(f"Agent {self._agent_id} plan update completed, state changed from {AgentStatus.UPDATING} to {AgentStatus.EXECUTING}")
                    if not self._validate_plan_before_execution():
                        logger.info(f"Agent {self._agent_id} plan update failed validation, replanning")
                        self._transition_to(AgentStatus.PLANNING, force=True, reason="plan update validation failed")
                        continue
                    self._transition_to(AgentStatus.EXECUTING)
                elif self.status == AgentStatus.SUMMARIZING:
                    # Conclusion with tracing
                    logger.info(f"Agent {self._agent_id} started summarizing")
                    with trace_ctx.span("summarizing", SpanKind.AGENT_STEP) as summary_span:
                        async for event in self.executor.summarize():
                            if isinstance(event, (ReportEvent, MessageEvent)):
                                content = event.content if isinstance(event, ReportEvent) else event.message
                                content = content or ""
                                attachments = event.attachments if hasattr(event, "attachments") else None
                                compliance_report = self._run_compliance_gates(content, attachments)
                                summary_span.set_attribute("compliance.passed", compliance_report.passed)
                                if compliance_report.blocking_issues:
                                    summary_span.set_attribute("compliance.blocking", len(compliance_report.blocking_issues))
                                if not compliance_report.passed:
                                    logger.warning(
                                        "Compliance gates failed: "
                                        + "; ".join(compliance_report.blocking_issues)
                                    )
                                    yield ErrorEvent(
                                        error="Compliance gates failed: "
                                        + "; ".join(compliance_report.blocking_issues)
                                    )
                                    self._transition_to(
                                        AgentStatus.ERROR,
                                        force=True,
                                        reason="compliance gates failed"
                                    )
                                    break
                            yield event
                    if self.status == AgentStatus.ERROR:
                        continue
                    logger.info(f"Agent {self._agent_id} summarizing completed, state changed from {AgentStatus.SUMMARIZING} to {AgentStatus.COMPLETED}")
                    self._transition_to(AgentStatus.COMPLETED)
                elif self.status == AgentStatus.COMPLETED:
                    self.plan.status = ExecutionStatus.COMPLETED
                    logger.info(f"Agent {self._agent_id} plan has been completed")
                    yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)
                    self._transition_to(AgentStatus.IDLE)
                    break

            except Exception as e:
                # Classify and handle error with tracing
                self._error_context = self._error_handler.classify_error(e)
                self._previous_status = self.status
                self._transition_to(AgentStatus.ERROR, force=True, reason="exception handler")
                logger.error(f"Agent {self._agent_id} encountered error: {e}")

                # Add error span with health assessment
                with trace_ctx.span("error", SpanKind.ERROR_RECOVERY) as error_span:
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
                                f"Agent {self._agent_id} health CRITICAL: "
                                f"{', '.join(health.recommended_actions)}"
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
