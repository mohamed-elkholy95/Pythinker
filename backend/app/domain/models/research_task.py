"""Research task model for wide research pattern.

This model enables the "Wide Research" pattern where:
- Complex research is decomposed into independent sub-tasks
- Sub-tasks run in parallel with isolated contexts
- The 100th item gets the same quality attention as the 1st
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResearchStatus(str, Enum):
    """Status of a research sub-task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResearchTask(BaseModel):
    """
    A single research sub-task in wide research.

    Each task is independent and can be processed in parallel
    by separate agent instances without context interference.

    Attributes:
        id: Unique identifier for the research task
        query: The specific research query to investigate
        parent_task_id: ID of the parent research request
        index: Position in the research batch (0-indexed)
        total: Total items in the batch
        status: Current status of the task
        result: The research result (when completed)
        sources: List of source URLs/references
        error: Error message (when failed or skipped)
        started_at: Timestamp when task started
        completed_at: Timestamp when task completed
    """

    id: str = Field(default_factory=lambda: f"research_{datetime.utcnow().timestamp()}")
    query: str = Field(..., description="The specific research query")
    parent_task_id: str = Field(..., description="ID of the parent research request")
    index: int = Field(..., ge=0, description="Position in the research batch")
    total: int = Field(..., ge=1, description="Total items in batch")
    status: ResearchStatus = Field(default=ResearchStatus.PENDING)
    result: str | None = Field(default=None)
    sources: list[str] = Field(default_factory=list)
    error: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    def start(self) -> None:
        """Mark task as started."""
        self.status = ResearchStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()

    def complete(self, result: str, sources: list[str] | None = None) -> None:
        """Mark task as completed with result.

        Args:
            result: The research result text
            sources: Optional list of source URLs/references
        """
        self.status = ResearchStatus.COMPLETED
        self.result = result
        self.sources = sources or []
        self.completed_at = datetime.utcnow()

    def fail(self, error: str) -> None:
        """Mark task as failed.

        Args:
            error: Error message describing the failure
        """
        self.status = ResearchStatus.FAILED
        self.error = error
        self.completed_at = datetime.utcnow()

    def skip(self, reason: str = "Skipped by user") -> None:
        """Mark task as skipped.

        Args:
            reason: Reason for skipping the task
        """
        self.status = ResearchStatus.SKIPPED
        self.error = reason
        self.completed_at = datetime.utcnow()
