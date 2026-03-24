"""
Unified state transition validation for agent workflows.

Provides a centralized state machine definition and validation to ensure
consistent agent behavior across the system.
"""

from enum import Enum


class AgentStatus(str, Enum):
    """Agent status states for the PlanActFlow."""

    IDLE = "idle"
    PLANNING = "planning"
    VERIFYING = "verifying"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    UPDATING = "updating"
    REFLECTING = "reflecting"
    ERROR = "error"


# Valid state transitions for AgentStatus
VALID_TRANSITIONS: dict[AgentStatus, list[AgentStatus]] = {
    AgentStatus.IDLE: [AgentStatus.PLANNING],
    AgentStatus.PLANNING: [
        AgentStatus.VERIFYING,
        AgentStatus.EXECUTING,
        AgentStatus.COMPLETED,  # For empty plans
        AgentStatus.ERROR,
    ],
    AgentStatus.VERIFYING: [
        AgentStatus.EXECUTING,
        AgentStatus.PLANNING,  # Revision needed
        AgentStatus.SUMMARIZING,  # Verification failed
        AgentStatus.ERROR,
    ],
    AgentStatus.EXECUTING: [
        AgentStatus.UPDATING,
        AgentStatus.SUMMARIZING,
        AgentStatus.REFLECTING,
        AgentStatus.PLANNING,  # Re-plan when new user message arrives mid-execution
        AgentStatus.ERROR,
    ],
    AgentStatus.UPDATING: [
        AgentStatus.EXECUTING,
        AgentStatus.ERROR,
    ],
    AgentStatus.SUMMARIZING: [
        AgentStatus.COMPLETED,
        AgentStatus.ERROR,
    ],
    AgentStatus.COMPLETED: [
        AgentStatus.IDLE,
    ],
    AgentStatus.REFLECTING: [
        AgentStatus.EXECUTING,
        AgentStatus.SUMMARIZING,
        AgentStatus.PLANNING,
        AgentStatus.ERROR,
    ],
    AgentStatus.ERROR: [
        AgentStatus.PLANNING,
        AgentStatus.EXECUTING,
        AgentStatus.IDLE,
    ],
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status: AgentStatus, to_status: AgentStatus, message: str | None = None):
        self.from_status = from_status
        self.to_status = to_status
        if message:
            super().__init__(message)
        else:
            valid = VALID_TRANSITIONS.get(from_status, [])
            super().__init__(
                f"Invalid transition from {from_status.value} to {to_status.value}. "
                f"Valid transitions: {[s.value for s in valid]}"
            )


def validate_transition(from_status: AgentStatus, to_status: AgentStatus) -> bool:
    """Check if a state transition is valid.

    Args:
        from_status: The current status
        to_status: The target status

    Returns:
        True if the transition is valid, False otherwise
    """
    valid_targets = VALID_TRANSITIONS.get(from_status, [])
    return to_status in valid_targets


def get_valid_transitions(status: AgentStatus) -> list[AgentStatus]:
    """Get list of valid transition targets from a given status.

    Args:
        status: The current status

    Returns:
        List of valid target statuses
    """
    return VALID_TRANSITIONS.get(status, [])


def is_terminal_status(status: AgentStatus) -> bool:
    """Check if a status is terminal (no further transitions except to IDLE).

    Args:
        status: The status to check

    Returns:
        True if terminal, False otherwise
    """
    return status == AgentStatus.COMPLETED


def is_error_status(status: AgentStatus) -> bool:
    """Check if a status indicates an error state.

    Args:
        status: The status to check

    Returns:
        True if error state, False otherwise
    """
    return status == AgentStatus.ERROR


def get_recovery_paths(from_error: bool = True) -> list[AgentStatus]:
    """Get possible recovery paths from error state.

    Args:
        from_error: Whether we're recovering from error state

    Returns:
        List of valid recovery target statuses
    """
    if from_error:
        return VALID_TRANSITIONS.get(AgentStatus.ERROR, [])
    return []
