"""Browser Workflow Subgraph for Complex Browser Tasks

Provides a LangGraph subgraph for handling multi-step browser
automation tasks with proper state management and error recovery.

Phase 2 Enhancement: Browser-use as LangGraph Subgraph

Key Features:
- Multi-step browser task orchestration
- Error recovery and retry logic
- Human-in-the-loop interruption support
- Progress tracking and event streaming
- Composable with parent workflows

Usage:
    from app.domain.services.langgraph.subgraphs import create_browser_workflow

    # Create standalone browser workflow
    browser_graph = create_browser_workflow()

    # Or compose into parent graph
    parent_graph.add_node("browser", browser_graph)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.domain.models.event import BaseEvent
from app.domain.services.langgraph.nodes.browser_agent_node import (
    BrowserNodeConfig,
    BrowserNodeResult,
    BrowserStepEvent,
    BrowserStepStatus,
)

logger = logging.getLogger(__name__)


def merge_events(a: list[BaseEvent], b: list[BaseEvent] | None) -> list[BaseEvent]:
    """Reducer to accumulate events."""
    if b is None:
        return a
    return a + b


class BrowserWorkflowState(TypedDict, total=False):
    """State for browser workflow subgraph.

    This state is designed to be composed into parent workflow state.
    """

    # Task definition
    browser_task: str  # High-level task description
    browser_subtasks: list[str]  # Decomposed subtasks (optional)
    current_subtask_index: int

    # Execution context
    cdp_url: str
    session_id: str
    max_steps: int
    timeout_seconds: int

    # Results
    browser_result: BrowserNodeResult | None
    subtask_results: list[BrowserNodeResult]
    final_result: str | None

    # Control flow
    retry_count: int
    max_retries: int
    needs_human_input: bool
    human_response: str | None

    # Error handling
    error: str | None
    error_count: int

    # Events for streaming
    pending_events: Annotated[list[BaseEvent], merge_events]

    # Event queue for real-time streaming (from parent state)
    event_queue: asyncio.Queue | None


@dataclass
class BrowserWorkflowConfig:
    """Configuration for browser workflow."""

    max_subtasks: int = 5
    max_retries: int = 2
    step_timeout: int = 120
    total_timeout: int = 600
    use_decomposition: bool = True
    stream_events: bool = True


def create_initial_browser_state(
    task: str,
    cdp_url: str,
    session_id: str = "",
    event_queue: asyncio.Queue | None = None,
    config: BrowserWorkflowConfig | None = None,
) -> BrowserWorkflowState:
    """Create initial state for browser workflow.

    Args:
        task: Browser task description
        cdp_url: Chrome DevTools Protocol URL
        session_id: Session identifier
        event_queue: Optional queue for real-time events
        config: Workflow configuration

    Returns:
        Initialized BrowserWorkflowState
    """
    config = config or BrowserWorkflowConfig()

    return BrowserWorkflowState(
        browser_task=task,
        browser_subtasks=[],
        current_subtask_index=0,
        cdp_url=cdp_url,
        session_id=session_id,
        max_steps=15,
        timeout_seconds=config.step_timeout,
        browser_result=None,
        subtask_results=[],
        final_result=None,
        retry_count=0,
        max_retries=config.max_retries,
        needs_human_input=False,
        human_response=None,
        error=None,
        error_count=0,
        pending_events=[],
        event_queue=event_queue,
    )


# =============================================================================
# Workflow Nodes
# =============================================================================


async def decompose_task_node(state: BrowserWorkflowState) -> dict[str, Any]:
    """Decompose complex browser task into subtasks.

    For simple tasks, returns the original task as a single subtask.
    For complex tasks, breaks into logical steps.

    Args:
        state: Current workflow state

    Returns:
        State update with browser_subtasks
    """
    task = state.get("browser_task", "")
    events: list[BaseEvent] = []

    # Emit planning event
    events.append(
        BrowserStepEvent(
            step_number=0,
            status=BrowserStepStatus.THINKING,
            thought=f"Planning browser task: {task[:100]}...",
        )
    )

    # Simple heuristic decomposition
    # In production, this could use LLM for intelligent decomposition
    subtasks = _decompose_task_simple(task)

    logger.info(f"Decomposed browser task into {len(subtasks)} subtasks")

    return {
        "browser_subtasks": subtasks,
        "current_subtask_index": 0,
        "pending_events": events,
    }


async def execute_subtask_node(state: BrowserWorkflowState) -> dict[str, Any]:
    """Execute current browser subtask.

    Args:
        state: Current workflow state

    Returns:
        State update with browser_result
    """
    from app.domain.services.langgraph.nodes.browser_agent_node import (
        _execute_browser_agent,
    )

    subtasks = state.get("browser_subtasks", [])
    current_index = state.get("current_subtask_index", 0)
    cdp_url = state.get("cdp_url", "")
    events: list[BaseEvent] = []

    if not subtasks or current_index >= len(subtasks):
        return {
            "browser_result": None,
            "error": "No subtask to execute",
            "pending_events": events,
        }

    current_task = subtasks[current_index]

    # Emit execution event
    events.append(
        BrowserStepEvent(
            step_number=current_index + 1,
            status=BrowserStepStatus.STARTED,
            thought=f"Executing subtask {current_index + 1}/{len(subtasks)}: {current_task[:100]}",
        )
    )

    # Configure execution
    settings = get_settings()
    config = BrowserNodeConfig(
        max_steps=state.get("max_steps", 15),
        timeout_seconds=state.get("timeout_seconds", 120),
        use_vision=settings.browser_agent_use_vision,
        stream_events=True,
    )

    # Execute subtask
    try:
        result = await _execute_browser_agent(
            state,
            current_task,
            cdp_url,
            config,
        )

        # Collect subtask events
        events.extend(result.events)

        return {
            "browser_result": result,
            "pending_events": events,
        }

    except Exception as e:
        error_msg = f"Subtask execution failed: {e!s}"
        logger.error(error_msg, exc_info=True)

        events.append(
            BrowserStepEvent(
                step_number=current_index + 1,
                status=BrowserStepStatus.FAILED,
                error=error_msg,
            )
        )

        return {
            "browser_result": BrowserNodeResult(
                success=False,
                errors=[error_msg],
            ),
            "error": error_msg,
            "error_count": state.get("error_count", 0) + 1,
            "pending_events": events,
        }


async def update_progress_node(state: BrowserWorkflowState) -> dict[str, Any]:
    """Update progress after subtask completion.

    Moves to next subtask or marks workflow complete.

    Args:
        state: Current workflow state

    Returns:
        State update with progress
    """
    result = state.get("browser_result")
    subtasks = state.get("browser_subtasks", [])
    current_index = state.get("current_subtask_index", 0)
    subtask_results = state.get("subtask_results", []).copy()

    # Store result
    if result:
        subtask_results.append(result)

    # Move to next subtask
    next_index = current_index + 1

    # Check if all subtasks complete
    if next_index >= len(subtasks):
        # Aggregate final result
        final_result = _aggregate_results(subtask_results)

        return {
            "subtask_results": subtask_results,
            "current_subtask_index": next_index,
            "final_result": final_result,
            "retry_count": 0,  # Reset retry count
        }

    return {
        "subtask_results": subtask_results,
        "current_subtask_index": next_index,
        "retry_count": 0,  # Reset retry count for next subtask
    }


async def handle_error_node(state: BrowserWorkflowState) -> dict[str, Any]:
    """Handle errors with retry logic.

    Args:
        state: Current workflow state

    Returns:
        State update for retry or failure
    """
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    error = state.get("error")
    events: list[BaseEvent] = []

    if retry_count < max_retries:
        # Emit retry event
        events.append(
            BrowserStepEvent(
                step_number=state.get("current_subtask_index", 0),
                status=BrowserStepStatus.THINKING,
                thought=f"Retrying after error (attempt {retry_count + 1}/{max_retries}): {error}",
            )
        )

        return {
            "retry_count": retry_count + 1,
            "error": None,  # Clear error for retry
            "pending_events": events,
        }

    # Max retries exceeded
    events.append(
        BrowserStepEvent(
            step_number=state.get("current_subtask_index", 0),
            status=BrowserStepStatus.FAILED,
            error=f"Max retries exceeded: {error}",
        )
    )

    return {
        "error": f"Max retries exceeded: {error}",
        "pending_events": events,
    }


async def finalize_node(state: BrowserWorkflowState) -> dict[str, Any]:
    """Finalize browser workflow results.

    Args:
        state: Current workflow state

    Returns:
        Final state update
    """
    subtask_results = state.get("subtask_results", [])
    final_result = state.get("final_result")
    events: list[BaseEvent] = []

    # Calculate aggregate metrics
    total_steps = sum(r.steps_executed for r in subtask_results)
    total_time_ms = sum(r.execution_time_ms for r in subtask_results)
    all_success = all(r.success for r in subtask_results)

    # Emit completion event
    events.append(
        BrowserStepEvent(
            step_number=total_steps,
            status=BrowserStepStatus.COMPLETED if all_success else BrowserStepStatus.FAILED,
            thought=f"Browser workflow completed: {len(subtask_results)} subtasks, {total_steps} steps",
            metadata={
                "total_steps": total_steps,
                "total_time_ms": total_time_ms,
                "subtask_count": len(subtask_results),
                "all_success": all_success,
            },
        )
    )

    # Create aggregate result
    aggregate_result = BrowserNodeResult(
        success=all_success,
        result=final_result,
        steps_executed=total_steps,
        execution_time_ms=total_time_ms,
        errors=[err for r in subtask_results for err in r.errors],
    )

    return {
        "browser_result": aggregate_result,
        "pending_events": events,
    }


# =============================================================================
# Routing Functions
# =============================================================================

BrowserRoute = Literal["execute", "update", "handle_error", "finalize", "__end__"]


def route_after_decompose(state: BrowserWorkflowState) -> BrowserRoute:
    """Route after task decomposition."""
    subtasks = state.get("browser_subtasks", [])

    if not subtasks:
        return "finalize"

    return "execute"


def route_after_execute(state: BrowserWorkflowState) -> BrowserRoute:
    """Route after subtask execution."""
    result = state.get("browser_result")
    error = state.get("error")

    # Check for human input interrupt
    if state.get("needs_human_input"):
        return "__end__"

    # Check for error
    if error or (result and not result.success):
        return "handle_error"

    return "update"


def route_after_update(state: BrowserWorkflowState) -> BrowserRoute:
    """Route after progress update."""
    subtasks = state.get("browser_subtasks", [])
    current_index = state.get("current_subtask_index", 0)

    if current_index >= len(subtasks):
        return "finalize"

    return "execute"


def route_after_error(state: BrowserWorkflowState) -> BrowserRoute:
    """Route after error handling."""
    error = state.get("error")

    # If error cleared (will retry)
    if not error:
        return "execute"

    # Max retries exceeded
    return "finalize"


# =============================================================================
# Helper Functions
# =============================================================================


def _decompose_task_simple(task: str) -> list[str]:
    """Simple heuristic task decomposition.

    For production, consider using LLM-based decomposition.

    Args:
        task: Task description

    Returns:
        List of subtasks
    """
    task_lower = task.lower()

    # Check for multi-step indicators
    if " then " in task_lower or " and then " in task_lower:
        # Split on sequence indicators
        import re

        parts = re.split(r"\s+(?:and\s+)?then\s+", task, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p.strip()]

    # Check for numbered steps
    import re

    numbered = re.findall(r"\d+\.\s*(.+?)(?=\d+\.|$)", task, re.DOTALL)
    if numbered:
        return [n.strip() for n in numbered if n.strip()]

    # Check for bullet points
    bullets = re.findall(r"[-*•]\s*(.+?)(?=[-*•]|$)", task, re.DOTALL)
    if bullets:
        return [b.strip() for b in bullets if b.strip()]

    # Single task
    return [task]


def _aggregate_results(results: list[BrowserNodeResult]) -> str:
    """Aggregate multiple subtask results into final result.

    Args:
        results: List of subtask results

    Returns:
        Aggregated result string
    """
    if not results:
        return ""

    # Collect all non-empty results
    parts = []
    for i, r in enumerate(results):
        if r.result:
            parts.append(f"Step {i + 1}: {r.result}")

    if parts:
        return "\n".join(parts)

    # Fallback to last successful result
    for r in reversed(results):
        if r.success and r.result:
            return r.result

    return "Browser workflow completed"


# =============================================================================
# Graph Construction
# =============================================================================


def create_browser_workflow(config: BrowserWorkflowConfig | None = None) -> StateGraph:
    """Create browser workflow subgraph.

    Args:
        config: Workflow configuration

    Returns:
        Compiled StateGraph for browser workflow
    """
    config = config or BrowserWorkflowConfig()

    # Create graph builder
    builder = StateGraph(BrowserWorkflowState)

    # Add nodes
    builder.add_node("decompose", decompose_task_node)
    builder.add_node("execute", execute_subtask_node)
    builder.add_node("update", update_progress_node)
    builder.add_node("handle_error", handle_error_node)
    builder.add_node("finalize", finalize_node)

    # Set entry point
    builder.set_entry_point("decompose")

    # Add conditional edges
    builder.add_conditional_edges("decompose", route_after_decompose)
    builder.add_conditional_edges("execute", route_after_execute)
    builder.add_conditional_edges("update", route_after_update)
    builder.add_conditional_edges("handle_error", route_after_error)

    # Finalize goes to END
    builder.add_edge("finalize", END)

    # Compile and return
    return builder.compile()


__all__ = [
    "BrowserWorkflowConfig",
    "BrowserWorkflowState",
    "create_browser_workflow",
    "create_initial_browser_state",
]
