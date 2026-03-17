"""REST endpoints for MCP server health, tool discovery, and test-connection."""

import contextlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.domain.models.mcp_config import MCPConfig, MCPServerConfig, MCPTransport
from app.domain.models.user import User
from app.domain.services.tools.mcp import MCPClientManager
from app.domain.services.tools.mcp_registry import get_mcp_registry
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.mcp import (
    McpServerStatus,
    McpStatusResponse,
    McpTestConnectionRequest,
    McpTestConnectionResponse,
    McpToolInfo,
    McpToolListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _build_server_status(name: str, health, config: MCPServerConfig | None = None) -> McpServerStatus:
    """Convert a ServerHealth dataclass into an McpServerStatus schema."""
    return McpServerStatus(
        name=name,
        healthy=health.healthy,
        degraded=health.degraded,
        transport=config.transport.value if config else None,
        tools_count=health.tools_count,
        avg_response_time_ms=round(health.avg_response_time_ms, 2),
        success_rate=round(health.success_rate * 100, 1),
        last_error=health.last_error,
        last_check=health.last_check.isoformat() if health.last_check else None,
        consecutive_failures=health.consecutive_failures,
    )


@router.get("/status")
async def get_mcp_status(
    current_user: User = Depends(get_current_user),
) -> APIResponse[McpStatusResponse]:
    """Aggregated health summary for all MCP servers."""
    registry = get_mcp_registry()
    entry = registry.get(current_user.id)

    if entry is None or entry.manager is None:
        return APIResponse.success(McpStatusResponse())

    manager = entry.manager
    health_status = manager.get_health_status()
    config = manager._config

    servers: list[McpServerStatus] = []
    for name, health in health_status.items():
        srv_config = config.mcp_servers.get(name) if config else None
        servers.append(_build_server_status(name, health, srv_config))

    healthy = sum(1 for s in servers if s.healthy and not s.degraded)
    degraded = sum(1 for s in servers if s.degraded)
    unhealthy = sum(1 for s in servers if not s.healthy)
    total_tools = sum(s.tools_count for s in servers)

    if unhealthy > 0:
        overall = "unhealthy"
    elif degraded > 0:
        overall = "degraded"
    elif servers:
        overall = "healthy"
    else:
        overall = "unknown"

    return APIResponse.success(
        McpStatusResponse(
            overall_status=overall,
            total_servers=len(servers),
            healthy_count=healthy,
            unhealthy_count=unhealthy,
            degraded_count=degraded,
            total_tools=total_tools,
            servers=servers,
        )
    )


@router.get("/servers")
async def get_mcp_servers(
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[McpServerStatus]]:
    """List all MCP servers with individual health info."""
    registry = get_mcp_registry()
    entry = registry.get(current_user.id)

    if entry is None or entry.manager is None:
        return APIResponse.success([])

    manager = entry.manager
    health_status = manager.get_health_status()
    config = manager._config

    servers = [
        _build_server_status(name, health, config.mcp_servers.get(name) if config else None)
        for name, health in health_status.items()
    ]
    return APIResponse.success(servers)


@router.get("/servers/{server_name}/tools")
async def get_mcp_server_tools(
    server_name: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[McpToolListResponse]:
    """List tool schemas for a specific MCP server."""
    registry = get_mcp_registry()
    entry = registry.get(current_user.id)

    if entry is None or entry.manager is None:
        raise HTTPException(status_code=404, detail="No active MCP session")

    all_tools = await entry.manager.get_all_tools()
    # Filter tools belonging to this server (mcp__<server>__<tool> convention)
    matched: list[McpToolInfo] = []
    for tool_def in all_tools:
        func = tool_def.get("function", {})
        tool_name: str = func.get("name", "")
        parts = tool_name.split("__")
        srv = parts[1] if len(parts) >= 3 else "default"
        if srv == server_name:
            matched.append(
                McpToolInfo(
                    name=tool_name,
                    description=func.get("description"),
                    server_name=srv,
                    parameters=func.get("parameters"),
                )
            )

    return APIResponse.success(
        McpToolListResponse(
            server_name=server_name,
            tools=matched,
            total=len(matched),
        )
    )


@router.post("/test-connection")
async def test_mcp_connection(
    request: McpTestConnectionRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[McpTestConnectionResponse]:
    """Test an MCP server configuration before saving.

    Creates an ephemeral MCPClientManager, connects, counts tools,
    and tears down. Returns latency and tool count on success.
    """
    # Build an MCPServerConfig from the request
    try:
        transport = MCPTransport(request.transport)
    except ValueError:
        return APIResponse.success(
            McpTestConnectionResponse(
                success=False,
                error=f"Unknown transport: {request.transport}",
            )
        )

    server_config = MCPServerConfig(
        transport=transport,
        command=request.command,
        args=request.args,
        url=request.url,
        env=request.env,
        headers=request.headers,
    )

    config = MCPConfig(mcp_servers={request.name: server_config})
    manager = MCPClientManager(config)

    start = time.monotonic()
    try:
        await manager.initialize()
        tools = await manager.get_all_tools()
        latency_ms = (time.monotonic() - start) * 1000

        result = McpTestConnectionResponse(
            success=True,
            latency_ms=round(latency_ms, 1),
            tools_count=len(tools),
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        logger.warning("MCP test-connection failed for %s: %s", request.name, e)
        result = McpTestConnectionResponse(
            success=False,
            latency_ms=round(latency_ms, 1),
            error=str(e),
        )
    finally:
        with contextlib.suppress(Exception):
            await manager.cleanup()

    return APIResponse.success(result)
