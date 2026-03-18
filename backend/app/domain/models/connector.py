"""Connector domain models.

Connectors allow users to connect external APIs and MCP servers to Pythinker.
Three types: pre-built app connectors, custom API connectors, and custom MCP connectors.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ConnectorType(str, Enum):
    APP = "app"
    CUSTOM_API = "custom_api"
    CUSTOM_MCP = "custom_mcp"


class ConnectorStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class ConnectorAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class ConnectorAvailability(str, Enum):
    AVAILABLE = "available"
    COMING_SOON = "coming_soon"
    BUILT_IN = "built_in"


class CredentialField(BaseModel):
    """Describes a credential the user must provide to connect an app connector."""

    key: str
    label: str
    description: str = ""
    placeholder: str = ""
    required: bool = True
    secret: bool = True


class McpTemplate(BaseModel):
    """Pre-configured MCP server template for app connectors."""

    command: str
    args: list[str] = Field(default_factory=list)
    transport: str = "stdio"
    credential_fields: list[CredentialField] = Field(default_factory=list)


class CustomApiConfig(BaseModel):
    """Configuration for a custom API connector."""

    base_url: str
    auth_type: ConnectorAuthType = ConnectorAuthType.NONE
    api_key: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 header entries allowed")
        return v


# Allowlist for custom MCP stdio commands
MCP_COMMAND_ALLOWLIST = frozenset(
    {
        "npx",
        "node",
        "python",
        "python3",
        "uvx",
        "docker",
        "deno",
        "bun",
        "tsx",
        "ts-node",
        "pipx",
    }
)

# Blocked env var names for MCP connectors
MCP_BLOCKED_ENV_VARS = frozenset(
    {
        "PATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "HOME",
        "USER",
        "SHELL",
        "PYTHONPATH",
        "NODE_PATH",
        "CLASSPATH",
    }
)


class CustomMcpConfig(BaseModel):
    """Configuration for a custom MCP server connector."""

    transport: str  # stdio, sse, streamable-http
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "sse", "streamable-http"}
        if v not in allowed:
            raise ValueError(f"Transport must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if v and v not in MCP_COMMAND_ALLOWLIST:
                raise ValueError(f"Command must be one of: {', '.join(sorted(MCP_COMMAND_ALLOWLIST))}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v.startswith(("http://", "https://")):
                raise ValueError("URL must start with http:// or https://")
            if len(v) > 2048:
                raise ValueError("URL must not exceed 2048 characters")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 header entries allowed")
        return v

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 environment variables allowed")
        blocked = MCP_BLOCKED_ENV_VARS & set(v.keys())
        if blocked:
            raise ValueError(f"Blocked environment variables: {', '.join(sorted(blocked))}")
        return v


class Connector(BaseModel):
    """Catalog entry — pre-built app or custom definition."""

    id: str
    name: str
    description: str = ""
    connector_type: ConnectorType = ConnectorType.APP
    icon: str = ""
    brand_color: str = "#6366f1"
    category: str = "general"
    app_config: dict[str, str] | None = None
    api_config: CustomApiConfig | None = None
    mcp_config: CustomMcpConfig | None = None
    mcp_template: McpTemplate | None = None
    availability: str = ConnectorAvailability.AVAILABLE.value
    is_official: bool = False
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 100:
            raise ValueError("Name must be between 1 and 100 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("Description must not exceed 500 characters")
        return v


class UserConnector(BaseModel):
    """Per-user connection instance."""

    id: str
    user_id: str
    connector_id: str | None = None
    connector_type: ConnectorType
    name: str
    description: str = ""
    icon: str = ""
    status: ConnectorStatus = ConnectorStatus.PENDING
    enabled: bool = True
    api_config: CustomApiConfig | None = None
    mcp_config: CustomMcpConfig | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    last_connected_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
