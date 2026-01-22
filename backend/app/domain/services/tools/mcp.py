import os
import logging
from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool as MCPTool

from app.domain.services.tools.base import BaseTool, tool
from app.domain.models.tool_result import ToolResult
from app.domain.models.mcp_config import MCPConfig, MCPServerConfig

logger = logging.getLogger(__name__)


class MCPClientManager:
    """MCP Client Manager"""

    def __init__(self, config: Optional[MCPConfig] = None):
        self._clients: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._tools_cache: Dict[str, List[MCPTool]] = {}
        self._initialized = False
        self._config = config

    async def initialize(self):
        """Initialize MCP client manager"""
        if self._initialized:
            return

        try:
            logger.info(f"Loaded {len(self._config.mcpServers)} MCP server configurations")

            # Connect to all enabled servers
            await self._connect_servers()

            self._initialized = True
            logger.info("MCP client manager initialized successfully")

        except Exception as e:
            logger.error(f"MCP client manager initialization failed: {e}")
            raise


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
        """Cache server tool list"""
        try:
            tools_response = await session.list_tools()
            tools = tools_response.tools if tools_response else []
            self._tools_cache[server_name] = tools
            logger.info(f"Server {server_name} provides {len(tools)} tools")

        except Exception as e:
            logger.error(f"Failed to get tool list from server {server_name}: {e}")
            self._tools_cache[server_name] = []

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
        """Call MCP tool"""
        try:
            # Parse tool name
            server_name = None
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

            # Get client session
            session = self._clients.get(server_name)
            if not session:
                return ToolResult(
                    success=False,
                    message=f"MCP server {server_name} not connected"
                )

            # Call tool
            result = await session.call_tool(original_tool_name, arguments)

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
