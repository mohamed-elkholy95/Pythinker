"""API schemas for usage tracking endpoints."""
from typing import List, Dict, Optional
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
    tokens_by_model: Dict[str, int]
    cost_by_model: Dict[str, float]


class DailyUsageListResponse(BaseModel):
    """List of daily usage records."""
    days: List[DailyUsageResponse]
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
    cost_by_model: Dict[str, float]


class MonthlyUsageListResponse(BaseModel):
    """List of monthly usage records."""
    months: List[MonthlyUsageDetailResponse]
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
    tokens_by_model: Dict[str, int]
    cost_by_model: Dict[str, float]
    first_activity: Optional[datetime]
    last_activity: Optional[datetime]


class ModelPricingResponse(BaseModel):
    """Pricing for a single model."""
    model: str
    prompt_price: float  # Per 1M tokens
    completion_price: float  # Per 1M tokens
    cached_price: Optional[float]  # Per 1M tokens (if available)


class PricingListResponse(BaseModel):
    """List of all model pricing."""
    models: List[ModelPricingResponse]
