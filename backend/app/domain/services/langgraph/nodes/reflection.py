"""Reflection node for the LangGraph PlanAct workflow.

This node performs self-reflection on progress using the ReflectionAgent.
Enhanced with:
- Grounding validation for hallucination prevention
- Intent tracking for user prompt adherence
- Drift detection for scope management
- Stuck pattern analysis for targeted recovery guidance
"""

import asyncio
import logging
from typing import Any

from app.core.alert_manager import get_alert_manager
from app.core.config import get_feature_flags
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.event import ReflectionEvent, ReflectionStatus
from app.domain.models.reflection import ReflectionTriggerType

# P0 Priority: Hallucination Prevention & Prompt Adherence
from app.domain.services.agents.grounding_validator import (
    GroundingLevel,
    get_grounding_validator,
)
from app.domain.services.agents.intent_tracker import get_intent_tracker
from app.domain.services.agents.memory_manager import get_memory_manager
from app.domain.services.agents.stuck_detector import LoopType, StuckAnalysis
from app.domain.services.langgraph.state import PlanActState
from app.domain.services.prediction.failure_predictor import FailurePredictor

# Module-level metrics instance (can be overridden for testing)
_metrics: MetricsPort = get_null_metrics()


def set_metrics(metrics: MetricsPort) -> None:
    """Set the metrics instance for this module."""
    global _metrics
    _metrics = metrics


def _record_failure_prediction(prediction: str, confidence: float) -> None:
    """Record failure prediction metric."""
    _metrics.record_failure_prediction(prediction, confidence)


logger = logging.getLogger(__name__)


async def reflection_node(state: PlanActState) -> dict[str, Any]:
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
        confidence=1.0,  # Could be dynamic based on context
        recent_actions=task_state_manager.get_recent_actions() if task_state_manager else None,
    )

    # Failure prediction (Phase 5, shadow mode)
    prediction = None
    flags = get_feature_flags()
    if flags.get("failure_prediction"):
        try:
            token_usage_pct = None
            executor = state.get("executor")
            if executor:
                try:
                    memory_manager = get_memory_manager()
                    await executor._ensure_memory()
                    pressure = memory_manager.get_pressure_status(executor.memory.estimate_tokens())
                    token_usage_pct = pressure.usage_ratio
                except Exception as e:
                    logger.debug(f"Token pressure lookup failed: {e}")

            predictor = FailurePredictor()
            prediction = predictor.predict(
                progress=progress,
                recent_actions=task_state_manager.get_recent_actions(),
                stuck_analysis=state.get("stuck_analysis"),
                token_usage_pct=token_usage_pct,
            )
            _record_failure_prediction(
                "predicted" if prediction.will_fail else "clear",
                prediction.probability,
            )
            await get_alert_manager().check_thresholds(
                state.get("session_id") or "unknown",
                {"failure_prediction_probability": prediction.probability},
            )
            if prediction.will_fail and not trigger_type:
                trigger_type = ReflectionTriggerType.EXPLICIT
        except Exception as e:
            logger.debug(f"Failure prediction failed: {e}")

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

    # === P0: Stuck Pattern Analysis ===
    # Check if execution detected any stuck patterns
    stuck_analysis: StuckAnalysis | None = state.get("stuck_analysis")

    if stuck_analysis:
        logger.warning(
            f"Reflection received stuck analysis: {stuck_analysis.loop_type.value} "
            f"(confidence: {stuck_analysis.confidence:.2f})"
        )

        # Add stuck-specific guidance
        stuck_guidance = _get_stuck_recovery_guidance(stuck_analysis)
        if stuck_guidance:
            additional_guidance.append(stuck_guidance)

        # Severe stuck patterns may require replanning or aborting
        severe_patterns = {
            LoopType.TOOL_FAILURE_CASCADE,
            LoopType.REPEATING_ACTION_ERROR,
            LoopType.BROWSER_CLICK_FAILURES,
        }

        if stuck_analysis.loop_type in severe_patterns and stuck_analysis.confidence > 0.8:
            # Very high confidence stuck with cascade = abort (summarize what we have)
            if stuck_analysis.confidence > 0.95 and stuck_analysis.loop_type == LoopType.TOOL_FAILURE_CASCADE:
                decision = "abort"
                feedback = (
                    f"Aborting: systemic failure in {stuck_analysis.loop_type.value} "
                    f"(confidence: {stuck_analysis.confidence:.0%}). {stuck_analysis.details}"
                )
            else:
                decision = "replan"
                feedback = f"Stuck in {stuck_analysis.loop_type.value}: {stuck_analysis.details}"

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
            f"{action.get('function_name', '')}: {action.get('result', '')[:100]}" for action in recent_actions[-10:]
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
        last_error=task_state_manager.get_last_error(),
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

    if prediction and prediction.will_fail and decision == "continue":
        decision = "adjust"
        prediction_feedback = (
            f"Failure prediction: {prediction.probability:.0%} risk. "
            f"Factors: {', '.join(prediction.factors) or 'unknown'}. "
            f"Recommended: {prediction.recommended_action}."
        )
        combined_feedback = (
            f"{combined_feedback}\n\n{prediction_feedback}" if combined_feedback else prediction_feedback
        )

    return {
        "reflection_decision": decision,
        "reflection_feedback": combined_feedback if combined_feedback else None,
        "last_had_error": False,  # Reset after reflection
        "pending_events": pending_events,
        "grounding_checked": True,  # Flag that grounding was validated
        "intent_checked": True,  # Flag that intent was verified
        "stuck_analysis": None,  # Clear stuck analysis after reflection
    }


def _get_stuck_recovery_guidance(analysis: StuckAnalysis) -> str:
    """Generate recovery guidance based on stuck analysis.

    Provides targeted advice for breaking out of different stuck patterns,
    especially browser-specific issues.

    Args:
        analysis: The stuck analysis from execution

    Returns:
        Recovery guidance string
    """
    guidance_map = {
        LoopType.BROWSER_SAME_PAGE_LOOP: (
            "BROWSER STUCK: Navigating to the same page repeatedly.\n"
            "RECOVERY: The page is already loaded. Use browser_view to see content, "
            "or interact with elements (click, input) instead of re-navigating."
        ),
        LoopType.BROWSER_SCROLL_NO_PROGRESS: (
            "BROWSER STUCK: Scrolling without extracting content.\n"
            "RECOVERY: After scrolling, use browser_view to see the newly loaded content. "
            "Then extract the information you need."
        ),
        LoopType.BROWSER_CLICK_FAILURES: (
            "BROWSER STUCK: Click attempts failing repeatedly.\n"
            "RECOVERY: Element indices may have changed. Use browser_view to get fresh "
            "interactive element indices before clicking."
        ),
        LoopType.REPEATING_ACTION_OBSERVATION: (
            "STUCK: Same action producing same result repeatedly.\n"
            "RECOVERY: Process the data you already have instead of re-fetching. "
            "Move on to the next step."
        ),
        LoopType.REPEATING_ACTION_ERROR: (
            "STUCK: Same action failing repeatedly.\n"
            "RECOVERY: Analyze the error message. Fix the root cause or try an "
            "alternative approach instead of retrying."
        ),
        LoopType.ALTERNATING_PATTERN: (
            "STUCK: Oscillating between two approaches without progress.\n"
            "RECOVERY: Commit to ONE approach, or try a completely different strategy."
        ),
        LoopType.TOOL_FAILURE_CASCADE: (
            "STUCK: Multiple tools failing - possible systemic issue.\n"
            "RECOVERY: Check environment setup. Try simpler operations to diagnose. "
            "May need to escalate to user."
        ),
    }

    base_guidance = guidance_map.get(analysis.loop_type, "")

    if base_guidance:
        return f"{base_guidance}\nDetails: {analysis.details}"

    return f"Stuck pattern detected: {analysis.loop_type.value}. {analysis.details}"
