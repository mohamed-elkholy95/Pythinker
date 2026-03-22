"""Project domain models for organizing sessions under shared context."""

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.domain.models.file import FileInfo


class ProjectStatus(str, Enum):
    """Project lifecycle status."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(BaseModel):
    """Project domain model — container for sessions with shared context."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str
    name: str
    instructions: str = ""
    connector_ids: list[str] = Field(default_factory=list)
    file_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    status: ProjectStatus = ProjectStatus.ACTIVE
    session_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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

    @field_validator("connector_ids", "file_ids", "skill_ids", mode="before")
    @classmethod
    def validate_id_lists(cls, v: list[str]) -> list[str]:
        if len(v) > 50:
            raise ValueError("Maximum 50 items per list")
        return v


def _format_file_size(size_bytes: int | None) -> str:
    """Format bytes to human-readable string."""
    if size_bytes is None:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


class ProjectContext(BaseModel):
    """Resolved project context for agent session injection."""

    instructions: str = ""
    files: list[FileInfo] = Field(default_factory=list)
    connector_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)

    def file_manifest_text(self) -> str:
        """Format file list for system prompt injection."""
        if not self.files:
            return ""
        lines = ["[PROJECT FILES — These files have been uploaded to the sandbox at /home/ubuntu/upload/]"]
        for f in self.files:
            size_str = _format_file_size(f.size) if f.size else "unknown size"
            lines.append(f"- /home/ubuntu/upload/{f.filename} ({size_str})")
        lines.append("[END PROJECT FILES]")
        return "\n".join(lines)

    def instructions_text(self) -> str:
        """Format instructions for system prompt injection."""
        if not self.instructions:
            return ""
        return (
            "[PROJECT INSTRUCTIONS — Follow these instructions for all responses in this project.]\n"
            f"{self.instructions}\n"
            "[END PROJECT INSTRUCTIONS]"
        )

    def has_context(self) -> bool:
        """Return True if any project context is set."""
        return bool(self.instructions or self.files or self.skill_ids)
