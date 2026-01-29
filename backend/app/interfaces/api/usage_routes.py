"""API routes for usage tracking and statistics."""
import logging

from fastapi import APIRouter, Depends, Query

from app.application.services.usage_service import get_usage_service
from app.domain.models.user import User
from app.domain.services.usage.pricing import MODEL_PRICING
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.usage import (
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
