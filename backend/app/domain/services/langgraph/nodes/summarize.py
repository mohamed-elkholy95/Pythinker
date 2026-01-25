"""Summarize node for the LangGraph PlanAct workflow.

This node generates the final summary using the ExecutionAgent.
"""

import asyncio
import logging
from typing import Dict, Any

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.plan import ExecutionStatus
from app.domain.models.event import PlanEvent, PlanStatus, DoneEvent

logger = logging.getLogger(__name__)


async def summarize_node(state: PlanActState) -> Dict[str, Any]:
    """Summarize the completed work.

    This node invokes the ExecutionAgent to generate a summary of
    the completed task and emits completion events.

    Args:
        state: Current workflow state

    Returns:
        State updates with summary events
    """
    executor = state.get("executor")
    plan = state.get("plan")

    if not executor:
        logger.warning("Summarize node: no executor available")
        return {
            "pending_events": [DoneEvent()],
        }

    logger.info("Summarizing completed work")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []

    async for event in executor.summarize():
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Mark plan as completed and emit completion event
    if plan:
        plan.status = ExecutionStatus.COMPLETED
        plan_event = PlanEvent(status=PlanStatus.COMPLETED, plan=plan)
        if event_queue:
            await event_queue.put(plan_event)
        else:
            pending_events.append(plan_event)

    # Always emit done event at the end
    done_event = DoneEvent()
    if event_queue:
        await event_queue.put(done_event)
    else:
        pending_events.append(done_event)

    return {
        "plan": plan,
        "pending_events": pending_events,
    }
