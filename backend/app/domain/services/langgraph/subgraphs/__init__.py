"""LangGraph Subgraphs for Complex Workflows

Provides reusable subgraph components that can be composed
into larger LangGraph workflows.

Available Subgraphs:
- browser_workflow: Autonomous browser task execution
"""

from app.domain.services.langgraph.subgraphs.browser_workflow import (
    BrowserWorkflowState,
    create_browser_workflow,
)

__all__ = [
    "BrowserWorkflowState",
    "create_browser_workflow",
]
