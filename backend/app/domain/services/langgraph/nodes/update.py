"""Update node for the LangGraph PlanAct workflow.

This node updates the plan after step completion using the PlannerAgent.
Also handles state pruning to prevent unbounded growth.
"""

import asyncio
import logging
from typing import Any

from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# P1.3: State pruning limits to prevent unbounded memory growth
MAX_PENDING_EVENTS = 100
MAX_RECENT_ACTIONS = 50
MAX_RECENT_TOOLS = 100


def prune_accumulated_state(state: PlanActState) -> dict[str, Any]:
    """Prune accumulated state fields to prevent unbounded growth.

    This function is called during the update node to ensure that
    accumulated lists don't grow indefinitely, which could cause
    memory issues during long-running workflows.

    Args:
        state: Current workflow state

    Returns:
        Dict with pruned state updates (only fields that need pruning)
    """
    updates: dict[str, Any] = {}

    # Prune pending_events - keep most recent
    pending_events = state.get("pending_events", [])
    if len(pending_events) > MAX_PENDING_EVENTS:
        pruned_count = len(pending_events) - MAX_PENDING_EVENTS
        updates["pending_events"] = pending_events[-MAX_PENDING_EVENTS:]
        logger.debug(f"Pruned {pruned_count} old events from pending_events")

    # Prune recent_actions - keep most recent
    recent_actions = state.get("recent_actions", [])
    if recent_actions and len(recent_actions) > MAX_RECENT_ACTIONS:
        pruned_count = len(recent_actions) - MAX_RECENT_ACTIONS
        updates["recent_actions"] = recent_actions[-MAX_RECENT_ACTIONS:]
        logger.debug(f"Pruned {pruned_count} old actions from recent_actions")

    # Prune recent_tools - keep most recent
    recent_tools = state.get("recent_tools", [])
    if recent_tools and len(recent_tools) > MAX_RECENT_TOOLS:
        pruned_count = len(recent_tools) - MAX_RECENT_TOOLS
        updates["recent_tools"] = recent_tools[-MAX_RECENT_TOOLS:]
        logger.debug(f"Pruned {pruned_count} old tools from recent_tools")

    return updates


async def update_node(state: PlanActState) -> dict[str, Any]:
    """Update the plan after step completion.

    This node invokes the PlannerAgent to update the plan based on
    the results of the completed step. Also tracks iteration count
    for budget management.

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

    # Increment iteration count
    iteration_count = state.get("iteration_count", 0) + 1
    max_iterations = state.get("max_iterations", 200)

    # Check if we're approaching the limit
    if iteration_count >= max_iterations * 0.9:
        logger.warning(
            f"Approaching iteration limit: {iteration_count}/{max_iterations} "
            f"({iteration_count / max_iterations * 100:.0f}%)"
        )

    # Check if limit exceeded - trigger graceful completion
    if iteration_count >= max_iterations:
        logger.warning(
            f"Iteration limit reached ({iteration_count}/{max_iterations}), "
            "marking remaining steps as blocked and proceeding to summary"
        )
        # Mark remaining steps as blocked
        from app.domain.models.plan import ExecutionStatus

        for step in plan.steps:
            if step.status == ExecutionStatus.PENDING:
                step.status = ExecutionStatus.BLOCKED
                step.notes = "Skipped due to iteration limit"
        return {
            "plan": plan,
            "iteration_count": iteration_count,
            "all_steps_done": True,  # Force completion
            "pending_events": [],
        }

    logger.info(f"Updating plan after step {current_step.id} (iteration {iteration_count})")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []

    async for event in planner.update_plan(plan, current_step):
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # P1.3: Prune accumulated state to prevent memory growth
    pruned_updates = prune_accumulated_state(state)

    return {
        "plan": plan,
        "iteration_count": iteration_count,
        "pending_events": pending_events,
        **pruned_updates,  # Apply any pruning updates
    }
