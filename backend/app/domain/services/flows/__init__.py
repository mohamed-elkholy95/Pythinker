from app.domain.services.flows.base import BaseFlow
from app.domain.services.flows.deep_research import DeepResearchFlow
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.flows.plan_act_graph import PlanActGraphFlow
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

__all__ = [
    "END",
    "START",
    "BaseFlow",
    "DeepResearchFlow",
    "DiscussFlow",
    "LangGraphPlanActFlow",
    "PlanActFlow",
    "PlanActGraphFlow",
    "WorkflowBuilder",
    "WorkflowGraph",
    "WorkflowState",
]
