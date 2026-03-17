"""Resource monitoring service for sandbox containers.

Monitors CPU, memory, and other resource usage of Docker containers.
"""

import asyncio
import contextlib
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ContainerResources(BaseModel):
    """Snapshot of container resource usage."""

    cpu_percent: float
    memory_used_mb: float
    memory_percent: float
    timestamp: datetime


class ResourceMonitor:
    """Monitors sandbox container resources via Docker Stats API."""

    def __init__(self, docker_client: Any | None = None):
        """Initialize resource monitor.

        Args:
            docker_client: Docker client instance (optional, will create if not provided)
        """
        self._docker_client = docker_client
        self._monitoring_active: dict[str, bool] = {}
        self._resource_history: dict[str, list[ContainerResources]] = defaultdict(list)
        self._monitoring_tasks: dict[str, asyncio.Task] = {}

    async def start_monitoring(self, session_id: str, container_id: str) -> None:
        """Start monitoring container resources every 10 seconds.

        Args:
            session_id: Session identifier
            container_id: Docker container ID
        """
        if session_id in self._monitoring_active:
            logger.warning(f"Already monitoring session {session_id}")
            return

        self._monitoring_active[session_id] = True
        task = asyncio.create_task(self._monitor_loop(session_id, container_id))
        self._monitoring_tasks[session_id] = task
        logger.info(f"Started resource monitoring for session {session_id}")

    async def stop_monitoring(self, session_id: str) -> None:
        """Stop monitoring a session.

        Args:
            session_id: Session identifier
        """
        self._monitoring_active[session_id] = False

        if session_id in self._monitoring_tasks:
            task = self._monitoring_tasks[session_id]
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            del self._monitoring_tasks[session_id]

        logger.info(f"Stopped resource monitoring for session {session_id}")

    async def _monitor_loop(self, session_id: str, container_id: str) -> None:
        """Monitor container resources in a loop.

        Args:
            session_id: Session identifier
            container_id: Docker container ID
        """
        if not self._docker_client:
            logger.warning("No Docker client available, skipping resource monitoring")
            return

        try:
            container = self._docker_client.containers.get(container_id)
        except Exception as e:
            logger.error(f"Failed to get container {container_id}: {e}")
            return

        while self._monitoring_active.get(session_id, False):
            try:
                stats = container.stats(stream=False)

                snapshot = ContainerResources(
                    cpu_percent=self._calculate_cpu_percent(stats),
                    memory_used_mb=stats["memory_stats"]["usage"] / 1024 / 1024,
                    memory_percent=(stats["memory_stats"]["usage"] / stats["memory_stats"]["limit"]) * 100,
                    timestamp=datetime.now(UTC),
                )

                self._resource_history[session_id].append(snapshot)

                # Keep only last 100 snapshots to prevent memory bloat
                if len(self._resource_history[session_id]) > 100:
                    self._resource_history[session_id] = self._resource_history[session_id][-100:]

                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring resources for {session_id}: {e}")
                await asyncio.sleep(10)

    def _calculate_cpu_percent(self, stats: dict) -> float:
        """Calculate CPU usage percentage from Docker stats.

        Args:
            stats: Docker stats dictionary

        Returns:
            CPU usage percentage
        """
        try:
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            num_cpus = stats["cpu_stats"]["online_cpus"]

            if system_delta > 0 and cpu_delta > 0:
                return (cpu_delta / system_delta) * num_cpus * 100.0
        except (KeyError, ZeroDivisionError) as e:
            logger.debug(f"Failed to calculate CPU percent: {e}")

        return 0.0

    def get_latest_snapshot(self, session_id: str) -> ContainerResources | None:
        """Get the most recent resource snapshot for a session.

        Args:
            session_id: Session identifier

        Returns:
            Latest ContainerResources or None if no data available
        """
        history = self._resource_history.get(session_id, [])
        return history[-1] if history else None

    def get_resource_history(self, session_id: str) -> list[ContainerResources]:
        """Get full resource history for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of ContainerResources snapshots
        """
        return self._resource_history.get(session_id, [])

    def get_average_usage(self, session_id: str) -> dict[str, float] | None:
        """Calculate average resource usage for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary with average CPU and memory usage, or None if no data
        """
        history = self._resource_history.get(session_id, [])
        if not history:
            return None

        avg_cpu = sum(s.cpu_percent for s in history) / len(history)
        avg_memory = sum(s.memory_used_mb for s in history) / len(history)

        return {
            "avg_cpu_percent": avg_cpu,
            "avg_memory_mb": avg_memory,
            "peak_cpu_percent": max(s.cpu_percent for s in history),
            "peak_memory_mb": max(s.memory_used_mb for s in history),
        }


# Global instance
_resource_monitor: ResourceMonitor | None = None


def get_resource_monitor() -> ResourceMonitor:
    """Get the global resource monitor instance.

    Returns:
        ResourceMonitor instance
    """
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = ResourceMonitor()
    return _resource_monitor
