"""Tests for usage tracking domain models."""

from datetime import date

from app.domain.models.usage import (
    DailyUsageAggregate,
    MonthlyUsageSummary,
    SessionMetrics,
    SessionUsage,
    UsageRecord,
    UsageType,
)


class TestUsageType:
    def test_values(self) -> None:
        assert UsageType.LLM_CALL == "llm_call"
        assert UsageType.TOOL_CALL == "tool_call"
        assert UsageType.EMBEDDING == "embedding"


class TestUsageRecord:
    def test_defaults(self) -> None:
        r = UsageRecord(user_id="u-1", session_id="s-1", model="gpt-4o", provider="openai")
        assert r.prompt_tokens == 0
        assert r.completion_tokens == 0
        assert r.cached_tokens == 0
        assert r.total_cost == 0.0
        assert r.usage_type == UsageType.LLM_CALL
        assert r.created_at is not None
        assert len(r.id) > 0

    def test_with_tokens(self) -> None:
        r = UsageRecord(
            user_id="u-1",
            session_id="s-1",
            model="claude-3",
            provider="anthropic",
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=200,
            total_cost=0.05,
        )
        assert r.prompt_tokens == 1000
        assert r.total_cost == 0.05


class TestSessionUsage:
    def test_defaults(self) -> None:
        su = SessionUsage(session_id="s-1", user_id="u-1")
        assert su.total_prompt_tokens == 0
        assert su.total_cost == 0.0
        assert su.llm_call_count == 0
        assert su.tokens_by_model == {}

    def test_with_data(self) -> None:
        su = SessionUsage(
            session_id="s-1",
            user_id="u-1",
            total_prompt_tokens=5000,
            total_completion_tokens=2000,
            total_cost=0.15,
            llm_call_count=10,
            tokens_by_model={"gpt-4o": 7000},
        )
        assert su.total_prompt_tokens == 5000
        assert su.llm_call_count == 10


class TestSessionMetrics:
    def test_defaults(self) -> None:
        sm = SessionMetrics(session_id="s-1", user_id="u-1")
        assert sm.tasks_completed == 0
        assert sm.error_count == 0
        assert sm.budget_consumed == 0.0
        assert sm.tool_usage_stats == {}

    def test_with_metrics(self) -> None:
        sm = SessionMetrics(
            session_id="s-1",
            user_id="u-1",
            tasks_completed=3,
            steps_executed=10,
            total_tokens_used=15000,
            tool_usage_stats={"search": 5, "browser": 3},
        )
        assert sm.tasks_completed == 3
        assert sm.tool_usage_stats["search"] == 5


class TestDailyUsageAggregate:
    def test_defaults(self) -> None:
        d = DailyUsageAggregate(user_id="u-1", date=date(2026, 3, 25))
        assert d.total_cost == 0.0
        assert d.session_count == 0
        assert d.active_sessions == []

    def test_with_data(self) -> None:
        d = DailyUsageAggregate(
            user_id="u-1",
            date=date(2026, 3, 25),
            total_prompt_tokens=50000,
            total_cost=1.50,
            llm_call_count=100,
            session_count=5,
        )
        assert d.total_prompt_tokens == 50000
        assert d.session_count == 5


class TestMonthlyUsageSummary:
    def test_defaults(self) -> None:
        m = MonthlyUsageSummary(user_id="u-1", year=2026, month=3)
        assert m.total_cost == 0.0
        assert m.total_sessions == 0
        assert m.active_days == 0

    def test_with_data(self) -> None:
        m = MonthlyUsageSummary(
            user_id="u-1",
            year=2026,
            month=3,
            total_cost=45.00,
            total_llm_calls=5000,
            total_sessions=200,
            active_days=25,
            cost_by_model={"gpt-4o": 30.00, "claude-3": 15.00},
        )
        assert m.total_cost == 45.00
        assert m.cost_by_model["gpt-4o"] == 30.00
