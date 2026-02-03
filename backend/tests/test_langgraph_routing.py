from app.domain.models.plan import Plan, Step
from app.domain.services.langgraph.routing import route_after_planning


def test_route_after_planning_replan_on_validation_failure():
    state = {
        "plan_validation_failed": True,
        "verification_loops": 0,
        "max_verification_loops": 2,
        "plan": Plan(title="Test", goal="Goal", steps=[Step(id="1", description="Do thing")]),
    }
    assert route_after_planning(state) == "plan"


def test_route_after_planning_executes_after_max_validation_loops():
    state = {
        "plan_validation_failed": True,
        "verification_loops": 2,
        "max_verification_loops": 2,
        "plan": Plan(title="Test", goal="Goal", steps=[Step(id="1", description="Do thing")]),
    }
    assert route_after_planning(state) == "execute"


def test_route_after_planning_summarizes_when_done():
    state = {
        "all_steps_done": True,
        "plan": Plan(title="Test", goal="Goal", steps=[]),
    }
    assert route_after_planning(state) == "summarize"


def test_route_after_planning_verifies_when_verifier_present():
    state = {
        "plan": Plan(title="Test", goal="Goal", steps=[Step(id="1", description="Do thing")]),
        "verifier": object(),
    }
    assert route_after_planning(state) == "verify"


def test_route_after_planning_executes_without_verifier():
    state = {
        "plan": Plan(title="Test", goal="Goal", steps=[Step(id="1", description="Do thing")]),
        "verifier": None,
    }
    assert route_after_planning(state) == "execute"
