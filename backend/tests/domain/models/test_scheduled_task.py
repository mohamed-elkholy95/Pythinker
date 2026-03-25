"""Tests for scheduled task domain model."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models.scheduled_task import (
    ExecutionRecord,
    ExecutionStatus,
    NotificationChannel,
    NotificationConfig,
    OutputConfig,
    OutputDeliveryMethod,
    ScheduleConfig,
    ScheduledTask,
    ScheduledTaskStatus,
    ScheduleType,
)


@pytest.mark.unit
class TestScheduleTypeEnum:
    def test_all_values(self) -> None:
        expected = {"once", "recurring", "daily", "weekly", "monthly", "cron"}
        assert {t.value for t in ScheduleType} == expected


@pytest.mark.unit
class TestNotificationChannelEnum:
    def test_all_values(self) -> None:
        expected = {"email", "slack", "webhook", "in_app"}
        assert {c.value for c in NotificationChannel} == expected


@pytest.mark.unit
class TestOutputDeliveryMethodEnum:
    def test_all_values(self) -> None:
        expected = {"file", "email", "webhook", "session"}
        assert {m.value for m in OutputDeliveryMethod} == expected


@pytest.mark.unit
class TestScheduledTaskStatusEnum:
    def test_all_values(self) -> None:
        expected = {"pending", "running", "completed", "cancelled", "failed", "paused"}
        assert {s.value for s in ScheduledTaskStatus} == expected


@pytest.mark.unit
class TestExecutionStatusEnum:
    def test_all_values(self) -> None:
        expected = {"success", "failed", "timeout", "cancelled"}
        assert {s.value for s in ExecutionStatus} == expected


@pytest.mark.unit
class TestExecutionRecord:
    def test_construction(self) -> None:
        now = datetime.now(UTC)
        record = ExecutionRecord(started_at=now)
        assert record.started_at == now
        assert record.completed_at is None
        assert record.status == ExecutionStatus.SUCCESS
        assert record.retry_number == 0
        assert record.execution_id  # auto-generated

    def test_full_construction(self) -> None:
        now = datetime.now(UTC)
        record = ExecutionRecord(
            started_at=now,
            completed_at=now + timedelta(seconds=30),
            status=ExecutionStatus.FAILED,
            duration_seconds=30.0,
            result_summary="Task failed",
            error_message="Timeout exceeded",
        )
        assert record.status == ExecutionStatus.FAILED
        assert record.duration_seconds == 30.0


@pytest.mark.unit
class TestScheduleConfig:
    def test_defaults(self) -> None:
        config = ScheduleConfig()
        assert config.time_of_day is None
        assert config.days_of_week == []
        assert config.day_of_month is None
        assert config.cron_expression is None


@pytest.mark.unit
class TestNotificationConfig:
    def test_defaults(self) -> None:
        config = NotificationConfig()
        assert config.channels == []
        assert config.notify_on_success is False
        assert config.notify_on_failure is True
        assert config.notify_on_completion is True


@pytest.mark.unit
class TestOutputConfig:
    def test_defaults(self) -> None:
        config = OutputConfig()
        assert config.delivery_method == OutputDeliveryMethod.SESSION
        assert config.file_path is None


@pytest.mark.unit
class TestScheduledTask:
    def _make_task(self, **kwargs) -> ScheduledTask:
        defaults = {
            "user_id": "user1",
            "task_description": "Test task",
            "scheduled_at": datetime.now(UTC) + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return ScheduledTask(**defaults)

    def test_basic_construction(self) -> None:
        task = self._make_task()
        assert task.user_id == "user1"
        assert task.status == ScheduledTaskStatus.PENDING
        assert task.execution_count == 0
        assert task.id  # auto-generated

    def test_is_active(self) -> None:
        task = self._make_task(status=ScheduledTaskStatus.PENDING)
        assert task.is_active() is True
        task.status = ScheduledTaskStatus.RUNNING
        assert task.is_active() is True
        task.status = ScheduledTaskStatus.COMPLETED
        assert task.is_active() is False

    def test_can_execute_future_task(self) -> None:
        task = self._make_task(scheduled_at=datetime.now(UTC) + timedelta(hours=1))
        assert task.can_execute() is False

    def test_can_execute_past_task(self) -> None:
        task = self._make_task(scheduled_at=datetime.now(UTC) - timedelta(hours=1))
        assert task.can_execute() is True

    def test_validate_interval_valid(self) -> None:
        task = self._make_task(
            schedule_type=ScheduleType.RECURRING,
            interval_seconds=600,
        )
        assert task.validate_interval() is True

    def test_validate_interval_too_short(self) -> None:
        task = self._make_task(
            schedule_type=ScheduleType.RECURRING,
            interval_seconds=60,
        )
        assert task.validate_interval() is False

    def test_validate_interval_once_type(self) -> None:
        task = self._make_task(schedule_type=ScheduleType.ONCE)
        assert task.validate_interval() is True

    def test_mark_executed_once(self) -> None:
        task = self._make_task(schedule_type=ScheduleType.ONCE)
        task.last_executed_at = datetime.now(UTC)
        task.mark_executed(status=ExecutionStatus.SUCCESS)
        assert task.status == ScheduledTaskStatus.COMPLETED
        assert task.execution_count == 1
        assert len(task.execution_history) == 1

    def test_mark_executed_recurring(self) -> None:
        task = self._make_task(
            schedule_type=ScheduleType.RECURRING,
            interval_seconds=600,
        )
        task.mark_executed(status=ExecutionStatus.SUCCESS)
        assert task.status == ScheduledTaskStatus.PENDING
        assert task.next_execution_at is not None

    def test_mark_executed_max_reached(self) -> None:
        task = self._make_task(
            schedule_type=ScheduleType.RECURRING,
            interval_seconds=600,
            max_executions=1,
        )
        task.mark_executed(status=ExecutionStatus.SUCCESS)
        assert task.status == ScheduledTaskStatus.COMPLETED

    def test_should_retry_after_failure(self) -> None:
        task = self._make_task()
        task.last_execution_status = ExecutionStatus.FAILED
        assert task.should_retry() is True

    def test_should_not_retry_after_success(self) -> None:
        task = self._make_task()
        task.last_execution_status = ExecutionStatus.SUCCESS
        assert task.should_retry() is False

    def test_should_not_retry_max_retries(self) -> None:
        task = self._make_task(max_retries=2)
        task.last_execution_status = ExecutionStatus.FAILED
        task.retry_count = 2
        assert task.should_retry() is False

    def test_increment_retry(self) -> None:
        task = self._make_task()
        next_time = task.increment_retry()
        assert task.retry_count == 1
        assert next_time > datetime.now(UTC)

    def test_pause_resume(self) -> None:
        task = self._make_task()
        task.pause()
        assert task.status == ScheduledTaskStatus.PAUSED
        task.resume()
        assert task.status == ScheduledTaskStatus.PENDING

    def test_resume_only_from_paused(self) -> None:
        task = self._make_task(status=ScheduledTaskStatus.COMPLETED)
        task.resume()
        assert task.status == ScheduledTaskStatus.COMPLETED

    def test_cancel(self) -> None:
        task = self._make_task()
        task.cancel()
        assert task.status == ScheduledTaskStatus.CANCELLED

    def test_mark_failed(self) -> None:
        task = self._make_task()
        task.mark_failed("Something broke")
        assert task.status == ScheduledTaskStatus.FAILED
        assert task.error_message == "Something broke"

    def test_execution_stats_empty(self) -> None:
        task = self._make_task()
        stats = task.get_execution_stats()
        assert stats["total_executions"] == 0
        assert stats["success_rate"] == 0.0

    def test_execution_stats_with_history(self) -> None:
        task = self._make_task()
        now = datetime.now(UTC)
        task.execution_history = [
            ExecutionRecord(started_at=now, status=ExecutionStatus.SUCCESS, duration_seconds=10.0),
            ExecutionRecord(started_at=now, status=ExecutionStatus.SUCCESS, duration_seconds=20.0),
            ExecutionRecord(started_at=now, status=ExecutionStatus.FAILED),
        ]
        stats = task.get_execution_stats()
        assert stats["total_executions"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["avg_duration_seconds"] == 15.0

    def test_execution_history_capped_at_100(self) -> None:
        task = self._make_task(schedule_type=ScheduleType.RECURRING, interval_seconds=600)
        now = datetime.now(UTC)
        for _ in range(110):
            task.last_executed_at = now
            task.mark_executed(status=ExecutionStatus.SUCCESS)
        assert len(task.execution_history) <= 100
