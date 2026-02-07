"""
Lightweight health check endpoints for connectivity and readiness verification.
Separate from the comprehensive monitoring endpoints for minimal overhead.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.health_monitor import ComponentStatus, get_health_monitor

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
