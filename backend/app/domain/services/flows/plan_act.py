import asyncio
import logging
import os
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.logging import get_agent_logger
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
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
    WideResearchEvent,
    WideResearchStatus,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Step
from app.domain.models.session import SessionStatus
from app.domain.models.state_model import AgentStatus, StateTransitionError, validate_transition
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.fast_path import FastPathRouter, QueryIntent

# Import research task detection for acknowledgment messages
from app.domain.services.prompts.research import is_research_task
from app.domain.services.tools.browser import BrowserTool
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
# Import for type hints
from typing import TYPE_CHECKING

from app.core.alert_manager import get_alert_manager
from app.core.config import get_feature_flags, get_settings
from app.domain.external.observability import get_metrics, get_tracer
from app.domain.services.agents.compliance_gates import ComplianceReport, get_compliance_gates
from app.domain.services.agents.error_handler import ErrorContext, ErrorHandler

# Import error integration bridge for coordinated health assessment
from app.domain.services.agents.error_integration import (
    AgentHealthLevel,
    ErrorIntegrationBridge,
)

# Import memory management for Phase 3 proactive compaction
from app.domain.services.agents.memory_manager import (
    get_memory_manager,
)
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig

# Import parallel executor for Phase 4
from app.domain.services.flows.parallel_executor import (
    ParallelExecutionMode,
    ParallelExecutor,
)
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
from app.domain.services.tools.idle import IdleTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.skill_creator import get_skill_creator_tools
from app.domain.services.tools.skill_invoke import create_skill_invoke_tool
from app.domain.services.validation.plan_validator import PlanValidator

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
        search_engine: SearchEngine | None = None,
        cdp_url: str | None = None,
        enable_verification: bool = True,
        enable_multi_agent: bool = True,
        enable_parallel_execution: bool = False,
        parallel_max_concurrency: int = 3,
        memory_service: Optional["MemoryService"] = None,
        user_id: str | None = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._log = get_agent_logger(agent_id, session_id)
        self.status = AgentStatus.IDLE
        self.plan = None

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

        # State management for error recovery
        self._previous_status: AgentStatus | None = None
        self._error_context: ErrorContext | None = None
        self._error_handler = ErrorHandler()
        self._max_error_recovery_attempts = 3
        self._error_recovery_attempts = 0

        # Verification state (Phase 1: Plan-Verify-Execute)
        self._verification_verdict: str | None = None
        self._verification_feedback: str | None = None
        self._verification_loops = 0
        self._max_verification_loops = 1  # Reduced from 2 to 1 for faster response

        tools = [
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            CodeExecutorTool(sandbox=sandbox, session_id=session_id),
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
        settings = get_settings()
        if cdp_url and settings.browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
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
        self.verifier: VerifierAgent | None = None
        if enable_verification:
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

        # Phase 4: Parallel step execution configuration
        self._enable_parallel_execution = enable_parallel_execution
        self._parallel_executor: ParallelExecutor | None = None
        if enable_parallel_execution:
            self._parallel_executor = ParallelExecutor(
                max_concurrency=parallel_max_concurrency,
                mode=ParallelExecutionMode.PARALLEL,
            )
            logger.info(f"Parallel step execution enabled with max_concurrency={parallel_max_concurrency}")
        self._agent_factory: DefaultAgentFactory | None = None
        self._specialized_agents: dict[str, BaseAgent] = {}

        if enable_multi_agent:
            self._init_multi_agent_dispatch()

        # Phase 3: Proactive memory compaction tracking
        self._memory_manager = get_memory_manager()
        self._iteration_count = 0
        self._recent_tools: list[str] = []
        self._max_recent_tools = 10

        # Cache complexity score for skip-update optimization
        self._cached_complexity: float | None = None

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
        now = datetime.now()
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
                    flags = get_feature_flags()

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
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _track_tool_usage(self, tool_name: str) -> None:
        """Track recent tool usage for proactive compaction decisions."""
        self._recent_tools.append(tool_name)
        if len(self._recent_tools) > self._max_recent_tools:
            self._recent_tools = self._recent_tools[-self._max_recent_tools :]

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
        self._log.workflow_transition(
            from_state=old_status.value,
            to_state=new_status.value,
            reason=reason,
        )

    def _generate_acknowledgment(self, user_message: str) -> str:
        """Generate an acknowledgment message before starting to plan.

        Args:
            user_message: The user's original message

        Returns:
            A brief acknowledgment message describing what will be done
        """
        message_lower = user_message.lower()

        # Skill creation acknowledgment
        if "/skill-creator" in message_lower:
            if message_lower.strip().startswith("/skill-creator"):
                command_match = re.match(r"^\s*/skill-creator(?:\s+(.*))?$", user_message, flags=re.IGNORECASE)
                if command_match:
                    skill_name = (command_match.group(1) or "").strip().strip('"')
                    if skill_name:
                        return f'I\'ll help you create the "{skill_name}" skill. Let me first review the skill creation guidelines.'
            # Try to extract a quoted skill name for a more natural response
            match = re.search(r'"([^"]+)"', user_message)
            if match and match.group(1).strip():
                return f'I\'ll help you create the "{match.group(1).strip()}" skill. Let me first review the skill creation guidelines.'
            return "I'll help you create that skill. Let me first review the skill creation guidelines."

        # Check for research-type tasks
        if is_research_task(user_message):
            # Extract the actual research topic from the user's message
            topic = self._extract_research_topic(user_message)
            if topic:
                # Truncate long topics for the acknowledgment
                display_topic = topic[:100] + "..." if len(topic) > 100 else topic
                return f"I'll research {display_topic} and provide you with a detailed report."
            return "I'll conduct comprehensive research on this topic and provide you with a detailed report."

        # Check for specific task types and generate appropriate acknowledgments
        if any(word in message_lower for word in ["create", "build", "make", "generate", "write"]):
            return "I'll help you with that. Let me create a plan and get started."

        if any(word in message_lower for word in ["fix", "debug", "solve", "resolve"]):
            return "I'll analyze the issue and work on a solution."

        if any(word in message_lower for word in ["find", "search", "look for", "locate"]):
            return "I'll search for that information."

        if any(word in message_lower for word in ["explain", "how does", "what is", "why"]):
            return "Let me look into that for you."

        if any(word in message_lower for word in ["update", "modify", "change", "edit"]):
            return "I'll work on making those changes."

        if any(word in message_lower for word in ["install", "setup", "configure"]):
            return "I'll help you set that up."

        if any(word in message_lower for word in ["test", "check", "verify", "validate"]):
            return "I'll run some checks on that."

        # Default acknowledgment
        return "I'll help you with that. Let me work on it."

    def _extract_research_topic(self, user_message: str) -> str | None:
        """Extract the research topic from the user's message.

        Args:
            user_message: The user's original message

        Returns:
            The extracted topic or None if not found
        """
        message_lower = user_message.lower()

        # Patterns to extract topic after common research request phrases
        # Order matters - more specific patterns first
        topic_patterns = [
            # "research report on: X" or "research report about X"
            r"research\s+report\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            # "comprehensive research on X"
            r"comprehensive\s+research\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            # "research on: X" or "research about X"
            r"research\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            # "research X" (without on/about)
            r"(?:^|\s)research[:\s]+(.+?)(?:\.|$)",
            # "investigate X"
            r"investigate[:\s]+(.+?)(?:\.|$)",
            # "find information on/about X"
            r"find\s+(?:information|info|details)\s+(?:on|about)[:\s]+(.+?)(?:\.|$)",
            # "look into X"
            r"look\s+into[:\s]+(.+?)(?:\.|$)",
            # "analyze X"
            r"analyze[:\s]+(.+?)(?:\.|$)",
            # "study X"
            r"study[:\s]+(.+?)(?:\.|$)",
        ]

        for pattern in topic_patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                topic = match.group(1).strip()
                # Clean up the topic
                topic = re.sub(r"\s+", " ", topic)  # Normalize whitespace
                # Strip leading conjunctions from compound verbs (e.g. "research and compare X" → "X")
                topic = re.sub(
                    r"^(?:and|or)\s+(?:compare|analyze|evaluate|assess|examine|study|review|summarize|investigate)\s+",
                    "",
                    topic,
                    flags=re.IGNORECASE,
                )
                # Remove trailing phrases like "and provide", "then create", etc.
                topic = re.sub(
                    r"\s+(?:and\s+(?:provide|create|give|send)|then\s+\w+).*$", "", topic, flags=re.IGNORECASE
                )
                if topic and len(topic) > 3:  # Avoid very short/empty topics
                    return topic

        # Fallback: Try to extract after "Create a ... report on:"
        report_match = re.search(
            r"create\s+(?:a\s+)?(?:\w+\s+)*report\s+(?:on|about)[:\s]+(.+?)(?:\.|$)", message_lower
        )
        if report_match:
            topic = report_match.group(1).strip()
            topic = re.sub(r"\s+", " ", topic)
            if topic and len(topic) > 3:
                return topic

        # Last fallback: If message starts with a research indicator, take the rest as topic
        if message_lower.startswith(("research ", "investigate ", "analyze ")):
            parts = user_message.split(" ", 1)
            if len(parts) > 1:
                topic = parts[1].strip()
                # Remove leading "on:" or "about:" if present
                topic = re.sub(r"^(?:on|about)[:\s]+", "", topic, flags=re.IGNORECASE)
                if topic and len(topic) > 3:
                    return topic[:150]  # Limit length

        return None

    async def _execute_deep_research(
        self, topic: str, original_message: str, trace_ctx
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute deep research using the wide_research tool.

        This method is called when the user enables Deep Research mode.
        It calls the wide_research tool for parallel multi-source search.

        Args:
            topic: The research topic extracted from the user's message
            original_message: The original user message for context
            trace_ctx: The trace context for observability

        Yields:
            BaseEvent: Events from the wide_research tool execution
        """
        from uuid import uuid4

        logger.info(f"Executing deep research on topic: {topic}")

        # Generate queries from the topic
        queries = self._generate_research_queries(topic)
        search_types = ["info", "news"]
        research_id = str(uuid4())[:12]

        # Emit PENDING WideResearchEvent at start
        yield WideResearchEvent(
            research_id=research_id,
            topic=topic,
            status=WideResearchStatus.PENDING,
            total_queries=len(queries) * len(search_types),
            completed_queries=0,
            sources_found=0,
            search_types=search_types,
        )

        # Emit tool calling event for wide_research
        tool_call_id = str(uuid4())
        function_args = {
            "topic": topic,
            "queries": queries,
            "search_types": search_types,
            "aggregation": "synthesize",
        }

        # Emit calling event
        yield ToolEvent(
            tool_call_id=tool_call_id,
            tool_name="wide_research",
            function_name="wide_research",
            function_args=function_args,
            status=ToolStatus.CALLING,
        )

        # Emit SEARCHING WideResearchEvent
        yield WideResearchEvent(
            research_id=research_id,
            topic=topic,
            status=WideResearchStatus.SEARCHING,
            total_queries=len(queries) * len(search_types),
            completed_queries=0,
            sources_found=0,
            search_types=search_types,
            current_query=queries[0] if queries else None,
        )

        try:
            # Execute wide_research through the search tool
            if self._search_tool:
                result = await self._search_tool.wide_research(
                    topic=topic,
                    queries=queries,
                    search_types=search_types,
                )

                # Emit AGGREGATING WideResearchEvent
                # result.data is a SearchResults Pydantic model, not a dict
                if result and result.data:
                    sources_found = getattr(result.data, "total_results", 0)
                    result_dict = result.data.model_dump() if hasattr(result.data, "model_dump") else {}
                else:
                    sources_found = 0
                    result_dict = {}
                yield WideResearchEvent(
                    research_id=research_id,
                    topic=topic,
                    status=WideResearchStatus.AGGREGATING,
                    total_queries=len(queries) * len(search_types),
                    completed_queries=len(queries) * len(search_types),
                    sources_found=sources_found,
                    search_types=search_types,
                )

                # Emit called event with results
                yield ToolEvent(
                    tool_call_id=tool_call_id,
                    tool_name="wide_research",
                    function_name="wide_research",
                    function_args=function_args,
                    function_result=result_dict,
                    status=ToolStatus.CALLED,
                )

                # Emit report event with synthesized content
                if result and result.success and result.data:
                    # result.message contains the formatted research summary
                    content = result.message or ""

                    # Create a report from the research
                    report_id = str(uuid4())
                    yield ReportEvent(
                        id=report_id,
                        title=f"Research: {topic}",
                        content=content,
                        attachments=[],
                    )

                    # Emit COMPLETED WideResearchEvent
                    yield WideResearchEvent(
                        research_id=research_id,
                        topic=topic,
                        status=WideResearchStatus.COMPLETED,
                        total_queries=len(queries) * len(search_types),
                        completed_queries=len(queries) * len(search_types),
                        sources_found=sources_found,
                        search_types=search_types,
                    )

                    # Emit done event
                    yield DoneEvent()
                else:
                    # Research failed or no results
                    error_msg = result.message if result else "No search tool available"

                    # Emit FAILED WideResearchEvent
                    yield WideResearchEvent(
                        research_id=research_id,
                        topic=topic,
                        status=WideResearchStatus.FAILED,
                        total_queries=len(queries) * len(search_types),
                        completed_queries=len(queries) * len(search_types),
                        sources_found=0,
                        search_types=search_types,
                        errors=[error_msg],
                    )

                    yield MessageEvent(message=f"I was unable to complete the deep research: {error_msg}")
                    yield DoneEvent()
            else:
                # Emit FAILED WideResearchEvent for missing search tool
                yield WideResearchEvent(
                    research_id=research_id,
                    topic=topic,
                    status=WideResearchStatus.FAILED,
                    total_queries=len(queries) * len(search_types),
                    completed_queries=0,
                    sources_found=0,
                    search_types=search_types,
                    errors=["Search capabilities are not available"],
                )

                yield MessageEvent(message="Search capabilities are not available for deep research.")
                yield DoneEvent()

        except Exception as e:
            logger.error(f"Deep research failed: {e}")

            # Emit FAILED WideResearchEvent on exception
            yield WideResearchEvent(
                research_id=research_id,
                topic=topic,
                status=WideResearchStatus.FAILED,
                total_queries=len(queries) * len(search_types),
                completed_queries=0,
                sources_found=0,
                search_types=search_types,
                errors=[str(e)],
            )

            yield ToolEvent(
                tool_call_id=tool_call_id,
                tool_name="wide_research",
                function_name="wide_research",
                function_args=function_args,
                function_result={"error": str(e)},
                status=ToolStatus.CALLED,
            )
            yield ErrorEvent(error=f"Deep research failed: {e}")
            yield DoneEvent()

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
        import datetime

        current_year = datetime.datetime.now().year
        if str(current_year) not in topic and str(current_year - 1) not in topic:
            queries.append(f"{topic} {current_year}")

        return queries[:5]  # Limit to 5 queries

    def _validate_plan_before_execution(self) -> bool:
        """Validate plan before execution; returns True if safe to proceed."""
        if not self.plan:
            logger.warning("No plan available for validation")
            return False

        flags = get_feature_flags()
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

    def _background_save_task_state(self, force: bool = False) -> None:
        """Schedule task state save as a non-blocking background task with debouncing.

        Args:
            force: Force save regardless of debounce timer
        """
        # Debounce check (skip if saved recently, unless forced)
        now = datetime.now()
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
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _handle_step_failure(self, failed_step: Step) -> list[str]:
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
        return self.plan.mark_blocked_cascade(
            blocked_step_id=failed_step.id,
            reason=reason[:200],  # Limit reason length
        )

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
                1 for s in self.plan.steps if s.status == ExecutionStatus.COMPLETED and s.id != step.id
            )
            if completed_count > 0:
                # Could potentially skip - but be conservative
                return False, ""

        return False, ""

    def _check_and_skip_steps(self) -> list[str]:
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

        # Read-only action patterns
        read_only_patterns = [
            "read",
            "view",
            "list",
            "search",
            "find",
            "check",
            "verify",
            "inspect",
            "examine",
            "analyze",
            "review",
            "look",
            "browse",
            "fetch",
            "get",
            "retrieve",
            "show",
            "display",
            "print",
            "understand",
            "learn",
            "research",
            "investigate",
            "explore",
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
        # Always skip for last step or near completion
        if remaining_steps <= 1:
            return True, f"last step or near completion ({remaining_steps} remaining)"

        # Skip if step failed (will trigger replanning anyway)
        if not step.success:
            return True, "step failed"

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
        if self._is_read_only_step(step):
            return True, "read-only step"

        # Skip if we have few remaining steps (< 3) - plan is nearly complete
        if remaining_steps <= 2:
            return True, f"few steps remaining ({remaining_steps})"

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

        if self._error_recovery_attempts >= self._max_error_recovery_attempts:
            logger.error(f"Max recovery attempts ({self._max_error_recovery_attempts}) reached")
            return False

        self._error_recovery_attempts += 1
        logger.info(f"Attempting error recovery ({self._error_recovery_attempts}/{self._max_error_recovery_attempts})")

        # Try to recover based on error type - restore previous status if recoverable
        if self._error_context.recoverable and self._previous_status:
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
            attributes={"message.preview": message.message[:100]},
        ) as trace_ctx:
            async for event in self._run_with_trace(message, trace_ctx):
                yield event

    async def _run_with_trace(self, message: Message, trace_ctx) -> AsyncGenerator[BaseEvent, None]:
        """Internal run method with tracing."""
        # TODO: move to task runner
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise ValueError(f"Session {self._session_id} not found")

        # Phase 3.5: Initialize skill_invoke tool with available skills (lazy load)
        await self._init_skill_invoke_tool()

        # === INSTANT ACKNOWLEDGMENT: Emit before any processing ===
        # This gives users immediate feedback that their message was received
        if session.status not in (SessionStatus.WAITING, SessionStatus.RUNNING):
            # Emit text acknowledgment
            acknowledgment = self._generate_acknowledgment(message.message)
            yield MessageEvent(message=acknowledgment)
            logger.info(f"Emitted acknowledgment for session {self._session_id}")

            # Emit analyzing progress event
            yield ProgressEvent(
                phase=PlanningPhase.ANALYZING,
                message="Analyzing your request...",
                progress_percent=15,
            )

        # === FAST PATH: Check if this is a simple query that can skip planning ===
        # For PENDING or COMPLETED sessions (not INITIALIZING where browser may not be ready)
        # COMPLETED sessions can still receive new messages and should use fast path for greetings/simple queries
        logger.info(f"Fast path check: session.status={session.status}, message={message.message[:50]}")
        if session.status in (SessionStatus.PENDING, SessionStatus.COMPLETED):
            try:
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

                if intent == QueryIntent.GREETING:
                    # Greetings don't need browser or tools - always use fast path
                    use_fast_path = True
                elif intent == QueryIntent.KNOWLEDGE:
                    # Knowledge queries don't need browser - always safe
                    use_fast_path = True
                elif intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH):
                    # Browser queries need verified browser readiness (Phase 2)
                    browser_ready = await self._verify_browser_ready(session)
                    if browser_ready:
                        use_fast_path = True
                    else:
                        skip_reason = "browser not ready"
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
                elif intent in (QueryIntent.DIRECT_BROWSE, QueryIntent.WEB_SEARCH):
                    logger.info(f"Fast path skipped for {intent.value} - {skip_reason}, using normal workflow")
                else:
                    logger.debug("Query classified as TASK, proceeding with full workflow")
            except Exception as e:
                logger.exception(f"Fast path analysis failed: {e}")
                yield ErrorEvent(error=f"Failed to analyze request: {str(e)[:200]}")
                # Continue with normal workflow instead of failing completely
        elif session.status == SessionStatus.INITIALIZING:
            logger.debug("Session still INITIALIZING, skipping fast path check")

        # === END FAST PATH ===

        # Assess task complexity and set dynamic iteration limits (Phase 3)
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

        logger.info(f"Agent {self._agent_id} started processing message: {message.message[:50]}...")

        # NOTE: Acknowledgment moved earlier (before fast path) for instant feedback

        # Emit a skill loading tool event for /skill-creator commands
        skill_command = self._extract_skill_creator_command(message.message)
        if skill_command:
            async for event in self._emit_skill_invoke_events(*skill_command):
                yield event

        # === DEEP RESEARCH MODE ===
        # When deep_research is True, directly execute wide_research tool
        # This provides parallel multi-source search capabilities
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
                    logger.info(f"Agent {self._agent_id} started creating plan")
                    with trace_ctx.span("planning", "plan_create") as plan_span:
                        # Pass replan context if we're replanning after verification
                        replan_context = self._verification_feedback if self._verification_verdict == "revise" else None
                        async for event in self.planner.create_plan(message, replan_context=replan_context):
                            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                                self.plan = event.plan

                                # Infer smart dependencies for BLOCKED cascade and parallel execution
                                self.plan.infer_smart_dependencies(use_sequential_fallback=True)

                                plan_span.set_attribute("plan.steps", len(event.plan.steps))
                                plan_span.set_attribute("plan.title", event.plan.title)
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
                    logger.info(f"Agent {self._agent_id} started verifying plan")
                    with trace_ctx.span("verifying", "agent_step") as verify_span:
                        async for event in self.verifier.verify_plan(
                            plan=self.plan, user_request=message.message, task_context=""
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
                                f"Agent {self._agent_id} max verification loops reached, proceeding with execution"
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
                        logger.info(
                            f"Agent {self._agent_id} has no more steps, state changed from {AgentStatus.EXECUTING} to {AgentStatus.COMPLETED}"
                        )
                        self._transition_to(AgentStatus.SUMMARIZING)
                        continue

                    # Check if step should be skipped (blocked by previous failures)
                    if step.status == ExecutionStatus.BLOCKED:
                        logger.info(f"Skipping blocked step {step.id}: {step.notes or 'blocked by dependency'}")
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
                        "agent_step",
                        {"step.id": step.id, "step.description": step.description[:100]},
                    ) as step_span:
                        # Mark step as in progress BEFORE execution starts
                        # This fixes "0/4" stall by updating progress immediately
                        step.status = ExecutionStatus.RUNNING
                        self._task_state_manager.update_step_status(str(step.id), "in_progress")

                        # Emit PlanEvent so frontend sees updated progress immediately
                        yield PlanEvent(status=PlanStatus.UPDATED, plan=self.plan)

                        # Select appropriate executor for this step (multi-agent dispatch)
                        step_executor = await self._get_executor_for_step(step)
                        if step_executor != self.executor:
                            step_span.set_attribute(
                                "step.executor",
                                step_executor.name if hasattr(step_executor, "name") else type(step_executor).__name__,
                            )
                            logger.info(f"Using specialized executor for step {step.id}")

                        # Phase 4 P1: Mark step executing to prevent compaction
                        if hasattr(step_executor, "_token_manager"):
                            step_executor._token_manager.mark_step_executing()

                        async for event in step_executor.execute_step(self.plan, step, message):
                            # Phase 3: Track tool usage for proactive compaction
                            if isinstance(event, ToolEvent) and event.tool_name:
                                self._track_tool_usage(event.tool_name)
                            yield event

                            # Yield any pending events from skill creator tools (Phase 3: Custom Skills)
                            while self._pending_events:
                                pending_event = self._pending_events.pop(0)
                                logger.info(f"Yielding pending event: {type(pending_event).__name__}")
                                yield pending_event

                        # Phase 4 P1: Mark step completed to allow compaction
                        if hasattr(step_executor, "_token_manager"):
                            step_executor._token_manager.mark_step_completed()

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

                    # Check if we can skip plan update phase for faster response
                    # Skipping saves 2-5 seconds by avoiding an LLM call
                    flags = get_feature_flags()
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
                            await get_alert_manager().check_thresholds(
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
                    logger.info(f"Agent {self._agent_id} started updating plan")
                    with trace_ctx.span("plan-update", "plan_update") as update_span:
                        async for event in self.planner.update_plan(self.plan, step):
                            yield event
                        update_span.set_attribute(
                            "plan.remaining_steps", len([s for s in self.plan.steps if not s.is_done()])
                        )
                    logger.info(
                        f"Agent {self._agent_id} plan update completed, state changed from {AgentStatus.UPDATING} to {AgentStatus.EXECUTING}"
                    )
                    if not self._validate_plan_before_execution():
                        logger.info(f"Agent {self._agent_id} plan update failed validation, replanning")
                        self._transition_to(AgentStatus.PLANNING, force=True, reason="plan update validation failed")
                        continue
                    self._transition_to(AgentStatus.EXECUTING)
                elif self.status == AgentStatus.SUMMARIZING:
                    # Conclusion with tracing
                    logger.info(f"Agent {self._agent_id} started summarizing")

                    # Fetch session files to include in the final report
                    session_files: list[FileInfo] = []
                    try:
                        session = await self._session_repository.find_by_id(self._session_id)
                        if session and session.files:
                            session_files = session.files
                            logger.debug(f"Found {len(session_files)} session files to include in report")
                    except Exception as e:
                        logger.warning(f"Failed to fetch session files: {e}")

                    with trace_ctx.span("summarizing", "agent_step") as summary_span:
                        async for event in self.executor.summarize():
                            if isinstance(event, (ReportEvent, MessageEvent)):
                                content = event.content if isinstance(event, ReportEvent) else event.message
                                content = content or ""

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
                    if self.status == AgentStatus.ERROR:
                        continue
                    logger.info(
                        f"Agent {self._agent_id} summarizing completed, state changed from {AgentStatus.SUMMARIZING} to {AgentStatus.COMPLETED}"
                    )
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
