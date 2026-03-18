"""Multi-task challenge domain models."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of individual task within challenge"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


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

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
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

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
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

    def get_progress_percentage(self) -> float:
        """Calculate overall progress"""
        if not self.tasks:
            return 0.0
        return (len(self.completed_tasks) / len(self.tasks)) * 100
