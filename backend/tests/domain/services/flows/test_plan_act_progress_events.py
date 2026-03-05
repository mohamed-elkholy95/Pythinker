"""Tests for verification phase progress events in PlanActFlow.

Validates that:
1. PlanningPhase enum has VERIFYING and EXECUTING_SETUP members.
2. FlowStatus enum has VERIFYING, REFLECTING, and FAILED members.
3. ProgressEvent can be constructed with the new PlanningPhase values.
"""

import pytest

from app.domain.models.event import PlanningPhase, ProgressEvent
from app.domain.models.flow_state import FlowStatus

# ---------------------------------------------------------------------------
# PlanningPhase enum
# ---------------------------------------------------------------------------


def test_planning_phase_has_verifying() -> None:
    assert PlanningPhase.VERIFYING == "verifying"


def test_planning_phase_has_executing_setup() -> None:
    assert PlanningPhase.EXECUTING_SETUP == "executing_setup"


def test_planning_phase_existing_members_unchanged() -> None:
    """Regression: existing members must keep their original values."""
    assert PlanningPhase.RECEIVED == "received"
    assert PlanningPhase.ANALYZING == "analyzing"
    assert PlanningPhase.PLANNING == "planning"
    assert PlanningPhase.FINALIZING == "finalizing"
    assert PlanningPhase.HEARTBEAT == "heartbeat"
    assert PlanningPhase.WAITING == "waiting"


# ---------------------------------------------------------------------------
# FlowStatus enum
# ---------------------------------------------------------------------------


def test_flow_status_has_verifying() -> None:
    assert FlowStatus.VERIFYING == "verifying"


def test_flow_status_has_reflecting() -> None:
    assert FlowStatus.REFLECTING == "reflecting"


def test_flow_status_has_failed() -> None:
    assert FlowStatus.FAILED == "failed"


def test_flow_status_existing_members_unchanged() -> None:
    """Regression: existing members must keep their original values."""
    assert FlowStatus.IDLE == "idle"
    assert FlowStatus.PLANNING == "planning"
    assert FlowStatus.EXECUTING == "executing"
    assert FlowStatus.SUMMARIZING == "summarizing"
    assert FlowStatus.COMPLETED == "completed"
    assert FlowStatus.ERROR == "error"
    assert FlowStatus.PAUSED == "paused"


# ---------------------------------------------------------------------------
# ProgressEvent construction with new phases
# ---------------------------------------------------------------------------


def test_progress_event_verifying_phase() -> None:
    event = ProgressEvent(
        phase=PlanningPhase.VERIFYING,
        message="Checking plan quality...",
    )
    assert event.phase == PlanningPhase.VERIFYING
    assert event.message == "Checking plan quality..."
    assert event.type == "progress"
    assert event.progress_percent is None


def test_progress_event_executing_setup_phase() -> None:
    event = ProgressEvent(
        phase=PlanningPhase.EXECUTING_SETUP,
        message="Preparing to execute plan...",
        progress_percent=0,
    )
    assert event.phase == PlanningPhase.EXECUTING_SETUP
    assert event.message == "Preparing to execute plan..."
    assert event.progress_percent == 0


@pytest.mark.parametrize(
    "phase",
    [
        PlanningPhase.VERIFYING,
        PlanningPhase.EXECUTING_SETUP,
    ],
)
def test_progress_event_serialises_new_phases(phase: PlanningPhase) -> None:
    """Ensure model_dump() serialises new phases as plain strings."""
    event = ProgressEvent(phase=phase, message="test")
    data = event.model_dump()
    assert data["phase"] == phase.value
