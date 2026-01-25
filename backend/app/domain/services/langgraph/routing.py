"""Routing functions for the LangGraph PlanAct workflow.

This module defines the conditional edge functions that determine
workflow transitions based on state.
"""

import logging
from typing import Literal

from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)

# Define the possible routing destinations
PlanningRoute = Literal["verify", "execute", "summarize"]
VerificationRoute = Literal["execute", "plan", "summarize"]
ExecutionRoute = Literal["reflect", "update", "summarize", "__end__"]
ReflectionRoute = Literal["update", "plan", "summarize"]


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
            logger.warning(
                f"Max verification loops ({max_loops}) reached, "
                "proceeding with execution"
            )
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
