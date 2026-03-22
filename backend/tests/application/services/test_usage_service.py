from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.application.services.usage_service import UsageService
from app.domain.models.agent_usage import AgentRun, AgentRunStatus, AgentStep, AgentStepStatus, AgentStepType
from app.domain.models.usage import DailyUsageAggregate, UsageRecord, UsageType
from app.domain.services.agents.usage_context import UsageContextManager
from app.infrastructure.models.documents import AgentRunDocument, AgentStepDocument, DailyUsageDocument, UsageDocument


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

    with patch.object(DailyUsageDocument, "get_motor_collection", return_value=fake_collection):
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

    with patch.object(DailyUsageDocument, "get_motor_collection", return_value=fake_collection):
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
    today_doc = DailyUsageAggregate(
        user_id="user-1",
        date=today,
        total_prompt_tokens=10,
        total_completion_tokens=5,
        total_cost=0.12,
        llm_call_count=2,
        tool_call_count=1,
        active_sessions=["session-1"],
    )
    month_doc = DailyUsageAggregate(
        user_id="user-1",
        date=month_start,
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


@pytest.mark.asyncio
async def test_start_agent_run_persists_running_document() -> None:
    service = UsageService()
    fake_doc = SimpleNamespace(insert=AsyncMock())

    with patch.object(AgentRunDocument, "from_domain", return_value=fake_doc):
        run = await service.start_agent_run(
            user_id="user-1",
            session_id="session-1",
            agent_id="agent-1",
            entrypoint="chat_message",
        )

    assert run.user_id == "user-1"
    assert run.session_id == "session-1"
    assert run.agent_id == "agent-1"
    assert run.entrypoint == "chat_message"
    assert run.status == AgentRunStatus.RUNNING
    fake_doc.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_agent_run_uses_injected_usage_repository() -> None:
    class StartRunRepository:
        def __init__(self) -> None:
            self.inserted_run = None

        async def insert_agent_run(self, run):  # type: ignore[no-untyped-def]
            self.inserted_run = run
            return run

    repository = StartRunRepository()
    service = UsageService(repository=repository)  # type: ignore[arg-type]

    run = await service.start_agent_run(user_id="user-1", session_id="session-1")

    assert run is not None
    assert repository.inserted_run is run


@pytest.mark.asyncio
async def test_start_agent_run_returns_none_when_insert_fails() -> None:
    service = UsageService()
    fake_doc = SimpleNamespace(insert=AsyncMock(side_effect=RuntimeError("insert failed")))

    with patch.object(AgentRunDocument, "from_domain", return_value=fake_doc):
        run = await service.start_agent_run(
            user_id="user-1",
            session_id="session-1",
        )

    assert run is None


@pytest.mark.asyncio
async def test_record_agent_step_updates_run_totals() -> None:
    service = UsageService()
    fake_collection = AsyncMock()
    step = AgentStep(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
        step_type=AgentStepType.LLM,
        provider="openai",
        model="gpt-4o-mini",
        status="completed",
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=40,
        reasoning_tokens=12,
        total_tokens=140,
        estimated_cost_usd=0.123,
    )

    fake_step_doc = SimpleNamespace(insert=AsyncMock())
    with (
        patch.object(AgentStepDocument, "from_domain", return_value=fake_step_doc),
        patch.object(AgentRunDocument, "get_motor_collection", return_value=fake_collection),
    ):
        recorded = await service.record_agent_step(step)

    assert recorded.run_id == "run-1"
    fake_step_doc.insert.assert_awaited_once()
    fake_collection.find_one_and_update.assert_awaited_once()
    _filter_doc, update_doc = fake_collection.find_one_and_update.await_args.args[:2]
    assert update_doc["$inc"]["step_count"] == 1
    assert update_doc["$inc"]["total_input_tokens"] == 100
    assert update_doc["$inc"]["total_cached_input_tokens"] == 20
    assert update_doc["$inc"]["total_output_tokens"] == 40
    assert update_doc["$inc"]["total_reasoning_tokens"] == 12
    assert update_doc["$inc"]["total_tokens"] == 140
    assert update_doc["$inc"]["estimated_cost_usd"] == pytest.approx(0.123)
    assert update_doc["$inc"]["tool_call_count"] == 0
    assert update_doc["$inc"]["mcp_call_count"] == 0
    assert update_doc["$set"]["primary_model"] == "gpt-4o-mini"
    assert update_doc["$set"]["primary_provider"] == "openai"


@pytest.mark.asyncio
async def test_record_agent_step_does_not_clobber_primary_model_for_tool_steps() -> None:
    service = UsageService()
    fake_collection = AsyncMock()
    step = AgentStep(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
        step_type=AgentStepType.TOOL,
        tool_name="search_query",
        status="completed",
    )

    fake_step_doc = SimpleNamespace(insert=AsyncMock())
    with (
        patch.object(AgentStepDocument, "from_domain", return_value=fake_step_doc),
        patch.object(AgentRunDocument, "get_motor_collection", return_value=fake_collection),
    ):
        await service.record_agent_step(step)

    _filter_doc, update_doc = fake_collection.find_one_and_update.await_args.args[:2]
    assert "$set" not in update_doc


@pytest.mark.asyncio
async def test_record_agent_step_skips_run_aggregate_when_step_insert_fails() -> None:
    service = UsageService()
    run_collection = AsyncMock()
    step = AgentStep(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
        step_type=AgentStepType.TOOL,
        tool_name="search_query",
        status=AgentStepStatus.COMPLETED,
    )

    fake_step_doc = SimpleNamespace(insert=AsyncMock(side_effect=RuntimeError("insert failed")))
    with (
        patch.object(AgentStepDocument, "from_domain", return_value=fake_step_doc),
        patch.object(AgentRunDocument, "get_motor_collection", return_value=run_collection),
    ):
        recorded = await service.record_agent_step(step)

    assert recorded == step
    run_collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_llm_usage_with_run_context_records_agent_step() -> None:
    service = UsageService()
    usage_doc = SimpleNamespace(save=AsyncMock())

    with (
        patch.object(UsageDocument, "from_domain", return_value=usage_doc),
        patch.object(service, "_update_daily_aggregate", new=AsyncMock()),
        patch.object(service, "record_agent_step", new=AsyncMock()) as record_agent_step,
    ):
        async with UsageContextManager(user_id="user-1", session_id="session-1", run_id="run-1"):
            await service.record_llm_usage(
                user_id="user-1",
                session_id="session-1",
                model="gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=40,
                cached_tokens=20,
                provider_usage_raw={
                    "prompt_tokens": 100,
                    "completion_tokens": 40,
                    "total_tokens": 140,
                    "prompt_tokens_details": {"cached_tokens": 20},
                    "completion_tokens_details": {"reasoning_tokens": 12},
                },
            )

    record_agent_step.assert_awaited_once()
    step = record_agent_step.await_args.args[0]
    assert step.run_id == "run-1"
    assert step.step_type == AgentStepType.LLM
    assert step.provider == "openai"
    assert step.model == "gpt-4o-mini"
    assert step.input_tokens == 100
    assert step.cached_input_tokens == 20
    assert step.output_tokens == 40
    assert step.reasoning_tokens == 12
    assert step.total_tokens == 140


@pytest.mark.asyncio
async def test_finalize_agent_run_updates_terminal_status_and_duration() -> None:
    service = UsageService()
    fake_collection = AsyncMock()
    started_at = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 3, 17, 12, 0, 5, tzinfo=UTC)
    fake_collection.find_one = AsyncMock(
        return_value={
            "run_id": "run-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": AgentRunStatus.RUNNING.value,
            "started_at": started_at,
        }
    )
    fake_collection.find_one_and_update = AsyncMock(
        return_value={
            "run_id": "run-1",
            "user_id": "user-1",
            "session_id": "session-1",
            "status": AgentRunStatus.COMPLETED.value,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": 5000.0,
        }
    )

    with patch.object(AgentRunDocument, "get_motor_collection", return_value=fake_collection):
        finalized = await service.finalize_agent_run(
            run_id="run-1",
            status=AgentRunStatus.COMPLETED,
            completed_at=completed_at,
        )

    assert finalized is not None
    assert finalized.status == AgentRunStatus.COMPLETED
    assert finalized.completed_at == completed_at
    assert finalized.duration_ms == 5000.0
    fake_collection.find_one_and_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_agent_usage_summary_aggregates_runs_and_cache_savings() -> None:
    service = UsageService()
    run_cursor = AsyncMock()
    step_cursor = AsyncMock()
    run_cursor.to_list = AsyncMock(
        return_value=[
            AgentRun(
                run_id="run-1",
                user_id="user-1",
                session_id="session-1",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 17, 10, 0, tzinfo=UTC),
                duration_ms=2000.0,
                estimated_cost_usd=0.20,
                total_input_tokens=100,
                total_cached_input_tokens=20,
                total_output_tokens=40,
                total_reasoning_tokens=12,
                tool_call_count=2,
                mcp_call_count=1,
            ),
            AgentRun(
                run_id="run-2",
                user_id="user-1",
                session_id="session-2",
                status=AgentRunStatus.FAILED,
                started_at=datetime(2026, 3, 17, 11, 0, tzinfo=UTC),
                duration_ms=4000.0,
                estimated_cost_usd=0.10,
                total_input_tokens=60,
                total_cached_input_tokens=0,
                total_output_tokens=20,
                total_reasoning_tokens=0,
                tool_call_count=1,
                mcp_call_count=0,
            ),
        ]
    )
    step_cursor.to_list = AsyncMock(
        return_value=[
            AgentStep(
                run_id="run-1",
                session_id="session-1",
                user_id="user-1",
                step_type=AgentStepType.LLM,
                status=AgentStepStatus.COMPLETED,
                model="gpt-4o-mini",
                cached_input_tokens=20,
            )
        ]
    )

    with (
        patch.object(AgentRunDocument, "find", return_value=run_cursor),
        patch.object(AgentStepDocument, "find", return_value=step_cursor),
    ):
        summary = await service.get_agent_usage_summary("user-1", days=30)

    assert summary.run_count == 2
    assert summary.completed_run_count == 1
    assert summary.failed_run_count == 1
    assert summary.success_rate == 0.5
    assert summary.avg_run_duration_ms == 3000.0
    assert summary.total_cost == pytest.approx(0.30)
    assert summary.total_input_tokens == 160
    assert summary.total_cached_input_tokens == 20
    assert summary.total_output_tokens == 60
    assert summary.total_reasoning_tokens == 12
    assert summary.total_tool_calls == 3
    assert summary.total_mcp_calls == 1
    assert summary.cache_savings_estimate > 0


@pytest.mark.asyncio
async def test_get_agent_usage_breakdown_groups_steps_by_model() -> None:
    service = UsageService()
    step_cursor = AsyncMock()
    step_cursor.to_list = AsyncMock(
        return_value=[
            AgentStep(
                run_id="run-1",
                session_id="session-1",
                user_id="user-1",
                step_type=AgentStepType.LLM,
                model="gpt-4o-mini",
                provider="openai",
                tool_name=None,
                mcp_server=None,
                status=AgentStepStatus.COMPLETED,
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=40,
                reasoning_tokens=12,
                estimated_cost_usd=0.20,
                duration_ms=1000.0,
            ),
            AgentStep(
                run_id="run-2",
                session_id="session-2",
                user_id="user-1",
                step_type=AgentStepType.LLM,
                model="gpt-4o-mini",
                provider="openai",
                tool_name=None,
                mcp_server=None,
                status=AgentStepStatus.FAILED,
                input_tokens=60,
                cached_input_tokens=0,
                output_tokens=20,
                reasoning_tokens=0,
                estimated_cost_usd=0.10,
                duration_ms=2000.0,
            ),
        ]
    )

    with patch.object(AgentStepDocument, "find", return_value=step_cursor):
        rows = await service.get_agent_usage_breakdown("user-1", days=30, group_by="model")

    assert len(rows) == 1
    row = rows[0]
    assert row.key == "gpt-4o-mini"
    assert row.run_count == 2
    assert row.input_tokens == 160
    assert row.cached_input_tokens == 20
    assert row.output_tokens == 60
    assert row.reasoning_tokens == 12
    assert row.cost == pytest.approx(0.30)
    assert row.avg_duration_ms == 1500.0
    assert row.error_rate == 0.5


@pytest.mark.asyncio
async def test_get_agent_usage_timeseries_groups_runs_by_day() -> None:
    service = UsageService()
    run_cursor = AsyncMock()
    run_cursor.to_list = AsyncMock(
        return_value=[
            AgentRun(
                run_id="run-1",
                user_id="user-1",
                session_id="session-1",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 16, 9, 0, tzinfo=UTC),
                estimated_cost_usd=0.20,
                total_input_tokens=100,
                total_cached_input_tokens=20,
                total_output_tokens=40,
                total_reasoning_tokens=12,
                tool_call_count=2,
                mcp_call_count=1,
            ),
            AgentRun(
                run_id="run-2",
                user_id="user-1",
                session_id="session-2",
                status=AgentRunStatus.FAILED,
                started_at=datetime(2026, 3, 16, 12, 0, tzinfo=UTC),
                estimated_cost_usd=0.10,
                total_input_tokens=60,
                total_cached_input_tokens=0,
                total_output_tokens=20,
                total_reasoning_tokens=0,
                tool_call_count=1,
                mcp_call_count=0,
            ),
            AgentRun(
                run_id="run-3",
                user_id="user-1",
                session_id="session-3",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 17, 8, 0, tzinfo=UTC),
                estimated_cost_usd=0.05,
                total_input_tokens=30,
                total_cached_input_tokens=0,
                total_output_tokens=10,
                total_reasoning_tokens=0,
                tool_call_count=1,
                mcp_call_count=0,
            ),
        ]
    )

    with patch.object(AgentRunDocument, "find", return_value=run_cursor):
        points = await service.get_agent_usage_timeseries("user-1", days=30)

    assert len(points) == 2
    first_point, second_point = points
    assert first_point.date.date().isoformat() == "2026-03-16"
    assert first_point.run_count == 2
    assert first_point.success_count == 1
    assert first_point.failed_count == 1
    assert first_point.cost == pytest.approx(0.30)
    assert second_point.date.date().isoformat() == "2026-03-17"
    assert second_point.run_count == 1
    assert second_point.success_count == 1


@pytest.mark.asyncio
async def test_get_agent_usage_timeseries_groups_runs_by_hour() -> None:
    service = UsageService()
    run_cursor = AsyncMock()
    run_cursor.to_list = AsyncMock(
        return_value=[
            AgentRun(
                run_id="run-1",
                user_id="user-1",
                session_id="session-1",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 17, 9, 5, tzinfo=UTC),
                estimated_cost_usd=0.10,
                total_input_tokens=50,
                total_output_tokens=20,
            ),
            AgentRun(
                run_id="run-2",
                user_id="user-1",
                session_id="session-2",
                status=AgentRunStatus.FAILED,
                started_at=datetime(2026, 3, 17, 9, 45, tzinfo=UTC),
                estimated_cost_usd=0.05,
                total_input_tokens=30,
                total_output_tokens=10,
            ),
            AgentRun(
                run_id="run-3",
                user_id="user-1",
                session_id="session-3",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 17, 10, 15, tzinfo=UTC),
                estimated_cost_usd=0.02,
                total_input_tokens=15,
                total_output_tokens=5,
            ),
        ]
    )

    with patch.object(AgentRunDocument, "find", return_value=run_cursor):
        points = await service.get_agent_usage_timeseries("user-1", days=30, bucket="hour")

    assert len(points) == 2
    assert points[0].date == datetime(2026, 3, 17, 9, 0, tzinfo=UTC)
    assert points[0].run_count == 2
    assert points[0].success_count == 1
    assert points[0].failed_count == 1
    assert points[1].date == datetime(2026, 3, 17, 10, 0, tzinfo=UTC)
    assert points[1].run_count == 1


@pytest.mark.asyncio
async def test_get_agent_usage_timeseries_groups_runs_by_week() -> None:
    service = UsageService()
    run_cursor = AsyncMock()
    run_cursor.to_list = AsyncMock(
        return_value=[
            AgentRun(
                run_id="run-1",
                user_id="user-1",
                session_id="session-1",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 16, 9, 0, tzinfo=UTC),
                estimated_cost_usd=0.10,
                total_input_tokens=50,
                total_output_tokens=20,
            ),
            AgentRun(
                run_id="run-2",
                user_id="user-1",
                session_id="session-2",
                status=AgentRunStatus.FAILED,
                started_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
                estimated_cost_usd=0.05,
                total_input_tokens=30,
                total_output_tokens=10,
            ),
            AgentRun(
                run_id="run-3",
                user_id="user-1",
                session_id="session-3",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
                estimated_cost_usd=0.02,
                total_input_tokens=15,
                total_output_tokens=5,
            ),
        ]
    )

    with patch.object(AgentRunDocument, "find", return_value=run_cursor):
        points = await service.get_agent_usage_timeseries("user-1", days=30, bucket="week")

    assert len(points) == 2
    assert points[0].date == datetime(2026, 3, 16, 0, 0, tzinfo=UTC)
    assert points[0].run_count == 2
    assert points[0].success_count == 1
    assert points[0].failed_count == 1
    assert points[1].date == datetime(2026, 3, 23, 0, 0, tzinfo=UTC)
    assert points[1].run_count == 1
