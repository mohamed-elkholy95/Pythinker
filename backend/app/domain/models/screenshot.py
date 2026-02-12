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
    storage_key: str  # MinIO S3 object key (e.g. "{session_id}/0001_periodic.jpg")
    thumbnail_storage_key: str | None = None
    trigger: ScreenshotTrigger
    tool_call_id: str | None = None
    tool_name: str | None = None
    function_name: str | None = None
    action_type: str | None = None
    size_bytes: int = 0
    # Deduplication fields
    perceptual_hash: str | None = None
    is_duplicate: bool = False
    original_storage_key: str | None = None  # Points to original if duplicate
