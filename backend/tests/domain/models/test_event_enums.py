from app.domain.models.event import PlanningPhase


def test_tool_executing_phase_exists():
    """TOOL_EXECUTING phase must exist for tool heartbeat events."""
    assert hasattr(PlanningPhase, "TOOL_EXECUTING")
    assert PlanningPhase.TOOL_EXECUTING.value == "tool_executing"
