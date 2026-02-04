"""Update node for the LangGraph PlanAct workflow.

This node updates the plan after step completion using the PlannerAgent.
Also handles state pruning to prevent unbounded growth.

Enhanced with:
- Requirement progress tracking (Phase 3: User Prompt Following)
"""

import asyncio
import logging
from typing import Any

from app.domain.services.langgraph.state import PlanActState, RequirementProgress

logger = logging.getLogger(__name__)

# P1.3: State pruning limits to prevent unbounded memory growth
MAX_PENDING_EVENTS = 100
MAX_RECENT_ACTIONS = 50
MAX_RECENT_TOOLS = 100

# Requirement progress tracking constants
REQUIREMENT_ADDRESSED_CONFIDENCE = 0.8  # Confidence when semantically matched
MAX_EVIDENCE_LENGTH = 200  # Max characters for evidence snippet


def _get_step_output(state: PlanActState) -> str:
    """Extract the output from the most recently completed step.

    Looks at tool results and step notes to construct a summary of what
    the step accomplished.

    Args:
        state: Current workflow state

    Returns:
        String representation of step output
    """
    outputs = []

    # Get current step notes
    current_step = state.get("current_step")
    if current_step and current_step.notes:
        outputs.append(current_step.notes)

    # Get recent tool results
    tool_results = state.get("tool_results", [])
    if tool_results:
        # Get the last few results (most relevant to completed step)
        recent_results = tool_results[-3:]
        for result in recent_results:
            if isinstance(result, dict):
                # Handle dict-style results
                output = result.get("output") or result.get("result") or result.get("content")
                if output:
                    outputs.append(str(output)[:500])
            elif hasattr(result, "output"):
                # Handle ToolResult objects
                if result.output:
                    outputs.append(str(result.output)[:500])

    return "\n".join(outputs) if outputs else ""


def _update_requirement_progress(
    state: PlanActState,
) -> tuple[list[RequirementProgress], float]:
    """Update requirement progress after step completion.

    Checks each unaddressed requirement against the completed step's output
    using semantic matching from the IntentTracker.

    Args:
        state: Current workflow state

    Returns:
        Tuple of (updated progress list, alignment score)
    """
    intent_tracker = state.get("intent_tracker")
    user_intent = state.get("user_intent")
    current_step = state.get("current_step")
    current_progress = state.get("requirement_progress", [])

    if not intent_tracker or not user_intent or not current_step:
        # No intent tracking available, return existing progress
        return current_progress, state.get("intent_alignment_score", 0.0)

    # Get step output for semantic matching
    step_output = _get_step_output(state)
    step_context = f"{current_step.description}\n{step_output}"

    # Create updated progress list
    updated_progress: list[RequirementProgress] = []

    for req_progress in current_progress:
        if req_progress.is_addressed:
            # Already addressed, keep as-is
            updated_progress.append(req_progress)
        else:
            # Check if this step addressed the requirement
            is_addressed = intent_tracker.check_requirement_addressed(
                requirement=req_progress.requirement,
                work_done=step_context,
                threshold=0.3,  # Use lower threshold for progress tracking
            )

            if is_addressed:
                # Create new progress object with updated state
                updated_req = RequirementProgress(
                    requirement=req_progress.requirement,
                    is_addressed=True,
                    confidence=REQUIREMENT_ADDRESSED_CONFIDENCE,
                    addressed_by_step=current_step.id,
                    evidence=step_output[:MAX_EVIDENCE_LENGTH] if step_output else None,
                )
                updated_progress.append(updated_req)
                logger.debug(f"Requirement addressed by step {current_step.id}: {req_progress.requirement[:50]}...")
            else:
                updated_progress.append(req_progress)

    # Calculate alignment score
    addressed_count = sum(1 for r in updated_progress if r.is_addressed)
    total_count = len(updated_progress) or 1
    alignment_score = addressed_count / total_count

    return updated_progress, alignment_score


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

    # Phase 3: Update requirement progress after step completion
    requirement_progress, alignment_score = _update_requirement_progress(state)

    # Log progress periodically
    if requirement_progress:
        addressed = sum(1 for r in requirement_progress if r.is_addressed)
        total = len(requirement_progress)
        logger.debug(f"Requirement progress: {addressed}/{total} addressed (alignment: {alignment_score:.1%})")

    return {
        "plan": plan,
        "iteration_count": iteration_count,
        "pending_events": pending_events,
        "requirement_progress": requirement_progress,
        "intent_alignment_score": alignment_score,
        **pruned_updates,  # Apply any pruning updates
    }
