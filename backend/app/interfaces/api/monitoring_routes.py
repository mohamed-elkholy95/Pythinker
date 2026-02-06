"""
Enhanced monitoring and health check API endpoints.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.error_manager import get_error_manager
from app.core.health_monitor import get_health_monitor
from app.core.sandbox_manager import get_sandbox_manager
from app.core.system_integrator import get_system_integrator
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user

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
    """Get sandbox statistics"""
    sandbox_manager = get_sandbox_manager()
    return sandbox_manager.get_sandbox_stats()


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
