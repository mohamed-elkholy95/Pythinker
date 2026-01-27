"""Execution node for the LangGraph PlanAct workflow.

This node executes the next step in the plan using the ExecutionAgent.
Enhanced with:
- Stuck pattern detection and recovery
- Security assessment integration
- Troubleshooting protocol for failures
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from app.domain.services.langgraph.state import PlanActState
from app.domain.models.plan import ExecutionStatus
from app.domain.models.event import ToolEvent, WaitEvent, ErrorEvent
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.agents.stuck_detector import StuckAnalysis, LoopType

logger = logging.getLogger(__name__)

# Per-step tool call limit to prevent runaway exploration
MAX_TOOL_CALLS_PER_STEP = 100

# Stuck detection thresholds
STUCK_CHECK_INTERVAL = 10  # Check for stuck every N tool calls


async def execution_node(state: PlanActState) -> Dict[str, Any]:
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
        stuck_analysis: Optional[StuckAnalysis] = None

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
                    recent_actions.append({
                        "function_name": event.function_name,
                        "success": event.function_result.success if event.function_result else True,
                        "result": str(event.function_result.message)[:200] if event.function_result else "",
                        "error": event.function_result.message if event.function_result and not event.function_result.success else None,
                    })

                # Periodically check for stuck patterns
                if step_tool_calls % STUCK_CHECK_INTERVAL == 0:
                    # Check if executor has detected stuck pattern
                    if hasattr(executor, '_stuck_detector'):
                        analysis = executor._stuck_detector.get_analysis()
                        if analysis:
                            logger.warning(
                                f"Stuck pattern detected at tool call {step_tool_calls}: "
                                f"{analysis.loop_type.value}"
                            )
                            stuck_analysis = analysis

                            # For severe stuck patterns, break early
                            if analysis.loop_type in (
                                LoopType.TOOL_FAILURE_CASCADE,
                                LoopType.REPEATING_ACTION_ERROR,
                            ) and analysis.repeat_count >= 5:
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

        # Log step execution stats
        step_duration = time.time() - step_start_time
        logger.info(
            f"Step {step.id} completed: {step_tool_calls} tool calls in {step_duration:.1f}s"
        )

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
        if not stuck_analysis and hasattr(executor, '_stuck_detector'):
            stuck_analysis = executor._stuck_detector.get_analysis()

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
