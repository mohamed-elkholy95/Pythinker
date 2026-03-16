"""Span definitions for distributed tracing.

Spans represent units of work within the agent system, providing visibility into:
- LLM calls and their token usage
- Tool executions and results
- Flow state transitions
- Error contexts

Designed to be compatible with OpenTelemetry semantics for future integration.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SpanKind(str, Enum):
    """Type of span being traced."""

    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    FLOW_STATE = "flow_state"
    AGENT_STEP = "agent_step"
    PLAN_CREATE = "plan_create"
    PLAN_UPDATE = "plan_update"
    MEMORY_OPERATION = "memory_operation"
    ERROR_RECOVERY = "error_recovery"
    INTERNAL = "internal"


class SpanStatus(str, Enum):
    """Status of a span."""

    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class SpanEvent:
    """An event that occurred during a span's lifetime."""

    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    """Token usage information for LLM calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class Span:
    """A unit of work in the tracing system.

    Spans can be nested to represent parent-child relationships between
    operations. Each span captures timing, attributes, and events.

    Attributes:
        span_id: Unique identifier for this span
        trace_id: Identifier for the overall trace
        parent_span_id: ID of the parent span (if nested)
        name: Human-readable name describing the operation
        kind: Type of operation (LLM call, tool execution, etc.)
        start_time: When the span started (unix timestamp)
        end_time: When the span ended (unix timestamp)
        status: Final status of the span
        status_message: Description if status is ERROR
        attributes: Key-value pairs describing the span
        events: List of events that occurred during the span
        token_usage: Token usage if this is an LLM call span
    """

    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    trace_id: str = ""
    parent_span_id: str | None = None
    name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: SpanStatus = SpanStatus.UNSET
    status_message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    token_usage: TokenUsage | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a single attribute on the span."""
        self.attributes[key] = value

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """Set multiple attributes on the span."""
        self.attributes.update(attributes)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span timeline."""
        self.events.append(SpanEvent(name=name, attributes=attributes or {}))

    def set_status(self, status: SpanStatus, message: str | None = None) -> None:
        """Set the span's final status."""
        self.status = status
        if message:
            self.status_message = message

    def set_token_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0, cached_tokens: int = 0) -> None:
        """Record token usage for an LLM call span."""
        self.token_usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cached_tokens=cached_tokens,
        )

    def end(self, status: SpanStatus | None = None) -> None:
        """Mark the span as ended."""
        self.end_time = time.time()
        if status:
            self.status = status
        elif self.status == SpanStatus.UNSET:
            self.status = SpanStatus.OK

    @property
    def duration_ms(self) -> float | None:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for serialization."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "status_message": self.status_message,
            "attributes": self.attributes,
            "events": [{"name": e.name, "timestamp": e.timestamp, "attributes": e.attributes} for e in self.events],
            "token_usage": {
                "prompt_tokens": self.token_usage.prompt_tokens,
                "completion_tokens": self.token_usage.completion_tokens,
                "total_tokens": self.token_usage.total_tokens,
                "cached_tokens": self.token_usage.cached_tokens,
            }
            if self.token_usage
            else None,
        }


def create_llm_span(trace_id: str, name: str, model: str, parent_span_id: str | None = None) -> Span:
    """Create a span for an LLM call."""
    span = Span(trace_id=trace_id, parent_span_id=parent_span_id, name=name, kind=SpanKind.LLM_CALL)
    span.set_attribute("llm.model", model)
    return span


def create_tool_span(trace_id: str, tool_name: str, function_name: str, parent_span_id: str | None = None) -> Span:
    """Create a span for a tool execution."""
    span = Span(
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        name=f"tool:{tool_name}.{function_name}",
        kind=SpanKind.TOOL_EXECUTION,
    )
    span.set_attributes({"tool.name": tool_name, "tool.function": function_name})
    return span


def create_flow_span(trace_id: str, state: str, parent_span_id: str | None = None) -> Span:
    """Create a span for a flow state transition."""
    span = Span(trace_id=trace_id, parent_span_id=parent_span_id, name=f"flow:{state}", kind=SpanKind.FLOW_STATE)
    span.set_attribute("flow.state", state)
    return span
