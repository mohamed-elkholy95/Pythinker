"""
Event Projection Service - Derive current state from immutable event log.

Projections are materialized views built from events.
Projections can have TTL (events cannot).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.models.agent_event import AgentEvent, AgentEventType

logger = logging.getLogger(__name__)


@dataclass
class SessionStateProjection:
    """Current session state derived from events."""

    session_id: str
    task_id: str | None
    status: str  # INITIALIZING, PLANNING, EXECUTING, COMPLETED, FAILED
    current_step_id: str | None
    total_steps: int
    completed_steps: int
    failed_steps: int
    total_tools_called: int
    total_tokens_used: int
    total_cost_usd: float
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None

    # Progress indicators
    progress_percentage: float
    current_phase: str  # PLANNING, EXECUTION, VERIFICATION, SUMMARIZATION

    # Last updated timestamp
    updated_at: datetime


@dataclass
class CostAnalyticsProjection:
    """Cost analytics derived from model selection events."""

    session_id: str
    total_cost_usd: float
    breakdown_by_model: dict[str, float]  # model_name -> cost
    breakdown_by_tier: dict[str, float]  # tier -> cost
    total_tokens: int
    breakdown_tokens: dict[str, int]  # model_name -> tokens


@dataclass
class ToolEffectivenessProjection:
    """Tool effectiveness metrics derived from tool events."""

    session_id: str
    tool_name: str
    total_calls: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_seconds: float
    total_duration_seconds: float


class EventProjectionService:
    """
    Service for building projections from immutable event log.

    Projections are derived views that can be cached and have TTL.
    The event log is the source of truth (NO TTL).
    """

    def __init__(self):
        pass

    def build_session_state(self, events: list[AgentEvent]) -> SessionStateProjection:
        """
        Build current session state from events.

        Args:
            events: List of events for session (ordered by sequence)

        Returns:
            Current session state
        """
        if not events:
            raise ValueError("No events provided")

        session_id = events[0].session_id
        task_id = None
        status = "INITIALIZING"
        current_step_id = None
        total_steps = 0
        completed_steps = 0
        failed_steps = 0
        total_tools_called = 0
        total_tokens_used = 0
        total_cost_usd = 0.0
        started_at = None
        completed_at = None
        current_phase = "INITIALIZING"

        for event in events:
            if event.event_type == AgentEventType.TASK_STARTED:
                task_id = event.task_id
                status = "RUNNING"
                started_at = event.timestamp

            elif event.event_type == AgentEventType.PLAN_CREATED:
                total_steps = event.payload.get("steps_count", 0)
                current_phase = "PLANNING"

            elif event.event_type == AgentEventType.STEP_STARTED:
                current_step_id = event.payload.get("step_id")
                current_phase = "EXECUTION"

            elif event.event_type == AgentEventType.STEP_COMPLETED:
                completed_steps += 1
                current_step_id = None

            elif event.event_type == AgentEventType.STEP_FAILED:
                failed_steps += 1
                current_step_id = None

            elif event.event_type == AgentEventType.TOOL_CALLED:
                total_tools_called += 1

            elif event.event_type == AgentEventType.MODEL_SELECTED:
                total_tokens_used += event.payload.get("estimated_tokens", 0)

            elif event.event_type == AgentEventType.TASK_COMPLETED:
                status = "COMPLETED"
                completed_at = event.timestamp
                total_cost_usd = event.payload.get("total_cost_usd", 0.0)
                total_tokens_used = event.payload.get("total_tokens_used", total_tokens_used)

            elif event.event_type == AgentEventType.TASK_FAILED:
                status = "FAILED"
                completed_at = event.timestamp

            elif event.event_type == AgentEventType.TASK_CANCELLED:
                status = "CANCELLED"
                completed_at = event.timestamp

        # Calculate duration
        duration_seconds = None
        if started_at and completed_at:
            duration_seconds = (completed_at - started_at).total_seconds()

        # Calculate progress
        progress_percentage = 0.0
        if total_steps > 0:
            progress_percentage = (completed_steps / total_steps) * 100

        return SessionStateProjection(
            session_id=session_id,
            task_id=task_id,
            status=status,
            current_step_id=current_step_id,
            total_steps=total_steps,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            total_tools_called=total_tools_called,
            total_tokens_used=total_tokens_used,
            total_cost_usd=total_cost_usd,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            progress_percentage=progress_percentage,
            current_phase=current_phase,
            updated_at=datetime.now(UTC),
        )

    def build_cost_analytics(self, events: list[AgentEvent]) -> CostAnalyticsProjection:
        """
        Build cost analytics from model selection events.

        Args:
            events: List of events for session

        Returns:
            Cost analytics projection
        """
        session_id = events[0].session_id if events else ""
        total_cost_usd = 0.0
        breakdown_by_model: dict[str, float] = {}
        breakdown_by_tier: dict[str, float] = {}
        total_tokens = 0
        breakdown_tokens: dict[str, int] = {}

        for event in events:
            if event.event_type == AgentEventType.MODEL_SELECTED:
                model_name = event.payload.get("model_name", "unknown")
                tier = event.payload.get("model_tier", "BALANCED")
                tokens = event.payload.get("estimated_tokens", 0)

                # Simplified cost calculation (should use actual pricing)
                cost_per_token = {
                    "FAST": 0.00001,  # $0.01 per 1K tokens
                    "BALANCED": 0.00003,  # $0.03 per 1K tokens
                    "POWERFUL": 0.00015,  # $0.15 per 1K tokens
                }.get(tier, 0.00003)

                cost = tokens * cost_per_token

                total_cost_usd += cost
                total_tokens += tokens

                breakdown_by_model[model_name] = breakdown_by_model.get(model_name, 0.0) + cost
                breakdown_by_tier[tier] = breakdown_by_tier.get(tier, 0.0) + cost
                breakdown_tokens[model_name] = breakdown_tokens.get(model_name, 0) + tokens

        return CostAnalyticsProjection(
            session_id=session_id,
            total_cost_usd=total_cost_usd,
            breakdown_by_model=breakdown_by_model,
            breakdown_by_tier=breakdown_by_tier,
            total_tokens=total_tokens,
            breakdown_tokens=breakdown_tokens,
        )

    def build_tool_effectiveness(self, events: list[AgentEvent], tool_name: str) -> ToolEffectivenessProjection:
        """
        Build tool effectiveness metrics from tool events.

        Args:
            events: List of events for session
            tool_name: Tool name to analyze

        Returns:
            Tool effectiveness projection
        """
        session_id = events[0].session_id if events else ""
        total_calls = 0
        success_count = 0
        failure_count = 0
        total_duration = 0.0

        for event in events:
            if event.event_type == AgentEventType.TOOL_RESULT and event.payload.get("tool_name") == tool_name:
                total_calls += 1
                duration = event.payload.get("duration_seconds", 0.0)
                total_duration += duration

                if event.payload.get("success", False):
                    success_count += 1
                else:
                    failure_count += 1

        success_rate = (success_count / total_calls) if total_calls > 0 else 0.0
        avg_duration = (total_duration / total_calls) if total_calls > 0 else 0.0

        return ToolEffectivenessProjection(
            session_id=session_id,
            tool_name=tool_name,
            total_calls=total_calls,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            avg_duration_seconds=avg_duration,
            total_duration_seconds=total_duration,
        )
