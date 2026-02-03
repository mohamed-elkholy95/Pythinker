"""OpenTelemetry Exporter for Pythinker

Provides optional integration with OpenTelemetry for distributed tracing
and metrics export to OTEL collectors.

This module is designed to work with or without the opentelemetry packages.
When packages are not available, it gracefully degrades to no-op behavior.

Usage:
    from app.infrastructure.observability.otel_exporter import (
        configure_otel,
        get_otel_tracer,
    )

    # Configure at startup
    configure_otel(
        endpoint="http://localhost:4317",
        service_name="pythinker-agent",
    )
"""

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Check for OpenTelemetry availability
OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:
    logger.debug("OpenTelemetry packages not installed. OTEL export disabled.")


@dataclass
class OTELConfig:
    """Configuration for OpenTelemetry export."""

    enabled: bool = False
    endpoint: str = ""
    service_name: str = "pythinker-agent"
    insecure: bool = True  # Use insecure connection (no TLS)
    headers: dict[str, str] = None

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


_otel_config: OTELConfig | None = None
_otel_tracer = None


def configure_otel(
    endpoint: str | None = None,
    service_name: str = "pythinker-agent",
    insecure: bool = True,
    headers: dict[str, str] | None = None,
) -> bool:
    """Configure OpenTelemetry exporter.

    Args:
        endpoint: OTEL collector endpoint (e.g., "http://localhost:4317")
        service_name: Service name for traces
        insecure: Whether to use insecure connection
        headers: Optional headers for authentication

    Returns:
        True if successfully configured, False otherwise
    """
    global _otel_config, _otel_tracer

    # Try to get endpoint from settings if not provided
    if endpoint is None:
        settings = get_settings()
        endpoint = getattr(settings, "otel_endpoint", None)

    if not endpoint:
        logger.debug("No OTEL endpoint configured, skipping OTEL setup")
        _otel_config = OTELConfig(enabled=False)
        return False

    if not OTEL_AVAILABLE:
        logger.warning(
            "OpenTelemetry requested but packages not installed. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        _otel_config = OTELConfig(enabled=False)
        return False

    try:
        # Create resource with service name
        resource = Resource.create({SERVICE_NAME: service_name})

        # Create OTLP exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=insecure,
            headers=headers or {},
        )

        # Create and set tracer provider
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _otel_tracer = trace.get_tracer(service_name)

        _otel_config = OTELConfig(
            enabled=True,
            endpoint=endpoint,
            service_name=service_name,
            insecure=insecure,
            headers=headers or {},
        )

        logger.info(f"OpenTelemetry configured successfully: endpoint={endpoint}")
        return True

    except Exception as e:
        logger.error(f"Failed to configure OpenTelemetry: {e}")
        _otel_config = OTELConfig(enabled=False)
        return False


def get_otel_tracer():
    """Get the configured OTEL tracer.

    Returns:
        OTEL tracer if configured, None otherwise
    """
    return _otel_tracer


def is_otel_enabled() -> bool:
    """Check if OTEL export is enabled."""
    return _otel_config is not None and _otel_config.enabled


def get_otel_config() -> OTELConfig | None:
    """Get the current OTEL configuration."""
    return _otel_config


class OTELSpanContext:
    """Context manager for creating OTEL spans.

    Works as a no-op when OTEL is not configured.
    """

    def __init__(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ):
        self.name = name
        self.attributes = attributes or {}
        self._span = None

    def __enter__(self):
        if _otel_tracer is not None:
            self._span = _otel_tracer.start_span(self.name)
            for key, value in self.attributes.items():
                self._span.set_attribute(key, value)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span is not None:
            if exc_type is not None:
                self._span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc_val)))
            else:
                self._span.set_status(trace.Status(trace.StatusCode.OK))
            self._span.end()
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        if self._span is not None:
            self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        if self._span is not None:
            self._span.add_event(name, attributes=attributes or {})


def otel_span(name: str, attributes: dict[str, Any] | None = None) -> OTELSpanContext:
    """Create an OTEL span context manager.

    Args:
        name: Span name
        attributes: Initial attributes

    Returns:
        OTELSpanContext that works as no-op when OTEL is disabled
    """
    return OTELSpanContext(name, attributes)


def export_trace_to_otel(trace_context: Any) -> None:
    """Export a Pythinker trace context to OTEL.

    This can be used as the on_trace_complete callback for the Tracer.

    Args:
        trace_context: TraceContext from pythinker tracer
    """
    if not is_otel_enabled() or _otel_tracer is None:
        return

    try:
        # Create OTEL spans from trace context spans
        for span in trace_context.spans:
            with _otel_tracer.start_span(span.name) as otel_span:
                # Set attributes
                for key, value in span.attributes.items():
                    if isinstance(value, (str, int, float, bool)):
                        otel_span.set_attribute(key, value)

                # Set token usage if present
                if span.token_usage:
                    otel_span.set_attribute("llm.prompt_tokens", span.token_usage.prompt_tokens)
                    otel_span.set_attribute("llm.completion_tokens", span.token_usage.completion_tokens)
                    otel_span.set_attribute("llm.cached_tokens", span.token_usage.cached_tokens)

                # Set status
                if span.status_message:
                    otel_span.set_attribute("error.message", span.status_message)

        logger.debug(f"Exported trace {trace_context.trace_id[:8]} to OTEL")

    except Exception as e:
        logger.warning(f"Failed to export trace to OTEL: {e}")
