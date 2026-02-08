"""Beanie documents for canvas project persistence."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.domain.models.canvas import CanvasPage, CanvasProject, CanvasVersion
from app.infrastructure.models.documents import BaseDocument


class CanvasProjectDocument(
    BaseDocument[CanvasProject],
    id_field="project_id",
    domain_model_class=CanvasProject,
):
    """MongoDB document for canvas projects."""

    project_id: str
    user_id: str
    session_id: str | None = None
    name: str = "Untitled Design"
    description: str = ""
    pages: list[dict[str, Any]] = Field(default_factory=list)
    width: float = 1920.0
    height: float = 1080.0
    background: str = "#FFFFFF"
    thumbnail: str | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "canvas_projects"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("project_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)]),
            "user_id",
        ]

    def to_domain(self) -> CanvasProject:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("project_id")
        data["pages"] = [CanvasPage.model_validate(p) for p in data.get("pages", [])]
        return CanvasProject.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: CanvasProject) -> "CanvasProjectDocument":
        data = domain_obj.model_dump()
        data["project_id"] = data.pop("id")
        return cls.model_validate(data)


class CanvasVersionDocument(
    BaseDocument[CanvasVersion],
    id_field="version_id",
    domain_model_class=CanvasVersion,
):
    """MongoDB document for canvas project versions."""

    version_id: str
    project_id: str
    version: int
    name: str = ""
    pages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "canvas_versions"
        indexes: ClassVar[list[Any]] = [
            IndexModel(
                [("project_id", ASCENDING), ("version", ASCENDING)],
                unique=True,
            ),
            IndexModel([("project_id", ASCENDING), ("created_at", DESCENDING)]),
        ]

    def to_domain(self) -> CanvasVersion:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("version_id")
        data["pages"] = [CanvasPage.model_validate(p) for p in data.get("pages", [])]
        return CanvasVersion.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: CanvasVersion) -> "CanvasVersionDocument":
        data = domain_obj.model_dump()
        data["version_id"] = data.pop("id")
        return cls.model_validate(data)
