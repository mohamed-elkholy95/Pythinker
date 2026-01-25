"""LangGraph-based PlanAct flow implementation.

This module provides the LangGraphPlanActFlow class that wraps the LangGraph
workflow in a BaseFlow-compatible interface.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional, List, Any

from app.domain.services.flows.base import BaseFlow
from app.domain.models.message import Message
from app.domain.models.event import BaseEvent
from app.domain.models.session import SessionStatus
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.utils.json_parser import JsonParser
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.tools.code_executor import CodeExecutorTool
from app.domain.services.tools.base import BaseTool
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.models.reflection import ReflectionConfig
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.core.config import get_settings
from app.infrastructure.observability import get_tracer

from app.domain.services.langgraph.state import PlanActState, create_initial_state
from app.domain.services.langgraph.graph import create_plan_act_graph
from app.domain.services.langgraph.checkpointer import MongoDBCheckpointer

# BrowserAgentTool is optional (requires browser_use package)
try:
    from app.domain.services.tools.browser_agent import BrowserAgentTool, BROWSER_USE_AVAILABLE
except ImportError:
    BrowserAgentTool = None
    BROWSER_USE_AVAILABLE = False

logger = logging.getLogger(__name__)


class LangGraphPlanActFlow(BaseFlow):
    """LangGraph-based PlanAct flow implementation.

    This flow uses LangGraph's StateGraph for workflow orchestration,
    providing built-in checkpointing, streaming, and better composability.

    The flow preserves compatibility with the existing event system and
    agent implementations while leveraging LangGraph's features.
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
        enable_reflection: bool = True,
        enable_checkpointing: bool = False,
        mongodb_db: Optional[Any] = None,  # AsyncIOMotorDatabase for checkpointing
        memory_service: Optional[Any] = None,
        user_id: Optional[str] = None,
    ):
        """Initialize the LangGraph PlanAct flow.

        Args:
            agent_id: Unique agent identifier
            agent_repository: Repository for agent persistence
            session_id: Current session ID
            session_repository: Repository for session persistence
            llm: Language model instance
            sandbox: Sandbox for tool execution
            browser: Browser for web operations
            json_parser: JSON parser for responses
            mcp_tool: MCP tool for external integrations
            search_engine: Optional search engine
            cdp_url: Optional Chrome DevTools Protocol URL
            enable_verification: Enable plan verification (default True)
            enable_reflection: Enable self-reflection (default True)
            enable_checkpointing: Enable MongoDB checkpointing (default False)
            mongodb_db: MongoDB database for checkpointing
            memory_service: Optional memory service for long-term context
            user_id: Optional user ID for memory service
        """
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._user_id = user_id
        self._memory_service = memory_service

        # Build tools list
        tools: List[BaseTool] = [
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            CodeExecutorTool(sandbox=sandbox, session_id=session_id),
            MessageTool(),
            IdleTool(),
            mcp_tool
        ]

        if search_engine:
            tools.append(SearchTool(search_engine))

        settings = get_settings()
        if cdp_url and settings.browser_agent_enabled and BROWSER_USE_AVAILABLE and BrowserAgentTool:
            try:
                tools.append(BrowserAgentTool(cdp_url))
                logger.info(f"Browser agent tool enabled for Agent {agent_id}")
            except ImportError as e:
                logger.warning(f"Browser agent tool not available: {e}")

        # Create planner agent
        self.planner = PlannerAgent(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            memory_service=memory_service,
            user_id=user_id,
        )
        logger.debug(f"Created planner agent for Agent {agent_id}")

        # Create execution agent
        self.executor = ExecutionAgent(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            memory_service=memory_service,
            user_id=user_id,
        )
        logger.debug(f"Created execution agent for Agent {agent_id}")

        # Create verifier agent (optional)
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

        # Create reflection agent (optional)
        self.reflection_agent: Optional[ReflectionAgent] = None
        if enable_reflection:
            self.reflection_agent = ReflectionAgent(
                llm=llm,
                json_parser=json_parser,
                config=ReflectionConfig(
                    enabled=True,
                    max_reflections_per_task=10,
                    min_steps_between_reflections=1,
                )
            )
            logger.info(f"ReflectionAgent enabled for Agent {agent_id}")

        # Task state manager
        self._task_state_manager = TaskStateManager(sandbox)

        # Create checkpointer if enabled
        checkpointer = None
        if enable_checkpointing and mongodb_db:
            checkpointer = MongoDBCheckpointer(mongodb_db)
            logger.info(f"MongoDB checkpointing enabled for Agent {agent_id}")

        # Create and compile the graph
        self._graph = create_plan_act_graph(checkpointer=checkpointer)
        self._checkpointer = checkpointer

        logger.info(f"LangGraphPlanActFlow initialized for Agent {agent_id}")

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Execute the plan-act workflow.

        Args:
            message: User message to process

        Yields:
            Events from workflow execution (streamed in real-time)
        """
        tracer = get_tracer()

        # Handle session state
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise ValueError(f"Session {self._session_id} not found")

        await self._session_repository.update_status(
            self._session_id,
            SessionStatus.RUNNING
        )

        # Create event queue for real-time streaming
        event_queue: asyncio.Queue[BaseEvent | None] = asyncio.Queue()

        # Create initial state with event queue for real-time streaming
        initial_state = create_initial_state(
            message=message,
            agent_id=self._agent_id,
            session_id=self._session_id,
            user_id=self._user_id,
            planner=self.planner,
            executor=self.executor,
            verifier=self.verifier,
            reflection_agent=self.reflection_agent,
            task_state_manager=self._task_state_manager,
            existing_plan=session.get_last_plan(),
            event_queue=event_queue,
        )

        # Config for the graph run
        config = {
            "configurable": {
                "thread_id": self._session_id,
            }
        }

        async def run_graph():
            """Run the graph and signal completion via queue."""
            try:
                with tracer.trace(
                    "langgraph-plan-act",
                    agent_id=self._agent_id,
                    session_id=self._session_id,
                    attributes={"message.preview": message.message[:100]}
                ):
                    async for chunk in self._graph.astream(initial_state, config):
                        # Each chunk is a dict with node_name -> state_update
                        for node_name, state_update in chunk.items():
                            logger.debug(f"LangGraph node completed: {node_name}")

                            # Also yield any batched pending_events (fallback)
                            pending_events = state_update.get("pending_events", [])
                            for event in pending_events:
                                await event_queue.put(event)
            except Exception as e:
                logger.error(f"Graph execution error: {e}")
            finally:
                # Signal completion
                await event_queue.put(None)

        # Start graph execution in background
        graph_task = asyncio.create_task(run_graph())

        # Yield events from queue in real-time
        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield event
        finally:
            # Ensure graph task completes
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except asyncio.CancelledError:
                    pass

        logger.info(f"LangGraphPlanActFlow completed for Agent {self._agent_id}")

    async def resume(self, human_input: str) -> AsyncGenerator[BaseEvent, None]:
        """Resume workflow after human-in-the-loop interrupt.

        Args:
            human_input: Input from the human user

        Yields:
            Events from resumed workflow execution
        """
        if not self._checkpointer:
            logger.warning("Cannot resume without checkpointing enabled")
            return

        config = {
            "configurable": {
                "thread_id": self._session_id,
            }
        }

        # Get the current state from the checkpoint
        checkpoint_tuple = await self._checkpointer.aget_tuple(config)
        if not checkpoint_tuple:
            logger.error(f"No checkpoint found for session {self._session_id}")
            return

        # Update state with human response
        current_state = checkpoint_tuple.checkpoint.get("channel_values", {})
        current_state["human_response"] = human_input
        current_state["needs_human_input"] = False

        # Re-inject agents (not serialized in checkpoint)
        current_state["planner"] = self.planner
        current_state["executor"] = self.executor
        current_state["verifier"] = self.verifier
        current_state["reflection_agent"] = self.reflection_agent
        current_state["task_state_manager"] = self._task_state_manager

        # Resume the graph
        async for chunk in self._graph.astream(current_state, config):
            for node_name, state_update in chunk.items():
                logger.debug(f"LangGraph resume node completed: {node_name}")

                pending_events = state_update.get("pending_events", [])
                for event in pending_events:
                    yield event

    def is_done(self) -> bool:
        """Check if workflow is complete.

        Returns:
            True (graph handles completion internally)
        """
        return True  # Graph completion is handled by END node


# Export for use
__all__ = [
    "LangGraphPlanActFlow",
]
