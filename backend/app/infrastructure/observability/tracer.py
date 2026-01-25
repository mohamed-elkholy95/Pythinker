"""Tracer implementation for agent observability.

The Tracer class provides a high-level interface for creating and managing spans,
collecting metrics, and exporting trace data. It's designed as a foundation that
can be extended to integrate with external observability platforms.

Usage:
    tracer = get_tracer()

    # Start a trace for an agent session
    with tracer.trace("agent-run", agent_id="agent-123") as trace_ctx:

        # Create nested spans
        with trace_ctx.span("planning", kind=SpanKind.PLAN_CREATE) as span:
            # Do planning work
            span.set_attribute("plan.steps", 5)

        with trace_ctx.span("execution", kind=SpanKind.AGENT_STEP) as span:
            # Execute steps
            span.set_token_usage(prompt_tokens=100, completion_tokens=50)
"""

import time
import uuid
import logging
import asyncio
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager, asynccontextmanager
from collections import defaultdict

from app.infrastructure.observability.spans import (
    Span,
    SpanKind,
    SpanStatus,
    TokenUsage,
    create_llm_span,
    create_tool_span,
    create_flow_span,
)


logger = logging.getLogger(__name__)


@dataclass
class TraceMetrics:
    """Aggregated metrics for a trace."""
    total_spans: int = 0
    total_duration_ms: float = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    error_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_spans": self.total_spans,
            "total_duration_ms": self.total_duration_ms,
            "llm_call_count": self.llm_call_count,
            "tool_call_count": self.tool_call_count,
            "error_count": self.error_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class TraceContext:
    """Context for an active trace, providing span creation and management."""

    trace_id: str
    root_span: Span
    spans: List[Span] = field(default_factory=list)
    _current_span: Optional[Span] = None
    _tracer: Optional["Tracer"] = None

    def __post_init__(self):
        self.spans.append(self.root_span)
        self._current_span = self.root_span

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """Create a child span within this trace context.

        Args:
            name: Human-readable name for the span
            kind: Type of span
            attributes: Initial attributes to set

        Yields:
            The created Span object
        """
        parent_span_id = self._current_span.span_id if self._current_span else None

        span = Span(
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind
        )

        if attributes:
            span.set_attributes(attributes)

        # Push onto span stack
        old_current = self._current_span
        self._current_span = span
        self.spans.append(span)

        try:
            yield span
            span.end(SpanStatus.OK)
        except Exception as e:
            span.set_status(SpanStatus.ERROR, str(e))
            span.end()
            raise
        finally:
            self._current_span = old_current

    @asynccontextmanager
    async def span_async(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """Async version of span context manager."""
        with self.span(name, kind, attributes) as span:
            yield span

    def llm_span(self, name: str, model: str):
        """Create a span specifically for LLM calls."""
        return self.span(name, SpanKind.LLM_CALL, {"llm.model": model})

    def tool_span(self, tool_name: str, function_name: str):
        """Create a span specifically for tool executions."""
        return self.span(
            f"tool:{tool_name}.{function_name}",
            SpanKind.TOOL_EXECUTION,
            {"tool.name": tool_name, "tool.function": function_name}
        )

    def flow_span(self, state: str):
        """Create a span for flow state transitions."""
        return self.span(f"flow:{state}", SpanKind.FLOW_STATE, {"flow.state": state})

    @property
    def current_span(self) -> Optional[Span]:
        """Get the currently active span."""
        return self._current_span

    def get_metrics(self) -> TraceMetrics:
        """Calculate metrics from all spans in this trace."""
        metrics = TraceMetrics()

        for span in self.spans:
            metrics.total_spans += 1

            if span.duration_ms:
                metrics.total_duration_ms += span.duration_ms

            if span.kind == SpanKind.LLM_CALL:
                metrics.llm_call_count += 1
            elif span.kind == SpanKind.TOOL_EXECUTION:
                metrics.tool_call_count += 1

            if span.status == SpanStatus.ERROR:
                metrics.error_count += 1

            if span.token_usage:
                metrics.total_prompt_tokens += span.token_usage.prompt_tokens
                metrics.total_completion_tokens += span.token_usage.completion_tokens
                metrics.total_cached_tokens += span.token_usage.cached_tokens

        return metrics

    def end(self) -> None:
        """End the trace and its root span."""
        self.root_span.end()
        if self._tracer:
            self._tracer._on_trace_end(self)


class Tracer:
    """Central tracer for managing traces and spans.

    The tracer maintains active traces and can export completed traces
    to various backends (logs, files, external services).
    """

    def __init__(
        self,
        service_name: str = "pythinker-agent",
        export_to_log: bool = True,
        on_trace_complete: Optional[Callable[[TraceContext], None]] = None
    ):
        """Initialize the tracer.

        Args:
            service_name: Name of the service for trace identification
            export_to_log: Whether to log completed traces
            on_trace_complete: Callback for custom trace processing
        """
        self.service_name = service_name
        self.export_to_log = export_to_log
        self.on_trace_complete = on_trace_complete
        self._active_traces: Dict[str, TraceContext] = {}
        self._completed_traces: List[TraceContext] = []
        self._metrics_by_agent: Dict[str, TraceMetrics] = defaultdict(TraceMetrics)

    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """Start a new trace.

        Args:
            name: Name for the trace
            agent_id: Optional agent identifier
            session_id: Optional session identifier
            attributes: Initial attributes

        Yields:
            TraceContext for managing spans within the trace
        """
        trace_id = str(uuid.uuid4())

        root_span = Span(
            trace_id=trace_id,
            name=name,
            kind=SpanKind.INTERNAL
        )

        root_span.set_attribute("service.name", self.service_name)
        if agent_id:
            root_span.set_attribute("agent.id", agent_id)
        if session_id:
            root_span.set_attribute("session.id", session_id)
        if attributes:
            root_span.set_attributes(attributes)

        trace_ctx = TraceContext(
            trace_id=trace_id,
            root_span=root_span,
            _tracer=self
        )

        self._active_traces[trace_id] = trace_ctx

        try:
            yield trace_ctx
        finally:
            trace_ctx.end()

    def _on_trace_end(self, trace_ctx: TraceContext) -> None:
        """Handle trace completion."""
        trace_id = trace_ctx.trace_id

        # Remove from active
        if trace_id in self._active_traces:
            del self._active_traces[trace_id]

        # Store in completed (with limit)
        self._completed_traces.append(trace_ctx)
        if len(self._completed_traces) > 100:
            self._completed_traces = self._completed_traces[-50:]

        # Update agent metrics
        agent_id = trace_ctx.root_span.attributes.get("agent.id")
        if agent_id:
            trace_metrics = trace_ctx.get_metrics()
            agent_metrics = self._metrics_by_agent[agent_id]
            agent_metrics.total_spans += trace_metrics.total_spans
            agent_metrics.llm_call_count += trace_metrics.llm_call_count
            agent_metrics.tool_call_count += trace_metrics.tool_call_count
            agent_metrics.error_count += trace_metrics.error_count
            agent_metrics.total_prompt_tokens += trace_metrics.total_prompt_tokens
            agent_metrics.total_completion_tokens += trace_metrics.total_completion_tokens
            agent_metrics.total_cached_tokens += trace_metrics.total_cached_tokens

        # Export
        if self.export_to_log:
            self._log_trace(trace_ctx)

        if self.on_trace_complete:
            try:
                self.on_trace_complete(trace_ctx)
            except Exception as e:
                logger.warning(f"Error in trace complete callback: {e}")

    def _log_trace(self, trace_ctx: TraceContext) -> None:
        """Log trace summary."""
        metrics = trace_ctx.get_metrics()
        root = trace_ctx.root_span

        logger.info(
            f"Trace completed: {root.name} "
            f"[trace_id={trace_ctx.trace_id[:8]}] "
            f"[duration={metrics.total_duration_ms:.0f}ms] "
            f"[spans={metrics.total_spans}] "
            f"[llm_calls={metrics.llm_call_count}] "
            f"[tools={metrics.tool_call_count}] "
            f"[tokens={metrics.total_tokens}] "
            f"[errors={metrics.error_count}]"
        )

    def get_active_traces(self) -> List[TraceContext]:
        """Get all currently active traces."""
        return list(self._active_traces.values())

    def get_agent_metrics(self, agent_id: str) -> TraceMetrics:
        """Get aggregated metrics for a specific agent."""
        return self._metrics_by_agent.get(agent_id, TraceMetrics())

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get metrics summary for all agents."""
        return {
            "active_traces": len(self._active_traces),
            "completed_traces": len(self._completed_traces),
            "agents": {
                agent_id: metrics.to_dict()
                for agent_id, metrics in self._metrics_by_agent.items()
            }
        }


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


def configure_tracer(
    service_name: str = "pythinker-agent",
    export_to_log: bool = True,
    on_trace_complete: Optional[Callable[[TraceContext], None]] = None,
    export_to_otel: bool = False,
) -> Tracer:
    """Configure and return the global tracer.

    Args:
        service_name: Name of the service
        export_to_log: Whether to log traces
        on_trace_complete: Custom trace handler
        export_to_otel: Whether to export traces to OpenTelemetry

    Returns:
        Configured Tracer instance
    """
    global _tracer

    # Combine OTEL export with custom callback if both are enabled
    final_callback = on_trace_complete

    if export_to_otel:
        try:
            from app.infrastructure.observability.otel_exporter import (
                export_trace_to_otel,
                is_otel_enabled,
            )

            if is_otel_enabled():
                def combined_callback(trace_ctx: TraceContext) -> None:
                    export_trace_to_otel(trace_ctx)
                    if on_trace_complete:
                        on_trace_complete(trace_ctx)

                final_callback = combined_callback
                logger.info("OTEL trace export enabled")
        except ImportError:
            logger.debug("OTEL exporter not available")

    _tracer = Tracer(
        service_name=service_name,
        export_to_log=export_to_log,
        on_trace_complete=final_callback
    )
    return _tracer
