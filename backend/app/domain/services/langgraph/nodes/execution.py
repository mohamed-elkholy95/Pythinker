"""Execution node for the LangGraph PlanAct workflow.

This node executes the next step in the plan using the ExecutionAgent.
Enhanced with:
- Stuck pattern detection and recovery
- Security assessment integration
- Troubleshooting protocol for failures
- Inline grounding validation for informational tools
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from app.domain.models.event import ErrorEvent, ToolEvent, WaitEvent
from app.domain.models.plan import ExecutionStatus
from app.domain.services.agents.grounding_validator import GroundingValidator
from app.domain.services.agents.memory_manager import get_memory_manager
from app.domain.services.agents.stuck_detector import LoopType, StuckAnalysis
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# Tools that fetch information and should be grounding-validated
INFORMATIONAL_TOOLS = frozenset(
    {
        "browser_browse",
        "browser_get_content",
        "browser_navigate",
        "search",
        "info_search_web",
    }
)

# Threshold below which we log a warning about poor grounding
GROUNDING_WARNING_THRESHOLD = 0.3

# Shared grounding validator instance
_grounding_validator: GroundingValidator | None = None


def _get_grounding_validator() -> GroundingValidator:
    """Get or create the shared grounding validator instance."""
    global _grounding_validator
    if _grounding_validator is None:
        _grounding_validator = GroundingValidator(
            grounding_threshold=0.4,
            min_claim_words=3,
            max_claims_to_check=10,  # Limit for inline performance
        )
    return _grounding_validator


# Per-step tool call limit to prevent runaway exploration
MAX_TOOL_CALLS_PER_STEP = 100

# Stuck detection thresholds
STUCK_CHECK_INTERVAL = 10  # Check for stuck every N tool calls

# Node timeout in seconds (5 minutes for execution)
EXECUTION_NODE_TIMEOUT = 300


async def execution_node(state: PlanActState) -> dict[str, Any]:
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

    user_id = state.get("user_id")
    session_id = state.get("session_id")

    @asynccontextmanager
    async def usage_context():
        if user_id and session_id:
            async with UsageContextManager(user_id=user_id, session_id=session_id):
                yield
        else:
            yield

    async with usage_context():
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

        # Execute the step with per-step tool call tracking
        pending_events = []
        recent_tools = []
        recent_actions = []  # For stuck pattern analysis
        needs_human_input = False
        last_had_error = False
        step_tool_calls = 0
        step_start_time = time.time()
        stuck_analysis: StuckAnalysis | None = None
        try:
            # P1.1: Wrap execution in timeout to prevent hanging nodes
            async with asyncio.timeout(EXECUTION_NODE_TIMEOUT):
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
                        step_tool_calls += 1

                        # Track action details for stuck analysis
                        if event.function_result:
                            action_record = {
                                "function_name": event.function_name,
                                "success": event.function_result.success if event.function_result else True,
                                "result": str(event.function_result.message)[:200] if event.function_result else "",
                                "error": event.function_result.message
                                if event.function_result and not event.function_result.success
                                else None,
                            }
                            recent_actions.append(action_record)

                            # P0.3: Inline grounding validation for informational tools
                            # This catches poorly grounded tool results before they're used
                            if (
                                event.function_name in INFORMATIONAL_TOOLS
                                and event.function_result.success
                                and event.function_result.message
                            ):
                                try:
                                    grounding_result = _get_grounding_validator().validate(
                                        source=str(event.function_result.data)[:2000]
                                        if event.function_result.data
                                        else "",
                                        query=str(user_message.content)[:500] if user_message else "",
                                        response=event.function_result.message[:500],
                                    )
                                    action_record["grounding_score"] = grounding_result.overall_score
                                    action_record["grounding_level"] = grounding_result.level.value

                                    if grounding_result.overall_score < GROUNDING_WARNING_THRESHOLD:
                                        logger.warning(
                                            f"Poorly grounded tool result from {event.function_name}: "
                                            f"score={grounding_result.overall_score:.2f}, "
                                            f"level={grounding_result.level.value}"
                                        )
                                except Exception as e:
                                    # Don't fail execution on grounding validation errors
                                    logger.debug(f"Grounding validation skipped: {e}")

                            # Feed tool action to stuck detector for pattern analysis
                            if hasattr(executor, "_stuck_detector"):
                                tool_args = event.function_args or {}
                                analysis = executor._stuck_detector.track_tool_action(
                                    tool_name=event.function_name,
                                    tool_args=tool_args,
                                    success=event.function_result.success if event.function_result else True,
                                    result=str(event.function_result.data)[:500]
                                    if event.function_result and event.function_result.data
                                    else None,
                                    error=action_record["error"],
                                )
                                if analysis and not stuck_analysis:
                                    stuck_analysis = analysis

                        # Periodically check for stuck patterns
                        if step_tool_calls % STUCK_CHECK_INTERVAL == 0 and hasattr(executor, "_stuck_detector"):
                            # Check if executor has detected stuck pattern
                            analysis = executor._stuck_detector.get_analysis()
                            if analysis:
                                logger.warning(
                                    f"Stuck pattern detected at tool call {step_tool_calls}: {analysis.loop_type.value}"
                                )
                                stuck_analysis = analysis

                                # For severe stuck patterns, break early
                                severe_patterns = {
                                    LoopType.TOOL_FAILURE_CASCADE,
                                    LoopType.REPEATING_ACTION_ERROR,
                                    LoopType.BROWSER_CLICK_FAILURES,
                                    LoopType.BROWSER_SAME_PAGE_LOOP,
                                }
                                if analysis.loop_type in severe_patterns and analysis.repeat_count >= 4:
                                    logger.warning(
                                        f"Severe stuck pattern ({analysis.loop_type.value}), "
                                        "breaking execution for recovery"
                                    )
                                    step.notes = f"Interrupted: {analysis.details}"
                                    break

                        # Check per-step tool call limit
                        if step_tool_calls >= MAX_TOOL_CALLS_PER_STEP:
                            logger.warning(
                                f"Step {step.id} reached tool call limit ({MAX_TOOL_CALLS_PER_STEP}), "
                                "marking as completed with partial results"
                            )
                            step.status = ExecutionStatus.COMPLETED
                            step.success = True
                            step.result = (
                                f"Step partially completed after {step_tool_calls} tool calls. "
                                "Consider breaking this into smaller sub-steps for better results."
                            )
                            break

                    # Check for wait event (human input needed)
                    if isinstance(event, WaitEvent):
                        needs_human_input = True

                    # Check for error events
                    if isinstance(event, ErrorEvent):
                        last_had_error = True

        except TimeoutError:
            # P1.1: Handle execution timeout gracefully
            last_had_error = True
            logger.error(f"Execution node timed out after {EXECUTION_NODE_TIMEOUT}s for step {step.id}")
            step.status = ExecutionStatus.FAILED
            step.error = f"Step execution timed out after {EXECUTION_NODE_TIMEOUT} seconds"

        # Log step execution stats
        step_duration = time.time() - step_start_time
        logger.info(f"Step {step.id} completed: {step_tool_calls} tool calls in {step_duration:.1f}s")

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

        # Final stuck check at end of step
        if not stuck_analysis and hasattr(executor, "_stuck_detector"):
            stuck_analysis = executor._stuck_detector.get_analysis()

        # Optional context optimization (Phase 3)
        feature_flags = state.get("feature_flags", {})
        if feature_flags.get("context_optimization") and executor:
            try:
                memory_manager = get_memory_manager()
                await executor._ensure_memory()
                messages = executor.memory.get_messages()
                optimized_messages, report = memory_manager.optimize_context(
                    messages,
                    preserve_recent=10,
                    token_threshold=int(
                        memory_manager.get_pressure_status(executor.memory.estimate_tokens()).max_tokens * 0.65
                    ),
                )
                if report.tokens_saved > 0:
                    executor.memory.messages = optimized_messages
                    agent_id = state.get("agent_id") or getattr(executor, "_agent_id", "unknown")
                    await executor._repository.save_memory(agent_id, executor.name, executor.memory)
                    logger.info(
                        f"LangGraph context optimization saved {report.tokens_saved} tokens "
                        f"(semantic={report.semantic_compacted}, temporal={report.temporal_compacted})"
                    )
            except Exception as e:
                logger.warning(f"LangGraph context optimization failed: {e}")

        return {
            "current_step": step,
            "plan": plan,  # Plan may have been modified
            "needs_human_input": needs_human_input,
            "last_had_error": last_had_error,
            "pending_events": pending_events,
            "recent_tools": recent_tools,
            "recent_actions": recent_actions,  # For stuck pattern reflection
            "stuck_analysis": stuck_analysis,  # For enhanced reflection
        }
