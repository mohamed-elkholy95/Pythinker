"""Repository interface for usage and agent-usage persistence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.domain.models.agent_usage import AgentRun, AgentRunStatus, AgentStep
from app.domain.models.usage import DailyUsageAggregate, UsageRecord


class UsageRepository(Protocol):
    """Repository for usage tracking persistence and queries."""

    async def insert_agent_run(self, run: AgentRun) -> AgentRun | None:
        """Persist a new agent run."""

    async def finalize_agent_run(
        self,
        run_id: str,
        status: AgentRunStatus,
        completed_at: datetime,
    ) -> AgentRun | None:
        """Finalize an existing agent run."""

    async def insert_agent_step(self, step: AgentStep) -> bool:
        """Persist an agent step, returning whether the insert succeeded."""

    async def increment_agent_run_aggregate(self, step: AgentStep) -> None:
        """Roll a persisted step into its parent run aggregate."""

    async def save_usage_record(self, record: UsageRecord) -> None:
        """Persist an individual usage record."""

    async def upsert_tool_call_daily(
        self,
        user_id: str,
        session_id: str,
        today: date,
        now: datetime,
    ) -> None:
        """Increment the daily aggregate for a tool call."""

    async def upsert_daily_aggregate(
        self,
        record: UsageRecord,
        today: date,
        now: datetime,
    ) -> None:
        """Roll an LLM usage record into the daily aggregate."""

    async def list_session_usage_records(self, session_id: str) -> list[UsageRecord]:
        """Return all usage records for a session."""

    async def list_agent_runs(self, user_id: str, start_time: datetime) -> list[AgentRun]:
        """Return agent runs for a user since the start time."""

    async def list_agent_steps(self, user_id: str, start_time: datetime) -> list[AgentStep]:
        """Return agent steps for a user since the start time."""

    async def list_daily_usage_since(self, user_id: str, start_date: date) -> list[DailyUsageAggregate]:
        """Return daily usage aggregates since a given day."""

    async def list_daily_usage_for_day(self, user_id: str, day: date) -> list[DailyUsageAggregate]:
        """Return daily usage aggregates for a specific day."""


_usage_repository: UsageRepository | None = None


def set_usage_repository(repository: UsageRepository | None) -> None:
    """Set the global usage repository implementation."""
    global _usage_repository
    _usage_repository = repository


def get_usage_repository() -> UsageRepository | None:
    """Return the configured usage repository implementation, if any."""
    return _usage_repository
