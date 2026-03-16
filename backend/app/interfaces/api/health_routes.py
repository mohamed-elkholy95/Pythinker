"""
Lightweight health check endpoints for connectivity and readiness verification.
Separate from the comprehensive monitoring endpoints for minimal overhead.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.health_monitor import ComponentStatus, get_health_monitor
from app.domain.models.user import User
from app.domain.services.stream_guard import get_aggregate_stream_metrics
from app.interfaces.dependencies import get_current_user

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint integrated with the health monitor.

    Returns system health status from the health monitor.
    Returns 503 when system is unhealthy.
    """
    health = get_health_monitor().get_system_health()
    status_code = 200 if health["overall_status"] != ComponentStatus.UNHEALTHY.value else 503
    return JSONResponse(
        content={
            "status": health["overall_status"],
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "pythinker-backend",
            "components": health.get("components", {}),
        },
        status_code=status_code,
    )


@router.get("/health/live")
async def liveness_probe() -> dict[str, Any]:
    """
    Liveness probe — always returns 200 if the process is running.

    Used by container orchestrators (Docker, K8s) to detect hung processes.
    """
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/health/ready")
async def readiness_probe() -> JSONResponse:
    """
    Readiness probe — returns 503 if the system is not ready to serve traffic.

    Used by load balancers to stop routing traffic to unhealthy instances.
    """
    health = get_health_monitor().get_system_health()
    is_ready = health["overall_status"] != ComponentStatus.UNHEALTHY.value
    return JSONResponse(
        content={
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now(UTC).isoformat(),
            "monitoring_active": health.get("monitoring_active", False),
        },
        status_code=200 if is_ready else 503,
    )


@router.get("/health/streaming")
async def streaming_health(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get streaming health metrics.

    Returns aggregate metrics about SSE connections for monitoring:
    - Active connections count
    - Average event latency
    - Reconnection rate
    - Error rate by category
    - Stream health score (0-100)

    Requires authentication as this is a monitoring endpoint.
    """
    # Get aggregate metrics from stream guard
    aggregate_metrics = await get_aggregate_stream_metrics()

    # Calculate health score based on metrics
    health_score = _calculate_health_score(aggregate_metrics)

    error_rate_by_category = {
        category: round(rate, 4) for category, rate in aggregate_metrics.get("error_rate_by_category", {}).items()
    }
    return {
        "status": "healthy" if health_score >= 70 else "degraded" if health_score >= 40 else "unhealthy",
        "health_score": health_score,
        "metrics": {
            "active_connections": aggregate_metrics["active_connections"],
            "active_connections_by_endpoint": aggregate_metrics.get("active_connections_by_endpoint", {}),
            "total_sessions": aggregate_metrics["total_sessions"],
            "total_events": aggregate_metrics["total_events"],
            "avg_events_per_session": round(aggregate_metrics["avg_events_per_session"], 2),
            "avg_events_per_second": aggregate_metrics["avg_events_per_second"],
            "latency_ms": aggregate_metrics.get("latency_ms", {}),
            "error_rate": round(aggregate_metrics["error_rate"], 4),
            "error_count_by_category": aggregate_metrics.get("error_count_by_category", {}),
            "error_rate_by_category": error_rate_by_category,
            "cancellation_rate": round(aggregate_metrics["cancellation_rate"], 4),
            "waiting_events_total": aggregate_metrics.get("waiting_events_total", 0),
            "avg_waiting_events_per_session": round(aggregate_metrics.get("avg_waiting_events_per_session", 0.0), 2),
            "waiting_event_ratio": round(aggregate_metrics.get("waiting_event_ratio", 0.0), 4),
            "waiting_stage_counts": aggregate_metrics.get("waiting_stage_counts", {}),
            "reconnections_last_5m": aggregate_metrics.get("reconnections_last_5m", 0),
            "reconnection_rate_per_min": aggregate_metrics.get("reconnection_rate_per_min", 0.0),
            "reconnections_last_5m_by_endpoint": aggregate_metrics.get("reconnections_last_5m_by_endpoint", {}),
            "metrics_window_seconds": aggregate_metrics.get("metrics_window_seconds", 300.0),
        },
        "recommendations": _get_recommendations(aggregate_metrics, health_score),
    }


def _calculate_health_score(metrics: dict[str, Any]) -> int:
    """Calculate a health score from 0-100 based on streaming metrics."""
    score = 100.0

    # Deduct for high error rate
    error_rate = metrics.get("error_rate", 0)
    if error_rate > 0.5:
        score -= 40
    elif error_rate > 0.2:
        score -= 25
    elif error_rate > 0.1:
        score -= 10
    elif error_rate > 0.05:
        score -= 5

    # Deduct for high cancellation rate
    cancellation_rate = metrics.get("cancellation_rate", 0)
    if cancellation_rate > 0.5:
        score -= 20
    elif cancellation_rate > 0.3:
        score -= 10
    elif cancellation_rate > 0.1:
        score -= 5

    # Deduct for low event rate (indicates stuck connections)
    events_per_second = metrics.get("avg_events_per_second", 0)
    if events_per_second < 0.1:
        score -= 15
    elif events_per_second < 0.5:
        score -= 5

    latency = metrics.get("latency_ms", {})
    p95_latency_ms = latency.get("p95")
    if isinstance(p95_latency_ms, (int, float)):
        if p95_latency_ms > 5000:
            score -= 20
        elif p95_latency_ms > 2500:
            score -= 10
        elif p95_latency_ms > 1200:
            score -= 5

    reconnections_per_min = metrics.get("reconnection_rate_per_min", 0.0)
    if reconnections_per_min > 20:
        score -= 15
    elif reconnections_per_min > 10:
        score -= 8
    elif reconnections_per_min > 5:
        score -= 4

    return max(0, min(100, int(score)))


def _get_recommendations(metrics: dict[str, Any], health_score: int) -> list[str]:
    """Get recommendations based on current metrics."""
    recommendations = []

    error_rate = metrics.get("error_rate", 0)
    cancellation_rate = metrics.get("cancellation_rate", 0)
    events_per_second = metrics.get("avg_events_per_second", 0)
    reconnections_per_min = metrics.get("reconnection_rate_per_min", 0.0)
    p95_latency = metrics.get("latency_ms", {}).get("p95")
    waiting_event_ratio = metrics.get("waiting_event_ratio", 0.0)

    if error_rate > 0.2:
        recommendations.append("High error rate detected. Check backend logs for errors.")

    if cancellation_rate > 0.3:
        recommendations.append("High cancellation rate. Users may be experiencing connectivity issues.")

    if events_per_second < 0.1:
        recommendations.append("Low event rate. Some streams may be stuck or idle.")

    if isinstance(p95_latency, (int, float)) and p95_latency > 2500:
        recommendations.append("p95 stream latency is elevated. Investigate slow upstream operations.")

    if reconnections_per_min > 5:
        recommendations.append("Frequent reconnects detected. Check SSE transport stability and proxy settings.")

    if waiting_event_ratio > 0.5:
        recommendations.append("High execution-wait beacon ratio detected. Investigate slow tools/LLM calls.")

    if health_score < 40:
        recommendations.append("System health is degraded. Consider scaling or investigating issues.")

    if not recommendations:
        recommendations.append("All systems operating normally.")

    return recommendations
