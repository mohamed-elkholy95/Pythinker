"""Planning node for the LangGraph PlanAct workflow.

This node wraps the PlannerAgent to create or update plans.
Enhanced with:
- Input guardrails for prompt injection/jailbreak detection
- Intent extraction for user prompt adherence tracking
- Parallel tool prefetching for reduced latency
- Comprehension phase for long/complex messages
"""

import asyncio
import logging
from typing import Any

from app.domain.models.event import (
    ComprehensionEvent,
    ErrorEvent,
    PlanEvent,
    PlanStatus,
    TaskRecreationEvent,
    TitleEvent,
)

# P0 Priority: Input Guardrails
from app.domain.services.agents.guardrails import InputRiskLevel, get_guardrails_manager
from app.domain.services.agents.intent_tracker import UserIntent, get_intent_tracker
from app.domain.services.langgraph.state import PlanActState, RequirementProgress
from app.domain.services.tools.dynamic_toolset import get_toolset_manager
from app.domain.services.validation.plan_validator import PlanValidator

logger = logging.getLogger(__name__)

# Comprehension threshold - messages longer than this trigger comprehension phase
COMPREHENSION_THRESHOLD_CHARS = 500


def _initialize_requirement_progress(user_intent: UserIntent) -> list[RequirementProgress]:
    """Initialize requirement progress tracking from user intent.

    Creates a RequirementProgress entry for each explicit and implicit
    requirement extracted from the user's message.

    Args:
        user_intent: Extracted user intent with requirements

    Returns:
        List of RequirementProgress entries, all initially unaddressed
    """
    progress: list[RequirementProgress] = []

    # Add explicit requirements
    for req in user_intent.explicit_requirements:
        progress.append(
            RequirementProgress(
                requirement=req,
                is_addressed=False,
                confidence=0.0,
                addressed_by_step=None,
                evidence=None,
            )
        )

    # Add implicit requirements
    for req in user_intent.implicit_requirements:
        progress.append(
            RequirementProgress(
                requirement=req,
                is_addressed=False,
                confidence=0.0,
                addressed_by_step=None,
                evidence=None,
            )
        )

    logger.debug(
        f"Initialized requirement progress: {len(progress)} requirements "
        f"({len(user_intent.explicit_requirements)} explicit, "
        f"{len(user_intent.implicit_requirements)} implicit)"
    )

    return progress


async def _prefetch_tools_for_task(user_message_text: str, include_mcp: bool = True) -> list[dict[str, Any]] | None:
    """Prefetch tools in background while planning proceeds.

    Args:
        user_message_text: The user's message text
        include_mcp: Whether to include MCP tools

    Returns:
        List of prefetched tool schemas, or None on error
    """
    try:
        toolset_manager = get_toolset_manager()

        # Use the async prefetch method
        tools = await toolset_manager.prefetch_tools_async(user_message_text, include_mcp=include_mcp)

        logger.debug(f"Prefetched {len(tools)} tools for planning")
        return tools

    except Exception as e:
        logger.warning(f"Tool prefetch failed (non-blocking): {e}")
        return None


async def _comprehend_long_message(
    state: PlanActState,
    message_text: str,
    user_intent: Any,
) -> dict[str, Any] | None:
    """Comprehend a long/complex message before creating tasks.

    This phase allows the agent to fully understand complex requirements
    before breaking them down into tasks. Useful for:
    - Long specification documents
    - Multi-part requirements
    - Complex feature requests

    Args:
        state: Current workflow state
        message_text: The full user message
        user_intent: Extracted user intent

    Returns:
        Comprehension result with summary and requirements, or None on error
    """
    planner = state.get("planner")
    if not planner or not hasattr(planner, "llm"):
        return None

    try:
        # Build comprehension prompt
        comprehension_prompt = f"""Carefully read and understand the following request.
Summarize what the user wants in 2-3 sentences, then list the key requirements.

USER REQUEST:
{message_text}

Respond in this JSON format:
{{
    "summary": "Brief 2-3 sentence summary of what the user wants",
    "requirements": ["requirement 1", "requirement 2", ...],
    "complexity_score": 0.0 to 1.0 (how complex is this task),
    "suggested_approach": "Brief description of how to approach this task"
}}"""

        # Use planner's LLM for comprehension
        response = await planner.llm.ask(
            [
                {
                    "role": "system",
                    "content": "You are a task comprehension assistant. Read carefully and extract key requirements.",
                },
                {"role": "user", "content": comprehension_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.get("content", "{}")

        # Parse response
        import json

        try:
            result = json.loads(content)
            logger.info(f"Comprehension complete: {len(result.get('requirements', []))} requirements extracted")
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse comprehension response as JSON")
            return {
                "summary": content[:500],
                "requirements": user_intent.explicit_requirements if user_intent else [],
                "complexity_score": 0.7,
            }

    except Exception as e:
        logger.warning(f"Comprehension phase failed: {e}")
        return None


async def planning_node(state: PlanActState) -> dict[str, Any]:
    """Create or revise the execution plan.

    This node invokes the PlannerAgent to create a plan from the user message.
    If verification feedback is present, it passes that context for revision.

    Optimization: Starts tool prefetching in parallel with plan creation
    to reduce overall latency.

    Args:
        state: Current workflow state

    Returns:
        State updates including the new plan and accumulated events
    """
    planner = state.get("planner")
    user_message = state.get("user_message")
    task_state_manager = state.get("task_state_manager")

    if not planner or not user_message:
        logger.error("Planning node missing required agents or message")
        return {
            "error": "Planning node missing required agents or message",
            "pending_events": [],
        }

    logger.info(f"Planning node: creating plan for session {state.get('session_id')}")

    # === P0: Input Guardrails Check ===
    # Screen user input for prompt injection, jailbreak attempts, etc.
    message_text = user_message.message if hasattr(user_message, "message") else str(user_message)
    guardrails = get_guardrails_manager()
    input_result = guardrails.check_input(message_text)

    if input_result.risk_level == InputRiskLevel.BLOCKED:
        logger.warning(
            f"Input blocked by guardrails: {len(input_result.issues)} issues, "
            f"types={[i.issue_type.value for i in input_result.issues]}"
        )
        # Return error event - don't proceed with planning
        error_event = ErrorEvent(
            error="I cannot process this request as it appears to contain problematic content. "
            "Please rephrase your request."
        )
        return {
            "error": "Input blocked by guardrails",
            "pending_events": [error_event],
            "input_blocked": True,
        }

    if input_result.needs_clarification:
        logger.info(f"Input needs clarification: {input_result.clarification_questions}")
        # Could trigger a clarification flow here in the future

    # Use cleaned input if guardrails modified it
    if input_result.cleaned_input and input_result.cleaned_input != message_text:
        logger.debug("Using guardrail-sanitized input")
        # Note: We log but don't modify - let planner see original for context

    # === P0: Intent Extraction ===
    # Extract user intent for tracking throughout execution
    intent_tracker = get_intent_tracker()
    user_intent = intent_tracker.extract_intent(message_text)
    logger.info(
        f"Extracted user intent: type={user_intent.intent_type.value}, "
        f"requirements={len(user_intent.explicit_requirements)}"
    )

    # Get event queue for real-time streaming (moved up for comprehension phase)
    event_queue: asyncio.Queue | None = state.get("event_queue")
    pending_events: list = []

    # === Comprehension Phase for Long Messages ===
    # If message is long/complex, trigger comprehension to understand fully before planning
    comprehension_result = None
    if task_state_manager and task_state_manager.should_trigger_comprehension(
        message_text, threshold_chars=COMPREHENSION_THRESHOLD_CHARS
    ):
        logger.info(f"Triggering comprehension phase for long message ({len(message_text)} chars)")
        comprehension_result = await _comprehend_long_message(state, message_text, user_intent)
        if comprehension_result:
            # Emit comprehension event
            comprehension_event = ComprehensionEvent(
                original_length=len(message_text),
                summary=comprehension_result.get("summary", ""),
                key_requirements=comprehension_result.get("requirements", []),
                complexity_score=comprehension_result.get("complexity_score"),
            )
            if event_queue:
                await event_queue.put(comprehension_event)
            else:
                pending_events.append(comprehension_event)

    # Check if this is a replan due to verification feedback
    replan_context = None
    if state.get("verification_feedback") and state.get("verification_verdict") == "revise":
        replan_context = state.get("verification_feedback")
        logger.info("Replanning with verification feedback")

    # Start tool prefetch in background (runs parallel to planning)
    # This reduces latency by preparing tools while the plan is being created
    prefetch_task = asyncio.create_task(_prefetch_tools_for_task(message_text, include_mcp=True))

    # Collect events from the planner
    plan = None
    plan_created = False

    async for event in planner.create_plan(user_message, replan_context=replan_context):
        if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
            plan = event.plan
            plan_created = True

            # Infer smart dependencies for BLOCKED cascade and parallel execution
            plan.infer_smart_dependencies(use_sequential_fallback=True)

            # Initialize task state for recitation
            if task_state_manager:
                # Use comprehension-based recreation if we did comprehension phase
                if comprehension_result:
                    task_state_manager.recreate_from_comprehension(
                        original_objective=user_message.message,
                        comprehension_summary=comprehension_result.get("summary", ""),
                        new_steps=[{"id": s.id, "description": s.description} for s in plan.steps],
                        preserve_findings=False,  # Fresh start for new task
                    )
                    # Emit task recreation event
                    recreation_event = TaskRecreationEvent(
                        reason="Tasks created after comprehending long message",
                        previous_step_count=0,
                        new_step_count=len(plan.steps),
                        preserved_findings=0,
                    )
                    if event_queue:
                        await event_queue.put(recreation_event)
                    else:
                        pending_events.append(recreation_event)
                else:
                    task_state_manager.initialize_from_plan(
                        objective=user_message.message,
                        steps=[{"id": s.id, "description": s.description} for s in plan.steps],
                    )

            # Emit title event
            title_event = TitleEvent(title=plan.title)
            if event_queue:
                await event_queue.put(title_event)
            else:
                pending_events.append(title_event)

        # Stream event in real-time if queue available
        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Await prefetch completion (should already be done by now)
    prefetched_tools = None
    try:
        prefetched_tools = await prefetch_task
        if prefetched_tools:
            logger.debug(f"Tool prefetch completed: {len(prefetched_tools)} tools ready")
    except Exception as e:
        logger.warning(f"Tool prefetch await failed: {e}")

    # Check if plan has no steps (direct completion)
    all_steps_done = False
    if plan and len(plan.steps) == 0:
        logger.info("Plan created with no steps - marking as done")
        all_steps_done = True

    # Plan validation (Phase 1)
    plan_validation_failed = False
    verification_verdict = None
    verification_feedback = None
    verification_loops = state.get("verification_loops", 0)
    max_verification_loops = state.get("max_verification_loops", 2)

    if plan:
        flags = state.get("feature_flags", {})
        if flags.get("plan_validation_v2"):
            tool_names = [
                t.get("function", {}).get("name", "") for t in (planner.get_available_tools() if planner else []) or []
            ]
            validation = PlanValidator(tool_names=tool_names).validate(plan)
        else:
            validation = plan.validate_plan()

        if not validation.passed:
            summary = (
                validation.to_summary()
                if hasattr(validation, "to_summary")
                else "\n- " + "\n- ".join(validation.errors[:5])
            )
            if flags.get("plan_validation_v2") and flags.get("shadow_mode", True):
                logger.warning(f"Plan pre-validation errors (shadow): {summary}")
            else:
                plan_validation_failed = True
                verification_verdict = "revise"
                verification_feedback = "Plan validation failed:" + summary
                if verification_loops < max_verification_loops:
                    verification_loops += 1

    # Phase 3: Initialize requirement progress tracking
    requirement_progress = _initialize_requirement_progress(user_intent)

    return {
        "plan": plan,
        "plan_created": plan_created,
        "all_steps_done": all_steps_done,
        "plan_validation_failed": plan_validation_failed,
        # Reset verification state after replanning unless validation failed
        "verification_verdict": verification_verdict,
        "verification_feedback": verification_feedback,
        "verification_loops": verification_loops,
        "pending_events": pending_events,
        "iteration_count": state.get("iteration_count", 0) + 1,
        # Include prefetched tools for execution node
        "prefetched_tools": prefetched_tools,
        # Phase 3: User intent tracking for constraint enforcement
        "user_intent": user_intent,
        "intent_tracker": intent_tracker,
        # Phase 3: Requirement progress tracking
        "requirement_progress": requirement_progress,
        "intent_alignment_score": 0.0,  # Will be updated as steps complete
    }
