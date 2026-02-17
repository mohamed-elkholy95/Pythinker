from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class MCPTransport(str, Enum):
    """MCP transport types"""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class MCPServerConfig(BaseModel):
    """
    MCP server configuration model
    """

    # For stdio transport
    command: str | None = None
    args: list[str] | None = None

    # For HTTP-based transports
    url: str | None = None
    headers: dict[str, str] | None = None

    # Common fields
    transport: MCPTransport
    enabled: bool = Field(default=True)
    description: str | None = None
    env: dict[str, str] | None = None

    @field_validator("url")
    @classmethod
    def validate_url_for_http_transport(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate URL is required for HTTP-based transports"""
        if info.data:
            transport = info.data.get("transport")
            if transport in [MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP] and not v:
                raise ValueError("URL is required for HTTP-based transports")
        return v

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate command is required for stdio transport"""
        if info.data:
            transport = info.data.get("transport")
            if transport == MCPTransport.STDIO and not v:
                raise ValueError("Command is required for stdio transport")
        return v

    model_config = ConfigDict(extra="allow")


class MCPConfig(BaseModel):
    """
    MCP configuration model containing all server configurations
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        populate_by_name=True,
    )

    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict, alias="mcpServers")
