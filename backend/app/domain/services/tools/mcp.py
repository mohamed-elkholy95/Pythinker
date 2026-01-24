import os
import logging
import hashlib
import time
from typing import Dict, Any, List, Optional, Set
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
from app.domain.models.mcp_resource import (
    MCPResource,
    MCPResourceContent,
    ResourceTemplate,
    ResourceListResult,
    ResourceReadResult,
    ResourceType,
)

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
    """MCP Client Manager with health checking, dynamic reload, and resource support"""

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

        # Resource management
        self._resources_cache: Dict[str, List[MCPResource]] = {}
        self._templates_cache: Dict[str, List[ResourceTemplate]] = {}
        self._resource_subscriptions: Dict[str, Set[str]] = {}  # server -> set of URIs

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

            # Also cache resources if available
            await self._cache_server_resources(server_name, session)

        except Exception as e:
            logger.error(f"Failed to get tool list from server {server_name}: {e}")
            self._tools_cache[server_name] = []
            self._server_health[server_name] = ServerHealth(
                server_name=server_name,
                healthy=False,
                last_error=str(e),
                consecutive_failures=1
            )

    async def _cache_server_resources(self, server_name: str, session: ClientSession):
        """Cache server resources and templates."""
        try:
            # List resources from server
            resources_response = await session.list_resources()

            resources = []
            templates = []

            if resources_response and hasattr(resources_response, 'resources'):
                for res in resources_response.resources:
                    resources.append(MCPResource(
                        uri=res.uri,
                        name=res.name,
                        description=getattr(res, 'description', None),
                        mime_type=getattr(res, 'mimeType', None),
                        server_name=server_name,
                        annotations=getattr(res, 'annotations', {}) or {}
                    ))

            # Check for resource templates
            if hasattr(resources_response, 'resourceTemplates') and resources_response.resourceTemplates:
                for tmpl in resources_response.resourceTemplates:
                    templates.append(ResourceTemplate(
                        uri_template=tmpl.uriTemplate,
                        name=tmpl.name,
                        description=getattr(tmpl, 'description', None),
                        mime_type=getattr(tmpl, 'mimeType', None),
                        server_name=server_name
                    ))

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
            errors=errors
        )

    async def read_resource(self, uri: str, server_name: Optional[str] = None) -> ResourceReadResult:
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
            return ResourceReadResult(
                success=False,
                error=f"No server found providing resource: {uri}"
            )

        session = self._clients.get(target_server)
        if not session:
            return ResourceReadResult(
                success=False,
                error=f"Server {target_server} not connected"
            )

        try:
            # Call MCP read_resource
            result = await session.read_resource(uri)

            if not result or not hasattr(result, 'contents') or not result.contents:
                return ResourceReadResult(
                    success=False,
                    error="Resource returned no content"
                )

            # Process the first content item (MCP can return multiple)
            content_item = result.contents[0]

            # Determine content type
            if hasattr(content_item, 'text') and content_item.text is not None:
                resource_content = MCPResourceContent(
                    uri=uri,
                    resource_type=ResourceType.TEXT,
                    text=content_item.text,
                    mime_type=getattr(content_item, 'mimeType', None)
                )
            elif hasattr(content_item, 'blob') and content_item.blob is not None:
                resource_content = MCPResourceContent(
                    uri=uri,
                    resource_type=ResourceType.BLOB,
                    blob=content_item.blob,
                    mime_type=getattr(content_item, 'mimeType', None)
                )
            else:
                return ResourceReadResult(
                    success=False,
                    error="Resource content format not recognized"
                )

            return ResourceReadResult(
                success=True,
                content=resource_content,
                read_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}")
            return ResourceReadResult(
                success=False,
                error=str(e),
                read_time_ms=(time.time() - start_time) * 1000
            )

    def _find_resource_server(self, uri: str) -> Optional[str]:
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
        pattern = template.replace('{', '(?P<').replace('}', '>[^/]+)')
        pattern = f"^{pattern}$"

        try:
            return bool(re.match(pattern, uri))
        except re.error:
            return False

    async def subscribe_resource(self, uri: str, server_name: Optional[str] = None) -> bool:
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

    async def unsubscribe_resource(self, uri: str, server_name: Optional[str] = None) -> bool:
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

    def get_cached_resources(self, server_name: Optional[str] = None) -> List[MCPResource]:
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

    def get_cached_templates(self, server_name: Optional[str] = None) -> List[ResourceTemplate]:
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
    """MCP Tool class with tool invocation and resource management.

    Provides access to:
    - MCP server tools (dynamically discovered)
    - MCP resources (listing, reading, subscribing)
    - Server health monitoring
    """

    name = "mcp"

    # Built-in resource management tools
    RESOURCE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "mcp_list_resources",
                "description": "List all available MCP resources across connected servers. Returns URIs, names, and descriptions of resources that can be read.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "server_name": {
                            "type": "string",
                            "description": "Optional: Filter by specific MCP server name"
                        }
                    },
                    "required": []
                }
            }
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
                            "description": "The URI of the resource to read (e.g., 'file:///path/to/file', 'db://table/record')"
                        },
                        "server_name": {
                            "type": "string",
                            "description": "Optional: Specific server to read from (auto-detected if not provided)"
                        }
                    },
                    "required": ["uri"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_server_status",
                "description": "Get health status and statistics for connected MCP servers.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

    def __init__(self):
        super().__init__()
        self._initialized = False
        self._tools = []
        self.manager: Optional[MCPClientManager] = None

    async def initialized(self, config: Optional[MCPConfig] = None):
        """Ensure manager is initialized"""
        if not self._initialized:
            self.manager = MCPClientManager(config)
            await self.manager.initialize()
            self._tools = await self.manager.get_all_tools()
            self._initialized = True

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all tool definitions including resource management tools."""
        # Combine MCP server tools with built-in resource tools
        all_tools = list(self._tools)  # Copy server tools

        # Add resource management tools if manager is initialized
        if self._initialized and self.manager:
            all_tools.extend(self.RESOURCE_TOOLS)

        return all_tools

    def has_function(self, function_name: str) -> bool:
        """Check if specified function exists (including dynamic MCP tools)"""
        # Check built-in resource tools
        resource_tool_names = {t['function']['name'] for t in self.RESOURCE_TOOLS}
        if function_name in resource_tool_names:
            return True

        # Check MCP server tools
        for tool in self._tools:
            if tool['function']['name'] == function_name:
                return True

        return False

    async def invoke_function(self, function_name: str, **kwargs) -> ToolResult:
        """Call tool function (MCP server tool or built-in resource tool)."""
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
        return await self.manager.call_tool(function_name, kwargs)

    async def _list_resources(self, server_name: Optional[str] = None) -> ToolResult:
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
                output_parts.append(f"\n**Errors:**")
                for srv, err in result.errors.items():
                    output_parts.append(f"- {srv}: {err}")

            if not resources and not templates:
                output_parts.append("No resources available from connected MCP servers.")

            return ToolResult(
                success=True,
                data="\n".join(output_parts)
            )

        except Exception as e:
            logger.error(f"Failed to list resources: {e}")
            return ToolResult(success=False, message=f"Failed to list resources: {str(e)}")

    async def _read_resource(self, uri: str, server_name: Optional[str] = None) -> ToolResult:
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

                return ToolResult(
                    success=True,
                    data=f"{metadata}\n\n---\n\n{data}"
                )
            else:
                # Binary content - provide info only
                return ToolResult(
                    success=True,
                    data=f"Binary resource read successfully.\nURI: {uri}\nMIME Type: {result.content.mime_type or 'unknown'}\nSize: {len(result.content.blob or b'')} bytes"
                )

        except Exception as e:
            logger.error(f"Failed to read resource {uri}: {e}")
            return ToolResult(success=False, message=f"Failed to read resource: {str(e)}")

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
                        f"  - {name}: {stats.call_count} calls, "
                        f"{success_rate:.0f}% success, {avg_duration:.0f}ms avg"
                    )

            return ToolResult(success=True, data="\n".join(output_parts))

        except Exception as e:
            logger.error(f"Failed to get server status: {e}")
            return ToolResult(success=False, message=f"Failed to get status: {str(e)}")

    async def refresh_resources(self) -> None:
        """Refresh the resource cache from all servers."""
        if self.manager:
            await self.manager.list_all_resources()

    async def cleanup(self):
        """Cleanup resources"""
        if self.manager:
            await self.manager.cleanup()
