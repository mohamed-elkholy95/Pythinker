"""State schema for the LangGraph PlanAct workflow.

This module defines the TypedDict state that flows through the graph,
preserving compatibility with existing agent implementations.
"""

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.domain.models.event import BaseEvent
from app.domain.models.message import Message
from app.domain.models.plan import Plan, Step
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.intent_tracker import IntentTracker, UserIntent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.reflection import ReflectionAgent
from app.domain.services.agents.stuck_detector import StuckAnalysis
from app.domain.services.agents.task_state_manager import TaskStateManager
from app.domain.services.agents.verifier import VerifierAgent


@dataclass
class RequirementProgress:
    """Track progress on a single requirement.

    Used for monitoring which user requirements have been addressed
    during execution and by which step.
    """

    requirement: str
    is_addressed: bool = False
    confidence: float = 0.0
    addressed_by_step: str | None = None
    evidence: str | None = None


def merge_requirement_progress(
    a: list[RequirementProgress],
    b: list[RequirementProgress] | None,
) -> list[RequirementProgress]:
    """Reducer function to update requirement progress.

    When new progress is provided, it replaces the old list entirely
    since updates are computed as a complete replacement.
    """
    if b is None:
        return a
    # New progress replaces old progress entirely
    return b


def merge_events(a: list[BaseEvent], b: list[BaseEvent] | None) -> list[BaseEvent]:
    """Reducer function to accumulate events from multiple nodes."""
    if b is None:
        return a
    return a + b


def merge_tools(a: list[str], b: list[str] | None) -> list[str]:
    """Reducer function to track tool usage."""
    if b is None:
        return a
    return a + b


def merge_tool_results(
    a: list[ToolResult[Any] | dict[str, Any]], b: list[ToolResult[Any] | dict[str, Any]] | None
) -> list[ToolResult[Any] | dict[str, Any]]:
    """Reducer function to accumulate tool results across execution nodes.

    Tool results are collected for chain-of-verification (CoVe) to validate
    claims in the final summary against actual tool outputs.
    """
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
    plan: Plan | None
    current_step: Step | None

    # Session identifiers
    agent_id: str
    session_id: str
    user_id: str | None

    # Execution tracking
    iteration_count: int
    max_iterations: int

    # Verification state (Phase 1: Plan-Verify-Execute)
    verification_verdict: str | None  # "pass", "revise", "fail"
    verification_feedback: str | None
    verification_loops: int
    max_verification_loops: int

    # Reflection state (Phase 2: Enhanced Self-Reflection)
    reflection_decision: str | None  # "continue", "adjust", "replan", "escalate"
    last_had_error: bool
    # Plan validation state (Phase 1: Pre-validation)
    plan_validation_failed: bool

    # Stuck pattern analysis (Enhanced with OpenHands patterns)
    stuck_analysis: StuckAnalysis | None
    recent_actions: list[dict] | None  # Tool action history for stuck analysis

    # Phase 3: User Intent Tracking for Prompt Adherence
    user_intent: UserIntent | None  # Extracted user intent from planning
    intent_tracker: IntentTracker | None  # Intent tracker instance
    human_input_reason: str | None  # Reason for requesting human input

    # Phase 3: Requirement Progress Tracking
    # Track which requirements have been addressed and by which step
    requirement_progress: Annotated[list[RequirementProgress], merge_requirement_progress]
    constraint_violations: list[str]  # Accumulated constraint violations during execution
    intent_alignment_score: float  # 0.0 to 1.0 - overall alignment with user intent

    # Error handling
    error: str | None
    error_count: int

    # Human-in-the-loop
    needs_human_input: bool
    human_response: str | None

    # Event accumulator (streamed to frontend)
    # Using Annotated with reducer to properly accumulate events across nodes
    pending_events: Annotated[list[BaseEvent], merge_events]

    # Tool tracking for memory compaction
    recent_tools: Annotated[list[str], merge_tools]

    # Tool results for chain-of-verification (CoVe)
    # Accumulated from execution nodes for claim verification in summarize node
    tool_results: Annotated[list[ToolResult[Any] | dict[str, Any]], merge_tool_results]

    # Injected agents (not serialized in checkpoints)
    planner: PlannerAgent | None
    executor: ExecutionAgent | None
    verifier: VerifierAgent | None
    reflection_agent: ReflectionAgent | None
    task_state_manager: TaskStateManager | None

    # Flow control flags
    plan_created: bool
    all_steps_done: bool

    # Real-time event streaming queue (not serialized in checkpoints)
    event_queue: asyncio.Queue | None

    # Phase 2: Browser Node Integration
    # Browser task for autonomous browser agent node
    browser_task: str | None
    # CDP URL for browser connection (from sandbox)
    cdp_url: str | None
    # Result from browser agent node execution
    browser_result: Any  # BrowserNodeResult when feature_browser_node enabled


def create_initial_state(
    message: Message,
    agent_id: str,
    session_id: str,
    user_id: str | None = None,
    planner: PlannerAgent | None = None,
    executor: ExecutionAgent | None = None,
    verifier: VerifierAgent | None = None,
    reflection_agent: ReflectionAgent | None = None,
    task_state_manager: TaskStateManager | None = None,
    existing_plan: Plan | None = None,
    max_iterations: int = 200,  # Increased for complex multi-step tasks
    max_verification_loops: int = 3,  # Allow more revision attempts
    event_queue: asyncio.Queue | None = None,
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
        # Plan validation state
        plan_validation_failed=False,
        # User intent tracking
        user_intent=None,
        intent_tracker=None,
        human_input_reason=None,
        # Requirement progress tracking
        requirement_progress=[],
        constraint_violations=[],
        intent_alignment_score=0.0,
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
        # Tool results for CoVe
        tool_results=[],
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
        # Phase 2: Browser node fields
        browser_task=None,
        cdp_url=None,
        browser_result=None,
    )
