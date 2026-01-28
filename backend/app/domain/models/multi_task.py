"""Multi-task challenge domain models."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from enum import Enum
import uuid


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
    validation_criteria: Optional[str] = None


class TaskDefinition(BaseModel):
    """Definition of a single task within multi-task challenge"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str
    deliverables: List[Deliverable] = []
    workspace_folder: Optional[str] = None  # e.g., "task_1_research"
    validation_criteria: Optional[str] = None
    estimated_complexity: float = 0.5  # 0.0-1.0
    depends_on: List[str] = []  # Task IDs this depends on
    status: TaskStatus = TaskStatus.PENDING

    # Execution tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    iterations_used: int = 0


class TaskResult(BaseModel):
    """Result of task execution"""
    task_id: str
    status: TaskStatus
    deliverables_created: List[str] = []  # File paths
    validation_passed: bool = False
    validation_report: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float
    iterations_used: int


class MultiTaskChallenge(BaseModel):
    """Container for multi-task challenge execution"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    title: str
    description: str
    tasks: List[TaskDefinition] = []

    # Workspace configuration
    workspace_root: str = "/workspace"
    workspace_template: Optional[str] = None  # "research", "data_analysis", "code_project"

    # Progress tracking
    current_task_index: int = 0
    completed_tasks: List[str] = []  # Task IDs
    failed_tasks: List[str] = []  # Task IDs

    # Execution metadata
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None

    # Results
    task_results: List[TaskResult] = []
    overall_success: bool = False

    def get_current_task(self) -> Optional[TaskDefinition]:
        """Get currently active task"""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    def get_progress_percentage(self) -> float:
        """Calculate overall progress"""
        if not self.tasks:
            return 0.0
        return (len(self.completed_tasks) / len(self.tasks)) * 100
