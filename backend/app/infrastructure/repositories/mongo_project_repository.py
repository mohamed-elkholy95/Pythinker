"""MongoDB implementation of project repository."""

from datetime import UTC, datetime

from app.domain.models.project import Project, ProjectStatus
from app.infrastructure.models.project_documents import ProjectDocument


class MongoProjectRepository:
    """MongoDB implementation of ProjectRepository."""

    async def create(self, project: Project) -> Project:
        document = ProjectDocument.from_domain(project)
        await document.save()
        return document.to_domain()

    async def get_by_id(self, project_id: str, user_id: str) -> Project | None:
        document = await ProjectDocument.find_one(
            ProjectDocument.project_id == project_id,
            ProjectDocument.user_id == user_id,
        )
        return document.to_domain() if document else None

    async def list_by_user(
        self,
        user_id: str,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        query_args = [ProjectDocument.user_id == user_id]
        if status is not None:
            query_args.append(ProjectDocument.status == status.value)
        documents = await ProjectDocument.find(*query_args).sort("-updated_at").skip(offset).limit(limit).to_list()
        return [doc.to_domain() for doc in documents]

    async def update(self, project: Project) -> Project | None:
        document = await ProjectDocument.find_one(
            ProjectDocument.project_id == project.id,
            ProjectDocument.user_id == project.user_id,
        )
        if not document:
            return None
        document.update_from_domain(project)
        document.updated_at = datetime.now(UTC)
        await document.save()
        return document.to_domain()

    async def delete(self, project_id: str, user_id: str) -> bool:
        document = await ProjectDocument.find_one(
            ProjectDocument.project_id == project_id,
            ProjectDocument.user_id == user_id,
        )
        if not document:
            return False
        await document.delete()
        return True

    async def increment_session_count(self, project_id: str, delta: int = 1) -> None:
        document = await ProjectDocument.find_one(
            ProjectDocument.project_id == project_id,
        )
        if document:
            document.session_count = max(0, document.session_count + delta)
            document.updated_at = datetime.now(UTC)
            await document.save()
