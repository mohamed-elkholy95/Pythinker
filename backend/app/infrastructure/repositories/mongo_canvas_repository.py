"""MongoDB implementation of canvas repository."""

from datetime import UTC, datetime

from app.domain.models.canvas import CanvasProject, CanvasVersion
from app.infrastructure.models.canvas_documents import (
    CanvasProjectDocument,
    CanvasVersionDocument,
)


class MongoCanvasRepository:
    """MongoDB implementation of CanvasRepository."""

    async def save(self, project: CanvasProject) -> CanvasProject:
        document = CanvasProjectDocument.from_domain(project)
        await document.save()
        return document.to_domain()

    async def find_by_id(self, project_id: str) -> CanvasProject | None:
        document = await CanvasProjectDocument.find_one(CanvasProjectDocument.project_id == project_id)
        return document.to_domain() if document else None

    async def find_by_session_id(self, session_id: str) -> CanvasProject | None:
        documents = (
            await CanvasProjectDocument.find(CanvasProjectDocument.session_id == session_id)
            .sort("-updated_at")
            .limit(1)
            .to_list()
        )
        return documents[0].to_domain() if documents else None

    async def find_by_user_id(self, user_id: str, skip: int = 0, limit: int = 50) -> list[CanvasProject]:
        documents = (
            await CanvasProjectDocument.find(CanvasProjectDocument.user_id == user_id)
            .sort("-updated_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def update(self, project_id: str, project: CanvasProject) -> CanvasProject | None:
        document = await CanvasProjectDocument.find_one(CanvasProjectDocument.project_id == project_id)
        if not document:
            return None
        document.update_from_domain(project)
        document.updated_at = datetime.now(UTC)
        await document.save()
        return document.to_domain()

    async def delete(self, project_id: str) -> bool:
        document = await CanvasProjectDocument.find_one(CanvasProjectDocument.project_id == project_id)
        if not document:
            return False
        await document.delete()
        return True

    async def count_by_user_id(self, user_id: str) -> int:
        return await CanvasProjectDocument.find(CanvasProjectDocument.user_id == user_id).count()

    async def save_version(self, version: CanvasVersion) -> CanvasVersion:
        document = CanvasVersionDocument.from_domain(version)
        await document.save()
        return document.to_domain()

    async def get_versions(self, project_id: str, limit: int = 20) -> list[CanvasVersion]:
        documents = (
            await CanvasVersionDocument.find(CanvasVersionDocument.project_id == project_id)
            .sort("-version")
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def get_version(self, project_id: str, version: int) -> CanvasVersion | None:
        document = await CanvasVersionDocument.find_one(
            CanvasVersionDocument.project_id == project_id,
            CanvasVersionDocument.version == version,
        )
        return document.to_domain() if document else None

    async def count_versions(self, project_id: str) -> int:
        return await CanvasVersionDocument.find(CanvasVersionDocument.project_id == project_id).count()
