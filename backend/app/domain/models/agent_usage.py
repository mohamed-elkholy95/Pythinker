"""Domain models for agent usage tracking."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentRunStatus(str, Enum):
    """Lifecycle status for a single agent run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BillingStatus(str, Enum):
    """Billing confidence/source state."""

    ESTIMATED = "estimated"
    PROVIDER_REPORTED = "provider_reported"
    SELF_HOSTED = "self_hosted"


class AgentStepType(str, Enum):
    """Step categories within a run."""

    LLM = "llm"
    TOOL = "tool"
    MCP = "mcp"
    RETRIEVAL = "retrieval"
    REFLECTION = "reflection"
    VERIFICATION = "verification"


class AgentStepStatus(str, Enum):
    """Execution status for an individual agent step."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRun(BaseModel):
    """Aggregated usage for a single agent execution."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    session_id: str
    agent_id: str | None = None
    entrypoint: str | None = None
    status: AgentRunStatus = AgentRunStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    step_count: int = 0
    tool_call_count: int = 0
    mcp_call_count: int = 0
    error_count: int = 0
    total_input_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    provider_billed_cost_usd: float | None = None
    billing_status: BillingStatus = BillingStatus.ESTIMATED
    primary_model: str | None = None
    primary_provider: str | None = None

    @model_validator(mode="after")
    def _set_total_tokens(self) -> "AgentRun":
        if self.total_tokens == 0:
            self.total_tokens = self.total_input_tokens + self.total_output_tokens + self.total_reasoning_tokens
        return self


class AgentStep(BaseModel):
    """Usage and execution details for a single step inside a run."""

    step_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    run_id: str
    session_id: str
    user_id: str
    step_type: AgentStepType
    provider: str | None = None
    model: str | None = None
    tool_name: str | None = None
    mcp_server: str | None = None
    status: AgentStepStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    provider_billed_cost_usd: float | None = None
    error_type: str | None = None
    provider_usage_raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _set_total_tokens(self) -> "AgentStep":
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens + self.reasoning_tokens
        return self


class AgentUsageSummary(BaseModel):
    """Top-level aggregate usage metrics for a time window."""

    run_count: int = 0
    completed_run_count: int = 0
    failed_run_count: int = 0
    success_rate: float = 0.0
    avg_run_duration_ms: float = 0.0
    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_tool_calls: int = 0
    total_mcp_calls: int = 0
    cache_savings_estimate: float = 0.0


class AgentUsageBreakdownRow(BaseModel):
    """Grouped usage metrics for model/provider/tool/MCP breakdowns."""

    key: str
    run_count: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    avg_duration_ms: float = 0.0
    error_rate: float = 0.0


class AgentUsageTimeseriesPoint(BaseModel):
    """Chart point for agent usage trends."""

    date: datetime
    run_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    cost: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    mcp_calls: int = 0
