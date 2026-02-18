from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.usage_service import UsageService
from app.domain.models.usage import UsageRecord, UsageType
from app.infrastructure.models.documents import DailyUsageDocument


@pytest.mark.asyncio
async def test_update_daily_aggregate_upserts_by_usage_id_and_sets_date_type() -> None:
    service = UsageService()
    fake_collection = AsyncMock()
    today = datetime.now(tz=UTC).date()
    usage_id = f"user-1_{today.isoformat()}"
    record = UsageRecord(
        user_id="user-1",
        session_id="session-1",
        model="gpt-4o-mini",
        provider="openai",
        prompt_tokens=10,
        completion_tokens=20,
        cached_tokens=0,
        usage_type=UsageType.LLM_CALL,
    )

    with patch.object(DailyUsageDocument, "get_pymongo_collection", return_value=fake_collection):
        await service._update_daily_aggregate(record)

    fake_collection.find_one_and_update.assert_awaited_once()
    filter_doc, update_doc = fake_collection.find_one_and_update.await_args.args[:2]
    kwargs = fake_collection.find_one_and_update.await_args.kwargs

    assert filter_doc == {"usage_id": usage_id}
    assert kwargs["upsert"] is True
    assert update_doc["$set"]["user_id"] == "user-1"
    today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
    assert update_doc["$set"]["date"] == today_dt
    assert isinstance(update_doc["$set"]["date"], datetime)
    assert update_doc["$setOnInsert"]["usage_id"] == usage_id


@pytest.mark.asyncio
async def test_record_tool_call_uses_atomic_upsert_with_date_object() -> None:
    service = UsageService()
    fake_collection = AsyncMock()
    today = datetime.now(tz=UTC).date()
    usage_id = f"user-1_{today.isoformat()}"

    with patch.object(DailyUsageDocument, "get_pymongo_collection", return_value=fake_collection):
        await service.record_tool_call(user_id="user-1", session_id="session-1")

    fake_collection.find_one_and_update.assert_awaited_once()
    filter_doc, update_doc = fake_collection.find_one_and_update.await_args.args[:2]
    kwargs = fake_collection.find_one_and_update.await_args.kwargs

    assert filter_doc == {"usage_id": usage_id}
    assert kwargs["upsert"] is True
    assert update_doc["$inc"]["tool_call_count"] == 1
    assert update_doc["$set"]["user_id"] == "user-1"
    today_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
    assert update_doc["$set"]["date"] == today_dt
    assert isinstance(update_doc["$set"]["date"], datetime)


@pytest.mark.asyncio
async def test_get_usage_summary_queries_legacy_and_date_storage() -> None:
    service = UsageService()
    today = datetime.now(tz=UTC).date()
    month_start = date(today.year, today.month, 1)
    today_doc = SimpleNamespace(
        total_prompt_tokens=10,
        total_completion_tokens=5,
        total_cost=0.12,
        llm_call_count=2,
        tool_call_count=1,
        active_sessions=["session-1"],
    )
    month_doc = SimpleNamespace(
        total_prompt_tokens=10,
        total_completion_tokens=5,
        total_cost=0.12,
        llm_call_count=2,
        tool_call_count=1,
        active_sessions=["session-1"],
    )
    today_cursor = AsyncMock()
    today_cursor.to_list = AsyncMock(return_value=[today_doc])
    month_cursor = AsyncMock()
    month_cursor.to_list = AsyncMock(return_value=[month_doc])

    def _find_side_effect(query: dict) -> AsyncMock:
        clauses = query.get("$or", [])
        if {"date": today} in clauses:
            return today_cursor
        return month_cursor

    with patch.object(DailyUsageDocument, "find", side_effect=_find_side_effect) as find_mock:
        summary = await service.get_usage_summary("user-1")

    assert len(find_mock.call_args_list) == 2
    today_query = find_mock.call_args_list[0].args[0]
    month_query = find_mock.call_args_list[1].args[0]

    assert {"date": today} in today_query["$or"]
    assert {"date": today.isoformat()} in today_query["$or"]
    assert any(
        isinstance(clause.get("date"), dict) and "$gte" in clause["date"] and "$lt" in clause["date"]
        for clause in today_query["$or"]
    )
    assert {"date": {"$gte": month_start}} in month_query["$or"]
    assert {"date": {"$gte": month_start.isoformat()}} in month_query["$or"]
    assert any(
        isinstance(clause.get("date"), dict)
        and "$gte" in clause["date"]
        and isinstance(clause["date"]["$gte"], datetime)
        for clause in month_query["$or"]
    )
    assert summary["today"]["tokens"] == 15
    assert summary["month"]["active_days"] == 1
