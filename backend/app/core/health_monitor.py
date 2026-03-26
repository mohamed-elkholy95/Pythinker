"""
Health Monitoring and Metrics Collection System
Provides comprehensive monitoring for all system components.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
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

    def add_metric(self, metric: HealthMetric) -> None:
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

    async def start_monitoring(self) -> None:
        """Start health monitoring for all components"""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        logger.info("Starting health monitoring")

        # Start monitoring tasks for each component
        components = ["error_manager", "sandbox_manager", "database", "redis", "redis_cache", "qdrant", "minio"]

        for component in components:
            task = asyncio.create_task(self._monitor_component(component))
            self._monitoring_tasks[component] = task

    async def stop_monitoring(self) -> None:
        """Stop health monitoring"""
        self._is_monitoring = False

        # Cancel all monitoring tasks
        for task in self._monitoring_tasks.values():
            task.cancel()

        self._monitoring_tasks.clear()
        logger.info("Health monitoring stopped")

    async def _monitor_component(self, component: str) -> None:
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

    async def _check_component_health(self, component: str) -> None:
        """Check health of a specific component"""
        try:
            health = self._components.get(component, ComponentHealth(component, ComponentStatus.UNKNOWN))
            health.last_check = datetime.now(UTC)

            if component == "error_manager":
                await self._check_error_manager_health(health)
            elif component == "sandbox_manager":
                await self._check_sandbox_manager_health(health)
            elif component == "database":
                await self._check_database_health(health)
            elif component == "redis":
                await self._check_redis_health(health)
            elif component == "redis_cache":
                await self._check_redis_cache_health(health)
            elif component == "qdrant":
                await self._check_qdrant_health(health)
            elif component == "minio":
                await self._check_minio_health(health)

            self._components[component] = health

        except Exception as e:
            logger.error(f"Health check failed for {component}: {e}")
            health = self._components.get(component, ComponentHealth(component, ComponentStatus.UNHEALTHY))
            health.status = ComponentStatus.UNHEALTHY
            health.error_count += 1
            self._components[component] = health

    async def _check_error_manager_health(self, health: ComponentHealth) -> None:
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

        health.add_metric(
            HealthMetric(
                name="error_rate", value=error_rate, status=health.status, timestamp=datetime.now(UTC), metadata=stats
            )
        )

    async def _check_sandbox_manager_health(self, health: ComponentHealth) -> None:
        """Check sandbox manager health"""
        sandbox_manager = get_sandbox_manager()
        stats = sandbox_manager.get_sandbox_stats()

        # Check healthy sandbox ratio
        total = stats["total_sandboxes"]
        healthy = stats["healthy_sandboxes"]

        # No sandboxes is a valid idle state — not unhealthy
        healthy_ratio = 1.0 if total == 0 else healthy / total

        if healthy_ratio < 0.5:
            health.status = ComponentStatus.UNHEALTHY
        elif healthy_ratio < 0.8:
            health.status = ComponentStatus.DEGRADED
        else:
            health.status = ComponentStatus.HEALTHY

        # Include pool stats if pool is active
        try:
            from app.core.sandbox_pool import get_sandbox_pool

            pool = await get_sandbox_pool()
            if pool and pool.is_started:
                stats["pool"] = pool.get_pool_stats()
        except Exception:
            logger.debug("Failed to get sandbox pool stats", exc_info=True)

        health.add_metric(
            HealthMetric(
                name="healthy_sandbox_ratio",
                value=healthy_ratio,
                status=health.status,
                timestamp=datetime.now(UTC),
                metadata=stats,
            )
        )

    async def _check_database_health(self, health: ComponentHealth) -> None:
        """Check database connectivity with WiredTiger cache and connection stats."""
        try:
            import time

            from app.core.prometheus_metrics import (
                mongodb_connections_current,
                mongodb_wiredtiger_cache_bytes,
            )
            from app.infrastructure.storage.mongodb import get_mongodb

            mongodb = get_mongodb()
            start = time.monotonic()
            status = await mongodb.client.admin.command("serverStatus")
            response_time = time.monotonic() - start

            # WiredTiger cache metrics
            wt_cache = status.get("wiredTiger", {}).get("cache", {})
            cache_current = wt_cache.get("bytes currently in the cache", 0)
            cache_max = wt_cache.get("maximum bytes configured", 0)
            cache_dirty = wt_cache.get("tracked dirty bytes in the cache", 0)
            mongodb_wiredtiger_cache_bytes.set({"type": "current"}, cache_current)
            mongodb_wiredtiger_cache_bytes.set({"type": "max"}, cache_max)
            mongodb_wiredtiger_cache_bytes.set({"type": "dirty"}, cache_dirty)

            # Connection metrics
            connections = status.get("connections", {}).get("current", 0)
            mongodb_connections_current.set(value=connections)

            # Determine health from cache pressure
            cache_ratio = cache_current / cache_max if cache_max > 0 else 0
            if cache_ratio > 0.95:
                health.status = ComponentStatus.DEGRADED
            else:
                health.status = ComponentStatus.HEALTHY

        except Exception as e:
            health.status = ComponentStatus.UNHEALTHY
            response_time = -1
            logger.warning(f"Database health check failed: {e}")

        health.add_metric(
            HealthMetric(
                name="response_time",
                value=response_time,
                status=health.status,
                timestamp=datetime.now(UTC),
            )
        )

    async def _check_redis_health(self, health: ComponentHealth) -> None:
        """Check Redis connectivity with memory and hit ratio stats."""
        try:
            import time

            from app.core.prometheus_metrics import (
                cache_eviction_rate,
                redis_keyspace_hit_ratio,
                redis_memory_bytes,
            )
            from app.infrastructure.storage.redis import get_redis

            redis = get_redis()
            await redis.initialize()
            start = time.monotonic()
            info_raw = await redis.call("info", "all", max_retries=2)
            response_time = time.monotonic() - start

            # Parse INFO response into dict
            info: dict[str, str] = {}
            if isinstance(info_raw, (str, bytes)):
                text = info_raw.decode() if isinstance(info_raw, bytes) else info_raw
                for line in text.splitlines():
                    if ":" in line and not line.startswith("#"):
                        k, v = line.split(":", 1)
                        info[k.strip()] = v.strip()

            # Memory metrics
            used_memory = int(info.get("used_memory", 0))
            max_memory = int(info.get("maxmemory", 0))
            redis_memory_bytes.set({"type": "used"}, used_memory)
            redis_memory_bytes.set({"type": "max"}, max_memory)

            # Keyspace hit ratio
            hits = int(info.get("keyspace_hits", 0))
            misses = int(info.get("keyspace_misses", 0))
            total = hits + misses
            hit_ratio = hits / total if total > 0 else 1.0
            redis_keyspace_hit_ratio.set(value=hit_ratio)

            # Eviction rate
            evicted = int(info.get("evicted_keys", 0))
            cache_eviction_rate.set({"cache_type": "redis"}, evicted)

            # Determine health
            if max_memory > 0 and used_memory / max_memory > 0.95:
                health.status = ComponentStatus.DEGRADED
            else:
                health.status = ComponentStatus.HEALTHY

        except Exception as e:
            health.status = ComponentStatus.UNHEALTHY
            response_time = -1
            logger.warning(f"Redis health check failed: {e}")

        health.add_metric(
            HealthMetric(name="response_time", value=response_time, status=health.status, timestamp=datetime.now(UTC))
        )

    async def _check_redis_cache_health(self, health: ComponentHealth) -> None:
        """Check cache Redis connectivity.

        Cache Redis is optional for correctness. Failures degrade performance but should
        not make the entire system unavailable. Skipped entirely when redis_cache_enabled=False.
        """
        from app.infrastructure.storage.redis import get_cache_redis

        redis = get_cache_redis()
        if redis is None:
            health.status = ComponentStatus.HEALTHY
            health.add_metric(
                HealthMetric(name="response_time", value=0, status=health.status, timestamp=datetime.now(UTC))
            )
            return

        try:
            await redis.initialize()
            await redis.call("ping", max_retries=2)

            health.status = ComponentStatus.HEALTHY
            response_time = 0.05  # Placeholder

        except Exception as e:
            health.status = ComponentStatus.DEGRADED
            response_time = -1
            logger.warning(f"Cache Redis health check failed: {e}")

        health.add_metric(
            HealthMetric(name="response_time", value=response_time, status=health.status, timestamp=datetime.now(UTC))
        )

    async def _check_qdrant_health(self, health: ComponentHealth) -> None:
        """Check Qdrant connectivity with collection stats."""
        try:
            import time

            from app.core.prometheus_metrics import (
                qdrant_collection_size,
                qdrant_disk_usage_bytes,
            )
            from app.infrastructure.storage.qdrant import get_qdrant

            qdrant = get_qdrant()
            client = qdrant.client
            start = time.monotonic()
            collections_response = await client.get_collections()
            response_time = time.monotonic() - start

            # Collect per-collection stats
            optimizer_issues = False
            for col_info in collections_response.collections:
                try:
                    col_detail = await client.get_collection(col_info.name)
                    qdrant_collection_size.set(
                        {"collection": col_info.name},
                        col_detail.vectors_count or 0,
                    )
                    # disk_data_size may not be available on all versions
                    disk_size = getattr(col_detail, "disk_data_size", None) or 0
                    qdrant_disk_usage_bytes.set(
                        {"collection": col_info.name},
                        disk_size,
                    )
                    # Check optimizer status
                    opt_status = col_detail.optimizer_status
                    if opt_status and opt_status.status != "ok":
                        optimizer_issues = True
                except Exception:
                    logger.debug("Failed to get stats for collection %s", col_info.name, exc_info=True)

            if optimizer_issues:
                health.status = ComponentStatus.DEGRADED
            else:
                health.status = ComponentStatus.HEALTHY

        except Exception as e:
            health.status = ComponentStatus.DEGRADED  # Qdrant is optional
            response_time = -1
            logger.warning(f"Qdrant health check failed: {e}")

        health.add_metric(
            HealthMetric(name="response_time", value=response_time, status=health.status, timestamp=datetime.now(UTC))
        )

    async def _check_minio_health(self, health: ComponentHealth) -> None:
        """Check MinIO connectivity and bucket availability."""
        try:
            import time

            from app.infrastructure.storage.minio_storage import get_minio_storage

            storage = get_minio_storage()
            start = time.monotonic()
            # list_buckets is a lightweight operation that validates connectivity
            buckets = await asyncio.to_thread(storage._client.list_buckets)
            response_time = time.monotonic() - start

            bucket_names = [b.name for b in buckets] if buckets else []
            health.status = ComponentStatus.HEALTHY

        except Exception as e:
            health.status = ComponentStatus.DEGRADED  # MinIO is optional for core functionality
            response_time = -1
            bucket_names = []
            logger.warning(f"MinIO health check failed: {e}")

        health.add_metric(
            HealthMetric(
                name="response_time",
                value=response_time,
                status=health.status,
                timestamp=datetime.now(UTC),
                metadata={"buckets": bucket_names},
            )
        )

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
            "last_check": datetime.now(UTC).isoformat(),
            "monitoring_active": self._is_monitoring,
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
                    "metadata": m.metadata,
                }
                for m in health.metrics[-10:]  # Last 10 metrics
            ],
        }


# Global health monitor instance
_health_monitor = HealthMonitor()


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance"""
    return _health_monitor
