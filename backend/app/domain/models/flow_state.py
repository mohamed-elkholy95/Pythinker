"""
Flow state persistence models for checkpoint/recovery.

Enables resumption of agent flows after crashes or interruptions.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FlowStatus(str, Enum):
    """Status of a flow execution"""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    UPDATING = "updating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


class FlowStateSnapshot(BaseModel):
    """
    Snapshot of flow state for persistence and recovery.

    Captures all necessary state to resume a flow from where it left off.
    """

    # Identifiers
    agent_id: str
    session_id: str
    flow_id: str = Field(default_factory=lambda: "")

    # State information
    status: FlowStatus = FlowStatus.IDLE
    previous_status: FlowStatus | None = None

    # Plan state
    plan_id: str | None = None
    current_step_id: str | None = None
    completed_steps: list[str] = Field(default_factory=list)

    # Error state
    error_message: str | None = None
    error_type: str | None = None
    recovery_attempts: int = 0

    # Iteration tracking
    iteration_count: int = 0
    max_iterations: int = 100

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_activity_at: datetime = Field(default_factory=datetime.now)

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update(self, **kwargs) -> "FlowStateSnapshot":
        """Create updated snapshot with new values"""
        data = self.model_dump()
        data.update(kwargs)
        data["updated_at"] = datetime.now()
        data["last_activity_at"] = datetime.now()
        return FlowStateSnapshot.model_validate(data)

    def mark_step_completed(self, step_id: str) -> "FlowStateSnapshot":
        """Mark a step as completed"""
        new_completed = self.completed_steps.copy()
        if step_id not in new_completed:
            new_completed.append(step_id)
        return self.update(completed_steps=new_completed, current_step_id=None)

    def enter_error_state(self, error_message: str, error_type: str | None = None) -> "FlowStateSnapshot":
        """Transition to error state"""
        return self.update(
            previous_status=self.status, status=FlowStatus.ERROR, error_message=error_message, error_type=error_type
        )

    def recover_from_error(self) -> "FlowStateSnapshot":
        """Attempt to recover from error state"""
        if self.status != FlowStatus.ERROR:
            return self

        return self.update(
            status=self.previous_status or FlowStatus.IDLE,
            previous_status=FlowStatus.ERROR,
            recovery_attempts=self.recovery_attempts + 1,
            error_message=None,
            error_type=None,
        )

    def can_recover(self, max_attempts: int = 3) -> bool:
        """Check if recovery is possible"""
        return self.status == FlowStatus.ERROR and self.recovery_attempts < max_attempts

    def increment_iteration(self) -> "FlowStateSnapshot":
        """Increment iteration count"""
        return self.update(iteration_count=self.iteration_count + 1)

    def is_complete(self) -> bool:
        """Check if flow is complete"""
        return self.status == FlowStatus.COMPLETED

    def is_error(self) -> bool:
        """Check if flow is in error state"""
        return self.status == FlowStatus.ERROR
