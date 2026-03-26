"""Telemetry initialization for sandbox (OTEL + Sentry).

All imports are lazy — zero overhead when OTEL_ENABLED=false and SENTRY_DSN is unset.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def setup_telemetry(app: "FastAPI") -> None:
    """Initialize OpenTelemetry and/or Sentry if configured."""
    _setup_otel(app)
    _setup_sentry()


def _setup_otel(app: "FastAPI") -> None:
    """Configure OpenTelemetry tracing with OTLP HTTP exporter."""
    if not settings.OTEL_ENABLED or not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.info("OTEL disabled (OTEL_ENABLED=%s)", settings.OTEL_ENABLED)
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create(
            {
                "service.name": settings.OTEL_SERVICE_NAME,
                "service.env": "sandbox",
            }
        )

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces",
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY,
            )
        )
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()

        logger.info(
            "OTEL initialized: service=%s endpoint=%s",
            settings.OTEL_SERVICE_NAME,
            settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        )
    except ImportError:
        logger.warning("OTEL packages not installed — skipping")
    except Exception:
        logger.exception("OTEL setup failed — continuing without tracing")


def _setup_sentry() -> None:
    """Configure Sentry error tracking."""
    if not settings.SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=settings.OTEL_TRACES_SAMPLER_RATIO,
            environment="sandbox",
        )
        logger.info("Sentry initialized for sandbox")
    except ImportError:
        logger.warning("sentry-sdk not installed — skipping")
    except Exception:
        logger.exception("Sentry setup failed — continuing without error tracking")
