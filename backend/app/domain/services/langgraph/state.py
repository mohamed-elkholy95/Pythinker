"""State schema for the LangGraph PlanAct workflow.

This module defines the TypedDict state that flows through the graph,
preserving compatibility with existing agent implementations.
"""

import asyncio
from typing import TypedDict, Annotated, Optional, List, Any

from app.domain.models.plan import Plan, Step
from app.domain.models.message import Message
from app.domain.models.event import BaseEvent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.verifier import VerifierAgent
from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.stuck_detector import StuckAnalysis


def merge_events(a: List[BaseEvent], b: List[BaseEvent] | None) -> List[BaseEvent]:
    """Reducer function to accumulate events from multiple nodes."""
    if b is None:
        return a
    return a + b


def merge_tools(a: List[str], b: List[str] | None) -> List[str]:
    """Reducer function to track tool usage."""
    if b is None:
        return a
    return a + b


class PlanActState(TypedDict, total=False):
    """State for the LangGraph PlanAct workflow.

    This state schema preserves compatibility with existing PlanActFlow
    while enabling LangGraph features like checkpointing and streaming.

    Attributes:
        user_message: The original user message being processed
        plan: The current execution plan
        current_step: The step currently being executed

        agent_id: ID of the agent instance
        session_id: ID of the current session
        user_id: ID of the user (for memory service)

        iteration_count: Number of planning/execution iterations
        max_iterations: Maximum allowed iterations

        verification_verdict: Result of plan verification ("pass", "revise", "fail")
        verification_feedback: Feedback for plan revision
        verification_loops: Number of verification loop iterations
        max_verification_loops: Maximum verification attempts

        reflection_decision: Decision from reflection ("continue", "adjust", "replan", "escalate")
        last_had_error: Whether the last step had an error

        error: Current error message if any
        error_count: Number of errors encountered

        needs_human_input: Flag for human-in-the-loop interrupt
        human_response: Response from human input

        pending_events: Events accumulated during node execution (streamed to frontend)
        recent_tools: Recently used tool names for memory compaction decisions

        planner: PlannerAgent instance (injected)
        executor: ExecutionAgent instance (injected)
        verifier: VerifierAgent instance (optional, injected)
        reflection_agent: ReflectionAgent instance (optional, injected)
        task_state_manager: TaskStateManager for tracking execution state
    """

    # Core task data
    user_message: Message
    plan: Optional[Plan]
    current_step: Optional[Step]

    # Session identifiers
    agent_id: str
    session_id: str
    user_id: Optional[str]

    # Execution tracking
    iteration_count: int
    max_iterations: int

    # Verification state (Phase 1: Plan-Verify-Execute)
    verification_verdict: Optional[str]  # "pass", "revise", "fail"
    verification_feedback: Optional[str]
    verification_loops: int
    max_verification_loops: int

    # Reflection state (Phase 2: Enhanced Self-Reflection)
    reflection_decision: Optional[str]  # "continue", "adjust", "replan", "escalate"
    last_had_error: bool

    # Stuck pattern analysis (Enhanced with OpenHands patterns)
    stuck_analysis: Optional[StuckAnalysis]
    recent_actions: Optional[List[dict]]  # Tool action history for stuck analysis

    # Error handling
    error: Optional[str]
    error_count: int

    # Human-in-the-loop
    needs_human_input: bool
    human_response: Optional[str]

    # Event accumulator (streamed to frontend)
    # Using Annotated with reducer to properly accumulate events across nodes
    pending_events: Annotated[List[BaseEvent], merge_events]

    # Tool tracking for memory compaction
    recent_tools: Annotated[List[str], merge_tools]

    # Injected agents (not serialized in checkpoints)
    planner: Optional[PlannerAgent]
    executor: Optional[ExecutionAgent]
    verifier: Optional[VerifierAgent]
    reflection_agent: Optional[ReflectionAgent]
    task_state_manager: Optional[TaskStateManager]

    # Flow control flags
    plan_created: bool
    all_steps_done: bool

    # Real-time event streaming queue (not serialized in checkpoints)
    event_queue: Optional[asyncio.Queue]


def create_initial_state(
    message: Message,
    agent_id: str,
    session_id: str,
    user_id: Optional[str] = None,
    planner: Optional[PlannerAgent] = None,
    executor: Optional[ExecutionAgent] = None,
    verifier: Optional[VerifierAgent] = None,
    reflection_agent: Optional[ReflectionAgent] = None,
    task_state_manager: Optional[TaskStateManager] = None,
    existing_plan: Optional[Plan] = None,
    max_iterations: int = 200,  # Increased for complex multi-step tasks
    max_verification_loops: int = 3,  # Allow more revision attempts
    event_queue: Optional[asyncio.Queue] = None,
) -> PlanActState:
    """Create the initial state for a new workflow run.

    Args:
        message: User message to process
        agent_id: Agent instance ID
        session_id: Session ID
        user_id: Optional user ID for memory service
        planner: PlannerAgent instance
        executor: ExecutionAgent instance
        verifier: Optional VerifierAgent instance
        reflection_agent: Optional ReflectionAgent instance
        task_state_manager: Optional TaskStateManager instance
        existing_plan: Plan from a previous session to resume
        max_iterations: Maximum planning/execution iterations
        max_verification_loops: Maximum verification attempts

    Returns:
        Initialized PlanActState
    """
    return PlanActState(
        # Core task data
        user_message=message,
        plan=existing_plan,
        current_step=None,

        # Session identifiers
        agent_id=agent_id,
        session_id=session_id,
        user_id=user_id,

        # Execution tracking
        iteration_count=0,
        max_iterations=max_iterations,

        # Verification state
        verification_verdict=None,
        verification_feedback=None,
        verification_loops=0,
        max_verification_loops=max_verification_loops,

        # Reflection state
        reflection_decision=None,
        last_had_error=False,

        # Error handling
        error=None,
        error_count=0,

        # Human-in-the-loop
        needs_human_input=False,
        human_response=None,

        # Event accumulator
        pending_events=[],

        # Tool tracking
        recent_tools=[],

        # Injected agents
        planner=planner,
        executor=executor,
        verifier=verifier,
        reflection_agent=reflection_agent,
        task_state_manager=task_state_manager,

        # Flow control
        plan_created=False,
        all_steps_done=False,

        # Real-time event streaming
        event_queue=event_queue,
    )
