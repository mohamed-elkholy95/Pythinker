"""
Enhanced monitoring and health check API endpoints.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.error_manager import get_error_manager
from app.core.health_monitor import get_health_monitor
from app.core.sandbox_manager import get_sandbox_manager
from app.core.system_integrator import get_system_integrator
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/health")
async def get_system_health(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get comprehensive system health status"""
    health_monitor = get_health_monitor()
    return health_monitor.get_system_health()


@router.get("/health/{component}")
async def get_component_health(component: str, current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get health status for a specific component"""
    health_monitor = get_health_monitor()
    health = health_monitor.get_component_health(component)

    if not health:
        raise HTTPException(status_code=404, detail=f"Component {component} not found")

    return health


@router.get("/errors")
async def get_error_stats(hours: int = 24, current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get error statistics for the specified time period"""
    error_manager = get_error_manager()
    return error_manager.get_error_stats(hours=hours)


@router.get("/sandboxes")
async def get_sandbox_stats(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get sandbox statistics including pool status"""
    sandbox_manager = get_sandbox_manager()
    stats = sandbox_manager.get_sandbox_stats()

    # Include pool stats
    try:
        from app.core.sandbox_pool import get_sandbox_pool

        pool = await get_sandbox_pool()
        if pool and pool.is_started:
            stats["pool"] = pool.get_pool_stats()
    except Exception:
        logger.debug("Failed to get sandbox pool stats", exc_info=True)

    return stats


@router.get("/pressure")
async def get_system_pressure(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get current system pressure for load balancing decisions.

    Returns CPU/memory pressure, pool utilization, and whether
    the system can accept new tasks.
    """
    result: dict[str, Any] = {
        "can_accept_new_task": True,
        "reason": "ok",
    }

    # Host resource pressure (soft dependency on psutil)
    try:
        import asyncio

        import psutil

        result["cpu_percent"] = await asyncio.to_thread(lambda: psutil.cpu_percent(interval=0.1))
        mem = await asyncio.to_thread(lambda: psutil.virtual_memory())
        result["memory_percent"] = mem.percent
        result["memory_available_gb"] = round(mem.available / (1024**3), 2)

        if mem.percent > 90:
            result["can_accept_new_task"] = False
            result["reason"] = "host memory pressure critical (>90%)"
        elif result["cpu_percent"] > 95:
            result["can_accept_new_task"] = False
            result["reason"] = "host CPU pressure critical (>95%)"
    except (ImportError, OSError, Exception):
        result["cpu_percent"] = None
        result["memory_percent"] = None
        result["memory_available_gb"] = None

    # Pool utilization
    try:
        from app.core.sandbox_pool import get_sandbox_pool

        pool = await get_sandbox_pool()
        if pool and pool.is_started:
            pool_stats = pool.get_pool_stats()
            max_size = pool_stats["max_size"]
            pool_size = pool_stats["pool_size"]
            result["pool_utilization"] = round(1.0 - (pool_size / max(max_size, 1)), 2)
            result["pool_available"] = pool_size
            result["pool_circuit_open"] = pool_stats["circuit_open"]
            if pool_stats["circuit_open"]:
                result["can_accept_new_task"] = False
                result["reason"] = "sandbox pool circuit breaker open"
    except Exception:
        logger.debug("Failed to get sandbox pool pressure metrics", exc_info=True)

    # Active sandboxes
    sandbox_manager = get_sandbox_manager()
    stats = sandbox_manager.get_sandbox_stats()
    result["active_sandboxes"] = stats["total_sandboxes"]

    return result


@router.get("/status")
async def get_system_status(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get comprehensive system status"""
    integrator = get_system_integrator()
    return integrator.get_system_status()


@router.post("/health/start")
async def start_health_monitoring(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    """Start health monitoring"""
    health_monitor = get_health_monitor()
    await health_monitor.start_monitoring()
    return {"message": "Health monitoring started"}


@router.post("/health/stop")
async def stop_health_monitoring(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    """Stop health monitoring"""
    health_monitor = get_health_monitor()
    await health_monitor.stop_monitoring()
    return {"message": "Health monitoring stopped"}
