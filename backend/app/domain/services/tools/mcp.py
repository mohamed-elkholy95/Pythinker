import os
import logging
import hashlib
from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack
from datetime import datetime
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool as MCPToolType

from app.domain.services.tools.base import BaseTool, tool
from app.domain.models.tool_result import ToolResult
from app.domain.models.mcp_config import MCPConfig, MCPServerConfig

logger = logging.getLogger(__name__)


@dataclass
class ServerHealth:
    """Health status for an MCP server"""
    server_name: str
    healthy: bool = True
    last_check: datetime = field(default_factory=datetime.now)
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    tools_count: int = 0


@dataclass
class ToolUsageStats:
    """Usage statistics for a tool"""
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0
    last_used: Optional[datetime] = None


class MCPClientManager:
    """MCP Client Manager with health checking and dynamic reload"""

    def __init__(self, config: Optional[MCPConfig] = None):
        self._clients: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._tools_cache: Dict[str, List[MCPToolType]] = {}
        self._initialized = False
        self._config = config

        # Health tracking
        self._server_health: Dict[str, ServerHealth] = {}
        self._tool_usage: Dict[str, ToolUsageStats] = {}
        self._config_hash: Optional[str] = None
        self._max_consecutive_failures = 3

    async def initialize(self):
        """Initialize MCP client manager"""
        if self._initialized:
            return

        try:
            logger.info(f"Loaded {len(self._config.mcpServers)} MCP server configurations")

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
        return hashlib.md5(config_str.encode()).hexdigest()

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

    async def health_check(self) -> Dict[str, ServerHealth]:
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
                health.last_check = datetime.now()
                logger.debug(f"Health check passed for {server_name}")

            except Exception as e:
                health.healthy = False
                health.last_error = str(e)
                health.consecutive_failures += 1
                health.last_check = datetime.now()
                logger.warning(f"Health check failed for {server_name}: {e}")

            self._server_health[server_name] = health

        return self._server_health

    async def reconnect_unhealthy(self) -> List[str]:
        """
        Attempt to reconnect unhealthy servers.

        Returns:
            List of successfully reconnected server names
        """
        reconnected = []

        for server_name, health in self._server_health.items():
            if not health.healthy and health.consecutive_failures <= self._max_consecutive_failures:
                server_config = self._config.mcpServers.get(server_name)
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

    def record_tool_usage(self, tool_name: str, success: bool, duration_ms: float) -> None:
        """Record tool usage statistics"""
        if tool_name not in self._tool_usage:
            self._tool_usage[tool_name] = ToolUsageStats(tool_name=tool_name)

        stats = self._tool_usage[tool_name]
        stats.call_count += 1
        stats.total_duration_ms += duration_ms
        stats.last_used = datetime.now()

        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1

    def get_tool_stats(self) -> Dict[str, ToolUsageStats]:
        """Get tool usage statistics"""
        return self._tool_usage

    def get_health_status(self) -> Dict[str, ServerHealth]:
        """Get current health status of all servers"""
        return self._server_health


    async def _connect_servers(self):
        """Connect to all enabled MCP servers"""
        for server_name, server_config in self._config.mcpServers.items():
            if not server_config.enabled:
                continue

            try:
                await self._connect_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")
                # Continue connecting to other servers
                continue

    async def _connect_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to a single MCP server"""
        try:
            transport_type = server_config.transport

            if transport_type == 'stdio':
                await self._connect_stdio_server(server_name, server_config)
            elif transport_type == 'http' or transport_type == 'sse':
                await self._connect_http_server(server_name, server_config)
            elif transport_type == 'streamable-http':
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
            raise ValueError(f"Server {server_name} missing command configuration")


        # Create server parameters (path handling done in config provider)
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ, **env}
        )

        try:
            # Establish connection
            stdio_transport = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = stdio_transport

            # Create session
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            # Initialize session
            await session.initialize()

            # Cache client
            self._clients[server_name] = session

            # Get and cache tool list
            await self._cache_server_tools(server_name, session)

            logger.info(f"Successfully connected to stdio MCP server: {server_name}")

        except Exception as e:
            logger.error(f"Failed to connect to stdio MCP server {server_name}: {e}")
            raise

    async def _connect_http_server(self, server_name: str, server_config: MCPServerConfig):
        """Connect to HTTP MCP server"""
        url = server_config.url
        if not url:
            raise ValueError(f"Server {server_name} missing url configuration")

        try:
            # Establish SSE connection
            sse_transport = await self._exit_stack.enter_async_context(
                sse_client(url)
            )
            read_stream, write_stream = sse_transport

            # Create session
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

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
            raise ValueError(f"Server {server_name} missing url configuration")

        # Get optional configuration
        headers = server_config.headers or {}

        try:
            # Prepare connection parameters
            client_params = {"url": url}

            # Add custom headers
            if headers:
                client_params["headers"] = headers

            # Establish streamable-http connection
            streamable_transport = await self._exit_stack.enter_async_context(
                streamablehttp_client(**client_params)
            )

            # Unpack returned streams and optional third parameter
            if len(streamable_transport) == 3:
                read_stream, write_stream, _ = streamable_transport
            else:
                read_stream, write_stream = streamable_transport

            # Create MCP session
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

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
        """Cache server tool list and initialize health tracking"""
        try:
            tools_response = await session.list_tools()
            tools = tools_response.tools if tools_response else []
            self._tools_cache[server_name] = tools

            # Initialize health tracking
            self._server_health[server_name] = ServerHealth(
                server_name=server_name,
                healthy=True,
                tools_count=len(tools),
                last_check=datetime.now()
            )

            logger.info(f"Server {server_name} provides {len(tools)} tools")

        except Exception as e:
            logger.error(f"Failed to get tool list from server {server_name}: {e}")
            self._tools_cache[server_name] = []
            self._server_health[server_name] = ServerHealth(
                server_name=server_name,
                healthy=False,
                last_error=str(e),
                consecutive_failures=1
            )

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all MCP tools"""
        all_tools = []

        for server_name, tools in self._tools_cache.items():
            for tool in tools:
                # Generate tool name, avoid duplicate mcp_ prefix
                if server_name.startswith('mcp_'):
                    tool_name = f"{server_name}_{tool.name}"
                else:
                    tool_name = f"mcp_{server_name}_{tool.name}"

                # Convert to standard tool format
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"[{server_name}] {tool.description or tool.name}",
                        "parameters": tool.inputSchema
                    }
                }
                all_tools.append(tool_schema)

        return all_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Call MCP tool with health tracking and usage statistics"""
        import time
        start_time = time.time()
        server_name = None

        try:
            # Parse tool name
            original_tool_name = None

            # Find matching server name
            for srv_name in self._config.mcpServers.keys():
                expected_prefix = srv_name if srv_name.startswith('mcp_') else f"mcp_{srv_name}"
                if tool_name.startswith(f"{expected_prefix}_"):
                    server_name = srv_name
                    original_tool_name = tool_name[len(expected_prefix) + 1:]
                    break

            if not server_name or not original_tool_name:
                raise ValueError(f"Unable to parse MCP tool name: {tool_name}")

            # Check server health before calling
            health = self._server_health.get(server_name)
            if health and not health.healthy and health.consecutive_failures >= self._max_consecutive_failures:
                return ToolResult(
                    success=False,
                    message=f"MCP server {server_name} is unhealthy (failures: {health.consecutive_failures})"
                )

            # Get client session
            session = self._clients.get(server_name)
            if not session:
                return ToolResult(
                    success=False,
                    message=f"MCP server {server_name} not connected"
                )

            # Call tool
            result = await session.call_tool(original_tool_name, arguments)

            # Record successful call
            duration_ms = (time.time() - start_time) * 1000
            self.record_tool_usage(tool_name, success=True, duration_ms=duration_ms)

            # Mark server as healthy on success
            if server_name in self._server_health:
                self._server_health[server_name].healthy = True
                self._server_health[server_name].consecutive_failures = 0
                self._server_health[server_name].last_check = datetime.now()

            # Process result
            if result:
                content = []
                if hasattr(result, 'content') and result.content:
                    for item in result.content:
                        if hasattr(item, 'text'):
                            content.append(item.text)
                        else:
                            content.append(str(item))

                return ToolResult(
                    success=True,
                    data='\n'.join(content) if content else "Tool executed successfully"
                )
            else:
                return ToolResult(
                    success=True,
                    data="Tool executed successfully"
                )

        except Exception as e:
            # Record failed call
            duration_ms = (time.time() - start_time) * 1000
            self.record_tool_usage(tool_name, success=False, duration_ms=duration_ms)

            # Mark server as unhealthy on failure
            if server_name and server_name in self._server_health:
                health = self._server_health[server_name]
                health.healthy = False
                health.consecutive_failures += 1
                health.last_error = str(e)
                health.last_check = datetime.now()

            logger.error(f"Failed to call MCP tool {tool_name}: {e}")
            return ToolResult(
                success=False,
                message=f"Failed to call MCP tool: {str(e)}"
            )

    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self._exit_stack.aclose()
            self._clients.clear()
            self._tools_cache.clear()
            self._initialized = False
            logger.info("MCP client manager cleaned up")

        except Exception as e:
            logger.error(f"Failed to cleanup MCP client manager: {e}")


class MCPTool(BaseTool):
    """MCP Tool class"""

    name = "mcp"

    def __init__(self):
        super().__init__()
        self._initialized = False
        self._tools = []

    async def initialized(self, config: Optional[MCPConfig] = None):
        """Ensure manager is initialized"""
        if not self._initialized:
            self.manager = MCPClientManager(config)
            await self.manager.initialize()
            self._tools = await self.manager.get_all_tools()
            self._initialized = True

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get synchronous tool definitions (base tools)"""
        return self._tools

    def has_function(self, function_name: str) -> bool:
        """Check if specified function exists (including dynamic MCP tools)"""
        # Check if it's an MCP tool
        for tool in self._tools:
            if tool['function']['name'] == function_name:
                return True
        return False

    async def invoke_function(self, function_name: str, **kwargs) -> ToolResult:
        """Call tool function"""
        return await self.manager.call_tool(function_name, kwargs)

    async def cleanup(self):
        """Cleanup resources"""
        if self.manager:
            await self.manager.cleanup()
