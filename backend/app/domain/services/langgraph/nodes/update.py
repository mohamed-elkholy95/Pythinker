"""Update node for the LangGraph PlanAct workflow.

This node updates the plan after step completion using the PlannerAgent.
"""

import asyncio
import logging
from typing import Dict, Any

from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)


async def update_node(state: PlanActState) -> Dict[str, Any]:
    """Update the plan after step completion.

    This node invokes the PlannerAgent to update the plan based on
    the results of the completed step.

    Args:
        state: Current workflow state

    Returns:
        State updates with the modified plan and accumulated events
    """
    planner = state.get("planner")
    plan = state.get("plan")
    current_step = state.get("current_step")

    if not planner or not plan or not current_step:
        logger.warning("Update node: missing planner, plan, or current step")
        return {
            "pending_events": [],
        }

    logger.info(f"Updating plan after step {current_step.id}")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []

    async for event in planner.update_plan(plan, current_step):
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    return {
        "plan": plan,
        "pending_events": pending_events,
    }
