"""Application service for project management."""

import logging
from datetime import UTC, datetime

from app.domain.models.project import Project, ProjectContext, ProjectStatus
from app.infrastructure.repositories.mongo_project_repository import MongoProjectRepository

logger = logging.getLogger(__name__)


class ProjectService:
    """Business logic for project CRUD and context resolution."""

    def __init__(self) -> None:
        self._repo = MongoProjectRepository()

    async def create_project(
        self,
        user_id: str,
        name: str,
        instructions: str = "",
        connector_ids: list[str] | None = None,
    ) -> Project:
        project = Project(
            user_id=user_id,
            name=name,
            instructions=instructions,
            connector_ids=connector_ids or [],
        )
        return await self._repo.create(project)

    async def get_project(self, project_id: str, user_id: str) -> Project | None:
        return await self._repo.get_by_id(project_id, user_id)

    async def list_projects(
        self,
        user_id: str,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        return await self._repo.list_by_user(user_id, status, limit, offset)

    async def update_project(
        self,
        project_id: str,
        user_id: str,
        updates: dict,
    ) -> Project | None:
        project = await self._repo.get_by_id(project_id, user_id)
        if not project:
            return None

        filtered = {k: v for k, v in updates.items() if v is not None and hasattr(project, k)}
        project = project.model_copy(update=filtered)
        project.updated_at = datetime.now(UTC)
        return await self._repo.update(project)

    async def delete_project(self, project_id: str, user_id: str) -> bool:
        return await self._repo.delete(project_id, user_id)

    async def get_project_context(self, project_id: str, user_id: str) -> ProjectContext | None:
        project = await self._repo.get_by_id(project_id, user_id)
        if not project:
            return None
        return ProjectContext(
            instructions=project.instructions,
            connector_ids=project.connector_ids,
            skill_ids=project.skill_ids,
        )

    async def increment_session_count(self, project_id: str, delta: int = 1) -> None:
        await self._repo.increment_session_count(project_id, delta)

    async def list_project_sessions(
        self, project_id: str, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """List sessions belonging to a project via SessionDocument query."""
        from app.infrastructure.models.documents import SessionDocument

        documents = (
            await SessionDocument.find(
                SessionDocument.project_id == project_id,
                SessionDocument.user_id == user_id,
            )
            .sort("-updated_at")
            .skip(offset)
            .limit(limit)
            .to_list()
        )
        return [
            {
                "session_id": doc.session_id,
                "title": doc.title,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in documents
        ]


# Singleton factory
_project_service: ProjectService | None = None


def get_project_service() -> ProjectService:
    global _project_service
    if _project_service is None:
        _project_service = ProjectService()
    return _project_service
