"""Request/response schemas for project API."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.domain.models.project import ProjectStatus


class CreateProjectRequest(BaseModel):
    name: str
    instructions: str = ""
    connector_ids: list[str] = []

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name cannot be empty")
        if len(v) > 100:
            raise ValueError("Project name must not exceed 100 characters")
        return v

    @field_validator("instructions", mode="before")
    @classmethod
    def validate_instructions(cls, v: str) -> str:
        if len(v) > 10_000:
            raise ValueError("Instructions must not exceed 10,000 characters")
        return v


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    instructions: str | None = None
    connector_ids: list[str] | None = None
    file_ids: list[str] | None = None
    skill_ids: list[str] | None = None
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    instructions: str
    connector_ids: list[str]
    file_ids: list[str]
    skill_ids: list[str]
    status: ProjectStatus
    session_count: int
    created_at: datetime
    updated_at: datetime


class ProjectListItem(BaseModel):
    id: str
    name: str
    status: ProjectStatus
    session_count: int
    updated_at: datetime
