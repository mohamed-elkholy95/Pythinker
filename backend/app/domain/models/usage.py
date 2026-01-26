"""Usage tracking domain models for token consumption and cost tracking."""
from pydantic import BaseModel, Field
from datetime import datetime, date, UTC
from typing import Optional, Dict
from enum import Enum
import uuid


class UsageType(str, Enum):
    """Type of usage record"""
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    EMBEDDING = "embedding"


class UsageRecord(BaseModel):
    """Individual LLM call usage record.

    Tracks token consumption and cost for a single LLM API call.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    session_id: str

    # Model info
    model: str
    provider: str  # "openai", "anthropic", "ollama"

    # Token counts
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # For Anthropic prompt caching

    # Cost (in USD)
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0

    # Metadata
    usage_type: UsageType = UsageType.LLM_CALL
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionUsage(BaseModel):
    """Aggregated usage for a single session.

    Contains totals for all LLM calls within a session.
    """
    session_id: str
    user_id: str

    # Token totals
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0

    # Cost totals
    total_prompt_cost: float = 0.0
    total_completion_cost: float = 0.0
    total_cost: float = 0.0

    # Activity counts
    llm_call_count: int = 0
    tool_call_count: int = 0

    # Model breakdown (model -> token count)
    tokens_by_model: Dict[str, int] = {}
    cost_by_model: Dict[str, float] = {}

    # Time range
    first_activity: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class DailyUsageAggregate(BaseModel):
    """Daily usage rollup per user.

    Aggregates all usage for a user on a specific day.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    date: date  # The date this aggregate covers

    # Token totals
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0

    # Cost totals
    total_prompt_cost: float = 0.0
    total_completion_cost: float = 0.0
    total_cost: float = 0.0

    # Activity counts
    llm_call_count: int = 0
    tool_call_count: int = 0
    session_count: int = 0  # Unique sessions active this day

    # Model breakdown
    tokens_by_model: Dict[str, int] = {}
    cost_by_model: Dict[str, float] = {}

    # Sessions active this day
    active_sessions: list[str] = []

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MonthlyUsageSummary(BaseModel):
    """Monthly usage summary for billing/quota purposes."""
    user_id: str
    year: int
    month: int  # 1-12

    # Token totals
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0

    # Cost totals
    total_cost: float = 0.0

    # Activity counts
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_sessions: int = 0
    active_days: int = 0

    # Model breakdown
    cost_by_model: Dict[str, float] = {}
