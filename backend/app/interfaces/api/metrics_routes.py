"""Metrics API Routes

Provides endpoints for Prometheus scraping and metrics inspection.

Endpoints:
    GET /metrics - Prometheus text exposition format
    GET /metrics/json - JSON format metrics
    GET /metrics/health - Health check for monitoring
"""
from fastapi import APIRouter, Response
from typing import Dict, Any
import time

from app.infrastructure.observability.prometheus_metrics import (
    format_prometheus,
    collect_all_metrics,
    active_sessions,
    active_agents,
)
from app.infrastructure.observability.tracer import get_tracer
from app.infrastructure.observability.otel_exporter import get_otel_config
from app.domain.services.tools.cache_layer import get_cache_stats, get_combined_cache_stats
from app.domain.services.agents.metrics import get_metrics_collector
from app.domain.services.tools.dynamic_toolset import get_toolset_manager

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_class=Response)
async def get_prometheus_metrics():
    """Get metrics in Prometheus text exposition format.

    This endpoint is designed to be scraped by Prometheus.
    Returns metrics in the standard Prometheus text format.
    """
    # Update dynamic metrics before collection
    await _update_dynamic_metrics()

    # Generate Prometheus format
    content = format_prometheus()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/json")
async def get_json_metrics() -> Dict[str, Any]:
    """Get metrics in JSON format.

    Returns all metrics in a structured JSON format for
    custom dashboards or debugging.
    """
    # Update dynamic metrics
    await _update_dynamic_metrics()

    # Collect all metrics
    metrics_data = collect_all_metrics()

    # Add tracer metrics
    tracer = get_tracer()
    tracer_metrics = tracer.get_all_metrics()

    # Add cache stats
    cache_stats = get_cache_stats().to_dict()

    # Add OTEL status
    otel_config = get_otel_config()
    otel_status = {
        "enabled": otel_config.enabled if otel_config else False,
        "endpoint": otel_config.endpoint if otel_config else None,
    }

    return {
        **metrics_data,
        "tracer": tracer_metrics,
        "cache": cache_stats,
        "otel": otel_status,
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for monitoring systems.

    Returns basic health information and uptime status.
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "pythinker-agent",
    }


@router.get("/tracer")
async def get_tracer_metrics() -> Dict[str, Any]:
    """Get detailed tracer metrics.

    Returns metrics from the internal tracer including
    active traces and per-agent statistics.
    """
    tracer = get_tracer()
    return {
        "metrics": tracer.get_all_metrics(),
        "active_traces": len(tracer.get_active_traces()),
    }


@router.get("/cache")
async def get_cache_metrics() -> Dict[str, Any]:
    """Get tool cache statistics.

    Returns cache hit/miss rates and other caching metrics.
    """
    return {
        "cache": get_cache_stats().to_dict(),
    }


@router.get("/agent")
async def get_agent_optimization_metrics() -> Dict[str, Any]:
    """Get agent optimization metrics.

    Returns comprehensive metrics for all agent optimizations:
    - Token usage and cache savings
    - L1/L2 cache hit rates
    - Tool execution statistics
    - Hallucination detection counts
    - Dynamic toolset reduction rates
    - Latency percentiles
    """
    collector = get_metrics_collector()
    return collector.get_summary()


@router.get("/agent/prometheus")
async def get_agent_prometheus_metrics():
    """Get agent metrics in Prometheus format.

    Designed for Prometheus scraping of agent-specific metrics.
    """
    collector = get_metrics_collector()
    content = collector.export_prometheus()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/agent/timeseries")
async def get_agent_timeseries(minutes: int = 60) -> Dict[str, Any]:
    """Get time-series metrics for the last N minutes.

    Args:
        minutes: Number of minutes of history (max 60)

    Returns time-bucketed metrics for trend analysis.
    """
    collector = get_metrics_collector()
    minutes = min(minutes, 60)  # Cap at 60 minutes

    return {
        "period_minutes": minutes,
        "buckets": collector.get_time_series(minutes)
    }


@router.get("/agent/cache")
async def get_agent_cache_details() -> Dict[str, Any]:
    """Get detailed cache metrics including L1 and L2.

    Returns multi-tier cache performance data.
    """
    combined = get_combined_cache_stats()
    collector = get_metrics_collector()

    return {
        "l1": combined["l1"],
        "l2": combined["l2"],
        "combined": combined["combined"],
        "collector": {
            "l1_hits": collector.cache.l1_hits,
            "l1_misses": collector.cache.l1_misses,
            "l2_hits": collector.cache.l2_hits,
            "l2_misses": collector.cache.l2_misses,
        }
    }


@router.get("/agent/toolset")
async def get_toolset_metrics() -> Dict[str, Any]:
    """Get dynamic toolset filtering metrics.

    Returns statistics about tool filtering effectiveness.
    """
    manager = get_toolset_manager()
    collector = get_metrics_collector()

    return {
        "toolset": manager.get_stats(),
        "avg_reduction": f"{collector.avg_toolset_reduction:.1%}",
        "samples": len(collector._toolset_reductions),
    }


@router.post("/agent/reset")
async def reset_agent_metrics() -> Dict[str, Any]:
    """Reset all agent optimization metrics.

    Returns confirmation of reset.
    """
    collector = get_metrics_collector()
    collector.reset()

    return {
        "status": "reset",
        "timestamp": time.time()
    }


async def _update_dynamic_metrics() -> None:
    """Update metrics that need to be calculated dynamically.

    This is called before metrics collection to ensure
    gauges reflect current state.
    """
    tracer = get_tracer()
    tracer_metrics = tracer.get_all_metrics()

    # Update active counts
    active_sessions.set({}, tracer_metrics.get("active_traces", 0))
    # Note: active_agents would be updated by the agent service
