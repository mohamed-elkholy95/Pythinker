"""Planning node for the LangGraph PlanAct workflow.

This node wraps the PlannerAgent to create or update plans.
Enhanced with:
- Input guardrails for prompt injection/jailbreak detection
- Intent extraction for user prompt adherence tracking
- Parallel tool prefetching for reduced latency
"""

import asyncio
import logging
from typing import Any

from app.domain.models.event import ErrorEvent, PlanEvent, PlanStatus, TitleEvent

# P0 Priority: Input Guardrails
from app.domain.services.agents.guardrails import InputRiskLevel, get_guardrails_manager
from app.domain.services.agents.intent_tracker import get_intent_tracker
from app.domain.services.langgraph.state import PlanActState
from app.domain.services.tools.dynamic_toolset import get_toolset_manager

logger = logging.getLogger(__name__)


async def _prefetch_tools_for_task(
    user_message_text: str,
    include_mcp: bool = True
) -> list[dict[str, Any]] | None:
    """Prefetch tools in background while planning proceeds.

    Args:
        user_message_text: The user's message text
        include_mcp: Whether to include MCP tools

    Returns:
        List of prefetched tool schemas, or None on error
    """
    try:
        toolset_manager = get_toolset_manager()

        # Use the async prefetch method
        tools = await toolset_manager.prefetch_tools_async(
            user_message_text,
            include_mcp=include_mcp
        )

        logger.debug(f"Prefetched {len(tools)} tools for planning")
        return tools

    except Exception as e:
        logger.warning(f"Tool prefetch failed (non-blocking): {e}")
        return None


async def planning_node(state: PlanActState) -> dict[str, Any]:
    """Create or revise the execution plan.

    This node invokes the PlannerAgent to create a plan from the user message.
    If verification feedback is present, it passes that context for revision.

    Optimization: Starts tool prefetching in parallel with plan creation
    to reduce overall latency.

    Args:
        state: Current workflow state

    Returns:
        State updates including the new plan and accumulated events
    """
    planner = state.get("planner")
    user_message = state.get("user_message")
    task_state_manager = state.get("task_state_manager")

    if not planner or not user_message:
        logger.error("Planning node missing required agents or message")
        return {
            "error": "Planning node missing required agents or message",
            "pending_events": [],
        }

    logger.info(f"Planning node: creating plan for session {state.get('session_id')}")

    # === P0: Input Guardrails Check ===
    # Screen user input for prompt injection, jailbreak attempts, etc.
    message_text = user_message.message if hasattr(user_message, 'message') else str(user_message)
    guardrails = get_guardrails_manager()
    input_result = guardrails.check_input(message_text)

    if input_result.risk_level == InputRiskLevel.BLOCKED:
        logger.warning(
            f"Input blocked by guardrails: {len(input_result.issues)} issues, "
            f"types={[i.issue_type.value for i in input_result.issues]}"
        )
        # Return error event - don't proceed with planning
        error_event = ErrorEvent(
            error="I cannot process this request as it appears to contain problematic content. "
                  "Please rephrase your request."
        )
        return {
            "error": "Input blocked by guardrails",
            "pending_events": [error_event],
            "input_blocked": True,
        }

    if input_result.needs_clarification:
        logger.info(f"Input needs clarification: {input_result.clarification_questions}")
        # Could trigger a clarification flow here in the future

    # Use cleaned input if guardrails modified it
    if input_result.cleaned_input and input_result.cleaned_input != message_text:
        logger.debug("Using guardrail-sanitized input")
        # Note: We log but don't modify - let planner see original for context

    # === P0: Intent Extraction ===
    # Extract user intent for tracking throughout execution
    intent_tracker = get_intent_tracker()
    user_intent = intent_tracker.extract_intent(message_text)
    logger.info(
        f"Extracted user intent: type={user_intent.intent_type.value}, "
        f"requirements={len(user_intent.explicit_requirements)}"
    )

    # Check if this is a replan due to verification feedback
    replan_context = None
    if state.get("verification_feedback") and state.get("verification_verdict") == "revise":
        replan_context = state.get("verification_feedback")
        logger.info("Replanning with verification feedback")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    # Start tool prefetch in background (runs parallel to planning)
    # This reduces latency by preparing tools while the plan is being created
    message_text = user_message.message if hasattr(user_message, 'message') else str(user_message)
    prefetch_task = asyncio.create_task(
        _prefetch_tools_for_task(message_text, include_mcp=True)
    )

    # Collect events from the planner
    pending_events = []
    plan = None
    plan_created = False

    async for event in planner.create_plan(user_message, replan_context=replan_context):
        if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
            plan = event.plan
            plan_created = True

            # Infer sequential dependencies for BLOCKED cascade
            plan.infer_sequential_dependencies()

            # Initialize task state for recitation
            if task_state_manager:
                task_state_manager.initialize_from_plan(
                    objective=user_message.message,
                    steps=[{"id": s.id, "description": s.description} for s in plan.steps]
                )

            # Emit title event
            title_event = TitleEvent(title=plan.title)
            if event_queue:
                await event_queue.put(title_event)
            else:
                pending_events.append(title_event)

        # Stream event in real-time if queue available
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Await prefetch completion (should already be done by now)
    prefetched_tools = None
    try:
        prefetched_tools = await prefetch_task
        if prefetched_tools:
            logger.debug(f"Tool prefetch completed: {len(prefetched_tools)} tools ready")
    except Exception as e:
        logger.warning(f"Tool prefetch await failed: {e}")

    # Check if plan has no steps (direct completion)
    all_steps_done = False
    if plan and len(plan.steps) == 0:
        logger.info("Plan created with no steps - marking as done")
        all_steps_done = True

    return {
        "plan": plan,
        "plan_created": plan_created,
        "all_steps_done": all_steps_done,
        # Reset verification state after replanning
        "verification_verdict": None,
        "verification_feedback": None,
        "pending_events": pending_events,
        "iteration_count": state.get("iteration_count", 0) + 1,
        # Include prefetched tools for execution node
        "prefetched_tools": prefetched_tools,
    }
