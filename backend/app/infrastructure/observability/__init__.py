"""Observability infrastructure for agent tracing and debugging.

This module provides a foundation for observability features including:
- Distributed tracing with spans
- Token usage tracking
- Performance metrics
- Debug visualization

The implementation is designed to be pluggable, allowing integration with
external observability platforms (Logfire, LangSmith, OpenTelemetry) in the future.
"""

from app.infrastructure.observability.tracer import (
    Tracer,
    get_tracer,
    TraceContext,
)
from app.infrastructure.observability.spans import (
    Span,
    SpanKind,
    SpanStatus,
)

__all__ = [
    "Tracer",
    "get_tracer",
    "TraceContext",
    "Span",
    "SpanKind",
    "SpanStatus",
]
