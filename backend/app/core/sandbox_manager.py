"""
Enhanced Sandbox Manager with Robust Error Handling
Provides reliable sandbox lifecycle management with automatic recovery.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import docker
import httpx
from docker.models.containers import Container

from app.core.config import get_settings
from app.core.error_manager import (
    CircuitBreaker, ErrorCategory, ErrorContext, ErrorSeverity, error_context, error_handler, get_error_manager
)

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
    vnc_responsive: bool = False
    last_check: datetime = None
    
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
        self._sandboxes: Dict[str, "ManagedSandbox"] = {}
        self._circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self._health_check_interval = 30  # seconds
        self._max_recovery_attempts = 3
        
    @error_handler(
        severity=ErrorSeverity.CRITICAL,
        category=ErrorCategory.SANDBOX,
        auto_recover=True
    )
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
            severity=ErrorSeverity.CRITICAL
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
                asyncio.create_task(self._monitor_sandbox_health(sandbox))
                
                self._circuit_breaker.record_success()
                logger.info(f"Sandbox created successfully for session {session_id}")
                
                return sandbox
                
            except Exception as e:
                self._circuit_breaker.record_failure()
                logger.error(f"Failed to create sandbox for session {session_id}: {e}")
                raise
                
    async def get_sandbox(self, session_id: str) -> Optional["ManagedSandbox"]:
        """Get existing sandbox or create new one"""
        sandbox = self._sandboxes.get(session_id)
        
        if sandbox and sandbox.state == SandboxState.HEALTHY:
            return sandbox
        elif sandbox and sandbox.state in [SandboxState.UNHEALTHY, SandboxState.FAILED]:
            # Attempt recovery
            if await self._recover_sandbox(sandbox):
                return sandbox
            else:
                # Create new sandbox if recovery fails
                await self.destroy_sandbox(session_id)
                return await self.create_sandbox(session_id)
        else:
            # Create new sandbox
            return await self.create_sandbox(session_id)
            
    @error_handler(
        severity=ErrorSeverity.MEDIUM,
        category=ErrorCategory.SANDBOX,
        auto_recover=False
    )
    async def destroy_sandbox(self, session_id: str) -> bool:
        """Destroy sandbox with error handling"""
        sandbox = self._sandboxes.get(session_id)
        if not sandbox:
            return True
            
        try:
            await sandbox.destroy()
            self._sandboxes.pop(session_id, None)
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
                    sandbox.health.health_check_failures += 1
                    
                    if sandbox.health.health_check_failures >= 3:
                        sandbox.state = SandboxState.UNHEALTHY
                        logger.warning(f"Sandbox {sandbox.session_id} marked as unhealthy")
                        
                        # Attempt recovery
                        await self._recover_sandbox(sandbox)
                else:
                    # Reset failure count on successful health check
                    sandbox.health.health_check_failures = 0
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
            
    def get_sandbox_stats(self) -> Dict[str, Any]:
        """Get sandbox statistics"""
        total_sandboxes = len(self._sandboxes)
        healthy_sandboxes = len([s for s in self._sandboxes.values() if s.state == SandboxState.HEALTHY])
        
        return {
            "total_sandboxes": total_sandboxes,
            "healthy_sandboxes": healthy_sandboxes,
            "unhealthy_sandboxes": total_sandboxes - healthy_sandboxes,
            "circuit_breaker_state": self._circuit_breaker.state,
            "average_creation_time": sum(s.metrics.creation_time for s in self._sandboxes.values()) / max(total_sandboxes, 1)
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
        self.container: Optional[Container] = None
        self.container_name: Optional[str] = None
        self.ip_address: Optional[str] = None
        
        # API clients
        self.api_client: Optional[httpx.AsyncClient] = None
        
    async def create(self):
        """Create and start the sandbox container"""
        try:
            self.state = SandboxState.CREATING
            
            # Generate container name
            import uuid
            self.container_name = f"{self.manager.settings.sandbox_name_prefix}-{str(uuid.uuid4())[:8]}"
            
            # Create Docker client
            docker_client = docker.from_env()
            
            # Container configuration
            container_config = self._get_container_config()
            
            # Create and start container
            self.container = docker_client.containers.run(**container_config)
            
            # Get IP address
            self.container.reload()
            self.ip_address = self._get_container_ip()
            
            # Initialize API client
            self.api_client = httpx.AsyncClient(
                base_url=f"http://{self.ip_address}:8080",
                timeout=30.0
            )
            
            # Wait for services to start
            self.state = SandboxState.STARTING
            await self._wait_for_services()
            
            self.state = SandboxState.HEALTHY
            self.metrics.last_activity = datetime.now()
            
        except Exception as e:
            self.state = SandboxState.FAILED
            logger.error(f"Failed to create sandbox {self.session_id}: {e}")
            raise
            
    def _get_container_config(self) -> Dict[str, Any]:
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
                "/run": "size=100M,nosuid,nodev",
                "/tmp": "size=500M,nosuid,nodev",
                "/home/ubuntu/.cache": "size=200M,nosuid,nodev"
            },
            "shm_size": settings.sandbox_shm_size,
            "mem_limit": settings.sandbox_mem_limit,
            "nano_cpus": int((settings.sandbox_cpu_limit or 2.0) * 1_000_000_000),
            "pids_limit": settings.sandbox_pids_limit,
            "network": settings.sandbox_network,
        }
        
    def _get_container_ip(self) -> str:
        """Get container IP address"""
        network_settings = self.container.attrs.get('NetworkSettings', {})
        ip_address = network_settings.get('IPAddress', '')
        
        if not ip_address and 'Networks' in network_settings:
            networks = network_settings['Networks']
            for network_config in networks.values():
                if network_config.get('IPAddress'):
                    ip_address = network_config['IPAddress']
                    break
                    
        if not ip_address:
            raise Exception("Could not determine container IP address")
            
        return ip_address
        
    async def _wait_for_services(self, timeout: int = 60):
        """Wait for sandbox services to become available"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.health_check():
                self.metrics.startup_time = time.time() - start_time
                return
                
            await asyncio.sleep(2)
            
        raise Exception(f"Sandbox services did not start within {timeout} seconds")
        
    async def health_check(self) -> bool:
        """Perform comprehensive health check"""
        try:
            self.health.last_check = datetime.now()
            
            # Check API responsiveness
            self.health.api_responsive = await self._check_api_health()
            
            # Check browser responsiveness
            self.health.browser_responsive = await self._check_browser_health()
            
            # Check VNC (optional)
            self.health.vnc_responsive = await self._check_vnc_health()

            return self.health.is_healthy
            
        except Exception as e:
            logger.warning(f"Health check failed for sandbox {self.session_id}: {e}")
            return False
            
    async def _check_api_health(self) -> bool:
        """Check if sandbox API is responsive"""
        try:
            response = await self.api_client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
            
    async def _check_browser_health(self) -> bool:
        """Check if browser is responsive"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"http://{self.ip_address}:9222/json/version")
                return response.status_code == 200
        except Exception:
            return False
            
    async def _check_vnc_health(self) -> bool:
        """Check if VNC is responsive"""
        try:
            # Simple TCP connection check
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip_address, 5900),
                timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _restart_services(self) -> bool:
        """Restart sandbox services"""
        try:
            # Restart container
            self.container.restart()
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
            
            if self.api_client:
                await self.api_client.aclose()
                
            if self.container:
                self.container.stop(timeout=10)
                self.container.remove(force=True)
                
        except Exception as e:
            logger.warning(f"Error during sandbox destruction for {self.session_id}: {e}")


# Global sandbox manager instance
_sandbox_manager = EnhancedSandboxManager()


def get_sandbox_manager() -> EnhancedSandboxManager:
    """Get the global sandbox manager instance"""
    return _sandbox_manager
