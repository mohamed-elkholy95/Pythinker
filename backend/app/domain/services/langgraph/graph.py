"""Graph construction for the LangGraph PlanAct workflow.

This module creates the StateGraph that defines the workflow structure
with nodes, edges, and conditional routing.
"""

import logging
from typing import Optional, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.domain.services.langgraph.state import PlanActState
from app.domain.services.langgraph.nodes import (
    planning_node,
    verification_node,
    execution_node,
    reflection_node,
    update_node,
    summarize_node,
)
from app.domain.services.langgraph.routing import (
    route_after_planning,
    route_after_verification,
    route_after_execution,
    route_after_reflection,
)

logger = logging.getLogger(__name__)


def create_plan_act_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> Any:  # CompiledGraph
    """Create and compile the PlanAct workflow graph.

    The workflow follows the Plan-Verify-Execute pattern:

    ```
    START -> planning -> [conditional] -> verifying -> [conditional] -> executing -> [conditional]
                 ^                             |              ^                            |
                 |                        [REVISE]            |                            v
                 +-----------------------------+              +---- updating <-- reflecting
                 |                                                     |
            [REPLAN]                                              [CONTINUE]
                 ^                                                     |
                 +-------------------- reflecting <--------------------+

    executing -> [HUMAN INPUT] -> END (interrupt)
    executing -> [ALL DONE] -> summarizing -> END
    ```

    Args:
        checkpointer: Optional checkpoint saver for persistence

    Returns:
        Compiled StateGraph
    """
    logger.info("Creating PlanAct LangGraph workflow")

    # Create the state graph with our state schema
    workflow = StateGraph(PlanActState)

    # Add nodes
    workflow.add_node("plan", planning_node)
    workflow.add_node("verify", verification_node)
    workflow.add_node("execute", execution_node)
    workflow.add_node("reflect", reflection_node)
    workflow.add_node("update", update_node)
    workflow.add_node("summarize", summarize_node)

    # Entry point: always start with planning
    workflow.add_edge(START, "plan")

    # Conditional routing after planning
    # Routes to: verify, execute, or summarize
    workflow.add_conditional_edges(
        "plan",
        route_after_planning,
        {
            "verify": "verify",
            "execute": "execute",
            "summarize": "summarize",
        }
    )

    # Conditional routing after verification
    # Routes to: execute, plan (for revision), or summarize (on failure)
    workflow.add_conditional_edges(
        "verify",
        route_after_verification,
        {
            "execute": "execute",
            "plan": "plan",
            "summarize": "summarize",
        }
    )

    # Conditional routing after execution
    # Routes to: reflect, update, summarize, or END (for human input)
    workflow.add_conditional_edges(
        "execute",
        route_after_execution,
        {
            "reflect": "reflect",
            "update": "update",
            "summarize": "summarize",
            "__end__": END,
        }
    )

    # Conditional routing after reflection
    # Routes to: update, plan (for replan), or summarize (on escalate/abort)
    workflow.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "update": "update",
            "plan": "plan",
            "summarize": "summarize",
        }
    )

    # Direct edge: update always goes back to execute
    workflow.add_edge("update", "execute")

    # Direct edge: summarize always ends the workflow
    workflow.add_edge("summarize", END)

    # Compile the graph
    compiled = workflow.compile(checkpointer=checkpointer)

    logger.info("PlanAct LangGraph workflow compiled successfully")

    return compiled


def get_graph_visualization() -> str:
    """Get a text representation of the graph structure.

    Returns:
        ASCII art representation of the graph
    """
    return """
    PlanAct Workflow Graph
    ======================

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   START                                                         │
    │     │                                                           │
    │     ▼                                                           │
    │  ┌──────┐                                                       │
    │  │ plan │◄─────────────────────────────┐                       │
    │  └──┬───┘                              │                       │
    │     │                                  │                       │
    │     ├─[verify enabled]─► ┌────────┐   │                       │
    │     │                    │ verify │   │                       │
    │     │                    └───┬────┘   │                       │
    │     │                        │        │                       │
    │     │          [PASS]◄──────┤        │                       │
    │     │                        │        │                       │
    │     ▼                   [REVISE]──────┘                       │
    │  ┌─────────┐                 │                                 │
    │  │ execute │◄───────────[FAIL]──► ┌───────────┐               │
    │  └────┬────┘                       │ summarize │               │
    │       │                            └─────┬─────┘               │
    │       ├──[human input]───────────────────┼──────────► END     │
    │       │                                  │                     │
    │       ├──[all done]──────────────────────┘                     │
    │       │                                                        │
    │       ▼                                                        │
    │  ┌─────────┐                                                   │
    │  │ reflect │                                                   │
    │  └────┬────┘                                                   │
    │       │                                                        │
    │       ├──[continue/adjust]──► ┌────────┐                      │
    │       │                       │ update │                      │
    │       │                       └───┬────┘                      │
    │       │                           │                            │
    │       │                           └────► execute               │
    │       │                                                        │
    │       ├──[replan]────────────────────► plan                   │
    │       │                                                        │
    │       └──[escalate/abort]────────────► summarize              │
    │                                                                │
    └─────────────────────────────────────────────────────────────────┘
    """
