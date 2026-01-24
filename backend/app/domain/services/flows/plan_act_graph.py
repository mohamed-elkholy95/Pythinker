"""Graph-based PlanAct workflow implementation.

This module provides a graph-based implementation of the PlanAct workflow
using the WorkflowGraph engine. It demonstrates declarative workflow definition
with clear state transitions.

The workflow follows this structure (with Plan-Verify-Execute pattern):
    START -> planning -> verifying -> [PASS] -> executing -> [conditional] -> updating/summarizing -> END
                            ^             |          ^              |
                            |        [REVISE]        |              v
                            +--- planning <-+        +--- updating -+
                            |
                        [FAIL] -> summarizing -> END
"""

import logging
from typing import AsyncGenerator, Optional, List
from dataclasses import dataclass, field

from app.domain.services.flows.workflow_graph import (
    WorkflowGraph,
    WorkflowState,
    WorkflowBuilder,
    END,
)
from app.domain.services.flows.base import BaseFlow
from app.domain.models.agent import Agent
from app.domain.models.message import Message
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    MessageEvent,
    DoneEvent,
    TitleEvent,
    ErrorEvent,
    VerificationEvent,
    VerificationStatus,
)
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.models.reflection import ReflectionConfig, ReflectionDecision
from app.domain.models.agent_response import VerificationVerdict
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
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
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.core.config import get_settings
from app.infrastructure.observability import get_tracer, SpanKind


logger = logging.getLogger(__name__)


@dataclass
class PlanActState(WorkflowState):
    """State for the PlanAct workflow."""
    # Core data
    message: Optional[Message] = None
    plan: Optional[Plan] = None
    current_step: Optional[Step] = None

    # Agents (injected)
    planner: Optional[PlannerAgent] = None
    executor: Optional[ExecutionAgent] = None
    verifier: Optional[VerifierAgent] = None

    # Context
    agent_id: str = ""
    session_id: str = ""

    # Task state manager
    task_state_manager: Optional[TaskStateManager] = None

    # Events to yield (accumulated during node execution)
    pending_events: List[BaseEvent] = field(default_factory=list)

    # Flags
    plan_created: bool = False
    all_steps_done: bool = False
    needs_wait: bool = False

    # Verification state (Phase 1: Plan-Verify-Execute)
    verification_verdict: Optional[str] = None  # "pass", "revise", "fail"
    verification_feedback: Optional[str] = None
    verification_loops: int = 0
    max_verification_loops: int = 2

    # Reflection state (Phase 2: Enhanced Self-Reflection)
    reflection_agent: Optional["ReflectionAgent"] = None
    reflection_decision: Optional[str] = None  # "continue", "adjust", "replan", "escalate", "abort"
    reflection_feedback: Optional[str] = None
    last_had_error: bool = False


def create_plan_act_graph() -> WorkflowGraph:
    """Create the PlanAct workflow graph.

    Returns:
        Configured WorkflowGraph instance
    """

    async def planning_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Create the initial plan."""
        logger.info(f"Planning node: creating plan for agent {state.agent_id}")

        # Check if this is a replan due to verification feedback
        replan_context = None
        if state.verification_feedback and state.verification_verdict == "revise":
            replan_context = state.verification_feedback
            logger.info(f"Replanning with verification feedback")

        async for event in state.planner.create_plan(
            state.message,
            replan_context=replan_context
        ):
            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                state.plan = event.plan
                state.plan_created = True

                # Initialize task state
                if state.task_state_manager:
                    state.task_state_manager.initialize_from_plan(
                        objective=state.message.message,
                        steps=[{"id": s.id, "description": s.description}
                               for s in event.plan.steps]
                    )

                yield TitleEvent(title=event.plan.title)
            yield event

        # Reset verification state after replanning
        state.verification_verdict = None
        state.verification_feedback = None

        # Check if plan has no steps
        if state.plan and len(state.plan.steps) == 0:
            state.all_steps_done = True

    async def verifying_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Verify the plan before execution (Plan-Verify-Execute pattern)."""
        if not state.plan or not state.verifier:
            # No verifier configured, pass through
            state.verification_verdict = "pass"
            return

        logger.info(f"Verifying plan: {state.plan.title}")

        async for event in state.verifier.verify_plan(
            plan=state.plan,
            user_request=state.message.message if state.message else "",
            task_context=""
        ):
            yield event

            # Capture the verification result
            if isinstance(event, VerificationEvent):
                if event.status == VerificationStatus.PASSED:
                    state.verification_verdict = "pass"
                elif event.status == VerificationStatus.REVISION_NEEDED:
                    state.verification_verdict = "revise"
                    state.verification_feedback = event.revision_feedback
                    state.verification_loops += 1
                elif event.status == VerificationStatus.FAILED:
                    state.verification_verdict = "fail"

    async def executing_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Execute the next step in the plan."""
        if not state.plan:
            state.error = "No plan available for execution"
            return

        state.plan.status = ExecutionStatus.RUNNING
        step = state.plan.get_next_step()

        if not step:
            state.all_steps_done = True
            return

        state.current_step = step
        logger.info(f"Executing step {step.id}: {step.description[:50]}...")

        # Mark step as in progress
        if state.task_state_manager:
            state.task_state_manager.update_step_status(str(step.id), "in_progress")

        async for event in state.executor.execute_step(state.plan, step, state.message):
            # Check for wait event
            from app.domain.models.event import WaitEvent
            if isinstance(event, WaitEvent):
                state.needs_wait = True
            yield event

        # Mark step as completed
        if state.task_state_manager:
            state.task_state_manager.update_step_status(str(step.id), "completed")

    async def updating_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Update the plan after step completion."""
        if not state.plan or not state.current_step:
            return

        logger.info(f"Updating plan after step {state.current_step.id}")

        async for event in state.planner.update_plan(state.plan, state.current_step):
            yield event

    async def reflecting_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Reflect on progress and determine course correction (Phase 2)."""
        if not state.reflection_agent or not state.plan or not state.task_state_manager:
            # No reflection configured, pass through
            state.reflection_decision = "continue"
            return

        # Get progress metrics
        progress = state.task_state_manager.get_progress_metrics()
        if not progress:
            state.reflection_decision = "continue"
            return

        # Check if reflection should be triggered
        trigger_type = state.reflection_agent.should_reflect(
            progress=progress,
            last_had_error=state.last_had_error,
            confidence=1.0  # Could be dynamic based on context
        )

        if not trigger_type:
            state.reflection_decision = "continue"
            return

        logger.info(f"Reflecting on progress: trigger={trigger_type.value}")

        # Perform reflection
        from app.domain.models.event import ReflectionEvent, ReflectionStatus
        async for event in state.reflection_agent.reflect(
            goal=state.plan.goal,
            plan=state.plan,
            progress=progress,
            trigger_type=trigger_type,
            recent_actions=state.task_state_manager.get_recent_actions(),
            last_error=state.task_state_manager.get_last_error()
        ):
            yield event

            # Capture reflection decision
            if isinstance(event, ReflectionEvent) and event.status == ReflectionStatus.COMPLETED:
                state.reflection_decision = event.decision
                if event.decision in ["adjust", "replan"]:
                    state.reflection_feedback = event.summary

        # Reset error flag after reflection
        state.last_had_error = False

    async def summarizing_node(state: PlanActState) -> AsyncGenerator[BaseEvent, None]:
        """Summarize the completed work."""
        logger.info("Summarizing completed work")

        async for event in state.executor.summarize():
            yield event

        # Mark plan as completed
        if state.plan:
            state.plan.status = ExecutionStatus.COMPLETED
            yield PlanEvent(status=PlanStatus.COMPLETED, plan=state.plan)

        yield DoneEvent()

    def route_after_execution(state: PlanActState) -> str:
        """Route after execution based on state."""
        if state.needs_wait:
            # User input needed - exit workflow
            return END
        if state.all_steps_done:
            return "summarizing"
        # Check if reflection is enabled and should be considered
        if state.reflection_agent:
            return "reflecting"
        return "updating"

    def route_after_planning(state: PlanActState) -> str:
        """Route after planning based on state."""
        if state.all_steps_done:
            return "summarizing"
        # Route to verification if verifier is available
        if state.verifier:
            return "verifying"
        return "executing"

    def route_after_verification(state: PlanActState) -> str:
        """Route after verification based on verdict."""
        if state.verification_verdict == "pass":
            return "executing"
        elif state.verification_verdict == "revise":
            # Check if we've exceeded max revision loops
            if state.verification_loops >= state.max_verification_loops:
                logger.warning(
                    f"Max verification loops ({state.max_verification_loops}) reached, "
                    "proceeding with execution"
                )
                return "executing"
            # Return to planning with feedback
            return "planning"
        elif state.verification_verdict == "fail":
            # Exit gracefully
            return "summarizing"
        # Default: proceed with execution
        return "executing"

    def route_after_reflection(state: PlanActState) -> str:
        """Route after reflection based on decision (Phase 2)."""
        decision = state.reflection_decision or "continue"

        if decision == "continue":
            return "updating"
        elif decision == "adjust":
            # Minor adjustment - proceed with updating but apply adjustment
            # The adjustment is logged but execution continues
            logger.info(f"Reflection adjustment: {state.reflection_feedback}")
            return "updating"
        elif decision == "replan":
            # Major strategy change - return to planning
            logger.info(f"Reflection triggered replan: {state.reflection_feedback}")
            return "planning"
        elif decision == "escalate":
            # Need user input - summarize current state and wait
            logger.info("Reflection escalated to user")
            return "summarizing"
        elif decision == "abort":
            # Task cannot be completed - exit gracefully
            logger.warning("Reflection decided to abort task")
            return "summarizing"
        else:
            # Default: continue with updating
            return "updating"

    # Build the graph with verification and reflection steps
    graph = (
        WorkflowBuilder("plan-act", "Plan, verify, execute, and reflect with iterative updates")
        .node("planning", planning_node, "Create execution plan from user request")
        .conditional(route_after_planning, ["verifying", "executing", "summarizing"])
        .node("verifying", verifying_node, "Verify plan feasibility before execution")
        .conditional(route_after_verification, ["executing", "planning", "summarizing"])
        .node("executing", executing_node, "Execute the next step in the plan")
        .conditional(route_after_execution, ["reflecting", "updating", "summarizing", END])
        .node("reflecting", reflecting_node, "Reflect on progress and determine course correction")
        .conditional(route_after_reflection, ["updating", "planning", "summarizing"])
        .node("updating", updating_node, "Update plan based on step results")
        .edge("executing")
        .node("summarizing", summarizing_node, "Summarize completed work")
        .edge(END)
        .entry("planning")
        .build()
    )

    return graph


class PlanActGraphFlow(BaseFlow):
    """Graph-based PlanAct flow implementation.

    This is an alternative implementation of PlanActFlow using the WorkflowGraph
    engine for more declarative and testable workflow definition.

    Implements the Plan-Verify-Execute pattern where plans are verified
    before execution to catch infeasible plans early.
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
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository

        # Build tools list
        tools = [
            ShellTool(sandbox),
            BrowserTool(browser),
            FileTool(sandbox),
            MessageTool(),
            IdleTool(),
            mcp_tool
        ]

        if search_engine:
            tools.append(SearchTool(search_engine))

        settings = get_settings()
        if cdp_url and settings.browser_agent_enabled:
            tools.append(BrowserAgentTool(cdp_url))

        # Create agents
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )

        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
        )

        # Create verifier agent (Phase 1: Plan-Verify-Execute)
        self.verifier = None
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
            logger.info(f"VerifierAgent enabled for agent {agent_id}")

        # Create reflection agent (Phase 2: Enhanced Self-Reflection)
        self.reflection_agent = ReflectionAgent(
            llm=llm,
            json_parser=json_parser,
            config=ReflectionConfig(
                enabled=True,
                max_reflections_per_task=10,
                min_steps_between_reflections=1,
            )
        )
        logger.info(f"ReflectionAgent enabled for agent {agent_id}")

        # Task state manager
        self._task_state_manager = TaskStateManager(sandbox)

        # Create workflow graph
        self._graph = create_plan_act_graph()

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Execute the plan-act workflow.

        Args:
            message: User message to process

        Yields:
            Events from workflow execution
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

        # Create initial state
        state = PlanActState(
            message=message,
            plan=session.get_last_plan(),
            planner=self.planner,
            executor=self.executor,
            verifier=self.verifier,
            reflection_agent=self.reflection_agent,
            agent_id=self._agent_id,
            session_id=self._session_id,
            task_state_manager=self._task_state_manager,
        )

        # Run with tracing
        with tracer.trace(
            "plan-act-graph",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]}
        ) as trace_ctx:

            def on_node_start(node_name: str, state: PlanActState):
                logger.info(f"Graph node starting: {node_name}")

            def on_node_end(node_name: str, state: PlanActState, execution):
                logger.info(
                    f"Graph node completed: {node_name} "
                    f"[{execution.duration_ms:.0f}ms, {execution.events_emitted} events]"
                )

            async for event in self._graph.run(
                state,
                on_node_start=on_node_start,
                on_node_end=on_node_end
            ):
                yield event

        logger.info(f"PlanActGraphFlow completed for agent {self._agent_id}")

    def is_done(self) -> bool:
        """Check if workflow is complete."""
        return True  # Graph handles completion internally


# Export for use
__all__ = [
    "PlanActGraphFlow",
    "PlanActState",
    "create_plan_act_graph",
]
