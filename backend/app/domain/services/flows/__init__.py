from app.domain.services.flows.base import BaseFlow, FlowStatus
from app.domain.services.flows.deep_research import DeepResearchFlow
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.flows.workflow_graph import (
    END,
    START,
    WorkflowBuilder,
    WorkflowGraph,
    WorkflowState,
)

# Import LangGraph flow only when available
try:
    from app.domain.services.langgraph import LangGraphPlanActFlow

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LangGraphPlanActFlow = None
    LANGGRAPH_AVAILABLE = False

# Deprecated experimental flows — import directly if needed:
#   from app.domain.services.flows.plan_act_graph import PlanActGraphFlow
#   from app.domain.services.flows.tree_of_thoughts_flow import TreeOfThoughtsFlow

__all__ = [
    "END",
    "START",
    "BaseFlow",
    "DeepResearchFlow",
    "DiscussFlow",
    "FlowStatus",
    "LangGraphPlanActFlow",
    "PlanActFlow",
    "WorkflowBuilder",
    "WorkflowGraph",
    "WorkflowState",
]
