"""Execution node for the LangGraph PlanAct workflow.

This node executes the next step in the plan using the ExecutionAgent.
"""

import asyncio
import logging
from typing import Dict, Any

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.plan import ExecutionStatus
from app.domain.models.event import ToolEvent, WaitEvent

logger = logging.getLogger(__name__)


async def execution_node(state: PlanActState) -> Dict[str, Any]:
    """Execute the next step in the plan.

    This node gets the next pending step and invokes the ExecutionAgent
    to perform it. Tool events are collected and step status is updated.

    Args:
        state: Current workflow state

    Returns:
        State updates with step results and accumulated events
    """
    plan = state.get("plan")
    executor = state.get("executor")
    user_message = state.get("user_message")
    task_state_manager = state.get("task_state_manager")

    if not plan:
        logger.warning("Execution node: no plan available")
        return {
            "error": "No plan available for execution",
            "pending_events": [],
        }

    if not executor:
        logger.error("Execution node: no executor available")
        return {
            "error": "No executor available",
            "pending_events": [],
        }

    # Mark plan as running
    plan.status = ExecutionStatus.RUNNING

    # Get the next step to execute
    step = plan.get_next_step()

    if not step:
        logger.info("Execution node: no more steps to execute")
        return {
            "all_steps_done": True,
            "current_step": None,
            "pending_events": [],
        }

    # Check if step is blocked
    if step.status == ExecutionStatus.BLOCKED:
        logger.info(f"Skipping blocked step {step.id}: {step.notes or 'blocked by dependency'}")
        if task_state_manager:
            task_state_manager.update_step_status(str(step.id), "blocked")
        return {
            "current_step": step,
            "pending_events": [],
        }

    logger.info(f"Executing step {step.id}: {step.description[:50]}...")

    # Mark step as in progress
    if task_state_manager:
        task_state_manager.update_step_status(str(step.id), "in_progress")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    # Execute the step
    pending_events = []
    recent_tools = []
    needs_human_input = False
    last_had_error = False

    async for event in executor.execute_step(plan, step, user_message):
        # Stream event in real-time if queue available
        if event_queue:
            await event_queue.put(event)
        else:
            # Fallback: batch events for later
            pending_events.append(event)

        # Track tool usage
        if isinstance(event, ToolEvent) and event.tool_name:
            recent_tools.append(event.function_name)

        # Check for wait event (human input needed)
        if isinstance(event, WaitEvent):
            needs_human_input = True

    # Update task state after execution
    if task_state_manager:
        if step.status == ExecutionStatus.COMPLETED:
            task_state_manager.update_step_status(str(step.id), "completed")
        elif step.status == ExecutionStatus.FAILED:
            task_state_manager.update_step_status(str(step.id), "failed")
            last_had_error = True

    # Handle step failure - cascade blocking to dependent steps
    if not step.success and step.status == ExecutionStatus.FAILED:
        reason = step.error or step.result or "Step execution failed"
        blocked_ids = plan.mark_blocked_cascade(step.id, reason[:200])
        if blocked_ids:
            logger.info(f"Step {step.id} failure blocked {len(blocked_ids)} dependent steps")

    return {
        "current_step": step,
        "plan": plan,  # Plan may have been modified
        "needs_human_input": needs_human_input,
        "last_had_error": last_had_error,
        "pending_events": pending_events,
        "recent_tools": recent_tools,
    }
