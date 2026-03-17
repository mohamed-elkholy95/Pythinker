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

from app.domain.models.usage import (
    DailyUsageAggregate,
    MonthlyUsageSummary,
    SessionUsage,
    UsageRecord,
    UsageType,
)
from app.domain.services.usage.pricing import (
    calculate_cost,
    get_provider_from_model,
)
from app.infrastructure.models.documents import DailyUsageDocument, UsageDocument

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


class UsageService:
    """Service for tracking and aggregating LLM usage."""

    async def record_llm_usage(
        self,
        user_id: str,
        session_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        usage_type: UsageType = UsageType.LLM_CALL,
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
        doc = UsageDocument.from_domain(record)
        await doc.save()

        # Update daily aggregate
        await self._update_daily_aggregate(record)

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
    ) -> None:
        """Record a tool call (for activity tracking).

        This increments tool call counters without token/cost tracking.
        """
        today = datetime.now(UTC).date()
        usage_id = f"{user_id}_{today.isoformat()}"

        # Use atomic upsert to avoid duplicate docs under concurrency.
        collection = DailyUsageDocument.get_pymongo_collection()
        if collection is None:
            logger.warning("DailyUsageDocument motor collection is None, skipping tool call aggregate update")
            return

        now = datetime.now(UTC)
        # MongoDB cannot encode datetime.date — store as datetime at midnight UTC
        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        await collection.find_one_and_update(
            {"usage_id": usage_id},
            {
                "$inc": {"tool_call_count": 1},
                "$addToSet": {"active_sessions": session_id},
                "$set": {
                    "user_id": user_id,
                    "date": today_dt,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "usage_id": usage_id,
                    "created_at": now,
                    "session_count": 0,
                    "llm_call_count": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cached_tokens": 0,
                    "total_prompt_cost": 0.0,
                    "total_completion_cost": 0.0,
                    "total_cost": 0.0,
                },
            },
            upsert=True,
        )

    async def _update_daily_aggregate(self, record: UsageRecord) -> None:
        """Update daily aggregate with new usage record.

        Uses atomic find_one_and_update with upsert to eliminate the race
        condition where concurrent requests could create duplicate documents.
        """
        today = datetime.now(UTC).date()
        usage_id = f"{record.user_id}_{today.isoformat()}"

        # Sanitize model name for MongoDB key (/ and . are path separators)
        safe_model_key = _sanitize_model_key(record.model)

        # Use Beanie's get_pymongo_collection() with a guard against None
        # (Beanie can return None under concurrent access race conditions)
        collection = DailyUsageDocument.get_pymongo_collection()
        if collection is None:
            logger.warning("DailyUsageDocument motor collection is None, skipping daily aggregate update")
            return

        now = datetime.now(UTC)
        # MongoDB cannot encode datetime.date — store as datetime at midnight UTC
        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        await collection.find_one_and_update(
            {"usage_id": usage_id},
            {
                "$inc": {
                    "total_prompt_tokens": record.prompt_tokens,
                    "total_completion_tokens": record.completion_tokens,
                    "total_cached_tokens": record.cached_tokens,
                    "total_prompt_cost": record.prompt_cost,
                    "total_completion_cost": record.completion_cost,
                    "total_cost": record.total_cost,
                    "llm_call_count": 1 if record.usage_type == UsageType.LLM_CALL else 0,
                    f"tokens_by_model.{safe_model_key}": record.prompt_tokens + record.completion_tokens,
                    f"cost_by_model.{safe_model_key}": record.total_cost,
                },
                "$addToSet": {"active_sessions": record.session_id},
                "$set": {
                    "user_id": record.user_id,
                    "date": today_dt,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "usage_id": usage_id,
                    "created_at": now,
                    "tool_call_count": 0,
                    "session_count": 0,
                },
            },
            upsert=True,
        )

    async def get_session_usage(self, session_id: str) -> SessionUsage:
        """Get aggregated usage for a session.

        Args:
            session_id: The session ID

        Returns:
            SessionUsage with totals for the session
        """
        # Query all usage records for this session
        docs = await UsageDocument.find(UsageDocument.session_id == session_id).to_list()

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

        docs = await DailyUsageDocument.find(
            {
                "user_id": user_id,
                "$or": _date_gte_or_legacy_string(start_date),
            }
        ).to_list()
        docs.sort(key=lambda doc: _coerce_doc_day(getattr(doc, "date", "")))

        return [doc.to_domain() for doc in docs]

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
        docs = await DailyUsageDocument.find(
            {
                "user_id": user_id,
                "$or": _date_gte_or_legacy_string(start_date),
            }
        ).to_list()

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
        today_docs = await DailyUsageDocument.find(
            {
                "user_id": user_id,
                "$or": _date_eq_or_legacy_string(today),
            }
        ).to_list()

        # Get this month's usage
        month_docs = await DailyUsageDocument.find(
            {
                "user_id": user_id,
                "$or": _date_gte_or_legacy_string(month_start),
            }
        ).to_list()

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
