"""Application service for project management."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.domain.models.file import FileInfo
from app.domain.models.project import Project, ProjectContext, ProjectStatus
from app.infrastructure.repositories.mongo_project_repository import MongoProjectRepository

logger = logging.getLogger(__name__)


class FileInfoResolver(Protocol):
    async def get_file_info(self, file_id: str, user_id: str) -> FileInfo | None: ...


class ProjectService:
    """Business logic for project CRUD and context resolution."""

    def __init__(
        self,
        repo: MongoProjectRepository | None = None,
        file_service_factory: Callable[[], FileInfoResolver] | None = None,
    ) -> None:
        self._repo = repo or MongoProjectRepository()
        self._file_service_factory = file_service_factory

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

        # Resolve file_ids to FileInfo objects
        files: list[FileInfo] = []
        if project.file_ids and self._file_service_factory is not None:
            file_service = self._file_service_factory()
            for fid in project.file_ids:
                try:
                    info = await file_service.get_file_info(fid, user_id)
                    if info:
                        files.append(info)
                except Exception as e:
                    logger.warning(f"Failed to resolve file {fid}: {e}")

        return ProjectContext(
            instructions=project.instructions,
            files=files,
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
                "latest_message": getattr(doc, "latest_message", None),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in documents
        ]


# Singleton factory
_project_service: ProjectService | None = None


def get_project_service(file_service_factory: Callable[[], FileInfoResolver] | None = None) -> ProjectService:
    global _project_service
    if _project_service is None or (
        file_service_factory is not None and _project_service._file_service_factory is not file_service_factory
    ):
        _project_service = ProjectService(file_service_factory=file_service_factory)
    return _project_service
