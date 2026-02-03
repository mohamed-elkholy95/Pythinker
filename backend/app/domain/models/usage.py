"""Usage tracking domain models for token consumption and cost tracking."""

import uuid
from datetime import UTC, date, datetime
from enum import Enum

from pydantic import BaseModel, Field


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
    tokens_by_model: dict[str, int] = {}
    cost_by_model: dict[str, float] = {}

    # Time range
    first_activity: datetime | None = None
    last_activity: datetime | None = None


class SessionMetrics(BaseModel):
    """Enhanced session metrics for monitoring dashboard.

    Aggregates performance and activity metrics beyond just token usage.
    """

    session_id: str
    user_id: str

    # Time metrics
    duration_seconds: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Task metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    steps_executed: int = 0

    # Tool usage
    tool_usage_stats: dict[str, int] = {}  # tool_name -> count
    avg_step_duration_seconds: float = 0.0

    # Performance metrics
    total_tokens_used: int = 0
    error_count: int = 0
    warning_count: int = 0
    reflection_count: int = 0
    verification_count: int = 0

    # Budget tracking (references UsageRecord)
    budget_limit: float | None = None
    budget_consumed: float = 0.0
    budget_warnings_triggered: int = 0

    # Screenshot metrics
    screenshots_captured: int = 0

    # Deliverables
    files_created: int = 0
    files_modified: int = 0

    # Updated timestamp
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    tokens_by_model: dict[str, int] = {}
    cost_by_model: dict[str, float] = {}

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
    cost_by_model: dict[str, float] = {}
