import logging
import asyncio
from contextlib import asynccontextmanager
from app.domain.services.flows.base import BaseFlow
from app.domain.models.agent import Agent
from app.domain.models.message import Message
from typing import AsyncGenerator, Optional, List
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
)
from app.domain.models.plan import ExecutionStatus
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
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
from app.domain.services.tools.browser_agent import BrowserAgentTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.agents.error_handler import ErrorHandler, ErrorType, ErrorContext
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.core.config import get_settings
from app.infrastructure.observability import get_tracer, SpanKind

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    UPDATING = "updating"
    ERROR = "error"

class PlanActFlow(BaseFlow):
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
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self.status = AgentStatus.IDLE
        self.plan = None

        # State management for error recovery
        self._previous_status: Optional[AgentStatus] = None
        self._error_context: Optional[ErrorContext] = None
        self._error_handler = ErrorHandler()
        self._max_error_recovery_attempts = 3
        self._error_recovery_attempts = 0

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

        # Add browser agent tool when cdp_url is available and enabled
        settings = get_settings()
        if cdp_url and settings.browser_agent_enabled:
            tools.append(BrowserAgentTool(cdp_url))
            logger.info(f"Browser agent tool enabled for Agent {agent_id}")

        # Create planner and execution agents
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        logger.debug(f"Created planner agent for Agent {self._agent_id}")

        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )
        logger.debug(f"Created execution agent for Agent {self._agent_id}")

        # Track background tasks for cleanup
        self._background_tasks: set = set()

        # Task state manager for todo recitation
        self._task_state_manager = TaskStateManager(sandbox)

    def _background_compact_memory(self) -> None:
        """Schedule memory compaction as a non-blocking background task"""
        async def _compact():
            try:
                await self.executor.compact_memory()
                logger.debug(f"Agent {self._agent_id} background memory compact completed")
            except Exception as e:
                logger.warning(f"Agent {self._agent_id} background memory compact failed: {e}")

        task = asyncio.create_task(_compact())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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
        self.status = new_status
        logger.debug(f"Agent {self._agent_id} entering state: {new_status}")

        try:
            yield
        except Exception as e:
            self._previous_status = old_status
            self._error_context = self._error_handler.classify_error(e)
            self.status = AgentStatus.ERROR
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
                self.status = self._previous_status
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

        if session.status != SessionStatus.PENDING:
            logger.debug(f"Session {self._session_id} is not in PENDING status, rolling back")
            await self.executor.roll_back(message)
            await self.planner.roll_back(message)

        if session.status == SessionStatus.RUNNING:
            logger.debug(f"Session {self._session_id} is in RUNNING status")
            self.status = AgentStatus.PLANNING

        if session.status == SessionStatus.WAITING:
            logger.debug(f"Session {self._session_id} is in WAITING status")
            self.status = AgentStatus.EXECUTING

        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)
        self.plan = session.get_last_plan()

        logger.info(f"Agent {self._agent_id} started processing message: {message.message[:50]}...")
        step = None
        while True:
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
                    self.status = AgentStatus.PLANNING
                elif self.status == AgentStatus.PLANNING:
                    # Create plan with tracing
                    logger.info(f"Agent {self._agent_id} started creating plan")
                    with trace_ctx.span("planning", SpanKind.PLAN_CREATE) as plan_span:
                        async for event in self.planner.create_plan(message):
                            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                                self.plan = event.plan
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
                    logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.EXECUTING}")
                    self.status = AgentStatus.EXECUTING
                    if len(event.plan.steps) == 0:
                        logger.info(f"Agent {self._agent_id} created plan successfully with no steps")
                        self.status = AgentStatus.COMPLETED

                elif self.status == AgentStatus.EXECUTING:
                    # Execute plan
                    self.plan.status = ExecutionStatus.RUNNING
                    step = self.plan.get_next_step()
                    if not step:
                        logger.info(f"Agent {self._agent_id} has no more steps, state changed from {AgentStatus.EXECUTING} to {AgentStatus.COMPLETED}")
                        self.status = AgentStatus.SUMMARIZING
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

                        async for event in self.executor.execute_step(self.plan, step, message):
                            yield event

                        # Mark step as completed in task state
                        self._task_state_manager.update_step_status(str(step.id), "completed")
                        step_span.set_attribute("step.success", step.success)

                    logger.info(f"Agent {self._agent_id} completed step {step.id}, state changed from {AgentStatus.EXECUTING} to {AgentStatus.UPDATING}")
                    # Non-blocking background memory compaction
                    self._background_compact_memory()
                    self.status = AgentStatus.UPDATING
                elif self.status == AgentStatus.UPDATING:
                    # Update plan with tracing
                    logger.info(f"Agent {self._agent_id} started updating plan")
                    with trace_ctx.span("plan-update", SpanKind.PLAN_UPDATE) as update_span:
                        async for event in self.planner.update_plan(self.plan, step):
                            yield event
                        update_span.set_attribute("plan.remaining_steps", len([s for s in self.plan.steps if not s.is_done()]))
                    logger.info(f"Agent {self._agent_id} plan update completed, state changed from {AgentStatus.UPDATING} to {AgentStatus.EXECUTING}")
                    self.status = AgentStatus.EXECUTING
                elif self.status == AgentStatus.SUMMARIZING:
                    # Conclusion with tracing
                    logger.info(f"Agent {self._agent_id} started summarizing")
                    with trace_ctx.span("summarizing", SpanKind.AGENT_STEP) as summary_span:
                        async for event in self.executor.summarize():
                            yield event
                    logger.info(f"Agent {self._agent_id} summarizing completed, state changed from {AgentStatus.SUMMARIZING} to {AgentStatus.COMPLETED}")
                    self.status = AgentStatus.COMPLETED
                elif self.status == AgentStatus.COMPLETED:
                    self.plan.status = ExecutionStatus.COMPLETED
                    logger.info(f"Agent {self._agent_id} plan has been completed")
                    yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)
                    self.status = AgentStatus.IDLE
                    break

            except Exception as e:
                # Classify and handle error with tracing
                self._error_context = self._error_handler.classify_error(e)
                self._previous_status = self.status
                self.status = AgentStatus.ERROR
                logger.error(f"Agent {self._agent_id} encountered error: {e}")

                # Add error span
                with trace_ctx.span("error", SpanKind.ERROR_RECOVERY) as error_span:
                    error_span.set_attribute("error.type", str(self._error_context.error_type))
                    error_span.set_attribute("error.recoverable", self._error_context.recoverable)
                    error_span.set_attribute("error.message", str(e)[:200])

                # If not recoverable, yield error and exit
                if not self._error_context.recoverable:
                    yield ErrorEvent(error=f"Unrecoverable error: {self._error_context.message}")
                    break

        yield DoneEvent()

        logger.info(f"Agent {self._agent_id} message processing completed")
    
    def is_done(self) -> bool:
        return self.status == AgentStatus.IDLE