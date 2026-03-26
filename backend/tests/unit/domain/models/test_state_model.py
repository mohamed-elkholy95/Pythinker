"""Tests for state machine models (app.domain.models.state_model).

Covers AgentStatus enum, VALID_TRANSITIONS completeness,
validate_transition, get_valid_transitions, is_terminal_status,
is_error_status, get_recovery_paths, and StateTransitionError.
"""

import pytest

from app.domain.models.state_model import (
    VALID_TRANSITIONS,
    AgentStatus,
    StateTransitionError,
    get_recovery_paths,
    get_valid_transitions,
    is_error_status,
    is_terminal_status,
    validate_transition,
)

# ── AgentStatus ──────────────────────────────────────────────────────


class TestAgentStatus:
    def test_all_values(self) -> None:
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.PLANNING == "planning"
        assert AgentStatus.VERIFYING == "verifying"
        assert AgentStatus.EXECUTING == "executing"
        assert AgentStatus.SUMMARIZING == "summarizing"
        assert AgentStatus.COMPLETED == "completed"
        assert AgentStatus.UPDATING == "updating"
        assert AgentStatus.REFLECTING == "reflecting"
        assert AgentStatus.ERROR == "error"

    def test_all_statuses_in_transition_table(self) -> None:
        for status in AgentStatus:
            assert status in VALID_TRANSITIONS, f"{status} missing from VALID_TRANSITIONS"


# ── validate_transition ──────────────────────────────────────────────


class TestValidateTransition:
    def test_idle_to_planning(self) -> None:
        assert validate_transition(AgentStatus.IDLE, AgentStatus.PLANNING) is True

    def test_idle_to_executing_invalid(self) -> None:
        assert validate_transition(AgentStatus.IDLE, AgentStatus.EXECUTING) is False

    def test_planning_to_verifying(self) -> None:
        assert validate_transition(AgentStatus.PLANNING, AgentStatus.VERIFYING) is True

    def test_planning_to_executing(self) -> None:
        assert validate_transition(AgentStatus.PLANNING, AgentStatus.EXECUTING) is True

    def test_planning_to_completed(self) -> None:
        assert validate_transition(AgentStatus.PLANNING, AgentStatus.COMPLETED) is True

    def test_planning_to_error(self) -> None:
        assert validate_transition(AgentStatus.PLANNING, AgentStatus.ERROR) is True

    def test_verifying_to_executing(self) -> None:
        assert validate_transition(AgentStatus.VERIFYING, AgentStatus.EXECUTING) is True

    def test_verifying_to_planning_revision(self) -> None:
        assert validate_transition(AgentStatus.VERIFYING, AgentStatus.PLANNING) is True

    def test_executing_to_updating(self) -> None:
        assert validate_transition(AgentStatus.EXECUTING, AgentStatus.UPDATING) is True

    def test_executing_to_summarizing(self) -> None:
        assert validate_transition(AgentStatus.EXECUTING, AgentStatus.SUMMARIZING) is True

    def test_executing_to_reflecting(self) -> None:
        assert validate_transition(AgentStatus.EXECUTING, AgentStatus.REFLECTING) is True

    def test_executing_to_planning_replan(self) -> None:
        assert validate_transition(AgentStatus.EXECUTING, AgentStatus.PLANNING) is True

    def test_updating_to_executing(self) -> None:
        assert validate_transition(AgentStatus.UPDATING, AgentStatus.EXECUTING) is True

    def test_summarizing_to_completed(self) -> None:
        assert validate_transition(AgentStatus.SUMMARIZING, AgentStatus.COMPLETED) is True

    def test_completed_to_idle(self) -> None:
        assert validate_transition(AgentStatus.COMPLETED, AgentStatus.IDLE) is True

    def test_completed_to_planning_invalid(self) -> None:
        assert validate_transition(AgentStatus.COMPLETED, AgentStatus.PLANNING) is False

    def test_reflecting_to_executing(self) -> None:
        assert validate_transition(AgentStatus.REFLECTING, AgentStatus.EXECUTING) is True

    def test_reflecting_to_summarizing(self) -> None:
        assert validate_transition(AgentStatus.REFLECTING, AgentStatus.SUMMARIZING) is True

    def test_reflecting_to_planning(self) -> None:
        assert validate_transition(AgentStatus.REFLECTING, AgentStatus.PLANNING) is True

    def test_error_to_planning(self) -> None:
        assert validate_transition(AgentStatus.ERROR, AgentStatus.PLANNING) is True

    def test_error_to_executing(self) -> None:
        assert validate_transition(AgentStatus.ERROR, AgentStatus.EXECUTING) is True

    def test_error_to_idle(self) -> None:
        assert validate_transition(AgentStatus.ERROR, AgentStatus.IDLE) is True


# ── get_valid_transitions ────────────────────────────────────────────


class TestGetValidTransitions:
    def test_idle_transitions(self) -> None:
        transitions = get_valid_transitions(AgentStatus.IDLE)
        assert AgentStatus.PLANNING in transitions
        assert len(transitions) == 1

    def test_executing_transitions(self) -> None:
        transitions = get_valid_transitions(AgentStatus.EXECUTING)
        assert AgentStatus.UPDATING in transitions
        assert AgentStatus.SUMMARIZING in transitions
        assert AgentStatus.REFLECTING in transitions
        assert AgentStatus.PLANNING in transitions
        assert AgentStatus.ERROR in transitions

    def test_completed_transitions(self) -> None:
        transitions = get_valid_transitions(AgentStatus.COMPLETED)
        assert AgentStatus.IDLE in transitions
        assert len(transitions) == 1

    def test_error_has_recovery_paths(self) -> None:
        transitions = get_valid_transitions(AgentStatus.ERROR)
        assert len(transitions) >= 2


# ── is_terminal_status ───────────────────────────────────────────────


class TestIsTerminalStatus:
    def test_completed_is_terminal(self) -> None:
        assert is_terminal_status(AgentStatus.COMPLETED) is True

    def test_idle_not_terminal(self) -> None:
        assert is_terminal_status(AgentStatus.IDLE) is False

    def test_error_not_terminal(self) -> None:
        assert is_terminal_status(AgentStatus.ERROR) is False

    def test_executing_not_terminal(self) -> None:
        assert is_terminal_status(AgentStatus.EXECUTING) is False


# ── is_error_status ──────────────────────────────────────────────────


class TestIsErrorStatus:
    def test_error_is_error(self) -> None:
        assert is_error_status(AgentStatus.ERROR) is True

    def test_completed_not_error(self) -> None:
        assert is_error_status(AgentStatus.COMPLETED) is False

    def test_executing_not_error(self) -> None:
        assert is_error_status(AgentStatus.EXECUTING) is False


# ── get_recovery_paths ───────────────────────────────────────────────


class TestGetRecoveryPaths:
    def test_from_error(self) -> None:
        paths = get_recovery_paths(from_error=True)
        assert AgentStatus.PLANNING in paths
        assert AgentStatus.EXECUTING in paths
        assert AgentStatus.IDLE in paths

    def test_not_from_error(self) -> None:
        paths = get_recovery_paths(from_error=False)
        assert paths == []


# ── StateTransitionError ─────────────────────────────────────────────


class TestStateTransitionError:
    def test_default_message(self) -> None:
        err = StateTransitionError(AgentStatus.IDLE, AgentStatus.EXECUTING)
        assert "idle" in str(err)
        assert "executing" in str(err)
        assert "Valid transitions" in str(err)
        assert err.from_status == AgentStatus.IDLE
        assert err.to_status == AgentStatus.EXECUTING

    def test_custom_message(self) -> None:
        err = StateTransitionError(AgentStatus.IDLE, AgentStatus.EXECUTING, "Custom error")
        assert str(err) == "Custom error"

    def test_is_exception(self) -> None:
        err = StateTransitionError(AgentStatus.IDLE, AgentStatus.EXECUTING)
        assert isinstance(err, Exception)

    def test_can_be_raised(self) -> None:
        with pytest.raises(StateTransitionError):
            raise StateTransitionError(AgentStatus.IDLE, AgentStatus.EXECUTING)
