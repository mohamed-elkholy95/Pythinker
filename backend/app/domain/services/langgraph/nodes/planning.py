"""Planning node for the LangGraph PlanAct workflow.

This node wraps the PlannerAgent to create or update plans.
"""

import asyncio
import logging
from typing import Dict, Any

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.event import PlanEvent, PlanStatus, TitleEvent

logger = logging.getLogger(__name__)


async def planning_node(state: PlanActState) -> Dict[str, Any]:
    """Create or revise the execution plan.

    This node invokes the PlannerAgent to create a plan from the user message.
    If verification feedback is present, it passes that context for revision.

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

    # Check if this is a replan due to verification feedback
    replan_context = None
    if state.get("verification_feedback") and state.get("verification_verdict") == "revise":
        replan_context = state.get("verification_feedback")
        logger.info("Replanning with verification feedback")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

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
    }
