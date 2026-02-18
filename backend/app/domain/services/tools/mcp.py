import asyncio
import hashlib
import logging
import os
import time
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool as MCPToolType

from app.domain.exceptions.base import ToolConfigurationException, ToolNotFoundException
from app.domain.models.mcp_config import MCPConfig, MCPServerConfig
from app.domain.models.mcp_resource import (
    MCPResource,
    MCPResourceContent,
    ResourceListResult,
    ResourceReadResult,
    ResourceTemplate,
    ResourceType,
)
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.dynamic_toolset import get_warmup_manager

logger = logging.getLogger(__name__)


@dataclass
class ServerHealth:
    """Health status for an MCP server"""

    server_name: str
    healthy: bool = True
    last_check: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None
    consecutive_failures: int = 0
    tools_count: int = 0

    # Enhanced health metrics
    avg_response_time_ms: float = 0.0
    response_time_samples: list[float] = field(default_factory=list)
    max_response_samples: int = 50  # Keep last 50 response times

    # Reliability scoring
    success_count: int = 0
    failure_count: int = 0
    degraded: bool = False  # True if server is working but slow/unreliable
    priority: int = 100  # 0-100, lower = deprioritized

    def record_response_time(self, response_time_ms: float) -> None:
        """Record a response time sample."""
        self.response_time_samples.append(response_time_ms)
        if len(self.response_time_samples) > self.max_response_samples:
            self.response_time_samples.pop(0)
        self.avg_response_time_ms = sum(self.response_time_samples) / len(self.response_time_samples)

    def record_success(self) -> None:
        """Record a successful operation."""
        self.success_count += 1
        self._update_reliability()

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self._update_reliability()

    def _update_reliability(self) -> None:
        """Update reliability metrics and priority."""
        total = self.success_count + self.failure_count
        if total == 0:
            return

        success_rate = self.success_count / total

        # Degraded if success rate < 90%
        self.degraded = success_rate < 0.90

        # Calculate priority based on success rate and response time
        # Base priority from success rate (0-100)
        base_priority = int(success_rate * 100)

        # Penalize slow servers (response time > 2 seconds reduces priority)
        if self.avg_response_time_ms > 2000:
            speed_penalty = min(30, int((self.avg_response_time_ms - 2000) / 100))
            base_priority = max(0, base_priority - speed_penalty)

        self.priority = base_priority

    @property
    def success_rate(self) -> float:
        """Get the success rate as a percentage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "server_name": self.server_name,
            "healthy": self.healthy,
            "degraded": self.degraded,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "tools_count": self.tools_count,
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "success_rate": round(self.success_rate * 100, 1),
            "priority": self.priority,
        }


@dataclass
class CachedToolSchema:
    """Tool schema with TTL-based caching"""

    tools: list[MCPToolType]
    cached_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int = 300  # 5 minutes default

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        elapsed = (datetime.now(UTC) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds


@dataclass
class ToolUsageStats:
    """Usage statistics for a tool"""

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0
    last_used: datetime | None = None

    # Enhanced metrics
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0
    timeout_count: int = 0
    last_error: str | None = None

    @property
    def avg_duration_ms(self) -> float:
        """Average duration per call."""
        if self.call_count == 0:
            return 0
        return self.total_duration_ms / self.call_count

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        if self.call_count == 0:
            return 1.0
        return self.success_count / self.call_count

    @property
    def is_reliable(self) -> bool:
        """Check if tool is considered reliable (>90% success rate)."""
        return self.success_rate >= 0.90

    def record_call(self, success: bool, duration_ms: float, error: str | None = None, timeout: bool = False) -> None:
        """Record a tool call."""
        self.call_count += 1
        self.total_duration_ms += duration_ms
        self.last_used = datetime.now(UTC)

        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)

        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
            self.last_error = error

        if timeout:
            self.timeout_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate * 100, 1),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float("inf") else None,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "timeout_count": self.timeout_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "is_reliable": self.is_reliable,
        }


class MCPClientManager:
    """MCP Client Manager with health checking, dynamic reload, and resource support.

    Features TTL-based tool schema caching for optimal performance:
    - Tool schemas are cached with configurable TTL (default 5 minutes)
    - Expired cache entries are automatically refreshed on next access
    - Reduces overhead when tools don't change frequently
    """

    # Default TTL for tool schema cache (seconds)
    TOOL_SCHEMA_TTL = 300  # 5 minutes

    def __init__(self, config: MCPConfig | None = None):
        self._clients: dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._server_exit_stacks: dict[str, AsyncExitStack] = {}  # Per-server stacks for clean reconnect
        self._tools_cache: dict[str, CachedToolSchema] = {}  # Now uses TTL-based caching
        self._initialized = False
        self._config = config

        # Health tracking
        self._server_health: dict[str, ServerHealth] = {}
        self._tool_usage: dict[str, ToolUsageStats] = {}
        self._config_hash: str | None = None
        self._max_consecutive_failures = 3

        # Resource management
        self._resources_cache: dict[str, list[MCPResource]] = {}
        self._templates_cache: dict[str, list[ResourceTemplate]] = {}
        self._resource_subscriptions: dict[str, set[str]] = {}  # server -> set of URIs

    async def initialize(self):
        """Initialize MCP client manager"""
        if self._initialized:
            return

        try:
            logger.info(f"Loaded {len(self._config.mcp_servers)} MCP server configurations")

            # Store config hash for change detection
            self._config_hash = self._compute_config_hash()

            # Connect to all enabled servers
            await self._connect_servers()

            self._initialized = True
            logger.info("MCP client manager initialized successfully")

        except Exception as e:
            logger.error(f"MCP client manager initialization failed: {e}")
            raise

    def _compute_config_hash(self) -> str:
        """Compute hash of current configuration for change detection"""
        if not self._config:
            return ""
        config_str = str(self._config.model_dump())
        return hashlib.md5(config_str.encode(), usedforsecurity=False).hexdigest()

    async def check_and_reload(self) -> bool:
        """
        Check if configuration has changed and reload if necessary.

        Returns:
            True if configuration was reloaded
        """
        if not self._config:
            return False

        new_hash = self._compute_config_hash()
        if new_hash != self._config_hash:
            logger.info("MCP configuration changed, reloading...")
            await self.cleanup()
            self._initialized = False
            await self.initialize()
            return True

        return False

    async def health_check(self) -> dict[str, ServerHealth]:
        """
        Perform health check on all connected servers.

        Returns:
            Dict of server health statuses
        """
        for server_name, session in self._clients.items():
            health = self._server_health.get(server_name, ServerHealth(server_name=server_name))

            try:
                # Try to list tools as a health check
                tools_response = await session.list_tools()
                health.healthy = True
                health.last_error = None
                health.consecutive_failures = 0
                health.tools_count = len(tools_response.tools) if tools_response else 0
                health.last_check = datetime.now(UTC)
                logger.debug(f"Health check passed for {server_name}")

            except Exception as e:
                health.healthy = False
                health.last_error = str(e)
                health.consecutive_failures += 1
                health.last_check = datetime.now(UTC)
                logger.warning(f"Health check failed for {server_name}: {e}")

            self._server_health[server_name] = health

        return self._server_health

    async def reconnect_unhealthy(self) -> list[str]:
        """
        Attempt to reconnect unhealthy servers.

        Returns:
            List of successfully reconnected server names
        """
        reconnected = []

        for server_name, health in self._server_health.items():
            if not health.healthy and health.consecutive_failures <= self._max_consecutive_failures:
                server_config = self._config.mcp_servers.get(server_name)
                if server_config:
                    try:
                        logger.info(f"Attempting to reconnect to {server_name}")
                        await self._connect_server(server_name, server_config)
                        health.healthy = True
                        health.consecutive_failures = 0
                        health.last_error = None
                        reconnected.append(server_name)
                        logger.info(f"Successfully reconnected to {server_name}")
                    except Exception as e:
                        health.consecutive_failures += 1
                        health.last_error = str(e)
                        logger.error(f"Failed to reconnect to {server_name}: {e}")

        return reconnected

    def record_tool_usage(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        timeout: bool = False,
        server_name: str | None = None,
    ) -> None:
        """Record tool usage statistics.

        Args:
            tool_name: Name of the tool
            success: Whether the call succeeded
            duration_ms: Duration in milliseconds
            error: Error message if failed
            timeout: Whether failure was due to timeout
            server_name: Name of the server (for server-level metrics)
        """
        if tool_name not in self._tool_usage:
            self._tool_usage[tool_name] = ToolUsageStats(tool_name=tool_name)

        stats = self._tool_usage[tool_name]
        stats.record_call(success, duration_ms, error, timeout)

        # Also update server health if server_name provided
        if server_name and server_name in self._server_health:
            health = self._server_health[server_name]
            health.record_response_time(duration_ms)
            if success:
                health.record_success()
            else:
                health.record_failure()

    def get_tool_stats(self) -> dict[str, ToolUsageStats]:
        """Get tool usage statistics"""
        return self._tool_usage

    def get_reliable_tools(self, min_success_rate: float = 0.90) -> list[str]:
        """Get list of reliable tools based on success rate.

        Args:
            min_success_rate: Minimum success rate threshold (0.0-1.0)

        Returns:
            List of tool names that meet the reliability threshold
        """
        reliable = []
        for name, stats in self._tool_usage.items():
            if stats.call_count >= 3 and stats.success_rate >= min_success_rate:
                reliable.append(name)
        return reliable

    def get_unreliable_tools(self, max_success_rate: float = 0.80) -> list[str]:
        """Get list of unreliable tools that should be deprioritized.

        Args:
            max_success_rate: Maximum success rate to be considered unreliable

        Returns:
            List of tool names that are unreliable
        """
        unreliable = []
        for name, stats in self._tool_usage.items():
            if stats.call_count >= 3 and stats.success_rate < max_success_rate:
                unreliable.append(name)
        return unreliable

    def get_tools_by_priority(self) -> list[tuple[str, int]]:
        """Get all tools sorted by priority (server health-based).

        Returns:
            List of (tool_name, priority) tuples sorted by priority descending
        """
        tool_priorities = []
        for server_name, health in self._server_health.items():
            if server_name in self._tools_cache:
                tool_priorities.extend(
                    (cached_tool.name, health.priority) for cached_tool in self._tools_cache[server_name].tools
                )

        # Sort by priority descending
        tool_priorities.sort(key=lambda x: x[1], reverse=True)
        return tool_priorities

    def get_health_status(self) -> dict[str, ServerHealth]:
        """Get current health status of all servers"""
        return self._server_health

    async def _connect_servers(self):
        """Connect to all enabled MCP servers"""
        for server_name, server_config in self._config.mcp_servers.items():
            if not server_config.enabled:
                continue

            try:
                await self._connect_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")
                # Continue connecting to other servers
                continue

    async def _connect_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to a single MCP server.

        On reconnect, closes the old per-server exit stack to avoid
        accumulating stale connection contexts.
        """
        try:
            # Close old per-server exit stack if reconnecting
            old_stack = self._server_exit_stacks.pop(server_name, None)
            if old_stack:
                try:
                    await old_stack.aclose()
                except Exception as e:
                    logger.warning(f"Failed to close old exit stack for {server_name}: {e}")
            self._clients.pop(server_name, None)

            # Create a fresh exit stack for this server
            self._server_exit_stacks[server_name] = AsyncExitStack()

            transport_type = server_config.transport

            if transport_type == "stdio":
                await self._connect_stdio_server(server_name, server_config)
            elif transport_type == "http" or transport_type == "sse":
                await self._connect_http_server(server_name, server_config)
            elif transport_type == "streamable-http":
                await self._connect_streamable_http_server(server_name, server_config)
            else:
                logger.error(f"Unsupported transport type: {transport_type}")

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}")
            raise

    async def _connect_stdio_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to stdio MCP server"""
        command = server_config.command
        args = server_config.args or []
        env = server_config.env or {}

        if not command:
            raise ToolConfigurationException(f"Server {server_name} missing command configuration")

        # Create server parameters (path handling done in config provider)
        server_params = StdioServerParameters(command=command, args=args, env={**os.environ, **env})
        stack = self._server_exit_stacks[server_name]

        try:
            async with asyncio.timeout(30):  # 30s connection timeout
                # Establish connection
                stdio_transport = await stack.enter_async_context(stdio_client(server_params))
                read_stream, write_stream = stdio_transport

                # Create session
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))

                # Initialize session
                await session.initialize()

            # Cache client
            self._clients[server_name] = session

            # Get and cache tool list
            await self._cache_server_tools(server_name, session)

            logger.info(f"Successfully connected to stdio MCP server: {server_name}")

        except TimeoutError:
            logger.error(f"Timeout connecting to stdio MCP server {server_name} (30s)")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to stdio MCP server {server_name}: {e}")
            raise

    async def _connect_http_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to HTTP MCP server"""
        url = server_config.url
        if not url:
            raise ToolConfigurationException(f"Server {server_name} missing url configuration")

        stack = self._server_exit_stacks[server_name]

        try:
            async with asyncio.timeout(30):  # 30s connection timeout
                # Establish SSE connection
                sse_transport = await stack.enter_async_context(sse_client(url))
                read_stream, write_stream = sse_transport

                # Create session
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))

                # Initialize session
                await session.initialize()

            # Cache client
            self._clients[server_name] = session

            # Get and cache tool list
            await self._cache_server_tools(server_name, session)

            logger.info(f"Successfully connected to HTTP MCP server: {server_name}")

        except Exception as e:
            logger.error(f"Failed to connect to HTTP MCP server {server_name}: {e}")
            raise

    async def _connect_streamable_http_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to streamable-http MCP server

        Configuration options:
        - url: Server URL (required)
        - headers: Custom HTTP headers (optional)
        """
        url = server_config.url
        if not url:
            raise ToolConfigurationException(f"Server {server_name} missing url configuration")

        # Get optional configuration
        headers = server_config.headers or {}

        stack = self._server_exit_stacks[server_name]

        try:
            # Prepare connection parameters
            client_params = {"url": url}

            # Add custom headers
            if headers:
                client_params["headers"] = headers

            # Establish streamable-http connection
            streamable_transport = await stack.enter_async_context(streamablehttp_client(**client_params))

            # Unpack returned streams and optional third parameter
            if len(streamable_transport) == 3:
                read_stream, write_stream, _ = streamable_transport
            else:
                read_stream, write_stream = streamable_transport

            # Create MCP session
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))

            # Initialize session
            await session.initialize()

            # Cache client
            self._clients[server_name] = session

            # Get and cache tool list
            await self._cache_server_tools(server_name, session)

            logger.info(f"Successfully connected to streamable-http MCP server: {server_name} ({url})")

        except Exception as e:
            logger.error(f"Failed to connect to streamable-http MCP server {server_name}: {e}")
            raise

    async def _cache_server_tools(self, server_name: str, session: ClientSession):
        """Cache server tool list with TTL and initialize health tracking"""
        try:
            tools_response = await session.list_tools()
            tools = tools_response.tools if tools_response else []

            # Use TTL-based caching for tool schemas
            self._tools_cache[server_name] = CachedToolSchema(
                tools=tools, cached_at=datetime.now(UTC), ttl_seconds=self.TOOL_SCHEMA_TTL
            )

            # Initialize health tracking
            self._server_health[server_name] = ServerHealth(
                server_name=server_name, healthy=True, tools_count=len(tools), last_check=datetime.now(UTC)
            )

            logger.info(f"Server {server_name} provides {len(tools)} tools (cached for {self.TOOL_SCHEMA_TTL}s)")

            # Also cache resources if available
            await self._cache_server_resources(server_name, session)

        except Exception as e:
            logger.error(f"Failed to get tool list from server {server_name}: {e}")
            self._tools_cache[server_name] = CachedToolSchema(tools=[], ttl_seconds=60)  # Short TTL for failed cache
            self._server_health[server_name] = ServerHealth(
                server_name=server_name, healthy=False, last_error=str(e), consecutive_failures=1
            )

    async def _refresh_tools_if_expired(self, server_name: str) -> list[MCPToolType]:
        """Refresh tool cache if TTL expired, otherwise return cached tools"""
        cached = self._tools_cache.get(server_name)

        if cached and not cached.is_expired():
            return cached.tools

        # Cache expired or doesn't exist - refresh
        session = self._clients.get(server_name)
        if session:
            logger.debug(f"Refreshing tool cache for {server_name} (TTL expired)")
            await self._cache_server_tools(server_name, session)
            cached = self._tools_cache.get(server_name)
            return cached.tools if cached else []

        return []

    def invalidate_tool_cache(self, server_name: str | None = None):
        """Invalidate tool cache for a specific server or all servers.

        Args:
            server_name: Optional server name. If None, invalidates all caches.
        """
        if server_name:
            if server_name in self._tools_cache:
                del self._tools_cache[server_name]
                logger.debug(f"Invalidated tool cache for {server_name}")
        else:
            self._tools_cache.clear()
            logger.debug("Invalidated all tool caches")

    async def _cache_server_resources(self, server_name: str, session: ClientSession):
        """Cache server resources and templates."""
        try:
            # List resources from server
            resources_response = await session.list_resources()

            resources = []
            templates = []

            if resources_response and hasattr(resources_response, "resources"):
                resources.extend(
                    MCPResource(
                        uri=res.uri,
                        name=res.name,
                        description=getattr(res, "description", None),
                        mime_type=getattr(res, "mimeType", None),
                        server_name=server_name,
                        annotations=getattr(res, "annotations", {}) or {},
                    )
                    for res in resources_response.resources
                )

            # Check for resource templates
            if hasattr(resources_response, "resourceTemplates") and resources_response.resourceTemplates:
                templates.extend(
                    ResourceTemplate(
                        uri_template=tmpl.uriTemplate,
                        name=tmpl.name,
                        description=getattr(tmpl, "description", None),
                        mime_type=getattr(tmpl, "mimeType", None),
                        server_name=server_name,
                    )
                    for tmpl in resources_response.resourceTemplates
                )

            self._resources_cache[server_name] = resources
            self._templates_cache[server_name] = templates

            logger.info(f"Server {server_name} provides {len(resources)} resources and {len(templates)} templates")

        except Exception as e:
            # Resources are optional - servers may not support them
            logger.debug(f"Server {server_name} does not support resources or error: {e}")
            self._resources_cache[server_name] = []
            self._templates_cache[server_name] = []

    async def list_all_resources(self) -> ResourceListResult:
        """List all resources from all connected MCP servers.

        Returns:
            ResourceListResult with all available resources and templates
        """
        all_resources = []
        all_templates = []
        errors = {}

        for server_name, session in self._clients.items():
            # Check health before querying
            health = self._server_health.get(server_name)
            if health and not health.healthy:
                errors[server_name] = f"Server unhealthy: {health.last_error}"
                continue

            try:
                # Refresh resource cache
                await self._cache_server_resources(server_name, session)

                all_resources.extend(self._resources_cache.get(server_name, []))
                all_templates.extend(self._templates_cache.get(server_name, []))

            except Exception as e:
                errors[server_name] = str(e)
                logger.warning(f"Failed to list resources from {server_name}: {e}")

        return ResourceListResult(
            resources=all_resources,
            templates=all_templates,
            total_count=len(all_resources),
            servers_queried=list(self._clients.keys()),
            errors=errors,
        )

    async def read_resource(self, uri: str, server_name: str | None = None) -> ResourceReadResult:
        """Read content from an MCP resource.

        Args:
            uri: The URI of the resource to read
            server_name: Optional server name (auto-detected if not provided)

        Returns:
            ResourceReadResult with content or error
        """
        start_time = time.time()

        # Find the server that provides this resource
        target_server = server_name
        if not target_server:
            target_server = self._find_resource_server(uri)

        if not target_server:
            return ResourceReadResult(success=False, error=f"No server found providing resource: {uri}")

        session = self._clients.get(target_server)
        if not session:
            return ResourceReadResult(success=False, error=f"Server {target_server} not connected")

        try:
            # Call MCP read_resource
            result = await session.read_resource(uri)

            if not result or not hasattr(result, "contents") or not result.contents:
                return ResourceReadResult(success=False, error="Resource returned no content")

            # Process the first content item (MCP can return multiple)
            content_item = result.contents[0]

            # Determine content type
            if hasattr(content_item, "text") and content_item.text is not None:
                resource_content = MCPResourceContent(
                    uri=uri,
                    resource_type=ResourceType.TEXT,
                    text=content_item.text,
                    mime_type=getattr(content_item, "mimeType", None),
                )
            elif hasattr(content_item, "blob") and content_item.blob is not None:
                resource_content = MCPResourceContent(
                    uri=uri,
                    resource_type=ResourceType.BLOB,
                    blob=content_item.blob,
                    mime_type=getattr(content_item, "mimeType", None),
                )
            else:
                return ResourceReadResult(success=False, error="Resource content format not recognized")

            return ResourceReadResult(
                success=True, content=resource_content, read_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}")
            return ResourceReadResult(success=False, error=str(e), read_time_ms=(time.time() - start_time) * 1000)

    def _find_resource_server(self, uri: str) -> str | None:
        """Find which server provides a given resource URI."""
        for server_name, resources in self._resources_cache.items():
            for resource in resources:
                if resource.uri == uri:
                    return server_name

        # Try matching against templates
        for server_name, templates in self._templates_cache.items():
            for template in templates:
                # Simple template matching (could be enhanced)
                if self._matches_template(uri, template.uri_template):
                    return server_name

        return None

    def _matches_template(self, uri: str, template: str) -> bool:
        """Check if a URI matches a template pattern."""
        # Simple matching: template uses {placeholder} syntax
        import re

        # Convert template to regex
        pattern = template.replace("{", "(?P<").replace("}", ">[^/]+)")
        pattern = f"^{pattern}$"

        try:
            return bool(re.match(pattern, uri))
        except re.error:
            return False

    async def subscribe_resource(self, uri: str, server_name: str | None = None) -> bool:
        """Subscribe to updates for a resource.

        Args:
            uri: Resource URI to subscribe to
            server_name: Optional server name

        Returns:
            True if subscription successful
        """
        target_server = server_name or self._find_resource_server(uri)
        if not target_server:
            logger.warning(f"Cannot subscribe - no server found for {uri}")
            return False

        session = self._clients.get(target_server)
        if not session:
            return False

        try:
            await session.subscribe_resource(uri)

            if target_server not in self._resource_subscriptions:
                self._resource_subscriptions[target_server] = set()
            self._resource_subscriptions[target_server].add(uri)

            logger.info(f"Subscribed to resource {uri} on {target_server}")
            return True

        except Exception as e:
            logger.warning(f"Failed to subscribe to {uri}: {e}")
            return False

    async def unsubscribe_resource(self, uri: str, server_name: str | None = None) -> bool:
        """Unsubscribe from resource updates.

        Args:
            uri: Resource URI to unsubscribe from
            server_name: Optional server name

        Returns:
            True if unsubscription successful
        """
        target_server = server_name or self._find_resource_server(uri)
        if not target_server:
            return False

        session = self._clients.get(target_server)
        if not session:
            return False

        try:
            await session.unsubscribe_resource(uri)

            if target_server in self._resource_subscriptions:
                self._resource_subscriptions[target_server].discard(uri)

            logger.info(f"Unsubscribed from resource {uri}")
            return True

        except Exception as e:
            logger.warning(f"Failed to unsubscribe from {uri}: {e}")
            return False

    def get_cached_resources(self, server_name: str | None = None) -> list[MCPResource]:
        """Get cached resources without refreshing.

        Args:
            server_name: Optional filter by server

        Returns:
            List of cached MCPResource objects
        """
        if server_name:
            return self._resources_cache.get(server_name, [])

        all_resources = []
        for resources in self._resources_cache.values():
            all_resources.extend(resources)
        return all_resources

    def get_cached_templates(self, server_name: str | None = None) -> list[ResourceTemplate]:
        """Get cached resource templates without refreshing.

        Args:
            server_name: Optional filter by server

        Returns:
            List of cached ResourceTemplate objects
        """
        if server_name:
            return self._templates_cache.get(server_name, [])

        all_templates = []
        for templates in self._templates_cache.values():
            all_templates.extend(templates)
        return all_templates

    async def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all MCP tools, refreshing expired caches as needed"""
        all_tools = []

        for server_name in list(self._tools_cache.keys()):
            # Get tools with TTL check
            tools = await self._refresh_tools_if_expired(server_name)
            for tool in tools:
                # Generate tool name, avoid duplicate mcp_ prefix
                if server_name.startswith("mcp_"):
                    tool_name = f"{server_name}_{tool.name}"
                else:
                    tool_name = f"mcp_{server_name}_{tool.name}"

                # Convert to standard tool format
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"[{server_name}] {tool.description or tool.name}",
                        "parameters": tool.inputSchema,
                    },
                }
                all_tools.append(tool_schema)

        return all_tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call MCP tool with health tracking and usage statistics"""
        import time

        start_time = time.time()
        server_name = None

        try:
            # Parse tool name
            original_tool_name = None

            # Find matching server name
            for srv_name in self._config.mcp_servers:
                expected_prefix = srv_name if srv_name.startswith("mcp_") else f"mcp_{srv_name}"
                if tool_name.startswith(f"{expected_prefix}_"):
                    server_name = srv_name
                    original_tool_name = tool_name[len(expected_prefix) + 1 :]
                    break

            if not server_name or not original_tool_name:
                raise ToolNotFoundException(tool_name)

            # Check server health before calling
            health = self._server_health.get(server_name)
            if health and not health.healthy and health.consecutive_failures >= self._max_consecutive_failures:
                return ToolResult(
                    success=False,
                    message=f"MCP server {server_name} is unhealthy (failures: {health.consecutive_failures})",
                )

            # Get client session
            session = self._clients.get(server_name)
            if not session:
                return ToolResult(success=False, message=f"MCP server {server_name} not connected")

            # Call tool with timeout to prevent hung servers from blocking forever
            result = await asyncio.wait_for(
                session.call_tool(original_tool_name, arguments),
                timeout=120.0,  # 2 minute timeout per tool call
            )

            # Record successful call
            duration_ms = (time.time() - start_time) * 1000
            self.record_tool_usage(tool_name, success=True, duration_ms=duration_ms, server_name=server_name)

            # Mark server as healthy on success
            if server_name in self._server_health:
                self._server_health[server_name].healthy = True
                self._server_health[server_name].consecutive_failures = 0
                self._server_health[server_name].last_check = datetime.now(UTC)

            # Process result
            if result:
                content = []
                if hasattr(result, "content") and result.content:
                    for item in result.content:
                        if hasattr(item, "text"):
                            content.append(item.text)
                        else:
                            content.append(str(item))

                return ToolResult(success=True, data="\n".join(content) if content else "Tool executed successfully")
            return ToolResult(success=True, data="Tool executed successfully")

        except Exception as e:
            # Record failed call
            duration_ms = (time.time() - start_time) * 1000
            is_timeout = isinstance(e, TimeoutError)
            self.record_tool_usage(
                tool_name,
                success=False,
                duration_ms=duration_ms,
                error=str(e),
                timeout=is_timeout,
                server_name=server_name,
            )

            # Mark server as unhealthy on failure
            if server_name and server_name in self._server_health:
                health = self._server_health[server_name]
                health.healthy = False
                health.consecutive_failures += 1
                health.last_error = str(e)
                health.last_check = datetime.now(UTC)

            logger.error(f"Failed to call MCP tool {tool_name}: {e}")
            return ToolResult(success=False, message=f"Failed to call MCP tool: {e!s}")

    async def cleanup(self):
        """Cleanup resources, killing subprocess transports on failure."""
        # Close per-server exit stacks first
        for server_name, stack in list(self._server_exit_stacks.items()):
            try:
                await stack.aclose()
            except Exception as e:
                logger.warning(f"Failed to close exit stack for {server_name}: {e}")
        self._server_exit_stacks.clear()

        try:
            await self._exit_stack.aclose()
        except Exception as e:
            logger.error(f"Failed to cleanup MCP exit stack: {e}")
            # Attempt individual client session cleanup to avoid zombie processes
            for server_name, session in list(self._clients.items()):
                try:
                    transport = getattr(session, "_transport", None)
                    if transport and hasattr(transport, "close"):
                        transport.close()
                    # Kill subprocess if it exists
                    proc = getattr(transport, "_process", None) or getattr(transport, "process", None)
                    if proc and hasattr(proc, "kill"):
                        with suppress(ProcessLookupError):
                            proc.kill()
                except Exception as inner_e:
                    logger.warning(f"Failed to cleanup MCP client {server_name}: {inner_e}")
        finally:
            self._clients.clear()
            self._tools_cache.clear()
            self._initialized = False
            logger.info("MCP client manager cleaned up")


class MCPHealthMonitor:
    """Proactive health monitor for MCP servers.

    Runs periodic health checks and automatically:
    - Detects degraded servers
    - Deprioritizes unreliable tools
    - Attempts recovery of failed servers
    - Emits health events for monitoring

    Usage:
        monitor = MCPHealthMonitor(client_manager)
        await monitor.start()
        # ... later
        await monitor.stop()
    """

    def __init__(
        self,
        client_manager: MCPClientManager,
        check_interval_seconds: float = 300.0,  # 5 minutes
        recovery_interval_seconds: float = 60.0,  # 1 minute
    ):
        """Initialize health monitor.

        Args:
            client_manager: MCP client manager to monitor
            check_interval_seconds: Interval between health checks
            recovery_interval_seconds: Interval between recovery attempts
        """
        self._client_manager = client_manager
        self._check_interval = check_interval_seconds
        self._recovery_interval = recovery_interval_seconds
        self._running = False
        self._check_task: Any = None
        self._recovery_task: Any = None
        self._health_callbacks: list[Any] = []

    def add_health_callback(self, callback: Any) -> None:
        """Add callback for health events.

        Args:
            callback: Async function(health_status: dict) to call on health changes
        """
        self._health_callbacks.append(callback)

    async def start(self) -> None:
        """Start the health monitor."""
        if self._running:
            return

        self._running = True
        import asyncio

        self._check_task = asyncio.create_task(self._health_check_loop())
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        logger.info(f"MCP health monitor started (check every {self._check_interval}s)")

    async def stop(self) -> None:
        """Stop the health monitor."""
        import asyncio

        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"MCP health check task cleanup error: {e}")

        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"MCP recovery task cleanup error: {e}")

        logger.info("MCP health monitor stopped")

    async def _health_check_loop(self) -> None:
        """Run periodic health checks."""
        import asyncio

        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                if not self._running:
                    break

                start_time = time.time()
                health_status = await self._client_manager.health_check()
                duration_ms = (time.time() - start_time) * 1000

                # Emit health event
                await self._emit_health_event(health_status, duration_ms)

                # Log summary
                healthy_count = sum(1 for h in health_status.values() if h.healthy)
                degraded_count = sum(1 for h in health_status.values() if h.degraded)
                total_count = len(health_status)

                if degraded_count > 0:
                    logger.warning(
                        f"MCP health check: {healthy_count}/{total_count} healthy, "
                        f"{degraded_count} degraded (took {duration_ms:.0f}ms)"
                    )
                else:
                    logger.debug(f"MCP health check: {healthy_count}/{total_count} healthy (took {duration_ms:.0f}ms)")

            except Exception as e:
                logger.error(f"Health check failed: {e}")

    async def _recovery_loop(self) -> None:
        """Run periodic recovery attempts for unhealthy servers."""
        import asyncio

        while self._running:
            try:
                await asyncio.sleep(self._recovery_interval)
                if not self._running:
                    break

                # Check if any servers need recovery
                health_status = self._client_manager.get_health_status()
                unhealthy = [name for name, h in health_status.items() if not h.healthy]

                if unhealthy:
                    logger.info(f"Attempting recovery for {len(unhealthy)} unhealthy servers")
                    reconnected = await self._client_manager.reconnect_unhealthy()
                    if reconnected:
                        logger.info(f"Successfully recovered servers: {reconnected}")

            except Exception as e:
                logger.error(f"Recovery loop failed: {e}")

    async def _emit_health_event(self, health_status: dict[str, ServerHealth], duration_ms: float) -> None:
        """Emit health status to callbacks."""
        summary = self.get_health_summary()
        summary["check_duration_ms"] = duration_ms

        for callback in self._health_callbacks:
            try:
                await callback(summary)
            except Exception as e:
                logger.warning(f"Health callback failed: {e}")

    def get_health_summary(self) -> dict[str, Any]:
        """Get a summary of all MCP health metrics.

        Returns:
            Dict with aggregated health information
        """
        health_status = self._client_manager.get_health_status()
        tool_stats = self._client_manager.get_tool_stats()

        healthy_servers = [name for name, h in health_status.items() if h.healthy]
        unhealthy_servers = [name for name, h in health_status.items() if not h.healthy]
        degraded_servers = [name for name, h in health_status.items() if h.degraded]

        reliable_tools = self._client_manager.get_reliable_tools()
        unreliable_tools = self._client_manager.get_unreliable_tools()

        # Calculate aggregate metrics
        total_calls = sum(s.call_count for s in tool_stats.values())
        total_success = sum(s.success_count for s in tool_stats.values())
        overall_success_rate = total_success / total_calls if total_calls > 0 else 1.0

        avg_response_times = [h.avg_response_time_ms for h in health_status.values() if h.avg_response_time_ms > 0]
        overall_avg_response = sum(avg_response_times) / len(avg_response_times) if avg_response_times else 0

        return {
            "servers": {
                "total": len(health_status),
                "healthy": len(healthy_servers),
                "unhealthy": len(unhealthy_servers),
                "degraded": len(degraded_servers),
                "healthy_names": healthy_servers,
                "unhealthy_names": unhealthy_servers,
                "degraded_names": degraded_servers,
            },
            "tools": {
                "total": len(tool_stats),
                "reliable": len(reliable_tools),
                "unreliable": len(unreliable_tools),
                "unreliable_names": unreliable_tools,
            },
            "metrics": {
                "total_calls": total_calls,
                "overall_success_rate": round(overall_success_rate * 100, 1),
                "avg_response_time_ms": round(overall_avg_response, 2),
            },
            "status": "healthy" if not unhealthy_servers else "degraded" if not degraded_servers else "unhealthy",
        }


class MCPTool(BaseTool):
    """MCP Tool class with tool invocation and resource management.

    Provides access to:
    - MCP server tools (dynamically discovered)
    - MCP resources (listing, reading, subscribing)
    - Server health monitoring

    Phase 5 Enhancement: Supports lazy initialization via mcp_lazy_init config.
    When enabled, MCP connections are deferred until first tool call.
    """

    name = "mcp"

    # Built-in resource management tools
    RESOURCE_TOOLS: ClassVar[list[dict[str, Any]]] = [
        {
            "type": "function",
            "function": {
                "name": "mcp_list_resources",
                "description": "List all available MCP resources across connected servers. Returns URIs, names, and descriptions of resources that can be read.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_name": {"type": "string", "description": "Optional: Filter by specific MCP server name"}
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_read_resource",
                "description": "Read content from an MCP resource by its URI. Returns the text or binary content of the resource.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uri": {
                            "type": "string",
                            "description": "The URI of the resource to read (e.g., 'file:///path/to/file', 'db://table/record')",
                        },
                        "server_name": {
                            "type": "string",
                            "description": "Optional: Specific server to read from (auto-detected if not provided)",
                        },
                    },
                    "required": ["uri"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_server_status",
                "description": "Get health status and statistics for connected MCP servers.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]

    def __init__(self):
        super().__init__()
        self._initialized = False
        self._tools = []
        self.manager: MCPClientManager | None = None
        self._config: MCPConfig | None = None
        self._lazy_init_pending = False  # Phase 5: Track if lazy init is pending
        self._init_lock = asyncio.Lock()  # Prevent concurrent initialization races

    async def initialized(self, config: MCPConfig | None = None):
        """Ensure manager is initialized.

        Phase 5: When mcp_lazy_init is enabled, this method stores the config
        but defers actual initialization until first MCP tool call.
        """
        from app.core.config import get_settings

        settings = get_settings()

        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            self._config = config

            if settings.mcp_lazy_init:
                # Phase 5: Defer initialization until first tool call
                self._lazy_init_pending = True
                logger.info("MCP lazy initialization enabled - deferring until first use")
            else:
                # Immediate initialization (original behavior)
                await self._do_initialize()

    async def _do_initialize(self):
        """Perform actual MCP initialization."""
        if self._initialized:
            return

        if not self._config:
            logger.warning("MCP initialization skipped - no config provided")
            self._initialized = True
            return

        self.manager = MCPClientManager(self._config)
        await self.manager.initialize()
        self._tools = await self.manager.get_all_tools()
        self._initialized = True
        self._lazy_init_pending = False
        logger.info(f"MCP initialized with {len(self._tools)} tools")

    async def _ensure_initialized(self):
        """Ensure MCP is initialized before use (for lazy init).

        Uses a lock to prevent concurrent initialization races where
        multiple callers see _initialized=False simultaneously.
        """
        if self._initialized:
            return
        async with self._init_lock:
            # Double-check after acquiring lock
            if self._lazy_init_pending and not self._initialized:
                logger.info("MCP lazy initialization triggered by first use")
                await self._do_initialize()

    def get_tools(self) -> list[dict[str, Any]]:
        """Get all tool definitions including resource management tools.

        Phase 5: When lazy init is pending, returns resource tools only.
        Full tool list is available after first MCP call triggers initialization.
        """
        # Combine MCP server tools with built-in resource tools
        all_tools = list(self._tools)  # Copy server tools

        # Add resource management tools if initialized or lazy init pending
        # This allows resource tools to be available even before full init
        if self._initialized or self._lazy_init_pending:
            all_tools.extend(self.RESOURCE_TOOLS)

        return all_tools

    def has_function(self, function_name: str) -> bool:
        """Check if specified function exists (including dynamic MCP tools)"""
        # Check built-in resource tools
        resource_tool_names = {t["function"]["name"] for t in self.RESOURCE_TOOLS}
        if function_name in resource_tool_names:
            return True

        # Check MCP server tools
        return any(tool["function"]["name"] == function_name for tool in self._tools)

    async def invoke_function(self, function_name: str, **kwargs) -> ToolResult:
        """Call tool function (MCP server tool or built-in resource tool).

        Phase 5: Triggers lazy initialization on first call if enabled.
        """
        # Ensure MCP is initialized (lazy init support)
        await self._ensure_initialized()

        # Handle built-in resource tools
        if function_name == "mcp_list_resources":
            return await self._list_resources(kwargs.get("server_name"))

        if function_name == "mcp_read_resource":
            uri = kwargs.get("uri")
            if not uri:
                return ToolResult(success=False, message="URI is required")
            return await self._read_resource(uri, kwargs.get("server_name"))

        if function_name == "mcp_server_status":
            return await self._get_server_status()

        # Handle MCP server tools
        if not self.manager:
            return ToolResult(success=False, message="MCP manager not initialized")
        return await self.manager.call_tool(function_name, kwargs)

    async def _list_resources(self, server_name: str | None = None) -> ToolResult:
        """List available MCP resources."""
        if not self.manager:
            return ToolResult(success=False, message="MCP manager not initialized")

        try:
            result = await self.manager.list_all_resources()

            # Filter by server if specified
            resources = result.resources
            templates = result.templates

            if server_name:
                resources = [r for r in resources if r.server_name == server_name]
                templates = [t for t in templates if t.server_name == server_name]

            # Format for output
            output_parts = []

            if resources:
                output_parts.append(f"**Resources ({len(resources)}):**")
                for res in resources:
                    desc = f" - {res.description}" if res.description else ""
                    mime = f" [{res.mime_type}]" if res.mime_type else ""
                    output_parts.append(f"- `{res.uri}`{mime}: {res.name}{desc}")

            if templates:
                output_parts.append(f"\n**Resource Templates ({len(templates)}):**")
                for tmpl in templates:
                    desc = f" - {tmpl.description}" if tmpl.description else ""
                    output_parts.append(f"- `{tmpl.uri_template}`: {tmpl.name}{desc}")

            if result.errors:
                output_parts.append("\n**Errors:**")
                for srv, err in result.errors.items():
                    output_parts.append(f"- {srv}: {err}")

            if not resources and not templates:
                output_parts.append("No resources available from connected MCP servers.")

            return ToolResult(success=True, data="\n".join(output_parts))

        except Exception as e:
            logger.error(f"Failed to list resources: {e}")
            return ToolResult(success=False, message=f"Failed to list resources: {e!s}")

    async def _read_resource(self, uri: str, server_name: str | None = None) -> ToolResult:
        """Read content from an MCP resource."""
        if not self.manager:
            return ToolResult(success=False, message="MCP manager not initialized")

        try:
            result = await self.manager.read_resource(uri, server_name)

            if not result.success:
                return ToolResult(success=False, message=result.error or "Failed to read resource")

            if not result.content:
                return ToolResult(success=False, message="Resource returned no content")

            # Format content based on type
            if result.content.is_text:
                data = result.content.text
                # Add metadata
                metadata = f"URI: {uri}"
                if result.content.mime_type:
                    metadata += f"\nMIME Type: {result.content.mime_type}"
                metadata += f"\nRead Time: {result.read_time_ms:.1f}ms"

                return ToolResult(success=True, data=f"{metadata}\n\n---\n\n{data}")
            # Binary content - provide info only
            return ToolResult(
                success=True,
                data=f"Binary resource read successfully.\nURI: {uri}\nMIME Type: {result.content.mime_type or 'unknown'}\nSize: {len(result.content.blob or b'')} bytes",
            )

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}")
            return ToolResult(success=False, message=f"Failed to read resource: {e!s}")

    async def _get_server_status(self) -> ToolResult:
        """Get status of all MCP servers."""
        if not self.manager:
            return ToolResult(success=False, message="MCP manager not initialized")

        try:
            health = await self.manager.health_check()
            tool_stats = self.manager.get_tool_stats()

            output_parts = ["**MCP Server Status:**\n"]

            for server_name, status in health.items():
                status_emoji = "✅" if status.healthy else "❌"
                output_parts.append(f"**{status_emoji} {server_name}**")
                output_parts.append(f"  - Healthy: {status.healthy}")
                output_parts.append(f"  - Tools: {status.tools_count}")
                output_parts.append(f"  - Last Check: {status.last_check.strftime('%H:%M:%S')}")
                if status.last_error:
                    output_parts.append(f"  - Last Error: {status.last_error}")
                output_parts.append("")

            # Resource counts
            resources = self.manager.get_cached_resources()
            templates = self.manager.get_cached_templates()
            output_parts.append(f"**Resources:** {len(resources)} available")
            output_parts.append(f"**Templates:** {len(templates)} available")

            # Tool usage stats
            if tool_stats:
                output_parts.append("\n**Tool Usage Statistics:**")
                for name, stats in list(tool_stats.items())[:5]:  # Top 5
                    success_rate = (stats.success_count / stats.call_count * 100) if stats.call_count > 0 else 0
                    avg_duration = stats.total_duration_ms / stats.call_count if stats.call_count > 0 else 0
                    output_parts.append(
                        f"  - {name}: {stats.call_count} calls, {success_rate:.0f}% success, {avg_duration:.0f}ms avg"
                    )

            return ToolResult(success=True, data="\n".join(output_parts))

        except Exception as e:
            logger.error(f"Failed to get server status: {e}")
            return ToolResult(success=False, message=f"Failed to get status: {e!s}")

    async def refresh_resources(self) -> None:
        """Refresh the resource cache from all servers."""
        if self.manager:
            await self.manager.list_all_resources()

    async def warmup_caches(self) -> dict[str, bool]:
        """Perform cache warmup for MCP resources.

        Pre-populates caches with tool schemas and resource lists
        to reduce cold-start latency.

        Returns:
            Dict of warmup task names to success status
        """
        warmup_manager = get_warmup_manager()

        # Register MCP-specific warmup tasks
        if self.manager and not warmup_manager.is_warmed_up:
            # Warmup: Refresh all tool schemas
            warmup_manager.register_warmup_task(
                name="mcp_tool_schemas", coroutine_factory=lambda: self.manager.get_all_tools(), priority=1
            )

            # Warmup: Pre-fetch resource lists
            warmup_manager.register_warmup_task(
                name="mcp_resources", coroutine_factory=lambda: self.manager.list_all_resources(), priority=2
            )

            # Warmup: Health check all servers
            warmup_manager.register_warmup_task(
                name="mcp_health_check", coroutine_factory=lambda: self.manager.health_check(), priority=3
            )

        # Execute warmup
        return await warmup_manager.warmup()

    async def cleanup(self):
        """Cleanup resources"""
        if self.manager:
            await self.manager.cleanup()
