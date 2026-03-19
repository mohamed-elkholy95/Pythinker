"""
Podman Sandbox Adapter - Rootless container runtime for enhanced security.

Implements the Sandbox protocol using Podman instead of Docker.

Benefits over Docker:
- Rootless: No daemon running as root
- Daemonless: No single point of failure
- User namespace isolation: Container UID 0 maps to regular user
- Enhanced security: No privileged daemon attack surface
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

logger = logging.getLogger(__name__)


class PodmanSandbox:
    """
    Podman-based sandbox implementation.

    Uses Podman's rootless mode for enhanced security.
    Compatible with Docker images and Compose files.
    All blocking Podman API calls are wrapped in asyncio.to_thread().
    """

    def __init__(
        self,
        image: str,
        name_prefix: str = "sandbox",
        network: str | None = None,
    ):
        self.image = image
        self.name_prefix = name_prefix
        self.network = network

        try:
            from podman import PodmanClient

            self.client = PodmanClient()
            logger.info("Podman client initialized (rootless mode)")
        except ImportError:
            logger.error("podman-py package not installed. Install with: pip install podman-py")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Podman client: {e}", exc_info=True)
            raise

    async def create_container(
        self,
        container_id: str,
        env: dict[str, str] | None = None,
        resource_limits: dict[str, Any] | None = None,
    ) -> str:
        """Create rootless container with Podman."""
        memory_limit = resource_limits.get("mem_limit", "4g") if resource_limits else "4g"
        cpu_limit = resource_limits.get("nano_cpus", 1500000000) if resource_limits else 1500000000
        pids_limit = resource_limits.get("pids_limit", 300) if resource_limits else 300

        def _create():
            return self.client.containers.run(
                image=self.image,
                name=f"{self.name_prefix}-{container_id}",
                detach=True,
                auto_remove=False,
                environment=env or {},
                mem_limit=memory_limit,
                cpus=cpu_limit / 1_000_000_000,
                pids_limit=pids_limit,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"],
                network=self.network,
            )

        container = await asyncio.to_thread(_create)
        logger.info(
            f"Created rootless Podman container {container.id[:12]} (memory={memory_limit}, cpus={cpu_limit / 1e9:.1f})"
        )
        return container.id

    async def destroy_container(self, container_id: str, force: bool = True) -> None:
        """Destroy Podman container."""

        def _destroy():
            container = self.client.containers.get(container_id)
            container.remove(force=force)

        await asyncio.to_thread(_destroy)
        logger.info(f"Destroyed Podman container {container_id[:12]}")

    async def exec_command(self, container_id: str, command: list[str]) -> tuple[int, str]:
        """Execute command in Podman container."""

        def _exec():
            container = self.client.containers.get(container_id)
            result = container.exec_run(command)
            return result.exit_code, result.output.decode()

        return await asyncio.to_thread(_exec)

    async def get_container_status(self, container_id: str) -> str:
        """Get Podman container status."""

        def _status():
            container = self.client.containers.get(container_id)
            return container.status

        try:
            return await asyncio.to_thread(_status)
        except Exception as e:
            logger.error(f"Failed to get Podman container status: {e}")
            return "unknown"

    async def is_rootless(self) -> bool:
        """Check if Podman is running in rootless mode."""

        def _check():
            info = self.client.info()
            return info.get("host", {}).get("security", {}).get("rootless", False)

        try:
            return await asyncio.to_thread(_check)
        except Exception as e:
            logger.error(f"Failed to check rootless mode: {e}")
            return False

    async def get_resource_usage(self, container_id: str) -> dict[str, Any]:
        """Get container resource usage."""

        def _stats():
            container = self.client.containers.get(container_id)
            return container.stats(stream=False)

        try:
            stats = await asyncio.to_thread(_stats)
            return {
                "memory_usage_bytes": stats.get("memory_stats", {}).get("usage", 0),
                "memory_limit_bytes": stats.get("memory_stats", {}).get("limit", 0),
                "cpu_usage_percent": 0.0,
            }
        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")
            return {}


async def create_sandbox_adapter(settings) -> PodmanSandbox | DockerSandbox:
    """Create sandbox adapter based on available runtime.

    Prefers Podman (rootless) if available, falls back to Docker.
    """
    try:
        from podman import PodmanClient

        def _check_podman():
            client = PodmanClient()
            info = client.info()
            return info.get("host", {}).get("security", {}).get("rootless", False)

        is_rootless = await asyncio.to_thread(_check_podman)
        if is_rootless:
            logger.info("Using Podman rootless runtime")
            return PodmanSandbox(
                image=settings.sandbox_image,
                name_prefix=settings.sandbox_name_prefix,
                network=settings.sandbox_network,
            )
    except Exception as e:
        logger.debug(f"Podman not available or not rootless: {e}")

    logger.info("Using Docker runtime (Podman not available or not rootless)")
    from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

    return DockerSandbox(settings)
