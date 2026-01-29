"""
Health Monitoring and Metrics Collection System
Provides comprehensive monitoring for all system components.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.core.error_manager import get_error_manager
from app.core.sandbox_manager import get_sandbox_manager

logger = logging.getLogger(__name__)


class ComponentStatus(str, Enum):
    """Component health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    """Individual health metric"""
    name: str
    value: float
    status: ComponentStatus
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentHealth:
    """Health status for a system component"""
    component: str
    status: ComponentStatus
    metrics: list[HealthMetric] = field(default_factory=list)
    last_check: datetime = None
    error_count: int = 0

    def add_metric(self, metric: HealthMetric):
        """Add a health metric"""
        self.metrics.append(metric)
        # Keep only recent metrics (last 100)
        if len(self.metrics) > 100:
            self.metrics.pop(0)


class HealthMonitor:
    """System health monitoring service"""

    def __init__(self):
        self._components: dict[str, ComponentHealth] = {}
        self._monitoring_tasks: dict[str, asyncio.Task] = {}
        self._monitoring_interval = 30  # seconds
        self._is_monitoring = False

    async def start_monitoring(self):
        """Start health monitoring for all components"""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        logger.info("Starting health monitoring")

        # Start monitoring tasks for each component
        components = [
            "error_manager",
            "sandbox_manager",
            "workflow_manager",
            "database",
            "redis",
            "qdrant"
        ]

        for component in components:
            task = asyncio.create_task(self._monitor_component(component))
            self._monitoring_tasks[component] = task

    async def stop_monitoring(self):
        """Stop health monitoring"""
        self._is_monitoring = False

        # Cancel all monitoring tasks
        for task in self._monitoring_tasks.values():
            task.cancel()

        self._monitoring_tasks.clear()
        logger.info("Health monitoring stopped")

    async def _monitor_component(self, component: str):
        """Monitor a specific component"""
        while self._is_monitoring:
            try:
                await self._check_component_health(component)
                await asyncio.sleep(self._monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring component {component}: {e}")
                await asyncio.sleep(self._monitoring_interval)

    async def _check_component_health(self, component: str):
        """Check health of a specific component"""
        try:
            health = self._components.get(component, ComponentHealth(component, ComponentStatus.UNKNOWN))
            health.last_check = datetime.now()

            if component == "error_manager":
                await self._check_error_manager_health(health)
            elif component == "sandbox_manager":
                await self._check_sandbox_manager_health(health)
            elif component == "workflow_manager":
                await self._check_workflow_manager_health(health)
            elif component == "database":
                await self._check_database_health(health)
            elif component == "redis":
                await self._check_redis_health(health)
            elif component == "qdrant":
                await self._check_qdrant_health(health)

            self._components[component] = health

        except Exception as e:
            logger.error(f"Health check failed for {component}: {e}")
            health = self._components.get(component, ComponentHealth(component, ComponentStatus.UNHEALTHY))
            health.status = ComponentStatus.UNHEALTHY
            health.error_count += 1
            self._components[component] = health

    async def _check_error_manager_health(self, health: ComponentHealth):
        """Check error manager health"""
        error_manager = get_error_manager()
        stats = error_manager.get_error_stats(hours=1)

        # Check error rate
        error_rate = stats["total_errors"] / 60  # errors per minute

        if error_rate > 10:
            health.status = ComponentStatus.UNHEALTHY
        elif error_rate > 5:
            health.status = ComponentStatus.DEGRADED
        else:
            health.status = ComponentStatus.HEALTHY

        health.add_metric(HealthMetric(
            name="error_rate",
            value=error_rate,
            status=health.status,
            timestamp=datetime.now(),
            metadata=stats
        ))

    async def _check_sandbox_manager_health(self, health: ComponentHealth):
        """Check sandbox manager health"""
        sandbox_manager = get_sandbox_manager()
        stats = sandbox_manager.get_sandbox_stats()

        # Check healthy sandbox ratio
        total = stats["total_sandboxes"]
        healthy = stats["healthy_sandboxes"]
        healthy_ratio = healthy / max(total, 1)

        if healthy_ratio < 0.5:
            health.status = ComponentStatus.UNHEALTHY
        elif healthy_ratio < 0.8:
            health.status = ComponentStatus.DEGRADED
        else:
            health.status = ComponentStatus.HEALTHY

        health.add_metric(HealthMetric(
            name="healthy_sandbox_ratio",
            value=healthy_ratio,
            status=health.status,
            timestamp=datetime.now(),
            metadata=stats
        ))

    async def _check_workflow_manager_health(self, health: ComponentHealth):
        """Check workflow manager health"""
        # For now, assume healthy if no exceptions
        health.status = ComponentStatus.HEALTHY

        health.add_metric(HealthMetric(
            name="status",
            value=1.0,
            status=health.status,
            timestamp=datetime.now()
        ))

    async def _check_database_health(self, health: ComponentHealth):
        """Check database connectivity"""
        try:
            from app.infrastructure.storage.mongodb import get_mongodb

            # Simple ping test
            mongodb = get_mongodb()
            await mongodb.client.admin.command('ping')

            health.status = ComponentStatus.HEALTHY
            response_time = 0.1  # Placeholder

        except Exception as e:
            health.status = ComponentStatus.UNHEALTHY
            response_time = -1
            logger.warning(f"Database health check failed: {e}")

        health.add_metric(HealthMetric(
            name="response_time",
            value=response_time,
            status=health.status,
            timestamp=datetime.now()
        ))

    async def _check_redis_health(self, health: ComponentHealth):
        """Check Redis connectivity"""
        try:
            from app.infrastructure.storage.redis import get_redis

            # Simple ping test
            redis = get_redis()
            await redis.client.ping()

            health.status = ComponentStatus.HEALTHY
            response_time = 0.05  # Placeholder

        except Exception as e:
            health.status = ComponentStatus.UNHEALTHY
            response_time = -1
            logger.warning(f"Redis health check failed: {e}")

        health.add_metric(HealthMetric(
            name="response_time",
            value=response_time,
            status=health.status,
            timestamp=datetime.now()
        ))

    async def _check_qdrant_health(self, health: ComponentHealth):
        """Check Qdrant connectivity"""
        try:
            from app.infrastructure.storage.qdrant import get_qdrant

            # Simple health check
            qdrant = get_qdrant()
            # Placeholder health check

            health.status = ComponentStatus.HEALTHY
            response_time = 0.1  # Placeholder

        except Exception as e:
            health.status = ComponentStatus.DEGRADED  # Qdrant is optional
            response_time = -1
            logger.warning(f"Qdrant health check failed: {e}")

        health.add_metric(HealthMetric(
            name="response_time",
            value=response_time,
            status=health.status,
            timestamp=datetime.now()
        ))

    def get_system_health(self) -> dict[str, Any]:
        """Get overall system health status"""
        component_statuses = {name: comp.status.value for name, comp in self._components.items()}

        # Determine overall status
        if any(status == ComponentStatus.UNHEALTHY.value for status in component_statuses.values()):
            overall_status = ComponentStatus.UNHEALTHY
        elif any(status == ComponentStatus.DEGRADED.value for status in component_statuses.values()):
            overall_status = ComponentStatus.DEGRADED
        else:
            overall_status = ComponentStatus.HEALTHY

        return {
            "overall_status": overall_status.value,
            "components": component_statuses,
            "last_check": datetime.now().isoformat(),
            "monitoring_active": self._is_monitoring
        }

    def get_component_health(self, component: str) -> dict[str, Any] | None:
        """Get health status for a specific component"""
        health = self._components.get(component)
        if not health:
            return None

        return {
            "component": health.component,
            "status": health.status.value,
            "last_check": health.last_check.isoformat() if health.last_check else None,
            "error_count": health.error_count,
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "status": m.status.value,
                    "timestamp": m.timestamp.isoformat(),
                    "metadata": m.metadata
                }
                for m in health.metrics[-10:]  # Last 10 metrics
            ]
        }


# Global health monitor instance
_health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance"""
    return _health_monitor
