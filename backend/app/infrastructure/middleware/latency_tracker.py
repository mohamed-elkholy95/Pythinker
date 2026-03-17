"""Async context manager for tracking infrastructure operation latency and SLO violations.

Usage:
    from app.infrastructure.middleware.latency_tracker import track_operation

    async with track_operation("mongodb", "find", collection="sessions"):
        result = await collection.find(query).to_list()
"""

import contextlib
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.prometheus_metrics import (
    record_minio_operation,
    record_mongodb_operation,
    slo_violations_total,
)

logger = logging.getLogger(__name__)

# SLO threshold lookup by service name
_SLO_THRESHOLDS: dict[str, str] = {
    "mongodb": "slo_mongodb_p95_seconds",
    "redis": "slo_redis_p95_seconds",
    "minio": "slo_minio_p95_seconds",
    "qdrant": "slo_qdrant_p95_seconds",
}


@asynccontextmanager
async def track_operation(
    service: str,
    operation: str,
    *,
    collection: str = "",
    bucket: str = "",
) -> AsyncGenerator[None, None]:
    """Track an infrastructure operation's latency and check SLO threshold.

    Args:
        service: Service name ("mongodb", "redis", "minio", "qdrant").
        operation: Operation name (e.g., "find", "get", "put_object").
        collection: MongoDB collection name (for mongodb service).
        bucket: MinIO bucket name (for minio service).
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start

        # Record service-specific histogram metrics
        if service == "mongodb":
            record_mongodb_operation(
                operation,
                collection,
                duration,
                slo_threshold=_get_slo_threshold(service),
            )
        elif service == "minio":
            record_minio_operation(
                operation,
                bucket,
                duration,
                slo_threshold=_get_slo_threshold(service),
            )
        else:
            # Generic SLO check for redis/qdrant
            threshold = _get_slo_threshold(service)
            if duration > threshold:
                slo_violations_total.inc({"service": service, "operation": operation})

        # Warn on significant SLO breaches (>2x threshold)
        threshold = _get_slo_threshold(service)
        if duration > threshold * 2:
            logger.warning(
                "SLO breach: %s.%s took %.3fs (threshold: %.3fs)",
                service,
                operation,
                duration,
                threshold,
            )


def _get_slo_threshold(service: str) -> float:
    """Get the SLO P95 threshold for a service from settings."""
    with contextlib.suppress(Exception):
        settings = get_settings()
        attr = _SLO_THRESHOLDS.get(service)
        if attr:
            return getattr(settings, attr, 0.1)
    # Fallback defaults
    return {"mongodb": 0.1, "redis": 0.01, "minio": 0.5, "qdrant": 0.2}.get(service, 0.1)
