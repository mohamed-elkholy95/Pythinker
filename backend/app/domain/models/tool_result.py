from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar('T')

class ToolResult(BaseModel, Generic[T]):
    success: bool
    message: str | None = None
    data: T | None = None
