"""
Agent Event Sourcing - Immutable append-only event log.

All agent execution actions become events in an immutable log.
Current state is derived from event projections.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentEventType(StrEnum):
    """Agent event types for event sourcing."""

    # Planning events
    PLAN_CREATED = "plan_created"
    PLAN_VALIDATED = "plan_validated"
    PLAN_VERIFIED = "plan_verified"
    PLAN_REJECTED = "plan_rejected"

    # Execution events
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"

    # Tool events
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"

    # Model selection events
    MODEL_SELECTED = "model_selected"
    MODEL_SWITCHED = "model_switched"

    # Verification events
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"

    # Task lifecycle events
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"

    # Memory events
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_STORED = "memory_stored"

    # Context events
    CONTEXT_UPDATED = "context_updated"
    FILE_TRACKED = "file_tracked"


class AgentEvent(BaseModel):
    """
    Base agent event for event sourcing.

    All events are immutable and append-only.
    """

    event_id: str = Field(description="Unique event ID")
    event_type: AgentEventType = Field(description="Event type")
    session_id: str = Field(description="Session ID")
    task_id: str = Field(description="Task ID")
    sequence: int = Field(description="Monotonic sequence number for ordering")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Event payload (type depends on event_type)
    payload: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = True  # Immutable


# Specific event types with typed payloads


class PlanCreatedEvent(AgentEvent):
    """Plan created event."""

    event_type: AgentEventType = AgentEventType.PLAN_CREATED
    plan_id: str
    steps_count: int
    estimated_duration_seconds: int | None = None


class StepStartedEvent(AgentEvent):
    """Step execution started."""

    event_type: AgentEventType = AgentEventType.STEP_STARTED
    step_id: str
    step_type: str
    step_description: str


class StepCompletedEvent(AgentEvent):
    """Step execution completed."""

    event_type: AgentEventType = AgentEventType.STEP_COMPLETED
    step_id: str
    duration_seconds: float
    output_size_bytes: int | None = None


class ToolCalledEvent(AgentEvent):
    """Tool invocation started."""

    event_type: AgentEventType = AgentEventType.TOOL_CALLED
    tool_name: str
    tool_args: dict[str, Any]


class ToolResultEvent(AgentEvent):
    """Tool invocation completed."""

    event_type: AgentEventType = AgentEventType.TOOL_RESULT
    tool_name: str
    result_size_bytes: int
    duration_seconds: float
    success: bool


class ModelSelectedEvent(AgentEvent):
    """Model tier selected for step."""

    event_type: AgentEventType = AgentEventType.MODEL_SELECTED
    model_name: str
    model_tier: str  # FAST, BALANCED, POWERFUL
    complexity_score: float
    estimated_tokens: int | None = None


class TaskCompletedEvent(AgentEvent):
    """Task completed."""

    event_type: AgentEventType = AgentEventType.TASK_COMPLETED
    total_duration_seconds: float
    total_steps: int
    total_tools_called: int
    total_tokens_used: int | None = None
    total_cost_usd: float | None = None
