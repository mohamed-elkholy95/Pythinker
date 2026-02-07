import asyncio
import io
import logging
import socket
import uuid
from typing import BinaryIO

import docker
import httpx
from async_lru import alru_cache
from docker.types import Ulimit

from app.core.config import get_settings
from app.domain.external.browser import Browser
from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
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
        self._client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=600)
        # Resolve hostname to IP if needed (Chrome CDP requires IP, not hostname)
        raw_address = ip or settings.sandbox_address or "localhost"
        self.ip = self._resolve_to_ip(raw_address)
        self.base_url = f"http://{self.ip}:8080"
        self._vnc_url = f"ws://{self.ip}:5901"
        self._cdp_url = f"http://{self.ip}:9222"
        self._framework_url = f"http://{self.ip}:{settings.sandbox_framework_port}"
        self._container_name = container_name

    @property
    def client(self) -> httpx.AsyncClient:
        """Auto-healing httpx client — recreates if closed or None."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=600)
        return self._client

    @client.setter
    def client(self, value: httpx.AsyncClient | None) -> None:
        self._client = value

    @staticmethod
    def _resolve_to_ip(address: str) -> str:
        """Resolve hostname to IP address synchronously

        Args:
            address: Hostname or IP address

        Returns:
            IP address
        """
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
    def vnc_url(self) -> str:
        return self._vnc_url

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
            for _network_name, network_config in networks.items():
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

            # Prepare container configuration
            container_config = {
                "image": image,
                "name": container_name,
                "detach": True,
                "remove": True,
                "environment": {
                    "SERVICE_TIMEOUT_MINUTES": settings.sandbox_ttl_minutes,
                    "CHROME_ARGS": settings.sandbox_chrome_args,
                    "HTTPS_PROXY": settings.sandbox_https_proxy,
                    "HTTP_PROXY": settings.sandbox_http_proxy,
                    "NO_PROXY": settings.sandbox_no_proxy,
                },
                # Security hardening (aligned with docker-compose defaults)
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "cap_add": ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"],
                "tmpfs": {
                    "/run": "size=100M,nosuid,nodev",
                    "/tmp": "size=500M,nosuid,nodev",
                    "/home/ubuntu/.cache": "size=200M,nosuid,nodev",
                },
                "ulimits": [Ulimit(name="nofile", soft=65536, hard=65536), Ulimit(name="nproc", soft=4096, hard=8192)],
                "shm_size": settings.sandbox_shm_size,
                "mem_limit": settings.sandbox_mem_limit,
                "nano_cpus": int((settings.sandbox_cpu_limit or 2.0) * 1_000_000_000),
                "pids_limit": settings.sandbox_pids_limit,
            }

            # Optional seccomp profile (host path)
            if settings.sandbox_seccomp_profile:
                container_config["security_opt"].append(f"seccomp={settings.sandbox_seccomp_profile}")

            # Add network to container config if configured
            if settings.sandbox_network:
                container_config["network"] = settings.sandbox_network

            # Create container
            container = docker_client.containers.run(**container_config)

            # Get container IP address
            container.reload()  # Refresh container info
            ip_address = DockerSandbox._get_container_ip(container)

            # Create and return DockerSandbox instance
            return DockerSandbox(ip=ip_address, container_name=container_name)

        except Exception as e:
            raise Exception(f"Failed to create Docker sandbox: {e!s}") from e

    async def _verify_cdp_connection(self) -> bool:
        """Verify Chrome DevTools Protocol connection is working

        Checks if the browser is accessible via CDP by requesting the version endpoint.

        Returns:
            bool: True if CDP connection is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=CDP_HEALTH_CHECK_TIMEOUT) as client:
                response = await client.get(f"{self._cdp_url}/json/version")
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
        try:
            async with httpx.AsyncClient(timeout=CDP_HEALTH_CHECK_TIMEOUT) as client:
                response = await client.get(f"{self._cdp_url}/json/list")
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

        Returns:
            bool: True if browser is ready, False otherwise
        """
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
        """
        max_retries = 30  # Maximum number of retries
        retry_interval = 2  # Seconds between retries

        for attempt in range(max_retries):
            try:
                response = await self.client.get(f"{self.base_url}/api/v1/supervisor/status")
                response.raise_for_status()

                # Parse response as ToolResult
                tool_result = ToolResult(**response.json())

                if not tool_result.success:
                    logger.warning(f"Supervisor status check failed: {tool_result.message}")
                    await asyncio.sleep(retry_interval)
                    continue

                services = tool_result.data or []
                if not services:
                    logger.warning("No services found in supervisor status")
                    await asyncio.sleep(retry_interval)
                    continue

                # Check if all services are RUNNING
                # Note: context_generator is expected to EXITED (runs once at startup)
                all_running = True
                non_running_services = []
                expected_exit_services = {"context_generator", "xrandr_setup"}

                for service in services:
                    service_name = service.get("name", "unknown")
                    state_name = service.get("statename", "")

                    # Allow EXITED state for services that are expected to exit
                    if service_name in expected_exit_services:
                        if state_name not in ("EXITED", "RUNNING"):
                            all_running = False
                            non_running_services.append(f"{service_name}({state_name})")
                    elif state_name != "RUNNING":
                        all_running = False
                        non_running_services.append(f"{service_name}({state_name})")

                if not all_running:
                    logger.info(
                        f"Waiting for services... Non-running: {', '.join(non_running_services)} (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_interval)
                    continue

                # All services running - now verify browser health
                logger.debug("All supervisor services running, verifying browser health...")

                # Check CDP connection
                cdp_ok = await self._verify_cdp_connection()
                if not cdp_ok:
                    logger.info(f"CDP not ready yet (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_interval)
                    continue

                # Check browser responsiveness
                browser_ok = await self._verify_browser_responsive()
                if not browser_ok:
                    logger.info(f"Browser not responsive yet (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_interval)
                    continue

                logger.info(f"Sandbox fully ready: {len(services)} services running, browser healthy")
                return  # Success - all checks passed

            except httpx.ConnectError:
                # Connection refused — sandbox container is not reachable, reduce retries
                if attempt >= 5:
                    logger.error(f"Sandbox unreachable after {attempt + 1} attempts, giving up")
                    return
                logger.warning(f"Sandbox unreachable (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_interval)
            except Exception as e:
                logger.warning(f"Failed to check sandbox status (attempt {attempt + 1}/{max_retries}): {e!s}")
                await asyncio.sleep(retry_interval)

        # If we reach here, we've exhausted all retries
        error_message = (
            f"Sandbox failed to become ready after {max_retries} attempts ({max_retries * retry_interval} seconds)"
        )
        logger.error(error_message)

    async def ensure_framework(self, session_id: str) -> None:
        """Initialize sandbox framework state for the session."""
        settings = get_settings()
        if not settings.sandbox_framework_enabled:
            return

        try:
            response = await self.client.post(
                f"{self._framework_url}/api/v1/framework/bootstrap",
                json={"session_id": session_id},
            )
            response.raise_for_status()
        except Exception as e:
            message = f"Sandbox framework bootstrap failed for session {session_id}: {e}"
            if settings.sandbox_framework_required:
                raise RuntimeError(message) from e
            logger.warning(message)

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        response = await self.client.post(
            f"{self.base_url}/api/v1/shell/exec", json={"id": session_id, "exec_dir": exec_dir, "command": command}
        )
        return ToolResult(**response.json())

    async def view_shell(self, session_id: str, console: bool = False) -> ToolResult:
        response = await self.client.post(
            f"{self.base_url}/api/v1/shell/view", json={"id": session_id, "console": console}
        )
        return ToolResult(**response.json())

    async def wait_for_process(self, session_id: str, seconds: int | None = None) -> ToolResult:
        response = await self.client.post(
            f"{self.base_url}/api/v1/shell/wait", json={"id": session_id, "seconds": seconds}
        )
        return ToolResult(**response.json())

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        response = await self.client.post(
            f"{self.base_url}/api/v1/shell/write",
            json={"id": session_id, "input": input_text, "press_enter": press_enter},
        )
        return ToolResult(**response.json())

    async def kill_process(self, session_id: str) -> ToolResult:
        response = await self.client.post(f"{self.base_url}/api/v1/shell/kill", json={"id": session_id})
        return ToolResult(**response.json())

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
        response = await self.client.post(
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
        return ToolResult(**response.json())

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
        response = await self.client.post(
            f"{self.base_url}/api/v1/file/read",
            json={"file": file, "start_line": start_line, "end_line": end_line, "sudo": sudo},
        )
        return ToolResult(**response.json())

    async def file_exists(self, path: str) -> ToolResult:
        """Check if file exists

        Args:
            path: File path

        Returns:
            Whether file exists
        """
        response = await self.client.post(f"{self.base_url}/api/v1/file/exists", json={"path": path})
        return ToolResult(**response.json())

    async def file_delete(self, path: str) -> ToolResult:
        """Delete file

        Args:
            path: File path

        Returns:
            Result of delete operation
        """
        response = await self.client.post(f"{self.base_url}/api/v1/file/delete", json={"path": path})
        return ToolResult(**response.json())

    async def file_list(self, path: str) -> ToolResult:
        """List directory contents

        Args:
            path: Directory path

        Returns:
            List of directory contents
        """
        response = await self.client.post(f"{self.base_url}/api/v1/file/list", json={"path": path})
        return ToolResult(**response.json())

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
        response = await self.client.post(
            f"{self.base_url}/api/v1/file/replace",
            json={"file": file, "old_str": old_str, "new_str": new_str, "sudo": sudo},
        )
        return ToolResult(**response.json())

    async def file_search(self, file: str, regex: str, sudo: bool = False) -> ToolResult:
        """Search in file content

        Args:
            file: File path
            regex: Regular expression
            sudo: Whether to use sudo privileges

        Returns:
            Search results
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/file/search", json={"file": file, "regex": regex, "sudo": sudo}
        )
        return ToolResult(**response.json())

    async def file_find(self, path: str, glob_pattern: str) -> ToolResult:
        """Find files by name pattern

        Args:
            path: Search directory path
            glob_pattern: Glob match pattern

        Returns:
            List of found files
        """
        response = await self.client.post(
            f"{self.base_url}/api/v1/file/find", json={"path": path, "glob": glob_pattern}
        )
        return ToolResult(**response.json())

    async def file_upload(self, file_data: BinaryIO, path: str, filename: str | None = None) -> ToolResult:
        """Upload file to sandbox

        Args:
            file_data: File content as binary stream
            path: Target file path in sandbox
            filename: Original filename (optional)

        Returns:
            Upload operation result
        """
        # Prepare form data for upload
        files = {"file": (filename or "upload", file_data, "application/octet-stream")}
        data = {"path": path}

        response = await self.client.post(f"{self.base_url}/api/v1/file/upload", files=files, data=data)
        return ToolResult(**response.json())

    async def file_download(self, path: str) -> BinaryIO:
        """Download file from sandbox

        Args:
            path: File path in sandbox

        Returns:
            File content as binary stream
        """
        response = await self.client.get(f"{self.base_url}/api/v1/file/download", params={"path": path})
        response.raise_for_status()

        # Return the response content as a BinaryIO stream
        # TODO: change to real stream
        return io.BytesIO(response.content)

    # Workspace management methods
    async def workspace_init(
        self, session_id: str, project_name: str = "project", template: str = "none"
    ) -> ToolResult:
        """Initialize a workspace for a session"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/workspace/init",
            json={"session_id": session_id, "project_name": project_name, "template": template},
        )
        return ToolResult(**response.json())

    async def workspace_info(self, session_id: str) -> ToolResult:
        """Get workspace information"""
        response = await self.client.post(f"{self.base_url}/api/v1/workspace/info", json={"session_id": session_id})
        return ToolResult(**response.json())

    async def workspace_tree(self, session_id: str, depth: int = 3, include_hidden: bool = False) -> ToolResult:
        """Get workspace directory tree"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/workspace/tree",
            json={"session_id": session_id, "depth": depth, "include_hidden": include_hidden},
        )
        return ToolResult(**response.json())

    async def workspace_clean(self, session_id: str, preserve_config: bool = True) -> ToolResult:
        """Clean workspace contents"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/workspace/clean",
            json={"session_id": session_id, "preserve_config": preserve_config},
        )
        return ToolResult(**response.json())

    async def workspace_exists(self, session_id: str) -> ToolResult:
        """Check if workspace exists"""
        response = await self.client.post(f"{self.base_url}/api/v1/workspace/exists", json={"session_id": session_id})
        return ToolResult(**response.json())

    # Git operations
    async def git_clone(
        self, url: str, target_dir: str, branch: str | None = None, shallow: bool = True, auth_token: str | None = None
    ) -> ToolResult:
        """Clone a git repository"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/git/clone",
            json={"url": url, "target_dir": target_dir, "branch": branch, "shallow": shallow, "auth_token": auth_token},
        )
        return ToolResult(**response.json())

    async def git_status(self, repo_path: str) -> ToolResult:
        """Get git repository status"""
        response = await self.client.post(f"{self.base_url}/api/v1/git/status", json={"repo_path": repo_path})
        return ToolResult(**response.json())

    async def git_diff(self, repo_path: str, staged: bool = False, file_path: str | None = None) -> ToolResult:
        """Get git diff"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/git/diff", json={"repo_path": repo_path, "staged": staged, "file_path": file_path}
        )
        return ToolResult(**response.json())

    async def git_log(self, repo_path: str, limit: int = 10, file_path: str | None = None) -> ToolResult:
        """Get git commit history"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/git/log", json={"repo_path": repo_path, "limit": limit, "file_path": file_path}
        )
        return ToolResult(**response.json())

    async def git_branches(self, repo_path: str, show_remote: bool = True) -> ToolResult:
        """Get git branches"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/git/branches", json={"repo_path": repo_path, "show_remote": show_remote}
        )
        return ToolResult(**response.json())

    # Code development operations
    async def code_format(self, file_path: str, formatter: str = "auto", check_only: bool = False) -> ToolResult:
        """Format a code file"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/code/format",
            json={"file_path": file_path, "formatter": formatter, "check_only": check_only},
        )
        return ToolResult(**response.json())

    async def code_lint(self, path: str, linter: str = "auto", fix: bool = False) -> ToolResult:
        """Lint code files"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/code/lint", json={"path": path, "linter": linter, "fix": fix}
        )
        return ToolResult(**response.json())

    async def code_analyze(self, path: str, analysis_type: str = "all") -> ToolResult:
        """Analyze code"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/code/analyze", json={"path": path, "analysis_type": analysis_type}
        )
        return ToolResult(**response.json())

    async def code_search(
        self, directory: str, pattern: str, file_glob: str = "*", context_lines: int = 2, max_results: int = 100
    ) -> ToolResult:
        """Search code files"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/code/search",
            json={
                "directory": directory,
                "pattern": pattern,
                "file_glob": file_glob,
                "context_lines": context_lines,
                "max_results": max_results,
            },
        )
        return ToolResult(**response.json())

    # Test execution operations
    async def test_run(
        self,
        path: str,
        framework: str = "auto",
        pattern: str | None = None,
        coverage: bool = False,
        timeout: int = 300,
        verbose: bool = False,
    ) -> ToolResult:
        """Run tests"""
        response = await self.client.post(
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
        return ToolResult(**response.json())

    async def test_list(self, path: str, framework: str = "auto") -> ToolResult:
        """List available tests"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/test/list", json={"path": path, "framework": framework}
        )
        return ToolResult(**response.json())

    async def test_coverage(self, path: str, output_format: str = "html", output_dir: str | None = None) -> ToolResult:
        """Generate coverage report"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/test/coverage",
            json={"path": path, "output_format": output_format, "output_dir": output_dir},
        )
        return ToolResult(**response.json())

    # Export operations
    async def export_organize(self, session_id: str, source_path: str, target_category: str = "other") -> ToolResult:
        """Organize files"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/export/organize",
            json={"session_id": session_id, "source_path": source_path, "target_category": target_category},
        )
        return ToolResult(**response.json())

    async def export_archive(
        self,
        session_id: str,
        name: str,
        include_patterns: list | None = None,
        exclude_patterns: list | None = None,
        base_path: str | None = None,
    ) -> ToolResult:
        """Create archive"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/export/archive",
            json={
                "session_id": session_id,
                "name": name,
                "include_patterns": include_patterns,
                "exclude_patterns": exclude_patterns,
                "base_path": base_path,
            },
        )
        return ToolResult(**response.json())

    async def export_report(
        self,
        session_id: str,
        report_type: str = "summary",
        output_format: str = "markdown",
        title: str = "Workspace Report",
    ) -> ToolResult:
        """Generate report"""
        response = await self.client.post(
            f"{self.base_url}/api/v1/export/report",
            json={"session_id": session_id, "report_type": report_type, "output_format": output_format, "title": title},
        )
        return ToolResult(**response.json())

    async def export_list(self, session_id: str) -> ToolResult:
        """List exports"""
        response = await self.client.post(f"{self.base_url}/api/v1/export/list", json={"session_id": session_id})
        return ToolResult(**response.json())

    @staticmethod
    @alru_cache(maxsize=128, typed=True)
    async def _resolve_hostname_to_ip(hostname: str) -> str:
        """Resolve hostname to IP address

        Args:
            hostname: Hostname to resolve

        Returns:
            Resolved IP address, or None if resolution fails

        Note:
            This method is cached using LRU cache with a maximum size of 128 entries.
            The cache helps reduce repeated DNS lookups for the same hostname.
        """
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
            return None
        except Exception as e:
            # Log error and return None on failure
            logger.error(f"Failed to resolve hostname {hostname}: {e!s}")
            return None

    async def destroy(self) -> bool:
        """Destroy Docker sandbox"""
        try:
            # Invalidate LRU cache so future get() calls create a fresh instance
            if hasattr(DockerSandbox.get, "cache_invalidate"):
                if self._container_name:
                    DockerSandbox.get.cache_invalidate(self._container_name)
                else:
                    DockerSandbox.get.cache_clear()

            if self._client and not self._client.is_closed:
                await self._client.aclose()
            self._client = None
            if self._container_name:
                docker_client = docker.from_env()
                docker_client.containers.get(self._container_name).remove(force=True)
            return True
        except Exception as e:
            logger.error(f"Failed to destroy Docker sandbox: {e!s}")
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
            response = await self.client.get(
                f"{self.base_url}/api/v1/vnc/screenshot",
                params={"quality": quality, "scale": scale, "format": format},
                timeout=10.0,
            )
            response.raise_for_status()
            return response
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            raise

    async def get_browser(
        self,
        block_resources: bool = False,
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
        if verify_connection:
            # Verify CDP is accessible before creating browser instance
            # Uses exponential backoff for faster initial checks
            settings = get_settings()
            if not await self._verify_cdp_with_backoff():
                raise Exception(f"Failed to verify CDP connection after {settings.sandbox_cdp_retries} attempts")

        if use_pool:
            # Use connection pool for efficient browser reuse
            return await self._get_pooled_browser(block_resources, clear_session)

        # Legacy: Create new browser instance without pooling
        browser = PlaywrightBrowser(cdp_url=self.cdp_url, block_resources=block_resources)

        # Protocol: Clear browser state for new sessions
        if clear_session and browser:
            await browser.clear_session()
            logger.info("Browser session cleared for new chat")

        return browser

    async def _get_pooled_browser(
        self,
        block_resources: bool = False,
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

    async def release_pooled_browser(self, browser: Browser, had_error: bool = False) -> None:
        """Release a pooled browser back to the pool.

        Should be called when done with a pooled browser to allow reuse.
        If had_error is True, the connection will be marked as potentially
        unhealthy and may be replaced.

        Args:
            browser: The browser instance to release
            had_error: Whether an error occurred during use of this browser
        """
        pool = BrowserConnectionPool.get_instance()

        # Find and release the connection
        for cdp_url, connections in pool._pools.items():
            for conn in connections:
                if conn.browser is browser:
                    await pool._release_connection(cdp_url, conn, had_error=had_error)
                    logger.debug(f"Released pooled browser for {cdp_url}" + (" (with error)" if had_error else ""))
                    return

        logger.warning("Could not find browser in pool to release")

    @classmethod
    async def create(cls) -> Sandbox:
        """Create a new sandbox instance

        Returns:
            New sandbox instance
        """
        settings = get_settings()

        if settings.sandbox_address:
            # Chrome CDP needs IP address
            ip = await cls._resolve_hostname_to_ip(settings.sandbox_address)
            return DockerSandbox(ip=ip)

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
        if settings.sandbox_address:
            ip = await cls._resolve_hostname_to_ip(settings.sandbox_address)
            return DockerSandbox(ip=ip, container_name=id)

        docker_client = docker.from_env()
        container = docker_client.containers.get(id)
        container.reload()

        ip_address = cls._get_container_ip(container)
        logger.info(f"IP address: {ip_address}")
        return DockerSandbox(ip=ip_address, container_name=id)
