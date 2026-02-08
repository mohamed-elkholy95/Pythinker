"""Request/response schemas for connector API endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _mask_api_key(key: str | None) -> str | None:
    """Mask an API key to ****xxxx format."""
    if not key:
        return None
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


class ConnectorResponse(BaseModel):
    id: str
    name: str
    description: str
    connector_type: str
    icon: str
    brand_color: str
    category: str
    is_official: bool


class CustomApiConfigResponse(BaseModel):
    base_url: str
    auth_type: str
    api_key: str | None = None  # Masked
    headers: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class CustomMcpConfigResponse(BaseModel):
    transport: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class UserConnectorResponse(BaseModel):
    id: str
    connector_id: str | None = None
    connector_type: str
    name: str
    description: str
    icon: str
    status: str
    enabled: bool
    last_connected_at: datetime | None = None
    error_message: str | None = None
    api_config: CustomApiConfigResponse | None = None
    mcp_config: CustomMcpConfigResponse | None = None


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorResponse]
    total: int


class UserConnectorListResponse(BaseModel):
    connectors: list[UserConnectorResponse]
    total: int
    connected_count: int


class CreateCustomApiRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    base_url: str = Field(..., max_length=2048)
    auth_type: str = "none"
    api_key: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 headers allowed")
        return v


class CreateCustomMcpRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    transport: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "sse", "streamable-http"}
        if v not in allowed:
            raise ValueError(f"Transport must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 headers allowed")
        return v

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 env vars allowed")
        return v


class UpdateUserConnectorRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    api_config: dict[str, Any] | None = None
    mcp_config: dict[str, Any] | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: float | None = None
