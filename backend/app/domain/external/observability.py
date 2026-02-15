"""Observability Port - Domain Interface for Metrics and Tracing.

This port defines the interface for observability operations that domain
services can use without depending on infrastructure implementations.

The actual implementation is provided by infrastructure adapters that
implement these protocols (e.g., Prometheus, OpenTelemetry).

Usage:
    # In domain service constructors
    def __init__(self, metrics: MetricsPort | None = None):
        self._metrics = metrics or get_null_metrics()

    # In domain service code
    self._metrics.record_event("task_completed", {"task_id": "123"})

Pattern:
    This follows the Ports and Adapters (Hexagonal Architecture) pattern:
    - Domain defines the port (this file)
    - Infrastructure provides adapters that implement the port
    - Domain services depend only on the port interface
"""

from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsPort(Protocol):
    """Protocol for recording metrics.

    Domain services should depend on this protocol, not concrete
    implementations like prometheus_metrics.
    """

    def record_event(self, event_type: str, labels: dict[str, str] | None = None) -> None:
        """Record a generic event metric.

        Args:
            event_type: Type of event (e.g., "task_completed", "error_occurred")
            labels: Optional labels/tags for the metric
        """
        ...

    def increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter by 1. Convenience method used by DeepCode integrations."""
        ...

    def record_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Counter name
            value: Value to increment by (default 1.0)
            labels: Optional labels/tags
        """
        ...

    def record_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Gauge name
            value: Current value
            labels: Optional labels/tags
        """
        ...

    def record_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a value in a histogram.

        Args:
            name: Histogram name
            value: Observed value
            labels: Optional labels/tags
        """
        ...

    # Domain-specific metric methods
    def record_reward_hacking_signal(self, signal_type: str, severity: str) -> None:
        """Record a reward hacking detection signal.

        Args:
            signal_type: Type of signal detected
            severity: Severity level (low, medium, high)
        """
        ...

    def record_plan_verification(self, status: str) -> None:
        """Record plan verification result.

        Args:
            status: Verification status (pass, revise, fail, skip, error)
        """
        ...

    def record_failure_prediction(self, prediction: str, confidence: float) -> None:
        """Record a failure prediction.

        Args:
            prediction: Predicted failure type
            confidence: Confidence score (0-1)
        """
        ...

    def record_error(self, error_type: str, message: str) -> None:
        """Record an error occurrence.

        Args:
            error_type: Category of error
            message: Error message
        """
        ...

    def update_token_budget(self, used: int, remaining: int) -> None:
        """Update token budget gauge.

        Args:
            used: Tokens used
            remaining: Tokens remaining
        """
        ...

    def record_tool_trace_anomaly(self, tool_name: str, anomaly_type: str) -> None:
        """Record a tool trace anomaly.

        Args:
            tool_name: Name of the tool
            anomaly_type: Type of anomaly detected
        """
        ...

    def record_reflection_check(self, status: str) -> None:
        """Record a reflection check.

        Args:
            status: Check status (triggered, skipped)
        """
        ...

    def record_reflection_decision(self, decision: str) -> None:
        """Record a reflection decision.

        Args:
            decision: Decision made (continue, adjust, replan, escalate)
        """
        ...

    def record_reflection_trigger(self, trigger_type: str) -> None:
        """Record what triggered a reflection.

        Args:
            trigger_type: Type of trigger (progress_stall, high_error_rate, etc.)
        """
        ...

    def update_llm_concurrent_requests(self, active: int) -> None:
        """Update LLM concurrent requests gauge.

        Args:
            active: Number of active concurrent requests
        """
        ...

    def update_llm_queue_waiting(self, waiting: int) -> None:
        """Update LLM queue waiting count gauge.

        Args:
            waiting: Number of requests waiting in queue
        """
        ...


@runtime_checkable
class SpanContext(Protocol):
    """Protocol for a tracing span context."""

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        ...

    def set_status(self, status: str, message: str | None = None) -> None:
        """Set the span status."""
        ...

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        ...

    def end(self) -> None:
        """End the span."""
        ...


@runtime_checkable
class TraceContextPort(Protocol):
    """Protocol for a trace context that can create child spans.

    This represents an active trace that can have nested spans created within it.
    Domain services use this to create hierarchical tracing structures.
    """

    @contextmanager
    def span(
        self,
        name: str,
        kind: str = "internal",
        attributes: dict[str, Any] | None = None,
    ):
        """Create a child span within this trace context.

        Args:
            name: Human-readable name for the span
            kind: Type of span (internal, plan_create, agent_step, etc.)
            attributes: Initial attributes to set

        Yields:
            SpanContext for the child span
        """
        ...


@runtime_checkable
class TracerPort(Protocol):
    """Protocol for distributed tracing.

    Domain services should depend on this protocol for tracing
    operations instead of importing infrastructure directly.
    """

    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        """Start a new trace.

        Args:
            name: Name for the trace
            agent_id: Optional agent identifier
            session_id: Optional session identifier
            attributes: Initial attributes

        Yields:
            TraceContextPort for managing spans within the trace
        """
        ...

    @contextmanager
    def start_span(self, name: str, kind: str = "internal") -> SpanContext:
        """Start a new span.

        Args:
            name: Span name
            kind: Span kind (internal, client, server, producer, consumer)

        Yields:
            SpanContext for the new span
        """
        ...

    def get_current_span(self) -> SpanContext | None:
        """Get the current active span."""
        ...


# ===== Null Implementations =====


class NullMetrics:
    """Null implementation of MetricsPort that does nothing.

    Use this when metrics are not configured or in tests.
    """

    def record_event(self, event_type: str, labels: dict[str, str] | None = None) -> None:
        pass

    def increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter by 1. Used by DeepCode integrations."""
        pass

    def record_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        pass

    def record_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        pass

    def record_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        pass

    def record_reward_hacking_signal(self, signal_type: str, severity: str) -> None:
        pass

    def record_plan_verification(self, status: str) -> None:
        pass

    def record_failure_prediction(self, prediction: str, confidence: float) -> None:
        pass

    def record_error(self, error_type: str, message: str) -> None:
        pass

    def update_token_budget(self, used: int, remaining: int) -> None:
        pass

    def record_tool_trace_anomaly(self, tool_name: str, anomaly_type: str) -> None:
        pass

    def record_reflection_check(self, status: str) -> None:
        pass

    def record_reflection_decision(self, decision: str) -> None:
        pass

    def record_reflection_trigger(self, trigger_type: str) -> None:
        pass

    def update_llm_concurrent_requests(self, active: int) -> None:
        pass

    def update_llm_queue_waiting(self, waiting: int) -> None:
        pass


class NullSpanContext:
    """Null implementation of SpanContext."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: str, message: str | None = None) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def end(self) -> None:
        pass


class NullTraceContext:
    """Null implementation of TraceContextPort."""

    @contextmanager
    def span(
        self,
        name: str,
        kind: str = "internal",
        attributes: dict[str, Any] | None = None,
    ):
        yield NullSpanContext()


class NullTracer:
    """Null implementation of TracerPort that does nothing.

    Use this when tracing is not configured or in tests.
    """

    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        yield NullTraceContext()

    @contextmanager
    def start_span(self, name: str, kind: str = "internal") -> SpanContext:
        yield NullSpanContext()

    def get_current_span(self) -> SpanContext | None:
        return None


# ===== Singleton Accessors =====

_null_metrics: NullMetrics | None = None
_null_tracer: NullTracer | None = None


def get_null_metrics() -> NullMetrics:
    """Get singleton null metrics instance."""
    global _null_metrics
    if _null_metrics is None:
        _null_metrics = NullMetrics()
    return _null_metrics


def get_null_tracer() -> NullTracer:
    """Get singleton null tracer instance."""
    global _null_tracer
    if _null_tracer is None:
        _null_tracer = NullTracer()
    return _null_tracer


# ===== Module-level Metrics Singleton =====

_metrics: MetricsPort | None = None


def set_metrics(metrics: MetricsPort) -> None:
    """Set the global metrics instance.

    This should be called during application startup to inject the
    infrastructure metrics implementation.

    Args:
        metrics: MetricsPort implementation to use globally
    """
    global _metrics
    _metrics = metrics


def get_metrics() -> MetricsPort:
    """Get the global metrics instance.

    Returns the configured metrics or a null metrics if none is configured.
    Domain services should use this function to access metrics.

    Returns:
        MetricsPort implementation
    """
    global _metrics
    if _metrics is None:
        return get_null_metrics()
    return _metrics


# ===== Module-level Tracer Singleton =====

_tracer: TracerPort | None = None


def set_tracer(tracer: TracerPort) -> None:
    """Set the global tracer instance.

    This should be called during application startup to inject the
    infrastructure tracer implementation.

    Args:
        tracer: TracerPort implementation to use globally
    """
    global _tracer
    _tracer = tracer


def get_tracer() -> TracerPort:
    """Get the global tracer instance.

    Returns the configured tracer or a null tracer if none is configured.
    Domain services should use this function to access tracing.

    Returns:
        TracerPort implementation
    """
    global _tracer
    if _tracer is None:
        return get_null_tracer()
    return _tracer
