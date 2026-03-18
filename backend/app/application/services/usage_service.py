"""Usage tracking service for recording and aggregating LLM usage.

This service handles:
- Recording individual LLM call usage
- Aggregating usage by session
- Rolling up daily/monthly usage summaries
- Providing usage statistics for the API layer
"""

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.domain.models.agent_usage import (
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    AgentUsageBreakdownRow,
    AgentUsageSummary,
    AgentUsageTimeseriesPoint,
)
from app.domain.models.usage import (
    DailyUsageAggregate,
    MonthlyUsageSummary,
    SessionUsage,
    UsageRecord,
    UsageType,
)
from app.domain.repositories.usage_repository import UsageRepository, get_usage_repository
from app.domain.services.agents.usage_context import get_usage_context
from app.domain.services.usage.normalization import NormalizedUsage, normalize_provider_usage
from app.domain.services.usage.pricing import (
    calculate_cost,
    get_model_pricing,
    get_provider_from_model,
)

logger = logging.getLogger(__name__)


def _sanitize_model_key(model_name: str) -> str:
    """Sanitize model name for use as MongoDB dictionary key.

    MongoDB interprets '.' and '/' as path separators in field names,
    so we replace them with safe characters.
    """
    return model_name.replace("/", "_").replace(".", "_")


def _date_eq_or_legacy_string(day: date) -> list[dict[str, object]]:
    """Match daily keys across date/string/datetime legacy storage."""
    day_start_utc = datetime(day.year, day.month, day.day, tzinfo=UTC)
    next_day_utc = day_start_utc + timedelta(days=1)
    day_start_naive = datetime(day.year, day.month, day.day)  # noqa: DTZ001 - intentionally naive for legacy MongoDB records
    next_day_naive = day_start_naive + timedelta(days=1)
    return [
        {"date": day},
        {"date": day.isoformat()},
        {"date": {"$gte": day_start_utc, "$lt": next_day_utc}},
        {"date": {"$gte": day_start_naive, "$lt": next_day_naive}},
    ]


def _date_gte_or_legacy_string(day: date) -> list[dict[str, dict[str, date | str | datetime]]]:
    """Range-match date/string/datetime legacy storage."""
    day_start_utc = datetime(day.year, day.month, day.day, tzinfo=UTC)
    day_start_naive = datetime(day.year, day.month, day.day)  # noqa: DTZ001 - intentionally naive for legacy MongoDB records
    return [
        {"date": {"$gte": day}},
        {"date": {"$gte": day.isoformat()}},
        {"date": {"$gte": day_start_utc}},
        {"date": {"$gte": day_start_naive}},
    ]


def _coerce_doc_day(value: object) -> str:
    """Normalize mixed day value types for deterministic sorting."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _timeseries_bucket_start(started_at: datetime, bucket: str) -> datetime:
    """Normalize a run start time to its chart bucket boundary in UTC."""
    started_at_utc = started_at.astimezone(UTC)

    if bucket == "hour":
        return started_at_utc.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return datetime(started_at_utc.year, started_at_utc.month, started_at_utc.day, tzinfo=UTC)
    if bucket == "week":
        day_start = datetime(started_at_utc.year, started_at_utc.month, started_at_utc.day, tzinfo=UTC)
        return day_start - timedelta(days=day_start.weekday())

    raise ValueError(f"Unsupported usage timeseries bucket: {bucket}")


class UsageService:
    """Service for tracking and aggregating LLM usage."""

    def __init__(self, repository: UsageRepository | None = None) -> None:
        if repository is not None:
            self._repository = repository
            return

        configured_repository = get_usage_repository()
        if configured_repository is None:
            # Lazy import keeps the application service bound to the domain
            # protocol while still allowing a default runtime implementation.
            from app.infrastructure.repositories.mongo_usage_repository import MongoUsageRepository

            configured_repository = MongoUsageRepository()
        self._repository = configured_repository

    async def start_agent_run(
        self,
        user_id: str,
        session_id: str,
        agent_id: str | None = None,
        entrypoint: str | None = None,
        started_at: datetime | None = None,
    ) -> AgentRun | None:
        """Create and persist a new agent run record."""
        run = AgentRun(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            entrypoint=entrypoint,
            status=AgentRunStatus.RUNNING,
            started_at=started_at or datetime.now(UTC),
        )
        return await self._repository.insert_agent_run(run)

    async def finalize_agent_run(
        self,
        run_id: str,
        status: AgentRunStatus,
        completed_at: datetime | None = None,
    ) -> AgentRun | None:
        """Finalize an agent run with terminal status and duration."""
        completed_at_value = completed_at or datetime.now(UTC)
        return await self._repository.finalize_agent_run(run_id, status, completed_at_value)

    async def record_agent_step(self, step: AgentStep) -> AgentStep:
        """Persist an agent step and roll its counters into the parent run."""
        inserted = await self._repository.insert_agent_step(step)
        if not inserted:
            return step
        await self._repository.increment_agent_run_aggregate(step)
        return step

    async def record_llm_usage(
        self,
        user_id: str,
        session_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        usage_type: UsageType = UsageType.LLM_CALL,
        provider_usage_raw: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record usage for an LLM call.

        Args:
            user_id: User ID to attribute usage to
            session_id: Session ID to attribute usage to
            model: Model name/ID used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            cached_tokens: Number of cached prompt tokens (Anthropic)
            usage_type: Type of usage (LLM_CALL, TOOL_CALL, EMBEDDING)

        Returns:
            The created UsageRecord
        """
        # Calculate costs
        prompt_cost, completion_cost, total_cost = calculate_cost(
            model, prompt_tokens, completion_tokens, cached_tokens
        )

        # Get provider
        provider = get_provider_from_model(model)

        # Create usage record
        record = UsageRecord(
            user_id=user_id,
            session_id=session_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            prompt_cost=prompt_cost,
            completion_cost=completion_cost,
            total_cost=total_cost,
            usage_type=usage_type,
        )

        # Save to MongoDB
        await self._repository.save_usage_record(record)

        # Update daily aggregate
        await self._update_daily_aggregate(record)

        usage_context = get_usage_context()
        if usage_context and usage_context.run_id:
            normalized_usage = self._normalize_llm_usage(
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                provider_usage_raw=provider_usage_raw,
            )
            await self.record_agent_step(
                AgentStep(
                    run_id=usage_context.run_id,
                    session_id=session_id,
                    user_id=user_id,
                    step_type=AgentStepType.LLM,
                    provider=provider,
                    model=model,
                    status=AgentStepStatus.COMPLETED,
                    started_at=record.created_at,
                    completed_at=record.created_at,
                    input_tokens=normalized_usage.input_tokens,
                    cached_input_tokens=normalized_usage.cached_input_tokens,
                    output_tokens=normalized_usage.output_tokens,
                    reasoning_tokens=normalized_usage.reasoning_tokens,
                    total_tokens=normalized_usage.total_tokens,
                    estimated_cost_usd=total_cost,
                    provider_usage_raw=normalized_usage.raw_usage,
                )
            )

        logger.debug(
            f"Recorded usage: user={user_id}, session={session_id}, "
            f"model={model}, tokens={prompt_tokens}+{completion_tokens}, "
            f"cost=${total_cost:.6f}"
        )

        return record

    async def record_tool_call(
        self,
        user_id: str,
        session_id: str,
        tool_name: str | None = None,
        mcp_server: str | None = None,
        status: str = "completed",
        duration_ms: float | None = None,
        error_type: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Record a tool call (for activity tracking).

        This increments tool call counters without token/cost tracking.
        """
        today = datetime.now(UTC).date()

        # Use atomic upsert to avoid duplicate docs under concurrency.
        now = datetime.now(UTC)
        await self._repository.upsert_tool_call_daily(user_id, session_id, today, now)

        usage_context = get_usage_context()
        if usage_context and usage_context.run_id and tool_name:
            completed_at_value = completed_at or datetime.now(UTC)
            started_at_value = started_at or completed_at_value
            if duration_ms is not None and started_at is None:
                started_at_value = completed_at_value - timedelta(milliseconds=duration_ms)
            await self.record_agent_step(
                AgentStep(
                    run_id=usage_context.run_id,
                    session_id=session_id,
                    user_id=user_id,
                    step_type=AgentStepType.MCP if mcp_server else AgentStepType.TOOL,
                    tool_name=tool_name,
                    mcp_server=mcp_server,
                    status=status,
                    started_at=started_at_value,
                    completed_at=completed_at_value,
                    duration_ms=duration_ms,
                    error_type=error_type,
                )
            )

    async def _update_daily_aggregate(self, record: UsageRecord) -> None:
        """Update daily aggregate with new usage record.

        Uses atomic find_one_and_update with upsert to eliminate the race
        condition where concurrent requests could create duplicate documents.
        """
        today = datetime.now(UTC).date()
        now = datetime.now(UTC)
        await self._repository.upsert_daily_aggregate(record, today, now)

    async def _update_agent_run_aggregate(self, step: AgentStep) -> None:
        """Roll step counters into its parent run using an atomic update."""
        await self._repository.increment_agent_run_aggregate(step)

    def _normalize_llm_usage(
        self,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        provider_usage_raw: dict[str, Any] | None,
    ) -> NormalizedUsage:
        """Normalize provider-native or synthetic usage into the agent step shape."""
        if provider_usage_raw:
            normalized = normalize_provider_usage(provider, provider_usage_raw)
            if normalized.raw_usage:
                return normalized

        synthetic_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": cached_tokens},
        }
        return NormalizedUsage(
            input_tokens=prompt_tokens,
            cached_input_tokens=cached_tokens,
            output_tokens=completion_tokens,
            reasoning_tokens=0,
            total_tokens=prompt_tokens + completion_tokens,
            raw_usage=provider_usage_raw or synthetic_usage,
        )

    async def get_session_usage(self, session_id: str) -> SessionUsage:
        """Get aggregated usage for a session.

        Args:
            session_id: The session ID

        Returns:
            SessionUsage with totals for the session
        """
        # Query all usage records for this session
        docs = await self._repository.list_session_usage_records(session_id)

        if not docs:
            # Return empty usage for new sessions
            return SessionUsage(session_id=session_id, user_id="")

        # Aggregate
        user_id = docs[0].user_id
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        total_prompt_cost = 0.0
        total_completion_cost = 0.0
        total_cost = 0.0
        llm_call_count = 0
        tool_call_count = 0
        tokens_by_model: dict[str, int] = defaultdict(int)
        cost_by_model: dict[str, float] = defaultdict(float)
        first_activity: datetime | None = None
        last_activity: datetime | None = None

        for doc in docs:
            total_prompt_tokens += doc.prompt_tokens
            total_completion_tokens += doc.completion_tokens
            total_cached_tokens += doc.cached_tokens
            total_prompt_cost += doc.prompt_cost
            total_completion_cost += doc.completion_cost
            total_cost += doc.total_cost

            if doc.usage_type == UsageType.LLM_CALL.value:
                llm_call_count += 1
            elif doc.usage_type == UsageType.TOOL_CALL.value:
                tool_call_count += 1

            tokens_by_model[doc.model] += doc.prompt_tokens + doc.completion_tokens
            cost_by_model[doc.model] += doc.total_cost

            if first_activity is None or doc.created_at < first_activity:
                first_activity = doc.created_at
            if last_activity is None or doc.created_at > last_activity:
                last_activity = doc.created_at

        return SessionUsage(
            session_id=session_id,
            user_id=user_id,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_cached_tokens=total_cached_tokens,
            total_prompt_cost=total_prompt_cost,
            total_completion_cost=total_completion_cost,
            total_cost=total_cost,
            llm_call_count=llm_call_count,
            tool_call_count=tool_call_count,
            tokens_by_model=dict(tokens_by_model),
            cost_by_model=dict(cost_by_model),
            first_activity=first_activity,
            last_activity=last_activity,
        )

    async def get_agent_usage_summary(self, user_id: str, days: int = 30) -> AgentUsageSummary:
        """Aggregate run-level usage metrics for the agent usage tab."""
        start_time = _days_ago(days)
        run_docs = await self._repository.list_agent_runs(user_id, start_time)
        step_docs = await self._repository.list_agent_steps(user_id, start_time)

        completed_run_count = sum(1 for doc in run_docs if getattr(doc, "status", "") == AgentRunStatus.COMPLETED.value)
        failed_run_count = sum(1 for doc in run_docs if getattr(doc, "status", "") == AgentRunStatus.FAILED.value)
        terminal_run_count = sum(1 for doc in run_docs if getattr(doc, "status", "") != AgentRunStatus.RUNNING.value)
        duration_values = [doc.duration_ms for doc in run_docs if getattr(doc, "duration_ms", None) is not None]

        return AgentUsageSummary(
            run_count=len(run_docs),
            completed_run_count=completed_run_count,
            failed_run_count=failed_run_count,
            success_rate=(completed_run_count / terminal_run_count) if terminal_run_count else 0.0,
            avg_run_duration_ms=(sum(duration_values) / len(duration_values)) if duration_values else 0.0,
            total_cost=sum(getattr(doc, "estimated_cost_usd", 0.0) for doc in run_docs),
            total_input_tokens=sum(getattr(doc, "total_input_tokens", 0) for doc in run_docs),
            total_cached_input_tokens=sum(getattr(doc, "total_cached_input_tokens", 0) for doc in run_docs),
            total_output_tokens=sum(getattr(doc, "total_output_tokens", 0) for doc in run_docs),
            total_reasoning_tokens=sum(getattr(doc, "total_reasoning_tokens", 0) for doc in run_docs),
            total_tool_calls=sum(getattr(doc, "tool_call_count", 0) for doc in run_docs),
            total_mcp_calls=sum(getattr(doc, "mcp_call_count", 0) for doc in run_docs),
            cache_savings_estimate=sum(_estimate_cache_savings(step_doc) for step_doc in step_docs),
        )

    async def get_recent_agent_runs(self, user_id: str, days: int = 30, limit: int = 20) -> list[AgentRun]:
        """Return recent agent runs for table rendering."""
        start_time = _days_ago(days)
        run_docs = await self._repository.list_agent_runs(user_id, start_time)
        sorted_docs = sorted(
            run_docs, key=lambda doc: getattr(doc, "started_at", datetime.min.replace(tzinfo=UTC)), reverse=True
        )
        return sorted_docs[:limit]

    async def get_agent_usage_breakdown(
        self,
        user_id: str,
        days: int = 30,
        group_by: str = "model",
    ) -> list[AgentUsageBreakdownRow]:
        """Group agent steps by model/provider/tool/MCP server."""
        start_time = _days_ago(days)
        step_docs = await self._repository.list_agent_steps(user_id, start_time)

        grouped: dict[str, dict[str, Any]] = {}
        for doc in step_docs:
            key = _group_step_key(doc, group_by)
            if key not in grouped:
                grouped[key] = {
                    "run_ids": set(),
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost": 0.0,
                    "duration_total": 0.0,
                    "duration_count": 0,
                    "error_count": 0,
                    "step_count": 0,
                }

            group = grouped[key]
            group["run_ids"].add(getattr(doc, "run_id", ""))
            group["input_tokens"] += getattr(doc, "input_tokens", 0)
            group["cached_input_tokens"] += getattr(doc, "cached_input_tokens", 0)
            group["output_tokens"] += getattr(doc, "output_tokens", 0)
            group["reasoning_tokens"] += getattr(doc, "reasoning_tokens", 0)
            group["cost"] += getattr(doc, "estimated_cost_usd", 0.0)
            if getattr(doc, "duration_ms", None) is not None:
                group["duration_total"] += doc.duration_ms
                group["duration_count"] += 1
            if getattr(doc, "status", "") != AgentStepStatus.COMPLETED.value:
                group["error_count"] += 1
            group["step_count"] += 1

        rows = [
            AgentUsageBreakdownRow(
                key=key,
                run_count=len(data["run_ids"]),
                input_tokens=data["input_tokens"],
                cached_input_tokens=data["cached_input_tokens"],
                output_tokens=data["output_tokens"],
                reasoning_tokens=data["reasoning_tokens"],
                cost=data["cost"],
                avg_duration_ms=(data["duration_total"] / data["duration_count"] if data["duration_count"] else 0.0),
                error_rate=(data["error_count"] / data["step_count"]) if data["step_count"] else 0.0,
            )
            for key, data in grouped.items()
        ]
        return sorted(rows, key=lambda row: row.cost, reverse=True)

    async def get_agent_usage_timeseries(
        self,
        user_id: str,
        days: int = 30,
        bucket: str = "day",
    ) -> list[AgentUsageTimeseriesPoint]:
        """Build run-aware usage trend points for the requested bucket."""
        start_time = _days_ago(days)
        run_docs = await self._repository.list_agent_runs(user_id, start_time)

        grouped: dict[datetime, dict[str, Any]] = {}
        for doc in run_docs:
            started_at = getattr(doc, "started_at", None)
            if started_at is None:
                continue
            bucket_key = _timeseries_bucket_start(started_at, bucket)
            if bucket_key not in grouped:
                grouped[bucket_key] = {
                    "run_count": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "cost": 0.0,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "tool_calls": 0,
                    "mcp_calls": 0,
                }

            group = grouped[bucket_key]
            group["run_count"] += 1
            if getattr(doc, "status", "") == AgentRunStatus.COMPLETED.value:
                group["success_count"] += 1
            if getattr(doc, "status", "") == AgentRunStatus.FAILED.value:
                group["failed_count"] += 1
            group["cost"] += getattr(doc, "estimated_cost_usd", 0.0)
            group["input_tokens"] += getattr(doc, "total_input_tokens", 0)
            group["cached_input_tokens"] += getattr(doc, "total_cached_input_tokens", 0)
            group["output_tokens"] += getattr(doc, "total_output_tokens", 0)
            group["reasoning_tokens"] += getattr(doc, "total_reasoning_tokens", 0)
            group["tool_calls"] += getattr(doc, "tool_call_count", 0)
            group["mcp_calls"] += getattr(doc, "mcp_call_count", 0)

        return [
            AgentUsageTimeseriesPoint(
                date=bucket_start,
                run_count=data["run_count"],
                success_count=data["success_count"],
                failed_count=data["failed_count"],
                cost=data["cost"],
                input_tokens=data["input_tokens"],
                cached_input_tokens=data["cached_input_tokens"],
                output_tokens=data["output_tokens"],
                reasoning_tokens=data["reasoning_tokens"],
                tool_calls=data["tool_calls"],
                mcp_calls=data["mcp_calls"],
            )
            for bucket_start, data in sorted(grouped.items())
        ]

    async def get_daily_usage(
        self,
        user_id: str,
        days: int = 30,
    ) -> list[DailyUsageAggregate]:
        """Get daily usage breakdown for a user.

        Args:
            user_id: The user ID
            days: Number of days to include (default 30)

        Returns:
            List of DailyUsageAggregate, one per day with usage
        """
        start_date = datetime.now(UTC).date() - timedelta(days=days - 1)

        return await self._repository.list_daily_usage_since(user_id, start_date)

    async def get_monthly_summary(
        self,
        user_id: str,
        months: int = 12,
    ) -> list[MonthlyUsageSummary]:
        """Get monthly usage summaries for a user.

        Args:
            user_id: The user ID
            months: Number of months to include (default 12)

        Returns:
            List of MonthlyUsageSummary, one per month with usage
        """
        # Calculate date range
        today = datetime.now(UTC).date()
        start_date = date(today.year, today.month, 1) - timedelta(days=30 * (months - 1))

        # Get daily aggregates and roll up by month
        docs = await self._repository.list_daily_usage_since(user_id, start_date)

        # Group by year-month
        monthly_data: dict[tuple, dict] = {}
        for doc in docs:
            key = (doc.date.year, doc.date.month)
            if key not in monthly_data:
                monthly_data[key] = {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cached_tokens": 0,
                    "total_cost": 0.0,
                    "total_llm_calls": 0,
                    "total_tool_calls": 0,
                    "sessions": set(),
                    "active_days": 0,
                    "cost_by_model": defaultdict(float),
                }

            data = monthly_data[key]
            data["total_prompt_tokens"] += doc.total_prompt_tokens
            data["total_completion_tokens"] += doc.total_completion_tokens
            data["total_cached_tokens"] += doc.total_cached_tokens
            data["total_cost"] += doc.total_cost
            data["total_llm_calls"] += doc.llm_call_count
            data["total_tool_calls"] += doc.tool_call_count
            data["sessions"].update(doc.active_sessions)
            data["active_days"] += 1
            for model, cost in doc.cost_by_model.items():
                data["cost_by_model"][model] += cost

        # Convert to summaries
        summaries = []
        for (year, month), data in sorted(monthly_data.items()):
            summaries.append(
                MonthlyUsageSummary(
                    user_id=user_id,
                    year=year,
                    month=month,
                    total_prompt_tokens=data["total_prompt_tokens"],
                    total_completion_tokens=data["total_completion_tokens"],
                    total_cached_tokens=data["total_cached_tokens"],
                    total_cost=data["total_cost"],
                    total_llm_calls=data["total_llm_calls"],
                    total_tool_calls=data["total_tool_calls"],
                    total_sessions=len(data["sessions"]),
                    active_days=data["active_days"],
                    cost_by_model=dict(data["cost_by_model"]),
                )
            )

        return summaries

    async def get_usage_summary(self, user_id: str) -> dict:
        """Get a summary of usage for today and this month.

        Args:
            user_id: The user ID

        Returns:
            Dict with today and month summaries
        """
        today = datetime.now(UTC).date()
        month_start = date(today.year, today.month, 1)

        # Get today's usage
        today_docs = await self._repository.list_daily_usage_for_day(user_id, today)

        # Get this month's usage
        month_docs = await self._repository.list_daily_usage_since(user_id, month_start)

        # Calculate monthly totals
        month_tokens = 0
        month_cost = 0.0
        month_llm_calls = 0
        month_tool_calls = 0
        month_sessions = set()

        today_tokens = 0
        today_cost = 0.0
        today_llm_calls = 0
        today_tool_calls = 0

        for doc in today_docs:
            today_tokens += doc.total_prompt_tokens + doc.total_completion_tokens
            today_cost += doc.total_cost
            today_llm_calls += doc.llm_call_count
            today_tool_calls += doc.tool_call_count

        for doc in month_docs:
            month_tokens += doc.total_prompt_tokens + doc.total_completion_tokens
            month_cost += doc.total_cost
            month_llm_calls += doc.llm_call_count
            month_tool_calls += doc.tool_call_count
            month_sessions.update(doc.active_sessions)

        return {
            "today": {
                "tokens": today_tokens,
                "cost": today_cost,
                "llm_calls": today_llm_calls,
                "tool_calls": today_tool_calls,
            },
            "month": {
                "tokens": month_tokens,
                "cost": month_cost,
                "llm_calls": month_llm_calls,
                "tool_calls": month_tool_calls,
                "sessions": len(month_sessions),
                "active_days": len(month_docs),
            },
        }


# Global singleton instance
_usage_service: UsageService | None = None


def get_usage_service() -> UsageService:
    """Get the global UsageService instance."""
    global _usage_service
    if _usage_service is None:
        _usage_service = UsageService()
    return _usage_service


def _days_ago(days: int) -> datetime:
    """Return the inclusive UTC start timestamp for a rolling day window."""
    bounded_days = max(days, 1)
    return datetime.now(UTC) - timedelta(days=bounded_days - 1)


def _estimate_cache_savings(step_doc: Any) -> float:
    """Estimate cache savings from cached prompt tokens using legacy pricing."""
    model_name = getattr(step_doc, "model", None)
    cached_tokens = getattr(step_doc, "cached_input_tokens", 0)
    if not model_name or cached_tokens <= 0:
        return 0.0

    pricing = get_model_pricing(model_name)
    if pricing.cached_price is None or pricing.prompt_price <= pricing.cached_price:
        return 0.0

    return (cached_tokens / 1_000_000) * (pricing.prompt_price - pricing.cached_price)


def _group_step_key(step_doc: Any, group_by: str) -> str:
    """Resolve the grouping key for a step breakdown query."""
    field_name_by_group = {
        "model": "model",
        "provider": "provider",
        "tool": "tool_name",
        "mcp_server": "mcp_server",
    }
    field_name = field_name_by_group.get(group_by, "model")
    value = getattr(step_doc, field_name, None)
    return str(value or "unknown")


def _coerce_agent_run(run_doc: Any) -> AgentRun:
    """Convert a Beanie document or test double into an AgentRun."""
    if isinstance(run_doc, AgentRun):
        return run_doc

    if isinstance(run_doc, dict):
        return AgentRun.model_validate(run_doc)

    to_domain = getattr(run_doc, "to_domain", None)
    if callable(to_domain):
        return to_domain()

    model_dump = getattr(run_doc, "model_dump", None)
    if callable(model_dump):
        return AgentRun.model_validate(model_dump(exclude={"id"}))

    return AgentRun.model_validate(
        {key: value for key, value in vars(run_doc).items() if not key.startswith("_") and not callable(value)}
    )
