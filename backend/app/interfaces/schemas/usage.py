"""API schemas for usage tracking endpoints."""

from datetime import date, datetime

from pydantic import BaseModel


class TodayUsageResponse(BaseModel):
    """Today's usage summary."""

    tokens: int
    cost: float
    llm_calls: int
    tool_calls: int


class MonthUsageResponse(BaseModel):
    """This month's usage summary."""

    tokens: int
    cost: float
    llm_calls: int
    tool_calls: int
    sessions: int
    active_days: int


class UsageSummaryResponse(BaseModel):
    """Combined usage summary for today and this month."""

    today: TodayUsageResponse
    month: MonthUsageResponse


class DailyUsageResponse(BaseModel):
    """Daily usage breakdown."""

    date: date
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cached_tokens: int
    total_cost: float
    llm_call_count: int
    tool_call_count: int
    tokens_by_model: dict[str, int]
    cost_by_model: dict[str, float]


class DailyUsageListResponse(BaseModel):
    """List of daily usage records."""

    days: list[DailyUsageResponse]
    total_days: int


class MonthlyUsageDetailResponse(BaseModel):
    """Monthly usage detail."""

    year: int
    month: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cached_tokens: int
    total_cost: float
    total_llm_calls: int
    total_tool_calls: int
    total_sessions: int
    active_days: int
    cost_by_model: dict[str, float]


class MonthlyUsageListResponse(BaseModel):
    """List of monthly usage records."""

    months: list[MonthlyUsageDetailResponse]
    total_months: int


class SessionUsageResponse(BaseModel):
    """Usage for a specific session."""

    session_id: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cached_tokens: int
    total_cost: float
    llm_call_count: int
    tool_call_count: int
    tokens_by_model: dict[str, int]
    cost_by_model: dict[str, float]
    first_activity: datetime | None
    last_activity: datetime | None


class ModelPricingResponse(BaseModel):
    """Pricing for a single model."""

    model: str
    prompt_price: float  # Per 1M tokens
    completion_price: float  # Per 1M tokens
    cached_price: float | None  # Per 1M tokens (if available)


class PricingListResponse(BaseModel):
    """List of all model pricing."""

    models: list[ModelPricingResponse]


class AgentUsageSummaryResponse(BaseModel):
    """Run-aware usage summary for the selected period."""

    run_count: int
    completed_run_count: int
    failed_run_count: int
    success_rate: float
    avg_run_duration_ms: float
    total_cost: float
    total_input_tokens: int
    total_cached_input_tokens: int
    total_output_tokens: int
    total_reasoning_tokens: int
    total_tool_calls: int
    total_mcp_calls: int
    cache_savings_estimate: float


class AgentRunResponse(BaseModel):
    """Recent agent run row for the usage table."""

    run_id: str
    session_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    duration_ms: float | None
    total_cost: float
    total_tokens: int
    tool_call_count: int
    mcp_call_count: int
    primary_model: str | None
    primary_provider: str | None


class AgentRunListResponse(BaseModel):
    """List wrapper for recent agent runs."""

    runs: list[AgentRunResponse]
    total_runs: int


class AgentUsageBreakdownRowResponse(BaseModel):
    """Breakdown row grouped by model/provider/tool/MCP server."""

    key: str
    run_count: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost: float
    avg_duration_ms: float
    error_rate: float


class AgentUsageBreakdownListResponse(BaseModel):
    """List wrapper for grouped agent usage breakdowns."""

    rows: list[AgentUsageBreakdownRowResponse]
    total_rows: int


class AgentUsageTimeseriesPointResponse(BaseModel):
    """Daily trend point for the usage chart."""

    date: datetime
    run_count: int
    success_count: int
    failed_count: int
    cost: float
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    tool_calls: int
    mcp_calls: int


class AgentUsageTimeseriesResponse(BaseModel):
    """List wrapper for agent usage trend points."""

    points: list[AgentUsageTimeseriesPointResponse]
    total_points: int
