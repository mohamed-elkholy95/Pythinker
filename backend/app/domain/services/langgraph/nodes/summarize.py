"""Summarize node for the LangGraph PlanAct workflow.

This node generates the final summary using the ExecutionAgent.
Includes output validation for hallucination detection (logging only, non-blocking).
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.plan import ExecutionStatus
from app.domain.models.event import PlanEvent, PlanStatus, DoneEvent, MessageEvent
from app.domain.services.agents.content_hallucination_detector import (
    ContentHallucinationDetector,
    HallucinationAnalysisResult,
)
from app.domain.models.source_attribution import SourceAttribution, AttributionSummary

logger = logging.getLogger(__name__)

# Singleton hallucination detector for validation
_output_validator: Optional[ContentHallucinationDetector] = None


def get_output_validator() -> ContentHallucinationDetector:
    """Get or create shared output validator."""
    global _output_validator
    if _output_validator is None:
        _output_validator = ContentHallucinationDetector()
    return _output_validator


def _validate_output(
    output: str,
    source_attributions: Optional[List[SourceAttribution]] = None
) -> Dict[str, Any]:
    """Validate output for potential hallucinations (non-blocking).

    This is a logging-only validation that doesn't block delivery.
    Results are logged for monitoring and optionally added to metadata.

    Args:
        output: The summary output to validate
        source_attributions: Optional source attributions for cross-reference

    Returns:
        Validation result dict with issues and flags
    """
    validator = get_output_validator()

    # Get verified claims from attributions
    verified_claims = set()
    if source_attributions:
        verified_claims = {
            attr.claim for attr in source_attributions
            if attr.is_verified()
        }

    # Run hallucination detection
    result = validator.analyze(output, verified_claims)

    validation_result = {
        "passed": not result.has_high_risk_patterns,
        "issues": [],
        "high_risk_count": result.high_risk_count,
        "medium_risk_count": result.medium_risk_count,
    }

    if result.issues:
        validation_result["issues"] = [
            {
                "type": issue.pattern_type,
                "text": issue.matched_text[:100],
                "risk": issue.risk.value,
                "suggestion": issue.suggestion,
            }
            for issue in result.issues[:10]  # Limit to 10 issues
        ]

    return validation_result


async def summarize_node(state: PlanActState) -> Dict[str, Any]:
    """Summarize the completed work.

    This node invokes the ExecutionAgent to generate a summary of
    the completed task and emits completion events.

    Includes output validation for hallucination detection (logging only).
    Validation issues are logged for monitoring but don't block delivery.

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
    summary_content = ""

    async for event in executor.summarize():
        # Capture summary content for validation
        if isinstance(event, MessageEvent) and hasattr(event, 'message'):
            summary_content = event.message or ""

        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Perform output validation (non-blocking, logging only)
    validation_flags = []
    if summary_content and len(summary_content) > 100:
        try:
            # Get source attributions from state if available
            source_attributions = state.get("source_attributions", [])

            validation = _validate_output(summary_content, source_attributions)

            if not validation["passed"]:
                logger.warning(
                    f"Output validation flagged {validation['high_risk_count']} high-risk, "
                    f"{validation['medium_risk_count']} medium-risk potential hallucinations"
                )
                for issue in validation["issues"][:5]:
                    logger.warning(
                        f"  - {issue['type']}: '{issue['text'][:50]}...' "
                        f"({issue['risk']} risk) - {issue['suggestion']}"
                    )
                validation_flags = validation["issues"]
            else:
                logger.debug("Output validation passed with no high-risk issues")

        except Exception as e:
            # Validation errors should never block delivery
            logger.error(f"Output validation error (non-blocking): {e}")

    # Mark plan as completed and emit completion event
    if plan:
        plan.status = ExecutionStatus.COMPLETED
        # Store validation flags in plan metadata if available
        if validation_flags and hasattr(plan, 'metadata'):
            if plan.metadata is None:
                plan.metadata = {}
            plan.metadata["validation_flags"] = validation_flags

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
        "validation_flags": validation_flags,
    }
