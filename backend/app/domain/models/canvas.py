"""Canvas domain models for the interactive AI canvas editor."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ElementType(str, Enum):
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    TEXT = "text"
    IMAGE = "image"
    LINE = "line"
    PATH = "path"
    GROUP = "group"


class FillType(str, Enum):
    SOLID = "solid"
    GRADIENT = "gradient"


class GradientType(str, Enum):
    LINEAR = "linear"
    RADIAL = "radial"


class ExportFormat(str, Enum):
    PNG = "png"
    SVG = "svg"
    JSON = "json"


class SolidFill(BaseModel):
    type: FillType = FillType.SOLID
    color: str = "#000000"


class GradientStop(BaseModel):
    offset: float = 0.0  # 0-1
    color: str = "#000000"


class GradientFill(BaseModel):
    type: FillType = FillType.GRADIENT
    gradient_type: GradientType = GradientType.LINEAR
    stops: list[GradientStop] = Field(default_factory=list)
    angle: float = 0.0  # degrees, for linear gradients


Fill = SolidFill | GradientFill


class Stroke(BaseModel):
    color: str = "#000000"
    width: float = 1.0
    dash: list[float] | None = None  # dash pattern e.g. [5, 5]


class Shadow(BaseModel):
    color: str = "rgba(0,0,0,0.3)"
    blur: float = 10.0
    offset_x: float = 5.0
    offset_y: float = 5.0


class TextStyle(BaseModel):
    font_family: str = "Arial"
    font_size: float = 16.0
    font_weight: str = "normal"  # "normal", "bold", etc.
    font_style: str = "normal"  # "normal", "italic"
    text_align: str = "left"  # "left", "center", "right"
    vertical_align: str = "top"  # "top", "middle", "bottom"
    line_height: float = 1.2
    letter_spacing: float = 0.0
    text_decoration: str = "none"  # "none", "underline", "line-through"


class CanvasElement(BaseModel):
    """Single canvas element with flattened type-specific fields."""

    id: str
    type: ElementType
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False
    z_index: int = 0
    fill: dict[str, Any] | None = None  # SolidFill or GradientFill as dict
    stroke: dict[str, Any] | None = None  # Stroke as dict
    shadow: dict[str, Any] | None = None  # Shadow as dict
    corner_radius: float = 0.0

    # Text-specific
    text: str | None = None
    text_style: dict[str, Any] | None = None  # TextStyle as dict

    # Image-specific
    src: str | None = None

    # Path/Line-specific
    points: list[float] | None = None  # [x1, y1, x2, y2, ...]

    # Group-specific
    children: list[str] | None = None  # child element IDs


class CanvasPage(BaseModel):
    """A single page/artboard in the canvas project."""

    id: str
    name: str = "Page 1"
    width: float = 1920.0
    height: float = 1080.0
    background: str = "#FFFFFF"
    elements: list[CanvasElement] = Field(default_factory=list)
    sort_order: int = 0


class CanvasProject(BaseModel):
    """A canvas project owned by a user."""

    id: str
    user_id: str
    session_id: str | None = None  # links to agent session if created by agent
    name: str = "Untitled Design"
    description: str = ""
    pages: list[CanvasPage] = Field(default_factory=list)
    width: float = 1920.0
    height: float = 1080.0
    background: str = "#FFFFFF"
    thumbnail: str | None = None  # base64 or URL
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 200:
            raise ValueError("Name must be between 1 and 200 characters")
        return v

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, v: list[CanvasPage]) -> list[CanvasPage]:
        if len(v) > 50:
            raise ValueError("Maximum 50 pages per project")
        return v


class CanvasVersion(BaseModel):
    """A saved version/snapshot of a canvas project."""

    id: str
    project_id: str
    version: int
    name: str = ""
    pages: list[CanvasPage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
