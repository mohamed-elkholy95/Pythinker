"""Tool Input Schema Validation.

Provides Pydantic models for validating tool input arguments before execution.
This adds a layer of safety and validation to prevent malformed or dangerous inputs.

Usage:
    # Validate before execution
    args = ShellExecuteArgs(**raw_args)
    await shell_tool.execute(args.command, args.working_directory)

    # Or use the validator decorator
    @validate_tool_args(ShellExecuteArgs)
    async def shell_execute(args: ShellExecuteArgs):
        ...
"""

import re
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# Shell/Command Tool Schemas
# =============================================================================


class ShellExecuteArgs(BaseModel):
    """Arguments for shell command execution."""

    command: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Shell command to execute",
    )
    working_directory: str | None = Field(
        None,
        description="Working directory for command execution",
    )
    timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Command timeout in seconds",
    )
    capture_output: bool = Field(
        default=True,
        description="Whether to capture command output",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """Validate command doesn't contain obvious dangerous patterns."""
        # Block commands that could cause system-wide damage
        dangerous_patterns = [
            r"rm\s+-rf\s+/",
            r"dd\s+if=/dev/zero",
            r"mkfs\.",
            r":\(\)\s*{\s*:\|:\s*&\s*}",  # Fork bomb
            r">\s*/dev/sd[a-z]",  # Direct disk writes
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Command contains potentially dangerous pattern")

        return v

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, v: str | None) -> str | None:
        """Validate working directory path format."""
        if v is None:
            return v

        # Must be absolute path starting with / or ~ or relative
        if not v.startswith(("/home", "/tmp", "/var", "~", ".", "/workspace")):
            # Allow other paths but warn
            pass

        # Block obvious traversal attempts
        if ".." in v and v.count("..") > 3:
            raise ValueError("Excessive path traversal in working directory")

        return v


class ShellBackgroundArgs(ShellExecuteArgs):
    """Arguments for background shell execution."""

    name: str | None = Field(
        None,
        max_length=100,
        description="Optional name for the background process",
    )


# =============================================================================
# File Tool Schemas
# =============================================================================


class FileReadArgs(BaseModel):
    """Arguments for file read operations."""

    path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="File path to read",
    )
    encoding: str = Field(
        default="utf-8",
        description="File encoding",
    )
    max_lines: int | None = Field(
        None,
        ge=1,
        le=100000,
        description="Maximum lines to read",
    )
    start_line: int | None = Field(
        None,
        ge=1,
        description="Line number to start reading from",
    )

    @field_validator("encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        """Validate encoding is supported."""
        valid_encodings = {"utf-8", "utf-16", "utf-32", "ascii", "latin-1", "iso-8859-1", "cp1252", "utf-8-sig"}
        if v.lower() not in valid_encodings:
            raise ValueError(f"Unsupported encoding: {v}")
        return v.lower()


class FileWriteArgs(BaseModel):
    """Arguments for file write operations."""

    path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="File path to write",
    )
    content: str = Field(
        ...,
        max_length=10_000_000,  # 10MB limit
        description="Content to write",
    )
    encoding: str = Field(
        default="utf-8",
        description="File encoding",
    )
    create_directories: bool = Field(
        default=False,
        description="Create parent directories if they don't exist",
    )
    overwrite: bool = Field(
        default=True,
        description="Whether to overwrite existing file",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path doesn't target sensitive locations."""
        blocked_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/etc/sudoers",
            "~/.ssh/",
            "~/.gnupg/",
            "~/.aws/credentials",
            "/root/",
            "/boot/",
            "/sys/",
            "/proc/",
        ]

        for blocked in blocked_paths:
            if v.startswith(blocked) or blocked in v:
                raise ValueError(f"Cannot write to protected path: {blocked}")

        return v


class FileSearchArgs(BaseModel):
    """Arguments for file search operations."""

    pattern: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search pattern (regex or glob)",
    )
    directory: str | None = Field(
        None,
        description="Directory to search in",
    )
    file_pattern: str | None = Field(
        None,
        description="File name pattern to match",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Case sensitive search",
    )


# =============================================================================
# Browser Tool Schemas
# =============================================================================


class BrowserNavigateArgs(BaseModel):
    """Arguments for browser navigation."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="URL to navigate to",
    )
    wait_for: str | None = Field(
        None,
        description="Element to wait for before returning",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Navigation timeout in seconds",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and block dangerous protocols."""
        blocked_protocols = ["file://", "javascript:", "data:text/html"]

        for protocol in blocked_protocols:
            if v.lower().startswith(protocol):
                raise ValueError(f"Blocked protocol: {protocol}")

        # Basic URL format check
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("about:")) and not v.startswith(
            "/"
        ):
            # Allow relative URLs
            raise ValueError("URL must start with http://, https://, or be a relative path")

        return v


class BrowserClickArgs(BaseModel):
    """Arguments for browser click operations."""

    selector: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="CSS selector or element index",
    )
    button: str = Field(
        default="left",
        description="Mouse button (left, right, middle)",
    )
    double_click: bool = Field(
        default=False,
        description="Whether to double-click",
    )

    @field_validator("button")
    @classmethod
    def validate_button(cls, v: str) -> str:
        valid_buttons = {"left", "right", "middle"}
        if v.lower() not in valid_buttons:
            raise ValueError(f"Invalid button: {v}. Must be one of {valid_buttons}")
        return v.lower()


class BrowserInputArgs(BaseModel):
    """Arguments for browser input operations."""

    selector: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="CSS selector for input element",
    )
    text: str = Field(
        ...,
        max_length=50000,
        description="Text to input",
    )
    clear_first: bool = Field(
        default=True,
        description="Clear existing content before typing",
    )
    press_enter: bool = Field(
        default=False,
        description="Press Enter after typing",
    )


# =============================================================================
# Search Tool Schemas
# =============================================================================


class SearchWebArgs(BaseModel):
    """Arguments for enhanced multi-type web search."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query in Google search style",
    )
    search_type: str = Field(
        default="info",
        description="Type of search: info, news, image, academic, api, data, tool",
    )
    date_range: str | None = Field(
        None,
        description="Time range filter for search results",
    )
    expand_queries: bool = Field(
        default=False,
        description="Whether to search multiple query variants",
    )

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        """Validate search type is supported."""
        valid_types = {"info", "news", "image", "academic", "api", "data", "tool"}
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid search type: {v}. Must be one of {valid_types}")
        return v.lower()

    @field_validator("date_range")
    @classmethod
    def validate_date_range(cls, v: str | None) -> str | None:
        """Validate date range is supported."""
        if v is None:
            return v
        valid_ranges = {"all", "past_hour", "past_day", "past_week", "past_month", "past_year"}
        if v.lower() not in valid_ranges:
            raise ValueError(f"Invalid date range: {v}. Must be one of {valid_ranges}")
        return v.lower()


# =============================================================================
# MCP Tool Schemas
# =============================================================================


class MCPToolCallArgs(BaseModel):
    """Arguments for MCP tool calls."""

    server_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="MCP server name",
    )
    tool_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Tool name to call",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments",
    )

    @field_validator("server_name", "tool_name")
    @classmethod
    def validate_names(cls, v: str) -> str:
        """Validate names don't contain injection characters."""
        if any(c in v for c in [";", "|", "&", "$", "`", "\n", "\r"]):
            raise ValueError("Name contains invalid characters")
        return v


# =============================================================================
# Validation Utilities
# =============================================================================


def validate_tool_args(schema_class: type[T]) -> Callable:
    """Decorator to validate tool arguments against a Pydantic schema.

    Usage:
        @validate_tool_args(ShellExecuteArgs)
        async def shell_execute(**kwargs):
            # kwargs are now validated
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Validate kwargs against schema
            validated = schema_class(**kwargs)
            return await func(*args, **validated.model_dump())

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            validated = schema_class(**kwargs)
            return func(*args, **validated.model_dump())

        import asyncio

        return wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def validate_args(schema_class: type[T], args: dict[str, Any]) -> T:
    """Validate arguments against a schema and return validated model.

    Args:
        schema_class: Pydantic model class for validation
        args: Arguments to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        ValidationError: If validation fails
    """
    return schema_class(**args)


# Schema registry for dynamic validation
TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "shell_execute": ShellExecuteArgs,
    "shell_background": ShellBackgroundArgs,
    "file_read": FileReadArgs,
    "file_write": FileWriteArgs,
    "file_search": FileSearchArgs,
    "browser_navigate": BrowserNavigateArgs,
    "browser_click": BrowserClickArgs,
    "browser_input": BrowserInputArgs,
    "mcp_call": MCPToolCallArgs,
    "info_search_web": SearchWebArgs,
}


def get_schema_for_tool(tool_name: str) -> type[BaseModel] | None:
    """Get the validation schema for a tool by name.

    Args:
        tool_name: Name of the tool

    Returns:
        Pydantic model class or None if no schema defined
    """
    # Direct match
    if tool_name in TOOL_SCHEMAS:
        return TOOL_SCHEMAS[tool_name]

    # Try partial match
    for schema_name, schema_class in TOOL_SCHEMAS.items():
        if schema_name in tool_name.lower():
            return schema_class

    return None
