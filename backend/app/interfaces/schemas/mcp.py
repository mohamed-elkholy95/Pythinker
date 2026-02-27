"""Pydantic response schemas for MCP REST endpoints."""

from pydantic import BaseModel, Field


class McpServerStatus(BaseModel):
    """Health status for a single MCP server."""

    name: str
    healthy: bool
    degraded: bool = False
    transport: str | None = None  # "stdio", "sse", "streamable_http"
    tools_count: int = 0
    avg_response_time_ms: float = 0.0
    success_rate: float = 100.0
    last_error: str | None = None
    last_check: str | None = None  # ISO timestamp
    consecutive_failures: int = 0


class McpStatusResponse(BaseModel):
    """Aggregated MCP health summary."""

    overall_status: str = "unknown"  # "healthy", "degraded", "unhealthy", "unknown"
    total_servers: int = 0
    healthy_count: int = 0
    unhealthy_count: int = 0
    degraded_count: int = 0
    total_tools: int = 0
    servers: list[McpServerStatus] = Field(default_factory=list)


class McpToolInfo(BaseModel):
    """Information about a single MCP tool."""

    name: str
    description: str | None = None
    server_name: str
    parameters: dict | None = None  # JSON Schema


class McpToolListResponse(BaseModel):
    """List of tools for one or all MCP servers."""

    server_name: str | None = None
    tools: list[McpToolInfo] = Field(default_factory=list)
    total: int = 0


class McpTestConnectionRequest(BaseModel):
    """Request body for test-connection endpoint."""

    name: str
    transport: str  # "stdio", "sse", "streamable_http"
    command: str | None = None  # for stdio
    args: list[str] | None = None  # for stdio
    url: str | None = None  # for sse / streamable_http
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None


class McpTestConnectionResponse(BaseModel):
    """Result of a test-connection attempt."""

    success: bool
    latency_ms: float = 0.0
    tools_count: int = 0
    error: str | None = None
