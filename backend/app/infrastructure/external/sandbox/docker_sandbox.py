import asyncio
import contextlib
import io
import logging
import socket
import threading
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, BinaryIO, ClassVar

import docker
import httpx
from async_lru import alru_cache
from docker.errors import NotFound as DockerNotFound
from docker.types import Ulimit

from app.core.config import StreamingMode, get_settings
from app.core.prometheus_metrics import (
    sandbox_connection_attempts_total,
    sandbox_connection_failure_total,
    sandbox_warmup_duration,
)
from app.domain.external.browser import Browser
from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.domain.services.sandbox_security_policy_service import get_sandbox_security_policy
from app.infrastructure.external.browser.connection_pool import BrowserConnectionPool
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

logger = logging.getLogger(__name__)

# CDP health check timeout
CDP_HEALTH_CHECK_TIMEOUT = 10  # seconds
# Legacy constant - now configurable via settings
CDP_CONNECTION_RETRIES = 15


class DockerSandbox(Sandbox):
    def __init__(self, ip: str | None = None, container_name: str | None = None):
        """Initialize Docker sandbox and API interaction client"""
        settings = get_settings()
        # Resolve hostname to IP if needed (Chrome CDP requires IP, not hostname)
        raw_address = ip or settings.sandbox_address or "localhost"
        self.ip = self._resolve_to_ip(raw_address)
        self.base_url = f"http://{self.ip}:8080"
        self._cdp_url = f"http://{self.ip}:9222"
        self._framework_url = f"http://{self.ip}:{settings.sandbox_framework_port}"
        self._container_name = container_name
        self._background_tasks: set[asyncio.Task[Any]] = set()
        # Pool client name for HTTPClientPool
        self._pool_client_name = f"sandbox-{self.id}"
        # Progress callback for browser connection retry events
        self._browser_progress_callback: Callable[[str], Awaitable[None]] | None = None

    async def get_client(self):
        """Get HTTP client from connection pool.

        Phase 1: Connection pooling integration.
        Returns a managed client from HTTPClientPool for connection reuse.

        Returns:
            ManagedHTTPClient from the pool
        """
        from app.infrastructure.external.http_pool import HTTPClientConfig, HTTPClientPool

        settings = get_settings()

        # Inject shared secret header for sandbox API authentication (Phase 2 security)
        auth_headers: dict[str, str] = {}
        if settings.sandbox_api_secret:
            auth_headers["x-sandbox-secret"] = settings.sandbox_api_secret

        return await HTTPClientPool.get_client(
            name=self._pool_client_name,
            base_url=self.base_url,
            timeout=600.0,
            config=HTTPClientConfig(
                base_url=self.base_url,
                timeout=600.0,
                connect_timeout=10.0,
                read_timeout=600.0,
                write_timeout=30.0,
                pool_timeout=10.0,
                max_connections=10,  # Sandbox-specific limit
                max_keepalive_connections=5,
                keepalive_expiry=30.0,  # Keep connections alive longer for sandbox
                http2=settings.sandbox_http2_enabled,  # Phase 3: Controlled by feature flag
                headers=auth_headers,
            ),
        )

    def set_browser_progress_callback(self, callback: Callable[[str], Awaitable[None]] | None) -> None:
        """Set callback for browser connection retry progress events.

        Args:
            callback: Async callable that receives progress messages (e.g., "Retrying browser connection (1/3)...")
        """
        self._browser_progress_callback = callback

    @staticmethod
    def _normalize_address(address: str) -> str:
        """Strip scheme and port from an address, returning bare hostname or IP.

        SANDBOX_ADDRESS may be set to ``http://sandbox:8080`` (with scheme and
        port).  The sandbox constructor builds URLs as ``http://{ip}:8080``, so
        passing the raw value through would produce ``http://http://sandbox:8080:8080``.
        """
        addr = address.strip()
        # Strip scheme
        for prefix in ("https://", "http://"):
            if addr.lower().startswith(prefix):
                addr = addr[len(prefix) :]
                break
        # Strip port suffix (e.g. ":8080")
        if ":" in addr:
            addr = addr.rsplit(":", 1)[0]
        return addr

    @staticmethod
    def _resolve_to_ip(address: str) -> str:
        """Resolve hostname to IP address synchronously

        Args:
            address: Hostname or IP address (may include scheme/port)

        Returns:
            IP address
        """
        # Normalise first — SANDBOX_ADDRESS may contain scheme and port
        address = DockerSandbox._normalize_address(address)

        try:
            # Check if already an IP address
            socket.inet_pton(socket.AF_INET, address)
            return address
        except OSError:
            pass

        try:
            # Resolve hostname to IP
            return socket.gethostbyname(address)
        except Exception as e:
            logger.warning(f"Failed to resolve {address}, using as-is: {e}")
            return address

    @property
    def id(self) -> str:
        """Sandbox ID"""
        if not self._container_name:
            return "dev-sandbox"
        return self._container_name

    @property
    def cdp_url(self) -> str:
        return self._cdp_url

    @property
    def framework_url(self) -> str:
        return self._framework_url

    @staticmethod
    def _get_container_ip(container) -> str:
        """Get container IP address from network settings

        Args:
            container: Docker container instance

        Returns:
            Container IP address
        """
        # Get container network settings
        network_settings = container.attrs.get("NetworkSettings", {})
        ip_address = network_settings.get("IPAddress", "")

        # If default network has no IP, try to get IP from other networks
        if not ip_address and "Networks" in network_settings:
            networks = network_settings["Networks"]
            # Try to get IP from first available network
            for network_config in networks.values():
                if network_config.get("IPAddress"):
                    ip_address = network_config["IPAddress"]
                    break

        return ip_address

    @staticmethod
    def _create_task() -> "DockerSandbox":
        """Create a new Docker sandbox (static method)

        Args:
            image: Docker image name
            name_prefix: Container name prefix

        Returns:
            DockerSandbox instance
        """
        # Use configured default values
        settings = get_settings()

        image = settings.sandbox_image
        name_prefix = settings.sandbox_name_prefix
        container_name = f"{name_prefix}-{str(uuid.uuid4())[:8]}"

        try:
            # Create Docker client
            docker_client = docker.from_env()

            # Resolve security policy from centralized contract
            policy = get_sandbox_security_policy()

            # Build tmpfs dict from policy (append nosuid,nodev for hardening)
            tmpfs_dict: dict[str, str] = {}
            for mount_spec in policy.tmpfs_mounts:
                if ":" in mount_spec:
                    path, opts = mount_spec.split(":", 1)
                    tmpfs_dict[path.strip()] = f"{opts.strip()},nosuid,nodev"
                else:
                    tmpfs_dict[mount_spec.strip()] = "nosuid,nodev"

            security_opt = ["no-new-privileges:true"]
            # NOTE: Seccomp profiles are applied in docker-compose (file path
            # relative to compose context). The Docker API expects raw JSON or
            # an absolute host path — neither is available from inside the
            # backend container. Ephemeral containers are still hardened by
            # cap_drop=ALL, no-new-privileges, and resource limits.

            # Prepare container configuration
            # Build environment — mirror docker-compose sandbox service env vars
            # so ephemeral containers have full parity with static sandbox.
            container_env: dict[str, Any] = {
                "SERVICE_TIMEOUT_MINUTES": settings.sandbox_ttl_minutes,
                "CHROME_ARGS": settings.sandbox_chrome_args,
                "HTTPS_PROXY": settings.sandbox_https_proxy,
                "HTTP_PROXY": settings.sandbox_http_proxy,
                "NO_PROXY": settings.sandbox_no_proxy,
                "SANDBOX_STREAMING_MODE": str(settings.sandbox_streaming_mode),
            }
            # Optional secrets and tokens
            if settings.sandbox_api_secret:
                container_env["SANDBOX_API_SECRET"] = settings.sandbox_api_secret
            if settings.supervisor_rpc_password:
                container_env["SUPERVISOR_RPC_PASSWORD"] = settings.supervisor_rpc_password
            if settings.sandbox_chrome_args:
                container_env["CHROME_ARGS"] = settings.sandbox_chrome_args
            if settings.sandbox_gh_token:
                container_env["GH_TOKEN"] = settings.sandbox_gh_token
            if settings.sandbox_google_drive_token:
                container_env["GOOGLE_DRIVE_TOKEN"] = settings.sandbox_google_drive_token
            if settings.sandbox_google_workspace_token:
                container_env["GOOGLE_WORKSPACE_CLI_TOKEN"] = settings.sandbox_google_workspace_token
            if settings.sandbox_https_proxy:
                container_env["HTTPS_PROXY"] = settings.sandbox_https_proxy
            if settings.sandbox_http_proxy:
                container_env["HTTP_PROXY"] = settings.sandbox_http_proxy
            if settings.sandbox_no_proxy:
                container_env["NO_PROXY"] = settings.sandbox_no_proxy

            container_config = {
                "image": image,
                "name": container_name,
                "detach": True,
                "remove": True,
                "environment": container_env,
                # Identity labels for orphan reaper and lifecycle tracking
                "labels": {
                    "pythinker.managed": "true",
                    "pythinker.component": "sandbox",
                    "pythinker.lifecycle_mode": settings.sandbox_lifecycle_mode,
                },
                # Security hardening from centralized policy contract
                "security_opt": security_opt,
                "cap_drop": policy.cap_drop,
                "cap_add": policy.cap_add_allowlist,
                "tmpfs": tmpfs_dict,
                # nproc removed: redundant with cgroup pids_limit and scoped per-UID (moby/moby#31424)
                "ulimits": [Ulimit(name="nofile", soft=65536, hard=65536)],
                "shm_size": settings.sandbox_shm_size,
                "mem_limit": settings.sandbox_mem_limit,
                "nano_cpus": int((settings.sandbox_cpu_limit or 2.0) * 1_000_000_000),
                "pids_limit": settings.sandbox_pids_limit,
            }

            # Add network to container config if configured
            if settings.sandbox_network:
                container_config["network"] = settings.sandbox_network

            # Create container — if anything after this line fails we must clean up
            container = docker_client.containers.run(**container_config)

            try:
                # Get container IP address
                container.reload()  # Refresh container info
                ip_address = DockerSandbox._get_container_ip(container)

                # Create and return DockerSandbox instance
                return DockerSandbox(ip=ip_address, container_name=container_name)
            except Exception:
                # Prevent container orphaning: stop/remove the container on init failure
                with contextlib.suppress(Exception):
                    container.stop(timeout=5)
                with contextlib.suppress(Exception):
                    container.remove(force=True)
                raise

        except Exception as e:
            raise Exception(f"Failed to create Docker sandbox: {e!s}") from e

    async def _verify_cdp_connection(self) -> bool:
        """Verify Chrome DevTools Protocol connection is working

        Checks if the browser is accessible via CDP by requesting the version endpoint.

        Returns:
            bool: True if CDP connection is healthy, False otherwise
        """
        from app.infrastructure.external.http_pool import HTTPClientPool

        try:
            client = await HTTPClientPool.get_client(
                name=f"cdp-health-{self.id}",
                base_url=self._cdp_url,
                timeout=CDP_HEALTH_CHECK_TIMEOUT,
            )
            response = await client.get("/json/version")
            if response.status_code == 200:
                version_info = response.json()
                logger.debug(f"CDP connection verified: {version_info.get('Browser', 'Unknown browser')}")
                return True
            logger.warning(f"CDP version check returned status {response.status_code}")
            return False
        except Exception as e:
            logger.debug(f"CDP connection check failed: {e}")
            return False

    async def _verify_browser_responsive(self) -> bool:
        """Verify the browser is responsive by checking for available pages

        Returns:
            bool: True if browser has pages available, False otherwise
        """
        from app.infrastructure.external.http_pool import HTTPClientPool

        try:
            client = await HTTPClientPool.get_client(
                name=f"cdp-health-{self.id}",
                base_url=self._cdp_url,
                timeout=CDP_HEALTH_CHECK_TIMEOUT,
            )
            response = await client.get("/json/list")
            if response.status_code == 200:
                pages = response.json()
                # Browser should have at least one page (the default tab)
                if isinstance(pages, list) and len(pages) > 0:
                    logger.debug(f"Browser responsive with {len(pages)} page(s)")
                    return True
                logger.warning("Browser has no pages available")
                return False
            return False
        except Exception as e:
            logger.debug(f"Browser responsiveness check failed: {e}")
            return False

    async def _verify_cdp_with_backoff(self) -> bool:
        """Verify CDP connection with exponential backoff

        Uses configurable retry parameters for faster initial checks
        while still allowing for longer delays if needed.

        Returns:
            bool: True if CDP connection is healthy, False otherwise
        """
        settings = get_settings()
        delay = settings.sandbox_cdp_initial_delay
        max_delay = settings.sandbox_cdp_max_delay
        retries = settings.sandbox_cdp_retries

        for attempt in range(retries):
            if await self._verify_cdp_connection():
                logger.debug(f"CDP connection verified on attempt {attempt + 1}")
                return True
            if attempt < retries - 1:
                logger.debug(f"CDP connection attempt {attempt + 1} failed, retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)  # Exponential backoff with cap
        return False

    async def verify_browser_ready(self) -> bool:
        """Lightweight health check to verify browser is ready

        This can be run in parallel with other initialization tasks.
        Ensures Chrome is started on-demand before polling CDP.

        Returns:
            bool: True if browser is ready, False otherwise
        """
        # Trigger on-demand Chrome start before polling CDP.
        # Chrome has autostart=false in supervisord; without this call,
        # _verify_cdp_with_backoff() would poll a dead endpoint for 90s.
        await self._ensure_chrome_running()

        return await self._verify_cdp_with_backoff() and await self._verify_browser_responsive()

    async def browser_health_check(self) -> bool:
        """Quick browser health check for fast path verification.

        Phase 2 enhancement: Instant check for browser readiness without backoff.
        Used by fast path to determine if browser is ready for immediate use.

        Returns:
            bool: True if browser is healthy, False otherwise
        """
        try:
            # Single quick check - no retries (browser should already be pre-warmed)
            cdp_ok = await self._verify_cdp_connection()
            if not cdp_ok:
                return False
            return await self._verify_browser_responsive()
        except Exception as e:
            logger.debug(f"Browser health check failed: {e}")
            return False

    async def ensure_sandbox(self) -> None:
        """Ensure sandbox is ready by checking all services and browser health

        This method verifies:
        1. All supervisor services are RUNNING
        2. Chrome DevTools Protocol is accessible
        3. Browser is responsive and has pages available

        Uses a warmup grace period to avoid race conditions during container startup.

        Metrics are recorded ONCE per warmup session (not per retry attempt) to
        avoid inflating failure counts.
        """
        import time

        settings = get_settings()

        # Configurable warmup parameters (Phase 6: race condition fix)
        max_retries = 30  # Maximum number of retries
        warmup_grace_period = settings.sandbox_warmup_grace_period
        initial_retry_delay = settings.sandbox_warmup_initial_retry_delay
        max_retry_delay = settings.sandbox_warmup_max_retry_delay
        backoff_multiplier = settings.sandbox_warmup_backoff_multiplier
        connection_failure_threshold = settings.sandbox_warmup_connection_failure_threshold
        wall_clock_timeout = settings.sandbox_warmup_wall_clock_timeout  # 0 = disabled (IMPORTANT-6)

        # Record start time for warmup tracking
        start_time = time.time()

        # Try a fast probe first — if the sandbox is already healthy (e.g. static
        # reuse) we skip the grace period entirely.  For freshly-created containers
        # the probe will fail and we fall back to the grace-period sleep.
        try:
            async with asyncio.timeout(1.5):
                await self._check_supervisor_status()
                await self._verify_cdp_connection()
            logger.debug("Sandbox already healthy, skipping warmup grace period")
        except Exception:
            if warmup_grace_period > 0:
                logger.debug("Waiting %.1fs warmup grace period before first health check...", warmup_grace_period)
                await asyncio.sleep(warmup_grace_period)

        retry_delay = initial_retry_delay
        connection_failures = 0

        # Track warmup result for metrics (record once at end, not per retry)
        warmup_succeeded = False
        final_error_reason = "unknown"

        for attempt in range(max_retries):
            elapsed = time.time() - start_time

            # Enforce hard wall-clock budget when configured (IMPORTANT-6)
            if wall_clock_timeout > 0 and elapsed >= wall_clock_timeout:
                final_error_reason = "wall_clock_timeout"
                logger.error(
                    "Sandbox warmup exceeded wall-clock budget of %.1fs after %d attempt(s)",
                    wall_clock_timeout,
                    attempt,
                )
                break

            in_warmup_window = elapsed < 10.0  # More tolerant during first 10 seconds

            try:
                client = await self.get_client()
                response = await client.get(f"{self.base_url}/api/v1/supervisor/status")
                response.raise_for_status()

                # Reset connection failure counter on successful connection
                connection_failures = 0

                # Parse response as ToolResult
                tool_result = ToolResult(**response.json())

                if not tool_result.success:
                    logger.warning(f"Supervisor status check failed: {tool_result.message}")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)
                    continue

                services = tool_result.data or []
                if not services:
                    logger.warning("No services found in supervisor status")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)
                    continue

                # Check if all services are RUNNING
                # Note: runtime_init/context_generator/fix_permissions can exit after startup.
                all_running = True
                non_running_services = []
                expected_exit_services = {
                    "runtime_init",
                    "context_generator",
                    "fix_permissions",
                    # chrome_cdp_only can transiently restart during bootstrap.
                    "chrome_cdp_only",
                    "dbus",
                    # gh_auth_setup is a one-shot that exits after configuring git.
                    "gh_auth_setup",
                    # hide_x11_cursor is a one-shot that hides the X11 cursor
                    # via XFIXES extension and exits immediately.
                    "hide_x11_cursor",
                    # code_server is optional (disabled by default); enters
                    # FATAL when ENABLE_CODE_SERVER is unset/false.
                    "code_server",
                }

                # In CDP-only mode, VNC services are intentionally not started
                if settings.sandbox_streaming_mode == StreamingMode.CDP_ONLY:
                    expected_exit_services.update(
                        {
                            "chrome_dual",
                            "openbox",
                            "websockify",
                            "x11vnc",
                            "xrandr_setup",
                            "xvfb",
                        }
                    )

                for service in services:
                    service_name = service.get("name", "unknown")
                    state_name = service.get("statename", "")

                    # Allow EXITED/FATAL/STOPPED state for services expected to exit/restart.
                    if service_name in expected_exit_services:
                        if state_name not in ("EXITED", "RUNNING", "FATAL", "STOPPED"):
                            all_running = False
                            non_running_services.append(f"{service_name}({state_name})")
                    elif state_name != "RUNNING":
                        all_running = False
                        non_running_services.append(f"{service_name}({state_name})")

                if not all_running:
                    logger.info(
                        f"Waiting for services... Non-running: {', '.join(non_running_services)} (attempt {attempt + 1}/{max_retries}, {elapsed:.1f}s elapsed)"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)
                    continue

                # All services running - now verify browser health
                logger.debug("All supervisor services running, verifying browser health...")

                # Trigger on-demand Chrome start before polling CDP.
                # Chrome has autostart=false; without this, CDP checks
                # poll a dead endpoint until the retry budget is exhausted.
                await self._ensure_chrome_running()

                # Check CDP connection
                cdp_ok = await self._verify_cdp_connection()
                if not cdp_ok:
                    logger.info(f"CDP not ready yet (attempt {attempt + 1}/{max_retries}, {elapsed:.1f}s elapsed)")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)
                    continue

                # Check browser responsiveness
                browser_ok = await self._verify_browser_responsive()
                if not browser_ok:
                    logger.info(
                        f"Browser not responsive yet (attempt {attempt + 1}/{max_retries}, {elapsed:.1f}s elapsed)"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)
                    continue

                # Success! Mark warmup as succeeded
                warmup_succeeded = True
                logger.info(
                    f"Sandbox fully ready: {len(services)} services running, browser healthy (warmup took {elapsed:.1f}s)"
                )
                break  # Exit retry loop

            except httpx.ConnectError as e:
                # Connection refused — sandbox container is not reachable
                connection_failures += 1
                final_error_reason = "refused"

                if not await asyncio.to_thread(self._container_exists_and_running):
                    final_error_reason = "container_stopped"
                    elapsed = time.time() - start_time
                    logger.error("Sandbox container %s is no longer running", self._container_name)
                    # Record metrics before raising
                    sandbox_connection_attempts_total.inc({"result": "failure"})
                    sandbox_connection_failure_total.inc({"reason": final_error_reason})
                    sandbox_warmup_duration.observe({"status": "failure"}, elapsed)
                    raise RuntimeError(f"Sandbox container {self._container_name} is no longer running") from e

                # Be more tolerant during warmup window
                failure_threshold = connection_failure_threshold if in_warmup_window else 8

                if connection_failures >= failure_threshold:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"Sandbox unreachable after {connection_failures} connection attempts ({elapsed:.1f}s elapsed), giving up"
                    )
                    # Record metrics before raising
                    sandbox_connection_attempts_total.inc({"result": "failure"})
                    sandbox_connection_failure_total.inc({"reason": final_error_reason})
                    sandbox_warmup_duration.observe({"status": "failure"}, elapsed)
                    raise RuntimeError(f"Sandbox unreachable after {connection_failures} connection attempts") from e

                logger.warning(
                    f"Sandbox unreachable (attempt {attempt + 1}/{max_retries}, connection failure {connection_failures}/{failure_threshold}, {elapsed:.1f}s elapsed)"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)

            except httpx.TimeoutException as e:
                final_error_reason = "timeout"
                logger.warning(
                    f"Sandbox health check timed out (attempt {attempt + 1}/{max_retries}, {elapsed:.1f}s elapsed): {e!s}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)

            except Exception as e:
                # Generic failure (could be network error, parsing error, etc.)
                final_error_reason = "error"
                logger.warning(
                    f"Failed to check sandbox status (attempt {attempt + 1}/{max_retries}, {elapsed:.1f}s elapsed): {e!s}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * backoff_multiplier, max_retry_delay)

        # Record metrics once at the end (not per retry attempt)
        elapsed = time.time() - start_time

        if warmup_succeeded:
            # Success - record successful warmup
            sandbox_connection_attempts_total.inc({"result": "success"})
            sandbox_warmup_duration.observe({"status": "success"}, elapsed)
            return  # Success - all checks passed

        # Failure - exhausted all retries
        sandbox_connection_attempts_total.inc({"result": "failure"})
        sandbox_connection_failure_total.inc({"reason": final_error_reason})
        sandbox_warmup_duration.observe({"status": "failure"}, elapsed)

        error_message = f"Sandbox failed to become ready after {max_retries} attempts ({elapsed:.1f}s elapsed)"
        logger.error(error_message)
        raise RuntimeError(error_message)

    def _container_exists_and_running(self) -> bool:
        """Best-effort check to avoid retry storms for removed containers."""
        if not self._container_name:
            return True
        if self._container_name.startswith("dev-sandbox-"):
            # Static sandbox identifiers are long-lived and externally managed.
            return True
        try:
            dc = docker.from_env()
            container = dc.containers.get(self._container_name)
            container.reload()
            return container.status in {"running", "restarting", "paused"}
        except DockerNotFound:
            return False
        except Exception:
            # If Docker API is temporarily unavailable, fall back to retry logic.
            return True

    async def ensure_framework(self, session_id: str) -> None:
        """Initialize sandbox framework state for the session."""
        settings = get_settings()
        if not settings.sandbox_framework_enabled:
            return

        try:
            client = await self.get_client()
            response = await client.post(
                f"{self._framework_url}/api/v1/framework/bootstrap",
                json={"session_id": session_id},
            )
            response.raise_for_status()
        except Exception as e:
            message = f"Sandbox framework bootstrap failed for session {session_id}: {e}"
            if settings.sandbox_framework_required:
                raise RuntimeError(message) from e
            logger.warning(message)

    @staticmethod
    def _parse_tool_result(response: httpx.Response) -> ToolResult:
        """Parse an httpx response into a ToolResult, guarding against non-2xx status.

        Without this guard, a 404/500 from the sandbox API would produce
        ``ToolResult(**error_json)`` which raises AttributeError when the
        response body lacks the expected ``success``/``data`` keys.
        """
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", body.get("message", response.text[:200]))
            except Exception:
                detail = response.text[:200] if response.text else f"HTTP {response.status_code}"
            return ToolResult(
                success=False,
                message=f"Sandbox API error (HTTP {response.status_code}): {detail}",
            )
        return ToolResult(**response.json())

    @staticmethod
    def _normalize_sandbox_user_path(path: str) -> tuple[str, bool]:
        """Map ``/app/...`` to ``/workspace/...`` — models often confuse app code dir with user workspace.

        Allowed roots in the sandbox include ``/workspace``; ``/app`` is reserved and blocked.
        """
        if not path or not str(path).strip():
            return path, False
        normalized = str(path).replace("\\", "/").strip()
        if normalized == "/app" or normalized.startswith("/app/"):
            rest = normalized[5:] if normalized.startswith("/app/") else ""
            rest = rest.strip("/")
            mapped = f"/workspace/{rest}" if rest else "/workspace"
            return mapped, True
        return path, False

    def _remap_file_arg(self, path: str, *, kind: str) -> str:
        out, remapped = self._normalize_sandbox_user_path(path)
        if remapped:
            logger.debug("Sandbox %s path remapped: %s -> %s", kind, path, out)
        return out

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/shell/exec", json={"id": session_id, "exec_dir": exec_dir, "command": command}
        )
        return self._parse_tool_result(response)

    async def view_shell(self, session_id: str, console: bool = False) -> ToolResult:
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/shell/view", json={"id": session_id, "console": console})
        return self._parse_tool_result(response)

    async def wait_for_process(self, session_id: str, seconds: int | None = None) -> ToolResult:
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/shell/wait", json={"id": session_id, "seconds": seconds})
        return self._parse_tool_result(response)

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/shell/write",
            json={"id": session_id, "input": input_text, "press_enter": press_enter},
        )
        return self._parse_tool_result(response)

    async def kill_process(self, session_id: str) -> ToolResult:
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/shell/kill", json={"id": session_id})
        return self._parse_tool_result(response)

    async def stream_shell_output(self, session_id: str) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        """Stream real-time shell output via SSE from the sandbox.

        Connects to the sandbox's ``GET /api/v1/shell/stream/{session_id}``
        SSE endpoint and yields parsed ``(event_type, data)`` tuples.

        Event types:
          - ``"output"``: ``{"content": "<delta text>"}``
          - ``"complete"``: ``{"returncode": int}``
          - ``"heartbeat"``: ``{}``
          - ``"error"``: ``{"message": str}``

        Falls back gracefully: caller should catch ``httpx.HTTPStatusError``
        with status 404 to detect sandboxes that lack this endpoint.
        """
        import json as _json

        url = f"{self.base_url}/api/v1/shell/stream/{session_id}"

        # Build auth headers
        settings = get_settings()
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if settings.sandbox_api_secret:
            headers["x-sandbox-secret"] = settings.sandbox_api_secret

        sse_client = await self.get_client()
        async with (
            sse_client.stream("GET", url, headers=headers) as response,
        ):
            response.raise_for_status()

            event_type = ""
            data_buf = ""

            async for raw_line in response.aiter_lines():
                line = raw_line.rstrip("\n").rstrip("\r")

                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_buf = line[6:]
                elif line == "":
                    # Empty line = end of event
                    if event_type and data_buf:
                        try:
                            parsed = _json.loads(data_buf)
                        except _json.JSONDecodeError:
                            parsed = {"raw": data_buf}
                        yield (event_type, parsed)
                    event_type = ""
                    data_buf = ""

    async def file_write(
        self,
        file: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> ToolResult:
        """Write content to file

        Args:
            file: File path
            content: Content to write
            append: Whether to append content
            leading_newline: Whether to add newline before content
            trailing_newline: Whether to add newline after content
            sudo: Whether to use sudo privileges

        Returns:
            Result of write operation
        """
        file = self._remap_file_arg(file, kind="file_write")
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/file/write",
            json={
                "file": file,
                "content": content,
                "append": append,
                "leading_newline": leading_newline,
                "trailing_newline": trailing_newline,
                "sudo": sudo,
            },
        )
        return self._parse_tool_result(response)

    async def file_read(
        self, file: str, start_line: int | None = None, end_line: int | None = None, sudo: bool = False
    ) -> ToolResult:
        """Read file content

        Args:
            file: File path
            start_line: Start line number
            end_line: End line number
            sudo: Whether to use sudo privileges

        Returns:
            File content
        """
        file = self._remap_file_arg(file, kind="file_read")
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/file/read",
            json={"file": file, "start_line": start_line, "end_line": end_line, "sudo": sudo},
        )
        return self._parse_tool_result(response)

    async def file_exists(self, path: str) -> ToolResult:
        """Check if file exists

        Args:
            path: File path

        Returns:
            Whether file exists
        """
        path = self._remap_file_arg(path, kind="file_exists")
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/file/exists", json={"file": path})
        return self._parse_tool_result(response)

    async def file_delete(self, path: str) -> ToolResult:
        """Delete file

        Args:
            path: File path

        Returns:
            Result of delete operation
        """
        path = self._remap_file_arg(path, kind="file_delete")
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/file/delete", json={"path": path})
        return self._parse_tool_result(response)

    async def file_list(self, path: str) -> ToolResult:
        """List directory contents

        Args:
            path: Directory path

        Returns:
            List of directory contents
        """
        path = self._remap_file_arg(path, kind="file_list")
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/file/list", json={"path": path})
        return self._parse_tool_result(response)

    async def file_replace(self, file: str, old_str: str, new_str: str, sudo: bool = False) -> ToolResult:
        """Replace string in file

        Args:
            file: File path
            old_str: String to replace
            new_str: String to replace with
            sudo: Whether to use sudo privileges

        Returns:
            Result of replace operation
        """
        file = self._remap_file_arg(file, kind="file_replace")
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/file/replace",
            json={"file": file, "old_str": old_str, "new_str": new_str, "sudo": sudo},
        )
        return self._parse_tool_result(response)

    async def file_search(self, file: str, regex: str, sudo: bool = False) -> ToolResult:
        """Search in file content

        Args:
            file: File path
            regex: Regular expression
            sudo: Whether to use sudo privileges

        Returns:
            Search results
        """
        file = self._remap_file_arg(file, kind="file_search")
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/file/search", json={"file": file, "regex": regex, "sudo": sudo}
        )
        return self._parse_tool_result(response)

    async def file_find(self, path: str, glob_pattern: str) -> ToolResult:
        """Find files by name pattern

        Args:
            path: Search directory path
            glob_pattern: Glob match pattern

        Returns:
            List of found files
        """
        path = self._remap_file_arg(path, kind="file_find")
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/file/find", json={"path": path, "glob": glob_pattern})
        return self._parse_tool_result(response)

    async def file_upload(self, file_data: BinaryIO, path: str, filename: str | None = None) -> ToolResult:
        """Upload file to sandbox

        Args:
            file_data: File content as binary stream
            path: Target file path in sandbox
            filename: Original filename (optional)

        Returns:
            Upload operation result
        """
        # Validate required fields before making the API call to avoid an opaque
        # HTTP 422 / Pydantic "Field required" error from the sandbox service.
        if file_data is None:
            return ToolResult(success=False, message="file_upload: file_data is required and must not be None")
        if not path or not path.strip():
            return ToolResult(success=False, message="file_upload: path is required and must not be empty")

        path = self._remap_file_arg(path, kind="file_upload")

        # Prepare form data for upload
        files = {"file": (filename or "upload", file_data, "application/octet-stream")}
        data = {"path": path}

        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/file/upload", files=files, data=data)
        return self._parse_tool_result(response)

    async def file_download(self, path: str) -> BinaryIO:
        """Download file from sandbox

        Args:
            path: File path in sandbox

        Returns:
            File content as binary stream
        """
        path = self._remap_file_arg(path, kind="file_download")
        client = await self.get_client()
        response = await client.get(f"{self.base_url}/api/v1/file/download", params={"path": path})
        response.raise_for_status()

        # Return the response content as a BinaryIO stream
        # TODO: change to real stream
        return io.BytesIO(response.content)

    # Workspace management methods
    async def workspace_init(
        self, session_id: str, project_name: str = "project", template: str = "none"
    ) -> ToolResult:
        """Initialize a workspace for a session"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/workspace/init",
            json={"session_id": session_id, "project_name": project_name, "template": template},
        )
        return self._parse_tool_result(response)

    async def workspace_info(self, session_id: str) -> ToolResult:
        """Get workspace information"""
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/workspace/info", json={"session_id": session_id})
        return self._parse_tool_result(response)

    async def workspace_tree(self, session_id: str, depth: int = 3, include_hidden: bool = False) -> ToolResult:
        """Get workspace directory tree"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/workspace/tree",
            json={"session_id": session_id, "depth": depth, "include_hidden": include_hidden},
        )
        return self._parse_tool_result(response)

    async def workspace_clean(self, session_id: str, preserve_config: bool = True) -> ToolResult:
        """Clean workspace contents"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/workspace/clean",
            json={"session_id": session_id, "preserve_config": preserve_config},
        )
        return self._parse_tool_result(response)

    async def workspace_exists(self, session_id: str) -> ToolResult:
        """Check if workspace exists"""
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/workspace/exists", json={"session_id": session_id})
        return self._parse_tool_result(response)

    # Git operations
    async def git_clone(
        self, url: str, target_dir: str, branch: str | None = None, shallow: bool = True, auth_token: str | None = None
    ) -> ToolResult:
        """Clone a git repository"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/git/clone",
            json={"url": url, "target_dir": target_dir, "branch": branch, "shallow": shallow, "auth_token": auth_token},
        )
        return self._parse_tool_result(response)

    async def git_status(self, repo_path: str) -> ToolResult:
        """Get git repository status"""
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/git/status", json={"repo_path": repo_path})
        return self._parse_tool_result(response)

    async def git_diff(self, repo_path: str, staged: bool = False, file_path: str | None = None) -> ToolResult:
        """Get git diff"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/git/diff", json={"repo_path": repo_path, "staged": staged, "file_path": file_path}
        )
        return self._parse_tool_result(response)

    async def git_log(self, repo_path: str, limit: int = 10, file_path: str | None = None) -> ToolResult:
        """Get git commit history"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/git/log", json={"repo_path": repo_path, "limit": limit, "file_path": file_path}
        )
        return self._parse_tool_result(response)

    async def git_branches(self, repo_path: str, show_remote: bool = True) -> ToolResult:
        """Get git branches"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/git/branches", json={"repo_path": repo_path, "show_remote": show_remote}
        )
        return self._parse_tool_result(response)

    # Code development operations
    async def code_format(self, file_path: str, formatter: str = "auto", check_only: bool = False) -> ToolResult:
        """Format a code file"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/code/format",
            json={"file_path": file_path, "formatter": formatter, "check_only": check_only},
        )
        return self._parse_tool_result(response)

    async def code_lint(self, path: str, linter: str = "auto", fix: bool = False) -> ToolResult:
        """Lint code files"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/code/lint", json={"path": path, "linter": linter, "fix": fix}
        )
        return self._parse_tool_result(response)

    async def code_analyze(self, path: str, analysis_type: str = "all") -> ToolResult:
        """Analyze code"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/code/analyze", json={"path": path, "analysis_type": analysis_type}
        )
        return self._parse_tool_result(response)

    async def code_search(
        self, directory: str, pattern: str, file_glob: str = "*", context_lines: int = 2, max_results: int = 100
    ) -> ToolResult:
        """Search code files"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/code/search",
            json={
                "directory": directory,
                "pattern": pattern,
                "file_glob": file_glob,
                "context_lines": context_lines,
                "max_results": max_results,
            },
        )
        return self._parse_tool_result(response)

    # Test execution operations
    async def test_run(
        self,
        path: str,
        framework: str = "auto",
        pattern: str | None = None,
        coverage: bool = False,
        timeout: int = 300,  # noqa: ASYNC109
        verbose: bool = False,
    ) -> ToolResult:
        """Run tests"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/test/run",
            json={
                "path": path,
                "framework": framework,
                "pattern": pattern,
                "coverage": coverage,
                "timeout": timeout,
                "verbose": verbose,
            },
        )
        return self._parse_tool_result(response)

    async def test_list(self, path: str, framework: str = "auto") -> ToolResult:
        """List available tests"""
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/test/list", json={"path": path, "framework": framework})
        return self._parse_tool_result(response)

    async def test_coverage(self, path: str, output_format: str = "html", output_dir: str | None = None) -> ToolResult:
        """Generate coverage report"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/test/coverage",
            json={"path": path, "output_format": output_format, "output_dir": output_dir},
        )
        return self._parse_tool_result(response)

    # Export operations
    async def export_organize(self, session_id: str, source_path: str, target_category: str = "other") -> ToolResult:
        """Organize files"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/export/organize",
            json={"session_id": session_id, "source_path": source_path, "target_category": target_category},
        )
        return self._parse_tool_result(response)

    async def export_archive(
        self,
        session_id: str,
        name: str,
        include_patterns: list | None = None,
        exclude_patterns: list | None = None,
        base_path: str | None = None,
    ) -> ToolResult:
        """Create archive"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/export/archive",
            json={
                "session_id": session_id,
                "name": name,
                "include_patterns": include_patterns,
                "exclude_patterns": exclude_patterns,
                "base_path": base_path,
            },
        )
        return self._parse_tool_result(response)

    async def export_report(
        self,
        session_id: str,
        report_type: str = "summary",
        output_format: str = "markdown",
        title: str = "Workspace Report",
    ) -> ToolResult:
        """Generate report"""
        client = await self.get_client()
        response = await client.post(
            f"{self.base_url}/api/v1/export/report",
            json={"session_id": session_id, "report_type": report_type, "output_format": output_format, "title": title},
        )
        return self._parse_tool_result(response)

    async def export_list(self, session_id: str) -> ToolResult:
        """List exports"""
        client = await self.get_client()
        response = await client.post(f"{self.base_url}/api/v1/export/list", json={"session_id": session_id})
        return self._parse_tool_result(response)

    @staticmethod
    @alru_cache(maxsize=128, typed=True)
    async def _resolve_hostname_to_ip(hostname: str) -> str:
        """Resolve hostname to IP address

        Args:
            hostname: Hostname to resolve (may include scheme/port)

        Returns:
            Resolved IP address, or None if resolution fails

        Note:
            This method is cached using LRU cache with a maximum size of 128 entries.
            The cache helps reduce repeated DNS lookups for the same hostname.
        """
        # Normalise: SANDBOX_ADDRESS may contain scheme and port
        hostname = DockerSandbox._normalize_address(hostname)

        try:
            # First check if hostname is already in IP address format
            try:
                socket.inet_pton(socket.AF_INET, hostname)
                # If successfully parsed, it's an IPv4 address format, return directly
                return hostname
            except OSError:
                # Not a valid IP address format, proceed with DNS resolution
                pass

            # Use socket.getaddrinfo for DNS resolution
            addr_info = socket.getaddrinfo(hostname, None, family=socket.AF_INET)
            # Return the first IPv4 address found
            if addr_info and len(addr_info) > 0:
                return addr_info[0][4][
                    0
                ]  # Return sockaddr[0] from (family, type, proto, canonname, sockaddr), which is the IP address
            logger.warning(f"No addresses found for hostname {hostname}, using as-is")
            return hostname
        except Exception as e:
            # Log error and return hostname as-is instead of None
            logger.error(f"Failed to resolve hostname {hostname}: {e!s}, using as-is")
            return hostname

    async def destroy(self) -> bool:
        """Destroy Docker sandbox and release all browser pool connections."""
        try:
            settings = get_settings()
            uses_static_sandboxes = bool(
                getattr(
                    settings,
                    "uses_static_sandbox_addresses",
                    bool(getattr(settings, "sandbox_address", None)),
                )
            )

            # Force-release browser pool connections for this sandbox's CDP URL
            # to prevent connection pool exhaustion on subsequent sessions
            try:
                pool = BrowserConnectionPool.get_instance()
                released = await pool.force_release_all(self._cdp_url)
                if released > 0:
                    logger.info(f"Force-released {released} browser pool connections for {self._cdp_url}")
            except Exception as e:
                logger.debug(f"Browser pool cleanup skipped: {e}")

            # Invalidate LRU cache so future get() calls create a fresh instance
            if hasattr(DockerSandbox.get, "cache_invalidate"):
                if self._container_name:
                    DockerSandbox.get.cache_invalidate(self._container_name)
                else:
                    DockerSandbox.get.cache_clear()

            # Phase 1: Close HTTP client from pool instead of direct aclose()
            # This allows the pool to properly cleanup and reuse connections
            try:
                from app.infrastructure.external.http_pool import HTTPClientPool

                closed = await HTTPClientPool.close_client(self._pool_client_name)
                if closed:
                    logger.debug(f"Closed HTTP pool client for sandbox {self.id}")
            except Exception as e:
                logger.debug(f"HTTP pool client cleanup skipped: {e}")

            is_static_sandbox_id = bool(
                uses_static_sandboxes and self._container_name and self._container_name.startswith("dev-sandbox-")
            )

            if self._container_name and not is_static_sandbox_id:

                def _remove_container(name: str) -> None:
                    dc = docker.from_env()
                    try:
                        dc.containers.get(name).remove(force=True)
                    except DockerNotFound:
                        # Idempotent cleanup: container may already be removed by
                        # another cleanup path.
                        logger.info(f"Docker sandbox container already removed: {name}")

                await asyncio.to_thread(_remove_container, self._container_name)
            elif is_static_sandbox_id:
                logger.debug(
                    "Skipping container removal for static sandbox mode (sandbox=%s)",
                    self._container_name,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to destroy Docker sandbox: {e!s}")
            return False

    async def force_destroy(self) -> bool:
        """Force-remove sandbox container with best-effort dependency cleanup."""
        settings = get_settings()
        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )
        is_static_sandbox_id = bool(
            uses_static_sandboxes and self._container_name and self._container_name.startswith("dev-sandbox-")
        )

        # Best-effort browser pool + HTTP client cleanup even in force path.
        with contextlib.suppress(Exception):
            pool = BrowserConnectionPool.get_instance()
            await pool.force_release_all(self._cdp_url)
        with contextlib.suppress(Exception):
            from app.infrastructure.external.http_pool import HTTPClientPool

            await HTTPClientPool.close_client(self._pool_client_name)

        if hasattr(DockerSandbox.get, "cache_invalidate"):
            with contextlib.suppress(Exception):
                if self._container_name:
                    DockerSandbox.get.cache_invalidate(self._container_name)
                else:
                    DockerSandbox.get.cache_clear()

        if not self._container_name or is_static_sandbox_id:
            if is_static_sandbox_id:
                logger.debug(
                    "Skipping force destroy for static sandbox mode (sandbox=%s)",
                    self._container_name,
                )
            return True

        def _force_remove_container(name: str) -> None:
            dc = docker.from_env()
            try:
                dc.containers.get(name).remove(force=True)
            except DockerNotFound:
                logger.info("Docker sandbox container already removed during force destroy: %s", name)

        try:
            await asyncio.to_thread(_force_remove_container, self._container_name)
            logger.warning("Force-removed Docker sandbox container: %s", self._container_name)
            return True
        except Exception as e:
            logger.error("Failed to force-destroy Docker sandbox %s: %s", self._container_name, e)
            return False

    async def pause(self) -> bool:
        """Pause container to reclaim CPU while preserving memory state."""
        if not self._container_name:
            return False
        try:

            def _pause(name: str) -> None:
                dc = docker.from_env()
                container = dc.containers.get(name)
                if container.status == "running":
                    container.pause()

            await asyncio.to_thread(_pause, self._container_name)
            logger.info(f"Paused sandbox container: {self._container_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to pause sandbox {self._container_name}: {e}")
            return False

    async def unpause(self) -> bool:
        """Unpause a paused container, resuming all processes."""
        if not self._container_name:
            return False
        try:

            def _unpause(name: str) -> None:
                dc = docker.from_env()
                container = dc.containers.get(name)
                if container.status == "paused":
                    container.unpause()

            await asyncio.to_thread(_unpause, self._container_name)
            logger.info(f"Unpaused sandbox container: {self._container_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to unpause sandbox {self._container_name}: {e}")
            return False

    @property
    def is_paused(self) -> bool:
        """Check if container is currently paused (synchronous, best-effort)."""
        if not self._container_name:
            return False
        try:
            dc = docker.from_env()
            container = dc.containers.get(self._container_name)
            return container.status == "paused"
        except Exception:
            return False

    async def get_screenshot(self, quality: int = 75, scale: float = 0.5, format: str = "jpeg") -> httpx.Response:
        """Capture desktop screenshot for thumbnail preview.

        Args:
            quality: JPEG quality (1-100, default 75)
            scale: Scale factor (0.1-1.0, default 0.5)
            format: Image format (jpeg or png, default jpeg)

        Returns:
            HTTP response with image bytes
        """
        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.base_url}/api/v1/screenshot",
                params={"quality": quality, "scale": scale, "format": format},
                timeout=10.0,
            )
            response.raise_for_status()
            return response
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            raise

    async def _ensure_chrome_running(self) -> None:
        """Request the sandbox to ensure Chrome is running (on-demand lifecycle).

        No-op when chrome_on_demand is disabled.  Idempotent — safe to call
        before every browser operation.
        """
        settings = get_settings()
        if not getattr(settings, "chrome_on_demand", False):
            return

        try:
            client = await self.get_client()
            timeout = getattr(settings, "chrome_ensure_timeout", 35.0)
            resp = await client.post(
                "/api/v1/browser/ensure",
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Chrome ensure returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
            else:
                data = resp.json().get("data", {})
                if data.get("cold_start"):
                    logger.info(
                        "Chrome cold-started in %sms for sandbox %s",
                        data.get("startup_ms"),
                        self.id,
                    )
        except Exception as e:
            logger.warning("Chrome ensure failed for sandbox %s: %s", self.id, e)

    async def get_browser(
        self,
        block_resources: bool = True,
        verify_connection: bool = True,
        clear_session: bool = False,
        use_pool: bool = True,
    ) -> Browser:
        """Get browser instance with optional connection verification and pooling.

        Args:
            block_resources: Whether to enable resource blocking for faster page loads
            verify_connection: Whether to verify CDP connection before returning (default: True)
            clear_session: If True, clear all existing tabs for a fresh session
            use_pool: Whether to use connection pooling (default: True for performance)

        Returns:
            Browser: Returns a configured PlaywrightBrowser instance
                    connected using the sandbox's CDP URL

        Raises:
            Exception: If verify_connection is True and connection cannot be established
        """
        # Ensure Chrome is running (on-demand lifecycle — no-op if disabled)
        await self._ensure_chrome_running()

        settings = get_settings()
        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )
        browser_pool_enabled = bool(getattr(settings, "browser_pool_enabled", True))
        effective_use_pool = use_pool and browser_pool_enabled and not uses_static_sandboxes

        if verify_connection and not await self._verify_cdp_with_backoff():
            # Verify CDP is accessible before creating browser instance
            # Uses exponential backoff for faster initial checks
            raise Exception(f"Failed to verify CDP connection after {settings.sandbox_cdp_retries} attempts")

        if effective_use_pool:
            # Use connection pool for efficient browser reuse
            return await self._get_pooled_browser(block_resources, clear_session)
        if use_pool and not effective_use_pool and uses_static_sandboxes:
            logger.debug("Browser pool bypassed for static SANDBOX_ADDRESS mode on %s", self.id)

        # Legacy: Create new browser instance without pooling
        browser = PlaywrightBrowser(cdp_url=self.cdp_url, block_resources=block_resources)

        # Protocol: Clear browser state for new sessions
        if clear_session and browser:
            await browser.clear_session()
            logger.info("Browser session cleared for new chat")

        return browser

    async def _get_pooled_browser(
        self,
        block_resources: bool = True,
        clear_session: bool = False,
        session_id: str | None = None,
    ) -> Browser:
        """Get a browser from the connection pool with robust error handling.

        The connection pool manages browser lifecycle, health checking,
        and efficient reuse of connections across requests.

        Args:
            block_resources: Whether to enable resource blocking
            clear_session: If True, clear all existing tabs for a fresh session
            session_id: Optional session ID for error context

        Returns:
            Browser: A pooled PlaywrightBrowser instance

        Raises:
            ConnectionPoolExhaustedError: When all connections are in use
            ConnectionTimeoutError: When connection attempt times out
            BrowserCrashedError: When browser initialization fails
        """
        from app.domain.exceptions.browser import (
            BrowserError,
            ConnectionPoolExhaustedError,
        )

        pool = await BrowserConnectionPool.get_instance_async()

        try:
            # Acquire from pool with proper error context
            connection = await pool._acquire_connection(
                cdp_url=self.cdp_url,
                block_resources=block_resources,
                session_id=session_id,
                sandbox_id=self.id,
                progress_callback=self._browser_progress_callback,
            )

            logger.debug(f"Acquired pooled browser for {self.cdp_url} (use count: {connection.use_count})")

            # Clear browser session if requested (e.g., for new chat sessions)
            if clear_session and connection.browser:
                await connection.browser.clear_session()
                logger.info("Cleared browser tabs for new session")

            return connection.browser

        except ConnectionPoolExhaustedError:
            # Log detailed pool stats for debugging
            pool_stats = pool.get_stats()
            logger.error(
                f"Connection pool exhausted for sandbox {self.id}",
                extra={
                    "cdp_url": self.cdp_url,
                    "session_id": session_id,
                    "pool_stats": pool_stats,
                },
            )

            # Attempt recovery: force release stale connections and retry once
            logger.info("Attempting recovery: forcing cleanup of all stale connections")
            cleaned = await pool.clear_stale_connections(self.cdp_url)
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} stale connections, retrying acquisition")
                try:
                    connection = await pool._acquire_connection(
                        cdp_url=self.cdp_url,
                        block_resources=block_resources,
                        session_id=session_id,
                        sandbox_id=self.id,
                        progress_callback=self._browser_progress_callback,
                    )
                    return connection.browser
                except ConnectionPoolExhaustedError:
                    pass  # Fall through to raise original error

            raise

        except BrowserError as e:
            logger.error(
                f"Browser error getting pooled browser: {e}",
                extra={
                    "error_code": e.code.value,
                    "cdp_url": self.cdp_url,
                    "session_id": session_id,
                    "recoverable": e.recoverable,
                },
            )
            raise

        except Exception as e:
            logger.error(f"Unexpected error getting pooled browser: {e}")
            raise

    async def release_pooled_browser(self, browser: Browser, had_error: bool = False) -> bool:
        """Release a pooled browser back to the pool.

        Should be called when done with a pooled browser to allow reuse.
        If had_error is True, the connection will be marked as potentially
        unhealthy and may be replaced.

        Args:
            browser: The browser instance to release
            had_error: Whether an error occurred during use of this browser
        Returns:
            True if the browser was found and released from the pool, False otherwise.
        """
        pool = BrowserConnectionPool.get_instance()

        # Find and release the connection
        for cdp_url, connections in pool._pools.items():
            for conn in connections:
                if conn.browser is browser:
                    await pool._release_connection(cdp_url, conn, had_error=had_error)
                    logger.debug(f"Released pooled browser for {cdp_url}" + (" (with error)" if had_error else ""))
                    return True

        logger.debug("Could not find browser in pool to release")
        return False

    # Round-robin counter for multi-sandbox dev mode
    _sandbox_rr_index: int = 0
    # threading.Lock for atomic read+increment of round-robin index.
    # Use threading.Lock (not asyncio.Lock) because the critical section
    # is synchronous (no await) and must be safe across concurrent coroutines.
    _sandbox_rr_lock: ClassVar[threading.Lock] = threading.Lock()
    # Sandbox → session ownership map (sandbox_address → session_id)
    _active_sessions: ClassVar[dict[str, str]] = {}
    # asyncio.Lock for session dict mutations. Callers are async methods,
    # so asyncio.Lock correctly serialises within a single event loop.
    _active_sessions_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def register_session(cls, sandbox_address: str, session_id: str) -> str | None:
        """Register a session as owning a sandbox address.

        Thread-safe: uses asyncio.Lock to serialise concurrent access
        to the shared ``_active_sessions`` dict.

        Returns the previous session_id if one was registered.
        Caller should check has_active_stream() before calling to avoid
        stealing sandboxes from active sessions.
        """
        async with cls._active_sessions_lock:
            previous = cls._active_sessions.get(sandbox_address)
            cls._active_sessions[sandbox_address] = session_id
            if previous and previous != session_id:
                logger.info(f"Sandbox {sandbox_address} reassigned: {previous} -> {session_id}")
            return previous if previous and previous != session_id else None

    @classmethod
    async def unregister_session(cls, sandbox_address: str, session_id: str | None = None) -> None:
        """Unregister a session from a sandbox address.

        Thread-safe: uses asyncio.Lock to serialise concurrent access
        to the shared ``_active_sessions`` dict.
        """
        async with cls._active_sessions_lock:
            current = cls._active_sessions.get(sandbox_address)
            if session_id is None or current == session_id:
                cls._active_sessions.pop(sandbox_address, None)
                logger.debug(f"Unregistered session from sandbox {sandbox_address}")

    @classmethod
    async def get_session_for_sandbox(cls, sandbox_address: str) -> str | None:
        """Get the session currently assigned to a sandbox address.

        Thread-safe: uses asyncio.Lock to serialise concurrent access
        to the shared ``_active_sessions`` dict.
        """
        async with cls._active_sessions_lock:
            return cls._active_sessions.get(sandbox_address)

    @classmethod
    async def create(cls) -> Sandbox:
        """Create a new sandbox instance

        Supports comma-separated sandbox addresses for concurrent dev sessions
        (e.g. SANDBOX_ADDRESS=sandbox,sandbox2). Uses round-robin allocation.

        Returns:
            New sandbox instance
        """
        settings = get_settings()

        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )

        if uses_static_sandboxes and settings.sandbox_address:
            addresses = [a.strip() for a in settings.sandbox_address.split(",") if a.strip()]
            # Atomic read+increment with threading.Lock to prevent concurrent
            # create() calls from receiving the same sandbox address.
            with cls._sandbox_rr_lock:
                address = addresses[cls._sandbox_rr_index % len(addresses)]
                cls._sandbox_rr_index += 1
            # Normalise: strip scheme/port so container name stays clean
            hostname = cls._normalize_address(address)
            ip = await cls._resolve_hostname_to_ip(hostname)
            container_name = f"dev-sandbox-{hostname}"
            logger.info(f"Assigned dev sandbox '{hostname}' (IP: {ip}) via round-robin")
            return DockerSandbox(ip=ip, container_name=container_name)

        return await asyncio.to_thread(DockerSandbox._create_task)

    @classmethod
    @alru_cache(maxsize=128, typed=True)
    async def get(cls, id: str) -> Sandbox:
        """Get sandbox by ID

        Args:
            id: Sandbox ID

        Returns:
            Sandbox instance
        """
        settings = get_settings()
        uses_static_sandboxes = bool(
            getattr(
                settings,
                "uses_static_sandbox_addresses",
                bool(getattr(settings, "sandbox_address", None)),
            )
        )
        if uses_static_sandboxes and settings.sandbox_address:
            # For multi-sandbox dev mode, extract hostname from container_name
            # Container names are "dev-sandbox-{hostname}" where hostname is normalised
            addresses = [a.strip() for a in settings.sandbox_address.split(",") if a.strip()]
            # Try to match the sandbox ID to a known normalised address
            for addr in addresses:
                hostname = cls._normalize_address(addr)
                if id == f"dev-sandbox-{hostname}":
                    ip = await cls._resolve_hostname_to_ip(hostname)
                    return DockerSandbox(ip=ip, container_name=id)
            # Fallback: use first address (normalised)
            ip = await cls._resolve_hostname_to_ip(addresses[0])
            return DockerSandbox(ip=ip, container_name=id)

        def _get_container_ip_sync() -> str:
            dc = docker.from_env()
            c = dc.containers.get(id)
            c.reload()
            return cls._get_container_ip(c)

        ip_address = await asyncio.to_thread(_get_container_ip_sync)
        logger.info(f"IP address: {ip_address}")
        return DockerSandbox(ip=ip_address, container_name=id)
