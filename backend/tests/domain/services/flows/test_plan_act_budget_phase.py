"""Tests for budget phase mapping during UPDATING transitions (Fix 7)."""

import time
from unittest.mock import MagicMock

from app.domain.models.state_model import AgentStatus


def _make_flow():
    """Create a minimal mock PlanActFlow for _transition_to testing."""
    from app.domain.services.flows.plan_act import PlanActFlow

    flow = MagicMock(spec=PlanActFlow)
    flow.status = AgentStatus.EXECUTING
    flow.planner = MagicMock()
    flow.executor = MagicMock()
    flow.verifier = None
    flow.plan = None
    flow._plan_validation_failures = 0
    flow._error_recovery = MagicMock()
    flow._log_search_health = MagicMock()
    flow._rebalance_token_budget = MagicMock()
    flow._last_transition_time = time.time()
    flow._pending_events = []
    flow._log = MagicMock()
    # Bind the real _transition_to method
    flow._transition_to = PlanActFlow._transition_to.__get__(flow)
    return flow


def test_updating_sets_planner_phase_to_executing():
    """UPDATING transition should set planner._active_phase = 'executing'."""
    flow = _make_flow()
    flow._transition_to(AgentStatus.UPDATING)
    assert flow.planner._active_phase == "executing"


def test_planning_sets_planner_phase_to_planning():
    """PLANNING transition should set planner._active_phase = 'planning'."""
    flow = _make_flow()
    flow.status = AgentStatus.IDLE
    flow._transition_to(AgentStatus.PLANNING)
    assert flow.planner._active_phase == "planning"


def test_executing_clears_executor_phase():
    """EXECUTING transition should set executor._active_phase = None."""
    flow = _make_flow()
    flow.status = AgentStatus.PLANNING
    flow._transition_to(AgentStatus.EXECUTING)
    assert flow.executor._active_phase is None
