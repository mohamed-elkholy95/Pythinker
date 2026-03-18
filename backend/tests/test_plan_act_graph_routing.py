from app.domain.services.flows.plan_act_graph import PlanActState, create_plan_act_graph


def _get_router(graph, node_name):
    return graph._conditional_edges[node_name].router


def test_plan_act_graph_route_after_planning_replan_on_validation_failure():
    graph = create_plan_act_graph()
    router = _get_router(graph, "planning")
    state = PlanActState(
        verification_verdict="revise",
        verification_loops=0,
        max_verification_loops=2,
    )
    assert router(state) == "planning"


def test_plan_act_graph_route_after_planning_executes_after_max_loops():
    graph = create_plan_act_graph()
    router = _get_router(graph, "planning")
    state = PlanActState(
        verification_verdict="revise",
        verification_loops=2,
        max_verification_loops=2,
    )
    assert router(state) == "executing"
