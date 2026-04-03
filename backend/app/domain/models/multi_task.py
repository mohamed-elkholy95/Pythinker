"""Multi-task challenge domain models."""

import logging
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.utils.task_ids import generate_workflow_task_id

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of individual task within challenge"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


def is_terminal_status(status: TaskStatus) -> bool:
    """Return True when a multi-task status is terminal."""
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)


class DeliverableType(str, Enum):
    """Type of deliverable"""

    FILE = "file"
    DIRECTORY = "directory"
    REPORT = "report"
    DATA = "data"
    CODE = "code"
    ARTIFACT = "artifact"


class Deliverable(BaseModel):
    """Expected deliverable for a task"""

    name: str
    type: DeliverableType
    path: str  # Expected path in workspace
    description: str
    required: bool = True
    validation_criteria: str | None = None


class TaskDefinition(BaseModel):
    """Definition of a single task within multi-task challenge"""

    id: str = Field(default_factory=generate_workflow_task_id)
    title: str
    description: str
    deliverables: list[Deliverable] = Field(default_factory=list)
    workspace_folder: str | None = None  # e.g., "task_1_research"
    validation_criteria: str | None = None
    estimated_complexity: float = 0.5  # 0.0-1.0
    depends_on: list[str] = Field(default_factory=list)  # Task IDs this depends on
    status: TaskStatus = TaskStatus.PENDING

    # Execution tracking
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    iterations_used: int = 0

    def can_transition(self) -> bool:
        """Return True when the task can still change state."""
        return not is_terminal_status(self.status)

    def transition_to(
        self,
        status: TaskStatus | str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_seconds: float | None = None,
    ) -> bool:
        """Transition the task unless it has already reached a terminal state."""
        next_status = status if isinstance(status, TaskStatus) else TaskStatus(status)
        if next_status == self.status:
            return False
        if is_terminal_status(self.status):
            logger.debug("Ignoring transition for terminal task %s (%s -> %s)", self.id, self.status, next_status)
            return False

        self.status = next_status
        if started_at is not None:
            self.started_at = started_at
        if completed_at is not None:
            self.completed_at = completed_at
        if duration_seconds is not None:
            self.duration_seconds = duration_seconds
        return True

    def mark_started(self, started_at: datetime | None = None) -> bool:
        """Mark the task as in progress."""
        return self.transition_to(TaskStatus.IN_PROGRESS, started_at=started_at)

    def mark_completed(self, *, completed_at: datetime | None = None, duration_seconds: float | None = None) -> bool:
        """Mark the task as completed."""
        return self.transition_to(
            TaskStatus.COMPLETED,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
        )

    def mark_failed(self, *, completed_at: datetime | None = None, duration_seconds: float | None = None) -> bool:
        """Mark the task as failed."""
        return self.transition_to(
            TaskStatus.FAILED,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
        )

    def mark_skipped(self, *, completed_at: datetime | None = None, duration_seconds: float | None = None) -> bool:
        """Mark the task as skipped."""
        return self.transition_to(
            TaskStatus.SKIPPED,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
        )


class TaskResult(BaseModel):
    """Result of task execution"""

    task_id: str
    status: TaskStatus
    deliverables_created: list[str] = Field(default_factory=list)  # File paths
    validation_passed: bool = False
    validation_report: str | None = None
    error_message: str | None = None
    duration_seconds: float
    iterations_used: int


class MultiTaskChallenge(BaseModel):
    """Container for multi-task challenge execution"""

    id: str = Field(default_factory=generate_workflow_task_id)
    title: str
    description: str
    tasks: list[TaskDefinition] = Field(default_factory=list)

    # Workspace configuration
    workspace_root: str = "/workspace"
    workspace_template: str | None = None  # "research", "data_analysis", "code_project"

    # Progress tracking
    current_task_index: int = 0
    completed_tasks: list[str] = Field(default_factory=list)  # Task IDs
    failed_tasks: list[str] = Field(default_factory=list)  # Task IDs

    # Execution metadata
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float | None = None

    # Results
    task_results: list[TaskResult] = Field(default_factory=list)
    overall_success: bool = False

    def get_current_task(self) -> TaskDefinition | None:
        """Get currently active task"""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    def current_task_is_terminal(self) -> bool:
        """Return True when the current task can no longer transition."""
        current_task = self.get_current_task()
        return bool(current_task and is_terminal_status(current_task.status))

    def advance_to_next_task(self) -> bool:
        """Advance to the next task unless the current task is terminal."""
        if self.current_task_is_terminal():
            logger.debug("Skipping task advance because current task is terminal")
            return False
        if self.current_task_index >= len(self.tasks) - 1:
            return False
        self.current_task_index += 1
        return True

    def get_progress_percentage(self) -> float:
        """Calculate overall progress"""
        if not self.tasks:
            return 0.0
        return (len(self.completed_tasks) / len(self.tasks)) * 100
