"""Summarize node for the LangGraph PlanAct workflow.

This node generates the final summary using the ExecutionAgent.
Includes output validation for hallucination detection (logging only, non-blocking).

Phase 4 Enhancement: Integrates Chain-of-Verification (CoVe) for reports
to detect and correct fabricated claims before delivery.
"""

import asyncio
import logging
from typing import Any

from app.domain.models.event import DoneEvent, MessageEvent, PlanEvent, PlanStatus
from app.domain.models.plan import ExecutionStatus
from app.domain.models.source_attribution import SourceAttribution
from app.domain.services.agents.chain_of_verification import (
    ChainOfVerification,
    CoVeResult,
)
from app.domain.services.agents.content_hallucination_detector import (
    ContentHallucinationDetector,
)
from app.domain.services.agents.grounding_validator import (
    EnhancedGroundingValidator,
)
from app.domain.services.agents.memory_manager import get_memory_manager
from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# Singleton hallucination detector for validation
_output_validator: ContentHallucinationDetector | None = None
_enhanced_grounding_validator: EnhancedGroundingValidator | None = None


def get_output_validator() -> ContentHallucinationDetector:
    """Get or create shared output validator."""
    global _output_validator
    if _output_validator is None:
        _output_validator = ContentHallucinationDetector()
    return _output_validator


def get_enhanced_grounding_validator() -> EnhancedGroundingValidator:
    """Get or create shared enhanced grounding validator."""
    global _enhanced_grounding_validator
    if _enhanced_grounding_validator is None:
        _enhanced_grounding_validator = EnhancedGroundingValidator(
            strict_numeric_mode=True,
        )
    return _enhanced_grounding_validator


def _validate_output(output: str, source_attributions: list[SourceAttribution] | None = None) -> dict[str, Any]:
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
        verified_claims = {attr.claim for attr in source_attributions if attr.is_verified()}

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


async def _run_cove_verification(
    content: str,
    state: PlanActState,
) -> tuple[str, CoVeResult | None]:
    """Run Chain-of-Verification on the content (Phase 4).

    This verifies claims in the content and generates a refined version
    if contradictions are found.

    Args:
        content: The summary content to verify
        state: Current workflow state for LLM access

    Returns:
        Tuple of (possibly refined content, CoVe result or None)
    """
    # Check feature flag
    feature_flags = state.get("feature_flags", {})
    if not feature_flags.get("cove_verification", True):
        logger.debug("CoVe verification disabled by feature flag")
        return content, None

    # Get LLM from executor
    executor = state.get("executor")
    if not executor:
        logger.warning("CoVe: No executor available, skipping verification")
        return content, None

    # Check minimum length (short responses don't need CoVe)
    if len(content) < 300:
        logger.debug(f"CoVe: Content too short ({len(content)} chars), skipping")
        return content, None

    try:
        # Import here to get json parser
        from app.domain.utils.json_parser import JsonParser

        json_parser = JsonParser()
        llm = executor._llm  # Access the LLM from executor

        # Create CoVe instance
        cove = ChainOfVerification(
            llm=llm,
            json_parser=json_parser,
            max_questions=5,
            parallel_verification=True,
            min_response_length=200,
        )

        # Run verification
        logger.info("Running Chain-of-Verification on summary content...")
        result = await cove.verify_and_refine(
            query="",  # No specific query context
            response=content,
            skip_if_short=True,
        )

        # Log results
        logger.info(
            f"CoVe completed: {result.claims_verified}/{len(result.verification_questions)} verified, "
            f"{result.claims_contradicted} contradicted, confidence={result.confidence_score:.2f}"
        )

        if result.claims_contradicted > 0:
            logger.warning(
                f"CoVe detected {result.claims_contradicted} contradicted claims. "
                f"Using refined response."
            )
            # Log specific contradictions
            for q in result.verification_questions:
                if q.status.value == "contradicted":
                    logger.warning(f"  CONTRADICTED: {q.claim_being_verified[:80]}...")

        # Return refined content if there were contradictions
        if result.has_contradictions:
            return result.verified_response, result
        return content, result

    except Exception as e:
        logger.error(f"CoVe verification failed (non-blocking): {e}")
        return content, None


def _run_enhanced_grounding_check(
    content: str,
    source_contents: list[str],
) -> dict[str, Any]:
    """Run enhanced grounding validation with numeric verification (Phase 3).

    Args:
        content: Content to validate
        source_contents: List of source content strings

    Returns:
        Grounding validation result
    """
    if not source_contents:
        return {"passed": True, "fabricated_claims": []}

    try:
        validator = get_enhanced_grounding_validator()
        result = validator.validate_against_sources(content, source_contents)

        grounding_result = {
            "passed": not result.has_fabricated_data,
            "overall_score": result.overall_score,
            "level": result.level.value,
            "numeric_verification_rate": result.numeric_verification_rate,
            "entity_verification_rate": result.entity_verification_rate,
            "fabricated_claims": result.fabricated_numeric_claims + result.fabricated_entity_claims,
        }

        if result.has_fabricated_data:
            logger.warning(
                f"Enhanced grounding detected fabricated data: "
                f"{len(result.fabricated_numeric_claims)} numeric, "
                f"{len(result.fabricated_entity_claims)} entity claims"
            )
            for warning in result.get_fabrication_warnings()[:5]:
                logger.warning(f"  {warning}")

        return grounding_result

    except Exception as e:
        logger.error(f"Enhanced grounding check failed: {e}")
        return {"passed": True, "error": str(e)}


async def summarize_node(state: PlanActState) -> dict[str, Any]:
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
        if isinstance(event, MessageEvent) and hasattr(event, "message"):
            summary_content = event.message or ""

        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Phase 4: Run Chain-of-Verification on summary content
    cove_result = None
    feature_flags = state.get("feature_flags", {})

    if summary_content and feature_flags.get("cove_verification", True):
        try:
            refined_content, cove_result = await _run_cove_verification(
                summary_content,
                state,
            )

            # If CoVe refined the content, update the summary
            if cove_result and cove_result.has_contradictions:
                logger.info(
                    f"CoVe refined summary: removed {cove_result.claims_contradicted} contradicted claims"
                )
                summary_content = refined_content

                # Emit updated message event with refined content
                refined_event = MessageEvent(message=refined_content)
                if event_queue:
                    await event_queue.put(refined_event)
                else:
                    pending_events.append(refined_event)

        except Exception as e:
            logger.error(f"CoVe verification error (non-blocking): {e}")

    # Phase 3: Run enhanced grounding validation with numeric verification
    grounding_result = {}
    if summary_content and feature_flags.get("enhanced_grounding", True):
        try:
            # Get source contents from state (tool results, search results)
            source_contents = []
            tool_results = state.get("tool_results", [])
            for result in tool_results:
                if isinstance(result, dict) and result.get("content"):
                    source_contents.append(str(result["content"]))

            # Also get from source attributions
            source_attributions = state.get("source_attributions", [])
            for attr in source_attributions:
                if hasattr(attr, "source_excerpt") and attr.source_excerpt:
                    source_contents.append(attr.source_excerpt)

            if source_contents:
                grounding_result = _run_enhanced_grounding_check(
                    summary_content,
                    source_contents,
                )

        except Exception as e:
            logger.error(f"Enhanced grounding check error (non-blocking): {e}")

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
                        f"  - {issue['type']}: '{issue['text'][:50]}...' ({issue['risk']} risk) - {issue['suggestion']}"
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
        if validation_flags and hasattr(plan, "metadata"):
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

    # Optional context optimization after summary (Phase 3)
    feature_flags = state.get("feature_flags", {})
    if feature_flags.get("context_optimization") and executor:
        try:
            memory_manager = get_memory_manager()
            await executor._ensure_memory()
            messages = executor.memory.get_messages()
            optimized_messages, report = memory_manager.optimize_context(
                messages,
                preserve_recent=6,
                token_threshold=int(
                    memory_manager.get_pressure_status(executor.memory.estimate_tokens()).max_tokens * 0.6
                ),
            )
            if report.tokens_saved > 0:
                executor.memory.messages = optimized_messages
                agent_id = state.get("agent_id") or getattr(executor, "_agent_id", "unknown")
                await executor._repository.save_memory(agent_id, executor.name, executor.memory)
                logger.info(
                    f"LangGraph summary context optimization saved {report.tokens_saved} tokens "
                    f"(semantic={report.semantic_compacted}, temporal={report.temporal_compacted})"
                )
        except Exception as e:
            logger.warning(f"LangGraph summary context optimization failed: {e}")

    # Build CoVe metadata if available
    cove_metadata = None
    if cove_result:
        cove_metadata = {
            "claims_verified": cove_result.claims_verified,
            "claims_contradicted": cove_result.claims_contradicted,
            "claims_uncertain": cove_result.claims_uncertain,
            "confidence_score": cove_result.confidence_score,
            "processing_time_ms": cove_result.processing_time_ms,
            "refined": cove_result.has_contradictions,
        }

    return {
        "plan": plan,
        "pending_events": pending_events,
        "validation_flags": validation_flags,
        "cove_result": cove_metadata,
        "grounding_result": grounding_result,
    }
