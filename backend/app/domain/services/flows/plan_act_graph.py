"""Graph-based PlanAct workflow implementation.

.. deprecated::
    PlanActGraphFlow is experimental and not used in production.
    Use PlanActFlow via FlowMode.PLAN_ACT instead.

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
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Optional

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.observability import get_metrics, get_tracer
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    PlanEvent,
    PlanStatus,
    TitleEvent,
    VerificationEvent,
    VerificationStatus,
)
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.models.reflection import ReflectionConfig, ReflectionTriggerType
from app.domain.models.session import SessionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.memory_manager import get_memory_manager
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.verifier import VerifierAgent, VerifierConfig
from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.graph_checkpoint_manager import get_graph_checkpoint_manager
from app.domain.services.flows.workflow_graph import (
    END,
    WorkflowBuilder,
    WorkflowGraph,
    WorkflowState,
)
from app.domain.services.prediction.failure_predictor import FailurePredictor
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.browser_agent import BrowserAgentTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.idle import IdleTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.validation.plan_validator import PlanValidator
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


@dataclass
class PlanActState(WorkflowState):
    """State for the PlanAct workflow."""

    # Core data
    message: Message | None = None
    plan: Plan | None = None
    current_step: Step | None = None

    # Agents (injected)
    planner: PlannerAgent | None = None
    executor: ExecutionAgent | None = None
    verifier: VerifierAgent | None = None

    # Context
    agent_id: str = ""
    session_id: str = ""

    # Task state manager
    task_state_manager: TaskStateManager | None = None

    # Events to yield (accumulated during node execution)
    pending_events: list[BaseEvent] = field(default_factory=list)

    # Flags
    plan_created: bool = False
    all_steps_done: bool = False
    needs_wait: bool = False

    # Verification state (Phase 1: Plan-Verify-Execute)
    verification_verdict: str | None = None  # "pass", "revise", "fail"
    verification_feedback: str | None = None
    verification_loops: int = 0
    max_verification_loops: int = 2

    # Reflection state (Phase 2: Enhanced Self-Reflection)
    reflection_agent: Optional["ReflectionAgent"] = None
    reflection_decision: str | None = None  # "continue", "adjust", "replan", "escalate", "abort"
    reflection_feedback: str | None = None
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
            logger.info("Replanning with verification feedback")

        async for event in state.planner.create_plan(state.message, replan_context=replan_context):
            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                state.plan = event.plan
                state.plan_created = True

                # Initialize task state
                if state.task_state_manager:
                    state.task_state_manager.initialize_from_plan(
                        objective=state.message.message,
                        steps=[{"id": s.id, "description": s.description} for s in event.plan.steps],
                    )

                yield TitleEvent(title=event.plan.title)
            yield event

        # Reset verification state after replanning
        state.verification_verdict = None
        state.verification_feedback = None

        # Plan validation (Phase 1)
        if state.plan:
            flags = state.metadata.get("feature_flags", {})
            if flags.get("plan_validation_v2"):
                tool_names = [
                    t.get("function", {}).get("name", "")
                    for t in (state.planner.get_available_tools() if state.planner else []) or []
                ]
                validation = PlanValidator(tool_names=tool_names).validate(state.plan)
                if not validation.passed:
                    summary = validation.to_summary()
                    if flags.get("shadow_mode", True):
                        logger.warning(f"Plan pre-validation errors (shadow): {summary}")
                    else:
                        state.verification_verdict = "revise"
                        state.verification_feedback = "Plan validation failed:" + summary
                        if state.verification_loops < state.max_verification_loops:
                            state.verification_loops += 1

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
            plan=state.plan, user_request=state.message.message if state.message else "", task_context=""
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
            await state.task_state_manager.update_step_status(str(step.id), "in_progress")

        async for event in state.executor.execute_step(state.plan, step, state.message):
            # Check for wait event
            from app.domain.models.event import WaitEvent

            if isinstance(event, WaitEvent):
                state.needs_wait = True
            yield event

        # Mark step as completed
        if state.task_state_manager:
            await state.task_state_manager.update_step_status(str(step.id), "completed")

        # Optional context optimization (Phase 3)
        flags = state.metadata.get("feature_flags", {})
        if flags.get("context_optimization") and state.executor:
            try:
                memory_manager = get_memory_manager()
                await state.executor._ensure_memory()
                messages = state.executor.memory.get_messages()
                optimized_messages, report = memory_manager.optimize_context(
                    messages,
                    preserve_recent=10,
                    token_threshold=int(
                        memory_manager.get_pressure_status(state.executor.memory.estimate_tokens()).max_tokens * 0.65
                    ),
                )
                if report.tokens_saved > 0:
                    state.executor.memory.messages = optimized_messages
                    await state.executor._repository.save_memory(
                        state.agent_id, state.executor.name, state.executor.memory
                    )
                    logger.info(
                        f"PlanActGraph context optimization saved {report.tokens_saved} tokens "
                        f"(semantic={report.semantic_compacted}, temporal={report.temporal_compacted})"
                    )
            except Exception as e:
                logger.warning(f"PlanActGraph context optimization failed: {e}")

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
            confidence=1.0,  # Could be dynamic based on context
            recent_actions=state.task_state_manager.get_recent_actions() if state.task_state_manager else None,
        )

        # Failure prediction (Phase 5, shadow mode)
        prediction = None
        flags = state.metadata.get("feature_flags", {})
        if flags.get("failure_prediction"):
            try:
                token_usage_pct = None
                if state.executor:
                    try:
                        memory_manager = get_memory_manager()
                        await state.executor._ensure_memory()
                        pressure = memory_manager.get_pressure_status(state.executor.memory.estimate_tokens())
                        token_usage_pct = pressure.usage_ratio
                    except Exception as e:
                        logger.debug(f"Token pressure lookup failed: {e}")

                predictor = FailurePredictor()
                prediction = predictor.predict(
                    progress=progress,
                    recent_actions=state.task_state_manager.get_recent_actions(),
                    stuck_analysis=None,
                    token_usage_pct=token_usage_pct,
                )
                get_metrics().record_failure_prediction(
                    "predicted" if prediction.will_fail else "clear",
                    prediction.probability,
                )
                alert_manager = state.metadata.get("alert_port")
                if alert_manager is None:
                    from app.core.alert_manager import get_alert_manager

                    alert_manager = get_alert_manager()
                await alert_manager.check_thresholds(
                    state.session_id,
                    {"failure_prediction_probability": prediction.probability},
                )
                if prediction.will_fail and not trigger_type:
                    trigger_type = ReflectionTriggerType.EXPLICIT
            except Exception as e:
                logger.debug(f"Failure prediction failed: {e}")

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
            last_error=state.task_state_manager.get_last_error(),
        ):
            yield event

            # Capture reflection decision
            if isinstance(event, ReflectionEvent) and event.status == ReflectionStatus.COMPLETED:
                state.reflection_decision = event.decision
                if event.decision in ["adjust", "replan"]:
                    state.reflection_feedback = event.summary

        if prediction and prediction.will_fail and (state.reflection_decision or "continue") == "continue":
            state.reflection_decision = "adjust"
            feedback = (
                f"Failure prediction: {prediction.probability:.0%} risk. "
                f"Factors: {', '.join(prediction.factors) or 'unknown'}. "
                f"Recommended: {prediction.recommended_action}."
            )
            state.reflection_feedback = (
                f"{state.reflection_feedback}\n\n{feedback}" if state.reflection_feedback else feedback
            )

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
        if state.verification_verdict == "revise":
            if state.verification_loops >= state.max_verification_loops:
                logger.warning(
                    f"Max validation loops ({state.max_verification_loops}) reached, proceeding with execution"
                )
                return "executing"
            return "planning"
        # Route to verification if verifier is available
        if state.verifier:
            return "verifying"
        return "executing"

    def route_after_verification(state: PlanActState) -> str:
        """Route after verification based on verdict."""
        if state.verification_verdict == "pass":
            return "executing"
        if state.verification_verdict == "revise":
            # Check if we've exceeded max revision loops
            if state.verification_loops >= state.max_verification_loops:
                logger.warning(
                    f"Max verification loops ({state.max_verification_loops}) reached, proceeding with execution"
                )
                return "executing"
            # Return to planning with feedback
            return "planning"
        if state.verification_verdict == "fail":
            # Exit gracefully
            return "summarizing"
        # Default: proceed with execution
        return "executing"

    def route_after_reflection(state: PlanActState) -> str:
        """Route after reflection based on decision (Phase 2)."""
        decision = state.reflection_decision or "continue"

        if decision == "continue":
            return "updating"
        if decision == "adjust":
            # Minor adjustment - proceed with updating but apply adjustment
            # The adjustment is logged but execution continues
            logger.info(f"Reflection adjustment: {state.reflection_feedback}")
            return "updating"
        if decision == "replan":
            # Major strategy change - return to planning
            logger.info(f"Reflection triggered replan: {state.reflection_feedback}")
            return "planning"
        if decision == "escalate":
            # Need user input - summarize current state and wait
            logger.info("Reflection escalated to user")
            return "summarizing"
        if decision == "abort":
            # Task cannot be completed - exit gracefully
            logger.warning("Reflection decided to abort task")
            return "summarizing"
        # Default: continue with updating
        return "updating"

    # Build the graph with verification and reflection steps
    return (
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
        search_engine: SearchEngine | None = None,
        cdp_url: str | None = None,
        enable_verification: bool = True,
        feature_flags: dict[str, bool] | None = None,
        browser_agent_enabled: bool = False,
        alert_port=None,
    ):
        self._feature_flags = feature_flags
        self._alert_port = alert_port
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository

        # Build tools list
        tools = [ShellTool(sandbox), BrowserTool(browser), FileTool(sandbox), MessageTool(), IdleTool(), mcp_tool]

        # Pass browser to SearchTool for visual search when search_prefer_browser is enabled
        if search_engine:
            tools.append(SearchTool(search_engine, browser=browser))

        if cdp_url and browser_agent_enabled:
            tools.append(BrowserAgentTool(cdp_url))

        # Create agents
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            feature_flags=feature_flags,
        )

        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=llm,
            tools=tools,
            json_parser=json_parser,
            feature_flags=feature_flags,
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
                ),
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
            ),
        )
        logger.info(f"ReflectionAgent enabled for agent {agent_id}")

        # Task state manager
        self._task_state_manager = TaskStateManager(sandbox)
        self.planner._task_state_manager = self._task_state_manager
        self.executor._task_state_manager = self._task_state_manager

        # Create workflow graph
        self._graph = create_plan_act_graph()

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

        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)

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
        state.metadata["feature_flags"] = self._resolve_feature_flags()
        state.metadata["alert_port"] = self._resolve_alert_port()

        # Run with tracing
        with tracer.trace(
            "plan-act-graph",
            agent_id=self._agent_id,
            session_id=self._session_id,
            attributes={"message.preview": message.message[:100]},
        ):

            def on_node_start(node_name: str, state: PlanActState):
                logger.info(f"Graph node starting: {node_name}")

            def on_node_end(node_name: str, state: PlanActState, execution):
                logger.info(
                    f"Graph node completed: {node_name} "
                    f"[{execution.duration_ms:.0f}ms, {execution.events_emitted} events]"
                )

            checkpoint_manager = None
            if state.metadata.get("feature_flags", {}).get("workflow_checkpointing"):
                checkpoint_manager = get_graph_checkpoint_manager()

            async for event in self._graph.run(
                state,
                on_node_start=on_node_start,
                on_node_end=on_node_end,
                checkpoint_manager=checkpoint_manager,
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
