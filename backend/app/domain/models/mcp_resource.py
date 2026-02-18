"""MCP Resource models for resource listing and reading.

Resources are a way for MCP servers to expose data that can be read by clients.
This enables access to files, database records, API responses, and other data
sources through a standardized interface.

Per MCP specification, resources:
- Have URIs for identification
- Can be text or binary (blob) content
- Support MIME types for content negotiation
- Can be subscribed to for real-time updates
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Type of resource content."""

    TEXT = "text"
    BLOB = "blob"


class MCPResource(BaseModel):
    """An MCP resource available from a server.

    Represents a resource that can be read through the MCP protocol.
    Resources are identified by URIs and can contain text or binary content.
    """

    uri: str = Field(description="Unique identifier for the resource (URI format)")
    name: str = Field(description="Human-readable name for the resource")
    description: str | None = Field(default=None, description="Description of the resource")
    mime_type: str | None = Field(default=None, description="MIME type of the resource content")
    server_name: str = Field(description="Name of the MCP server providing this resource")

    # Extended metadata
    size_bytes: int | None = Field(default=None, description="Size of resource in bytes if known")
    last_modified: datetime | None = Field(default=None, description="Last modification time")
    annotations: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class MCPResourceContent(BaseModel):
    """Content of an MCP resource after reading.

    Contains the actual data from a resource read operation.
    """

    uri: str = Field(description="URI of the resource that was read")
    resource_type: ResourceType = Field(description="Type of content (text or blob)")
    text: str | None = Field(default=None, description="Text content if resource_type is text")
    blob: bytes | None = Field(default=None, description="Binary content if resource_type is blob")
    mime_type: str | None = Field(default=None, description="MIME type of the content")

    @property
    def content(self) -> str | bytes | None:
        """Get the content regardless of type."""
        return self.text if self.resource_type == ResourceType.TEXT else self.blob

    @property
    def is_text(self) -> bool:
        """Check if content is text."""
        return self.resource_type == ResourceType.TEXT


class ResourceTemplate(BaseModel):
    """A template for generating resource URIs.

    Templates allow dynamic resource generation based on parameters.
    For example: "file://{path}" or "db://users/{user_id}"
    """

    uri_template: str = Field(description="URI template with placeholders")
    name: str = Field(description="Human-readable name for the template")
    description: str | None = Field(default=None, description="Description of the template")
    mime_type: str | None = Field(default=None, description="Expected MIME type of generated resources")
    server_name: str = Field(description="Name of the MCP server providing this template")


class ResourceSubscription(BaseModel):
    """Subscription to resource updates.

    Allows clients to receive notifications when resources change.
    """

    uri: str = Field(description="URI of the subscribed resource")
    server_name: str = Field(description="MCP server providing the resource")
    subscribed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active: bool = Field(default=True)


class ResourceListResult(BaseModel):
    """Result of listing resources from MCP servers."""

    resources: list[MCPResource] = Field(default_factory=list)
    templates: list[ResourceTemplate] = Field(default_factory=list)
    total_count: int = Field(default=0)
    servers_queried: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict, description="Errors by server name")


class ResourceReadResult(BaseModel):
    """Result of reading a resource."""

    success: bool = Field(description="Whether the read was successful")
    content: MCPResourceContent | None = Field(default=None)
    error: str | None = Field(default=None, description="Error message if read failed")
    read_time_ms: float = Field(default=0, description="Time taken to read in milliseconds")
