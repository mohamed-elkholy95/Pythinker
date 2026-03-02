"""Scheduled job domain model.

Lightweight model for channel-gateway scheduled jobs. This complements the
richer ScheduledTask model by providing a minimal schema for jobs triggered
through external channels (Telegram, Discord, cron, API).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models.channel import ChannelType


class ScheduledJob(BaseModel):
    """A lightweight scheduled job created via a channel gateway.

    Attributes:
        id: Unique job identifier (auto-generated hex).
        user_id: Owner user ID.
        schedule_type: How the job recurs — cron expression, fixed interval, or one-shot.
        schedule_expr: The schedule value (cron string, interval like "30m", or ISO timestamp).
        task_description: What the agent should do when the job fires.
        channel: Optional channel to deliver results to.
        chat_id: Optional chat/conversation to deliver results to.
        timezone: IANA timezone for schedule interpretation.
        enabled: Whether the job is active.
        last_run: When the job last executed.
        next_run: When the job will next execute.
        run_count: Total number of executions so far.
        max_runs: Optional cap on total executions (None = unlimited).
        metadata: Arbitrary extra data.
        created_at: When the job was created.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str
    schedule_type: Literal["cron", "interval", "once"]
    schedule_expr: str
    task_description: str
    channel: ChannelType | None = None
    chat_id: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
