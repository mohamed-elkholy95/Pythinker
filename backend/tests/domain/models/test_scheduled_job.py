"""Tests for ScheduledJob domain model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.scheduled_job import ScheduledJob


class TestScheduledJob:
    def test_minimal_construction(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            task_description="Daily report",
        )
        assert job.user_id == "u1"
        assert job.schedule_type == "cron"
        assert job.enabled is True
        assert job.run_count == 0
        assert job.max_runs is None
        assert job.timezone == "UTC"

    def test_auto_generated_id(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="once",
            schedule_expr="2026-03-25T12:00:00",
            task_description="One-time task",
        )
        assert job.id
        assert len(job.id) == 12

    def test_unique_ids(self) -> None:
        jobs = [
            ScheduledJob(
                user_id="u1",
                schedule_type="interval",
                schedule_expr="30m",
                task_description="Periodic check",
            )
            for _ in range(5)
        ]
        ids = {j.id for j in jobs}
        assert len(ids) == 5

    def test_schedule_type_literal(self) -> None:
        for t in ("cron", "interval", "once"):
            job = ScheduledJob(
                user_id="u1",
                schedule_type=t,
                schedule_expr="test",
                task_description="test",
            )
            assert job.schedule_type == t

    def test_invalid_schedule_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledJob(
                user_id="u1",
                schedule_type="invalid",  # type: ignore[arg-type]
                schedule_expr="test",
                task_description="test",
            )

    def test_defaults(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="cron",
            schedule_expr="0 * * * *",
            task_description="hourly",
        )
        assert job.channel is None
        assert job.chat_id is None
        assert job.last_run is None
        assert job.next_run is None
        assert job.metadata == {}

    def test_with_channel(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="cron",
            schedule_expr="0 9 * * 1",
            task_description="Weekly summary",
            channel="telegram",
            chat_id="12345",
        )
        assert job.channel == "telegram"
        assert job.chat_id == "12345"

    def test_metadata_dict(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="once",
            schedule_expr="now",
            task_description="test",
            metadata={"priority": "high", "tags": ["urgent"]},
        )
        assert job.metadata["priority"] == "high"

    def test_created_at_auto_set(self) -> None:
        job = ScheduledJob(
            user_id="u1",
            schedule_type="cron",
            schedule_expr="*/5 * * * *",
            task_description="check",
        )
        assert job.created_at is not None
