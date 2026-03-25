"""Extended tests for UsageService covering uncovered code paths.

Complements test_usage_service.py which already covers:
  start_agent_run, finalize_agent_run, record_agent_step,
  record_llm_usage (with run context), _update_daily_aggregate,
  record_tool_call (basic), get_usage_summary,
  get_agent_usage_summary, get_agent_usage_breakdown,
  get_agent_usage_timeseries (day/hour/week).

This file adds coverage for:
  - get_session_usage (empty, single record, multi-record with type branches)
  - get_monthly_summary (multi-day rollup, session dedup, cost_by_model, active_days)
  - get_recent_agent_runs (sorting, limit)
  - get_daily_usage (delegation)
  - record_tool_call (with run context: TOOL vs MCP step type, duration_ms backfill)
  - _normalize_llm_usage (synthetic fallback, real raw usage)
  - Module-level helpers: _days_ago, _estimate_cache_savings,
    _group_step_key, _sanitize_model_key, _date_eq_or_legacy_string,
    _date_gte_or_legacy_string, _coerce_doc_day, _timeseries_bucket_start
"""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.application.services.usage_service import (
    UsageService,
    _coerce_doc_day,
    _date_eq_or_legacy_string,
    _date_gte_or_legacy_string,
    _days_ago,
    _estimate_cache_savings,
    _group_step_key,
    _sanitize_model_key,
    _timeseries_bucket_start,
)
from app.domain.models.agent_usage import AgentRun, AgentRunStatus, AgentStep, AgentStepType
from app.domain.models.usage import DailyUsageAggregate, UsageRecord, UsageType
from app.domain.services.agents.usage_context import UsageContextManager

# ---------------------------------------------------------------------------
# Shared fake repository
# ---------------------------------------------------------------------------


class FakeUsageRepository:
    def __init__(self) -> None:
        self.upsert_daily_aggregate_calls: list = []
        self.upsert_tool_call_daily_calls: list = []
        self.save_usage_record_calls: list[UsageRecord] = []
        self.inserted_runs: list[AgentRun] = []
        self.inserted_steps: list[AgentStep] = []
        self.increment_calls: list[AgentStep] = []
        self.finalize_calls: list = []
        self.finalize_return: AgentRun | None = None
        self.insert_step_succeeds: bool = True
        self.insert_run_succeeds: bool = True
        self.session_usage_records: list[UsageRecord] = []
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
        return self.session_usage_records

    async def list_agent_runs(self, user_id: str, start_time: datetime) -> list[AgentRun]:
        return self.agent_runs_return

    async def list_agent_steps(self, user_id: str, start_time: datetime) -> list[AgentStep]:
        return self.agent_steps_return

    async def list_daily_usage_since(self, user_id: str, start_date: date) -> list[DailyUsageAggregate]:
        return self.daily_usage_since_return

    async def list_daily_usage_for_day(self, user_id: str, day: date) -> list[DailyUsageAggregate]:
        return self.daily_usage_for_day_return


def _make_service(repo: FakeUsageRepository | None = None) -> tuple[UsageService, FakeUsageRepository]:
    r = repo or FakeUsageRepository()
    return UsageService(repository=r), r  # type: ignore[arg-type]


def _make_record(
    user_id: str = "user-1",
    session_id: str = "session-1",
    model: str = "gpt-4o-mini",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int = 0,
    total_cost: float = 0.10,
    usage_type: UsageType = UsageType.LLM_CALL,
    created_at: datetime | None = None,
) -> UsageRecord:
    record = UsageRecord(
        user_id=user_id,
        session_id=session_id,
        model=model,
        provider="openai",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        prompt_cost=total_cost * 0.7,
        completion_cost=total_cost * 0.3,
        total_cost=total_cost,
        usage_type=usage_type,
    )
    if created_at is not None:
        record.created_at = created_at
    return record


# ===========================================================================
# get_session_usage
# ===========================================================================


@pytest.mark.asyncio
async def test_get_session_usage_returns_empty_usage_for_new_session() -> None:
    service, _ = _make_service()

    result = await service.get_session_usage("session-new")

    assert result.session_id == "session-new"
    assert result.user_id == ""
    assert result.total_prompt_tokens == 0
    assert result.total_cost == 0.0
    assert result.llm_call_count == 0


@pytest.mark.asyncio
async def test_get_session_usage_aggregates_single_record() -> None:
    service, repo = _make_service()
    repo.session_usage_records = [
        _make_record(
            user_id="user-1",
            session_id="s1",
            prompt_tokens=200,
            completion_tokens=80,
            cached_tokens=10,
            total_cost=0.25,
            usage_type=UsageType.LLM_CALL,
        )
    ]

    result = await service.get_session_usage("s1")

    assert result.user_id == "user-1"
    assert result.total_prompt_tokens == 200
    assert result.total_completion_tokens == 80
    assert result.total_cached_tokens == 10
    assert result.total_cost == pytest.approx(0.25)
    assert result.llm_call_count == 1
    assert result.tool_call_count == 0
    assert result.tokens_by_model == {"gpt-4o-mini": 280}
    assert result.cost_by_model == {"gpt-4o-mini": pytest.approx(0.25)}


@pytest.mark.asyncio
async def test_get_session_usage_counts_tool_calls_separately() -> None:
    service, repo = _make_service()
    repo.session_usage_records = [
        _make_record(usage_type=UsageType.LLM_CALL, total_cost=0.10),
        _make_record(usage_type=UsageType.TOOL_CALL, total_cost=0.0),
        _make_record(usage_type=UsageType.LLM_CALL, total_cost=0.05),
    ]

    result = await service.get_session_usage("s1")

    assert result.llm_call_count == 2
    assert result.tool_call_count == 1
    assert result.total_cost == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_get_session_usage_tracks_first_and_last_activity() -> None:
    service, repo = _make_service()
    t1 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)

    repo.session_usage_records = [
        _make_record(created_at=t1),
        _make_record(created_at=t2),
        _make_record(created_at=t3),
    ]

    result = await service.get_session_usage("s1")

    assert result.first_activity == t1
    assert result.last_activity == t2


@pytest.mark.asyncio
async def test_get_session_usage_groups_tokens_by_model() -> None:
    service, repo = _make_service()
    repo.session_usage_records = [
        _make_record(model="gpt-4o-mini", prompt_tokens=100, completion_tokens=40, total_cost=0.05),
        _make_record(model="gpt-4o", prompt_tokens=200, completion_tokens=80, total_cost=0.20),
        _make_record(model="gpt-4o-mini", prompt_tokens=50, completion_tokens=20, total_cost=0.02),
    ]

    result = await service.get_session_usage("s1")

    assert result.tokens_by_model["gpt-4o-mini"] == (100 + 40) + (50 + 20)
    assert result.tokens_by_model["gpt-4o"] == 200 + 80


# ===========================================================================
# get_monthly_summary
# ===========================================================================


@pytest.mark.asyncio
async def test_get_monthly_summary_rolls_up_daily_docs_into_months() -> None:
    service, repo = _make_service()
    repo.daily_usage_since_return = [
        DailyUsageAggregate(
            user_id="user-1",
            date=date(2026, 3, 10),
            total_prompt_tokens=500,
            total_completion_tokens=200,
            total_cached_tokens=50,
            total_cost=1.50,
            llm_call_count=5,
            tool_call_count=3,
            active_sessions=["session-a", "session-b"],
        ),
        DailyUsageAggregate(
            user_id="user-1",
            date=date(2026, 3, 12),
            total_prompt_tokens=300,
            total_completion_tokens=100,
            total_cached_tokens=20,
            total_cost=0.80,
            llm_call_count=2,
            tool_call_count=1,
            active_sessions=["session-b", "session-c"],
        ),
        DailyUsageAggregate(
            user_id="user-1",
            date=date(2026, 2, 28),
            total_prompt_tokens=100,
            total_completion_tokens=40,
            total_cached_tokens=0,
            total_cost=0.30,
            llm_call_count=1,
            tool_call_count=0,
            active_sessions=["session-d"],
        ),
    ]

    summaries = await service.get_monthly_summary("user-1", months=12)

    assert len(summaries) == 2
    feb = next(s for s in summaries if s.month == 2)
    mar = next(s for s in summaries if s.month == 3)

    assert feb.total_cost == pytest.approx(0.30)
    assert feb.total_sessions == 1
    assert feb.active_days == 1

    assert mar.total_prompt_tokens == 800
    assert mar.total_completion_tokens == 300
    assert mar.total_cost == pytest.approx(2.30)
    assert mar.total_llm_calls == 7
    assert mar.total_tool_calls == 4
    # Unique sessions: session-a, session-b, session-c
    assert mar.total_sessions == 3
    assert mar.active_days == 2


@pytest.mark.asyncio
async def test_get_monthly_summary_returns_empty_when_no_data() -> None:
    service, _ = _make_service()

    result = await service.get_monthly_summary("user-no-data")

    assert result == []


@pytest.mark.asyncio
async def test_get_monthly_summary_accumulates_cost_by_model() -> None:
    service, repo = _make_service()
    repo.daily_usage_since_return = [
        DailyUsageAggregate(
            user_id="user-1",
            date=date(2026, 3, 10),
            total_cost=1.0,
            cost_by_model={"gpt-4o-mini": 0.60, "gpt-4o": 0.40},
            active_sessions=[],
        ),
        DailyUsageAggregate(
            user_id="user-1",
            date=date(2026, 3, 11),
            total_cost=0.50,
            cost_by_model={"gpt-4o-mini": 0.50},
            active_sessions=[],
        ),
    ]

    summaries = await service.get_monthly_summary("user-1", months=1)

    assert len(summaries) == 1
    cost_by_model = summaries[0].cost_by_model
    assert cost_by_model["gpt-4o-mini"] == pytest.approx(1.10)
    assert cost_by_model["gpt-4o"] == pytest.approx(0.40)


# ===========================================================================
# get_recent_agent_runs
# ===========================================================================


@pytest.mark.asyncio
async def test_get_recent_agent_runs_returns_sorted_by_started_at_descending() -> None:
    service, repo = _make_service()
    t1 = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 11, 9, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
    repo.agent_runs_return = [
        AgentRun(run_id="run-1", user_id="user-1", session_id="s1", started_at=t1),
        AgentRun(run_id="run-3", user_id="user-1", session_id="s3", started_at=t3),
        AgentRun(run_id="run-2", user_id="user-1", session_id="s2", started_at=t2),
    ]

    runs = await service.get_recent_agent_runs("user-1", days=30)

    assert [r.run_id for r in runs] == ["run-3", "run-2", "run-1"]


@pytest.mark.asyncio
async def test_get_recent_agent_runs_respects_limit() -> None:
    service, repo = _make_service()
    repo.agent_runs_return = [
        AgentRun(run_id=f"run-{i}", user_id="u", session_id="s", started_at=datetime(2026, 3, i + 1, tzinfo=UTC))
        for i in range(5)
    ]

    runs = await service.get_recent_agent_runs("u", days=30, limit=2)

    assert len(runs) == 2


@pytest.mark.asyncio
async def test_get_recent_agent_runs_returns_empty_when_no_runs() -> None:
    service, _ = _make_service()

    runs = await service.get_recent_agent_runs("user-empty", days=30)

    assert runs == []


# ===========================================================================
# get_daily_usage
# ===========================================================================


@pytest.mark.asyncio
async def test_get_daily_usage_delegates_to_repository() -> None:
    service, repo = _make_service()
    today = datetime.now(UTC).date()
    expected = [DailyUsageAggregate(user_id="user-1", date=today, total_cost=0.50, active_sessions=[])]
    repo.daily_usage_since_return = expected

    result = await service.get_daily_usage("user-1", days=7)

    assert result is expected


# ===========================================================================
# record_tool_call — with run context
# ===========================================================================


@pytest.mark.asyncio
async def test_record_tool_call_with_run_context_records_tool_step() -> None:
    service, repo = _make_service()

    async with UsageContextManager(user_id="u1", session_id="s1", run_id="run-tool"):
        await service.record_tool_call(
            user_id="u1",
            session_id="s1",
            tool_name="file_read",
            status="completed",
            duration_ms=150.0,
        )

    assert len(repo.inserted_steps) == 1
    step = repo.inserted_steps[0]
    assert step.run_id == "run-tool"
    assert step.step_type == AgentStepType.TOOL
    assert step.tool_name == "file_read"
    assert step.mcp_server is None
    assert step.duration_ms == 150.0


@pytest.mark.asyncio
async def test_record_tool_call_with_run_context_records_mcp_step() -> None:
    service, repo = _make_service()

    async with UsageContextManager(user_id="u1", session_id="s1", run_id="run-mcp"):
        await service.record_tool_call(
            user_id="u1",
            session_id="s1",
            tool_name="browser_navigate",
            mcp_server="playwright",
            status="completed",
        )

    assert len(repo.inserted_steps) == 1
    step = repo.inserted_steps[0]
    assert step.step_type == AgentStepType.MCP
    assert step.mcp_server == "playwright"


@pytest.mark.asyncio
async def test_record_tool_call_backfills_started_at_from_duration_ms() -> None:
    service, repo = _make_service()

    async with UsageContextManager(user_id="u1", session_id="s1", run_id="run-backfill"):
        await service.record_tool_call(
            user_id="u1",
            session_id="s1",
            tool_name="search_web",
            duration_ms=500.0,
        )

    step = repo.inserted_steps[0]
    assert step.started_at < step.completed_at  # type: ignore[operator]
    delta = (step.completed_at - step.started_at).total_seconds() * 1000  # type: ignore[operator]
    assert abs(delta - 500.0) < 50  # within 50ms of expected


@pytest.mark.asyncio
async def test_record_tool_call_without_run_context_skips_step_recording() -> None:
    """No usage context → no agent step, but daily upsert still fires."""
    service, repo = _make_service()

    await service.record_tool_call(
        user_id="u1",
        session_id="s1",
        tool_name="terminal_exec",
    )

    assert len(repo.inserted_steps) == 0
    assert len(repo.upsert_tool_call_daily_calls) == 1


@pytest.mark.asyncio
async def test_record_tool_call_without_tool_name_skips_step_even_with_run_context() -> None:
    service, repo = _make_service()

    async with UsageContextManager(user_id="u1", session_id="s1", run_id="run-notool"):
        await service.record_tool_call(user_id="u1", session_id="s1")

    assert len(repo.inserted_steps) == 0


# ===========================================================================
# _normalize_llm_usage
# ===========================================================================


def test_normalize_llm_usage_returns_synthetic_when_no_raw_usage() -> None:
    service, _ = _make_service()

    result = service._normalize_llm_usage(
        provider="openai",
        prompt_tokens=100,
        completion_tokens=40,
        cached_tokens=20,
        provider_usage_raw=None,
    )

    assert result.input_tokens == 100
    assert result.output_tokens == 40
    assert result.cached_input_tokens == 20
    assert result.total_tokens == 140
    assert result.reasoning_tokens == 0
    assert result.raw_usage["prompt_tokens"] == 100
    assert result.raw_usage["completion_tokens"] == 40
    assert result.raw_usage["prompt_tokens_details"]["cached_tokens"] == 20


def test_normalize_llm_usage_uses_provider_raw_when_available() -> None:
    service, _ = _make_service()

    raw = {
        "prompt_tokens": 200,
        "completion_tokens": 80,
        "total_tokens": 280,
        "prompt_tokens_details": {"cached_tokens": 30},
        "completion_tokens_details": {"reasoning_tokens": 15},
    }

    result = service._normalize_llm_usage(
        provider="openai",
        prompt_tokens=200,
        completion_tokens=80,
        cached_tokens=30,
        provider_usage_raw=raw,
    )

    assert result.input_tokens == 200
    assert result.output_tokens == 80
    assert result.cached_input_tokens == 30
    assert result.reasoning_tokens == 15
    assert result.total_tokens == 280


def test_normalize_llm_usage_falls_back_to_synthetic_when_raw_empty() -> None:
    """Empty raw dict has no `raw_usage` after normalization, triggers synthetic."""
    service, _ = _make_service()

    result = service._normalize_llm_usage(
        provider="openai",
        prompt_tokens=50,
        completion_tokens=20,
        cached_tokens=5,
        provider_usage_raw={},
    )

    # Empty dict normalizes to a NormalizedUsage with empty raw_usage -> falls back
    assert result.input_tokens == 50
    assert result.output_tokens == 20


# ===========================================================================
# Module-level helpers
# ===========================================================================


# --- _sanitize_model_key ---


def test_sanitize_model_key_replaces_slashes_and_dots() -> None:
    assert _sanitize_model_key("google/gemini-2.5-flash") == "google_gemini-2_5-flash"


def test_sanitize_model_key_plain_name_unchanged() -> None:
    assert _sanitize_model_key("gpt-4o-mini") == "gpt-4o-mini"


# --- _date_eq_or_legacy_string ---


def test_date_eq_or_legacy_string_returns_four_entries() -> None:
    result = _date_eq_or_legacy_string(date(2026, 3, 15))

    assert len(result) == 4
    # First entry: exact date match
    assert result[0] == {"date": date(2026, 3, 15)}
    # Second entry: ISO string match
    assert result[1] == {"date": "2026-03-15"}


# --- _date_gte_or_legacy_string ---


def test_date_gte_or_legacy_string_returns_four_entries() -> None:
    result = _date_gte_or_legacy_string(date(2026, 3, 1))

    assert len(result) == 4
    assert result[0] == {"date": {"$gte": date(2026, 3, 1)}}
    assert result[1] == {"date": {"$gte": "2026-03-01"}}


# --- _coerce_doc_day ---


def test_coerce_doc_day_handles_datetime() -> None:
    dt = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
    assert _coerce_doc_day(dt) == "2026-03-15"


def test_coerce_doc_day_handles_date() -> None:
    d = date(2026, 3, 15)
    assert _coerce_doc_day(d) == "2026-03-15"


def test_coerce_doc_day_handles_string() -> None:
    assert _coerce_doc_day("2026-03-15") == "2026-03-15"


def test_coerce_doc_day_handles_arbitrary_object() -> None:
    result = _coerce_doc_day(42)
    assert result == "42"


# --- _timeseries_bucket_start ---


def test_timeseries_bucket_start_hour() -> None:
    dt = datetime(2026, 3, 15, 14, 37, 22, tzinfo=UTC)
    result = _timeseries_bucket_start(dt, "hour")
    assert result == datetime(2026, 3, 15, 14, 0, 0, tzinfo=UTC)


def test_timeseries_bucket_start_day() -> None:
    dt = datetime(2026, 3, 15, 14, 37, 22, tzinfo=UTC)
    result = _timeseries_bucket_start(dt, "day")
    assert result == datetime(2026, 3, 15, 0, 0, 0, tzinfo=UTC)


def test_timeseries_bucket_start_week_returns_monday() -> None:
    # 2026-03-15 is a Sunday (weekday == 6)
    dt = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
    result = _timeseries_bucket_start(dt, "week")
    # Monday of that week is 2026-03-09
    assert result == datetime(2026, 3, 9, 0, 0, 0, tzinfo=UTC)


def test_timeseries_bucket_start_raises_for_invalid_bucket() -> None:
    dt = datetime(2026, 3, 15, tzinfo=UTC)
    with pytest.raises(ValueError, match="Unsupported usage timeseries bucket"):
        _timeseries_bucket_start(dt, "month")


def test_timeseries_bucket_start_converts_non_utc_timezone_to_utc() -> None:
    # +05:00 offset
    tz_plus5 = timezone(timedelta(hours=5))
    dt = datetime(2026, 3, 15, 19, 0, 0, tzinfo=tz_plus5)  # 14:00 UTC
    result = _timeseries_bucket_start(dt, "hour")
    assert result == datetime(2026, 3, 15, 14, 0, 0, tzinfo=UTC)


# --- _days_ago ---


def test_days_ago_returns_datetime_n_minus_1_days_before_now() -> None:
    before = datetime.now(UTC)
    result = _days_ago(7)
    after = datetime.now(UTC)

    expected_delta = timedelta(days=6)
    assert before - expected_delta - timedelta(seconds=1) <= result <= after - expected_delta + timedelta(seconds=1)


def test_days_ago_clamps_to_one_day_minimum() -> None:
    result_zero = _days_ago(0)
    result_neg = _days_ago(-5)
    # Both should be ~now (1 day window → 0 days ago)
    now = datetime.now(UTC)
    assert abs((now - result_zero).total_seconds()) < 5
    assert abs((now - result_neg).total_seconds()) < 5


# --- _estimate_cache_savings ---


def test_estimate_cache_savings_returns_zero_when_no_model() -> None:
    class NoModel:
        cached_input_tokens = 100

    assert _estimate_cache_savings(NoModel()) == 0.0


def test_estimate_cache_savings_returns_zero_when_no_cached_tokens() -> None:
    class NoCache:
        model = "gpt-4o-mini"
        cached_input_tokens = 0

    assert _estimate_cache_savings(NoCache()) == 0.0


def test_estimate_cache_savings_returns_zero_when_cached_price_is_none() -> None:
    class FreeCacheModel:
        model = "gpt-4o-2024-05-13"  # has cached_price=None in pricing table
        cached_input_tokens = 500

    result = _estimate_cache_savings(FreeCacheModel())
    assert result == 0.0


def test_estimate_cache_savings_returns_positive_for_known_model_with_cached_price() -> None:
    class GoodCache:
        model = "gpt-4o-mini"  # prompt=0.15, cached=0.075 → savings > 0
        cached_input_tokens = 1_000_000

    result = _estimate_cache_savings(GoodCache())
    # Savings = (1_000_000 / 1_000_000) * (0.15 - 0.075) = 0.075
    assert result == pytest.approx(0.075)


def test_estimate_cache_savings_returns_zero_when_cached_price_exceeds_prompt_price() -> None:
    """No savings when cached_price >= prompt_price (edge case)."""
    from app.domain.services.usage.pricing import MODEL_PRICING, ModelPricing

    original = MODEL_PRICING.get("test-model-edge")
    MODEL_PRICING["test-model-edge"] = ModelPricing(prompt_price=1.0, completion_price=2.0, cached_price=2.0)
    try:

        class EdgeModel:
            model = "test-model-edge"
            cached_input_tokens = 1_000_000

        result = _estimate_cache_savings(EdgeModel())
        assert result == 0.0
    finally:
        if original is None:
            del MODEL_PRICING["test-model-edge"]
        else:
            MODEL_PRICING["test-model-edge"] = original


# --- _group_step_key ---


def test_group_step_key_by_model() -> None:
    class Step:
        model = "gpt-4o-mini"
        provider = "openai"
        tool_name = None
        mcp_server = None

    assert _group_step_key(Step(), "model") == "gpt-4o-mini"


def test_group_step_key_by_provider() -> None:
    class Step:
        model = "gpt-4o-mini"
        provider = "openai"
        tool_name = None
        mcp_server = None

    assert _group_step_key(Step(), "provider") == "openai"


def test_group_step_key_by_tool() -> None:
    class Step:
        model = None
        provider = None
        tool_name = "search_web"
        mcp_server = None

    assert _group_step_key(Step(), "tool") == "search_web"


def test_group_step_key_by_mcp_server() -> None:
    class Step:
        model = None
        provider = None
        tool_name = "browse"
        mcp_server = "playwright"

    assert _group_step_key(Step(), "mcp_server") == "playwright"


def test_group_step_key_falls_back_to_model_for_unknown_group_by() -> None:
    class Step:
        model = "kimi-for-coding"
        provider = "moonshot"
        tool_name = None
        mcp_server = None

    assert _group_step_key(Step(), "unknown_group") == "kimi-for-coding"


def test_group_step_key_returns_unknown_when_field_is_none() -> None:
    class Step:
        model = None
        provider = None
        tool_name = None
        mcp_server = None

    assert _group_step_key(Step(), "tool") == "unknown"
