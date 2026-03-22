"""Beanie document for project persistence."""

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.domain.models.project import Project
from app.infrastructure.models.documents import BaseDocument


class ProjectDocument(
    BaseDocument[Project],
    id_field="project_id",
    domain_model_class=Project,
):
    """MongoDB document for projects."""

    project_id: str
    user_id: str
    name: str
    instructions: str = ""
    connector_ids: list[str] = Field(default_factory=list)
    file_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    status: str = "active"
    session_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "projects"
        indexes: ClassVar[list[Any]] = [
            IndexModel([("project_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)]),
        ]

    def to_domain(self) -> Project:
        data = self.model_dump(exclude={"id"})
        data["id"] = data.pop("project_id")
        return Project.model_validate(data)

    @classmethod
    def from_domain(cls, domain_obj: Project) -> "ProjectDocument":
        data = domain_obj.model_dump()
        data["project_id"] = data.pop("id")
        return cls.model_validate(data)
