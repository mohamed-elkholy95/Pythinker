"""Reflection node for the LangGraph PlanAct workflow.

This node performs self-reflection on progress using the ReflectionAgent.
Enhanced with:
- Grounding validation for hallucination prevention
- Intent tracking for user prompt adherence
- Drift detection for scope management
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.event import ReflectionEvent, ReflectionStatus

# P0 Priority: Hallucination Prevention & Prompt Adherence
from app.domain.services.agents.grounding_validator import (
    get_grounding_validator,
    GroundingLevel,
)
from app.domain.services.agents.intent_tracker import get_intent_tracker

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

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []
    decision = "continue"
    feedback = None
    additional_guidance = []

    # === P0: Grounding Validation ===
    # Check if recent execution results are grounded in context
    recent_actions = state.get("recent_actions", [])
    user_message = state.get("user_message")
    execution_context = state.get("execution_context", "")

    if recent_actions and execution_context:
        grounding_validator = get_grounding_validator()
        # Combine recent action results for grounding check
        recent_results = " ".join(
            str(action.get("result", ""))
            for action in recent_actions[-5:]  # Last 5 actions
            if action.get("success")
        )

        if recent_results:
            grounding_result = grounding_validator.validate(
                source=execution_context,
                query=user_message.message if user_message else "",
                response=recent_results,
            )

            if grounding_result.needs_revision:
                logger.warning(
                    f"Grounding check failed: level={grounding_result.level.value}, "
                    f"ungrounded_claims={len(grounding_result.ungrounded_claims)}"
                )
                additional_guidance.append(grounding_result.get_revision_guidance())

                # If severely ungrounded, suggest replan
                if grounding_result.level == GroundingLevel.UNGROUNDED:
                    decision = "replan"
                    feedback = "Execution results not grounded in source context. Need to verify claims."

    # === P0: Intent Tracking ===
    # Check alignment with user's original intent
    intent_tracker = get_intent_tracker()

    if plan and user_message:
        # Extract intent if not already done
        current_intent = intent_tracker._current_intent
        if not current_intent:
            intent_tracker.extract_intent(user_message.message)

        # Get current work summary from recent actions
        current_work = " ".join(
            f"{action.get('function_name', '')}: {action.get('result', '')[:100]}"
            for action in recent_actions[-10:]
        )

        # Check alignment
        alignment_result = intent_tracker.check_alignment(
            current_work=current_work,
            plan_steps=[step.description for step in plan.steps],
        )

        if alignment_result.needs_correction:
            logger.warning(
                f"Intent alignment issue: coverage={alignment_result.coverage_percent:.1f}%, "
                f"drift_alerts={len(alignment_result.drift_alerts)}"
            )

            if alignment_result.guidance:
                additional_guidance.append(alignment_result.guidance)

            # Severe drift -> suggest replan
            if alignment_result.coverage_percent < 30 or len(alignment_result.drift_alerts) >= 2:
                decision = "replan"
                feedback = f"Execution drifted from user intent. Coverage: {alignment_result.coverage_percent:.0f}%"

        # Mark addressed requirements from completed steps
        completed_steps = [s for s in plan.steps if s.is_done() and s.success]
        for step in completed_steps:
            intent_tracker.mark_addressed(
                requirement=step.description,
                step_id=str(step.id),
            )

    # Perform reflection
    async for event in reflection_agent.reflect(
        goal=plan.goal,
        plan=plan,
        progress=progress,
        trigger_type=trigger_type,
        recent_actions=task_state_manager.get_recent_actions(),
        last_error=task_state_manager.get_last_error()
    ):
        # Stream event in real-time if queue available
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

        # Capture reflection decision
        if isinstance(event, ReflectionEvent) and event.status == ReflectionStatus.COMPLETED:
            decision = event.decision
            if event.decision in ["adjust", "replan"]:
                feedback = event.summary

    # Combine feedback with additional guidance
    combined_feedback = feedback or ""
    if additional_guidance:
        if combined_feedback:
            combined_feedback += "\n\n"
        combined_feedback += "\n".join(additional_guidance)

    return {
        "reflection_decision": decision,
        "reflection_feedback": combined_feedback if combined_feedback else None,
        "last_had_error": False,  # Reset after reflection
        "pending_events": pending_events,
        "grounding_checked": True,  # Flag that grounding was validated
        "intent_checked": True,     # Flag that intent was verified
    }
