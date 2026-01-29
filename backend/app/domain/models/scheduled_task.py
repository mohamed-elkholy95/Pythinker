"""
Scheduled Task Model
Defines scheduled tasks for deferred or recurring agent execution.
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ScheduleType(str, Enum):
    """Type of schedule"""
    ONCE = "once"       # One-time execution at scheduled_at
    RECURRING = "recurring"  # Recurring execution at interval


class ScheduledTaskStatus(str, Enum):
    """Status of scheduled task"""
    PENDING = "pending"     # Waiting to execute
    RUNNING = "running"     # Currently executing
    COMPLETED = "completed"  # Finished (for one-time tasks)
    CANCELLED = "cancelled"  # Cancelled by user
    FAILED = "failed"       # Execution failed


class ScheduledTask(BaseModel):
    """
    Scheduled task model for deferred or recurring agent execution.

    Constraints:
    - One active scheduled task per user
    - Minimum interval for recurring tasks is 5 minutes (300 seconds)
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    session_id: str | None = None  # Session to execute in (created if None)

    # Task details
    task_description: str  # What the agent should do
    schedule_type: ScheduleType = ScheduleType.ONCE

    # Timing
    scheduled_at: datetime  # When to execute (first execution for recurring)
    interval_seconds: int | None = None  # Interval for recurring (min 300 = 5 minutes)
    last_executed_at: datetime | None = None
    next_execution_at: datetime | None = None

    # Status tracking
    status: ScheduledTaskStatus = ScheduledTaskStatus.PENDING
    execution_count: int = 0
    max_executions: int | None = None  # Limit for recurring tasks (None = unlimited)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None

    # Minimum interval for recurring tasks (5 minutes)
    MIN_INTERVAL_SECONDS: int = 300

    def validate_interval(self) -> bool:
        """Validate that recurring tasks have minimum interval"""
        if self.schedule_type == ScheduleType.RECURRING:
            if not self.interval_seconds or self.interval_seconds < self.MIN_INTERVAL_SECONDS:
                return False
        return True

    def is_active(self) -> bool:
        """Check if task is active (pending or running)"""
        return self.status in (ScheduledTaskStatus.PENDING, ScheduledTaskStatus.RUNNING)

    def can_execute(self) -> bool:
        """Check if task is ready for execution"""
        if not self.is_active():
            return False
        now = datetime.now(UTC)
        target_time = self.next_execution_at or self.scheduled_at
        return now >= target_time

    def mark_executed(self) -> None:
        """Update task after execution"""
        self.last_executed_at = datetime.now(UTC)
        self.execution_count += 1
        self.updated_at = datetime.now(UTC)

        if self.schedule_type == ScheduleType.ONCE:
            self.status = ScheduledTaskStatus.COMPLETED
        elif self.schedule_type == ScheduleType.RECURRING:
            # Check if max executions reached
            if self.max_executions and self.execution_count >= self.max_executions:
                self.status = ScheduledTaskStatus.COMPLETED
            else:
                # Schedule next execution
                if self.interval_seconds:
                    from datetime import timedelta
                    self.next_execution_at = self.last_executed_at + timedelta(seconds=self.interval_seconds)

    def cancel(self) -> None:
        """Cancel the scheduled task"""
        self.status = ScheduledTaskStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        """Mark task as failed with error message"""
        self.status = ScheduledTaskStatus.FAILED
        self.error_message = error
        self.updated_at = datetime.now(UTC)
