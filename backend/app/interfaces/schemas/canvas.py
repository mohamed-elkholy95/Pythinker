"""Request/response schemas for canvas API endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CreateProjectRequest(BaseModel):
    name: str = Field(default="Untitled Design", max_length=200)
    width: float = 1920.0
    height: float = 1080.0
    background: str = "#FFFFFF"
    session_id: str | None = None

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions(cls, v: float) -> float:
        if v < 1 or v > 8192:
            raise ValueError("Dimensions must be between 1 and 8192")
        return v


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    pages: list[dict[str, Any]] | None = None
    width: float | None = None
    height: float | None = None
    background: str | None = None
    thumbnail: str | None = None


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    width: int = 1024
    height: int = 1024

    @field_validator("width", "height")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v < 64 or v > 2048:
            raise ValueError("Image size must be between 64 and 2048")
        return v


class EditImageRequest(BaseModel):
    image_url: str = Field(..., max_length=2048)
    instruction: str = Field(..., min_length=1, max_length=2000)

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class RemoveBackgroundRequest(BaseModel):
    image_url: str = Field(..., max_length=2048)

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class AIEditRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000)


class ExportRequest(BaseModel):
    format: str = "png"
    quality: int = 90

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = {"png", "svg", "json"}
        if v not in allowed:
            raise ValueError(f"Format must be one of: {', '.join(sorted(allowed))}")
        return v


class ElementResponse(BaseModel):
    id: str
    type: str
    name: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False
    z_index: int = 0
    fill: dict[str, Any] | None = None
    stroke: dict[str, Any] | None = None
    shadow: dict[str, Any] | None = None
    corner_radius: float = 0.0
    text: str | None = None
    text_style: dict[str, Any] | None = None
    src: str | None = None
    points: list[float] | None = None
    children: list[str] | None = None
    scale_x: float = 1.0
    scale_y: float = 1.0


class PageResponse(BaseModel):
    id: str
    name: str
    width: float
    height: float
    background: str
    elements: list[ElementResponse] = Field(default_factory=list)
    sort_order: int = 0


class ProjectResponse(BaseModel):
    id: str
    user_id: str
    session_id: str | None = None
    name: str
    description: str
    pages: list[PageResponse] = Field(default_factory=list)
    width: float
    height: float
    background: str
    thumbnail: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


class VersionResponse(BaseModel):
    id: str
    project_id: str
    version: int
    name: str
    created_at: datetime


class VersionListResponse(BaseModel):
    versions: list[VersionResponse]
    total: int


class ImageResponse(BaseModel):
    urls: list[str]


class DeleteProjectResponse(BaseModel):
    """Response schema for deleting a canvas project."""

    deleted: bool = Field(..., description="Whether the project was successfully deleted")
