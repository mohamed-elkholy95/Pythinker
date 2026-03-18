"""Resource Manager for Centralized Lifecycle Management.

Provides centralized registration and cleanup of application resources
including database connections, HTTP clients, background tasks, and
external service connections.

Usage:
    manager = get_resource_manager()

    # Register a resource with cleanup handler
    await manager.register(
        name="mongodb",
        resource=mongodb_client,
        cleanup_handler=lambda r: r.close(),
    )

    # Shutdown all resources gracefully
    await manager.shutdown_all(timeout=30.0)

Features:
- Ordered shutdown based on registration order (LIFO)
- Timeout handling for slow cleanups
- Error isolation (one failure doesn't block others)
- Health status tracking
- Resource dependency management
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ResourceState(str, Enum):
    """Resource lifecycle states."""

    PENDING = "pending"
    ACTIVE = "active"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"
    ERROR = "error"


@dataclass
class ManagedResource:
    """A registered resource with its metadata."""

    name: str
    resource: Any
    cleanup_handler: Callable | None = None
    state: ResourceState = ResourceState.PENDING
    priority: int = 0  # Higher priority = shutdown first
    depends_on: list[str] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Tracking
    last_error: str | None = None
    shutdown_duration_ms: float = 0.0

    async def shutdown(self, timeout: float = 10.0) -> bool:  # noqa: ASYNC109
        """Shutdown this resource.

        Args:
            timeout: Maximum time to wait for shutdown

        Returns:
            True if shutdown successful
        """
        if self.state in (ResourceState.SHUTDOWN, ResourceState.SHUTTING_DOWN):
            return True

        self.state = ResourceState.SHUTTING_DOWN
        start_time = time.perf_counter()

        try:
            if self.cleanup_handler:
                # Handle both async and sync cleanup handlers
                result = self.cleanup_handler(self.resource)
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=timeout)

            self.state = ResourceState.SHUTDOWN
            self.shutdown_duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Resource '{self.name}' shutdown in {self.shutdown_duration_ms:.1f}ms")
            return True

        except TimeoutError:
            self.state = ResourceState.ERROR
            self.last_error = f"Shutdown timed out after {timeout}s"
            logger.warning(f"Resource '{self.name}' shutdown timed out")
            return False

        except Exception as e:
            self.state = ResourceState.ERROR
            self.last_error = str(e)
            logger.error(f"Resource '{self.name}' shutdown failed: {e}")
            return False


class ResourceManager:
    """Centralized resource lifecycle manager."""

    def __init__(self):
        self._resources: dict[str, ManagedResource] = {}
        self._shutdown_order: list[str] = []
        self._lock = asyncio.Lock()
        self._is_shutting_down = False

    async def register(
        self,
        name: str,
        resource: Any,
        cleanup_handler: Callable | None = None,
        priority: int = 0,
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ManagedResource:
        """Register a resource for lifecycle management.

        Args:
            name: Unique resource name
            resource: The resource object
            cleanup_handler: Callable to cleanup the resource (can be async)
            priority: Shutdown priority (higher = shutdown first)
            depends_on: List of resource names this depends on
            metadata: Additional metadata

        Returns:
            ManagedResource wrapper

        Raises:
            ValueError: If resource with name already exists
        """
        async with self._lock:
            if name in self._resources:
                raise ValueError(f"Resource '{name}' already registered")

            managed = ManagedResource(
                name=name,
                resource=resource,
                cleanup_handler=cleanup_handler,
                priority=priority,
                depends_on=depends_on or [],
                state=ResourceState.ACTIVE,
                metadata=metadata or {},
            )

            self._resources[name] = managed
            self._shutdown_order.append(name)

            logger.info(f"Registered resource: {name}", extra={"resource": name, "priority": priority})

            return managed

    async def unregister(self, name: str, cleanup: bool = True) -> bool:
        """Unregister a resource, optionally cleaning it up.

        Args:
            name: Resource name
            cleanup: Whether to call cleanup handler

        Returns:
            True if resource was found and removed
        """
        async with self._lock:
            if name not in self._resources:
                return False

            managed = self._resources[name]

            if cleanup:
                await managed.shutdown()

            del self._resources[name]
            if name in self._shutdown_order:
                self._shutdown_order.remove(name)

            logger.debug(f"Unregistered resource: {name}")
            return True

    def get(self, name: str) -> Any | None:
        """Get a registered resource by name.

        Args:
            name: Resource name

        Returns:
            The resource or None if not found
        """
        managed = self._resources.get(name)
        return managed.resource if managed else None

    def get_managed(self, name: str) -> ManagedResource | None:
        """Get the ManagedResource wrapper by name."""
        return self._resources.get(name)

    async def shutdown_all(self, timeout: float = 30.0) -> dict[str, bool]:  # noqa: ASYNC109
        """Shutdown all resources gracefully.

        Resources are shutdown in reverse registration order,
        respecting dependencies and priorities.

        Args:
            timeout: Total timeout for all shutdowns

        Returns:
            Dict mapping resource names to shutdown success
        """
        if self._is_shutting_down:
            logger.warning("Shutdown already in progress")
            return {}

        self._is_shutting_down = True
        start_time = time.perf_counter()
        results: dict[str, bool] = {}

        logger.info(f"Shutting down {len(self._resources)} resources...")

        # Build shutdown order (reverse of registration, respecting priority)
        shutdown_order = self._build_shutdown_order()

        per_resource_timeout = timeout / max(1, len(shutdown_order))

        for name in shutdown_order:
            # Check if we've exceeded total timeout
            elapsed = time.perf_counter() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"Shutdown timeout reached, {len(shutdown_order) - len(results)} resources not cleaned up"
                )
                break

            remaining_timeout = timeout - elapsed
            resource_timeout = min(per_resource_timeout, remaining_timeout)

            managed = self._resources.get(name)
            if managed:
                success = await managed.shutdown(timeout=resource_timeout)
                results[name] = success

        total_time = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for v in results.values() if v)

        logger.info(f"Resource shutdown complete: {success_count}/{len(results)} successful in {total_time:.1f}ms")

        self._is_shutting_down = False
        return results

    def _build_shutdown_order(self) -> list[str]:
        """Build shutdown order respecting priorities and dependencies."""
        # Sort by priority (descending) then by reverse registration order
        resources = list(self._resources.values())
        resources.sort(key=lambda r: (-r.priority, -self._shutdown_order.index(r.name)))

        # Topological sort for dependencies
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            managed = self._resources.get(name)
            if managed:
                # Visit dependencies first (they should shutdown after)
                for dep in managed.depends_on:
                    if dep not in visited and dep in self._resources:
                        visit(dep)

            ordered.append(name)

        for resource in resources:
            visit(resource.name)

        return ordered

    def get_status(self) -> dict[str, Any]:
        """Get status of all managed resources."""
        return {
            "total": len(self._resources),
            "is_shutting_down": self._is_shutting_down,
            "resources": {
                name: {
                    "state": r.state.value,
                    "priority": r.priority,
                    "depends_on": r.depends_on,
                    "last_error": r.last_error,
                    "registered_at": r.registered_at,
                }
                for name, r in self._resources.items()
            },
        }

    def get_health(self) -> dict[str, str]:
        """Get health status of all resources."""
        return {
            name: "healthy" if r.state == ResourceState.ACTIVE else r.state.value for name, r in self._resources.items()
        }


# Global resource manager instance
_resource_manager: ResourceManager | None = None


def get_resource_manager() -> ResourceManager:
    """Get the global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager
