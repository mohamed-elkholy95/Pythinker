"""Coordinator flow that integrates the swarm with the existing flow system.

Provides a high-level interface for using multi-agent orchestration
that integrates seamlessly with the existing PlanActFlow pattern.
"""

import logging
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any, Set
from enum import Enum
from datetime import datetime

from app.domain.services.flows.base import BaseFlow
from app.domain.services.orchestration.swarm import (
    Swarm,
    SwarmConfig,
    SwarmTask,
    AgentStatus,
)
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
from app.domain.services.orchestration.handoff import (
    HandoffProtocol,
    get_handoff_protocol,
)
from app.domain.models.message import Message
from app.domain.models.event import (
    BaseEvent,
    MessageEvent,
    ErrorEvent,
    DoneEvent,
    PlanEvent,
    PlanStatus,
    TitleEvent,
)
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.utils.json_parser import JsonParser
from app.domain.services.tools.mcp import MCPTool

logger = logging.getLogger(__name__)


class CoordinatorMode(str, Enum):
    """Modes of operation for the coordinator."""
    AUTO = "auto"               # Automatically decide when to use swarm
    SWARM = "swarm"             # Always use swarm for multi-agent
    SINGLE = "single"           # Single agent mode (no swarm)


class TaskComplexity(str, Enum):
    """Complexity levels for task classification."""
    SIMPLE = "simple"           # Single agent can handle
    MODERATE = "moderate"       # May benefit from specialization
    COMPLEX = "complex"         # Requires multi-agent collaboration


class CoordinatorFlow(BaseFlow):
    """High-level flow that orchestrates multi-agent task execution.

    This flow acts as the main entry point for complex tasks that may
    require multiple specialized agents. It:
    1. Analyzes incoming tasks to determine complexity
    2. Delegates to specialized agents via the swarm
    3. Coordinates handoffs between agents
    4. Aggregates and returns results

    Can operate in different modes:
    - AUTO: Analyzes task and decides whether to use swarm
    - SWARM: Always uses multi-agent swarm
    - SINGLE: Falls back to single-agent mode

    Example:
        flow = CoordinatorFlow(
            agent_id="agent-123",
            agent_repository=repo,
            session_id="session-456",
            session_repository=session_repo,
            llm=llm,
            sandbox=sandbox,
            browser=browser,
            json_parser=parser,
            mcp_tool=mcp,
            mode=CoordinatorMode.AUTO,
        )

        async for event in flow.run(message):
            yield event
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
        mode: CoordinatorMode = CoordinatorMode.AUTO,
        swarm_config: Optional[SwarmConfig] = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._json_parser = json_parser
        self._mcp_tool = mcp_tool
        self._search_engine = search_engine
        self._mode = mode

        # Initialize the agent factory
        self._factory = SpecializedAgentFactory(
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            sandbox=sandbox,
            browser=browser,
            search_engine=search_engine,
            mcp_tool=mcp_tool,
        )

        # Initialize the swarm
        self._swarm = Swarm(
            agent_factory=self._factory,
            config=swarm_config or SwarmConfig(),
            registry=get_agent_registry(),
            handoff_protocol=get_handoff_protocol(),
        )

        # Execution state
        self._current_task: Optional[SwarmTask] = None
        self._plan: Optional[Plan] = None
        self._complexity: TaskComplexity = TaskComplexity.SIMPLE

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Execute the coordinator flow.

        Args:
            message: The user's message/request

        Yields:
            Events from task execution
        """
        logger.info(f"CoordinatorFlow starting for session {self._session_id}")

        try:
            # Step 1: Analyze the task
            self._complexity = await self._analyze_task(message)
            logger.info(f"Task complexity: {self._complexity.value}")

            # Step 2: Decide execution strategy
            use_swarm = self._should_use_swarm(message)

            if use_swarm:
                # Multi-agent execution
                async for event in self._execute_with_swarm(message):
                    yield event
            else:
                # Single agent execution (delegate to standard flow)
                async for event in self._execute_single_agent(message):
                    yield event

        except Exception as e:
            logger.error(f"CoordinatorFlow error: {e}")
            yield ErrorEvent(error=f"Execution failed: {str(e)}")

        yield DoneEvent()
        logger.info(f"CoordinatorFlow completed for session {self._session_id}")

    async def _analyze_task(self, message: Message) -> TaskComplexity:
        """Analyze a task to determine its complexity.

        Uses heuristics and optional LLM analysis to classify tasks.

        Args:
            message: The user's message

        Returns:
            TaskComplexity classification
        """
        text = message.message.lower()

        # Simple heuristics for task complexity
        complexity_indicators = {
            TaskComplexity.COMPLEX: [
                "multiple", "several", "comprehensive", "full",
                "analyze and", "research and", "build and",
                "compare", "contrast", "evaluate all",
                "create a complete", "develop a system",
            ],
            TaskComplexity.MODERATE: [
                "research", "investigate", "analyze",
                "write code", "implement", "create",
                "browse", "search for", "find",
            ],
        }

        # Check for complexity indicators
        for complexity, indicators in complexity_indicators.items():
            for indicator in indicators:
                if indicator in text:
                    return complexity

        # Check message length (longer usually means more complex)
        if len(message.message) > 500:
            return TaskComplexity.MODERATE

        # Check for multiple sentences/tasks
        sentence_count = text.count('.') + text.count('?') + text.count('!')
        if sentence_count > 3:
            return TaskComplexity.MODERATE

        return TaskComplexity.SIMPLE

    def _should_use_swarm(self, message: Message) -> bool:
        """Determine whether to use swarm execution.

        Args:
            message: The user's message

        Returns:
            True if swarm should be used
        """
        if self._mode == CoordinatorMode.SWARM:
            return True

        if self._mode == CoordinatorMode.SINGLE:
            return False

        # AUTO mode: decide based on complexity
        return self._complexity in (TaskComplexity.COMPLEX, TaskComplexity.MODERATE)

    async def _execute_with_swarm(
        self,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a task using the multi-agent swarm.

        Args:
            message: The user's message

        Yields:
            Events from swarm execution
        """
        logger.info("Executing with multi-agent swarm")

        # Determine required capabilities
        required_capabilities = self._infer_capabilities(message)

        # Create swarm task
        task = SwarmTask(
            description=message.message,
            original_request=message.message,
            context={
                "session_id": self._session_id,
                "agent_id": self._agent_id,
                "attachments": message.attachments,
            },
            required_capabilities=required_capabilities,
            timeout_seconds=300,
        )

        self._current_task = task

        # Create a plan for visibility
        plan = Plan(
            goal=message.message,
            title=f"Multi-Agent Task: {message.message[:50]}...",
            language="en",
            steps=[
                Step(id="1", description="Analyze task and select specialized agents"),
                Step(id="2", description="Execute task with agent swarm"),
                Step(id="3", description="Aggregate results and summarize"),
            ],
        )
        self._plan = plan

        yield TitleEvent(title=plan.title)
        yield PlanEvent(status=PlanStatus.CREATED, plan=plan)

        # Execute with swarm
        async for event in self._swarm.execute(task):
            yield event

        # Complete the plan
        for step in plan.steps:
            step.status = ExecutionStatus.COMPLETED

        yield PlanEvent(status=PlanStatus.COMPLETED, plan=plan)

    async def _execute_single_agent(
        self,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a task with a single specialized agent.

        For simpler tasks, we bypass the full swarm and use a single agent.

        Args:
            message: The user's message

        Yields:
            Events from agent execution
        """
        logger.info("Executing with single agent")

        # Select the best agent for this task
        registry = get_agent_registry()
        candidates = registry.select_for_task(
            task_description=message.message,
            context={"session_id": self._session_id},
        )

        if not candidates:
            # Fall back to executor
            spec = registry.get(AgentType.EXECUTOR)
        else:
            spec = candidates[0]

        logger.info(f"Selected agent: {spec.agent_type.value}")

        # Create the agent
        agent = await self._factory.create_agent(
            spec.agent_type,
            f"{self._agent_id}_single",
            spec,
        )

        # Execute
        async for event in self._factory.execute_agent(
            agent,
            message.message,
            {"session_id": self._session_id, "attachments": message.attachments},
        ):
            yield event

    def _infer_capabilities(self, message: Message) -> Set[AgentCapability]:
        """Infer required capabilities from the message.

        Args:
            message: The user's message

        Returns:
            Set of inferred capabilities
        """
        text = message.message.lower()
        capabilities: Set[AgentCapability] = set()

        # Capability keyword mapping
        keyword_map = {
            AgentCapability.CODE_WRITING: [
                "code", "implement", "write function", "script", "program",
                "create class", "build", "develop"
            ],
            AgentCapability.CODE_REVIEW: [
                "review", "check code", "find bugs", "audit", "critique"
            ],
            AgentCapability.WEB_BROWSING: [
                "browse", "visit", "navigate", "website", "page", "click"
            ],
            AgentCapability.WEB_SEARCH: [
                "search", "find", "look up", "google", "query"
            ],
            AgentCapability.RESEARCH: [
                "research", "investigate", "study", "learn about", "analyze"
            ],
            AgentCapability.FILE_OPERATIONS: [
                "file", "read", "write", "save", "create file", "modify file"
            ],
            AgentCapability.SHELL_COMMANDS: [
                "run", "execute", "shell", "command", "terminal", "bash"
            ],
            AgentCapability.SUMMARIZATION: [
                "summarize", "summary", "brief", "overview", "condense"
            ],
            AgentCapability.ANALYSIS: [
                "analyze", "examine", "evaluate", "assess", "review"
            ],
        }

        for capability, keywords in keyword_map.items():
            for keyword in keywords:
                if keyword in text:
                    capabilities.add(capability)
                    break

        return capabilities

    def get_swarm_stats(self) -> Dict[str, Any]:
        """Get statistics from the swarm.

        Returns:
            Dictionary of swarm statistics
        """
        return self._swarm.get_stats()

    def is_done(self) -> bool:
        """Check if the flow is complete.

        Returns:
            True if execution is complete
        """
        if self._current_task:
            return self._current_task.status in (
                AgentStatus.COMPLETED,
                AgentStatus.FAILED,
            )
        return True

    async def shutdown(self) -> None:
        """Shutdown the coordinator and swarm.

        Cleans up resources and waits for active tasks.
        """
        await self._swarm.shutdown()


def create_coordinator_flow(
    agent_id: str,
    session_id: str,
    agent_repository: AgentRepository,
    session_repository: SessionRepository,
    llm: LLM,
    sandbox: Sandbox,
    browser: Browser,
    json_parser: JsonParser,
    mcp_tool: MCPTool,
    search_engine: Optional[SearchEngine] = None,
    mode: CoordinatorMode = CoordinatorMode.AUTO,
    **kwargs,
) -> CoordinatorFlow:
    """Factory function for creating CoordinatorFlow instances.

    Provides a convenient way to create properly configured coordinator flows.

    Args:
        agent_id: Unique agent identifier
        session_id: Session identifier
        agent_repository: Repository for agent data
        session_repository: Repository for session data
        llm: LLM instance for agent execution
        sandbox: Sandbox for code execution
        browser: Browser instance for web tasks
        json_parser: JSON parser utility
        mcp_tool: MCP tool for external integrations
        search_engine: Optional search engine
        mode: Coordinator operation mode
        **kwargs: Additional configuration

    Returns:
        Configured CoordinatorFlow instance
    """
    config = SwarmConfig(**kwargs) if kwargs else None

    return CoordinatorFlow(
        agent_id=agent_id,
        agent_repository=agent_repository,
        session_id=session_id,
        session_repository=session_repository,
        llm=llm,
        sandbox=sandbox,
        browser=browser,
        json_parser=json_parser,
        mcp_tool=mcp_tool,
        search_engine=search_engine,
        mode=mode,
        swarm_config=config,
    )
