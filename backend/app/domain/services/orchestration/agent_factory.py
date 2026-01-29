"""Agent factory for creating specialized agent instances in the swarm.

Provides the concrete implementation for creating and executing agents
that work within the multi-agent orchestration system.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.agent import Agent
from app.domain.models.event import BaseEvent, ErrorEvent, MessageEvent, StepEvent, StepStatus, ToolEvent
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.agents.base import BaseAgent
from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentSpec,
    AgentType,
)
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.code_executor import CodeExecutorTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.shell import ShellTool
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class SwarmAgent(BaseAgent):
    """A specialized agent for swarm execution.

    Extends BaseAgent with swarm-specific capabilities like
    handoff detection and multi-agent coordination.
    """

    name: str = "swarm_agent"
    max_iterations: int = 50

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        spec: AgentSpec,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        tools: list[BaseTool],
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )
        self.agent_type = agent_type
        self.spec = spec
        self.name = f"swarm_{agent_type.value}"
        self.system_prompt = spec.system_prompt_template
        self.max_iterations = spec.max_iterations

    async def execute_task(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a task with this agent.

        Args:
            prompt: The task prompt
            context: Additional context

        Yields:
            Events from task execution
        """
        # Add context to prompt if provided
        full_prompt = prompt
        if context:
            context_str = "\n".join(f"- {k}: {v}" for k, v in context.items() if v)
            if context_str:
                full_prompt = f"{prompt}\n\n## Context\n{context_str}"

        # Execute using base agent's execute method
        async for event in self.execute(full_prompt):
            yield event

    async def execute_step(
        self,
        plan: Plan,
        step: Step,
        message: Message
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a single step from a plan.

        This method provides compatibility with the multi-agent dispatch
        in PlanActFlow which expects executors to have execute_step().

        Args:
            plan: The plan containing the step
            step: The step to execute
            message: The user's original message

        Yields:
            Events from step execution including StepEvent status updates
        """
        # Build execution prompt from step
        execution_prompt = f"""Execute the following step:

## Step Description
{step.description}

## Original Request
{message.message}

## Instructions
- Execute the step using available tools
- Report your findings
- Indicate success/failure with a result summary

Respond with JSON in this format:
{{
    "success": true/false,
    "result": "Summary of what was accomplished"
}}"""

        # Mark step as running
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(status=StepStatus.STARTED, step=step)

        has_completed = False  # Track if we've yielded a completion event
        try:
            async for event in self.execute(execution_prompt):
                if isinstance(event, ErrorEvent):
                    step.status = ExecutionStatus.FAILED
                    step.error = event.error
                    yield StepEvent(status=StepStatus.FAILED, step=step)
                    has_completed = True
                    yield event
                    return  # Exit early on error
                elif isinstance(event, MessageEvent):
                    # Try to parse result from response
                    try:
                        parsed = await self.json_parser.parse(event.message)
                        step.success = parsed.get("success", False)
                        step.result = parsed.get("result", event.message)
                    except Exception:
                        # If parsing fails, treat as successful with the message as result
                        step.success = True
                        step.result = event.message

                    step.status = ExecutionStatus.COMPLETED
                    yield StepEvent(status=StepStatus.COMPLETED, step=step)
                    has_completed = True
                    if step.result:
                        yield MessageEvent(message=step.result)
                elif isinstance(event, ToolEvent):
                    yield event
                else:
                    yield event

            # If we haven't yielded a completion event yet, mark as completed
            if not has_completed:
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = "Step completed"
                yield StepEvent(status=StepStatus.COMPLETED, step=step)

        except ValueError as e:
            # Handle known errors like "Agent not found" more gracefully
            error_msg = str(e)
            logger.error(
                f"SwarmAgent {self._agent_id} step execution failed with ValueError: {error_msg}"
            )
            step.status = ExecutionStatus.FAILED
            step.error = error_msg
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield ErrorEvent(error=f"Agent configuration error: {error_msg}")

        except Exception as e:
            logger.exception(
                f"SwarmAgent {self._agent_id} step execution failed unexpectedly: {e}"
            )
            step.status = ExecutionStatus.FAILED
            step.error = str(e)
            yield StepEvent(status=StepStatus.FAILED, step=step)
            yield ErrorEvent(error=f"Step execution failed: {e!s}")


class DefaultAgentFactory:
    """Default implementation of AgentFactory for the swarm.

    Creates SwarmAgent instances with appropriate tools based on
    the agent specification's capabilities.
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        sandbox: Sandbox | None = None,
        browser: Browser | None = None,
        search_engine: SearchEngine | None = None,
        mcp_tool: MCPTool | None = None,
    ):
        self._repository = agent_repository
        self._llm = llm
        self._json_parser = json_parser
        self._sandbox = sandbox
        self._browser = browser
        self._search_engine = search_engine
        self._mcp_tool = mcp_tool

        # Cache of created agents
        self._agents: dict[str, SwarmAgent] = {}

    async def create_agent(
        self,
        agent_type: AgentType,
        agent_id: str,
        spec: AgentSpec,
    ) -> SwarmAgent:
        """Create an agent instance of the specified type.

        Args:
            agent_type: Type of agent to create
            agent_id: Unique identifier for the agent
            spec: Agent specification

        Returns:
            A configured SwarmAgent instance

        Raises:
            RuntimeError: If agent document cannot be created in the database
        """
        # Ensure the agent document exists in the database for memory operations
        # This is CRITICAL: without a database record, memory operations will fail
        await self._ensure_agent_document_exists(agent_id)

        # Determine tools based on capabilities
        tools = self._build_tools_for_spec(spec)

        agent = SwarmAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            spec=spec,
            agent_repository=self._repository,
            llm=self._llm,
            json_parser=self._json_parser,
            tools=tools,
        )

        self._agents[agent_id] = agent
        logger.info(f"Created swarm agent: {agent_type.value} ({agent_id[:8]})")

        return agent

    async def _ensure_agent_document_exists(self, agent_id: str) -> None:
        """Ensure an agent document exists in the database.

        Creates the document if it doesn't exist. This is required for
        memory operations to work correctly.

        Args:
            agent_id: The agent's unique identifier

        Raises:
            RuntimeError: If the document cannot be created
        """
        try:
            existing = await self._repository.find_by_id(agent_id)
            if not existing:
                agent_model = Agent(id=agent_id)
                await self._repository.save(agent_model)
                logger.debug(f"Created agent document in database: {agent_id[:16]}")
            else:
                logger.debug(f"Agent document already exists: {agent_id[:16]}")
        except Exception as e:
            logger.error(f"Failed to ensure agent document exists for {agent_id}: {e}")
            raise RuntimeError(
                f"Cannot create agent {agent_id}: database operation failed - {e}"
            ) from e

    async def execute_agent(
        self,
        agent: SwarmAgent,
        prompt: str,
        context: dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute an agent with the given prompt and context.

        Args:
            agent: The agent instance to execute
            prompt: The task prompt
            context: Additional context

        Yields:
            Events from agent execution
        """
        try:
            async for event in agent.execute_task(prompt, context):
                yield event
        except Exception as e:
            logger.error(f"Agent {agent.agent_type.value} execution failed: {e}")
            yield ErrorEvent(error=f"Agent execution failed: {e!s}")

    def _build_tools_for_spec(self, spec: AgentSpec) -> list[BaseTool]:
        """Build the tool list for an agent based on its specification.

        Args:
            spec: Agent specification

        Returns:
            List of tools the agent should have access to
        """
        tools: list[BaseTool] = []

        # Always include message tool for user communication
        tools.append(MessageTool())

        # Add tools based on capabilities
        if AgentCapability.SHELL_COMMANDS in spec.capabilities:
            if self._sandbox:
                tools.append(ShellTool(self._sandbox))

        if AgentCapability.FILE_OPERATIONS in spec.capabilities:
            if self._sandbox:
                tools.append(FileTool(self._sandbox))

        if AgentCapability.WEB_BROWSING in spec.capabilities:
            if self._browser:
                tools.append(BrowserTool(self._browser))

        if AgentCapability.WEB_SEARCH in spec.capabilities:
            if self._search_engine:
                tools.append(SearchTool(self._search_engine))

        if AgentCapability.CODE_EXECUTION in spec.capabilities:
            if self._sandbox:
                tools.append(CodeExecutorTool(
                    sandbox=self._sandbox,
                    session_id=spec.agent_type.value
                ))

        # Add MCP tool if available (provides additional capabilities)
        if self._mcp_tool:
            tools.append(self._mcp_tool)

        logger.debug(
            f"Built {len(tools)} tools for {spec.agent_type.value}: "
            f"{[t.name for t in tools]}"
        )

        return tools

    def get_agent(self, agent_id: str) -> SwarmAgent | None:
        """Get a previously created agent by ID.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            The agent instance or None if not found
        """
        return self._agents.get(agent_id)

    def get_all_agents(self) -> list[SwarmAgent]:
        """Get all created agents.

        Returns:
            List of all agent instances
        """
        return list(self._agents.values())


class SpecializedAgentFactory(DefaultAgentFactory):
    """Extended agent factory with support for custom agent implementations.

    Allows registering custom agent classes for specific agent types,
    while falling back to SwarmAgent for unregistered types.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._custom_agents: dict[AgentType, type] = {}

    def register_agent_class(
        self,
        agent_type: AgentType,
        agent_class: type,
    ) -> None:
        """Register a custom agent class for a specific type.

        Args:
            agent_type: The agent type
            agent_class: The custom agent class to use
        """
        self._custom_agents[agent_type] = agent_class
        logger.info(f"Registered custom agent class for {agent_type.value}")

    async def create_agent(
        self,
        agent_type: AgentType,
        agent_id: str,
        spec: AgentSpec,
    ) -> BaseAgent:
        """Create an agent, using custom class if registered.

        Args:
            agent_type: Type of agent to create
            agent_id: Unique identifier
            spec: Agent specification

        Returns:
            An agent instance (custom or SwarmAgent)

        Raises:
            RuntimeError: If agent document cannot be created in the database
        """
        if agent_type in self._custom_agents:
            # Ensure the agent document exists in the database for memory operations
            # This is CRITICAL: without a database record, memory operations will fail
            await self._ensure_agent_document_exists(agent_id)

            # Use custom agent class
            agent_class = self._custom_agents[agent_type]
            tools = self._build_tools_for_spec(spec)

            agent = agent_class(
                agent_id=agent_id,
                agent_repository=self._repository,
                llm=self._llm,
                json_parser=self._json_parser,
                tools=tools,
            )
            self._agents[agent_id] = agent
            logger.info(f"Created custom agent: {agent_type.value} ({agent_id[:8]})")
            return agent

        # Fall back to default
        return await super().create_agent(agent_type, agent_id, spec)
