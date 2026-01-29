"""Verification node for the LangGraph PlanAct workflow.

This node verifies plans before execution using the VerifierAgent.
"""

import asyncio
import logging
from typing import Any

from app.domain.models.event import VerificationEvent, VerificationStatus
from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)


async def verification_node(state: PlanActState) -> dict[str, Any]:
    """Verify the plan before execution.

    This node implements the Plan-Verify-Execute pattern by checking
    the plan's feasibility before proceeding to execution.

    Args:
        state: Current workflow state

    Returns:
        State updates with verification verdict and feedback
    """
    plan = state.get("plan")
    verifier = state.get("verifier")
    user_message = state.get("user_message")

    # No verifier configured - pass through
    if not verifier:
        logger.debug("No verifier configured, passing plan through")
        return {
            "verification_verdict": "pass",
            "pending_events": [],
        }

    if not plan:
        logger.warning("Verification node: no plan to verify")
        return {
            "verification_verdict": "pass",
            "pending_events": [],
        }

    logger.info(f"Verifying plan: {plan.title} ({len(plan.steps)} steps)")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []
    verdict = None
    feedback = None
    loops = state.get("verification_loops", 0)

    async for event in verifier.verify_plan(
        plan=plan,
        user_request=user_message.message if user_message else "",
        task_context=""
    ):
        # Stream event in real-time if queue available
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

        # Capture the verification result
        if isinstance(event, VerificationEvent):
            if event.status == VerificationStatus.PASSED:
                verdict = "pass"
            elif event.status == VerificationStatus.REVISION_NEEDED:
                verdict = "revise"
                feedback = event.revision_feedback
                loops += 1
            elif event.status == VerificationStatus.FAILED:
                verdict = "fail"

    return {
        "verification_verdict": verdict,
        "verification_feedback": feedback,
        "verification_loops": loops,
        "pending_events": pending_events,
    }
