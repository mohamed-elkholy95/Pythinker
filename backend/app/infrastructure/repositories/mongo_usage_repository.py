"""MongoDB-backed usage repository."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

from pymongo import ReturnDocument

from app.domain.models.agent_usage import (
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    BillingStatus,
)
from app.domain.models.usage import DailyUsageAggregate, UsageRecord, UsageType
from app.domain.repositories.usage_repository import UsageRepository
from app.infrastructure.models.documents import (
    AgentRunDocument,
    AgentStepDocument,
    DailyUsageDocument,
    UsageDocument,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _sanitize_model_key(model_name: str) -> str:
    return model_name.replace("/", "_").replace(".", "_")


def _date_eq_or_legacy_string(day: date) -> list[dict[str, object]]:
    day_start_utc = datetime(day.year, day.month, day.day, tzinfo=UTC)
    next_day_utc = day_start_utc + timedelta(days=1)
    day_start_naive = datetime(day.year, day.month, day.day)  # noqa: DTZ001
    next_day_naive = day_start_naive + timedelta(days=1)
    return [
        {"date": day},
        {"date": day.isoformat()},
        {"date": {"$gte": day_start_utc, "$lt": next_day_utc}},
        {"date": {"$gte": day_start_naive, "$lt": next_day_naive}},
    ]


def _date_gte_or_legacy_string(day: date) -> list[dict[str, dict[str, date | str | datetime]]]:
    day_start_utc = datetime(day.year, day.month, day.day, tzinfo=UTC)
    day_start_naive = datetime(day.year, day.month, day.day)  # noqa: DTZ001
    return [
        {"date": {"$gte": day}},
        {"date": {"$gte": day.isoformat()}},
        {"date": {"$gte": day_start_utc}},
        {"date": {"$gte": day_start_naive}},
    ]


def _coerce_doc_day(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _coerce_domain(model_cls: type[T], value: Any) -> T | None:
    if isinstance(value, model_cls):
        return value

    try:
        if isinstance(value, dict):
            return model_cls.model_validate(value)

        to_domain = getattr(value, "to_domain", None)
        if callable(to_domain):
            return to_domain()

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_cls.model_validate(model_dump(exclude={"id"}))

        attributes = getattr(value, "__dict__", None)
        if isinstance(attributes, dict):
            return model_cls.model_validate(
                {
                    key: field_value
                    for key, field_value in attributes.items()
                    if not key.startswith("_") and not callable(field_value)
                }
            )
    except Exception as exc:
        logger.warning("Failed to coerce %s to %s: %s", type(value).__name__, model_cls.__name__, exc)
        return None

    logger.warning("Unsupported %s value for %s coercion", type(value).__name__, model_cls.__name__)
    return None


class MongoUsageRepository(UsageRepository):
    """MongoDB implementation of usage persistence."""

    async def insert_agent_run(self, run: AgentRun) -> AgentRun | None:
        try:
            doc = AgentRunDocument.from_domain(run)
            await doc.insert()
            return run
        except Exception as exc:
            logger.exception("Failed to insert agent run %s: %s", run.run_id, exc)
            return None

    async def finalize_agent_run(
        self,
        run_id: str,
        status: AgentRunStatus,
        completed_at: datetime,
    ) -> AgentRun | None:
        try:
            collection = AgentRunDocument.get_motor_collection()
            finalized_run = await collection.find_one_and_update(
                {"run_id": run_id},
                [
                    {
                        "$set": {
                            "status": status.value,
                            "completed_at": completed_at,
                            "duration_ms": {
                                "$max": [
                                    {
                                        "$toDouble": {
                                            "$subtract": [
                                                completed_at,
                                                {"$ifNull": ["$started_at", completed_at]},
                                            ]
                                        }
                                    },
                                    0.0,
                                ]
                            },
                            "billing_status": BillingStatus.ESTIMATED.value,
                        }
                    }
                ],
                return_document=ReturnDocument.AFTER,
            )
        except Exception as exc:
            logger.exception("Failed to finalize agent run %s: %s", run_id, exc)
            return None

        return _coerce_domain(AgentRun, finalized_run) if finalized_run is not None else None

    async def insert_agent_step(self, step: AgentStep) -> bool:
        try:
            doc = AgentStepDocument.from_domain(step)
            await doc.insert()
            return True
        except Exception as exc:
            logger.exception("Failed to insert agent step %s for run %s: %s", step.step_id, step.run_id, exc)
            return False

    async def increment_agent_run_aggregate(self, step: AgentStep) -> None:
        try:
            collection = AgentRunDocument.get_motor_collection()
        except Exception as exc:
            logger.warning("AgentRunDocument collection not initialized, skipping aggregate: %s", exc)
            return

        update_doc: dict[str, Any] = {
            "$inc": {
                "step_count": 1,
                "tool_call_count": 1 if step.step_type == AgentStepType.TOOL else 0,
                "mcp_call_count": 1 if step.step_type == AgentStepType.MCP else 0,
                "error_count": 1 if step.status != AgentStepStatus.COMPLETED else 0,
                "total_input_tokens": step.input_tokens,
                "total_cached_input_tokens": step.cached_input_tokens,
                "total_output_tokens": step.output_tokens,
                "total_reasoning_tokens": step.reasoning_tokens,
                "total_tokens": step.total_tokens,
                "estimated_cost_usd": step.estimated_cost_usd,
            }
        }
        if step.model:
            update_doc["$set"] = {
                "primary_model": step.model,
                "primary_provider": step.provider,
            }

        try:
            await collection.find_one_and_update({"run_id": step.run_id}, update_doc)
        except Exception as exc:
            logger.exception("Failed to update aggregate for run %s from step %s: %s", step.run_id, step.step_id, exc)

    async def save_usage_record(self, record: UsageRecord) -> None:
        doc = UsageDocument.from_domain(record)
        try:
            await doc.save()
        except Exception as exc:
            logger.exception("Failed to save usage record %s for session %s: %s", record.id, record.session_id, exc)

    async def upsert_tool_call_daily(
        self,
        user_id: str,
        session_id: str,
        today: date,
        now: datetime,
    ) -> None:
        usage_id = f"{user_id}_{today.isoformat()}"
        try:
            collection = DailyUsageDocument.get_motor_collection()
        except Exception as exc:
            logger.warning("DailyUsageDocument collection not initialized, skipping tool call aggregate: %s", exc)
            return

        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        try:
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
        except Exception as exc:
            logger.exception("Failed to upsert tool usage aggregate %s: %s", usage_id, exc)

    async def upsert_daily_aggregate(
        self,
        record: UsageRecord,
        today: date,
        now: datetime,
    ) -> None:
        usage_id = f"{record.user_id}_{today.isoformat()}"
        safe_model_key = _sanitize_model_key(record.model)
        try:
            collection = DailyUsageDocument.get_motor_collection()
        except Exception as exc:
            logger.warning("DailyUsageDocument collection not initialized, skipping daily aggregate: %s", exc)
            return

        today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        try:
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
        except Exception as exc:
            logger.exception("Failed to upsert daily usage aggregate %s: %s", usage_id, exc)

    async def list_session_usage_records(self, session_id: str) -> list[UsageRecord]:
        try:
            docs = await UsageDocument.find(UsageDocument.session_id == session_id).to_list()
        except Exception as exc:
            logger.exception("Failed to list session usage for %s: %s", session_id, exc)
            return []
        return [record for doc in docs if (record := _coerce_domain(UsageRecord, doc)) is not None]

    async def list_agent_runs(self, user_id: str, start_time: datetime) -> list[AgentRun]:
        try:
            docs = await AgentRunDocument.find(
                {
                    "user_id": user_id,
                    "started_at": {"$gte": start_time},
                }
            ).to_list()
        except Exception as exc:
            logger.exception("Failed to list agent runs for %s since %s: %s", user_id, start_time.isoformat(), exc)
            return []
        return [run for doc in docs if (run := _coerce_domain(AgentRun, doc)) is not None]

    async def list_agent_steps(self, user_id: str, start_time: datetime) -> list[AgentStep]:
        try:
            docs = await AgentStepDocument.find(
                {
                    "user_id": user_id,
                    "started_at": {"$gte": start_time},
                }
            ).to_list()
        except Exception as exc:
            logger.exception("Failed to list agent steps for %s since %s: %s", user_id, start_time.isoformat(), exc)
            return []
        return [step for doc in docs if (step := _coerce_domain(AgentStep, doc)) is not None]

    async def list_daily_usage_since(self, user_id: str, start_date: date) -> list[DailyUsageAggregate]:
        try:
            docs = await DailyUsageDocument.find(
                {
                    "user_id": user_id,
                    "$or": _date_gte_or_legacy_string(start_date),
                }
            ).to_list()
        except Exception as exc:
            logger.exception("Failed to list daily usage for %s since %s: %s", user_id, start_date.isoformat(), exc)
            return []
        docs.sort(key=lambda doc: _coerce_doc_day(getattr(doc, "date", "")))
        return [day for doc in docs if (day := _coerce_domain(DailyUsageAggregate, doc)) is not None]

    async def list_daily_usage_for_day(self, user_id: str, day: date) -> list[DailyUsageAggregate]:
        try:
            docs = await DailyUsageDocument.find(
                {
                    "user_id": user_id,
                    "$or": _date_eq_or_legacy_string(day),
                }
            ).to_list()
        except Exception as exc:
            logger.exception("Failed to list daily usage for %s on %s: %s", user_id, day.isoformat(), exc)
            return []
        return [aggregate for doc in docs if (aggregate := _coerce_domain(DailyUsageAggregate, doc)) is not None]
