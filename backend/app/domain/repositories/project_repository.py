"""Repository protocol for project persistence."""

from typing import Protocol

from app.domain.models.project import Project, ProjectStatus


class ProjectRepository(Protocol):
    """Protocol for project persistence."""

    async def create(self, project: Project) -> Project: ...

    async def get_by_id(self, project_id: str, user_id: str) -> Project | None: ...

    async def list_by_user(
        self,
        user_id: str,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]: ...

    async def update(self, project: Project) -> Project | None: ...

    async def delete(self, project_id: str, user_id: str) -> bool: ...

    async def increment_session_count(self, project_id: str, delta: int = 1) -> None: ...
