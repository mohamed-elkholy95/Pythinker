"""API routes for usage tracking and statistics."""

import logging

from fastapi import APIRouter, Depends, Query

from app.application.services.usage_service import get_usage_service
from app.domain.models.user import User
from app.domain.services.usage.pricing import MODEL_PRICING
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.usage import (
    AgentRunListResponse,
    AgentRunResponse,
    AgentUsageBreakdownListResponse,
    AgentUsageBreakdownRowResponse,
    AgentUsageSummaryResponse,
    AgentUsageTimeseriesPointResponse,
    AgentUsageTimeseriesResponse,
    DailyUsageListResponse,
    DailyUsageResponse,
    ModelPricingResponse,
    MonthlyUsageDetailResponse,
    MonthlyUsageListResponse,
    MonthUsageResponse,
    PricingListResponse,
    SessionUsageResponse,
    TodayUsageResponse,
    UsageSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])

_AGENT_RANGE_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


@router.get("/summary", response_model=APIResponse[UsageSummaryResponse])
async def get_usage_summary(
    current_user: User = Depends(get_current_user),
):
    """Get usage summary for today and this month.

    Returns token counts, costs, and activity metrics for the current user.
    """
    usage_service = get_usage_service()
    summary = await usage_service.get_usage_summary(current_user.id)

    return APIResponse(
        success=True,
        data=UsageSummaryResponse(
            today=TodayUsageResponse(**summary["today"]),
            month=MonthUsageResponse(**summary["month"]),
        ),
    )


@router.get("/daily", response_model=APIResponse[DailyUsageListResponse])
async def get_daily_usage(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to retrieve"),
    current_user: User = Depends(get_current_user),
):
    """Get daily usage breakdown.

    Returns usage data for each day in the specified range.
    """
    usage_service = get_usage_service()
    daily_records = await usage_service.get_daily_usage(current_user.id, days)

    daily_responses = [
        DailyUsageResponse(
            date=record.date,
            total_prompt_tokens=record.total_prompt_tokens,
            total_completion_tokens=record.total_completion_tokens,
            total_cached_tokens=record.total_cached_tokens,
            total_cost=record.total_cost,
            llm_call_count=record.llm_call_count,
            tool_call_count=record.tool_call_count,
            tokens_by_model=record.tokens_by_model,
            cost_by_model=record.cost_by_model,
        )
        for record in daily_records
    ]

    return APIResponse(
        success=True,
        data=DailyUsageListResponse(
            days=daily_responses,
            total_days=len(daily_responses),
        ),
    )


@router.get("/monthly", response_model=APIResponse[MonthlyUsageListResponse])
async def get_monthly_usage(
    months: int = Query(default=12, ge=1, le=24, description="Number of months to retrieve"),
    current_user: User = Depends(get_current_user),
):
    """Get monthly usage summaries.

    Returns usage data aggregated by month.
    """
    usage_service = get_usage_service()
    monthly_records = await usage_service.get_monthly_summary(current_user.id, months)

    monthly_responses = [
        MonthlyUsageDetailResponse(
            year=record.year,
            month=record.month,
            total_prompt_tokens=record.total_prompt_tokens,
            total_completion_tokens=record.total_completion_tokens,
            total_cached_tokens=record.total_cached_tokens,
            total_cost=record.total_cost,
            total_llm_calls=record.total_llm_calls,
            total_tool_calls=record.total_tool_calls,
            total_sessions=record.total_sessions,
            active_days=record.active_days,
            cost_by_model=record.cost_by_model,
        )
        for record in monthly_records
    ]

    return APIResponse(
        success=True,
        data=MonthlyUsageListResponse(
            months=monthly_responses,
            total_months=len(monthly_responses),
        ),
    )


@router.get("/session/{session_id}", response_model=APIResponse[SessionUsageResponse])
async def get_session_usage(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get usage for a specific session.

    Returns token counts and costs for all LLM calls in the session.
    """
    usage_service = get_usage_service()
    session_usage = await usage_service.get_session_usage(session_id)

    # Verify the session belongs to this user
    if session_usage.user_id and session_usage.user_id != current_user.id:
        return APIResponse(
            success=False,
            error="Session not found or access denied",
        )

    return APIResponse(
        success=True,
        data=SessionUsageResponse(
            session_id=session_usage.session_id,
            total_prompt_tokens=session_usage.total_prompt_tokens,
            total_completion_tokens=session_usage.total_completion_tokens,
            total_cached_tokens=session_usage.total_cached_tokens,
            total_cost=session_usage.total_cost,
            llm_call_count=session_usage.llm_call_count,
            tool_call_count=session_usage.tool_call_count,
            tokens_by_model=session_usage.tokens_by_model,
            cost_by_model=session_usage.cost_by_model,
            first_activity=session_usage.first_activity,
            last_activity=session_usage.last_activity,
        ),
    )


@router.get("/pricing", response_model=APIResponse[PricingListResponse])
async def get_model_pricing():
    """Get pricing information for all supported models.

    Returns pricing per 1M tokens for prompt, completion, and cached tokens.
    """
    models = [
        ModelPricingResponse(
            model=model_name,
            prompt_price=pricing.prompt_price,
            completion_price=pricing.completion_price,
            cached_price=pricing.cached_price,
        )
        for model_name, pricing in MODEL_PRICING.items()
    ]

    return APIResponse(
        success=True,
        data=PricingListResponse(models=models),
    )


@router.get("/agent/summary", response_model=APIResponse[AgentUsageSummaryResponse])
async def get_agent_usage_summary(
    time_range: str = Query(default="30d", alias="range", pattern="^(7d|30d|90d)$", description="Rolling time window"),
    current_user: User = Depends(get_current_user),
):
    """Get run-aware usage summary for the selected period."""
    usage_service = get_usage_service()
    summary = await usage_service.get_agent_usage_summary(current_user.id, days=_AGENT_RANGE_DAYS[time_range])
    return APIResponse(success=True, data=AgentUsageSummaryResponse(**summary.model_dump()))


@router.get("/agent/runs", response_model=APIResponse[AgentRunListResponse])
async def get_agent_runs(
    time_range: str = Query(default="30d", alias="range", pattern="^(7d|30d|90d)$", description="Rolling time window"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum runs to return"),
    current_user: User = Depends(get_current_user),
):
    """Get recent agent runs for the selected period."""
    usage_service = get_usage_service()
    runs = await usage_service.get_recent_agent_runs(current_user.id, days=_AGENT_RANGE_DAYS[time_range], limit=limit)
    return APIResponse(
        success=True,
        data=AgentRunListResponse(
            runs=[
                AgentRunResponse(
                    run_id=run.run_id,
                    session_id=run.session_id,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    status=run.status.value,
                    duration_ms=run.duration_ms,
                    total_cost=run.estimated_cost_usd,
                    total_tokens=run.total_tokens,
                    tool_call_count=run.tool_call_count,
                    mcp_call_count=run.mcp_call_count,
                    primary_model=run.primary_model,
                    primary_provider=run.primary_provider,
                )
                for run in runs
            ],
            total_runs=len(runs),
        ),
    )


@router.get("/agent/breakdown", response_model=APIResponse[AgentUsageBreakdownListResponse])
async def get_agent_usage_breakdown(
    time_range: str = Query(default="30d", alias="range", pattern="^(7d|30d|90d)$", description="Rolling time window"),
    group_by: str = Query(
        default="model",
        pattern="^(model|provider|tool|mcp_server)$",
        description="Breakdown dimension",
    ),
    current_user: User = Depends(get_current_user),
):
    """Get grouped breakdown rows for the selected period."""
    usage_service = get_usage_service()
    rows = await usage_service.get_agent_usage_breakdown(
        current_user.id,
        days=_AGENT_RANGE_DAYS[time_range],
        group_by=group_by,
    )
    return APIResponse(
        success=True,
        data=AgentUsageBreakdownListResponse(
            rows=[AgentUsageBreakdownRowResponse(**row.model_dump()) for row in rows],
            total_rows=len(rows),
        ),
    )


@router.get("/agent/timeseries", response_model=APIResponse[AgentUsageTimeseriesResponse])
async def get_agent_usage_timeseries(
    time_range: str = Query(default="30d", alias="range", pattern="^(7d|30d|90d)$", description="Rolling time window"),
    bucket: str = Query(default="day", pattern="^(hour|day|week)$", description="Aggregation bucket"),
    current_user: User = Depends(get_current_user),
):
    """Get run-aware daily trend points for the usage chart."""
    usage_service = get_usage_service()
    points = await usage_service.get_agent_usage_timeseries(
        current_user.id,
        days=_AGENT_RANGE_DAYS[time_range],
        bucket=bucket,
    )
    return APIResponse(
        success=True,
        data=AgentUsageTimeseriesResponse(
            points=[AgentUsageTimeseriesPointResponse(**point.model_dump()) for point in points],
            total_points=len(points),
        ),
    )
