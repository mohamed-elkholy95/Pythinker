"""Session screenshot domain models."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ScreenshotTrigger(str, Enum):
    TOOL_BEFORE = "tool_before"
    TOOL_AFTER = "tool_after"
    PERIODIC = "periodic"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class SessionScreenshot(BaseModel):
    id: str
    session_id: str
    sequence_number: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    gridfs_file_id: str
    thumbnail_file_id: str | None = None
    trigger: ScreenshotTrigger
    tool_call_id: str | None = None
    tool_name: str | None = None
    function_name: str | None = None
    action_type: str | None = None
    size_bytes: int = 0
