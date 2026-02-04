from typing import Generic, Self, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Result of a tool execution.

    Attributes:
        success: Whether the tool execution succeeded
        message: Human-readable message (required for errors, optional for success)
        data: Structured data for programmatic access
    """

    success: bool
    message: str | None = None
    data: T | None = None

    @classmethod
    def ok(cls, message: str | None = None, data: T | None = None) -> Self:
        """Create a successful result.

        Args:
            message: Optional success message for display
            data: Optional structured data

        Returns:
            ToolResult with success=True
        """
        return cls(success=True, message=message, data=data)

    @classmethod
    def error(cls, message: str, data: T | None = None) -> Self:
        """Create an error result.

        Args:
            message: Error message (required)
            data: Optional structured data with error details

        Returns:
            ToolResult with success=False
        """
        return cls(success=False, message=message, data=data)
