from datetime import UTC, date, datetime

import pytest

from app.application.services.usage_service import UsageService
from app.domain.models.agent_usage import AgentRun, AgentRunStatus, AgentStep, AgentStepStatus, AgentStepType
from app.domain.models.usage import DailyUsageAggregate, UsageRecord, UsageType
from app.domain.services.agents.usage_context import UsageContextManager


class FakeUsageRepository:
    """In-memory fake that captures calls for assertion."""

    def __init__(self) -> None:
        self.upsert_daily_aggregate_calls: list[tuple[UsageRecord, date, datetime]] = []
        self.upsert_tool_call_daily_calls: list[tuple[str, str, date, datetime]] = []
        self.save_usage_record_calls: list[UsageRecord] = []
        self.inserted_runs: list[AgentRun] = []
        self.inserted_steps: list[AgentStep] = []
        self.increment_calls: list[AgentStep] = []
        self.finalize_calls: list[tuple[str, AgentRunStatus, datetime]] = []
        self.finalize_return: AgentRun | None = None
        self.insert_step_succeeds: bool = True
        self.insert_run_succeeds: bool = True
        # Query return values
        self.daily_usage_for_day_return: list[DailyUsageAggregate] = []
        self.daily_usage_since_return: list[DailyUsageAggregate] = []
        self.agent_runs_return: list[AgentRun] = []
        self.agent_steps_return: list[AgentStep] = []

    async def insert_agent_run(self, run: AgentRun) -> AgentRun | None:
        if not self.insert_run_succeeds:
            return None
        self.inserted_runs.append(run)
        return run

    async def finalize_agent_run(self, run_id: str, status: AgentRunStatus, completed_at: datetime) -> AgentRun | None:
        self.finalize_calls.append((run_id, status, completed_at))
        return self.finalize_return

    async def insert_agent_step(self, step: AgentStep) -> bool:
        if not self.insert_step_succeeds:
            return False
        self.inserted_steps.append(step)
        return True

    async def increment_agent_run_aggregate(self, step: AgentStep) -> None:
        self.increment_calls.append(step)

    async def save_usage_record(self, record: UsageRecord) -> None:
        self.save_usage_record_calls.append(record)

    async def upsert_tool_call_daily(self, user_id: str, session_id: str, today: date, now: datetime) -> None:
        self.upsert_tool_call_daily_calls.append((user_id, session_id, today, now))

    async def upsert_daily_aggregate(self, record: UsageRecord, today: date, now: datetime) -> None:
        self.upsert_daily_aggregate_calls.append((record, today, now))

    async def list_session_usage_records(self, session_id: str) -> list[UsageRecord]:
        return []

    async def list_agent_runs(self, user_id: str, start_time: datetime) -> list[AgentRun]:
        return self.agent_runs_return

    async def list_agent_steps(self, user_id: str, start_time: datetime) -> list[AgentStep]:
        return self.agent_steps_return

    async def list_daily_usage_since(self, user_id: str, start_date: date) -> list[DailyUsageAggregate]:
        return self.daily_usage_since_return

    async def list_daily_usage_for_day(self, user_id: str, day: date) -> list[DailyUsageAggregate]:
        return self.daily_usage_for_day_return


@pytest.mark.asyncio
async def test_update_daily_aggregate_upserts_by_usage_id_and_sets_date_type() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]
    today = datetime.now(tz=UTC).date()
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

    await service._update_daily_aggregate(record)

    assert len(repo.upsert_daily_aggregate_calls) == 1
    call_record, call_today, call_now = repo.upsert_daily_aggregate_calls[0]
    assert call_record is record
    assert call_today == today
    assert isinstance(call_now, datetime)


@pytest.mark.asyncio
async def test_record_tool_call_uses_atomic_upsert_with_date_object() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]
    today = datetime.now(tz=UTC).date()

    await service.record_tool_call(user_id="user-1", session_id="session-1")

    assert len(repo.upsert_tool_call_daily_calls) == 1
    user_id, session_id, call_today, call_now = repo.upsert_tool_call_daily_calls[0]
    assert user_id == "user-1"
    assert session_id == "session-1"
    assert call_today == today
    assert isinstance(call_now, datetime)


@pytest.mark.asyncio
async def test_get_usage_summary_queries_legacy_and_date_storage() -> None:
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
    repo = FakeUsageRepository()
    repo.daily_usage_for_day_return = [today_doc]
    repo.daily_usage_since_return = [month_doc]
    service = UsageService(repository=repo)  # type: ignore[arg-type]

    summary = await service.get_usage_summary("user-1")

    assert summary["today"]["tokens"] == 15
    assert summary["month"]["active_days"] == 1


@pytest.mark.asyncio
async def test_start_agent_run_persists_running_document() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]

    run = await service.start_agent_run(
        user_id="user-1",
        session_id="session-1",
        agent_id="agent-1",
        entrypoint="chat_message",
    )

    assert run is not None
    assert run.user_id == "user-1"
    assert run.session_id == "session-1"
    assert run.agent_id == "agent-1"
    assert run.entrypoint == "chat_message"
    assert run.status == AgentRunStatus.RUNNING
    assert len(repo.inserted_runs) == 1
    assert repo.inserted_runs[0] is run


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
    repo = FakeUsageRepository()
    repo.insert_run_succeeds = False
    service = UsageService(repository=repo)  # type: ignore[arg-type]

    run = await service.start_agent_run(
        user_id="user-1",
        session_id="session-1",
    )

    assert run is None


@pytest.mark.asyncio
async def test_record_agent_step_updates_run_totals() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]
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

    recorded = await service.record_agent_step(step)

    assert recorded.run_id == "run-1"
    assert len(repo.inserted_steps) == 1
    assert repo.inserted_steps[0] is step
    assert len(repo.increment_calls) == 1
    incremented_step = repo.increment_calls[0]
    assert incremented_step.input_tokens == 100
    assert incremented_step.cached_input_tokens == 20
    assert incremented_step.output_tokens == 40
    assert incremented_step.reasoning_tokens == 12
    assert incremented_step.total_tokens == 140
    assert incremented_step.estimated_cost_usd == pytest.approx(0.123)
    assert incremented_step.model == "gpt-4o-mini"
    assert incremented_step.provider == "openai"


@pytest.mark.asyncio
async def test_record_agent_step_does_not_clobber_primary_model_for_tool_steps() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]
    step = AgentStep(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
        step_type=AgentStepType.TOOL,
        tool_name="search_query",
        status="completed",
    )

    await service.record_agent_step(step)

    assert len(repo.inserted_steps) == 1
    assert len(repo.increment_calls) == 1
    # The step passed to increment has no model set (tool step)
    assert repo.increment_calls[0].model is None


@pytest.mark.asyncio
async def test_record_agent_step_skips_run_aggregate_when_step_insert_fails() -> None:
    repo = FakeUsageRepository()
    repo.insert_step_succeeds = False
    service = UsageService(repository=repo)  # type: ignore[arg-type]
    step = AgentStep(
        run_id="run-1",
        session_id="session-1",
        user_id="user-1",
        step_type=AgentStepType.TOOL,
        tool_name="search_query",
        status=AgentStepStatus.COMPLETED,
    )

    recorded = await service.record_agent_step(step)

    assert recorded == step
    assert len(repo.increment_calls) == 0


@pytest.mark.asyncio
async def test_record_llm_usage_with_run_context_records_agent_step() -> None:
    repo = FakeUsageRepository()
    service = UsageService(repository=repo)  # type: ignore[arg-type]

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

    assert len(repo.inserted_steps) == 1
    step = repo.inserted_steps[0]
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
    started_at = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 3, 17, 12, 0, 5, tzinfo=UTC)

    repo = FakeUsageRepository()
    repo.finalize_return = AgentRun(
        run_id="run-1",
        user_id="user-1",
        session_id="session-1",
        status=AgentRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=5000.0,
    )
    service = UsageService(repository=repo)  # type: ignore[arg-type]

    finalized = await service.finalize_agent_run(
        run_id="run-1",
        status=AgentRunStatus.COMPLETED,
        completed_at=completed_at,
    )

    assert finalized is not None
    assert finalized.status == AgentRunStatus.COMPLETED
    assert finalized.completed_at == completed_at
    assert finalized.duration_ms == 5000.0
    assert len(repo.finalize_calls) == 1
    call_run_id, call_status, call_completed_at = repo.finalize_calls[0]
    assert call_run_id == "run-1"
    assert call_status == AgentRunStatus.COMPLETED
    assert call_completed_at == completed_at


@pytest.mark.asyncio
async def test_get_agent_usage_summary_aggregates_runs_and_cache_savings() -> None:
    repo = FakeUsageRepository()
    repo.agent_runs_return = [
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
    repo.agent_steps_return = [
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
    service = UsageService(repository=repo)  # type: ignore[arg-type]

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
    repo = FakeUsageRepository()
    repo.agent_steps_return = [
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
    service = UsageService(repository=repo)  # type: ignore[arg-type]

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
    repo = FakeUsageRepository()
    repo.agent_runs_return = [
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
    service = UsageService(repository=repo)  # type: ignore[arg-type]

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
    repo = FakeUsageRepository()
    repo.agent_runs_return = [
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
    service = UsageService(repository=repo)  # type: ignore[arg-type]

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
    repo = FakeUsageRepository()
    repo.agent_runs_return = [
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
    service = UsageService(repository=repo)  # type: ignore[arg-type]

    points = await service.get_agent_usage_timeseries("user-1", days=30, bucket="week")

    assert len(points) == 2
    assert points[0].date == datetime(2026, 3, 16, 0, 0, tzinfo=UTC)
    assert points[0].run_count == 2
    assert points[0].success_count == 1
    assert points[0].failed_count == 1
    assert points[1].date == datetime(2026, 3, 23, 0, 0, tzinfo=UTC)
    assert points[1].run_count == 1
