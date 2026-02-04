"""Domain port for distributed tracing.

This module provides an abstraction layer for tracing, following DDD principles
by keeping infrastructure concerns (OpenTelemetry) out of the domain layer.

The TracerPort protocol defines what the domain needs from tracing, while
infrastructure adapters (in app.infrastructure.observability) provide the
actual implementations.

Usage:
    # In domain services
    from app.domain.external.tracing import get_tracer, SpanKind

    tracer = get_tracer()
    with tracer.trace("operation-name", agent_id="agent-123") as ctx:
        with ctx.span("sub-operation", SpanKind.CLIENT) as span:
            span.set_attribute("key", "value")
            # Do work...

Pattern:
    This follows the Ports and Adapters (Hexagonal Architecture) pattern:
    - Domain defines the port (this file)
    - Infrastructure provides adapters that implement the port
    - Domain services depend only on the port interface
"""

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from typing import Any, Protocol


class SpanKind(Enum):
    """Type of span in distributed tracing.

    Standard OpenTelemetry span kinds plus domain-specific kinds for
    agent workflow tracing.
    """

    # Standard OpenTelemetry kinds
    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"
    PRODUCER = "producer"
    CONSUMER = "consumer"

    # Domain-specific span kinds for agent workflows
    PLAN_CREATE = "plan_create"
    PLAN_UPDATE = "plan_update"
    AGENT_STEP = "agent_step"
    FLOW_STATE = "flow_state"
    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    ERROR_RECOVERY = "error_recovery"


class SpanProtocol(Protocol):
    """Protocol for span operations.

    Spans represent units of work within the tracing system. They can record
    attributes, events, and exceptions that occurred during the operation.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span.

        Args:
            key: Attribute name
            value: Attribute value (should be serializable)
        """
        ...

    def record_exception(self, exception: BaseException) -> None:
        """Record an exception that occurred during the span.

        Args:
            exception: The exception to record
        """
        ...


class TraceContextProtocol(Protocol):
    """Protocol for trace context operations.

    A trace context represents an active trace and allows creating nested spans.
    """

    @contextmanager
    def span(
        self, name: str, kind: SpanKind = SpanKind.INTERNAL, **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Create a child span within this trace context.

        Args:
            name: Human-readable name for the span
            kind: Type of span
            **attributes: Initial attributes to set on the span

        Yields:
            SpanProtocol for the new span
        """
        ...


class TracerPort(ABC):
    """Abstract port for tracing operations.

    Domain services depend on this abstraction rather than concrete
    infrastructure implementations like OpenTelemetry or custom tracers.

    This port provides two main entry points:
    - start_span(): For simple span creation
    - trace(): For creating a trace context that supports nested spans
    """

    @abstractmethod
    @contextmanager
    def start_span(
        self, name: str, kind: SpanKind = SpanKind.INTERNAL, **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Start a new span.

        This is a simple entry point for creating spans without a full trace context.

        Args:
            name: Human-readable name for the span
            kind: Type of span (internal, client, server, etc.)
            **attributes: Initial attributes to set on the span

        Yields:
            SpanProtocol for the new span
        """
        ...

    @abstractmethod
    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[TraceContextProtocol, None, None]:
        """Start a new trace with a root span.

        This creates a trace context that supports nested span creation.

        Args:
            name: Name for the trace/root span
            agent_id: Optional agent identifier for correlation
            session_id: Optional session identifier for correlation
            attributes: Initial attributes for the root span

        Yields:
            TraceContextProtocol for managing spans within the trace
        """
        ...


class NullSpan:
    """No-op span implementation.

    Used when tracing is disabled or in tests where tracing is not needed.
    All operations are no-ops that accept arguments without side effects.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op: accepts attribute without storing it."""
        pass

    def record_exception(self, exception: BaseException) -> None:
        """No-op: accepts exception without recording it."""
        pass


class NullTraceContext:
    """No-op trace context implementation.

    Provides a null implementation of TraceContextProtocol for use when
    tracing is disabled.
    """

    @contextmanager
    def span(
        self, name: str, kind: SpanKind = SpanKind.INTERNAL, **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Return a no-op span."""
        yield NullSpan()


class NullTracer(TracerPort):
    """No-op tracer for testing and when tracing is disabled.

    This implementation satisfies the TracerPort interface but performs
    no actual tracing. Use this as a default when tracing infrastructure
    is not configured.
    """

    @contextmanager
    def start_span(
        self, name: str, kind: SpanKind = SpanKind.INTERNAL, **attributes: Any
    ) -> Generator[SpanProtocol, None, None]:
        """Return a no-op span."""
        yield NullSpan()

    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[TraceContextProtocol, None, None]:
        """Return a no-op trace context."""
        yield NullTraceContext()


# Module-level default instance
_tracer: TracerPort = NullTracer()


def get_tracer() -> TracerPort:
    """Get the current tracer instance.

    Returns the configured tracer or a NullTracer if none is configured.
    Domain services should use this function to access tracing.

    Returns:
        TracerPort implementation
    """
    return _tracer


def set_tracer(tracer: TracerPort) -> None:
    """Set the tracer instance (for dependency injection).

    This should be called during application startup to inject the
    infrastructure tracer implementation.

    Args:
        tracer: TracerPort implementation to use globally
    """
    global _tracer
    _tracer = tracer
