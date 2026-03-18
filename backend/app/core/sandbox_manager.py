"""
Enhanced Sandbox Manager with Robust Error Handling
Provides reliable sandbox lifecycle management with automatic recovery.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import docker
from docker.models.containers import Container

from app.core.async_utils import gather_compat
from app.core.config import get_settings
from app.core.error_manager import (
    CircuitBreaker,
    ErrorCategory,
    ErrorSeverity,
    error_context,
    error_handler,
)
from app.core.retry import sandbox_retry
from app.infrastructure.external.http_pool import HTTPClientPool, ManagedHTTPClient

logger = logging.getLogger(__name__)


class SandboxState(str, Enum):
    """Sandbox states"""

    CREATING = "creating"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"
    FAILED = "failed"
    DESTROYED = "destroyed"


@dataclass
class SandboxHealth:
    """Sandbox health status"""

    api_responsive: bool = False
    browser_responsive: bool = False
    last_check: datetime | None = None

    @property
    def is_healthy(self) -> bool:
        """Check if sandbox is considered healthy"""
        return self.api_responsive and self.browser_responsive


@dataclass
class SandboxMetrics:
    """Sandbox performance metrics"""

    creation_time: float = 0.0
    startup_time: float = 0.0
    health_check_failures: int = 0
    recovery_attempts: int = 0
    last_activity: datetime = None


class EnhancedSandboxManager:
    """Enhanced sandbox manager with comprehensive error handling"""

    def __init__(self):
        self.settings = get_settings()
        self._sandboxes: dict[str, ManagedSandbox] = {}
        self._circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self._health_check_interval = 30  # seconds
        self._max_recovery_attempts = 3
        self._background_tasks: set[asyncio.Task] = set()
        # Per-session locks prevent duplicate-sandbox races (HIGH-4).
        # _session_locks and _locks_mutex are not used inside the lock itself,
        # so there is no deadlock risk.
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()

    @error_handler(severity=ErrorSeverity.CRITICAL, category=ErrorCategory.SANDBOX, auto_recover=True)
    async def create_sandbox(self, session_id: str) -> Optional["ManagedSandbox"]:
        """Create a new sandbox with comprehensive error handling"""

        if not self._circuit_breaker.can_execute():
            logger.warning("Sandbox creation blocked by circuit breaker")
            return None

        async with error_context(
            component="SandboxManager",
            operation="create_sandbox",
            session_id=session_id,
            category=ErrorCategory.SANDBOX,
            severity=ErrorSeverity.CRITICAL,
        ):
            start_time = time.time()

            try:
                # Create sandbox instance
                sandbox = ManagedSandbox(session_id, self)
                await sandbox.create()

                # Track creation time
                sandbox.metrics.creation_time = time.time() - start_time

                # Store in registry
                self._sandboxes[session_id] = sandbox

                # Start health monitoring
                task = asyncio.create_task(self._monitor_sandbox_health(sandbox))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

                self._circuit_breaker.record_success()
                logger.info(f"Sandbox created successfully for session {session_id}")

                return sandbox

            except Exception as e:
                self._circuit_breaker.record_failure()
                logger.error(f"Failed to create sandbox for session {session_id}: {e}")
                raise

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Return (creating if necessary) the per-session lock for *session_id*."""
        async with self._locks_mutex:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def get_sandbox(self, session_id: str) -> Optional["ManagedSandbox"]:
        """Get existing sandbox or create new one.

        A per-session lock ensures that concurrent callers for the same session
        cannot both observe a missing/unhealthy sandbox and each create one,
        which would result in duplicate containers (HIGH-4 race condition fix).
        """
        lock = await self._get_session_lock(session_id)
        async with lock:
            sandbox = self._sandboxes.get(session_id)

            if sandbox and sandbox.state == SandboxState.HEALTHY:
                return sandbox
            if sandbox and sandbox.state in [SandboxState.UNHEALTHY, SandboxState.FAILED]:
                # Attempt recovery
                if await self._recover_sandbox(sandbox):
                    return sandbox
                # Create new sandbox if recovery fails
                await self.destroy_sandbox(session_id)
                return await self.create_sandbox(session_id)
            # Create new sandbox
            return await self.create_sandbox(session_id)

    @error_handler(severity=ErrorSeverity.MEDIUM, category=ErrorCategory.SANDBOX, auto_recover=False)
    async def destroy_sandbox(self, session_id: str) -> bool:
        """Destroy sandbox with error handling"""
        sandbox = self._sandboxes.get(session_id)
        if not sandbox:
            return True

        try:
            await sandbox.destroy()
            self._sandboxes.pop(session_id, None)
            # Evict the per-session lock so the lock map doesn't grow indefinitely
            async with self._locks_mutex:
                self._session_locks.pop(session_id, None)
            logger.info(f"Sandbox destroyed for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to destroy sandbox for session {session_id}: {e}")
            return False

    async def _monitor_sandbox_health(self, sandbox: "ManagedSandbox"):
        """Monitor sandbox health continuously"""
        while sandbox.state not in [SandboxState.DESTROYED, SandboxState.FAILED]:
            try:
                await asyncio.sleep(self._health_check_interval)

                if sandbox.state == SandboxState.DESTROYED:
                    break

                # Perform health check
                is_healthy = await sandbox.health_check()

                if not is_healthy:
                    sandbox.metrics.health_check_failures += 1

                    if sandbox.metrics.health_check_failures >= 3:
                        sandbox.state = SandboxState.UNHEALTHY
                        logger.warning(f"Sandbox {sandbox.session_id} marked as unhealthy")

                        # Attempt recovery
                        await self._recover_sandbox(sandbox)
                else:
                    # Reset failure count on successful health check
                    sandbox.metrics.health_check_failures = 0
                    if sandbox.state == SandboxState.UNHEALTHY:
                        sandbox.state = SandboxState.HEALTHY
                        logger.info(f"Sandbox {sandbox.session_id} recovered to healthy state")

            except Exception as e:
                logger.error(f"Health monitoring error for sandbox {sandbox.session_id}: {e}")

    async def _recover_sandbox(self, sandbox: "ManagedSandbox") -> bool:
        """Attempt to recover an unhealthy sandbox"""
        if sandbox.metrics.recovery_attempts >= self._max_recovery_attempts:
            logger.error(f"Max recovery attempts reached for sandbox {sandbox.session_id}")
            sandbox.state = SandboxState.FAILED
            return False

        sandbox.state = SandboxState.RECOVERING
        sandbox.metrics.recovery_attempts += 1

        try:
            # Attempt recovery strategies
            recovery_strategies = [
                sandbox._restart_services,
                sandbox._recreate_container,
            ]

            for strategy in recovery_strategies:
                try:
                    logger.info(f"Attempting recovery strategy: {strategy.__name__}")
                    if await strategy():
                        sandbox.state = SandboxState.HEALTHY
                        logger.info(f"Sandbox {sandbox.session_id} recovered successfully")
                        return True
                except Exception as e:
                    logger.warning(f"Recovery strategy {strategy.__name__} failed: {e}")

            sandbox.state = SandboxState.FAILED
            return False

        except Exception as e:
            logger.error(f"Recovery failed for sandbox {sandbox.session_id}: {e}")
            sandbox.state = SandboxState.FAILED
            return False

    async def shutdown(self) -> None:
        """Cancel and await all background health-monitor tasks (HIGH-3).

        Must be called during application shutdown to prevent orphaned tasks
        from running after the event loop is torn down.
        """
        tasks = list(self._background_tasks)
        if not tasks:
            return
        logger.info("Shutting down %d sandbox health-monitor task(s)", len(tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        logger.info("Sandbox manager shutdown complete")

    def get_sandbox_stats(self) -> dict[str, Any]:
        """Get sandbox statistics"""
        total_sandboxes = len(self._sandboxes)
        healthy_sandboxes = len([s for s in self._sandboxes.values() if s.state == SandboxState.HEALTHY])

        return {
            "total_sandboxes": total_sandboxes,
            "healthy_sandboxes": healthy_sandboxes,
            "unhealthy_sandboxes": total_sandboxes - healthy_sandboxes,
            "circuit_breaker_state": self._circuit_breaker.state,
            "average_creation_time": sum(s.metrics.creation_time for s in self._sandboxes.values())
            / max(total_sandboxes, 1),
        }


class ManagedSandbox:
    """Enhanced sandbox with health monitoring and recovery"""

    def __init__(self, session_id: str, manager: EnhancedSandboxManager):
        self.session_id = session_id
        self.manager = manager
        self.state = SandboxState.CREATING
        self.health = SandboxHealth()
        self.metrics = SandboxMetrics()

        # Docker resources
        self.container: Container | None = None
        self.container_name: str | None = None
        self.ip_address: str | None = None

        # API clients (managed by HTTPClientPool)
        self.api_client: ManagedHTTPClient | None = None

    async def create(self):
        """Create and start the sandbox container"""
        try:
            self.state = SandboxState.CREATING

            # Generate container name
            import uuid

            self.container_name = f"{self.manager.settings.sandbox_name_prefix}-{str(uuid.uuid4())[:8]}"

            # Container configuration (built before thread to capture state)
            container_config = self._get_container_config()

            # Run blocking Docker SDK calls in a thread to avoid blocking the event loop
            def _create_container():
                client = docker.from_env()
                container = client.containers.run(**container_config)
                container.reload()
                return container

            self.container = await asyncio.to_thread(_create_container)
            self.ip_address = self._get_container_ip()

            # Initialize API client via connection pool
            self.api_client = await HTTPClientPool.get_client(
                name=f"sandbox-{self.session_id}",
                base_url=f"http://{self.ip_address}:8080",
                timeout=30.0,
            )

            # Wait for services to start
            self.state = SandboxState.STARTING
            await self._wait_for_services()

            self.state = SandboxState.HEALTHY
            self.metrics.last_activity = datetime.now(UTC)

        except Exception as e:
            self.state = SandboxState.FAILED
            logger.error(f"Failed to create sandbox {self.session_id}: {e}")
            raise

    def _get_container_config(self) -> dict[str, Any]:
        """Get Docker container configuration"""
        settings = self.manager.settings

        return {
            "image": settings.sandbox_image,
            "name": self.container_name,
            "detach": True,
            "remove": True,
            "environment": {
                "SERVICE_TIMEOUT_MINUTES": settings.sandbox_ttl_minutes,
                "CHROME_ARGS": settings.sandbox_chrome_args or "",
            },
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "cap_add": ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"],
            "tmpfs": {
                "/run": "size=50M,nosuid,nodev",
                "/tmp": "size=300M,nosuid,nodev",
                "/home/ubuntu/.cache": "size=150M,nosuid,nodev",
            },
            "shm_size": settings.sandbox_shm_size,
            "mem_limit": settings.sandbox_mem_limit,
            "nano_cpus": int((settings.sandbox_cpu_limit or 2.0) * 1_000_000_000),
            "pids_limit": settings.sandbox_pids_limit,
            "network": settings.sandbox_network,
        }

    def _get_container_ip(self) -> str:
        """Get container IP address"""
        network_settings = self.container.attrs.get("NetworkSettings", {})
        ip_address = network_settings.get("IPAddress", "")

        if not ip_address and "Networks" in network_settings:
            networks = network_settings["Networks"]
            for network_config in networks.values():
                if network_config.get("IPAddress"):
                    ip_address = network_config["IPAddress"]
                    break

        if not ip_address:
            raise Exception("Could not determine container IP address")

        return ip_address

    async def _wait_for_services(self, timeout: int = 60):  # noqa: ASYNC109
        """Wait for sandbox services to become available"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.health_check():
                self.metrics.startup_time = time.time() - start_time
                return

            await asyncio.sleep(2)

        raise Exception(f"Sandbox services did not start within {timeout} seconds")

    async def health_check(self) -> bool:
        """Perform comprehensive health check with parallel execution.

        Phase 3 enhancement: Run all health checks concurrently to reduce
        total check time from ~15s (sequential) to ~2-3s (parallel).

        Phase 1 (Agent Enhancement): Uses TaskGroup-based gather when feature flag
        is enabled for better cancellation and exception handling.
        """
        try:
            self.health.last_check = datetime.now(UTC)

            # Check if TaskGroup feature is enabled
            settings = get_settings()
            use_taskgroup = settings.feature_taskgroup_enabled

            # Run all health checks in parallel for faster response
            api_task = asyncio.create_task(self._check_api_health())
            browser_task = asyncio.create_task(self._check_browser_health())
            health_tasks: list[asyncio.Task[Any]] = [api_task, browser_task]

            # Wait for all checks with individual exception handling
            # Use TaskGroup-based gather if feature flag enabled
            results = await gather_compat(
                *health_tasks,
                return_exceptions=True,
                use_taskgroup=use_taskgroup,
            )

            # Process results (handle exceptions as False)
            self.health.api_responsive = results[0] is True
            self.health.browser_responsive = results[1] is True

            # Log any exceptions that occurred
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    check_names = ["API", "Browser"]
                    logger.debug(f"{check_names[i]} health check exception: {result}")

            return self.health.is_healthy

        except Exception as e:
            logger.warning(f"Health check failed for sandbox {self.session_id}: {e}")
            return False

    @sandbox_retry
    async def _check_api_health(self) -> bool:
        """Check if sandbox API is responsive.

        Phase 3 enhancement: Reduced timeout from 5s to 2s for faster checks.
        Uses @sandbox_retry (3 attempts, 2-30s backoff) for transient failures.
        """
        response = await self.api_client.get("/health", timeout=2.0)
        return response.status_code == 200

    @sandbox_retry
    async def _check_browser_health(self) -> bool:
        """Check if browser is responsive.

        Phase 3 enhancement: Reduced timeout from 5s to 2s for faster checks.
        Uses @sandbox_retry (3 attempts, 2-30s backoff) for transient failures.
        """
        client = await HTTPClientPool.get_client(
            name=f"sandbox-browser-{self.session_id}",
            base_url=f"http://{self.ip_address}:9222",
            timeout=2.0,
        )
        response = await client.get("/json/version")
        return response.status_code == 200

    async def _restart_services(self) -> bool:
        """Restart sandbox services"""
        try:
            # Restart container (blocking SDK call → thread pool)
            container = self.container
            await asyncio.to_thread(container.restart)
            await asyncio.sleep(10)  # Wait for restart

            # Wait for services
            await self._wait_for_services(timeout=30)
            return True
        except Exception as e:
            logger.error(f"Failed to restart services for sandbox {self.session_id}: {e}")
            return False

    async def _recreate_container(self) -> bool:
        """Recreate the container"""
        try:
            # Destroy current container
            await self.destroy()

            # Create new container
            await self.create()
            return True
        except Exception as e:
            logger.error(f"Failed to recreate container for sandbox {self.session_id}: {e}")
            return False

    async def destroy(self):
        """Destroy the sandbox"""
        try:
            self.state = SandboxState.DESTROYED

            # Close pool-managed clients for this sandbox
            await HTTPClientPool.close_client(f"sandbox-{self.session_id}")
            await HTTPClientPool.close_client(f"sandbox-browser-{self.session_id}")
            self.api_client = None

            if self.container:
                container = self.container
                await asyncio.to_thread(container.stop, timeout=10)
                await asyncio.to_thread(container.remove, force=True)

        except Exception as e:
            logger.warning(f"Error during sandbox destruction for {self.session_id}: {e}")


# Global sandbox manager instance
_sandbox_manager = EnhancedSandboxManager()


def get_sandbox_manager() -> EnhancedSandboxManager:
    """Get the global sandbox manager instance"""
    return _sandbox_manager
