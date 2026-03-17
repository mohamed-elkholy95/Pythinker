"""Screenshot API response schemas."""

from pydantic import BaseModel


class ScreenshotMetadataResponse(BaseModel):
    id: str
    session_id: str
    sequence_number: int
    timestamp: float
    trigger: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    function_name: str | None = None
    action_type: str | None = None
    size_bytes: int
    has_thumbnail: bool


class ScreenshotListResponse(BaseModel):
    screenshots: list[ScreenshotMetadataResponse]
    total: int
