"""
Scheduled Task Model
Defines scheduled tasks for deferred or recurring agent execution.

Enhanced with Manus-style scheduling capabilities:
- Cron expression support
- Timezone handling
- Notification channels
- Output delivery options
- Execution history tracking
- Retry logic
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class ScheduleType(str, Enum):
    """Type of schedule."""

    ONCE = "once"  # One-time execution at scheduled_at
    RECURRING = "recurring"  # Recurring execution at interval
    DAILY = "daily"  # Daily at specific time
    WEEKLY = "weekly"  # Weekly on specific day(s)
    MONTHLY = "monthly"  # Monthly on specific day
    CRON = "cron"  # Cron expression based


class NotificationChannel(str, Enum):
    """Notification delivery channels."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class OutputDeliveryMethod(str, Enum):
    """How to deliver task output."""

    FILE = "file"  # Save to file in workspace
    EMAIL = "email"  # Send via email
    WEBHOOK = "webhook"  # POST to webhook URL
    SESSION = "session"  # Keep in session (default)


class ScheduledTaskStatus(str, Enum):
    """Status of scheduled task."""

    PENDING = "pending"  # Waiting to execute
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished (for one-time tasks)
    CANCELLED = "cancelled"  # Cancelled by user
    FAILED = "failed"  # Execution failed
    PAUSED = "paused"  # Temporarily paused


class ExecutionStatus(str, Enum):
    """Status of a single execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ExecutionRecord(BaseModel):
    """Record of a single task execution."""

    execution_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime
    completed_at: datetime | None = None
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    duration_seconds: float | None = None
    result_summary: str | None = None
    error_message: str | None = None
    output_location: str | None = None  # File path or URL for output
    retry_number: int = 0


class ScheduleConfig(BaseModel):
    """Configuration for schedule timing."""

    # For DAILY
    time_of_day: str | None = None  # HH:MM format

    # For WEEKLY
    days_of_week: list[int] = Field(default_factory=list)  # 0=Monday, 6=Sunday

    # For MONTHLY
    day_of_month: int | None = None  # 1-31

    # For CRON
    cron_expression: str | None = None  # "0 9 * * 1-5" format


class NotificationConfig(BaseModel):
    """Configuration for notifications."""

    channels: list[NotificationChannel] = Field(default_factory=list)
    notify_on_success: bool = False
    notify_on_failure: bool = True
    notify_on_completion: bool = True  # For recurring tasks reaching max
    email_recipients: list[str] = Field(default_factory=list)
    webhook_url: str | None = None
    slack_webhook_url: str | None = None


class OutputConfig(BaseModel):
    """Configuration for output delivery."""

    delivery_method: OutputDeliveryMethod = OutputDeliveryMethod.SESSION
    file_path: str | None = None  # For FILE delivery
    email_recipients: list[str] = Field(default_factory=list)  # For EMAIL delivery
    webhook_url: str | None = None  # For WEBHOOK delivery


class ScheduledTask(BaseModel):
    """Scheduled task model for deferred or recurring agent execution.

    Enhanced with Manus-style scheduling capabilities:
    - Multiple schedule types (cron, daily, weekly, monthly)
    - Timezone support
    - Notification channels
    - Output delivery options
    - Execution history
    - Retry logic

    Constraints:
    - One active scheduled task per user (configurable)
    - Minimum interval for recurring tasks is 5 minutes (300 seconds)
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    session_id: str | None = None  # Session to execute in (created if None)

    # Task details
    name: str = ""  # Human-readable name for the task
    task_description: str  # What the agent should do
    schedule_type: ScheduleType = ScheduleType.ONCE

    # Timing
    scheduled_at: datetime  # When to execute (first execution for recurring)
    interval_seconds: int | None = None  # Interval for recurring (min 300 = 5 minutes)
    last_executed_at: datetime | None = None
    next_execution_at: datetime | None = None
    timezone: str = "UTC"  # User's timezone

    # Enhanced schedule configuration
    schedule_config: ScheduleConfig = Field(default_factory=ScheduleConfig)

    # Status tracking
    status: ScheduledTaskStatus = ScheduledTaskStatus.PENDING
    execution_count: int = 0
    max_executions: int | None = None  # Limit for recurring tasks (None = unlimited)

    # Retry configuration
    max_retries: int = 2
    retry_count: int = 0
    retry_delay_seconds: int = 60  # Delay between retries

    # Notification configuration
    notification_config: NotificationConfig = Field(default_factory=NotificationConfig)

    # Output delivery configuration
    output_config: OutputConfig = Field(default_factory=OutputConfig)

    # Execution history
    execution_history: list[ExecutionRecord] = Field(default_factory=list)
    last_execution_status: ExecutionStatus | None = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None
    tags: list[str] = Field(default_factory=list)  # For organization

    # Minimum interval for recurring tasks (5 minutes)
    MIN_INTERVAL_SECONDS: int = 300

    def validate_interval(self) -> bool:
        """Validate that recurring tasks have minimum interval"""
        return not (
            self.schedule_type == ScheduleType.RECURRING
            and (not self.interval_seconds or self.interval_seconds < self.MIN_INTERVAL_SECONDS)
        )

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

    def mark_executed(
        self,
        status: ExecutionStatus = ExecutionStatus.SUCCESS,
        result_summary: str | None = None,
        error_message: str | None = None,
        output_location: str | None = None,
    ) -> None:
        """Update task after execution and record in history."""
        now = datetime.now(UTC)

        # Calculate duration
        duration = None
        if self.last_executed_at:
            duration = (now - self.last_executed_at).total_seconds()

        # Create execution record
        record = ExecutionRecord(
            started_at=self.last_executed_at or now,
            completed_at=now,
            status=status,
            duration_seconds=duration,
            result_summary=result_summary,
            error_message=error_message,
            output_location=output_location,
            retry_number=self.retry_count,
        )

        # Add to history (keep last 100 records)
        self.execution_history.append(record)
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]

        self.last_executed_at = now
        self.last_execution_status = status
        self.execution_count += 1
        self.updated_at = now

        # Reset retry count on success
        if status == ExecutionStatus.SUCCESS:
            self.retry_count = 0

        if self.schedule_type == ScheduleType.ONCE:
            self.status = ScheduledTaskStatus.COMPLETED
        elif self.schedule_type in (
            ScheduleType.RECURRING,
            ScheduleType.DAILY,
            ScheduleType.WEEKLY,
            ScheduleType.MONTHLY,
            ScheduleType.CRON,
        ):
            # Check if max executions reached
            if self.max_executions and self.execution_count >= self.max_executions:
                self.status = ScheduledTaskStatus.COMPLETED
            else:
                # Schedule next execution
                self.next_execution_at = self._calculate_next_execution()

    def _calculate_next_execution(self) -> datetime:
        """Calculate the next execution time based on schedule type."""
        now = datetime.now(UTC)
        base_time = self.last_executed_at or now

        if self.schedule_type == ScheduleType.RECURRING and self.interval_seconds:
            return base_time + timedelta(seconds=self.interval_seconds)

        if self.schedule_type == ScheduleType.DAILY:
            # Execute at the same time tomorrow
            next_day = base_time + timedelta(days=1)
            if self.schedule_config.time_of_day:
                parts = self.schedule_config.time_of_day.split(":")
                hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                next_day = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return next_day

        if self.schedule_type == ScheduleType.WEEKLY:
            # Find next matching day of week
            days_of_week = self.schedule_config.days_of_week or [base_time.weekday()]
            current_day = base_time.weekday()
            days_ahead = 7  # Default to same day next week

            for day in sorted(days_of_week):
                if day > current_day:
                    days_ahead = day - current_day
                    break
            else:
                # Wrap to next week
                if days_of_week:
                    days_ahead = 7 - current_day + min(days_of_week)

            return base_time + timedelta(days=days_ahead)

        if self.schedule_type == ScheduleType.MONTHLY:
            # Same day next month
            day_of_month = self.schedule_config.day_of_month or base_time.day
            next_month = base_time.month + 1
            next_year = base_time.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            return base_time.replace(year=next_year, month=next_month, day=min(day_of_month, 28))

        if self.schedule_type == ScheduleType.CRON:
            # For cron, we'd need a cron parser library
            # For now, fall back to interval
            if self.interval_seconds:
                return base_time + timedelta(seconds=self.interval_seconds)
            return base_time + timedelta(days=1)

        # Fallback
        return now + timedelta(hours=1)

    def should_retry(self) -> bool:
        """Check if the task should be retried after failure."""
        return self.last_execution_status == ExecutionStatus.FAILED and self.retry_count < self.max_retries

    def increment_retry(self) -> datetime:
        """Increment retry count and return next retry time."""
        self.retry_count += 1
        self.updated_at = datetime.now(UTC)
        return datetime.now(UTC) + timedelta(seconds=self.retry_delay_seconds)

    def pause(self) -> None:
        """Pause the scheduled task."""
        self.status = ScheduledTaskStatus.PAUSED
        self.updated_at = datetime.now(UTC)

    def resume(self) -> None:
        """Resume a paused task."""
        if self.status == ScheduledTaskStatus.PAUSED:
            self.status = ScheduledTaskStatus.PENDING
            self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        """Cancel the scheduled task."""
        self.status = ScheduledTaskStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        """Mark task as failed with error message."""
        self.status = ScheduledTaskStatus.FAILED
        self.error_message = error
        self.last_execution_status = ExecutionStatus.FAILED
        self.updated_at = datetime.now(UTC)

    def get_execution_stats(self) -> dict:
        """Get execution statistics from history."""
        if not self.execution_history:
            return {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": None,
            }

        success_count = sum(1 for r in self.execution_history if r.status == ExecutionStatus.SUCCESS)
        failure_count = sum(1 for r in self.execution_history if r.status == ExecutionStatus.FAILED)
        durations = [r.duration_seconds for r in self.execution_history if r.duration_seconds]
        avg_duration = sum(durations) / len(durations) if durations else None

        return {
            "total_executions": len(self.execution_history),
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / len(self.execution_history) if self.execution_history else 0.0,
            "avg_duration_seconds": avg_duration,
        }
