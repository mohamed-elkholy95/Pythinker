"""Reflection node for the LangGraph PlanAct workflow.

This node performs self-reflection on progress using the ReflectionAgent.
"""

import logging
from typing import Dict, Any

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.event import ReflectionEvent, ReflectionStatus

logger = logging.getLogger(__name__)


async def reflection_node(state: PlanActState) -> Dict[str, Any]:
    """Reflect on progress and determine course correction.

    This node implements Phase 2 Enhanced Self-Reflection by analyzing
    execution progress and deciding whether to continue, adjust, replan,
    or escalate.

    Args:
        state: Current workflow state

    Returns:
        State updates with reflection decision and feedback
    """
    reflection_agent = state.get("reflection_agent")
    plan = state.get("plan")
    task_state_manager = state.get("task_state_manager")

    # No reflection configured - continue
    if not reflection_agent:
        logger.debug("No reflection agent configured, continuing")
        return {
            "reflection_decision": "continue",
            "pending_events": [],
        }

    if not plan or not task_state_manager:
        logger.debug("Missing plan or task state manager for reflection")
        return {
            "reflection_decision": "continue",
            "pending_events": [],
        }

    # Get progress metrics
    progress = task_state_manager.get_progress_metrics()
    if not progress:
        return {
            "reflection_decision": "continue",
            "pending_events": [],
        }

    # Check if reflection should be triggered
    trigger_type = reflection_agent.should_reflect(
        progress=progress,
        last_had_error=state.get("last_had_error", False),
        confidence=1.0  # Could be dynamic based on context
    )

    if not trigger_type:
        return {
            "reflection_decision": "continue",
            "pending_events": [],
        }

    logger.info(f"Reflecting on progress: trigger={trigger_type.value}")

    pending_events = []
    decision = "continue"
    feedback = None

    # Perform reflection
    async for event in reflection_agent.reflect(
        goal=plan.goal,
        plan=plan,
        progress=progress,
        trigger_type=trigger_type,
        recent_actions=task_state_manager.get_recent_actions(),
        last_error=task_state_manager.get_last_error()
    ):
        pending_events.append(event)

        # Capture reflection decision
        if isinstance(event, ReflectionEvent) and event.status == ReflectionStatus.COMPLETED:
            decision = event.decision
            if event.decision in ["adjust", "replan"]:
                feedback = event.summary

    return {
        "reflection_decision": decision,
        "reflection_feedback": feedback if feedback else None,
        "last_had_error": False,  # Reset after reflection
        "pending_events": pending_events,
    }
