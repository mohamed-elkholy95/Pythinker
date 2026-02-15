"""
Podman Sandbox Adapter - Rootless container runtime for enhanced security.

Implements the Sandbox protocol using Podman instead of Docker.

Benefits over Docker:
- Rootless: No daemon running as root
- Daemonless: No single point of failure
- User namespace isolation: Container UID 0 maps to regular user
- Enhanced security: No privileged daemon attack surface
"""

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
    """

    def __init__(
        self,
        image: str,
        name_prefix: str = "sandbox",
        network: str | None = None,
    ):
        """
        Initialize Podman sandbox adapter.

        Args:
            image: Container image name
            name_prefix: Container name prefix
            network: Pod network name
        """
        self.image = image
        self.name_prefix = name_prefix
        self.network = network

        # Try to import podman library
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
        """
        Create rootless container with Podman.

        Args:
            container_id: Container ID/name
            env: Environment variables
            resource_limits: Resource limits (memory, CPU, PIDs)

        Returns:
            Container ID
        """
        try:
            # Convert resource limits to Podman format
            memory_limit = resource_limits.get("mem_limit", "4g") if resource_limits else "4g"
            cpu_limit = resource_limits.get("nano_cpus", 1500000000) if resource_limits else 1500000000
            pids_limit = resource_limits.get("pids_limit", 300) if resource_limits else 300

            # Podman run command (rootless)
            container = self.client.containers.run(
                image=self.image,
                name=f"{self.name_prefix}-{container_id}",
                detach=True,
                auto_remove=False,
                environment=env or {},
                # Resource limits
                mem_limit=memory_limit,
                cpus=cpu_limit / 1_000_000_000,  # Convert nano CPUs to CPUs
                pids_limit=pids_limit,
                # Security options
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"],
                # Network
                network=self.network,
            )

            logger.info(
                f"Created rootless Podman container {container.id[:12]} "
                f"(memory={memory_limit}, cpus={cpu_limit / 1e9:.1f})"
            )

            return container.id

        except Exception as e:
            logger.error(f"Failed to create Podman container: {e}", exc_info=True)
            raise

    async def destroy_container(self, container_id: str, force: bool = True) -> None:
        """
        Destroy Podman container.

        Args:
            container_id: Container ID
            force: Force removal
        """
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)

            logger.info(f"Destroyed Podman container {container_id[:12]}")

        except Exception as e:
            logger.error(f"Failed to destroy Podman container {container_id}: {e}")
            raise

    async def exec_command(self, container_id: str, command: list[str]) -> tuple[int, str]:
        """
        Execute command in Podman container.

        Args:
            container_id: Container ID
            command: Command to execute

        Returns:
            Tuple of (exit_code, output)
        """
        try:
            container = self.client.containers.get(container_id)
            result = container.exec_run(command)

            return result.exit_code, result.output.decode()

        except Exception as e:
            logger.error(f"Failed to exec in Podman container: {e}")
            raise

    async def get_container_status(self, container_id: str) -> str:
        """
        Get Podman container status.

        Args:
            container_id: Container ID

        Returns:
            Status string ("running", "stopped", etc.)
        """
        try:
            container = self.client.containers.get(container_id)
            return container.status

        except Exception as e:
            logger.error(f"Failed to get Podman container status: {e}")
            return "unknown"

    def is_rootless(self) -> bool:
        """
        Check if Podman is running in rootless mode.

        Returns:
            True if rootless, False otherwise
        """
        try:
            info = self.client.info()
            # Podman info includes rootless status
            return info.get("host", {}).get("security", {}).get("rootless", False)

        except Exception as e:
            logger.error(f"Failed to check rootless mode: {e}")
            return False

    async def get_resource_usage(self, container_id: str) -> dict[str, Any]:
        """
        Get container resource usage.

        Args:
            container_id: Container ID

        Returns:
            Resource usage dict
        """
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)

            # Parse stats (format similar to Docker)
            return {
                "memory_usage_bytes": stats.get("memory_stats", {}).get("usage", 0),
                "memory_limit_bytes": stats.get("memory_stats", {}).get("limit", 0),
                "cpu_usage_percent": 0.0,  # TODO: Calculate from stats
            }

        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")
            return {}


# Migration helper: Detect runtime and create appropriate adapter
async def create_sandbox_adapter(settings) -> "PodmanSandbox | DockerSandbox":
    """
    Create sandbox adapter based on available runtime.

    Prefers Podman (rootless) if available, falls back to Docker.

    Args:
        settings: Application settings

    Returns:
        Sandbox adapter (Podman or Docker)
    """
    try:
        # Try Podman first
        from podman import PodmanClient

        client = PodmanClient()
        info = client.info()

        if info.get("host", {}).get("security", {}).get("rootless", False):
            logger.info("Using Podman rootless runtime")
            return PodmanSandbox(
                image=settings.sandbox_image,
                name_prefix=settings.sandbox_name_prefix,
                network=settings.sandbox_network,
            )

    except Exception as e:
        logger.debug(f"Podman not available or not rootless: {e}")

    # Fall back to Docker
    logger.info("Using Docker runtime (Podman not available or not rootless)")
    from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

    return DockerSandbox(settings)
