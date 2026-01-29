"""Observability infrastructure for agent tracing and debugging.

This module provides a foundation for observability features including:
- Distributed tracing with spans
- LLM call tracing with cost tracking
- Token usage tracking
- Performance metrics
- Request context propagation
- Debug visualization

The implementation is designed to be pluggable, allowing integration with
external observability platforms (Langfuse, LangSmith, OpenTelemetry).
"""

from app.infrastructure.observability.context import (
    RequestContext,
    get_agent_id,
    get_request_context,
    get_request_id,
    get_session_id,
    get_user_id,
    request_context_scope,
    set_request_context,
)
from app.infrastructure.observability.llm_tracer import (
    LLMTrace,
    LLMTracerInterface,
    ToolTrace,
    configure_llm_tracer,
    estimate_cost,
    get_llm_tracer,
    trace_generation,
)
from app.infrastructure.observability.spans import (
    Span,
    SpanKind,
    SpanStatus,
)
from app.infrastructure.observability.tracer import (
    TraceContext,
    Tracer,
    get_tracer,
)

__all__ = [
    # Tracer
    "Tracer",
    "get_tracer",
    "TraceContext",
    # Spans
    "Span",
    "SpanKind",
    "SpanStatus",
    # LLM Tracer
    "LLMTracerInterface",
    "LLMTrace",
    "ToolTrace",
    "get_llm_tracer",
    "configure_llm_tracer",
    "trace_generation",
    "estimate_cost",
    # Request Context
    "RequestContext",
    "get_request_context",
    "set_request_context",
    "request_context_scope",
    "get_request_id",
    "get_session_id",
    "get_user_id",
    "get_agent_id",
]
