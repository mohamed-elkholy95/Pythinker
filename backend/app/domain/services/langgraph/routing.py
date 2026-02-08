"""Routing functions for the LangGraph PlanAct workflow.

This module defines the conditional edge functions that determine
workflow transitions based on state.

Phase 2 Enhancement: Added browser node routing for autonomous browser tasks.
"""

import logging
from typing import Literal

from app.core.config import get_settings
from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# Define the possible routing destinations
# Phase 2: Added "browser" destination for browser agent node
PlanningRoute = Literal["verify", "execute", "browser", "summarize"]
VerificationRoute = Literal["execute", "browser", "plan", "summarize"]
ExecutionRoute = Literal["reflect", "update", "browser", "summarize", "__end__"]
ReflectionRoute = Literal["update", "plan", "browser", "summarize"]


def route_after_planning(state: PlanActState) -> PlanningRoute:
    """Route after planning node completes.

    Routes to:
    - "summarize" if plan has no steps
    - "verify" if verification is enabled
    - "execute" otherwise

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    plan = state.get("plan")

    # No steps - go directly to summarize
    if state.get("all_steps_done") or not plan or len(plan.steps) == 0:
        logger.debug("Routing after planning -> summarize (no steps)")
        return "summarize"

    # Route back to planning if pre-validation failed
    if state.get("plan_validation_failed"):
        loops = state.get("verification_loops", 0)
        max_loops = state.get("max_verification_loops", 2)
        if loops >= max_loops:
            logger.warning(f"Max validation loops ({max_loops}) reached, proceeding with execution")
            return "execute"
        logger.debug("Routing after planning -> plan (validation failed)")
        return "plan"

    # Route to verification if verifier is available
    if state.get("verifier"):
        logger.debug("Routing after planning -> verify")
        return "verify"

    logger.debug("Routing after planning -> execute")
    return "execute"


def route_after_verification(state: PlanActState) -> VerificationRoute:
    """Route after verification node completes.

    Routes to:
    - "execute" if verdict is pass
    - "plan" if verdict is revise (and loops not exceeded)
    - "execute" if max revision loops exceeded
    - "summarize" if verdict is fail

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    verdict = state.get("verification_verdict", "pass")
    loops = state.get("verification_loops", 0)
    max_loops = state.get("max_verification_loops", 2)

    if verdict == "pass":
        logger.debug("Routing after verification -> execute (passed)")
        return "execute"

    if verdict == "revise":
        if loops >= max_loops:
            logger.warning(f"Max verification loops ({max_loops}) reached, proceeding with execution")
            return "execute"
        logger.debug("Routing after verification -> plan (revision needed)")
        return "plan"

    if verdict == "fail":
        logger.debug("Routing after verification -> summarize (failed)")
        return "summarize"

    # Default: proceed with execution
    logger.debug("Routing after verification -> execute (default)")
    return "execute"


def route_after_execution(state: PlanActState) -> ExecutionRoute:
    """Route after execution node completes.

    Routes to:
    - "__end__" if human input is needed (interrupt)
    - "summarize" if all steps are done
    - "reflect" if reflection is enabled
    - "update" otherwise

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    # Human input needed - exit for interrupt
    if state.get("needs_human_input"):
        logger.debug("Routing after execution -> __end__ (needs human input)")
        return "__end__"

    # All steps done
    if state.get("all_steps_done"):
        logger.debug("Routing after execution -> summarize (all done)")
        return "summarize"

    # Check if reflection is enabled
    if state.get("reflection_agent"):
        logger.debug("Routing after execution -> reflect")
        return "reflect"

    logger.debug("Routing after execution -> update")
    return "update"


def route_after_reflection(state: PlanActState) -> ReflectionRoute:
    """Route after reflection node completes.

    Routes based on reflection decision:
    - "update" for continue or adjust
    - "plan" for replan
    - "summarize" for escalate or abort

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    decision = state.get("reflection_decision", "continue")

    if decision in ("continue", "adjust"):
        if decision == "adjust":
            feedback = state.get("reflection_feedback")
            logger.info(f"Reflection adjustment: {feedback}")
        logger.debug("Routing after reflection -> update")
        return "update"

    if decision == "replan":
        feedback = state.get("reflection_feedback")
        logger.info(f"Reflection triggered replan: {feedback}")
        return "plan"

    if decision == "escalate":
        logger.info("Reflection escalated to user")
        return "summarize"

    if decision == "abort":
        logger.warning("Reflection decided to abort task")
        return "summarize"

    # Default: continue with updating
    logger.debug("Routing after reflection -> update (default)")
    return "update"


# =============================================================================
# Phase 2: Browser Node Routing
# =============================================================================


def should_use_browser_node(state: PlanActState) -> bool:
    """Determine if current step should use browser agent node.

    Checks if the step description indicates a browser automation task
    that would benefit from the autonomous browser-use agent.

    Args:
        state: Current workflow state

    Returns:
        True if browser node should handle this step
    """
    settings = get_settings()

    # Check if feature is enabled
    if not settings.feature_browser_node:
        return False

    # Check if CDP URL is available
    if not state.get("cdp_url"):
        return False

    # Get current step
    step = state.get("current_step")
    if not step:
        return False

    # Keywords that indicate browser agent is appropriate
    browser_keywords = [
        "browse",
        "navigate",
        "scrape",
        "fill form",
        "autonomous",
        "web automation",
        "click",
        "submit form",
        "extract data",
        "web scraping",
        "website",
        "webpage",
        "login",
        "sign in",
        "fill out",
    ]

    # Check step description
    description = getattr(step, "description", "").lower()

    for keyword in browser_keywords:
        if keyword in description:
            logger.debug(f"Step matches browser keyword '{keyword}', routing to browser node")
            return True

    # Check if step has explicit browser_task metadata
    metadata = getattr(step, "metadata", {}) or {}
    return bool(metadata.get("use_browser_agent"))


def route_with_browser_check(
    state: PlanActState,
    default_route: str,
) -> str:
    """Helper to check browser node routing before default.

    Args:
        state: Current workflow state
        default_route: Route to use if browser check fails

    Returns:
        "browser" if browser node should be used, else default_route
    """
    if should_use_browser_node(state):
        return "browser"
    return default_route


# Browser-specific routes
BrowserRoute = Literal["execute", "update", "summarize", "__end__"]


def route_after_browser(state: PlanActState) -> BrowserRoute:
    """Route after browser node completes.

    Routes based on browser execution result:
    - "update" if successful (to continue with next step)
    - "execute" if retry needed
    - "summarize" if terminal failure

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    result = state.get("browser_result")

    # Check for human input interrupt
    if state.get("needs_human_input"):
        logger.debug("Routing after browser -> __end__ (needs human input)")
        return "__end__"

    # Check if all steps done
    if state.get("all_steps_done"):
        logger.debug("Routing after browser -> summarize (all done)")
        return "summarize"

    # Check result
    if result:
        if hasattr(result, "success") and result.success:
            logger.debug("Routing after browser -> update (success)")
            return "update"

        if hasattr(result, "interrupted") and result.interrupted:
            logger.debug("Routing after browser -> __end__ (interrupted)")
            return "__end__"

        # Check for retryable error
        error_count = state.get("error_count", 0)
        if error_count < 3:
            logger.debug(f"Routing after browser -> execute (retry, errors={error_count})")
            return "execute"

    # Default: proceed to update
    logger.debug("Routing after browser -> update (default)")
    return "update"
